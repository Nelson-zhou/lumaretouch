"""预览管线：源图与输出帧常驻显存，滑块拖动期间不做逐帧 numpy 往返。

为什么要这一层：M0/M1-1 实测 1280×800 挂管线 34.9 ms/帧，而滤波内核只占 7.9 ms，
剩下的全是 numpy 前后处理与 H2D/D2H——`astype/255` 3.6、转置 2.7、H2D 1.8、
D2H 1.8、`clip*255→uint8` 4.5。也就是说我们花了 4 倍于算法的成本在搬运上。

约定：
- 源图以 uint8 (1,3,H,W) 一次性进显存，之后**不再回 CPU**；
- 每次渲染只改系数（对应滑块值），全程 GPU kernel；
- 输出用一张常驻 (H,W,4) uint8 显存帧，回读一次即共享内存的字节布局，
  不需要 permute/contiguous/tobytes 任何一步额外拷贝。
"""

from __future__ import annotations

from .ops import curves as curve_ops
from .levels_stage import LevelsStage
from .fabric_stage import FabricStage
from .local_grade_stage import LocalGradeStage
from .effect_recovery_stage import EffectRecoveryStage
from .manual_liquify_stage import ManualLiquifyStage
from .studio_background_stage import StudioBackgroundStage
from .optics_stage import OpticsStage
from .reference_color_stage import ReferenceColorStage
from .extended_tone_stage import ExtendedToneStage
from .semantic_colour_stage import SemanticColourStage
from .sky_replacement_stage import SkyReplacementStage

import math
from dataclasses import dataclass

import numpy as np
import time

from .optional_dependencies import optional_module

torch = optional_module("torch")

from .ops.guided import (bands_t, combine_t, mix_masked,
                         DEFAULT_BROAD_GAIN, DEFAULT_DETAIL_GAIN, DEFAULT_EPS,
                         DEFAULT_MID_GAIN, DEFAULT_RADIUS, DEFAULT_TEXTURE_RADIUS)
from .repair_record import DEFAULT_REPAIR, RepairOp, validate_repair_ops
from .repair_replay import replay_repair_t
from .ops.deform import (KINDS, analytic_frontal_landmarks, check_amounts,
                         identity_grid, unit_field, warp_t, prepare_warp_t, apply_prepared_warp_t)
from .ops.light import dodge_burn_t, DEFAULT_DB_EXPOSURE, DEFAULT_DB_RADIUS
from .ops import enhance as ENH
from . import under_eye_layer as UNDER
from . import people_pipeline as PEOPLE_PIPE
from . import lip_makeup_runtime as LIPR, lip_makeup_layer as LIPL, lip_makeup_state as LIPS
from . import brow_shape_runtime as BROWR, brow_shape_state as BROWS, nose_shape_runtime as NOSER, nose_shape_state as NOSES, eye_shape_state as EYES, eye_shape_runtime as EYER, mouth_shape_state as MOUTHS, mouth_shape_runtime as MOUTHR
from . import facial_wrinkle_runtime as WRUNTIME, facial_wrinkle_layer as WLAYER, facial_wrinkle_state as WSTATE
from .ops.grade import (DH_LIMIT, DS_LIMIT, DV_LIMIT, check_params, grade_t)
from .ops.geometry import (MAX_ANGLE as GEOM_ANGLE_LIMIT, check as geometry_check,
                          crop_rotate_t, is_identity as geometry_identity,
                          out_size as geometry_out_size)
from .ops.exposure import (EV_LIMIT, TEMP_LIMIT_K, TINT_LIMIT, REFERENCE_K,
                           check_params as exposure_check, exposure_t)
from .ops.tone import TONE_LIMIT, check_tone
from .ops.hsl import (BAND_CENTERS, BAND_NAMES, HUE_LIMIT as HSL_HUE_LIMIT,
                      LUM_LIMIT as HSL_LUM_LIMIT, SAT_LIMIT as HSL_SAT_LIMIT,
                      check_hsl, hsl_t)
from .custom_lut_asset import CustomCube
from .ops.lut import (DEFAULT_LUT_AMOUNT, QUALITY_SIZE_3D, CubeLut, LutError,
                      apply_lut_t, bake, check_amount)
from .quant import quantize_t

# 磨皮参数默认值只有一个出处：ops.guided（探针量出来的），这里只转发不改数。
# 以前在这里写字面量、server 里又写一份，就是 M1-2 那次「默认值改了但调用方还带着
# 旧字面量」的同构隐患。

@dataclass
class LightOp:
    """一笔修容：只存画笔覆盖度（uint8）与方向符号，**不存结果也不存自己的曝光**。

    为什么曝光/半径是层属性而不是笔属性：产品口径是“修容强度滑块决定最终档数”，
    而档数由 `gain = 2^(exposure·场)` 给出。每笔自带曝光的话，拖滑块时到底按哪一笔算
    就没有答案了；而且那样“多画几笔”会指数叠加把脸烧穿。
    现在的语义：场是各笔带符号覆盖度的**线性累加**（夹到 [-1,1]），exposure 是这层的
    档数上限，笔数决定接近它的程度。三条都有探针用例钉着（抵消/线性累加/饱和）。
    """

    op_id: int
    weight: np.ndarray            # (H,W) uint8，画笔覆盖度
    sign: int = 1                 # +1 减淡 / -1 加深

    @property
    def area_px(self) -> int:
        return int((self.weight > 0).sum())

    def nbytes(self) -> int:
        return int(self.weight.nbytes)


# 肤色定向层的作用域名单（COLOR-004 局部调色）。放在模块层而不是类里：命令层刚收到
# 一条 `grade scope=…` 时还没有可活的会话，“这个作用域存不存在”必须先能回答；而事件
# 载荷与 doc_state 报的都是同一份名单。写两份的下场本仓已经付过很多次学费。
GRADE_SCOPES = ("all", "skin", "brush", "objects")


class PreviewPipeline:
    """一张图的 GPU 常驻预览会话。

    拆成 retouch()/pack() 两步而不是一个大函数，是为了让跑靶能把「滤波内核」
    和「float→uint8 收尾」分开计时——只有分开量，才能证明省下的 25 ms 全在
    搬运上，而不是顺手把算法也跳过了。
    """

    def __init__(self, device: str, w: int, h: int, *, high_precision_warp: bool = False):
        if torch is None:
            raise RuntimeError("torch 未安装，显存常驻预览路径不可用（装 rocm/cuda/cpu 任一变体）")
        self.w, self.h = w, h
        self.high_precision_warp = bool(high_precision_warp)
        want_cuda = device.startswith("cuda")
        if want_cuda and not torch.cuda.is_available():
            # 静默退到 CPU 会让「GPU 常驻」的结论变成假的，必须让调用方能看见
            self.fallback = f"要求 {device}，但 torch.cuda.is_available()=False，已退到 cpu"
            device = "cpu"
        else:
            self.fallback = None
        self.device = torch.device(device)
        self.fabric = FabricStage(self.device)
        self.local_grade_layers = LocalGradeStage(self.device, (h, w))
        self.effect_recovery = EffectRecoveryStage(self.device, (h, w))
        self._effect_recovery_key = None
        self.manual_liquify = ManualLiquifyStage(self.device, (self.h, self.w), self.high_precision_warp)
        self._manual_liquify_key = None
        self.studio_background = StudioBackgroundStage(self.device, (self.h, self.w))
        self._studio_background_key = None
        self.sky_replacement = SkyReplacementStage(self.device, (self.h,self.w))
        self._sky_replacement_key = None
        self.optics = OpticsStage()
        self.extended_tone = ExtendedToneStage(None)
        self.extended_tone_override = None
        self.reference_color = ReferenceColorStage(None)
        self.semantic_colour = SemanticColourStage(None)
        self._optics_key = None
        # 源图 float 与 uint8 都留着：float 供滤波，uint8 供"恢复原图"这类需要原始像素的操作
        self.src_u8: torch.Tensor | None = None
        self.src_f32: torch.Tensor | None = None
        self.frame_gpu: torch.Tensor | None = None   # (H,W,4) uint8，回读即 shm 布局
        # M1-3b：导入期预计算产物也常驻。掩膜 (K,1,H,W) float32，关键点 (478,3) float32。
        # 不进渲染默认路径，只按通道名取用——这样 strength=0 恒等那条承诺不会被掩膜弄碎。
        self.masks_gpu: torch.Tensor | None = None
        self.mask_names: list[str] = []
        self.landmarks_gpu: torch.Tensor | None = None
        # M1-3c：与 strength 无关的滤波结果也常驻。拖滑块期间只重算混合那一步。
        # filter_key 记下这份结果对应哪组参数；源图一变（load_rgb_u8）必须作废。
        self.retouched: torch.Tensor | None = None
        self.filter_key: tuple | None = None
        # M2-a：四条带单独缓存。分带只依赖 (radius, eps, texture_radius)，重组只依赖三个
        # 增益——分两层存，拖“匀肤/细节/肌理”时才不会把 4.5 ms 的分带再跑一遍。
        self.bands: tuple | None = None
        self.bands_key: tuple | None = None
        # 上一次 retouch() 里重算滤波花掉的毫秒；0.0 就是命中缓存。分段计时靠它把
        # 「一次性成本」与「每帧成本」分开上报，不然缓存到底有没有生效看不出来。
        self.last_filter_ms = 0.0
        # 同一次 prepare 里「分带」那一半的成本。报表靠它区分“真的重跑了 guided”
        # 与“只重跑了逐点乘加”——两者都算 last_filter_ms > 0，混在一起就看不出分层有没有生效。
        self.last_bands_ms = 0.0
        # M1-4：消除笔图层。操作列表在 CPU 侧（uint8 画笔），合成结果在显存侧，
        # repair_version 进滤波缓存键——底图变了，旧的那份滤波结果对新底图没有任何意义。
        self.repair_ops: list[RepairOp] = []
        self.redo_ops: list[RepairOp] = []
        self.repair_base: torch.Tensor | None = None
        self.repair_version: int = 0
        self.last_repair_ms: float = 0.0
        self.repair_box: tuple | None = None
        # M2-a2：修容层。它是盖在磨皮**之上**的独立调整层，不是底图的一部分——
        # 为什么不当底图：那样拖“修容强度”滑块会连带把 9 ms 的分带重跑一遍（底图变了）。
        # 当上层则只对 `img` 与 `retouched` 两个混合操作数各施一次 db（~2 ms），
        # 分带缓存原样命中，磨皮的缓存键也一分不改。
        self.light_ops: list[LightOp] = []
        self.light_redo: list[LightOp] = []
        self.light_field_gpu: torch.Tensor | None = None     # (1,1,H,W) float32，带符号
        self.light_version: int = 0                            # 图层内容变了
        self.light_exposure: float = DEFAULT_DB_EXPOSURE
        self.light_radius: int = DEFAULT_DB_RADIUS
        self.light_src: torch.Tensor | None = None             # db(img)
        self.light_src_key: tuple | None = None
        self.light_res: torch.Tensor | None = None             # db(retouched)
        self.light_res_key: tuple | None = None
        self.last_light_ms: float = 0.0
        # M2-b：形变层。存的是每一种形变各自的**单位场**（amount=1 时的位移场），
        # 滑块值只当系数用。为什么能这样拆：TPS 的解对右端项线性，而请求位移与
        # amount 成正比，所以 field(a) = a·field(1) 是恒等而不是近似
        # （探针 m2b4 量到 ‖f(0.5)−0.5·f(1)‖max = 0.000e+00 px）。
        # 于是拖滑块期间一次 TPS 都不解——那玩意在 GPU 上 float64 要 34–79 ms。
        self.deform_units: dict[str, torch.Tensor] = {}
        self.deform_amounts: dict[str, float] = {k: 0.0 for k in KINDS}
        self.deform_grid_base: torch.Tensor | None = None      # 恒等网格，常驻
        self._deform_warp = None
        self._deform_warp_key = None
        self.deform_version: int = 0
        self.deform_meta: dict[str, dict] = {}
        self.last_deform_ms: float = 0.0
        # build_deform 的累计次数。拖滑块期内它必须不增——这才是“零推理”的可测口径：
        # 每帧的 deform ms 无论如何都 > 0（grid_sample 真在跑），拿它当“有没有重算”
        # 的判据会恒真。计数器只能由解算那一层递增，伪代码伪不出一个不增的数。
        self.deform_builds: int = 0
        # M3-a2：调色层。存的是**表本身（CPU 原件 float64）+ 一次上显存的体积**，
        # 每帧只做一次 grid_sample(3d)（产品档实测 0.35 ms）。
        # 它与形变/修容的根本差别：一张 LUT 与像素位置无关，所以它
        # ① 不进滤波缓存键（设完 LUT 拖磨皮滑块仍然零重算），
        # ② 不随底图作废（换图是文档级的事，由命令层清），
        # ③ 只随会话的**设备**重挂——体积张量活在那块卡上，不跟着会话走就是读别的设备的显存。
        self.lut: CubeLut | None = None
        self.lut_vol = None                 # (1,3,D,H,W) float32，常驻；恒等表不挂
        self.lut_amount: float = DEFAULT_LUT_AMOUNT
        self.last_lut_ms: float = 0.0
        # M3-b：肤色定向层。与调色层的分工是探针量出来的（ops/grade.py 头部写了数）：
        # 色彩观平滑，33³ 表复现 2 LSB；肤色窗口在 RGB 里陡峭，同一组参数烘进表要差到
        # 7–9 LSB / 9–10% 像素，所以它**不烘表**，走逐帧内核（实测与 f64 参考差 1 LSB，
        # 而且窗外逐位等于输入）。全图作用域时这一层不持有任何张量（状态就是三个数与
        # 一个混入比例）；局部调色（brush）起会常驻一份掩膜权重，账单走 grade_resident_bytes。
        self.grade_params: tuple = (0.0, 0.0, 0.0)      # (dh, ds, dv)，提交前已过 check_params
        self.grade_amount: float = 1.0
        # COLOR-004 局部调色：这一层原来只能全图。作用域把“调谁”与“调多少”分开，
        # 三个滑块与混入比例的语义一分不改（scope=all 就是旧行为，逐字节相同）。
        self.grade_scope: str = "all"                   # all | skin | brush
        self.grade_mask: "np.ndarray | None" = None     # (H,W) uint8，代理帧坐标的画笔覆盖度
        self._grade_mask_gpu = None                     # (1,1,H,W) float，brush 时才常驻
        self._local_mask_gpu = None
        self.local_mask_suspended = None
        self.last_grade_ms: float = 0.0
        # PORTRAIT-009：眼牙局部增强（眼白 / 虹膜 / 牙齿，三个子功能独立启停）。
        # 它持有的是**权重场**（不是参数）：几何 ∩ 内容门在挂层时算一次，每帧只做逐点乘加。
        # 为什么不在每帧算门：内容门要算池均值，那是一次 D2H 同步，而拖滑块期间每帧一次
        # 就是断帧的来源（与形变的“单位场只解一次、拖滑块只当系数”同一条理由）。
        # 判据取**源片**那份颜色而不是屏幕上那份：这一层找的是“这里是不是眼白/牙齿”
        # （身份），身份必须在未上色的像素上判，否则一张橙色 LUT 会把嘴唇认成牙齿
        # （与肤色定向“所见即所调”的口径相反，差别写在 ops/enhance.py 头部）。
        WRUNTIME.clear_face(self)
        LIPR.clear_face(self); self.lip_makeup = LIPS.neutral(); self.lip_makeup_suspended = None
        BROWR.clear(self); self.brow_shape = BROWS.neutral(); self.brow_shape_suspended = None
        NOSER.clear(self); self.nose_shape = NOSES.neutral(); self.nose_shape_suspended = None
        EYER.clear(self)
        self.eye_shape = EYES.neutral()
        self.eye_shape_suspended = None
        MOUTHR.clear(self)
        self.mouth_shape = MOUTHS.neutral()
        self.mouth_shape_suspended = None
        self.enhance_amounts: dict = {k: 0.0 for k in ENH.AMOUNT_KEYS}
        WRUNTIME.clear_layer(self)
        self.enhance_lm_sig = None
        self.under_eye_layer = None
        self.under_eye_delta = None
        self.under_eye_local = None
        self.enhance_field = None        # (3,fh,fw) float32 [0,1]，窗口那一片的权重原件
        self.enhance_gpu = None          # 同一份的上卡副本
        self.enhance_window = None       # 画布坐标 (y0,x0,fh,fw)（报出去用）
        self.enhance_local = None        # 本会话坐标 (ly0,lx0,lh,lw)（每帧切片用）
        self.enhance_facts: dict = {}    # 每子功能的一手事实：几何 px、门后 px、拒绝原因
        # 画这张场用的那份关键点的指纹。它只回答一件事："几何有没有变"——滑块动而几何
        # 没动时不许重画（重画是每事件一次栅格化 + 内容门 + 一次 D2H，实测 12 ms/次，
        # 而拖动期间真正要付的只有窗口内那一次逐点乘加，实测 1 ms 级）。与形变层同一
        # 分工：build 认几何，set 认系数。进程内稳定即可（跨进程要重画，本来也是）。
        self.enhance_lm_sig: int | None = None
        self.enhance_info: dict = {}     # 几何读数（开口度、虹膜半径、星形校验结果）
        self.last_enhance_ms: float = 0.0
        self.enhance_build_ms: float = 0.0
        # P0：全局曝光与白平衡层（lnx.exposure / lnx.white_balance）。与定向层同构：
        # 状态就是三个数 + 一个参考白，不持有任何张量，所以它既不参缓存键也不随设备重挂。
        # 中性默认 (0,0,0)：这一层的 identity 必须是逐字节恒等（ADR-0003 定的容差 0），
        # 所以没点火时 apply 一步直接递回原张量，一个算子也不跑。
        self.crop_rect: tuple = (0.0, 0.0, 1.0, 1.0)      # 归一化裁剪框（P0 lnx.crop.v1）
        self.crop_rotation: float = 0.0                   # 角度，正=顺时针
        self.last_geometry_ms = 0.0
        # (ev, temperature_shift, tint_shift, contrast, highlights, shadows, saturation)
        # 影调四项与 EV 同一层：都是逐点、无位置、无掩膜的整图变换。
        self.exposure_params: tuple = (0.0,) * 7
        self.exposure_ref_k: float = REFERENCE_K
        self.wb_options = None
        self.prepared_wb = None
        self.last_exposure_ms: float = 0.0
        # 八色 HSL（原创扩展）：与曝光层同一条纪律（逐点、无位置、无掩膜、中性逐
        # 字节恒等），但它是按色相分段的窗口变换，所以单独一组数、单独一帧记账。
        # 24 个数 = 8 段 × (色相偏移, 饱和度, 明亮度)；全 0 时 apply 一步递回。
        self.hsl_bands: tuple = (0.0,) * 24
        self.last_hsl_ms: float = 0.0
        self.levels_stage = LevelsStage()
        self.curves_spec = curve_ops.default_curves()
        self.curves_compiled = (None,) * 5
        self.last_curves_ms = 0.0
        # M6：换底层。挂在渲染链最尾（肤色之后、量化之前），是逐帧的 `α·前景+(1-α)·背景`。
        # 与其它层的差别：遮罩是按**这一档代理帧像素坐标**成立的，所以它随代理档作废
        # （进 PROXY_BOUND），也随设备重挂（遮罩张量活在那块卡上）。没活时 apply 一步直接
        # 把张量递回，一个算子都不跑——strength=0/没换底那帧的逐字节恒等承诺一分不改。
        self.bg_matte = None        # (1,1,H,W) float32 [0,1]，常驻
        self.bg_ref = None          # (1,3,1,1) float32 [0,1]（单色背景）或 (1,3,H,W)（整幅背景）
        self.bg_active = False
        self.last_bg_ms: float = 0.0

    # ---- 装载：一次性 H2D ----------------------------------------------
    def load_rgb_u8(self, rgb: np.ndarray) -> None:
        """(H,W,3) uint8 → 显存常驻。整场会话只调一次（导入或换图时）。"""
        if rgb.shape[:2] != (self.h, self.w):
            raise ValueError(f"源图尺寸 {rgb.shape[:2]} != 会话 {self.h}x{self.w}")
        arr = np.ascontiguousarray(rgb.transpose(2, 0, 1))[None]
        # 不开 non_blocking：从 pageable 内存异步上传，调用方一释放这块 numpy 就是未定义行为；
        # 这里整场会话只走一次，同步拷贝不花什么钱。
        u8 = torch.from_numpy(arr).to(self.device)
        self._begin_source(u8.to(torch.float32).div_(255.0), src_u8=u8)

    def load_rgb_f32(self, rgb: np.ndarray) -> None:
        """(H,W,3) float32 ∈ [0,1] → 显存常驻。**导出通路专用**。

        为什么要有这条入口：全尺寸导出的底图是"消除笔在满幅算完的那份结果"，而它是
        float。走 load_rgb_u8 就得先 round 成 uint8 再除回 255，导出的底图比预览少一整档
        精度——"导出与预览是同一条链"这句话当场就假了（M2-a2 那个向零截断的坑就是同一
        类：只在不在格点上时才露出来）。

        src_u8 留 None 是有意的：这条会话没有原始像素。谁要"恢复原图"就得拿到一句明确
        的 None 拒绝，而不是拿一份已经过 round 的底图悄悄当原图用。
        """
        if rgb.shape[:2] != (self.h, self.w):
            raise ValueError(f"源图尺寸 {rgb.shape[:2]} != 会话 {self.h}x{self.w}")
        if rgb.dtype != np.float32:
            raise ValueError(f"load_rgb_f32 要 float32，得到 {rgb.dtype}："
                             "上游换了 dtype 会让导出与预览不是同一个数")
        if not np.isfinite(rgb).all():
            raise ValueError("源图含非有限值：NaN 会一路渗进常驻缓存与滤波结果")
        arr = np.ascontiguousarray(rgb.transpose(2, 0, 1))[None]
        self._begin_source(torch.from_numpy(arr).to(self.device), src_u8=None)

    def _begin_source(self, src_f32, *, src_u8) -> None:
        """两条装载入口的公共体：会话状态的重置只有一份，不靠"两边都记得改"。"""
        self.src_u8 = src_u8
        self.fabric.clear()
        self.local_grade_layers.set([])
        self._local_grade_layers_key = None
        self.effect_recovery = EffectRecoveryStage(self.device, (self.h, self.w))
        self._effect_recovery_key = None
        self.manual_liquify = ManualLiquifyStage(self.device, (self.h, self.w), self.high_precision_warp)
        self._manual_liquify_key = None
        self.studio_background = StudioBackgroundStage(self.device, (self.h, self.w))
        self._studio_background_key = None
        self.sky_replacement = SkyReplacementStage(self.device, (self.h,self.w))
        self._sky_replacement_key = None
        self.optics = OpticsStage()
        self.extended_tone = ExtendedToneStage(None)
        self.extended_tone_override = None
        self.reference_color = ReferenceColorStage(None)
        self.semantic_colour = SemanticColourStage(None)
        self._optics_key = None
        self.src_f32 = src_f32
        self.frame_gpu = torch.empty((self.h, self.w, 4), dtype=torch.uint8, device=self.device)
        self.frame_gpu[..., 3] = 255
        # 换图就是换源张量：旧滤波结果对新图没有任何意义，继续用等于拿别人的脸磨自己的皮
        self.retouched = None
        self.filter_key = None
        self.bands = None
        self.bands_key = None
        self.last_filter_ms = 0.0
        self.last_bands_ms = 0.0
        # 同理，上一张图的画笔坐标与新图毫无关系：不清的话新图会凭空长出几个坑
        self.repair_ops = []
        self.redo_ops = []
        self.repair_base = None
        self.repair_box = None
        self.repair_version += 1
        self.last_repair_ms = 0.0
        self._reset_light()
        self._reset_deform()
        self._reset_enhance()
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)

    def _reset_enhance(self) -> None:
        """换图/换代理档时清增强层：权重场画在**这一档画布**的坐标上，对下一张图没有意义。

        只放场、不放参数：参数（三个数）是用户意图，属于文档状态，由命令层与工程档管；
        场是这份意图在这张图上的落地物，可以随时从关键点重算。
        """
        WRUNTIME.clear_face(self)
        LIPR.clear_face(self); self.lip_makeup = LIPS.neutral(); self.lip_makeup_suspended = None
        BROWR.clear(self); self.brow_shape = BROWS.neutral(); self.brow_shape_suspended = None
        NOSER.clear(self); self.nose_shape = NOSES.neutral(); self.nose_shape_suspended = None
        EYER.clear(self)
        self.eye_shape = EYES.neutral()
        self.eye_shape_suspended = None
        MOUTHR.clear(self)
        self.mouth_shape = MOUTHS.neutral()
        self.mouth_shape_suspended = None
        self.enhance_lm_sig = None
        self.under_eye_layer = None
        self.under_eye_delta = None
        self.under_eye_local = None
        self.enhance_field = None
        self.enhance_gpu = None
        self.enhance_window = None
        self.enhance_local = None
        self.enhance_facts = {}
        self.enhance_info = {}
        self.enhance_build_ms = 0.0
        self.last_enhance_ms = 0.0

    def _reset_deform(self) -> None:
        """换图时清形变层：单位场是从这张图的关键点解出来的，对下一张图没有意义。"""
        self._deform_warp = None
        self._deform_warp_key = None
        self.deform_units = {}
        self.deform_amounts = {k: 0.0 for k in KINDS}
        self.deform_grid_base = None
        self.deform_meta = {}
        self.deform_version += 1
        self.last_deform_ms = 0.0

    def _reset_light(self) -> None:
        """换图时清空修容层：上一张图的笔迹坐标与新图没有任何关系。"""
        self.light_ops = []
        self.light_redo = []
        self.light_field_gpu = None
        self.light_version += 1
        self.light_src = None
        self.light_src_key = None
        self.light_res = None
        self.light_res_key = None
        self.last_light_ms = 0.0

    # ---- 渲染：全 GPU，无 CPU 参与 --------------------------------------
    @staticmethod
    def _filter_parameters(radius, eps, detail_gain, mid_gain, broad_gain, texture_radius):
        # 先把入参归一化再算键：键与实际执行必须来自同一个值。之前是 int(radius) 进键、
        # 原始的 radius 进滤波，传 12.5 时键说 12 而算的是 12.5——两个不同的滤波结果会
        # 撞同一个键，下次拿到的就是错的那份。
        r = int(radius)
        e = float(eps)
        rf = int(texture_radius)
        g = float(detail_gain)
        mg = float(mid_gain)
        bg = float(broad_gain)
        # eps 必须严格为正：`a = var/(var+eps)` 在 eps=0 时于平坦皮区算 0/0，产出 NaN
        # （产品档实测 402795 个子像素 NaN）。radius=0 在库层是合法的退化恒等滤波（输出有限、
        # strength=0 仍逐字节成立），协议层另有下界拦住它带来的"空滑块"。
        if r < 0 or rf < 0 or e <= 0.0 or not (math.isfinite(e) and math.isfinite(g)
                                              and math.isfinite(mg) and math.isfinite(bg)):
            raise ValueError(f"磨皮参数非法：radius={r}（需 ≥0）、texture_radius={rf}（需 ≥0）、"
                             f"eps={e}（需 >0 的有限值）、三个增益（需有限值）")
        return r, e, rf, g, mg, bg

    def prepare(self, radius: int = DEFAULT_RADIUS, eps: float = DEFAULT_EPS,
                detail_gain: float = DEFAULT_DETAIL_GAIN,
                mid_gain: float = DEFAULT_MID_GAIN,
                broad_gain: float = DEFAULT_BROAD_GAIN,
                texture_radius: int = DEFAULT_TEXTURE_RADIUS, force: bool = False) -> float:
        """把滤波结果备好并常驻，返回本次重算的毫秒数；0.0 表示命中缓存没有重算。

        拖滑块期间这个 0.0 才是常态：strength 不进滤波，只在混合那一步当系数。

        M2-a 把它拆成两层：
          1) 分带 bands_t：贵（产品档 ~5 ms），只随 (radius, eps, texture_radius, 底图) 变；
          2) 重组 combine_t：便宜（逐点乘加），只随三个增益变。
        以前三个增益任何一个动一下都要把整条 guided 链重跑；现在拖“肌理/细节/匀肤”
        只付第 2 层。第 1 层的实际花费记在 last_bands_ms 里，报表能分开看。
        """
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb_u8 再 prepare")
        r, e, rf, g, mg, bg = self._filter_parameters(
            radius, eps, detail_gain, mid_gain, broad_gain, texture_radius)
        bands_key = (r, e, rf, self.repair_version)
        # 成品键把修补版本放最后一位（M1-3c 起就是这个约定，测试与报表都按它读）：
        # 前面六个全是磨皮参数，第 7 位是底图身份。
        key = (r, e, rf, bg, mg, g, self.repair_version)
        if not force and self.retouched is not None and self.filter_key == key:
            self.last_filter_ms = 0.0
            self.last_bands_ms = 0.0
            return 0.0
        t0 = time.perf_counter()
        if force or self.bands is None or self.bands_key != bands_key:
            tb = time.perf_counter()
            got = bands_t(self.base(), radius=r, eps=e, texture_radius=rf)
            # 最后一道防线：不把非有限值写进常驻缓存。缓存里的 NaN 会长期作恶——
            # `(1-0)*img + 0*NaN` 仍是 NaN，strength=0 的逐字节恒等当场失效。
            # 代价是重算路径上多一次归约与同步（只在换图/换参数时发生，不在拖拽热路径上）。
            if not all(torch.isfinite(t).all() for t in got):
                self.bands = None
                self.bands_key = None
                raise ValueError(f"分带产出非有限值，已拒绝写入常驻缓存："
                                 f"radius={r} eps={e} texture_radius={rf}")
            self.bands = got
            self.bands_key = bands_key
            self.last_bands_ms = (time.perf_counter() - tb) * 1000.0
        else:
            self.last_bands_ms = 0.0
        out = combine_t(*self.bands, broad_gain=bg, mid_gain=mg, detail_gain=g)
        if not torch.isfinite(out).all():
            raise ValueError(f"滤波产出非有限值，已拒绝写入常驻缓存："
                             f"radius={r} eps={e} 增益=({bg},{mg},{g})")
        self.retouched = out
        self.filter_key = key
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_filter_ms = (time.perf_counter() - t0) * 1000.0
        return self.last_filter_ms

    def retouch(self, strength: float, radius: int = DEFAULT_RADIUS,
                eps: float = DEFAULT_EPS, detail_gain: float = DEFAULT_DETAIL_GAIN,
                mid_gain: float = DEFAULT_MID_GAIN,
                broad_gain: float = DEFAULT_BROAD_GAIN,
                texture_radius: int = DEFAULT_TEXTURE_RADIUS,
                channel: str | None = None, scope_tap=None, render_stage="output"):
        """只跑算法，返回显存里的 float (1,3,H,W)。滑块每动一次调一次。

        channel 给定时走分通道渲染（掩膜加权），不给定时全图。两条都是纯 GPU。

        M1-3c：滤波结果走常驻缓存，这一步退化成一个线性插值。缓存路径与逐帧重算
        不是“近似相等”而是逐字节相等——混合用的表达式与操作数都完全相同：
        全图 `(1-s)*img + s*out`，分通道 `mix_masked(img, out, s, weight)`。
        因此 strength=0 恒等那条承诺一分不改：`0*out` 仍然恒为 0。
        """
        from .people_engine_runtime import require_ready
        require_ready(self)
        if render_stage not in ('output', 'wb-input', 'extended-tone-input', 'optics-input'):
            raise ValueError('Unknown production render stage')
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb_u8 再 render")
        # 每帧的 db 应用成本从 0 起算：它必须只由“这一帧真跑了什么”给出，
        # 不能把上一次建层的成本混进来（那是事件驱动的一次性账，另走 light_ms）
        self.last_light_ms = 0.0
        if strength == 0.0:
            # No filtered contribution: validate the same contract, then avoid
            # full-frame bands/allocation. Do not discard a useful warm cache.
            self._filter_parameters(radius, eps, detail_gain, mid_gain, broad_gain, texture_radius)
            if channel is not None:
                self.mask(channel)  # missing/unknown masks must still be rejected
            self.last_filter_ms = self.last_bands_ms = 0.0
            out = self.lighten_source()  # keep repair + dodge/burn, NOT original-view bypass
        else:
            self.prepare(radius=radius, eps=eps, detail_gain=detail_gain,
                         mid_gain=mid_gain, broad_gain=broad_gain,
                         texture_radius=texture_radius)
            base = self.lighten_source()
            result = self.lighten_result()
            out = mix_masked(base, result, strength, self.mask(channel)) if channel is not None \
                else (1.0 - strength) * base + strength * result
            # Recover only smoothing's contribution, preserving repair and light.
            out = self.effect_recovery.apply('skin_smoothing', base, out)
        # Actual order: repair/light + smoothing/recovery -> fabric/recovery ->
        # studio -> facial wrinkles/recovery -> auto+brow+nose ONE warp -> enhance -> exposure -> levels -> curves -> HSL ->
        # LUT -> legacy grade -> independent local grades -> background/recovery
        # -> manual liquify -> geometry. Source masks stay at their own consumers;
        # the final manual stage moves the complete processed RGB only.
        # Recovery at an operator mixes only that operator's own input/output;
        # later effects continue to consume the recovered pixels normally.
        out = self.effect_recovery.apply('fabric_fine', out, self.fabric.apply(out))
        out = self.studio_background.apply(out)
        if PEOPLE_PIPE.active(self):
            out=PEOPLE_PIPE.source_effect(self,'facial_wrinkles',out)
            out=PEOPLE_PIPE.source_effect(self,'lip_makeup',out)
            out=PEOPLE_PIPE.source_effect(self,'blush_makeup',out)
            out=PEOPLE_PIPE.source_effect(self,'lipstick',out)
            out=PEOPLE_PIPE.source_effect(self,'eyeliner',out)
            out=PEOPLE_PIPE.source_effect(self,'eyelash',out)
            out=PEOPLE_PIPE.source_effect(self,'brow_makeup',out)
            out=PEOPLE_PIPE.source_effect(self,'iris_makeup',out)
            out=PEOPLE_PIPE.source_effect(self,'hair_colour',out)
            out=PEOPLE_PIPE.source_effect(self,'eye_light',out)
        else:
            WLAYER.refresh_source(self)
            out = self.effect_recovery.apply('facial_wrinkles', out, WLAYER.apply_delta(self, out))
            LIPR.refresh_source(self)
            out = self.effect_recovery.apply('lip_makeup', out, LIPL.apply_delta(self, out))
        out = self.apply_enhance(self.apply_deform(out))
        if scope_tap is not None: scope_tap("wb-input", out)
        if render_stage == 'wb-input':
            return out
        out = self.apply_exposure(out)
        if render_stage == 'extended-tone-input':return out
        out = self.extended_tone_override if self.extended_tone_override is not None else self.extended_tone.apply_t(out)
        if scope_tap is not None: scope_tap("levels-input", out)
        out = self.apply_levels(out)
        if scope_tap is not None: scope_tap("curves-input", out)
        out = self.apply_grade(self.apply_lut(self.apply_hsl(self.apply_curves(out))))
        out = self.local_grade_layers.apply(out, self.align_source_grade_mask)
        out = self.sky_replacement.apply(out,self.align_source_grade_mask)
        out = self.apply_background(out)
        out = self.manual_liquify.apply(out)
        if render_stage == 'optics-input': return out
        out = self.optics.apply(out)
        out = self.apply_geometry(out)
        out = self.reference_color.apply_t(out)
        out = self.semantic_colour.apply_t(out,strict=False)
        out = self.extended_tone.finish_t(out)
        if scope_tap is not None: scope_tap("output", out)
        return out

    # ---- M1-3b：预计算产物的常驻与取用 ------------------------------------
    def load_face(self, precompute) -> dict:
        """把人脸关键点与语义掩膜一次性上显存。整张图只走这一次。"""
        # Masks describe geometry, not the storage dtype of the source. Export
        # keeps repaired pixels in float32 so attaching masks must not require
        # manufacturing a rounded uint8 "original".
        if self.src_f32 is None:
            raise RuntimeError("先装载源图：掩膜尺寸必须对得上会话尺寸")
        arr, names = precompute.stack()
        if arr.shape[1:] != (self.h, self.w):
            raise ValueError(f"掩膜尺寸 {arr.shape[1:]} != 会话 {(self.h, self.w)}，"
                             "预计算必须跟代理帧跑，不能拿原分辨率的掩膜来挂")
        masks = torch.from_numpy(np.ascontiguousarray(arr[:, None])).to(self.device)
        lm = torch.from_numpy(precompute.landmarks).to(self.device)
        # 常驻字节数与 CPU 原件必须等量：这是上报里 mask_bytes / landmark_bytes 唯一的出处。
        # 不校验的话“H2D 被截断”或“路上换了 dtype”在报表上仍是一个自洽的数，与 M1-3a
        # 那个「会话在 CPU 上跑却标 cuda」同属一类。校验放在赋值前：失败时旧产物原样留着，
        # 不会把会话变成「半张脸在显存里」那种更难查的状态。
        mb = int(masks.numel() * masks.element_size())
        lb = int(lm.numel() * lm.element_size())
        if mb != arr.nbytes or lb != int(precompute.landmarks.nbytes):
            raise RuntimeError(
                f"上显存后字节变了：掩膜 {arr.nbytes}→{mb}、关键点 "
                f"{precompute.landmarks.nbytes}→{lb}；常驻张量与 CPU 原件不是同一份东西")
        # 先写新引用再释放旧张量：掩膜按通道堆在一起，旧的不放会多占一份显存
        # （torch 会自动回收引用计数的旧张量，这里注释只说清为什么不需要手动 clear）
        WRUNTIME.install_face(self, precompute)
        LIPR.install_face(self, precompute)
        self.masks_gpu = masks
        self.mask_names = names
        self.landmarks_gpu = lm
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        return {
            "mask_channels": names,
            "mask_bytes": mb,
            "landmark_bytes": lb,
            "resident_device": str(self.device),
        }

    def clear_face(self) -> None:
        """换图 / 换设备前调用：旧会话的预计算产物对新图没有任何意义。"""
        self.masks_gpu = None
        self.mask_names = []
        self.landmarks_gpu = None
        WRUNTIME.clear_face(self)
        LIPR.clear_face(self); self.lip_makeup = LIPS.neutral(); self.lip_makeup_suspended = None
        BROWR.clear(self); self.brow_shape = BROWS.neutral(); self.brow_shape_suspended = None
        NOSER.clear(self); self.nose_shape = NOSES.neutral(); self.nose_shape_suspended = None
        EYER.clear(self)
        self.eye_shape = EYES.neutral()
        self.eye_shape_suspended = None
        MOUTHR.clear(self)
        self.mouth_shape = MOUTHS.neutral()
        self.mouth_shape_suspended = None
        # 调色作用域里 skin 是唯一靠掩膜活着的那个：掩膜一走还留着 scope=skin，
        # 下一帧渲染就是一条取不到权重的异常（与下面单位场“无源之水”同一条理由）。
        # brush 靠的是自己那份区域，不受 clear_face 影响。
        # Missing semantic analysis suspends grade; it never widens to all.
        # 单位场是从关键点解出来的，关键点一走它们就成了无源之水：继续用等于
        # 拿上一张脸的形状去瘦这一张脸
        if self.deform_units:
            self.clear_deform()

    def mask(self, channel: str):
        """按名字取一个常驻掩膜通道，形状 (1,1,H,W)，可直接与 (1,3,H,W) 广播。"""
        if self.masks_gpu is None:
            raise RuntimeError("尚未 load_face，没有可用掩膜")
        if channel not in self.mask_names:
            raise KeyError(f"没有通道 {channel}（可用：{', '.join(self.mask_names)}）")
        return self.masks_gpu[self.mask_names.index(channel):self.mask_names.index(channel) + 1]

    def face_resident_bytes(self) -> int:
        total = 0
        for t in (self.masks_gpu, self.landmarks_gpu):
            if t is not None:
                total += int(t.numel() * t.element_size())
        return total

    def filter_resident_bytes(self) -> int:
        """M1-3c 那份常驻滤波结果的字节数——零推理换来的显存代价，必须能看见。"""
        if self.retouched is None:
            return 0
        return int(self.retouched.numel() * self.retouched.element_size())

    def bands_resident_bytes(self) -> int:
        """M2-a 四条带的常驻字节。分带比成品多 4 份张量，不报就等于藏了一笔显存账。"""
        if self.bands is None:
            return 0
        return sum(int(t.numel() * t.element_size()) for t in self.bands)

    def drop_product(self) -> None:
        """只丢重组好的成品：下一次 prepare 命中分带、只重跑逐点乘加。"""
        self.retouched = None
        self.filter_key = None
        # db(成品) 以成品为入，它没了就必须跟着没；不丢的话下一次 prepare 算出新
        # 成品后，旧键里的 filter_key 已变，不会拿错——但旧张量会白占一份显存
        self._light_cache_drop("res")

    def drop_cache(self) -> None:
        """两层缓存全丢：下一次 prepare 从底图重跑整条滤波链。

        这个方法为什么在库里而不是各跑靶里各写一份：M2-a 把缓存拆成两层之后，只清
        成品已不等于“逐帧重算”了（分带还会命中）。跑靶里的“重算臂”如果漏了清分带，
        量到的就是重组那一条路，而 `last_filter_ms > 0` 会让它自检不出错——
        一个看起来完全正常、实则两臂在量同一条路的坑。定义放在执行侧比放在调用方安
        全：只有一个出处会漂。

        修容的两份 db 结果也一起清：它们以成品为入，成品都没了它们就是无源之水。
        跑靶的“全重算臂”如果漏这一句，量的就不是产品通路了。
        """
        self.drop_product()
        self.bands = None
        self.bands_key = None
        self._light_cache_drop("src")
        self._light_cache_drop("res")

    # ---- M1-4：消除笔图层（事件驱动） ------------------------------------
    def base(self):
        """当前送去滤波的底图：没打过消除笔就是原图，打过就是修补结果。

        修补必须在磨皮**之前**：否则引导滤波会把痘印当成“皮肤细节”去保边，
        强度一拉反而把它围出一圈更明显的亮环。
        """
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb_u8")
        return self.src_f32 if self.repair_base is None else self.repair_base

    def set_repair_ops(self, ops: list, redo: list | None = None) -> dict:
        """整体挂上一组操作（换设备重建时用）：只认输入，不认旧结果。

        redo 也一并带过来：产品口径是“撤销/重做/换设备都靠重放”，不带上 redo 栈
        就等于切一次设备静默抹掉重做历史。返回重建信息（与 add_repair 同一份口径）。
        """
        return self._commit_repair(list(ops), list(redo) if redo is not None else [])

    def add_repair(self, op: "RepairOp") -> dict:
        if op.weight.shape != (self.h, self.w):
            raise ValueError(f"画笔覆盖度尺寸 {op.weight.shape} != 会话 {(self.h, self.w)}，"
                             "画笔必须画在代理帧坐标系上")
        if op.weight.dtype != np.uint8:
            raise ValueError(f"画笔覆盖度必须是 uint8（0..255），得到 {op.weight.dtype}")
        # 新操作发生在新一次重做之上，旧 redo 栈就失效了：留着它，“重做”会拿到一个
        # 与当前图层列表都不兼容的状态
        return self._commit_repair(self.repair_ops + [op], [])

    def undo_repair(self) -> dict | None:
        if not self.repair_ops:
            return None
        last = self.repair_ops[-1]
        info = self._commit_repair(self.repair_ops[:-1], self.redo_ops + [last])
        info["undone_ops"] = len(self.repair_ops) + 1
        return info

    def redo_repair(self) -> dict | None:
        if not self.redo_ops:
            return None
        last = self.redo_ops[-1]
        info = self._commit_repair(self.repair_ops + [last], self.redo_ops[:-1])
        info["redone_ops"] = len(self.repair_ops)
        return info

    def clear_repair(self, keep_redo: bool = True) -> dict:
        return self._commit_repair([], self.redo_ops if keep_redo else [])

    def _commit_repair(self, ops: list, redo: list) -> dict:
        """按操作顺序逐笔重建修补底图，**全部算完才一次性提交**常驻状态。

        为什么逐笔而不是把掩膜并成一整块再一次算：实测两笔分开画在脸两侧时，
        合并后的 bbox 等于整幅（裁块优势归零），而并集掩膜还会让第二笔的周围
        含上第一笔的旧坑。逐笔应照操作顺序重放，与“只存输入”的非破坏原则同一条。

        为什么要“算进局部、成功才写回”：`inpaint_t`/`crop_apply_t` 完全可能抛
        （裁块过大 OOM、越界）。旧写法先把 op append 进列表、再把 `repair_base` 置 None，
        异常劈在中间就会留下三半状态：图层已含新笔、底图却是旧的（None ⇒ 回落
        src_f32）、而 `repair_version` 没变 ⇒ 下一次拖滑块的滤波缓存**精确命中旧结果**。
        新底图 × 旧滤波混进同一帧，看上去完全正常、语义是错的。现在异常路径一
        个字也不改，提交点后面的步骤不会再失败。

        上报里 `repair_ms` 就是这个重建成本。拖滑块期间它是 0——不是“没量到”，
        而是这一步真的没被执行（render 只读现成的 repair_base）。
        """
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb_u8 再打消除笔")
        t0 = time.perf_counter()
        validate_repair_ops(redo, shape=(self.h, self.w))
        cur, boxes, painted = replay_repair_t(self.src_f32, ops)
        base = cur if cur is not self.src_f32 else None
        box0 = boxes[0] if len(boxes) == 1 else None
        ms = (time.perf_counter() - t0) * 1000.0
        # ---- 提交点：到这里后面全是赋值，没有可失败的步骤 ----
        self.repair_ops = ops
        self.redo_ops = redo
        self.repair_base = base
        self.repair_box = box0
        self.repair_version += 1
        self.retouched = None          # 底图变了，滤波缓存立即作废（不靠下一次发现）
        self.filter_key = None
        self.bands = None              # 分带缓存同理：旧底图的带对新底图没有意义
        self.bands_key = None
        self.last_repair_ms = ms
        return {
            "repair_ms": round(ms, 2),
            "ops": len(ops),
            "applied": len(boxes),
            "redo_pending": len(redo),
            "painted_px": painted,
            "boxes": boxes,
            "bytes_base": self.repair_resident_bytes(),
            # 不叫 cached：cmd 层会在 `**info` 之后写一条同名的 filter_cached（滤波命中缓存），
            # 两件事一个名字就是字典后写吃掉先写。这条只说“本层真的重算了”。
            "layer_recomputed": True,
        }

    def repair_resident_bytes(self) -> int:
        """修补底图 + 画笔列表的常驻字节（显存与 CPU 侧分开看）。"""
        gpu = 0 if self.repair_base is None else int(self.repair_base.numel() * self.repair_base.element_size())
        cpu = sum(op.nbytes() for op in self.repair_ops) + sum(op.nbytes() for op in self.redo_ops)
        return gpu + cpu

    # ---- M2-a2：修容层（盖在磨皮之上的独立调整层，事件驱动） --------------
    def has_light(self) -> bool:
        """这一层到底有没有活。没活就一个算子都不跑，两个操作数原样进混合。

        曝光必须先是**有限数**：NaN != 0.0 在 Python 里为真，拿它当“生效”会让一层
        本来算不出来的东西被报成在生效，而每帧渲染到 dodge_burn 才抛——现场与病因
        隔了两个模块。这里当场判假（渲染路径同样有 _check 拦，两条不矛盾）。
        """
        e = float(self.light_exposure)
        return self.light_field_gpu is not None and math.isfinite(e) and e != 0.0

    def _light_cache_get(self, which: str):
        return (self.light_src, self.light_src_key) if which == "src" \
            else (self.light_res, self.light_res_key)

    def _light_cache_set(self, which: str, t, key: tuple) -> None:
        if which == "src":
            self.light_src, self.light_src_key = t, key
        else:
            self.light_res, self.light_res_key = t, key

    def _light_cache_drop(self, which: str) -> None:
        self._light_cache_set(which, None, None)

    def _apply_light_cached(self, t, which: str):
        """对一份常驻张量施加当前修容层，结果也常驻。

        which="src" 作用于底图（strength=0 那一侧），"res" 作用于磨皮结果（strength=1 那一侧）。
        两份分开存是必然的：修容与磨皮强度语义上独立，只存一份就得在拖 strength
        时重算，零推理那条承诺就碎了。
        """
        if not self.has_light():
            # 不短路时也得把旧缓存放下：不然下次开修容而参数恰好撞上旧键，就会拿到
            # 一份属于“上一回开启修容”的结果
            self._light_cache_drop(which)
            return t
        if t is None:
            # 产品通路不会走到这里（retouch 先 prepare），但 lighten_result() 是公开方法：
            # 直接调它拿到的应当是一句“先 prepare”，而不是下游 _shape_check 的
            # AttributeError: 'NoneType' object has no attribute 'shape'
            raise RuntimeError(f"先 prepare() 再取修容结果（which={which} 的入参还是 None）")
        # 底图身份看 repair_version，磨皮结果身份看 filter_key（它本身已含修补版本）
        key = ((self.repair_version, self.light_version,
                float(self.light_exposure), int(self.light_radius)) if which == "src"
               else (self.filter_key, self.light_version,
                     float(self.light_exposure), int(self.light_radius)))
        cur, ck = self._light_cache_get(which)
        if cur is not None and ck == key:
            return cur
        t0 = time.perf_counter()
        out = dodge_burn_t(t, self.light_field_gpu, exposure=self.light_exposure,
                           radius=self.light_radius)
        # 不把非有限值写进常驻：缓存里的 NaN 会长期作恶，而且 `(1-0)*NaN` 仍是 NaN，
        # strength=0 逐字节恒等当场失效（M1-3c 那条教训的原样复用）
        if not torch.isfinite(out).all():
            self._light_cache_drop(which)
            raise ValueError(f"修容产出非有限值，已拒绝写入常驻缓存："
                             f"exposure={self.light_exposure} radius={self.light_radius}")
        self._light_cache_set(which, out, key)
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_light_ms += (time.perf_counter() - t0) * 1000.0
        return out

    def lighten_source(self):
        """底图过修容层。"""
        return self._apply_light_cached(self.base(), "src")

    def lighten_result(self):
        """磨皮结果过修容层。必须在 prepare 之后调（要读 self.retouched）。"""
        return self._apply_light_cached(self.retouched, "res")

    def set_light_ops(self, ops: list, redo: list | None = None) -> dict:
        """整体挂上一组修容笔（换设备重建时用）：只认输入，不认旧结果。"""
        return self._commit_light(list(ops), list(redo) if redo is not None else [])

    def add_light(self, op: "LightOp") -> dict:
        # 新笔发生在新一次重做之上，旧 redo 栈当场失效（与消除笔同一条理由）
        return self._commit_light(self.light_ops + [op], [])

    def undo_light(self) -> dict | None:
        if not self.light_ops:
            return None
        last = self.light_ops[-1]
        info = self._commit_light(self.light_ops[:-1], self.light_redo + [last])
        info["undone_ops"] = len(self.light_ops) + 1
        return info

    def redo_light(self) -> dict | None:
        if not self.light_redo:
            return None
        last = self.light_redo[-1]
        info = self._commit_light(self.light_ops + [last], self.light_redo[:-1])
        info["redone_ops"] = len(self.light_ops)
        return info

    def clear_light(self, keep_redo: bool = True) -> dict:
        return self._commit_light([], self.light_redo if keep_redo else [])

    def set_light_params(self, exposure: float, radius: int) -> dict:
        """改修容强度/带限半径：只换参数，不动图层。

        两份 db 缓存立即放下：它们对新参数没有意义，而旧张量占着 13 MiB 显存
        （产品档两份）不给释放，拖一下滑块显存峰值就翻倍。缓存键里含这两个数，
        不放下也不会拿错，所以这是纯显存措施。

        校验必须在赋值之前，而且不能只靠调用方兜：上一版这里只做 float()/int()，
        直调库层的通路（m2-dnb-bench 的 prod()、_attach_pipeline 的直赋值）能把 NaN
        写进 light_exposure，而 lit 判据是 `exposure != 0.0`——**NaN 判为生效**，于是
        每帧都在渲染期抛 ValueError，会话卡死而 light_done 永不出现。参数先于图层这
        条约定与 cmd_set_strength / cmd_deform 花代价换来的同形。
        """
        from .ops.light import _check

        e, r = _check(exposure, radius)
        self.light_exposure = e
        self.light_radius = r
        self.light_src = None
        self.light_src_key = None
        self.light_res = None
        self.light_res_key = None
        # 键集必须与 _commit_light 完全一致：五种 action 共用 light_done 这一个事件名，
        # 少任何一个键，UI 那边按必存字段读就是 undefined（TS 编译期抓不到，谎报发生在
        # JSON 边界上）。参数这条臂不重算场，所以建层成本记 0、峰值从常驻场现算。
        peak = 0.0
        if self.light_field_gpu is not None:
            peak = float(self.light_field_gpu.abs().max().item())
        return self._light_payload(build_ms=0.0, ops=len(self.light_ops),
                                   redo=len(self.light_redo), painted=None,
                                   field_peak=peak, recomputed=False)

    def _light_payload(self, *, build_ms: float, ops: int, redo: int,
                       painted, field_peak: float, recomputed: bool) -> dict:
        """light_done 的图层字段只在这里组装一次（两条臂共用一份形状）。

        painted 为 None 表示“这一条没重数过笔”：场是常驻的那份，拿不到覆盖像素数时
        宁可给 0 也不留缺键——缺键的代价是 UI 读出 undefined 而无人报错，0 的代价只是
        一个看得出来的保守值。
        """
        return {
            # 建层成本（一次性）。与每帧的 last_light_ms 不同名：上一版两处都叫
            # light_ms，而 cmd 层的 `**info` 又被每帧那个覆盖，报表上完全看不出
            # 报的是哪一个——两个量差一个量级（建层 20 ms vs 每帧 0）。
            "light_build_ms": round(float(build_ms), 2),
            "ops": int(ops),
            "redo_pending": int(redo),
            "painted_px": int(painted or 0),
            "field_peak": round(float(field_peak), 6),
            "lit": bool(self.has_light()),
            "exposure": float(self.light_exposure),
            "radius": int(self.light_radius),
            "bytes_light": self.light_resident_bytes(),
            # 本层是否真的重算了。不能叫 cached：cmd 层那条 `cached` 说的是“这一帧的
            # 磨皮滤波命中缓存”，两件事同名就是字典后写静默吃掉先写（bench_done 的
            # light/deform 已经栽过一次，同一个坑不留在原地）。
            "layer_recomputed": bool(recomputed),
        }

    def _commit_light(self, ops: list, redo: list) -> dict:
        """重算带符号修容场并一次性提交。

        场是各笔的**线性累加**而不是逐笔应用 dodge_burn：逐笔会把 gain 指数乘起来
        （三笔 0.6 档就是 3.5 倍，脸就烧穿了），而累加后一次应用的成本与笔数无关，
        撤销一笔也只是从场里减回去。三条产品语义（抵消/线性累加/饱和）都有用例钉着。

        同样“全算完才提交”：参数或尺寸非法时一笔也不加，不会留下“图层多了一笔
        但场还是旧的”那种半截状态。
        """
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb_u8 再画修容")
        t0 = time.perf_counter()
        painted = 0
        field = np.zeros((self.h, self.w), dtype=np.float64)
        for i, op in enumerate(ops):
            if op.weight.shape != (self.h, self.w):
                raise ValueError(f"第 {i} 笔修容覆盖度尺寸 {op.weight.shape} != 会话 "
                                 f"{(self.h, self.w)}，笔必须画在代理帧坐标系上")
            if op.weight.dtype != np.uint8:
                raise ValueError(f"第 {i} 笔修容覆盖度必须是 uint8（0..255），得到 {op.weight.dtype}")
            if int(op.sign) not in (-1, 1):
                raise ValueError(f"第 {i} 笔修容方向非法：{op.sign!r}（需 +1 减淡 / -1 加深）")
            field += float(op.sign) * (op.weight.astype(np.float64) / 255.0)
            painted += int((op.weight > 0).sum())
        clipped = np.clip(field, -1.0, 1.0)
        if not np.isfinite(clipped).all():
            raise ValueError("修容场含非有限值，整条拒绝")
        # 全零场不上传也不存：has_light() 当场为假，两个操作数原样进混合（零开销）
        gpu = None
        if bool(clipped.any()):
            gpu = torch.from_numpy(np.ascontiguousarray(clipped[None, None].astype(np.float32))) \
                .to(self.device)
        ms = (time.perf_counter() - t0) * 1000.0
        # ---- 提交点：后面全是赋值 ----
        self.light_ops = ops
        self.light_redo = redo
        self.light_field_gpu = gpu
        self.light_version += 1
        self._light_cache_drop("src")
        self._light_cache_drop("res")
        return self._light_payload(build_ms=ms, ops=len(ops), redo=len(redo),
                                   painted=painted, field_peak=float(np.abs(clipped).max()),
                                   recomputed=True)

    def light_resident_bytes(self) -> int:
        """修容层的显存 + CPU 账单：场、两份 db 结果、画笔列表。"""
        gpu = 0
        for t in (self.light_field_gpu, self.light_src, self.light_res):
            if t is not None:
                gpu += int(t.numel() * t.element_size())
        cpu = sum(op.nbytes() for op in self.light_ops) + sum(op.nbytes() for op in self.light_redo)
        return gpu + cpu

    # ---- M2-b：形变层（盖在磨皮与修容之后的几何层）--------------------
    def has_deform(self) -> bool:
        if PEOPLE_PIPE.active(self):return self.people_prepared.geometry.peak>0
        """没建单或三个滑块全零 ⇒ 一个算子也不跑。"""
        return bool(self.deform_units) and any(self.deform_amounts.get(k, 0.0) != 0.0
                                               for k in self.deform_units)

    def build_deform(self, landmarks) -> dict:
        """从 478 点解出三种形变的单位场并常驻。一张图只跑一次。

        先算完、再提交：中途某个 kind 解算失败（关键点不够、后端只给占位几何）时，
        会话不能留下“一半形变已常驻”的跳状态。与 M1-3c 的“不留半截显存”同一条约束。
        """
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb_u8 再建形变层")
        lm = np.asarray(landmarks)
        t0 = time.perf_counter()
        units: dict[str, torch.Tensor] = {}
        meta: dict[str, dict] = {}
        for kind in KINDS:
            u, m = unit_field(lm, kind, self.h, self.w, device=self.device)
            if not torch.isfinite(u).all():
                raise ValueError(f"{kind} 的位移场含非有限值，整层拒绝：不写进常驻")
            units[kind] = u
            meta[kind] = m
        base = identity_grid(self.h, self.w, self.device)
        ms = (time.perf_counter() - t0) * 1000.0
        # ---- 提交点：后面全是赋值 ----
        self._deform_warp = None
        self._deform_warp_key = None
        self.deform_units = units
        self.deform_meta = meta
        self.deform_grid_base = base
        self.deform_version += 1
        self.deform_builds += 1
        return {
            "deform_build_ms": round(ms, 2),
            "deform_builds": self.deform_builds,
            "kinds": {k: meta[k] for k in KINDS},
            "bytes_deform": self.deform_resident_bytes(),
            "device": str(self.device),
        }

    def clear_deform(self) -> dict:
        """放下整层：三个单位场与恒等网格一共 5 份张量，不手动放就会一直占着。"""
        self._deform_warp = None
        self._deform_warp_key = None
        self.deform_units = {}
        self.deform_meta = {}
        self.deform_grid_base = None
        self.deform_amounts = {k: 0.0 for k in KINDS}
        self.deform_version += 1
        return {"amounts": dict(self.deform_amounts), "built": False, "lit": False,
                "deform_builds": self.deform_builds, "bytes_deform": 0}

    def set_deform_amounts(self, amounts: dict) -> dict:
        """改滑块值。**先校验后提交**：一个非法值也不能把其他两个带下水。

        不先校验的话 `"slim_face": 5.0` 会先把旧值覆盖成一个越界系数，下一帧就把
        脸拖成一陀——而事件里报的却是一句“参数非法”。M1-3c 的 set_strength 已经
        为同一个形状付过一次钱。
        """
        if not isinstance(amounts, dict) or not amounts:
            raise ValueError("deform amounts 至少要给一个 kind")
        got = check_amounts(amounts)
        new_amounts = dict(self.deform_amounts, **got)
        if new_amounts != self.deform_amounts:
            self._deform_warp = None
            self._deform_warp_key = None
        self.deform_amounts = new_amounts
        return {"amounts": dict(self.deform_amounts),
                "built": bool(self.deform_units),
                "lit": bool(self.has_deform())}

    def adopt_deform_field(self, delta) -> dict:
        # delta 是**前向位移场**（与 unit_field 同一种东西，模块 docstring 第 5 条）：
        # 导出器算的、预览建的、这里存的必须同一种单位制，负号只在 warp_t/warp_np 取。
        """挂一份**已经合成好的**位移场（1,H,W,2，像素单位）。导出通路专用。

        为什么不让导出器直接摸 `deform_units`/`deform_amounts`/`deform_grid_base`：
        那三个字段必须同时自洽（amounts 里的系数得与场里的合成结果对得上、网格得与
        会话同尺寸），从外面摸就是一个三条可以只改两条的状态。现在校验全在这里做，
        失败就是一个字段也不改。

        `deform_builds` 一分不增：这不是“解了一次 TPS”，而是“拿了一份现成的场”。
        那个计数器是“拖滑块零推理”的唯一可测口径，导出通路不能把它污染成“每帧重解”
        的反例——M2-b 的反向门禁专门钉的就是它。
        """
        if torch is None:
            raise RuntimeError("torch 未安装，形变层不可用")
        if not torch.is_tensor(delta):
            raise ValueError(f"adopt_deform_field 需要张量，得到 {type(delta).__name__}")
        want = (1, self.h, self.w, 2)
        if tuple(delta.shape) != want:
            raise ValueError(f"位移场形状 {tuple(delta.shape)} != 会话要的 {want}："
                             "场必须按 tile 的坐标帧算好再交进来")
        if delta.dtype != torch.float32:
            raise ValueError(f"位移场必须是 float32，得到 {delta.dtype}")
        if not torch.isfinite(delta).all():
            raise ValueError("位移场含非有限值：NaN 会被 grid_sample 采样到整块邻域")
        self.clear_deform()
        # 三个 kind 里只走 slim_face 这一位、系数给 1.0：apply_deform 会算
        # `unit * 1.0`，那是 IEEE 恒等（不改变一个 bit），而不是“又乘了一道强度”。
        self.deform_units = {"slim_face": delta.to(self.device)}
        self.deform_amounts = {"slim_face": 1.0, "big_eye": 0.0, "small_chin": 0.0}
        self.deform_grid_base = identity_grid(self.h, self.w, self.device)
        self.last_deform_ms = 0.0
        return {"amounts": dict(self.deform_amounts), "built": True,
                "lit": bool(self.has_deform()), "deform_builds": self.deform_builds,
                "bytes_deform": self.deform_resident_bytes(), "adopted": True}

    def apply_deform(self, t):
        """把当前形变层施加到一份常驻张量上。每帧只走这里，不走 TPS 解算。"""
        self.last_deform_ms = 0.0
        if PEOPLE_PIPE.active(self): return PEOPLE_PIPE.warp(self,t)
        if not self.has_deform() and not BROWR.has_brow(self) and not NOSER.has_nose(self) and not EYER.has_eye(self) and not MOUTHR.has_mouth(self):
            return t
        t0 = time.perf_counter()
        key = MOUTHR.warp_key(self)
        if key != self._deform_warp_key:
            delta = None
            for kind, unit in self.deform_units.items():
                amount = self.deform_amounts.get(kind, 0.0)
                if amount != 0.0:
                    delta = unit * amount if delta is None else delta + unit * amount
            delta = MOUTHR.joint_delta(self, delta)
            base = self.deform_grid_base
            if self.high_precision_warp:
                # RGB16 exposes normalized-float32 grid rounding as visible LSB
                # disagreement across tile sizes. Build and sample in float64,
                # then return to the float32 editing buffer; RGB8 is unchanged.
                delta = delta.to(torch.float64)
                base = identity_grid(self.h, self.w, self.device, dtype=torch.float64)
            self._deform_warp = prepare_warp_t(delta, self.h, self.w, base=base)
            self._deform_warp_key = key
        sample = t.to(torch.float64) if self.high_precision_warp else t
        out = apply_prepared_warp_t(sample, self._deform_warp).to(t.dtype)
        if not torch.isfinite(out).all():
            raise ValueError("形变产出非有限值，已拒绝：amounts="
                             f"{self.deform_amounts}")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_deform_ms = (time.perf_counter() - t0) * 1000.0
        return out

    def deform_resident_bytes(self) -> int:
        """形变层的显存账单：各单位场 + 恒等网格 + 已生成的采样网格/零位移掩膜。"""
        total = PEOPLE_PIPE.resident_bytes(self)
        if PEOPLE_PIPE.active(self):total += self.people_prepared.geometry.delta.nbytes + self.people_prepared.geometry.owner.nbytes
        for t in (list(self.deform_units.values()) + [self.deform_grid_base]
                  + list(self._deform_warp or ())):
            if t is not None:
                total += int(t.numel() * t.element_size())
        return total

    # ---- M3-a2：调色层（盖在形变之后的 3D LUT 输出变换）----------------
    def has_lut(self) -> bool:
        """恒等表、没挂表、强度 0 都是“一个字节也改不了”。

        与 has_light 同一条铁律：NaN 与 0.0 不相等，拿 `amount != 0.0` 当“生效”
        会把一层算不出东西的表报成在生效，而现场要到渲染期才抛。这里当场判假。
        """
        if self.lut is None or self.lut.neutral or (self.lut_vol is None and not isinstance(self.lut, CustomCube)):
            return False
        a = float(self.lut_amount)
        return math.isfinite(a) and a != 0.0

    def set_lut(self, cube, amount=None) -> dict:
        """挂上一张表：先全量校验，全算完才一次性提交。

        amount 不传就保留当前值（与 light add 带参数同形：“给了才改”，而不是静默忽略
        也不是静默重置）。上显存只有一个可能失败的步骤（to_device），它就在提交点前：
        抛了就是一个字段也不改，不会留下“上报写着新表、画面按旧表渲染”。
        """
        if torch is None:
            raise RuntimeError("torch 未安装，调色层不可用（装 rocm/cuda/cpu 任一变体）")
        if isinstance(cube, CustomCube):
            a = check_amount(self.lut_amount if amount is None else amount)
            self.lut, self.lut_vol, self.lut_amount = cube, None, a
            return self._lut_payload(mount_ms=0.0, layer_recomputed=True)
        if not isinstance(cube, CubeLut):
            raise LutError(f"set_lut 需要一张 CubeLut，得到 {type(cube).__name__}："
                           "先过 parse_cube / load_cube_file / bake")
        if cube.kind != "3d":
            raise LutError(f"本层只接三维表，得到 kind={cube.kind}")
        a = check_amount(self.lut_amount if amount is None else amount)
        t0 = time.perf_counter()
        vol = None if cube.neutral else cube.to_device(self.device)
        mount_ms = (time.perf_counter() - t0) * 1000.0
        if vol is not None:
            # 形状与字节必须与原件对得上：这是上报里 bytes_lut 唯一的出处。
            # permute 后不 contiguous、或者路上换了 dtype，在这里就红，而不是到渲染期
            # 让 grid_sample 拿一份维度对得上的错表去采。
            want = (1, 3, cube.size, cube.size, cube.size)
            got = tuple(vol.shape)
            mb = int(vol.numel() * vol.element_size())
            if got != want or vol.dtype != torch.float32 or mb * 2 != cube.nbytes():
                raise RuntimeError(
                    f"上显存后不是预期的体积：形状 {got}（需 {want}）、dtype {vol.dtype}"
                    f"（需 float32）、字节 {mb}（需表原件 {cube.nbytes()} 的一半）")
            if vol.device.type != self.device.type or (
                    self.device.index is not None and vol.device.index != self.device.index):
                # 不能用 `vol.device != self.device`：torch.device("cuda") 的 index 是 None，
                # 而张量实际报 cuda:0，于是两个完全兼容的设备写法不相等——GPU 上挂任何表
                # 都会报“跳设备”而当场挂掉（本轮单测在真卡上量到的）。
                raise RuntimeError(f"体积落在 {vol.device}，会话在 {self.device}："
                                   "跨设备张量会在下一帧读到不存在的显存")
        # ---- 提交点：后面全是赋值 ----
        self.lut = cube
        self.lut_vol = vol
        self.lut_amount = a
        # 不丢任何缓存：调色在混合与形变之后，它改不了分带/成品/db/单位场里的任何字节。
        # 这一句是“设完 LUT 拖磨皮滑块仍零重算”那条判据的根据，不是注释里的愿望。
        return self._lut_payload(mount_ms=mount_ms, layer_recomputed=True)

    def clear_lut(self) -> dict:
        """放下整层：体积与 CPU 原件一起放。强度回默认 1.0。

        强度不保留旧值：“清掉调色”与“挂一张新表但强度停在 0.2”合在一起，用户
        会看到“预设点了没反应”；清层就是把这一层回到它的出厂状态。
        """
        self.lut = None
        self.lut_vol = None
        self.lut_amount = DEFAULT_LUT_AMOUNT
        self.last_lut_ms = 0.0
        return self._lut_payload(mount_ms=0.0, layer_recomputed=False)

    def set_lut_amount(self, amount) -> dict:
        """只改混合系数，不重挂体积。这是拖“调色强度”滑块唯一的入口。"""
        if self.lut is None:
            raise LutError("还没有 LUT：调色强度无处可施，先用 set_lut 挂一张表")
        a = check_amount(amount)
        self.lut_amount = a
        return self._lut_payload(mount_ms=0.0, layer_recomputed=False)

    def _lut_payload(self, *, mount_ms: float, layer_recomputed: bool) -> dict:
        """lut_done 的图层字段只在这里组装一次（三条 action 臂共用一份形状）。

        M2 审查第一条发现就是“事件形状在 JSON 边界上漂，而且总是漂向少字段那条”：
        TS 把字段声明成必存，少一个键就是前端 TypeError 而编译期抓不到。所以这一层
        不给任何臂“只带自己那几个字段”的机会；没发重算的臂 mount_ms 给 0.0 而不是缺键。
        """
        cube = self.lut
        return {
            "lut_set": cube is not None,
            "lut_kind": (cube.kind if cube else None),
            "lut_size": (cube.size if cube else 0),
            "lut_title": (cube.title if cube else ""),
            "lut_source": (cube.source if cube else ""),
            "lut_asset_id": getattr(cube, "asset_id", None),
            "lut_neutral": bool(cube.neutral) if cube else False,
            "lut_clipped": int(cube.clipped) if cube else 0,
            "lut_notes": list(cube.notes) if cube else [],
            "lut_domain_min": [float(v) for v in cube.domain_min] if cube else [],
            "lut_domain_max": [float(v) for v in cube.domain_max] if cube else [],
            "lut_amount": float(self.lut_amount),
            "lut_lit": bool(self.has_lut()),
            "lut_mount_ms": round(float(mount_ms), 2),
            "bytes_lut": self.lut_resident_bytes(),
            "lut_grid_bytes": int(cube.nbytes()) if cube else 0,
            "device": str(self.device),
            # 与 layer_recomputed（本层真的重挂过）分开：后者与每帧的 filter_cached
            # 不同名就不怕字典后写吃掉先写（M2 审 ⑤ 的原话）
            "layer_recomputed": bool(layer_recomputed),
        }

    def apply_lut(self, t):
        """把当前调色层施加到一份常驻张量上。每帧只走这里，不走 H2D。

        恒等表/强度 0 当场短路把原张量递回去（不复制、不跑算子）：“strength=0
        逐字节等于解码原图”那条跨四个里程碑的验收口径，不能因为“挂了一张空表”就碎。
        """
        self.last_lut_ms = 0.0
        if not self.has_lut():
            return t
        t0 = time.perf_counter()
        if isinstance(self.lut, CustomCube):
            out = self.lut.apply_tensor(t, self.lut_amount, getattr(self, "custom_lut_cancelled", lambda: False))
            self.last_lut_ms = (time.perf_counter() - t0) * 1000.0
            return out
        graded = apply_lut_t(t, self.lut, vol=self.lut_vol)
        a = float(self.lut_amount)
        # a==1 不写 `(1-1)*t + 1*graded`：那在 IEEE 里对有限值是精确的，但白跑一次逐点
        # 乘加（产品档 1–2 ms）。更重要的是短路后“全强度”与 M3-a1 探针量那条路完全同式。
        out = graded if a == 1.0 else (1.0 - a) * t + a * graded
        if not torch.isfinite(out).all():
            raise ValueError(f"调色产出非有限值，已拒绝：lut={self.lut.source!r} "
                             f"size={self.lut.size} amount={a}")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_lut_ms = (time.perf_counter() - t0) * 1000.0
        return out

    def lut_resident_bytes(self) -> int:
        """调色层账单：显存里的体积 + CPU 侧的表原件。两份都得算，不报就等于藏账。"""
        gpu = 0 if self.lut_vol is None else int(self.lut_vol.numel() * self.lut_vol.element_size())
        cpu = 0 if self.lut is None else int(self.lut.nbytes())
        return gpu + cpu

    # ---- M3-b：肤色定向层 ----------------------------------------------
    def has_grade(self) -> bool:
        """这一层到底有没有活。参数在提交前已被 check_params 夹住，这里不再校。"""
        dh, ds, dv = self.grade_params
        return bool(float(self.grade_amount) != 0.0 and (dh != 0.0 or ds != 0.0 or dv != 0.0))

    def _grade_weight_gpu(self):
        """当前作用域对应的那份权重 (1,1,H,W)，None 表示全图（不加混合、逐字节不变）。

        `all` 走的是**真正的短路**而不是“乘一个全 1 的掩膜”：混式的两个操作数在
        w=1 时确实回到 graded，但那是每帧多跑一遍逐点乘加；而更要紧的是“旧行为逐字节
        不变”这条承诺不能依赖浮点巧合。与 apply_lut/apply_grade 的“没活就不跑算子”同构。
        """
        if self.grade_scope == "all":
            return None
        if self.grade_scope == "objects":
            return self.align_source_grade_mask(self._local_mask_gpu)
        if self.grade_scope == "skin":
            if self.masks_gpu is None:
                raise RuntimeError("skin 作用域要人脸掩膜，而本会话还没 precompute")
            if "skin" not in self.mask_names:
                # 掩膜在、就是没有那一格：拿 KeyError 去撞每帧渲染等于把一次性
                # 校验挪到无休止的失败里（set_channel 早就按同一份名单校过）。
                raise RuntimeError(f"掩膜里没有 skin 通道（可用：{', '.join(self.mask_names)}）")
            weight = self.mask("skin")
            return self.align_source_grade_mask(weight) if MOUTHR.has_source_geometry(self) else weight
        if self._grade_mask_gpu is None:
            raise RuntimeError("brush 作用域要画笔画出的区域，而当前一份也没有")
        return self.align_source_grade_mask(self._grade_mask_gpu) if MOUTHR.has_source_geometry(self) else self._grade_mask_gpu

    def align_source_grade_mask(self, weight):
        """Map source-domain coverage into the actual post-deformation grade stage.

        Reuse the image warp, including its unchanged pixels, border policy and
        RGB16 float64 grid. Do not reorder the established colour pipeline.
        """
        if weight is None:
            raise ValueError("Source-domain grade coverage is unavailable")
        if PEOPLE_PIPE.active(self): return PEOPLE_PIPE.warp(self,weight)
        if not self.has_deform() and not BROWR.has_brow(self) and not NOSER.has_nose(self) and not EYER.has_eye(self) and not MOUTHR.has_mouth(self):
            return weight
        image_warp_ms = self.last_deform_ms
        try:
            return self.apply_deform(weight)
        finally:
            self.last_deform_ms = image_warp_ms

    def set_local_mask(self, weight, *, reason=None):
        arr = np.asarray(weight)
        if arr.shape != (self.h, self.w) or arr.dtype != np.uint8:
            raise ValueError("Composed mask must match the source grid")
        self._local_mask_gpu = self._np_to_grade_weight(arr)
        self.local_mask_suspended = reason
        self.grade_scope = "objects"

    def set_grade_scope(self, scope: str) -> dict:
        """换作用域。掩膜拿不到就**整条拒**，不静默退回全图。

        这一条不是洁癖：局部调色静默变成全图调色，用户从画面上分不出来（画面真的在
        变），而他会以为只动了皮肤。与 face/inpaint 的 backend 不许静默降级同一条规矩。
        """
        if scope not in GRADE_SCOPES:
            raise ValueError(f"未知调色作用域 {scope!r}（可用：{', '.join(GRADE_SCOPES)}）")
        if scope == "skin" and self.masks_gpu is None:
            raise ValueError("skin 作用域需要人脸掩膜：先跑 precompute（mediapipe 后端）")
        if scope == "skin" and "skin" not in self.mask_names:
            raise ValueError(f"skin 作用域需要 skin 掩膜，而本会话的通道里没有它"
                             f"（可用：{', '.join(self.mask_names) or '无'}）")
        if scope == "brush" and (self.grade_mask is None or int((self.grade_mask > 0).sum()) == 0):
            raise ValueError("brush 作用域需要先画出区域：现在一笔也没有")
        if scope == "objects" and self._local_mask_gpu is None:
            raise ValueError("Create a composed mask before binding grade")
        self.grade_scope = scope
        # brush 的权重只在真要用的时候才常驻；切回 all/skin 就把那份显存放掉
        self._grade_mask_gpu = (self._np_to_grade_weight(self.grade_mask)
                                if scope == "brush" else None)
        return self._grade_payload(layer_recomputed=True)

    def _np_to_grade_weight(self, arr):
        """uint8 (H,W) 覆盖度 → (1,1,H,W) float，落在本会话的设备上。"""
        f = torch.as_tensor(arr.astype(np.float32) / 255.0, device=self.device)
        return f.reshape(1, 1, self.h, self.w).clamp_(0.0, 1.0)

    def set_grade_mask(self, weight, *, mode: str = "replace") -> dict:
        """递交画笔区域：weight 是 (H,W) uint8 覆盖度（代理帧坐标，0..255）。

        `mode=add` 与已有区域**取并集**（逐像素取大）：第二笔不该把第一笔擦掉，
        而“多笔累计”如果靠重放每条命令的 rle，历史里任何一次撤销都会连带退回整片区域。
        """
        if mode not in ("replace", "add"):
            raise ValueError(f"未知 grade mask mode {mode!r}（可用：replace/add）")
        arr = np.asarray(weight)
        if arr.shape != (self.h, self.w):
            raise ValueError(f"调色区域尺寸 {arr.shape} != 会话 {(self.h, self.w)}，"
                             "得用代理帧坐标而不是原图坐标")
        if arr.dtype != np.uint8:
            raise ValueError(f"调色区域必须是 uint8（0..255），得到 {arr.dtype}")
        if not np.isfinite(arr.astype(np.float32)).all():
            raise ValueError("调色区域含非有限值，整条拒绝")
        merged = arr if self.grade_mask is None or mode == "replace" \
            else np.maximum(self.grade_mask, arr)
        if int((merged > 0).sum()) == 0:
            raise ValueError("合并后一个像素也没盖到：这一笔不该发这条命令")
        self.grade_mask = merged
        if self.grade_scope == "brush":
            self._grade_mask_gpu = self._np_to_grade_weight(merged)
        return self._grade_payload(layer_recomputed=True)

    def clear_grade_mask(self) -> dict:
        """丢掉画笔区域。作用域不会“没掩膜还能是 brush”：顺手退回 all。"""
        self.grade_mask = None
        self._grade_mask_gpu = None
        if self.grade_scope == "brush":
            self.grade_scope = "all"
        return self._grade_payload(layer_recomputed=True)

    def set_grade(self, dh, ds, dv, amount=None) -> dict:
        """提交一组肤色定向参数。先全量校验，后才写入——被拒不留半截状态。

        这一层没有“建层”那一笔（不持有张量），所以也没有 mount/build 成本；但校验
        必须在提交之前：NaN 比大小恒为 False，不拦就会被当“合法”写进常驻层，然后
        每帧渲染才抛——set_strength / set_deform_amounts / set_lut 三次付过同一笔学费。
        """
        a = check_params(dh, ds, dv,
                         amount=float(self.grade_amount if amount is None else amount))
        self.grade_params = (a[0], a[1], a[2])
        self.grade_amount = a[3]
        return self._grade_payload(layer_recomputed=True)

    def set_grade_amount(self, amount) -> dict:
        """只改混入比例：三个数原封不动，所以“关掉”不是“忘记”。"""
        vals = check_params(self.grade_params[0], self.grade_params[1], self.grade_params[2],
                            amount=amount)
        self.grade_amount = vals[3]
        return self._grade_payload(layer_recomputed=False)

    def clear_grade(self) -> dict:
        """关整层：只把三个增量与混入比例回中性。

        **不动作用域与画笔区域**：区域是用户拿笔涂出来的东西，参数滑块归零不该顺手
        抹掉笔迹（与修容层的 params/clear 分工同构）。要清区域走 clear_grade_mask。
        """
        self.grade_params = (0.0, 0.0, 0.0)
        self.grade_amount = 1.0
        self.last_grade_ms = 0.0
        return self._grade_payload(layer_recomputed=False)

    def _grade_payload(self, *, layer_recomputed: bool) -> dict:
        """grade_done 的图层字段只在这里组装一次（set/clear/amount/scope/mask 共用一份形状）。

        窗口边界与硬上限一并带出去：滑块该夹在哪由引擎说，不让 UI 自己抄一份数、
        然后两处漂。它们不是计时也不是分段，所以名字与每帧的 grade 段不会撞。

        作用域与区域覆盖度也从这里报：“现在调的是全图还是只调皮肤/画笔区域”是
        画面事实，它只能在事件自己身上；UI 自己记得那一格就会在换图/重开后说谎。
        """
        dh, ds, dv = self.grade_params
        return {
            "grade_dh": float(dh), "grade_ds": float(ds), "grade_dv": float(dv),
            "grade_amount": float(self.grade_amount),
            "grade_set": bool(dh != 0.0 or ds != 0.0 or dv != 0.0),
            "grade_lit": bool(self.has_grade()),
            "grade_limits": [float(DH_LIMIT), float(DS_LIMIT), float(DV_LIMIT)],
            "bytes_grade": int(self.grade_resident_bytes()),
            # COLOR-004：作用域、可选值、以及“画笔区域到底盖了多少格”一起报出去。
            # mask_px 是 0 时 scope 不可能是 brush（set_grade_scope 已拦），但那一格
            # 仍然随事件走：让 UI 能**看到**而不是**推断**“区域空着”。
            "grade_scope": str(self.grade_scope),
            "grade_scopes": list(GRADE_SCOPES),
            "mask_px": 0 if self.grade_mask is None else int((self.grade_mask > 0).sum()),
            "device": str(self.device),
            "layer_recomputed": bool(layer_recomputed),
        }

    # ---- P0：裁剪 / 旋转（lnx.crop.v1）---------------------------------------
    def has_geometry(self) -> bool:
        return not geometry_identity(self.crop_rect, self.crop_rotation)

    def set_geometry(self, rect, rotation_degrees: float = 0.0) -> dict:
        """量程与判据全部交给 ops.geometry.check——本层不抄第二份数，认不出就抛。"""
        x0, y0, x1, y1, r = geometry_check(rect, rotation_degrees)
        self.crop_rect = (x0, y0, x1, y1)
        self.crop_rotation = r
        return self.geometry_state()

    def clear_geometry(self) -> dict:
        self.crop_rect = (0.0, 0.0, 1.0, 1.0)
        self.crop_rotation = 0.0
        return self.geometry_state()

    def geometry_state(self) -> dict:
        """把量程从引擎报出去：UI 不该自己抄一份 [-180,180]，两边分叉没人看得出来。"""
        ow, oh = geometry_out_size(int(self.w), int(self.h), self.crop_rect, self.crop_rotation)
        return {"crop_rect": list(self.crop_rect), "crop_rotation": float(self.crop_rotation),
                "crop_lit": bool(self.has_geometry()),
                "crop_out": [int(ow), int(oh)],
                "crop_limits": {"rect": [0.0, 1.0], "rotation": [-float(GEOM_ANGLE_LIMIT),
                                                                 float(GEOM_ANGLE_LIMIT)]},
                "bytes_geometry": 0, "geometry_ms": round(float(self.last_geometry_ms), 3)}

    def apply_geometry(self, t):
        """每帧只走这里；恒等时把张量原样递回去（不复制、不跑算子）。

        预览与导出的分工必须写清：这一层在**代理尺寸**上剪转之后，再把结果缩放回代理画布
        （显存常驻帧与 shm 双缓冲的尺寸是固定的，为一次拖滑块重分配画布不是"代价小"而是
        另一条通路）。导出走的是全幅那份数组、不做这一步回缩，所以文件的尺寸是
        `geometry_state()["crop_out"]` 报出去的真实值——预览是缩放视图，不是另一种构图。
        """
        self.last_geometry_ms = 0.0
        if not self.has_geometry():
            return t
        from .geometry_projection import project
        t0 = time.perf_counter()
        out = project(t, self.crop_rect, self.crop_rotation, (int(self.w), int(self.h)))
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_geometry_ms = (time.perf_counter() - t0) * 1000.0
        return out

    # ---- P0：全局曝光 / 白平衡 -----------------------------------------------
    def has_exposure(self) -> bool:
        return bool(self.exposure_params != (0.0,) * 7 or
                    (getattr(self, "prepared_wb", None) is not None and self.prepared_wb != (1.0, 1.0, 1.0)))

    def set_exposure(self, ev: float = 0.0, temperature_shift: float = 0.0,
                     tint_shift: float = 0.0, ref_k: float | None = None,
                     contrast: float = 0.0, highlights: float = 0.0,
                     shadows: float = 0.0, saturation: float = 0.0,
                     wb_options=None) -> dict:
        """先全量校验后一次性提交：越界/NaN 整条拒，不夹取也不留半截状态。

        参考白 (ref_k) 单独一条口：它不是用户滑杆、而是来片的 as-shot 色温。
        有 EXIF 就喂真值，没有就留默认 D65——“开尔文偏移”对任何源都成立的原因就在此。
        """
        if wb_options is not None:
            from .white_balance_math import _number
            for raw in (ev, temperature_shift, tint_shift, contrast, highlights, shadows, saturation):
                _number(raw)
            reference = self.exposure_ref_k if ref_k is None else _number(ref_k)
        else:
            reference = float(ref_k) if ref_k else self.exposure_ref_k
        e, dk, tn, rk = exposure_check(ev, temperature_shift, tint_shift, reference)
        c, h, s, sa = check_tone(contrast, highlights, shadows, saturation)
        options = prepared = None
        if wb_options is not None:
            from .white_balance_recipe import check_options, prepare_state
            options = check_options(wb_options)
            prepared = prepare_state({"_wb_options": options, "_exposure_ref_k": rk,
                                      "_exposure": (e, dk, tn, c, h, s, sa)})
        self.exposure_params = (e, dk, tn, c, h, s, sa)
        self.wb_options, self.prepared_wb = options, prepared
        self.exposure_ref_k = rk
        return self.exposure_state()

    def clear_exposure(self) -> dict:
        self.exposure_params = (0.0,) * 7
        self.exposure_ref_k = REFERENCE_K
        self.wb_options = self.prepared_wb = None
        self.last_exposure_ms = 0.0
        return self.exposure_state()

    def exposure_state(self) -> dict:
        """量程上限由引擎报出去：UI 该夹在哪不该由前端抄一份数（与 grade_limits 同一条）。"""
        e, dk, tn, c, h, s, sa = self.exposure_params
        return {
            "exposure_ev": float(e),
            "exposure_temperature_shift": float(dk),
            "exposure_tint_shift": float(tn),
            "tone_contrast": float(c), "tone_highlights": float(h),
            "tone_shadows": float(s), "tone_saturation": float(sa),
            "exposure_reference_k": float(self.exposure_ref_k),
            "exposure_set": bool(self.has_exposure()),
            "exposure_limits": [float(EV_LIMIT), float(TEMP_LIMIT_K), float(TINT_LIMIT)],
            "tone_limits": [float(TONE_LIMIT)] * 4,
            "bytes_exposure": 0,      # 本层不常驻张量：报真数而不是删字段
            "device": str(self.device),
        }

    def apply_exposure(self, t):
        """每帧只走这里。没点火直接把张量递回去（不复制、不跑算子）。

        位置在 lut **之前**：曝光是场景线性域的输入变换，LUT 是显示输出变换。
        两者都不改变像素位置，所以它与形变层的次序无关紧要；但它与 lut 的次序有关：
        先过表再加曝光会把 2^EV 乘到已被表压过的值上，高光恢复能力不同。
        """
        self.last_exposure_ms = 0.0
        if not self.has_exposure():
            return t
        t0 = time.perf_counter()
        e, dk, tn, c, h, s, sa = self.exposure_params
        out = exposure_t(t, e, dk, tn, ref_k=self.exposure_ref_k,
                         contrast=c, highlights=h, shadows=s, saturation=sa,
                         prepared_wb=getattr(self, "prepared_wb", None))
        if not torch.isfinite(out).all():
            raise ValueError(f"曝光/白平衡产出非有限值，已拒：{self.exposure_params} "
                             f"ref={self.exposure_ref_k}")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_exposure_ms = (time.perf_counter() - t0) * 1000.0
        return out

    # LevelsStage owns its recipe, parameters and execution timing.
    def set_levels(self, spec): return self.levels_stage.set(spec)
    def clear_levels(self): return self.levels_stage.set(None)
    def has_levels(self): return self.levels_stage.active
    def levels_state(self): return self.levels_stage.state()
    def apply_levels(self, tensor): return self.levels_stage.apply(tensor)

    # ---- Independent RGB/master point curves -----------------------------
    def set_curves(self, spec):
        checked = curve_ops.check_curves(spec)
        compiled = curve_ops.tensor_bundles(checked, self.device, torch.float32)
        # Compile/allocate completely before committing live state.
        self.curves_spec, self.curves_compiled = checked, compiled
        return self.curves_state()

    def clear_curves(self):
        return self.set_curves(curve_ops.default_curves())

    def has_curves(self):
        return any(bundle is not None for bundle in self.curves_compiled)

    def curves_state(self):
        return {"curves": curve_ops.check_curves(self.curves_spec), "curves_set": self.has_curves()}

    def apply_curves(self, tensor):
        self.last_curves_ms = 0.0
        if not self.has_curves():
            return tensor
        start = time.perf_counter()
        result = curve_ops.curves_t(tensor, self.curves_compiled)
        if not torch.isfinite(result).all():
            raise ValueError("curves produced nonfinite pixels")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_curves_ms = (time.perf_counter()-start)*1000.0
        return result

    # ---- 八色 HSL -----------------------------------------------------------
    def has_hsl(self) -> bool:
        return bool(self.hsl_bands != (0.0,) * 24)

    def set_hsl(self, bands) -> dict:
        """整组 24 个数一次提交：先全量校验再写 live，越界/NaN 整条拒。"""
        self.hsl_bands = check_hsl(bands)
        return self.hsl_state()

    def clear_hsl(self) -> dict:
        self.hsl_bands = (0.0,) * 24
        self.last_hsl_ms = 0.0
        return self.hsl_state()

    def hsl_state(self) -> dict:
        return {"hsl_bands": [float(v) for v in self.hsl_bands],
                "hsl_names": list(BAND_NAMES),
                "hsl_centers": [float(v) for v in BAND_CENTERS],
                "hsl_limits": {"hue": float(HSL_HUE_LIMIT),
                               "sat": float(HSL_SAT_LIMIT),
                               "lum": float(HSL_LUM_LIMIT)},
                "hsl_set": bool(self.has_hsl()),
                "bytes_hsl": 0,      # 本层不常驻张量：报真数而不是删字段
                "device": str(self.device)}

    def apply_hsl(self, t):
        """每帧只走这里。没点火直接把张量递回去（不复制、不跑算子）。"""
        self.last_hsl_ms = 0.0
        if not self.has_hsl():
            return t
        t0 = time.perf_counter()
        out = hsl_t(t, self.hsl_bands)
        if not torch.isfinite(out).all():
            raise ValueError(f"八色 HSL 产出非有限值，已拒：{self.hsl_bands}")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_hsl_ms = (time.perf_counter() - t0) * 1000.0
        return out

    def apply_grade(self, t):
        """每帧只走这里。没活就直接把张量递回去（一个算子也不跑，连混合都不做）。"""
        self.last_grade_ms = 0.0
        if not self.has_grade():
            return t
        if (self.grade_scope == "objects" and self._local_mask_gpu is None
                or self.grade_scope == "skin" and (self.masks_gpu is None or "skin" not in self.mask_names)
                or self.grade_scope == "brush" and self._grade_mask_gpu is None):
            return t  # Retain intent, suspend missing masks, never apply globally.
        t0 = time.perf_counter()
        dh, ds, dv = self.grade_params
        out = grade_t(t, dh, ds, dv, amount=float(self.grade_amount))
        if not torch.isfinite(out).all():
            # 不写回也不缓存：非有限值一旦进了 shm 就是一块绿斑，而报错比绿斑好查
            raise ValueError(f"肤色定向产出非有限值，已拒：dh={dh} ds={ds} dv={dv} "
                             f"amount={self.grade_amount}")
        # COLOR-004：局部调色。混合写成 mix_masked(t, out, 1.0, w) 而不是先混色再乘，
        # 是为了让“掩膜外逐字节不变”无条件成立：w=0 时 (1-0)*t + 0*out 就是 t 本身。
        # （这里的 0*out 在 out 有限时恒为 0，而上面那道 isfinite 护栏正好保证了“有限”。）
        weight = self._grade_weight_gpu()
        if weight is not None:
            out = mix_masked(t, out, 1.0, weight)
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_grade_ms = (time.perf_counter() - t0) * 1000.0
        return out

    def grade_resident_bytes(self) -> int:
        """本层账单：以前恒为 0（它不持有张量），局部调色起，brush 作用域会常驻一份
        掩膜权重。报实数而不是报 0：“查过、确实没占显存”才是那句话，“不报”等于藏账。"""
        return self.local_grade_layers.resident_bytes() + sum(
            int(t.numel() * t.element_size()) for t in
            (self._grade_mask_gpu, self._local_mask_gpu) if t is not None)

    def effect_recovery_resident_bytes(self) -> int:
        """Disposable per-operator uint8 masks, not persisted image buffers."""
        return self.effect_recovery.resident_bytes()

    def manual_liquify_resident_bytes(self) -> int:
        """Disposable inverse/protection field and prepared sampler, not RGB."""
        return self.manual_liquify.resident_bytes()

    @property
    def last_manual_liquify_ms(self):
        return self.manual_liquify.last_ms

    @property
    def last_local_grade_ms(self):
        return self.local_grade_layers.last_ms

    # ---- PORTRAIT-009：眼牙局部增强 ---------------------------------------
    def has_enhance(self) -> bool:
        if PEOPLE_PIPE.active(self):return any(r.stage in ("enhance","eye_detail","facial_wrinkles") for r in self.people_prepared.effects)
        """这一层到底有没有活：三个数至少一个非零，而权重场里确实有额度。

        只看参数不够：“三个数都是 0.4 而掩膜是空的”（闭嘴样本的牙齿那一格、两只眼都被
        几何校验拒了的侧脸）是一层没点火的层。让 `lit=true` 与画面互相打脸，就是面板替
        引擎说谎——所以判据必须把场也算进来（`grade` 那层没有这个问题：它的场是用户画的）。
        """
        if not WSTATE.active_enhance(self.enhance_amounts):
            return False
        return bool((self.facial_wrinkle_delta is not None and bool(self.facial_wrinkle_delta.any())) or
                    (self.under_eye_delta is not None and bool(self.under_eye_delta.any())) or
                    (self.enhance_gpu is not None and any(self.enhance_amounts.get(k, 0) > 0 and
                     float(self.enhance_gpu[i].max()) > 0 for i, k in enumerate(ENH.SUBS))))

    def build_enhance(self, landmarks, *, amounts=None) -> dict:
        """从 478 点重画这一层：几何栅格 + 内容门，然后上一次卡。

        挂层成本一次性报出去（`enhance_build_ms`）：它与每帧的 `enhance_ms` 是两种钱，
        混在一起就看不出“拖滑块时到底有没有重算掩膜”这件事。
        """
        if self.src_f32 is None:
            raise RuntimeError("build_enhance 需要先 load_rgb_u8/load_rgb_f32")
        t0 = time.perf_counter()
        requested = ENH.check_amounts(self.enhance_amounts if amounts is None else amounts)
        if WSTATE.active(requested) and not any(requested[k] for k in ENH.AMOUNT_KEYS if k not in WSTATE.INTENT_KEYS):
            # Wrinkle-only work must not inherit older eye ROI rejection for a
            # clipped face. Its regions independently report visible support.
            self.clear_enhance_field()
            self.enhance_facts = {}
            self.enhance_info = {}
            self.enhance_lm_sig = self._lm_fingerprint(landmarks)
            WRUNTIME.build_preview(self, landmarks)
            self.enhance_build_ms = round((time.perf_counter() - t0) * 1000, 2)
            return self._enhance_payload(layer_recomputed=True)
        reg = ENH.geometry(landmarks, self.h, self.w)
        y0, x0, fh, fw = reg.window
        # 只把窗口那一片搬下来（不是整幅）：内容门要的只是这一块，而整幅 D2H 在
        # 产品档上是 12 MB——那笔钱没有理由付。
        win = (self.src_f32[:, :, y0:y0 + fh, x0:x0 + fw]
               .permute(0, 2, 3, 1).to("cpu", torch.float32).numpy()[0])
        weight, facts = ENH.refine(reg, win)
        self.enhance_field = weight
        self.enhance_gpu = torch.as_tensor(weight, device=self.device)
        self.enhance_lm_sig = self._lm_fingerprint(landmarks)
        self.enhance_window = tuple(reg.window)
        self.enhance_local = tuple(reg.window)     # 会话原点就是画布原点
        window, lm = UNDER.bounds(landmarks, self.h, self.w)
        uy, ux, uh, uw = window
        under_source = self.repair_base if self.repair_base is not None else self.src_f32
        pixels = under_source[0, :, uy:uy+uh, ux:ux+uw].permute(1, 2, 0).to("cpu", torch.float32).numpy()
        self.under_eye_layer = UNDER.UnderEyeLayer(window, pixels, lm)
        self.under_eye_layer.source_version = self.repair_version
        self.enhance_facts = facts
        WRUNTIME.build_preview(self, landmarks)
        self.enhance_info = reg.info
        self.enhance_build_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return self._enhance_payload(layer_recomputed=True, build_ms=self.enhance_build_ms)

    def set_enhance_field(self, window, weight, *, origin=(0, 0)) -> dict:
        """挂一份**已经算好的**权重场。导出分块走这条路（与 grade_mask 逐块切同一条先例）。

        `window` 是画布坐标 (y0,x0,fh,fw)，`origin` 是本会话那块网格左上角的画布坐标：
        导出给每个块新建一份 PreviewPipeline，它的 (0,0) 不是画布的 (0,0)。不报原点就会
        把整幅的掩膜往块里贴，而块里的眼睛会被画到下巴上——那不是“没效果”，是**错效果**。
        """
        y0, x0, fh, fw = (int(v) for v in window)
        arr = np.asarray(weight, dtype=np.float32)
        if arr.shape != (3, fh, fw):
            raise ValueError(f"增强权重场形状 {arr.shape} 与窗口 {(3, fh, fw)} 不合")
        if not np.isfinite(arr).all():
            raise ValueError("增强权重场含非有限值，整层拒绝")
        oy, ox = int(origin[0]), int(origin[1])
        ly0, lx0 = y0 - oy, x0 - ox
        # 与本会话求交：完全在块外就整层不挂（该块逐字节与原片同），而不是贴一个空场
        iy0, ix0 = max(0, ly0), max(0, lx0)
        iy1, ix1 = min(self.h, ly0 + fh), min(self.w, lx0 + fw)
        if iy1 <= iy0 or ix1 <= ix0:
            self.clear_enhance_field()
            return self._enhance_payload(layer_recomputed=False)
        sub = arr[:, iy0 - ly0:iy1 - ly0, ix0 - lx0:ix1 - lx0]
        self.enhance_field = np.ascontiguousarray(sub)
        self.enhance_gpu = torch.as_tensor(self.enhance_field, device=self.device)
        self.enhance_local = (iy0, ix0, iy1 - iy0, ix1 - ix0)
        # 画布坐标只在这里报“这一块实际盖到了哪”：导出事件的账要对得上块，而不是对得上原图
        self.enhance_window = (iy0 + oy, ix0 + ox, iy1 - iy0, ix1 - ix0)
        self.enhance_build_ms = 0.0
        return self._enhance_payload(layer_recomputed=True)

    @staticmethod
    def _lm_fingerprint(landmarks) -> int:
        """关键点的进程内指纹（`hash(bytes)` 在同一次解释器里稳定，跨进程不稳定——
        而跨进程本来就要重画，所以这个性质正好）。"""
        arr = np.ascontiguousarray(np.asarray(landmarks, dtype=np.float32))
        return hash(arr.tobytes())

    def enhance_needs_rebuild(self, landmarks, *, amounts=None) -> bool:
        """这张场还能不能复用：没挂过、或关键点变了，就得重画。"""
        if amounts is not None and self.enhance_gpu is None and any(amounts.get(k, 0) for k in ENH.AMOUNT_KEYS if k not in WSTATE.INTENT_KEYS):
            return True
        return self.enhance_lm_sig != self._lm_fingerprint(landmarks)

    def clear_enhance_field(self) -> None:
        """放下权重场（参数不动）。没场的层就是没点火，`has_enhance()` 会如实说 false。"""
        WRUNTIME.clear_layer(self)
        self.enhance_lm_sig = None
        self.under_eye_layer = None
        self.under_eye_delta = None
        self.under_eye_local = None
        self.enhance_field = None
        self.enhance_gpu = None
        self.enhance_window = None
        self.enhance_local = None
        self.enhance_lm_sig = None      # 场放下了，指纹也没了：下一次必须重画

    def set_enhance(self, amounts) -> dict:
        """提交三个数。先全量校验，后才写入——被拒不留半截状态（与各层 setter 同规）。"""
        checked = ENH.check_amounts(amounts)
        WLAYER.refresh_source(self)
        WRUNTIME.solve_preview(self, checked)
        UNDER.refresh_source(self)
        if self.under_eye_layer is not None:
            delta = self.under_eye_layer.solve(checked)
            UNDER.attach_delta(self, self.under_eye_layer.window, delta)
            self.enhance_facts.update(self.under_eye_layer.facts)
        self.enhance_amounts = checked
        return self._enhance_payload(layer_recomputed=False)

    def clear_enhance(self) -> dict:
        """整层放下：三个数回零并把常驻场放掉。

        与 `clear_grade` 的分工不同处要写出来：定向层的区域是用户拿笔画的，归零不该抹笔迹；
        而这一层的场是从关键点重算的**派生物**，没有“用户画的东西”要保，所以留着它只会
        占一块没人能看见的常驻显存（`lit=false` 而 `bytes_enhance>0` 就是那种打脸）。
        要重新点火走 build_enhance（关键点还在，重算几百微秒）。
        """
        self.enhance_amounts = {k: 0.0 for k in ENH.AMOUNT_KEYS}
        self.clear_enhance_field()
        self.enhance_facts = {}
        self.enhance_info = {}
        self.last_enhance_ms = 0.0
        self.enhance_build_ms = 0.0
        return self._enhance_payload(layer_recomputed=False)

    def apply_enhance(self, t):
        """每帧只走这里。没活就直接把张量递回去（一个算子也不跑，连混合都不做）。"""
        self.last_enhance_ms = 0.0
        if PEOPLE_PIPE.active(self): return PEOPLE_PIPE.post_effects(self,t)
        UNDER.refresh_source(self)
        if not self.has_enhance():
            return t
        t0 = time.perf_counter()
        if MOUTHR.has_source_geometry(self):
            from .brow_shape_consumers import apply_enhance
            return apply_enhance(self,t)
        if self.enhance_local is None:
            out = UNDER.apply_delta(self, t)
            if self.device.type != "cpu":
                torch.cuda.synchronize(self.device)
            self.last_enhance_ms = (time.perf_counter() - t0) * 1000.0
            return out
        ly0, lx0, lh, lw = self.enhance_local
        sub = t[:, :, ly0:ly0 + lh, lx0:lx0 + lw]
        eff = ENH.enhance_t(sub, self.enhance_gpu, self.enhance_amounts)
        # 写回走 clone + 切片赋值：掩膜外的像素因此是**复制**过去的而不是混合出来的，
        # “掩膜外逐字节不变”这条承诺不依赖浮点巧合（与 apply_grade 用 mix_masked 等价，
        # 但这里窗口外那些像素连混合式都不该进——它们离掩膜有几百像素远）
        out = t.clone()
        out[:, :, ly0:ly0 + lh, lx0:lx0 + lw] = eff
        out = UNDER.apply_delta(self, out)
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_enhance_ms = (time.perf_counter() - t0) * 1000.0
        return out

    def enhance_resident_bytes(self) -> int:
        """本层账单：窗口那一片 float32 权重场。没挂就是 0（不是“查过没有”的 0）。"""
        n = WRUNTIME.resident_bytes(self) + LIPR.resident_bytes(self)
        if PEOPLE_PIPE.active(self):
            n += sum(a.nbytes for record in self.people_prepared.effects for a in (record.delta,record.weights) if a is not None)
            n += sum(record["weight"].nbytes for record in self.people_prepared.recovery.values())
            n += sum(field.resident_bytes() for field in (*self.people_prepared.face_fields,*self.people_prepared.body_fields))
        brow = getattr(self,"brow_shape_field",None)
        n += brow.resident_bytes() if brow else 0
        nose = getattr(self,"nose_shape_field",None)
        n += nose.resident_bytes() if nose else 0
        eye = getattr(self,"eye_shape_field",None)
        n += eye.resident_bytes() if eye else 0
        mouth = getattr(self,"mouth_shape_field",None)
        n += mouth.resident_bytes() if mouth else 0
        if self.under_eye_delta is not None:
            n += self.under_eye_delta.numel() * self.under_eye_delta.element_size()
        if self.under_eye_layer is not None:
            n += self.under_eye_layer.source.nbytes
            if self.under_eye_layer.delta is not None:
                n += self.under_eye_layer.delta.nbytes
        if self.enhance_gpu is not None:
            n += int(self.enhance_gpu.numel() * self.enhance_gpu.element_size())
        if self.enhance_field is not None:
            n += int(self.enhance_field.nbytes)
        return n

    def _enhance_payload(self, *, layer_recomputed: bool, build_ms: float | None = None) -> dict:
        """enhance_done 的图层字段只在这里组装一次（set/build/clear/挂场/放场共用一份形状）。

        三个子功能的“点火事实”必须随事件走：每个子层的额度像素数与被拦原因。闭嘴样本的
        牙齿那一格、被几何校验拒掉的侧脸，UI 要能**看到**而不是**推断**“那一格没活”——
        推断出来的那一句在换图之后就是说谎。
        """
        a = dict(self.enhance_amounts)
        subs = list(ENH.EFFECT_KEYS)
        facts = self.enhance_facts or {}
        return {
            "enhance_amounts": {k: float(a[k]) for k in ENH.AMOUNT_KEYS},
            "enhance_subs": subs,
            "enhance_limit": float(ENH.AMOUNT_LIMIT),
            "enhance_set": WSTATE.active_enhance(a),
            "enhance_facial_wrinkles": {k: dict(facts.get(k) or {}) for k in WSTATE.KEYS},
            "enhance_lit": bool(self.has_enhance()),
            "enhance_built": bool(self.enhance_gpu is not None or self.facial_wrinkle_layer is not None or self.facial_wrinkle_tile_key is not None),
            "enhance_gated_px": {k: int((facts.get(k) or {}).get("gated_px", 0)) for k in subs},
            "enhance_geom_px": {k: int((facts.get(k) or {}).get("geom_px", 0)) for k in subs},
            "enhance_reason": {k: (facts.get(k) or {}).get("reason") for k in subs},
            "enhance_mouth": dict((self.enhance_info or {}).get("mouth") or {}),
            "enhance_eyes": [dict(e) for e in ((self.enhance_info or {}).get("eyes") or [])],
            "enhance_window": list(self.enhance_window) if self.enhance_window else None,
            "bytes_enhance": int(self.enhance_resident_bytes()),
            "enhance_ms": round(self.last_enhance_ms, 2),
            "enhance_build_ms": round(self.enhance_build_ms if build_ms is None else build_ms, 2),
            "device": str(self.device),
            "layer_recomputed": bool(layer_recomputed),
        }

    # ---- M6：换底层 ----------------------------------------------------
    def has_background(self) -> bool:
        return bool(self.bg_active and self.bg_matte is not None and self.bg_ref is not None)

    def set_background(self, matte, bg, *, image_bg=None) -> dict:
        """提交一组常驻换底：先全量校验、后才写回（被拒不留半截）。同 set_grade 的铁律。

        matte：(H,W) [0,1] float 或 uint8(0..255)。bg：(3,) [0,1] 单色，或 image_bg 为 (H,W,3)
        整幅背景（二者取其一）。任何形状/非有限不匹配都拒，不往 shm 里递一块坏帧。
        """
        if self.sky_replacement.value["enabled"]:
            raise ValueError("完整换背景会覆盖天空替换，请先关闭天空效果")
        if matte.shape != (self.h, self.w):
            raise ValueError(f"遮罩形状 {matte.shape} 与会话 {self.h}x{self.w} 不符")
        m = np.asarray(matte, dtype=np.float64)
        if np.asarray(matte).dtype == np.uint8:
            m = m / 255.0
        if not np.isfinite(m).all():
            raise ValueError("遮罩含非有限值，已拒")
        m = np.clip(m, 0.0, 1.0)
        if image_bg is not None:
            b = np.asarray(image_bg, dtype=np.float64)
            if b.shape != (self.h, self.w, 3):
                raise ValueError(f"背景图形状 {b.shape} 与会话不符")
            if not np.isfinite(b).all():
                raise ValueError("背景图含非有限值，已拒")
            b = np.clip(b, 0.0, 1.0)
            b = np.ascontiguousarray(b.transpose(2, 0, 1))[None]        # (1,3,H,W)
            bref = torch.tensor(b, dtype=torch.float32, device=self.device)
        else:
            c = np.asarray(bg, dtype=np.float64).reshape(3)
            if not np.isfinite(c).all():
                raise ValueError("背景色含非有限值，已拒")
            c = np.clip(c, 0.0, 1.0)
            bref = torch.tensor(c.reshape(1, 3, 1, 1), dtype=torch.float32,
                                device=self.device)
        mt = torch.as_tensor(m, dtype=torch.float32, device=self.device)[None, None].contiguous()
        self.bg_matte, self.bg_ref = mt, bref
        self.bg_active = True
        return self._bg_payload()

    def clear_background(self) -> dict:
        self.bg_matte = None
        self.bg_ref = None
        self.bg_active = False
        self.last_bg_ms = 0.0
        return self._bg_payload()

    def _bg_payload(self) -> dict:
        return {"bg_active": bool(self.has_background()),
                "bytes_bg": int(self.bg_resident_bytes()),
                "device": str(self.device)}

    def bg_resident_bytes(self) -> int:
        if not self.has_background():
            return 0
        return int(self.bg_matte.numel() * self.bg_matte.element_size()
                   + self.bg_ref.numel() * self.bg_ref.element_size())

    def apply_background(self, t):
        """每帧只走这里。没活就把张量递回（一个算子也不跑，连混合都不做）。"""
        self.last_bg_ms = 0.0
        if not self.has_background():
            return t
        t0 = time.perf_counter()
        from .ops.matting import composite_t
        matte = self.align_source_grade_mask(self.bg_matte) if MOUTHR.has_source_geometry(self) else self.bg_matte
        out = composite_t(t, matte, self.bg_ref)
        # t already contains every foreground edit. Never blend with src_f32.
        out = self.effect_recovery.apply('background_replace', t, out,
                                         align=self.align_source_grade_mask)
        if not torch.isfinite(out).all():
            raise ValueError("换底合成产出非有限值，已拒（不写回也不缓存）")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_bg_ms = (time.perf_counter() - t0) * 1000.0
        return out

    def pack(self, out) -> None:
        """float→uint8 并写进常驻帧缓冲，同样全程在显存里做。

        **量化必须四舍五入，不是向零截断**。M2-a2 探针量出来的：`x.to(torch.uint8)`
        与 `astype(np.uint8)` 都是截断，对任意非格点值（实测 ×0.9875 与 ×1.0125）
        平均偏暗 0.48 LSB、绝对误差也正好 0.48 LSB，而舍入是 0.0000。也就是说
        只要画面不是原封不动的解码值，每一帧都在把全图压暗半级 LSB——暗部渐变
        多出可见的阶调台阶，而且预览与导出永远差半档。

        为什么以前没被“最大 1 LSB”的验收口径挡住：截断与舍入只在值不在格点上时
        才有差，磨皮/混合的输出离格点远，两臂又用同一个截断，偏差在对比里抵消了。
        D&B 把 gain≈1 的输出精确送回格点，才把这笔账算出来。

        也不用就地 clamp_：那会把调用方传进来的张量（包括常驻缓存）直接修改。
        """
        self.frame_gpu[..., :3] = quantize_t(out)[0].permute(1, 2, 0)

    def render_original(self) -> None:
        """Display the oriented working-space source, bypassing EVERY edit layer.

        Cropping is also an edit: this is the full original image, not a cropped
        or partially color-adjusted approximation. The recipe and layer caches
        are untouched; normal render restores the edited frame afterward.
        """
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb 再看原图")
        self.pack(self.src_f32)

    def render(self, strength: float, channel: str | None = None, **kw) -> None:
        """按当前全部编辑层出帧；strength=0 只关闭磨皮，原图对比用 render_original。"""
        self.pack(self.retouch(strength, channel=channel, **kw))

    def read_back(self) -> np.ndarray:
        """一次 D2H，返回可直接交给 shm.write_frame 的连续 (H,W,4) uint8。"""
        if self.frame_gpu is None:
            raise RuntimeError("尚未渲染")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        return self.frame_gpu.cpu().numpy()

    def stamp(self, seq: int) -> None:
        """把序号写进常驻帧缓冲里一个 16×16 小块——只给跑靶当「帧真的在换」的证据。

        位置与写法跟 frames.test_frame 逐字一致，两条臂因此可用同一套像素比对。
        生产通路不调它（HUD 由 WebGL 叠）。放在这里而不是让调用方改 numpy，是因为
        CPU 设备上 .cpu() 返回的就是常驻张量本身，在外面改等于改到了基图上。
        """
        if self.frame_gpu is None:
            raise RuntimeError("先 load_rgb_u8")
        s = seq & 0xFF
        blk = self.frame_gpu[16:32, 16:32]
        blk[..., 2] = s
        blk[..., 0] = 255 - s

    # ---- 以低频层为入的算法（M2 中性灰/质感）自己调 ops.guided.guided_t，
    # 不再在这里留一份 low_freq：上一版它引用了没 import 的 guided_t，一调就是 NameError；
    # 全仓 grep 以证明没有任何调用方，留着只会等一个偶现崩溃。


def make_pipeline(device: str, w: int, h: int, rgb: np.ndarray | None = None) -> PreviewPipeline:
    p = PreviewPipeline(device, w, h)
    if rgb is not None:
        p.load_rgb_u8(rgb)
    return p


def _warm_grade(x):
    """预热用的“非恒等但温和”的调色：整体压暗 2% + 蓝通道微量抬升。

    它必须**不是**恒等表：neutral 判定为真时 apply_lut 直接短路，grid_sample(3d)
    一个内核也不会跑，那句“已预热 3D 内核”就又成了恒真断言（M2 审 ⑤ 那个形状）。
    真预设是 M3-b 的事；预热只要走到同一个采样内核即可，不拿产品预设当靶。
    """
    return np.clip(x * 0.98 + np.array([0.0, 0.004, 0.010]), 0.0, 1.0)


def warm_device(device: str, side: int = 64) -> float:
    """把 GPU 上下文与首帧内核加载的成本从“导入第一张图”里挑出来，返实测 ms。

    为什么要挑出来：F 轮实测冷进程首图 ~299 ms、后续 ~35 ms，那 265 ms 与图尺寸无关，
    是上下文建立与内核模块首次加载——它挂在用户第一次点“导入”上，体感就是
    “这软件第一张特别慢”。引擎是后台起的，这笔钱付在起进程时没人看得见。

    预热跑的就是首帧那条链（建张量 → 盒式滤波 → 归一化混合 → uint8 打包 → 回读），
    不是空转一个 `torch.add` 报个好看的数——那样“预热了”三个字盖住的正是没被加载的
    那几个内核。设备不可用（没 torch / 没 GPU）时返 0.0，调用方据此不报预热事件。

    M2-a2 把修容链也纳进来：真窗口实测第一笔修容 light_ms 68.64 ms、后续 3.3 ms，
    那 65 ms 是 sRGB↔linear、带限 box 与 pow 这组内核首次加载。修容笔是产品里
    第一个“画下去立刻要看结果”的手势，这笔钱不能留在用户的第一笔上。

    M2-b 再把形变链纳进来：grid_sample 与恒等网格也是首拖才首次加载的内核。
    它用的关键点是 `analytic_frontal_landmarks` 那份解析几何（只为了把内核跑起来），
    不是产品路径——产品路径的形变必须拿 precompute 的真关键点。

    M3-a2 再把调色链纳进来：grid_sample 的 **3D** 与形变用的 **2D** 不是同一个编译单元，
    形变预热覆盖不到它——第一次载入 .cube 会白付一次内核加载（修容第一笔 68.6 ms 的
    同一个坑）。用的表是 `_warm_grade` 烘出来的非恒等表：恒等表会被 neutral 短路，
    那一句“已预热”就是假的。
    """
    if torch is None or not str(device).startswith("cuda") or not torch.cuda.is_available():
        return 0.0
    t0 = time.perf_counter()
    pipe = PreviewPipeline(device, side, side)
    try:
        pipe.load_rgb_u8(np.zeros((side, side, 3), dtype=np.uint8))
        pipe.render(0.5)
        # 修容臂：给一支半覆盖的笔，走的就是 cmd_light 之后每一帧走的那条链
        # （_commit_light 建场 → lighten_source/lighten_result 各跑一次 db → 混合）。
        pipe.set_light_ops([LightOp(op_id=1, weight=np.full((side, side), 128, np.uint8),
                                    sign=1)])
        pipe.set_light_params(DEFAULT_DB_EXPOSURE, DEFAULT_DB_RADIUS)
        pipe.render(0.5)
        # 形变臂：M2-b。grid_sample 与“恒等网格”这两份内核首次加载也要挑出来，
        # 否则用户第一次拖“瘦脸”滑块会白付一次内核加载（修容第一次落笔就是 65 ms 的前车）。
        pipe.build_deform(analytic_frontal_landmarks())
        pipe.set_deform_amounts({"slim_face": 0.5, "big_eye": 0.3, "small_chin": 0.2})
        pipe.render(0.5)
        # 调色臂：M3-a2。走的就是产品那一条路：bake → set_lut（上显存）→ render。
        # 首次执行就是内核加载那一笔：把它付在预热会话里，而不是付在用户第一次载入 .cube 上；
        # 之后的每帧就只剩实测那 0.35 ms 的真实成本。
        pipe.set_lut(bake(_warm_grade, QUALITY_SIZE_3D, title="warm", source="warm"), 1.0)
        pipe.render(0.5)
        # 肤色定向臂：M3-b。它是逐帧新的一组 elementwise 内核（HSV 正/反变换、三次
        # smoothstep、混合），调色那次预热只证了 grid_sample(3d) 已加载，盖不到它——
        # 同一个形状的事在修容（68.6 ms）与调色（3D 与 2D 不是一个编译单元）上各付过一次。
        # 用的数值与产品预设同量级，但不从 presets 取：预热不该把产品资产当靶。
        pipe.set_grade(0.006, -0.14, 0.05)
        pipe.render(0.5)
        torch.cuda.synchronize()        # 与引擎 _sync 同一个理由：不同步就把内核记到回读头上
        pipe.read_back()
    finally:
        pipe.retouched = None
        pipe.bands = None
        pipe.src_u8 = None
        pipe.src_f32 = None
        pipe.frame_gpu = None
        # 修容层的场与两份 db 结果必须一起丢掉：预热会话是临时的，把它的图层留在
        # 模块级引用上，下一个真会话可能继承一张不存在的笔印
        pipe.light_field_gpu = None
        pipe.light_src = None
        pipe.light_res = None
        pipe.light_ops = []
        pipe.light_redo = []
        # 形变层同理：三个单位场 + 恒等网格共 5 份张量，留在临时会话上就是泄显存
        pipe._deform_warp = None
        pipe._deform_warp_key = None
        pipe.deform_units = {}
        pipe.deform_grid_base = None
        pipe.deform_meta = {}
        # 调色层同理：那张预热用的临时表与它的体积不能让下一个真会话继承——
        # 否则 image_ready 里 bytes_lut 会多报 428 KB，而用户一张预设也没点
        pipe.lut = None
        pipe.lut_vol = None
        # 定向层同理：它只带三个数，但留着就是下一个会话开局“已点火”、
        # 而用户一个预设也没点（image_ready 里 grade 会多报一份不存在的影响）
        pipe.grade_params = (0.0, 0.0, 0.0)
        pipe.grade_amount = 1.0
        pipe.last_grade_ms = 0.0
        # 曝光层同理：三个数留着就是下一个会话开局“已点火”，而用户一个滑块也没碰
        pipe.exposure_params = (0.0,) * 7
        pipe.exposure_ref_k = REFERENCE_K
        pipe.wb_options = pipe.prepared_wb = None
        pipe.last_exposure_ms = 0.0
        pipe.hsl_bands = (0.0,) * 24
        pipe.last_hsl_ms = 0.0
        pipe.levels_stage = LevelsStage()
        pipe.curves_spec = curve_ops.default_curves()
        pipe.curves_compiled = (None,) * 5
        pipe.last_curves_ms = 0.0
        # 换底层同理：预热会话上挂的遮罩/背景张量不能让下一个真会话继承，
        # 否则 image_ready 里 bytes_bg 会多报一份用户从未点过的常驻。
        pipe.bg_matte = None
        pipe.bg_ref = None
        pipe.bg_active = False
        pipe.last_bg_ms = 0.0
    return (time.perf_counter() - t0) * 1000.0
