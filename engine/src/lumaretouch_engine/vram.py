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

import math
from dataclasses import dataclass, field

import numpy as np
import time

try:
    import torch          # 与 ops.guided 同一约定：torch 未装（M0 纯通路、CI 的 CPU job）
except Exception:        # 也要能 import 成功，不然整个测试收集阶段就报 ModuleNotFoundError
    torch = None

from .ops.guided import (bands_t, combine_t, mix_masked,
                         DEFAULT_BROAD_GAIN, DEFAULT_DETAIL_GAIN, DEFAULT_EPS,
                         DEFAULT_MID_GAIN, DEFAULT_RADIUS, DEFAULT_TEXTURE_RADIUS)
from .ops.inpaint import crop_apply_t, hole_extent, inpaint_t, levels_for, mask_bbox
from .ops.deform import (KINDS, analytic_frontal_landmarks, check_amounts,
                         identity_grid, unit_field, warp_t)
from .ops.light import dodge_burn_t, DEFAULT_DB_EXPOSURE, DEFAULT_DB_RADIUS
from .quant import quantize_t

# 磨皮参数默认值只有一个出处：ops.guided（探针量出来的），这里只转发不改数。
# 以前在这里写字面量、server 里又写一份，就是 M1-2 那次「默认值改了但调用方还带着
# 旧字面量」的同构隐患。

# 消除笔（M1-4）默认参数。refine_iters=6 不是凑的：整幅跑“平滑1/PM6”在产品代理档 9.4 ms，
# 比 PM2 多 4 ms 买到的是孔径 6→5.1 LSB、口径 12→6.3 LSB；而 PM12 再翻一倍时间只多拿 0.2 LSB。
# pad 是裁块边距下限，洞大时按 hole 半径自动扩（mask_bbox 里的 grow）。
DEFAULT_REPAIR = dict(smooth_iters=1, refine_iters=6, kappa=0.06, pad=32, grow=1.5)


@dataclass
class RepairOp:
    """一次消除笔操作：只存画笔覆盖度（uint8, 0..255）与参数，**不存结果**。

    为什么不存结果：存 `(3,H,W) float32` 补丁在产品代理档是 6.8 MB/笔，五十笔就是 340 MB；
    而修补算子是确定性的，重算一次几毫秒。只存输入等于天然支持撤销/重做与换设备重建，
    也不需要一套“图层产物”的失效逻辑——这与决策 11（非破坏、重放）是同一条路。
    """

    op_id: int
    weight: np.ndarray            # (H,W) uint8，画笔覆盖度
    params: dict = field(default_factory=lambda: dict(DEFAULT_REPAIR))

    @property
    def area_px(self) -> int:
        return int((self.weight > 0).sum())

    def nbytes(self) -> int:
        return int(self.weight.nbytes)


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


class PreviewPipeline:
    """一张图的 GPU 常驻预览会话。

    拆成 retouch()/pack() 两步而不是一个大函数，是为了让跑靶能把「滤波内核」
    和「float→uint8 收尾」分开计时——只有分开量，才能证明省下的 25 ms 全在
    搬运上，而不是顺手把算法也跳过了。
    """

    def __init__(self, device: str, w: int, h: int):
        if torch is None:
            raise RuntimeError("torch 未安装，显存常驻预览路径不可用（装 rocm/cuda/cpu 任一变体）")
        self.w, self.h = w, h
        want_cuda = device.startswith("cuda")
        if want_cuda and not torch.cuda.is_available():
            # 静默退到 CPU 会让「GPU 常驻」的结论变成假的，必须让调用方能看见
            self.fallback = f"要求 {device}，但 torch.cuda.is_available()=False，已退到 cpu"
            device = "cpu"
        else:
            self.fallback = None
        self.device = torch.device(device)
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
        # M2-b：形变层。存的是三种形变各自的**单位场**（amount=1 时的位移场），
        # 滑块值只当系数用。为什么能这样拆：TPS 的解对右端项线性，而请求位移与
        # amount 成正比，所以 field(a) = a·field(1) 是恒等而不是近似
        # （探针 m2b4 量到 ‖f(0.5)−0.5·f(1)‖max = 0.000e+00 px）。
        # 于是拖滑块期间一次 TPS 都不解——那玩意在 GPU 上 float64 要 34–79 ms。
        self.deform_units: dict[str, torch.Tensor] = {}
        self.deform_amounts: dict[str, float] = {k: 0.0 for k in KINDS}
        self.deform_grid_base: torch.Tensor | None = None      # 恒等网格，常驻
        self.deform_version: int = 0
        self.deform_meta: dict[str, dict] = {}
        self.last_deform_ms: float = 0.0
        # build_deform 的累计次数。拖滑块期内它必须不增——这才是“零推理”的可测口径：
        # 每帧的 deform ms 无论如何都 > 0（grid_sample 真在跑），拿它当“有没有重算”
        # 的判据会恒真。计数器只能由解算那一层递增，伪代码伪不出一个不增的数。
        self.deform_builds: int = 0

    # ---- 装载：一次性 H2D ----------------------------------------------
    def load_rgb_u8(self, rgb: np.ndarray) -> None:
        """(H,W,3) uint8 → 显存常驻。整场会话只调一次（导入或换图时）。"""
        if rgb.shape[:2] != (self.h, self.w):
            raise ValueError(f"源图尺寸 {rgb.shape[:2]} != 会话 {self.h}x{self.w}")
        arr = np.ascontiguousarray(rgb.transpose(2, 0, 1))[None]
        # 不开 non_blocking：从 pageable 内存异步上传，调用方一释放这块 numpy 就是未定义行为；
        # 这里整场会话只走一次，同步拷贝不花什么钱。
        self.src_u8 = torch.from_numpy(arr).to(self.device)
        self.src_f32 = self.src_u8.to(torch.float32).div_(255.0)
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
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)

    def _reset_deform(self) -> None:
        """换图时清形变层：单位场是从这张图的关键点解出来的，对下一张图没有意义。"""
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
                channel: str | None = None):
        """只跑算法，返回显存里的 float (1,3,H,W)。滑块每动一次调一次。

        channel 给定时走分通道渲染（掩膜加权），不给定时全图。两条都是纯 GPU。

        M1-3c：滤波结果走常驻缓存，这一步退化成一个线性插值。缓存路径与逐帧重算
        不是“近似相等”而是逐字节相等——混合用的表达式与操作数都完全相同：
        全图 `(1-s)*img + s*out`，分通道 `mix_masked(img, out, s, weight)`。
        因此 strength=0 恒等那条承诺一分不改：`0*out` 仍然恒为 0。
        """
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb_u8 再 render")
        # 每帧的 db 应用成本从 0 起算：它必须只由“这一帧真跑了什么”给出，
        # 不能把上一次建层的成本混进来（那是事件驱动的一次性账，另走 light_ms）
        self.last_light_ms = 0.0
        self.prepare(radius=radius, eps=eps, detail_gain=detail_gain,
                     mid_gain=mid_gain, broad_gain=broad_gain,
                     texture_radius=texture_radius)
        # M2-a2：两个混合操作数各自过一遍修容层。没画过修容时 lighten_* 直接把
        # 原张量递回来（不复制、不跑算子），所以混合式与操作数与 M2-a 完全相同，
        # strength=0 逐字节恒等那条承诺一分不改。
        base = self.lighten_source()
        result = self.lighten_result()
        out = mix_masked(base, result, strength, self.mask(channel)) if channel is not None \
            else (1.0 - strength) * base + strength * result
        # M2-b：形变盖在最后。为什么不盖在底图上：那样拖任意一个滑块都要把 9 ms 的
        # 分带重跑（底图变了），零推理那条承诺就碎了。盖在最后每帧只多一次 grid_sample。
        return self.apply_deform(out)

    # ---- M1-3b：预计算产物的常驻与取用 ------------------------------------
    def load_face(self, precompute) -> dict:
        """把人脸关键点与语义掩膜一次性上显存。整张图只走这一次。"""
        if self.src_u8 is None:
            raise RuntimeError("先 load_rgb_u8：掩膜尺寸必须对得上会话尺寸")
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
        painted = 0
        boxes: list = []
        cur = self.src_f32
        for op in ops:
            p = dict(op.params)
            wsub_np = op.weight.astype(np.float32) / 255.0
            painted += int((op.weight > 0).sum())
            box = mask_bbox(wsub_np, pad=int(p.get("pad", DEFAULT_REPAIR["pad"])),
                            grow=float(p.get("grow", DEFAULT_REPAIR["grow"])))
            if box is None:
                continue
            y0, y1, x0, x1 = box
            lv = levels_for(hole_extent(wsub_np), y1 - y0, x1 - x0)
            sub = cur[..., y0:y1, x0:x1]
            wsub = torch.from_numpy(np.ascontiguousarray(wsub_np[None, None, y0:y1, x0:x1])).to(self.device)
            fill = inpaint_t(sub, wsub, levels=lv,
                             smooth_iters=int(p.get("smooth_iters", DEFAULT_REPAIR["smooth_iters"])),
                             refine_iters=int(p.get("refine_iters", DEFAULT_REPAIR["refine_iters"])),
                             kappa=float(p.get("kappa", DEFAULT_REPAIR["kappa"])))
            cur = crop_apply_t(cur, box, fill)
            boxes.append([int(v) for v in box])
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
        self.deform_amounts = dict(self.deform_amounts, **got)
        return {"amounts": dict(self.deform_amounts),
                "built": bool(self.deform_units),
                "lit": bool(self.has_deform())}

    def apply_deform(self, t):
        """把当前形变层施加到一份常驻张量上。每帧只走这里，不走 TPS 解算。"""
        self.last_deform_ms = 0.0
        if not self.has_deform():
            return t
        t0 = time.perf_counter()
        delta = None
        for kind, unit in self.deform_units.items():
            a = self.deform_amounts.get(kind, 0.0)
            if a == 0.0:
                continue
            delta = unit * a if delta is None else delta + unit * a
        if delta is None:
            return t
        out = warp_t(t, delta, 1.0, base=self.deform_grid_base)
        if not torch.isfinite(out).all():
            raise ValueError("形变产出非有限值，已拒绝：amounts="
                             f"{self.deform_amounts}")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        self.last_deform_ms = (time.perf_counter() - t0) * 1000.0
        return out

    def deform_resident_bytes(self) -> int:
        """形变层的显存账单：三个单位场 + 恒等网格。"""
        total = 0
        for t in list(self.deform_units.values()) + [self.deform_grid_base]:
            if t is not None:
                total += int(t.numel() * t.element_size())
        return total

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

    def render(self, strength: float, channel: str | None = None, **kw) -> None:
        """算一帧写进常驻帧缓冲。strength=0 时不论有没有掩膜都应当逐字节等于原图。"""
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
        pipe.deform_units = {}
        pipe.deform_grid_base = None
        pipe.deform_meta = {}
    return (time.perf_counter() - t0) * 1000.0
