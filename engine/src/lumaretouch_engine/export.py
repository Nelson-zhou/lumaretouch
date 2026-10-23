"""M4 全尺寸分块导出：把预览那条链按 tile 切块跑满幅，显存峰值只随 tile 走。

为什么必须分块（`gpuspike/m4a.py` A 组实测，RX 7600 XT 16 GiB）：整幅一次跑的峰值
**约 84 MiB / 每 MB 源图**——2.1 MB 要 209 MiB，33.3 MB 要 2 786 MiB，而 71.4 MB
（6000×3968）直接 HIP OOM（"Tried to allocate 4.26 GiB"）。预览靠代理档把这件事躲掉了，
导出没有"代理"可躲：用户要的就是那 2400 万像素。分块之后峰值只由 tile 面积决定
（D 组：2150 宽与 6000 宽的 tile512 峰值同为 125.3 MiB），这才是"防爆显存"的实证口径。两笔不在这条口径里，各自单独记账
（`packaging/m4-export-bench.py` 第 5 节）：形变场按行带求值，峰值只随 `_FIELD_BAND_PX`
走，代价是场按整幅活在系统内存；消除笔按洞的 bbox 满幅预跑，峰值随 bbox 走（切 tile
去解它会换掉 levels 与 bbox，那才是真的错）。
手动液化另需整幅 CPU 位移/保护场；下面既有链的测量不覆盖这个新阶段，
新阶段的边界叠加和内存预检是保守实现，仍需本地分块与整幅质量验收。

margin 从哪来（`m4a2.py` 逐参数定点验证，不是推算）：
    分带     blur=box(rf) → low1=guided(blur, r) → base=guided(low1, 2r)
             每层 box 跨 2r，所以支撑 = 2·rf + 6·r
    修容     box(db_radius) → 2·r_db
    自动形变 warp 采样的位移 + 双线性那一脚 → ceil(peak|delta|) + 1
    手动液化 最终 RGB 采样另加 ceil(peak|manual|) + 1，不能与上游取 max
    消除笔   在分块**之前**按洞的 bbox 整幅跑一次，所以它不往 margin 里加东西
    色彩     逐点（lut/grade）——结构上就不需要 margin
实测结论：按这个公式给的 margin 下，分块与整幅单 pass **最大 1 LSB**，差异像素 ≤
0.03%（329 / 1.29 MP），而且**不落在 tile 网格线上**（边界占比与随机水平同量级）；
margin 少 8 px 时差异像素就成倍涨并且一半压在网格线上（那是真接缝）。1 LSB 那一点是
积分图 cumsum 前缀不同带来的 float64 舍入，属结构性而不是算法差异——这条口径写在
跑靶里，不写成"逐字节相等"，因为那不是真的。

导出与预览**不会**逐字节相等：预览是代理档、导出是满幅，形变场与画笔掩膜的坐标尺度
本来就不同（M2-b 定的正是"放大 2× 位移也精确 2×"这条缩放协变）。这里承诺的是
**同一幅尺寸上，分块 == 整幅**，以及**满幅跑的是同一条链、同一批算子**。
"""
from __future__ import annotations

from . import white_balance_recipe as WB

import math
import os
import time
from dataclasses import dataclass, field

import numpy as np

from .optional_dependencies import optional_module

torch = optional_module("torch")

from .ops import enhance as ENH
from . import under_eye_layer as UNDER
from . import lip_makeup_runtime as LIPR, lip_makeup_state as LIPS
from . import brow_shape_runtime as BROWR, brow_shape_state as BROWS, nose_shape_runtime as NOSER, nose_shape_state as NOSES, eye_shape_state as EYES, eye_shape_runtime as EYER, mouth_shape_state as MOUTHS, mouth_shape_runtime as MOUTHR
from .mouth_shape_field import compose_delta as compose_geometry_delta
from . import facial_wrinkle_runtime as WRUNTIME, facial_wrinkle_state as WSTATE
from .ops.deform import (analytic_frontal_landmarks, controls, face_frame,
                         support_radii, tps_field_from_state, tps_solve)
from .ops.grade import GradeError, check_params
from .ops import curves as CURVES
from .ops import levels as LEVELS
from .ops.hsl import check_hsl
from .repair_record import validate_repair_ops
from .repair_replay import replay_repair_t
from .ops.lut import DEFAULT_LUT_AMOUNT, LutError, check_amount
from .ops.upscale import Plan as UpscalePlan
from .ops.upscale import check_scale, unsharp_bands_np, unsharp_float_bands_np
from .quant import quantize16_np
from .vram import LightOp, PreviewPipeline, RepairOp, GRADE_SCOPES

DEFAULT_TILE = 1024
MIN_TILE = 256
MAX_TILE = 4096
# margin 是每个有效 tile 外侧额外读取的支撑宽度；过宽会让每块都处理巨大的重叠区。
# 超过固定上限就拒绝，不截短支撑、不偷偷改用代理场；增大 tile 不会改变这个上限。
MAX_MARGIN = 2048
# 形变场的逐带求值预算（像素数）。拿它除以图宽得到带高，于是带的显存量按这个常数走
# 而不是按图幅走。稠密求值的开销量在 (像素数 × 控制点数) 的 float64 U 矩阵上，所以
# 这一笔比看上去的大：1<<15 在 100 个控制点上是 ≈26 MiB（实测），而 1<<18 要 234 MiB，
# 会把整幅求值变成峰值的主人（那正是小块 tile 分块的意义被顶掉）。
_FIELD_BAND_PX = 1 << 15

FORMATS = ("jpg", "jpeg", "png", "tif", "tiff", "webp")

# 质量表的本厂口径版本号（FORMAT-001）。它存在的唯一理由是把"这个 1~100 是谁的量表"
# 写进产物：以后若改了映射（比如给 PNG 接上真实等级曲线），递增这一串，旧的导出清单
# 还能被读回去。不拿它暗示与任何外部量表（竞品 0~14、ffmpeg -qscale）等价。
QUALITY_MAPPING_VERSION = "lrt.quality.v1"

# 扩展名 → Pillow 的 format 名。编码到内存再提交时必须显式给（以前靠扩展名推断，
# 现在 img.save 的目标是一个 BytesIO，不推就不能定格式）。
_PIL_FORMAT = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP",
               "tif": "TIFF", "tiff": "TIFF"}
# 出片锐化的硬边界（M7）。为什么是模块常量而不是写在 check() 里：命令层要在**开跑前**
# 就拿同一对数拒掉非法请求（被拒的导出还发 export_progress，UI 的进度条会走完后发现
# 什么都没有），而两处各写一份数字就是下一轮改边界时漏改的那一处。
SHARPEN_AMOUNT_LIMIT = 2.0
SHARPEN_RADIUS_RANGE = (1, 24)
SHARPEN_THRESHOLD_LIMIT = 0.2
# 出片现在只接了确定性放大。realesrgan 的算子/权重门禁/分块前向都在包里（M7-a），但
# 出片环路还没调用它：那一台机器上设好 sha256 也仍然是整条拒。**拒绝的理由只写这一句**，
# 命令层与 ExportSpec 共用（写两处就会漂，上一轮 sharpen 那一课同一个形）。
# 文案也不把责任只推给权重：“请设 LRT_REALESRGAN_SHA256 后重试”会让人以为设完就能用。
UPSCALE_BACKENDS_WIRED = ("lanczos3",)
UPSCALE_NOT_WIRED = (
    "出片环路目前只接了确定性放大（lanczos3，分块逐字节等价已在 M7 钉住）；"
    "realesrgan 的权重门禁与分块前向已就绪，但还没接进导出环路——即使权重已按 sha256 放行也仍会拒。"
    "要神经网络超分请先等它接入；本引擎不会替你默默换成 Lanczos 然后报“AI 超分完成”。")


class ExportError(ValueError):
    """导出请求非法。整条拒绝，不产生半截文件。"""


@dataclass
class ExportSpec:
    """一次导出要用的全部图层参数。图层对象与预览会话里的同源，但**坐标是导出尺寸的**。

    为什么要单独一个结构而不是把 `PreviewPipeline` 搬过来：导出是在另一套尺寸上重跑，
    会话的常驻缓存、掩膜、单位场对满幅都没有意义。这里只带"输入"，与决策 11（非破坏、
    重放）同一条路。
    """

    strength: float = 0.5
    radius: int = 12
    eps: float = 6e-4
    detail_gain: float = 1.0
    mid_gain: float = 0.0
    broad_gain: float = 0.0
    texture_radius: int = 4
    channel: str | None = None
    masks: np.ndarray | None = None          # (K,H,W) float32，导出尺寸；channel 用
    mask_names: list = field(default_factory=list)
    landmarks: np.ndarray | None = None      # (478,3)，导出尺寸
    repair: list = field(default_factory=list)     # [RepairOp]，weight 是导出尺寸 (H,W)
    light: list = field(default_factory=list)      # [LightOp]
    light_exposure: float = 0.6
    light_radius: int = 24
    deform_amounts: dict = field(default_factory=dict)
    cube: object = None
    lut_amount: float = DEFAULT_LUT_AMOUNT
    grade: tuple = (0.0, 0.0, 0.0, 1.0)      # (dh, ds, dv, amount)
    # COLOR-004 局部调色：作用域与它的那一片区域（导出尺寸、(H,W) uint8 覆盖度）。
    # 为什么需要把区域也带到导出：只在屏上局部而出片全图，导出就不是“所见”了——
    # 而“屏上只动了皮肤、文件里全图都动了”是比“没做局部调色”难查得多的一件事。
    grade_scope: str = "all"
    grade_mask: np.ndarray | None = None
    local_masks: dict | None = None
    local_mask_semantics: dict = field(default_factory=dict)
    local_mask_source_path: str | None = None  # ephemeral verified source, never a persisted raster
    creative_mask_context: dict | None = None  # ephemeral effective-source/category proof
    creative_smoothing_context: dict | None = None  # frozen source-owned smoothing scope
    creative_fabric_context: dict | None = None  # frozen measured clothes/scale evidence
    creative_recovery_context: dict | None = None  # effective-source global vector ownership
    local_grade_groups: dict | None = None    # retained ordered groups, not merged masks
    local_grade_fields: list | None = None    # disposable full-source uint8 rasters
    local_grade_source_stamp: list | None = None  # decode-to-render source race guard
    effect_recovery: dict | None = None      # retained source-bound brush vectors
    effect_recovery_path: str | None = None  # ephemeral verified original source
    effect_recovery_stamp: list | None = None  # full-decode identity, never rebased
    effect_recovery_fields: list | None = None  # disposable full-source uint8 masks
    creative_sky_context: dict | None = None
    sky_replacement: dict | None = None
    sky_replacement_path: str | None = None
    sky_replacement_stamp: list | None = None
    sky_replacement_prepared: dict | None = None
    optics: dict | None = None
    optics_path: str | None = None
    optics_stamp: list | None = None
    id_background: dict | None = None
    id_background_bundle: dict | None = None
    id_background_path: str | None = None
    id_background_stamp: list | None = None
    id_background_prepared: dict | None = None
    creative_studio_context: dict | None = None
    studio_background: dict | None = None
    studio_background_path: str | None = None
    studio_background_stamp: list | None = None
    studio_background_prepared: dict | None = None
    manual_liquify: dict | None = None       # retained source-bound ordered gestures
    manual_liquify_path: str | None = None   # verified original, never a proxy
    manual_liquify_stamp: list | None = None # decode-to-render identity guard
    manual_liquify_field: np.ndarray | None = None  # disposable original-size dx/dy/protection
    # M6/P1-2 换底：与预览同一份 matte 与背景色（导出尺寸、(H,W) uint8 覆盖度、
    # bg_ref 是 [0,1] 三分量）。换底只活在预览而不进导出就是“屏幕换了、盘上没换”——
    # 前景仍在原位、只是背后的色没变，是最难从缩略图看出来的一类不一致。
    bg_matte: np.ndarray | None = None
    bg_ref: tuple | None = None
    # PORTRAIT-009：眼牙局部增强的三个子功能值。这里**只带参数**，不带掩膜场：
    # 场是关键点的派生物，导出前按导出尺寸重画一份（与形变重解场同一条路）。
    # 不拿预览档那张小掩膜放大——放大一份"身份"掩膜等于把眼睛涂到眉毛上，而且
    # 内容门的相对统计会跟着插值得到的假边一起漂。
    enhance: dict = field(default_factory=dict)
    people: dict | None = None
    body_pose: dict | None = None
    body_pose_source_path: str | None = None
    body_pose_source_stamp: list | None = None
    body_pose_source_proof: dict | None = None
    brow_shape: dict | None = None
    brow_shape_face: object | None = None
    nose_shape: dict | None = None
    nose_shape_face: object | None = None
    eye_shape: dict | None = None
    eye_shape_face: object | None = None
    mouth_shape: dict | None = None
    mouth_shape_face: object | None = None
    lip_makeup: dict | None = None
    lip_makeup_face: dict | None = None
    facial_wrinkle_skin: np.ndarray | None = None
    facial_wrinkle_backend: str | None = None
    facial_wrinkle_model_identity: str | None = None
    fabric_amount: float = 0.0
    fabric_mask: np.ndarray | None = None
    fabric_face_px: float | None = None
    # P0 全局曝光/白平衡：(ev, temperature_shift, tint_shift)。导出走的是同一个
    # PreviewPipeline，所以它与预览是同一份算式而不是“第二次实现”——这正是
    # “所见即所出”能当验收口径的原因。reference_k 缺省用层的默认（D65）。
    # (ev, temperature_shift, tint_shift, contrast, highlights, shadows, saturation)
    exposure: tuple = (0.0,) * 7
    exposure_ref_k: float | None = None
    wb_options: dict | None = None
    photo_grain: dict | None = None
    photo_detail: dict | None = None
    extended_tone: dict | None = None
    colour_grading: dict | None = None
    selective_colour: dict | None = None
    colour_editor: dict | None = None
    primary_calibration: dict | None = None
    reference_color: dict | None = None
    semantic_colour: dict | None = None
    semantic_colour_binding: dict | None = None
    semantic_colour_source_path: str | None = None
    semantic_colour_source_stamp: tuple | None = None
    float_output: bool = False  # internal full-precision analysis, never an encoded file
    provenance_output: bool = False
    provenance_result: np.ndarray | None = None
    # 八色 HSL：24 个数 = 8 段 × (色相/饱和度/明亮度)。与预览同一条链序
    # （曝光之后、LUT 之前），所以导出与屏上是同一份式子。
    hsl: tuple = (0.0,) * 24
    curves: dict | None = None
    levels: dict | None = None
    # 放大（M7）：输出倍率与出片锐化。为什么不在预览会话里做而在导出做：预览的
    # 幅面是代理档（屏幕就这么大），用户要的 2×/4× 只在出片那一刻存在。
    scale: int = 1
    upscale_backend: str = "lanczos3"
    sharpen_amount: float = 0.0
    sharpen_radius: int = 2
    sharpen_threshold: float = 0.01
    # Append fields to preserve existing positional library callers.
    # Canonical immutable RGBA record; original source path remains untouched.
    creative_base: dict | None = None

    def check_effect_recovery(self) -> None:
        """Validate retained intent and optional full-source fields before work."""
        from .effect_recovery_state import check
        from .effect_recovery_stage import check_fields
        try:
            self.effect_recovery = check(self.effect_recovery)
            path, stamp = self.effect_recovery_path, self.effect_recovery_stamp
            if path is not None and (type(path) is not str or not path or '\x00' in path):
                raise ValueError('效果恢复源图路径无效')
            if stamp is not None and (type(stamp) is not list or len(stamp) != 5
                    or any(type(n) is not int for n in stamp)):
                raise ValueError('效果恢复源图解码凭据无效')
            if self.effect_recovery['targets'] and (path is None or stamp is None):
                raise ValueError('效果恢复导出缺少经过验证的源图路径或解码凭据')
            if self.effect_recovery_fields is not None:
                source = self.effect_recovery['source']
                shape = (source['height'], source['width']) if source is not None else None
                check_fields(self.effect_recovery_fields, shape, state=self.effect_recovery)
        except ValueError as error:
            raise ExportError(f'效果恢复导出配方无效：{error}') from error

    def check_manual_liquify(self) -> None:
        """Validate even freeze-only/zero-displacement intent, never drop it."""
        from .manual_liquify_state import check
        from .manual_liquify_stage import check_field
        try:
            self.manual_liquify = check(self.manual_liquify)
            path, stamp = self.manual_liquify_path, self.manual_liquify_stamp
            if path is not None and (type(path) is not str or not path or '\x00' in path):
                raise ValueError('手动液化源图路径无效')
            if stamp is not None and (type(stamp) is not list or len(stamp) != 5
                    or any(type(n) is not int for n in stamp)):
                raise ValueError('手动液化源图解码凭据无效')
            if self.manual_liquify['strokes'] and (path is None or stamp is None):
                raise ValueError('手动液化导出缺少经过验证的源图路径或解码凭据')
            if self.manual_liquify_field is not None:
                source = self.manual_liquify['source']
                if source is None:
                    raise ValueError('无笔迹的液化配方不能携带不明来源的位移场')
                check_field(self.manual_liquify_field, (source['height'], source['width']))
        except ValueError as error:
            raise ExportError(f'手动液化导出配方无效：{error}') from error

    def check_sky_replacement(self) -> None:
        from .sky_replacement_export import check_spec
        check_spec(self)

    def check_optics(self) -> None:
        from .optics_export import check_spec
        check_spec(self)

    def check_id_background(self) -> None:
        from .id_background_export import check_spec
        check_spec(self)

    def check_studio_background(self) -> None:
        from .studio_background_export import check_spec
        check_spec(self)

    def check(self) -> None:
        """参数在进入昂贵通路之前先过一遍唯一校验口径（与各层 setter 同源）。"""
        from .creative_document_base import check as check_creative_base
        check_creative_base(self.creative_base)
        from .extended_tone_state import check as check_tone
        self.extended_tone=check_tone(self.extended_tone)
        from .photo_detail_state import check as check_detail
        self.photo_detail=check_detail(self.photo_detail)
        from .photo_grain_state import check as check_grain, neutral as neutral_grain
        self.photo_grain=neutral_grain() if self.photo_grain is None else check_grain(self.photo_grain)
        from .colour_grading_state import check as check_grading, neutral as neutral_grading
        self.colour_grading=neutral_grading() if self.colour_grading is None else check_grading(self.colour_grading)
        from .primary_calibration_native import admit as admit_primary
        from .primary_calibration_state import neutral as neutral_primary
        self.primary_calibration=admit_primary(neutral_primary() if self.primary_calibration is None else self.primary_calibration)
        from .selective_colour_state import check as check_selective, neutral as neutral_selective
        self.selective_colour=neutral_selective() if self.selective_colour is None else check_selective(self.selective_colour)
        from .colour_editor_state import check as check_editor, neutral as neutral_editor
        self.colour_editor=neutral_editor() if self.colour_editor is None else check_editor(self.colour_editor)
        self.check_effect_recovery()
        self.check_manual_liquify()
        self.check_studio_background()
        self.check_id_background()
        self.check_optics()
        self.check_sky_replacement()
        self.lip_makeup = LIPS.check(self.lip_makeup)
        self.brow_shape = BROWS.check(self.brow_shape)
        self.nose_shape = NOSES.check(self.nose_shape)
        self.eye_shape = EYES.check(self.eye_shape)
        self.mouth_shape = MOUTHS.check(self.mouth_shape)
        from .local_grade_layers import check as check_groups
        from .local_grade_stage import check_fields
        self.local_grade_groups = check_groups(self.local_grade_groups)
        if self.local_grade_groups['layers'] and not self.local_mask_source_path:
            raise ExportError('Independent local-grade export requires its bound original source path')
        if self.local_grade_fields is not None:
            check_fields(self.local_grade_fields, groups=self.local_grade_groups)
        try:
            validate_repair_ops(self.repair)
        except ValueError as error:
            raise ExportError(f"Invalid repair export: {error}") from error
        try:
            state = WB.normalize_state({"_exposure": self.exposure,
                "_exposure_ref_k": self.exposure_ref_k,
                "_wb_options": WB.default_options() if self.wb_options is None else self.wb_options})
            self.wb_options = state["_wb_options"]
            WB.prepare_state(state)
        except (ValueError, RuntimeError, OSError) as error:
            raise ExportError(f"White balance export rejected: {error}") from error
        from .fabric_stage import check_amount
        self.fabric_amount = check_amount(self.fabric_amount)
        if self.fabric_amount and self.fabric_mask is None: raise ExportError("衣物细褶缺少衣物语义蒙版")
        self.curves = CURVES.check_curves(self.curves)
        self.levels = LEVELS.check_levels(self.levels)
        s = float(self.strength)
        if not math.isfinite(s) or not 0.0 <= s <= 1.0:
            raise ExportError(f"strength={self.strength!r} 越界（需要 [0,1] 的有限数）")
        if int(self.radius) < 0 or int(self.texture_radius) < 0 or float(self.eps) <= 0.0:
            raise ExportError(f"磨皮参数非法：radius={self.radius} texture_radius={self.texture_radius} "
                              f"eps={self.eps}（半径需 ≥0、eps 需 >0）")
        for name in ("detail_gain", "mid_gain", "broad_gain"):
            v = float(getattr(self, name))
            if not math.isfinite(v):
                raise ExportError(f"{name}={v!r} 不是有限数")
        try:
            check_params(self.grade[0], self.grade[1], self.grade[2], amount=self.grade[3])
        except GradeError as e:
            raise ExportError(f"肤色定向参数非法：{e}") from None
        # 旧调用方可能只带 EV/WB：先把 HSL 补长到 24 再整组校（越界/NaN 落盘前拒）。
        try:
            self.hsl = check_hsl((tuple(float(v) for v in (self.hsl or ()))
                                  + (0.0,) * 24)[:24])
        except ValueError as e:
            raise ExportError(f"八色 HSL 参数非法：{e}") from None
        # PORTRAIT-009：参数先过唯一的校验口径；点火而没带关键点就是没有来源。
        # 不许退化成"那就不增强"：用户按了牙齿美白而出片里没有，事件必须说清楚为什么。
        if self.enhance:
            try:
                self.enhance = ENH.check_amounts(self.enhance)
            except ENH.EnhanceError as e:
                raise ExportError(f"眼牙增强参数非法：{e}") from None
        if (WSTATE.active_enhance(self.enhance or {})
                and self.landmarks is None):
            raise ExportError("眼牙增强导出需要关键点：这一层的掩膜是从 478 点重画出来的，"
                              "没有关键点就没有这一层（不拿上一张脸的场来凑，也不拿默认矩形猜）")
        if self.grade_scope not in GRADE_SCOPES:
            raise ExportError(f"未知调色作用域：{self.grade_scope!r}（可用 {', '.join(GRADE_SCOPES)}）")
        # 局部作用域 + 点火的定向 = 必须带区域。拿不到区域就把整层放下（命令层干的），
        # 而不是“那就全图调一下算了”：静默加宽作用域在磁盘上看不出来，而 export_done
        # 会报一个与实际像素不符的 scope（与 birefnet/lama 不许静默降级同一条规矩）。
        if (self.grade_scope != "all" and any(float(v) != 0.0 for v in self.grade[:3])
                and float(self.grade[3]) != 0.0):
            if self.grade_scope == "objects" and self.local_masks is not None and self.grade_mask is None:
                from .local_mask_state import check
                check(self.local_masks)
                gm = None  # Source-colour predicates resolve only after full decode.
            elif self.grade_mask is None:
                raise ExportError(f"局部调色（scope={self.grade_scope!r}）导出需要那一片区域，"
                                  "而本份没带上：宁可整层不带调色，也不会把它当成全图调色写出去")
            gm = None if self.grade_mask is None else np.asarray(self.grade_mask)
            if gm is not None and gm.ndim != 2:
                raise ExportError(f"调色区域必须是 (H,W)，得到 {gm.shape}")
            if gm is not None and self.grade_scope != "objects" and int((gm > 0).sum()) == 0:
                raise ExportError("调色区域一个像素也没盖到：这一层在导出里不会有任何作用，"
                                  "请清掉局部作用域或重新画一笔")
        if self.cube is not None:
            try:
                check_amount(self.lut_amount)
            except LutError as e:
                raise ExportError(f"调色强度非法：{e}") from None
        if self.channel is not None:
            if self.masks is None or not self.mask_names:
                raise ExportError(f"分通道导出需要掩膜：channel={self.channel!r} 但没有 masks/mask_names")
            if self.channel not in self.mask_names:
                raise ExportError(f"没有这个通道：{self.channel!r}（可用 {self.mask_names}）")
        # 放大（M7）：倍率、后端、锐化都先在这里过——导出会落盘，一条越界参数
        # 不该先花几秒分块再报错。
        try:
            self.scale = check_scale(self.scale)
        except ValueError as e:
            raise ExportError(f"放大倍率非法：{e}") from None
        if self.upscale_backend not in ("lanczos3", "realesrgan"):
            raise ExportError(f"未知放大后端：{self.upscale_backend!r}（可用 lanczos3/realesrgan）")
        if self.upscale_backend == "realesrgan":
            # 这里不接受也不降级：静默改用 Lanczos 然后报"AI 超分完成"是这一仓最不能
            # 犯的那类错（与 lama/birefnet 同规）。拒的理由与命令层同一句（单一出处）。
            raise ExportError(UPSCALE_NOT_WIRED)
        sa = float(self.sharpen_amount)
        if not math.isfinite(sa) or not 0.0 <= sa <= SHARPEN_AMOUNT_LIMIT:
            raise ExportError(f"sharpen_amount={self.sharpen_amount!r} 越界（需要 [0,{SHARPEN_AMOUNT_LIMIT}] 内的有限数）")
        if not (SHARPEN_RADIUS_RANGE[0] <= int(self.sharpen_radius) <= SHARPEN_RADIUS_RANGE[1]):
            raise ExportError(f"sharpen_radius={self.sharpen_radius} 越界（需要 "
                              f"{SHARPEN_RADIUS_RANGE[0]}~{SHARPEN_RADIUS_RANGE[1]}）")
        st = float(self.sharpen_threshold)
        if not math.isfinite(st) or not 0.0 <= st <= SHARPEN_THRESHOLD_LIMIT:
            raise ExportError(f"sharpen_threshold={self.sharpen_threshold!r} 越界（需要 [0,{SHARPEN_THRESHOLD_LIMIT}]）")
        # P1-2 换底：matte 与 ref 要么都不带，要么都带齐；半截状态在合成里会拿
        # 未定义行为写出一片“看着像换了、其实背景色取的是老值”，比整层不带更难归因。
        if self.bg_matte is not None:
            if self.bg_ref is None:
                raise ExportError("换底导出带 matte 却没带 bg_ref：宁可整层不带换底，也不拿未定义背景色写出去")
            bm = np.asarray(self.bg_matte)
            if bm.ndim != 2:
                raise ExportError(f"换底遮罩必须是 (H,W)，得到 {bm.shape}")
            if bm.shape[0] <= 0 or bm.shape[1] <= 0:
                raise ExportError(f"换底遮罩形状非法：{bm.shape}")
            ref = tuple(self.bg_ref)
            if len(ref) != 3:
                raise ExportError(f"bg_ref 必须是三分量，得到 {ref!r}")
            rf = [float(v) for v in ref]
            if not all(math.isfinite(v) for v in rf):
                raise ExportError(f"bg_ref 含非有限值：{ref!r}")
            if any(not 0.0 <= v <= 1.0 for v in rf):
                raise ExportError(f"bg_ref 分量越界（需要 [0,1]）：{ref!r}")
        elif self.bg_ref is not None:
            raise ExportError("带 bg_ref 却没带 matte：换底没有可套用的遮罩，整层应一起放下")

    # ---- margin：由参数算，不是量出来一个数写死 ----
    def margin_px(self, deform_peak_px: float = 0.0, manual_peak_px: float = 0.0) -> int:
        m = max(2 * int(self.texture_radius) + 6 * int(self.radius),
                2 * int(self.light_radius) if self.light else 0)
        if deform_peak_px:
            m += int(math.ceil(deform_peak_px)) + 1
        # Final manual sampling consumes already-filtered/auto-warped pixels.
        # Its support ADDS to the existing halo, including a second bilinear tap.
        # Freeze-only recipes still get validated/replayed, even when peak == 0.
        manual_active = bool(manual_peak_px or (self.manual_liquify or {}).get("strokes"))
        if manual_active:
            if not math.isfinite(manual_peak_px) or manual_peak_px < 0:
                raise ExportError("手动液化作用面必须是有限非负值")
            m += int(math.ceil(manual_peak_px)) + 1
        if int(self.scale) > 1:
            support = UpscalePlan.margin_for(int(self.scale))
            # Lanczos consumes a neighborhood of the manual output. Each of
            # those pixels needs the entire upstream+manual footprint, so this
            # support also adds. Preserve the established manual-free formula.
            m = m + support if manual_active else max(m, support)
        return m


def tile_rects(h: int, w: int, tile: int) -> list:
    """有效区矩形（不含 margin）。最后一块允许变小，不重复覆盖也不留缝。"""
    t = int(tile)
    if not (MIN_TILE <= t <= MAX_TILE):
        raise ExportError(f"tile={tile} 越界（允许 {MIN_TILE}~{MAX_TILE}）")
    return [(y0, min(y0 + t, h), x0, min(x0 + t, w))
            for y0 in range(0, h, t) for x0 in range(0, w, t)]


def _admit_manual_tile(spec, h, w, tile, margin, bits, device, manual_peak):
    """Conservative allocation admission, not a measured peak/OOM guarantee.

    Check the *halo-expanded* tile, not its nominal side. The existing filters,
    caches, auto warp and editing temporaries are reserved at 320 B/pixel. The
    second warp additionally needs inverse offsets, base/normalized grids, exact
    identity mask, interpolation/where output and RGB16 float64 source/output.
    Reserve 96/192 B/pixel for that stage (RGB8/RGB16), including its temporaries.
    Already-live full-source fields are reflected in the remaining CPU budget.
    """
    # Exact-zero displacement takes the stage's identity fast path; freeze
    # intent and its full protection field were still verified and replayed.
    if not spec.manual_liquify['strokes'] or manual_peak == 0:
        return 0
    from .cpu_memory_budget import available_estimate
    import resource
    pixels = min(h, int(tile)+2*margin) * min(w, int(tile)+2*margin)
    tile_bytes = pixels * (320 + (192 if bits == 16 else 96))
    # Output is float until the final RGB16 quantization. Full repair and fabric
    # products, when requested, are still to be allocated after this admission.
    full_bytes = h*w*(12 if bits == 16 else 3)*int(spec.scale)**2
    full_bytes += h*w*(12 if spec.repair else 0)
    full_bytes += h*w*(4 if spec.fabric_amount else 0)
    from .studio_background_export import resident_bytes as studio_bytes
    full_bytes += studio_bytes(spec)
    from .id_background_runtime import resident_bytes as id_background_bytes
    full_bytes += id_background_bytes(spec)
    headroom = 64*1024*1024
    target = torch.device(device)
    if target.type == 'cuda' and not torch.cuda.is_available():
        target = torch.device('cpu')  # Match PreviewPipeline's explicit fallback.
    # CPU transport/readback and per-tile float conversions remain even on GPU.
    cpu_need = full_bytes + (tile_bytes if target.type == 'cpu' else pixels*32) + headroom
    try:
        remaining = available_estimate()
        soft, _ = resource.getrlimit(resource.RLIMIT_AS)
        if soft != resource.RLIM_INFINITY:
            with open('/proc/self/statm', 'r', encoding='ascii') as info:
                mapped = int(info.read(128).split()[0])*os.sysconf('SC_PAGE_SIZE')
            remaining = min(remaining, max(0, soft-mapped))
        if cpu_need > remaining:
            raise ExportError('手动液化全尺寸分块内存预算不足；请减小导出分块，不会放大代理场代替')
        if target.type == 'cuda':
            free, _ = torch.cuda.mem_get_info(target)
            # Cached unallocated blocks belong to this process and are reusable.
            reusable = max(0, torch.cuda.memory_reserved(target)-torch.cuda.memory_allocated(target))
            if tile_bytes+headroom > int(free)+int(reusable):
                raise ExportError('手动液化分块含完整边界后超过可用显存；请减小分块或手动形变范围')
    except (OSError, ValueError, RuntimeError) as error:
        if isinstance(error, ExportError):
            raise
        raise ExportError(f'无法确认手动液化分块资源预算：{error}') from error
    return tile_bytes


class _MaskCarrier:
    """给 PreviewPipeline.load_face 用的最小载体：导出器没有 precompute 对象，只有数组。

    为什么不直接塞 `masks_gpu`：`load_face` 里那两条"字节必须与原件等量"的校验是这个
    仓库对跨设备张量唯一的抓手，绕开它等于自己重写一遍校验。
    """

    def __init__(self, arr, landmarks):
        self._arr = np.ascontiguousarray(arr, dtype=np.float32)
        self.landmarks = np.empty((0,3),dtype=np.float32) if landmarks is None else np.ascontiguousarray(landmarks, dtype=np.float32)

    def stack(self):
        return self._arr, list(self._carrier_names or [])

    _carrier_names: list = []


def _row_bands(y0: int, y1: int, w0: int, w1: int, budget_px: int = _FIELD_BAND_PX) -> list:
    """在 [y0,y1) × [w0,w1) 里按行切带：每带不超 budget_px 像素（带宽是那段的全部列，至少 1 行）。

    为什么按行而不按 tile：峰值位移要的是**整个作用域的 max**，而 margin 必须在切 tile
    之前就算出来。按行扫一遍能拿精确 max，而显存量只按那一带的面积走。
    """
    width = max(1, w1 - w0)
    rows = max(1, int(budget_px) // width)
    return [(a, min(a + rows, y1), w0, w1) for a in range(y0, y1, rows)]


def composed_delta(landmarks, amounts, h: int, w: int, device: str):
    """按导出尺寸解一次形变场，返回 ((1,h,w,2) float32 的 CPU 副本, 峰值位移 px)。

    为什么不能整幅一次在 GPU 上求值（上一版就是这么写的，实测账单）：稠密求值的开销量
    在 (像素数 × 控制点数) 的 U 矩阵上，5 MP 图上一个 kind 就是 GB 级——跑靶量到
    **峰值与 tile 无关地按图幅涨**（1024×1280 要 1042 MiB，2000×2500 要 3887 MiB，
    而 tile 从 256 换到 4096 一个字节都不变）。那句"峰值只随 tile 走"当场是假的。
    现在按行带求值（tps_solve 按 kind 解一次 + tps_field_from_state 逐带求值）：每带算完
    立刻落回 CPU，显存只跟带面积走。

    为什么几何参数按整幅、而求值按带？因为 TPS 求值里的 `scale=max(h,w)` 是
    **图像尺度**的归一，逐 tile 解会把 λ 换成 tile 尺度，那不是同一个场（M2-b 定的
    "放大 2× 位移也精确 2×"这条缩放协变会被打破）。切带/切 tile 只取 X 的子集，
    scale 仍按整幅算，所以它与整幅求值是同一张场（逐元素相等由 test_deform 钉住）。
    场最细落在 CPU、按 tile 切片上传，所以显存峰值不随整幅场走；代价是场按整幅活在
    系统内存里（2×float32 每像素），那笔在 `delta_cpu_mb` 里报出去，不遮。
    """
    if torch is None:
        raise ExportError("导出需要 torch（装 rocm/cuda/cpu 任一变体）")
    got = {k: float(v) for k, v in (amounts or {}).items() if float(v) != 0.0}
    if not got:
        return None, 0.0
    lm = landmarks if landmarks is not None else analytic_frontal_landmarks()
    cx, cy, R, _fw, _fh = face_frame(lm, h, w)
    r0, r1 = support_radii(R)
    # 解算那一段与图幅、与带数无关，按 kind 解一次就够（跑靶量到不拆时要 0.8 s，
    # 比五个算子段加起来还多：GPU 上一个 27×27 的 solve 启动开销就要几毫秒，乘以带数就是灾难）
    dev = torch.device(device)
    states = []
    for kind, amt in got.items():
        P, D, _meta = controls(lm, kind, 1.0, h, w)
        Pt = torch.as_tensor(np.asarray(P, dtype=np.float64), dtype=torch.float64, device=dev)
        Dt = torch.as_tensor(np.asarray(D, dtype=np.float64), dtype=torch.float64, device=dev)
        states.append((tps_solve(Pt, Dt, scale=float(max(h, w))), amt))
    acc = torch.zeros(1, h, w, 2, dtype=torch.float32)      # 在 CPU：这笔是 RAM，不是 VRAM
    peak = 0.0
    # 只在紧支撑窗的 bbox 内求值：窗外窗函数恰好为 0，所以 max 与那片零区都算对了。
    # 本仓的 fixture 把脸填满了画框，这条在跑靶里看不出省了多少；真照片留白多，
    # 省的就是 (bbox 面积 / 图幅) 那个比例。
    by0 = max(0, int(math.floor(cy - r1)))
    by1 = min(h, int(math.ceil(cy + r1)) + 1)
    bx0 = max(0, int(math.floor(cx - r1)))
    bx1 = min(w, int(math.ceil(cx + r1)) + 1)
    for y0, y1, x0, x1 in _row_bands(by0, by1, bx0, bx1):
        band = torch.zeros(1, y1 - y0, x1 - x0, 2, device=dev, dtype=torch.float32)
        for st, amt in states:
            band += tps_field_from_state(st, h, w, cx=cx, cy=cy, R=r1, r0=r0,
                                         device=dev, box=(y0, y1, x0, x1)) * amt
        # 峰值取**合成后**那一张的实际位移，不取各层峰相加：前者是 margin 真正要盖住的
        # 东西，后者只是一个上界（它会偏大，而偏大的 margin 是要拿面积去付钱的）
        peak = max(peak, float(band.abs().amax()))
        acc[:, y0:y1, x0:x1] = band.cpu()
        del band
    if torch.cuda.is_available() and str(device).startswith("cuda"):
        torch.cuda.empty_cache()
    return acc, peak


def apply_repair_full(src_u8: np.ndarray, ops: list, device: str, *, spec=None):
    """消除笔在**满幅**上按洞的 bbox 逐笔跑一次，返回 (H,W,3) float32 底图。

    为什么不在 tile 里跑：inpaint 是多尺度求解（`levels_for(hole_extent, box_h, box_w)`
    按洞的 bbox 定层数），tile 一切就把洞切碎，层数与 bbox 都变了——那不是一个能用
    margin 修好的边界效应。而它天生只需要洞周围那一圈，本来就不贵。
    与 `PreviewPipeline._commit_repair` 同一条重放顺序与同一批算子（逐笔而不是并集：
    并集会让第二笔的周围含上第一笔的旧坑）。
    """
    h, w = src_u8.shape[:2]
    try:
        validate_repair_ops(ops, shape=(h, w))
    except ValueError as error:
        raise ExportError(f"Invalid repair export: {error}") from error
    arr = np.ascontiguousarray(src_u8.transpose(2, 0, 1))[None]
    derived = src_u8.dtype == np.float32
    if derived:
        from .creative_derived_repair_export import verify_pixels
        if spec is None or ops is not spec.repair:
            raise ExportError("Float repair requires the export-owned source and operation stack")
        verify_pixels(spec,src_u8)
        divisor = 1.0
    else:
        if src_u8.dtype not in (np.uint8, np.uint16):
            raise ExportError("消除笔源图需要 uint8 或 uint16，或已验证的合成 float32 来源")
        if any(getattr(op,'source_binding',None) is not None for op in ops):
            raise ExportError("Derived repair records cannot replay on physical-original integer pixels")
        divisor = 65535.0 if src_u8.dtype == np.uint16 else 255.0
    cur = torch.from_numpy(arr).to(device).to(torch.float32).div_(divisor)
    t0 = time.perf_counter()
    cur, boxes, _ = replay_repair_t(cur, ops)
    ms = (time.perf_counter() - t0) * 1000.0
    out = cur[0].permute(1, 2, 0).cpu().numpy().astype(np.float32)
    del cur
    if torch.cuda.is_available() and str(device).startswith("cuda"):
        torch.cuda.empty_cache()
    if not np.isfinite(out).all():
        raise ExportError("消除笔满幅结果含非有限值，已拒绝进入导出")
    if derived:
        from .creative_derived_repair_export import stamp_replayed
        stamp_replayed(spec,src_u8,out)
    return out, {"repair_ms": round(ms, 2), "applied": len(boxes)}


def _crop_ops(ops, box, cls):
    cy0, cx0, cy1, cx1 = box
    out = []
    for op in ops:
        w = op.weight[cy0:cy1, cx0:cx1]
        if not w.any():
            continue
        out.append(cls(op_id=op.op_id, weight=np.ascontiguousarray(w), **_rest(op, cls)))
    return out


def _rest(op, cls):
    if cls is LightOp:
        return {"sign": op.sign}
    return {"params": dict(op.params)}


def export_image(src_u8: np.ndarray, spec: ExportSpec, *, device: str = "cuda",
                 tile: int = DEFAULT_TILE, progress=None, geometry=None) -> tuple:
    """Existing RGB8 entry point; do not silently promote source precision."""
    return _run_export(src_u8, spec, device=device, tile=tile,
                       progress=progress, bits=8, geometry=geometry)


def export_float(src, spec, *, geometry, progress=None, provenance=True):
    """Internal actual fully edited original-resolution RGB and provenance tap."""
    spec.float_output=True;spec.provenance_output=bool(provenance)
    return _run_export(src,spec,device='cpu',tile=DEFAULT_TILE,progress=progress,
                       bits=16 if src.dtype==np.uint16 else 8,geometry=geometry)


def export_image16(src_u16: np.ndarray, spec: ExportSpec, *, device: str = "cuda",
                   tile: int = DEFAULT_TILE, progress=None,
                   crop_rect=(0.0, 0.0, 1.0, 1.0), rotation_degrees: float = 0.0) -> tuple:
    """Working-sRGB RGB16 through the same editing chain, float until final RGB16.

    This is the editing-library entry point used by the application's end-to-end
    RAW/TIFF decode, recipe, crop and color-managed file-export integration.
    """
    return _run_export(src_u16, spec, device=device, tile=tile,
                       progress=progress, bits=16, geometry=(crop_rect, rotation_degrees))


def _run_export(source, spec, *, device, tile, progress, bits, geometry):
    """Resolve a creative source once, outside recursive full-frame prepasses.

    Source precision and file precision are independent. Creative pixels remain
    float through all edit/delivery passes; RGB8/RGB16 quantization happens once
    here only after an explicit alpha/HDR admissibility check. Internal float
    captures preserve extended results instead of quantizing them for display.
    """
    if spec.creative_base is None:
        return _export_image_impl(source, spec, device=device, tile=tile,
            progress=progress, bits=bits, geometry=geometry)
    from copy import copy
    from .creative_document_base import export_source, require_rebound_spec
    require_rebound_spec(spec)
    original = spec
    resolved = copy(spec)
    resolved._creative_source_resolved = True
    resolved.float_output = True
    # A creative composite cannot masquerade as unchanged original-scene
    # evidence for reference matching. Capture callers need pixels, not a
    # fabricated original-photo support map.
    resolved.provenance_output = False
    def cancelled():
        if progress:
            progress(0, 1, 0.)
        return False
    from .cpu_memory_budget import available_estimate
    work_bytes = min(4_000_000_000, max(1, int(available_estimate()) // 2))
    source = export_source(spec.creative_base, cancelled=cancelled, max_bytes=work_bytes)
    if resolved.repair:
        from .creative_derived_repair_export import stamp_pixels
        stamp_pixels(resolved,source)
    if resolved.creative_sky_context is not None:
        from .creative_derived_sky import stamp_pixels
        stamp_pixels(resolved,source)
    if resolved.creative_studio_context is not None:
        from .creative_derived_studio import stamp_pixels
        stamp_pixels(resolved,source)
    if resolved.creative_smoothing_context is not None:
        from .creative_derived_smoothing import stamp_pixels
        stamp_pixels(resolved,source)
    if resolved.creative_fabric_context is not None:
        from .creative_derived_fabric import stamp_pixels
        stamp_pixels(resolved,source)
    if resolved.creative_recovery_context is not None:
        from .creative_derived_global_recovery import stamp_pixels
        stamp_pixels(resolved,source)
    if resolved.creative_mask_context is not None:
        from .creative_derived_masks import stamp_pixels
        stamp_pixels(resolved,source)
    if resolved.body_pose is not None:
        from .creative_derived_body_export import stamp_pixels
        stamp_pixels(resolved,source)
    frame, facts = _export_image_impl(source, resolved, device=device, tile=tile,
        progress=progress, bits=bits, geometry=geometry)
    if hasattr(resolved, '_colour_editor_capture_coverage'):
        # The input picker consumes coverage through its caller-owned spec.
        # Source resolution uses a private shallow copy, not a different owner.
        original._colour_editor_capture_coverage = resolved._colour_editor_capture_coverage
    original.provenance_result = (np.zeros(frame.shape[:2], dtype=bool)
        if original.provenance_output else None)
    if not original.float_output:
        if not np.isfinite(frame).all() or np.any(frame < 0) or np.any(frame > 1):
            raise ExportError('Creative output has signed/HDR values that this RGB8/RGB16 encoder cannot preserve; no implicit clipping or tone mapping')
        frame = quantize16_np(frame) if bits == 16 else np.rint(frame * 255.).astype(np.uint8)
    facts = {**facts, 'creative_base': spec.creative_base['id'],
        'creative_source_bits': 32, 'creative_source_encoding': 'linear-srgb-d65',
        'creative_alpha_policy': 'opaque-only; no export matte',
        'creative_hdr_policy': 'float retained; integer output rejects out-of-range',
        'original_scene_evidence': False}
    return frame, facts


def _export_image_impl(src_u8: np.ndarray, spec: ExportSpec, *, device: str,
                       tile: int, progress, bits: int, geometry=None) -> tuple:
    t_function = time.perf_counter()
    if geometry is not None:
        from .ops.geometry import check as check_geometry
        check_geometry(*geometry)
    creative_source = bool(getattr(spec, '_creative_source_resolved', False))
    if spec.creative_base is not None and not creative_source:
        raise ExportError('Creative source must enter through the single public export resolver')
    dtype = np.float32 if creative_source else np.uint16 if bits == 16 else np.uint8
    divisor = 1.0 if creative_source else 65535.0 if bits == 16 else 255.0
    if src_u8.ndim != 3 or src_u8.shape[2] != 3 or src_u8.dtype != dtype:
        raise ExportError(f"导出要 (H,W,3) {np.dtype(dtype).name}，得到 {src_u8.shape} {src_u8.dtype}")
    from .photo_grain_state import check as check_grain, neutral as neutral_grain, active as grain_active
    grain_recipe=neutral_grain() if spec.photo_grain is None else check_grain(spec.photo_grain)
    from .colour_editor_state import from_state as editor_from_state, active as editor_active
    editor_recipe=editor_from_state({'_colour_editor':spec.colour_editor}) if spec.colour_editor is not None else editor_from_state({})
    editor_mode=getattr(spec,'_colour_editor_mode','render')
    if editor_mode not in ('render','input','view'): raise ExportError('Invalid editor render mode')
    editor_needed=editor_active(editor_recipe) or editor_mode!='render'
    if (grain_active(grain_recipe) or editor_needed) and not getattr(spec,'_extended_tone_prepass',False):
        from .photo_grain_runtime import admit
        admit(src_u8.shape[1],src_u8.shape[0],int(spec.scale))
        # Grain is a source-resolution effect. Delivery resize/sharpen follow the
        # entire source edit chain; geometry/colour/detail order stays unchanged.
        if int(spec.scale)!=1 or float(spec.sharpen_amount)!=0:
            from .photo_grain_export import render_delivery
            return render_delivery(src_u8,spec,renderer=_export_image_impl,device=device,tile=tile,progress=progress,bits=bits,geometry=geometry)
    from .extended_tone_state import check as check_tone, active as tone_active
    from .extended_tone_stage import ExtendedToneStage
    from .extended_tone_native import admit as admit_tone
    from .photo_detail_state import check as check_detail, active as detail_active
    from .photo_detail_stage import PhotoDetailStage
    from .photo_detail_native import admit as admit_detail
    detail_recipe=check_detail(spec.photo_detail)
    if detail_active(detail_recipe):admit_detail(src_u8.shape[0]*src_u8.shape[1]*int(spec.scale)**2)
    tone_recipe=check_tone(spec.extended_tone)
    tone_prepass=bool(getattr(spec,'_extended_tone_prepass',False))
    tone_field=None
    tone_poll_at=[0.]
    def tone_cancelled():
        now=time.perf_counter()
        if progress and now-tone_poll_at[0]>=0.05:
            tone_poll_at[0]=now
            progress(0,1,(now-t_function)*1000.)
        return False
    from .extended_tone_state import effective as tone_controls
    if any(tone_controls(tone_recipe)) and not tone_prepass:
        # Full-frame exposure boundary, not per-tile atmospheric estimates. The
        # second pass resumes downstream on this exact field with existing halo.
        from copy import copy
        admit_tone(src_u8.shape[0]*src_u8.shape[1])
        upstream=copy(spec)
        upstream._extended_tone_prepass=True
        upstream.scale=1;upstream.sharpen_amount=0.;upstream.float_output=True;upstream.provenance_output=False
        tone_input,_=_export_image_impl(src_u8,upstream,device=device,tile=tile,progress=progress,bits=bits,geometry=None)
        tone_field=ExtendedToneStage(tone_recipe,scale=1.,cancelled=tone_cancelled).apply_np(tone_input)
        del tone_input,upstream
    from .local_mask_state import export_prepare, file_stamp
    from .local_grade_runtime import export_prepare as prepare_local_grades
    from .local_grade_layers import check as check_groups
    from .local_grade_stage import check_fields
    from .effect_recovery_runtime import export_prepare as prepare_effect_recovery, attach_tile
    from .manual_liquify_runtime import export_prepare as prepare_manual_liquify, attach_tile as attach_manual_tile
    spec.check_effect_recovery()
    spec.check_manual_liquify()
    spec.check_optics()
    spec.check_sky_replacement()
    from .optics_state import active as optics_enabled
    optical = optics_enabled(spec.optics) and not tone_prepass
    from .reference_color_stage import ReferenceColorStage
    reference_stage=ReferenceColorStage(spec.reference_color)
    from .colour_grading_adapters import export_stage as grading_stage
    colour_grading_stage=grading_stage(spec)
    from .selective_colour_adapters import export_stage as selective_stage
    selective_colour_stage=selective_stage(spec)
    from .primary_calibration_adapters import export_stage as primary_stage
    primary_calibration_stage=primary_stage(spec)
    from .semantic_colour_stage import SemanticColourStage
    from .semantic_colour_runtime import verify_render_source as verify_semantic_source
    from .body_pose_render import verify_render_source as verify_body_source
    from .hair_colour_project import verify_render_source as verify_hair_source
    verify_semantic_source(spec)
    verify_body_source(spec)
    verify_hair_source(spec)
    semantic_stage=SemanticColourStage(spec.semantic_colour,binding=spec.semantic_colour_binding)
    floating=creative_source or detail_active(detail_recipe) or bits==16 or optical or reference_stage.active or semantic_stage.active or spec.float_output or tone_active(tone_recipe) or tone_prepass or colour_grading_stage.active or selective_colour_stage.active or primary_calibration_stage.active or grain_active(grain_recipe) or editor_needed
    if spec.provenance_output and (not spec.float_output or spec.scale!=1): raise ExportError("来源支持只用于原尺寸浮点分析")
    optical_budget = 0
    if optical:
        from .optics_export import admit
        optical_budget = admit(src_u8.shape[:2],int(spec.scale),spec.optics)
    manual_source_stamp = None
    if spec.manual_liquify["strokes"]:
        manual_source_stamp = file_stamp(spec.manual_liquify_path)
        if list(manual_source_stamp) != spec.manual_liquify_stamp:
            raise ExportError("手动液化源图自全尺寸解码后变化，停止导出")
    recovery_source_stamp = None
    if spec.effect_recovery['targets']:
        recovery_source_stamp = file_stamp(spec.effect_recovery_path)
        if list(recovery_source_stamp) != spec.effect_recovery_stamp:
            raise ExportError('效果恢复源图自全尺寸解码后变化，停止导出')
    groups = check_groups(spec.local_grade_groups)
    group_source_stamp = None
    if groups['layers']:
        if not spec.local_mask_source_path:
            raise ExportError('Independent local-grade export is missing its original source path')
        group_source_stamp = file_stamp(spec.local_mask_source_path)
        if (spec.local_grade_source_stamp is not None
                and list(group_source_stamp) != spec.local_grade_source_stamp):
            raise ExportError('Independent local-grade source changed since full decode')
    def mask_cancelled():
        # Existing inspection/export owners may raise cancellation in progress.
        # Prompted inference runs in a killable child, never an uninterruptible
        # long Torch call on this render thread.
        if progress: progress(0, 1, (time.perf_counter()-t_function)*1000.)
        return False
    from .studio_background_export import prepare_export as prepare_studio
    from .studio_background_runtime import attach_tile as attach_studio_tile
    prepare_studio(spec, src_u8, cancelled=mask_cancelled)
    from .id_background_runtime import export_prepare as prepare_id_background, attach_tile as attach_id_background, finish_export as finish_id_background
    from .id_background_export import admit_prepare as admit_id_background
    id_background_admission=admit_id_background(spec,src_u8.shape[:2],tile=tile,bits=bits)
    prepare_id_background(spec, src_u8, cancelled=mask_cancelled)
    from .sky_replacement_runtime import export_prepare as prepare_sky, attach_tile as attach_sky_tile, finish_export as finish_sky
    from .sky_replacement_export import admit_tile as admit_sky, resident_bytes as sky_bytes
    prepare_sky(spec,src_u8.shape[:2],cancelled=mask_cancelled,source_pixels=src_u8)
    export_prepare(spec, src_u8, cancelled=mask_cancelled)
    # Rasters are disposable. Drop a previous full render's fields before
    # allocating replacements instead of silently doubling the CPU mask budget.
    spec.local_grade_fields = None
    prepare_local_grades(spec, src_u8, cancelled=mask_cancelled)
    check_fields(spec.local_grade_fields, src_u8.shape[:2], groups=groups)
    spec.effect_recovery_fields = None
    prepare_effect_recovery(spec, src_u8.shape[:2], cancelled=mask_cancelled, source_pixels=src_u8)
    # Replay the vector recipe ONCE at original dimensions. Never enlarge a
    # proxy field or replay independent tiles whose field composition would differ.
    t_manual = time.perf_counter()
    spec.manual_liquify_field = None
    manual_peak = prepare_manual_liquify(spec, src_u8.shape[:2], cancelled=mask_cancelled)
    manual_field_ms = (time.perf_counter() - t_manual) * 1000.0
    if group_source_stamp is not None and file_stamp(spec.local_mask_source_path) != group_source_stamp:
        raise ExportError('Independent local-grade source changed during mask preparation')
    spec.check()
    # 纯校验全部排在 torch 守卫之前：没装 torch 的环境也要拿到同一句参数拒绝，
    # 而不是先被"导出需要 torch"抢掉——那样 CI 的 CPU job 根本测不到这些分支。
    h, w = src_u8.shape[:2]
    rects = tile_rects(h, w, tile)
    initial_margin = spec.margin_px(0.0, manual_peak)
    if initial_margin > MAX_MARGIN:
        # 不需要 torch 就能算出来的那一半：半径把作用面撑爆这件事与有没有 GPU 无关
        raise ExportError(f"这组参数的作用面宽到 margin={initial_margin} px"
                          f"（超过 {MAX_MARGIN}），请调小滤波半径或形变范围；不会截短边界继续出片")
    if torch is None:
        raise ExportError("导出需要 torch（装 rocm/cuda/cpu 任一变体）")
    base_f=None;repair_stats={}
    if spec.repair:base_f,repair_stats=apply_repair_full(src_u8,spec.repair,device,spec=spec)
    from .people_export import prepare as prepare_people
    people_start=time.perf_counter();people_prepared=prepare_people(spec,src_u8,base_f)
    people_prepare_ms=(time.perf_counter()-people_start)*1000.0 if people_prepared is not None else 0.0
    delta, peak = (None, 0.0)
    field_ms = 0.0
    if spec.deform_amounts:
        t_f = time.perf_counter()
        delta, peak = composed_delta(spec.landmarks, spec.deform_amounts, h, w, device)
        field_ms = (time.perf_counter() - t_f) * 1000.0
    brow_field = BROWR.export_field(spec, src_u8, divisor=65535 if src_u8.dtype == np.uint16 else 255)
    nose_field = NOSER.export_field(spec, src_u8, divisor=65535 if src_u8.dtype == np.uint16 else 255)
    eye_field = EYER.export_field(spec, src_u8, divisor=65535 if src_u8.dtype == np.uint16 else 255)
    mouth_field = MOUTHR.export_field(spec, src_u8, divisor=65535 if src_u8.dtype == np.uint16 else 255)
    delta, peak = compose_geometry_delta(delta, brow_field, nose_field, eye_field, mouth_field, (h,w))
    if people_prepared is not None: delta,peak=people_prepared.geometry.delta,people_prepared.geometry.peak
    if isinstance(delta,np.ndarray): delta = torch.from_numpy(delta)
    margin = spec.margin_px(peak, manual_peak)
    if margin > MAX_MARGIN:
        raise ExportError(f"这组参数的作用面宽到 margin={margin} px（超过 {MAX_MARGIN}），"
                          "请调小滤波半径或形变范围；不会截短边界继续出片")
    manual_tile_budget = _admit_manual_tile(spec, h, w, tile, margin, bits, device, manual_peak)
    sky_tile_budget = admit_sky(spec,h,w,tile,margin,bits,device)

    # 眼牙增强：在**整幅坐标**上把掩膜画一次，然后逐块切给自己那一片（与 grade_mask
    # 的先例同一条），而不是每块各自从关键点重画——两块交界处的软边必须与整幅一致，
    # 而每块重算会把羽化截断在块边界上（那会在出片里留下一条笔直的眼白接缝）。
    # 排在这里而不是最前面：内容门判的是“这份底图上的组”——消除笔先把口腔里的
    # 异物掉掉，那一组的均值就变了，与预览里“先修完再挂眼牙层”是同一条链。
    smoothing_pixels = None
    if spec.creative_smoothing_context is not None:
        from .creative_derived_smoothing import verify_export as verify_smoothing_export
        smoothing_pixels = verify_smoothing_export(spec,src_u8,base_f,divisor)
    from .fabric_export import prepare_export
    fabric_field = prepare_export(spec, src_u8, base_f, divisor)
    wrinkle_layer = WRUNTIME.prepare_export(spec, src_u8, base_f, divisor)
    lip_layer = LIPR.prepare_export(spec, src_u8, base_f, divisor)
    enh_reg = None
    enh_weight = None
    under_layer = None
    enhance_ms = 0.0
    if any(float(vv) != 0.0 for key, vv in (spec.enhance or {}).items() if key not in WSTATE.INTENT_KEYS):
        t_e = time.perf_counter()
        enh_reg = ENH.geometry(spec.landmarks, h, w)
        ey0, ex0, eeh, eew = enh_reg.window
        # 只把窗口那一片换成 float：整幅 astype 会在 24 MP 上多占 72 MB，而这一层用不着
        e_win = (base_f[ey0:ey0 + eeh, ex0:ex0 + eew] if base_f is not None
                 else src_u8[ey0:ey0 + eeh, ex0:ex0 + eew].astype(np.float32) / divisor)
        enh_weight, _enh_facts = ENH.refine(enh_reg, np.ascontiguousarray(e_win))
        if any(spec.enhance.get(k, 0) for k in UNDER.KEYS):
            uwindow, ulm = UNDER.bounds(spec.landmarks, h, w)
            uy, ux, uh, uw = uwindow
            upixels = (base_f[uy:uy+uh, ux:ux+uw] if base_f is not None else
                       src_u8[uy:uy+uh, ux:ux+uw].astype(np.float32) / divisor)
            under_layer = UNDER.UnderEyeLayer(uwindow, upixels, ulm)
            under_layer.solve(spec.enhance)
        enhance_ms = (time.perf_counter() - t_e) * 1000.0
    scale = int(spec.scale)
    plan = UpscalePlan(h, w, scale)          # 表只算一次，每块取自己那一段
    out_h, out_w = plan.out_h, plan.out_w
    out = np.zeros((h,w,3) if optical else (out_h,out_w,3), np.float32 if floating else np.uint8)
    support=np.zeros((h,w,3),np.float32) if spec.provenance_output else None
    editor_mask=None
    if editor_needed and editor_recipe['scope']=='local' and not tone_prepass:
        if spec.grade_scope=='all' or spec.grade_mask is None: raise ExportError('局部色彩编辑器需要当前有效蒙版，不能扩大至全图')
        if np.asarray(spec.grade_mask).shape!=(h,w): raise ExportError('Colour editor external mask differs from source domain')
        editor_mask=np.zeros((h,w,3),np.float32)
    seg = {"filter": 0.0, "light": 0.0, "deform": 0.0, "exposure": 0.0,
           "lut": 0.0, "grade": 0.0, "local_grade": 0.0, "enhance": 0.0, "bg": 0.0, "manual_liquify": 0.0}
    upscale_ms = 0.0
    # 三段非算子开销。为什么不只记算子：上一版只记五个算子段，跑靶量到"分段合计只占
    # 整帧 27%"——那 73% 不知道去哪了（真因是每块一次 empty_cache，把分配器缓存全
    # 放掉再重申请）。能归因的账单才是账单，否则只是把没说的话当作没事。
    io = {"setup": 0.0, "copyin": 0.0, "readback": 0.0}
    t_all = time.perf_counter()
    for i, (y0, y1, x0, x1) in enumerate(rects):
        cy0, cx0 = max(y0 - margin, 0), max(x0 - margin, 0)
        cy1, cx1 = min(y1 + margin, h), min(x1 + margin, w)
        th, tw = cy1 - cy0, cx1 - cx0
        t0 = time.perf_counter()
        pipe = PreviewPipeline(device, tw, th, high_precision_warp=(bits == 16 or creative_source))
        if base_f is not None:
            pipe.load_rgb_f32(np.ascontiguousarray(base_f[cy0:cy1, cx0:cx1]))
        elif bits == 16 or creative_source:
            pipe.load_rgb_f32(np.ascontiguousarray(src_u8[cy0:cy1, cx0:cx1], dtype=np.float32) / divisor)
        else:
            pipe.load_rgb_u8(src_u8[cy0:cy1, cx0:cx1])
        pipe.primary_calibration=primary_stage(spec)
        pipe.primary_calibration.cancelled=tone_cancelled
        # Rasterize once at source dimensions, then take the identical tile halo
        # used by all operators. RGB8/RGB16 share this float recovery stage.
        if people_prepared is not None:
            from .people_pipeline import install as install_people
            install_people(pipe,people_prepared,origin=(cy0,cx0))
        attach_tile(pipe, spec, (cy0, cx0, cy1, cx1))
        attach_manual_tile(pipe, spec, (cy0, cx0, cy1, cx1))
        attach_studio_tile(pipe, spec, (cy0, cx0, cy1, cx1))
        attach_id_background(pipe, spec, (cy0, cx0, cy1, cx1))
        attach_sky_tile(pipe,spec,(cy0,cx0,cy1,cx1))
        t_c = time.perf_counter()
        io["setup"] += (t_c - t0) * 1000.0
        if spec.light:
            sub = _crop_ops(spec.light, (cy0, cx0, cy1, cx1), LightOp)
            if sub:
                # 先挂笔迹再改参数：set_light_params 自己会把两份 db 缓存作废，
                # 导出器不该去碰那几个字段（“能只改两条的三条状态”是 M2 审过的病）
                pipe.set_light_ops(sub)
                pipe.set_light_params(spec.light_exposure, spec.light_radius)
        if fabric_field is not None:
            pipe.fabric.install(fabric_field[cy0:cy1, cx0:cx1], spec.fabric_amount)
        if delta is not None and people_prepared is None:
            pipe.adopt_deform_field(delta[:, cy0:cy1, cx0:cx1].contiguous().to(device))
            pipe.brow_shape_combined = brow_field is not None and brow_field.state is not None
            pipe.nose_shape_combined = nose_field is not None and nose_field.state is not None
            pipe.eye_shape_combined = eye_field is not None and eye_field.state is not None
            pipe.mouth_shape_combined = mouth_field is not None and mouth_field.state is not None
            if pipe.mouth_shape_combined:
                pipe.mouth_shape_teeth_support = mouth_field.teeth_support[cy0:cy1,cx0:cx1]
        if enh_reg is not None:
            # 先挂场再提交参数：set_enhance 只改三个数，而 has_enhance() 要同时看到场，
            # 反过来写会有一瞬"参数点火而场上没有额度"——那一瞬里 lit 报的是假话
            pipe.set_enhance_field(enh_reg.window, enh_weight, origin=(cy0, cx0))
        WRUNTIME.install_export_tile(pipe, wrinkle_layer, (cy0, cx0), spec.enhance or {})
        LIPR.install_export_tile(pipe, lip_layer, (cy0, cx0), spec.lip_makeup)
        if spec.enhance:
            pipe.set_enhance(spec.enhance)
        if under_layer is not None:
            UNDER.attach_delta(pipe, under_layer.window, under_layer.delta, origin=(cy0, cx0))
        # 旧调用方可能仍只带 EV/WB 三项：先补长到 7 元组，再判中性/取影调四项。
        expo = (tuple(float(v) for v in spec.exposure) + (0.0,) * 7)[:7]
        if expo != (0.0,) * 7 or WB.has_picks(spec.wb_options) or spec.wb_options["algorithm"] == WB.CORRECTED:
            # 插在 cube/grade 之前提交：与预览链里 apply_exposure 的位置一致（lut 前）。
            # 提交顺位不影响数值（链序在 render 里定死），但保持“按链序挂图层”这个习惯，
            # 以后谁改链序时不会在这里多一个错因不明的不同步。
            pipe.set_exposure(expo[0], expo[1], expo[2],
                              ref_k=spec.exposure_ref_k,
                              contrast=expo[3], highlights=expo[4],
                              shadows=expo[5], saturation=expo[6], wb_options=spec.wb_options)
        if not LEVELS.is_identity(spec.levels): pipe.set_levels(spec.levels)
        if not CURVES.is_identity(spec.curves):
            pipe.set_curves(spec.curves)
        if any(float(v) != 0.0 for v in spec.hsl):
            pipe.set_hsl(spec.hsl)
        if spec.cube is not None:
            pipe.set_lut(spec.cube, spec.lut_amount)
        if spec.grade != (0.0, 0.0, 0.0, 1.0):
            pipe.set_grade(*spec.grade[:3], amount=spec.grade[3])
            if spec.grade_scope != "all" and spec.grade_mask is not None:
                # 逐像素对应：调色是逐点的（margin 里那些像素不参与它），所以按与补丁
                # 完全相同的窗口切区域就行，不需要重采样也不需要外边扩。
                sub = spec.grade_mask[cy0:cy1, cx0:cx1]
                if spec.grade_scope == "objects":
                    # Objects live in the source domain, unlike the legacy
                    # brush display mask. Reuse the actual image warp at grade
                    # time; the existing displacement margin covers sampling.
                    pipe.set_local_mask(sub)
                elif int((sub > 0).sum()) > 0:
                    # 与预览同一份库层入口：先挂区域再切作用域（brush 无区域会被当场拒）
                    pipe.set_grade_mask(sub, mode="replace")
                    pipe.set_grade_scope("brush")
                else:
                    # 这一块完全在区域外：整层不挂 = 该块逐字节与原片同（而不是拿
                    # scope=brush 去撞一个“无区域”的异常，也不是默默全图调色）
                    pipe.clear_grade()
        pipe.local_grade_layers.set([
            {'id': item['id'], 'grade': item['grade'],
             'weight': item['weight'][cy0:cy1, cx0:cx1]}
            for item in spec.local_grade_fields])
        if spec.bg_matte is not None and spec.bg_ref is not None:
            # P1-2 换底：与 grade_mask 同一个切窗（逐像素对应，外边扩那些像素不参与
            # 混合，只喂给带限算子）；遮罩是代理档上算好后 resample 到导出尺寸的连续覆盖度，
            # 与预览链上那次 set_background 走的是同一份 composite_t 算式。
            pipe.set_background(spec.bg_matte[cy0:cy1, cx0:cx1], list(spec.bg_ref))
        if spec.channel is not None and spec.masks is not None:
            carrier = _MaskCarrier(spec.masks[:, cy0:cy1, cx0:cx1], spec.landmarks)
            carrier._carrier_names = list(spec.mask_names)
            pipe.load_face(carrier)
        if smoothing_pixels is not None:
            from .creative_derived_smoothing_runtime import bind as bind_smoothing_tile
            bind_smoothing_tile(pipe,spec.creative_smoothing_context['source'],
                smoothing_pixels[cy0:cy1,cx0:cx1],mask_channel=spec.channel,
                mask_pixels=None if spec.channel is None else spec.masks[0,cy0:cy1,cx0:cx1],
                domain='export-tile',evidence_key=spec._creative_smoothing_pixels)
        render_options = dict(radius=spec.radius, eps=spec.eps,
                              detail_gain=spec.detail_gain, mid_gain=spec.mid_gain,
                              broad_gain=spec.broad_gain, texture_radius=spec.texture_radius,
                              channel=spec.channel if spec.masks is not None else None)
        if tone_field is not None:
            pipe.extended_tone_override=torch.from_numpy(np.ascontiguousarray(tone_field[cy0:cy1,cx0:cx1].transpose(2,0,1))).unsqueeze(0).to(pipe.src_f32.device)
        if floating:
            rendered = pipe.retouch(spec.strength, **render_options, render_stage='extended-tone-input' if tone_prepass else 'output')
            t_r = time.perf_counter()
            got = np.ascontiguousarray(rendered[0].permute(1, 2, 0).detach().cpu().numpy())
            del rendered
        else:
            pipe.render(spec.strength, **render_options)
            t_r = time.perf_counter()
            got = pipe.read_back()[..., :3]
        if editor_mask is not None:
            weight=np.asarray(spec.grade_mask[cy0:cy1,cx0:cx1],dtype=np.float32)/255.
            coverage_t=torch.from_numpy(np.repeat(weight[...,None],3,axis=2)).permute(2,0,1)[None].to(pipe.device)
            if spec.grade_scope=='objects':coverage_t=pipe.align_source_grade_mask(coverage_t)
            coverage_t=pipe.manual_liquify.apply(coverage_t)
            mapped=coverage_t[0].permute(1,2,0).detach().cpu().numpy()
            editor_mask[y0:y1,x0:x1]=mapped[y0-cy0:y1-cy0,x0-cx0:x1-cx0]
        if support is not None:
            from .reference_color_provenance import source_support
            evidence=source_support(pipe,(cy0,cx0,cy1,cx1),(h,w),spec)
            support[y0:y1,x0:x1]=evidence[y0-cy0:y1-cy0,x0-cx0:x1-cx0]
        if scale == 1 or optical:
            out[y0:y1, x0:x1] = got[y0 - cy0:y1 - cy0, x0 - cx0:x1 - cx0]
        else:
            # 把本块有数区渲染结果按全局权重表放大到输出坐标里对应那一段。
            # 不是"先拼整幅再放大"——那会把峰值从 tile 拉回图幅；也不比 0：
            # 同一串 (下标, 权重) 同一累加顺序，与整幅 `plan.full` 逐字节同一
            t_u = time.perf_counter()
            sampler = plan.region_float if floating else plan.region
            out[y0 * scale:y1 * scale, x0 * scale:x1 * scale] = sampler(
                got, y0 * scale, y1 * scale, x0 * scale, x1 * scale, cy0, cx0)
            upscale_ms += (time.perf_counter() - t_u) * 1000.0
        io["readback"] += (time.perf_counter() - t_r) * 1000.0
        tile_seg = sum(float(getattr(pipe, f"last_{k}_ms", 0.0) or 0.0) for k in seg)
        for k in seg:
            seg[k] += float(getattr(pipe, f"last_{k}_ms", 0.0) or 0.0)
        # 剩下那一段 = 挂图层（重采样后的笔迹/掩膜上传、TPS 场切片上传、表与定向参数）
        # 减的是**本块**那五段，不是累计值：拿累计值去减会把负数夹成 0，看着像“零搬运”
        io["copyin"] += max(0.0, (t_r - t_c) * 1000.0 - tile_seg)
        del pipe
        if progress is not None:
            progress(i + 1, len(rects), (time.perf_counter() - t0) * 1000.0)
    if tone_prepass:
        finish_sky(spec)
        finish_id_background(spec)
        verify_body_source(spec);verify_hair_source(spec);verify_semantic_source(spec)
        return out, {'extended_tone_boundary':'exposure-output','prepass':True}
    del tone_field
    ms = (time.perf_counter() - t_all) * 1000.0
    optics_facts = {"applied":False}
    if optical:
        from .optics_runtime import apply_export
        from .optics_export import upscale as optical_upscale
        out,optics_facts=apply_export(out,spec,cancelled=mask_cancelled)
        if editor_mask is not None:
            from .reference_color_provenance import optical_support
            editor_mask=optical_support(editor_mask,spec)
        if support is not None:
            from .reference_color_provenance import optical_support
            support=optical_support(support,spec)
        t_u=time.perf_counter();out=optical_upscale(out,plan,cancelled=mask_cancelled)
        upscale_ms+=(time.perf_counter()-t_u)*1000.
    sharpen_ms = 0.0
    if float(spec.sharpen_amount) > 0.0:
        # 出片锐化排在放大之后、且切的是已经完整的输出图：带 halo 拿真像素，
        # 只有图的真边缘才用 replicate——所以与整图直锐逐字节同一，不拿近似当默认
        t_s = time.perf_counter()
        sharpener = unsharp_float_bands_np if floating else unsharp_bands_np
        out = sharpener(out, radius=float(spec.sharpen_radius),
                               amount=float(spec.sharpen_amount),
                               threshold=float(spec.sharpen_threshold))
        sharpen_ms = (time.perf_counter() - t_s) * 1000.0
    geometry_facts = {}
    if geometry is not None:
        from .ops.geometry import crop_rotate_np, is_identity
        t_geometry = time.perf_counter()
        out = crop_rotate_np(out, *geometry, uint8=False)
        if support is not None: support=crop_rotate_np(support,*geometry,uint8=False)
        if editor_mask is not None:editor_mask=crop_rotate_np(editor_mask,*geometry,uint8=False)
        out_h, out_w = out.shape[:2]
        geometry_facts = {"crop_applied": not is_identity(*geometry),
                          "geometry_ms": round((time.perf_counter() - t_geometry) * 1000, 2)}
    out=reference_stage.apply_np(out)
    out=semantic_stage.apply_np(out)
    out=colour_grading_stage.apply_np(out,cancelled=tone_cancelled)
    out=selective_colour_stage.apply_np(out,cancelled=tone_cancelled)
    if editor_needed and not tone_prepass:
        from .colour_editor_stage import ColourEditorStage
        editor=ColourEditorStage(editor_recipe)
        if hasattr(spec,'_colour_editor_domain'): editor.domain=spec._colour_editor_domain
        frozen=np.ascontiguousarray(out,dtype=np.float32)
        # Full source before delivery resampling. Transparent geometry padding is
        # excluded; the same external mask gates inversion and range view.
        from .photo_grain_geometry import mapping as editor_geometry
        mapping=editor_geometry((w,h),geometry,(frozen.shape[1],frozen.shape[0]))
        coverage=np.empty(frozen.shape[:2],dtype=np.float32)
        for yy in range(frozen.shape[0]):
            if yy%64==0:tone_cancelled()
            coverage[yy]=mapping(0,yy,frozen.shape[1])[:,2]
        if editor_mode=="input":spec._colour_editor_capture_coverage=coverage.copy()
        if editor_mask is not None:
            if editor_mask.shape!=frozen.shape: raise ExportError('Transformed external mask does not match editor canvas')
            coverage*=np.clip(np.min(editor_mask,axis=2),0,1)
        editor.external_mask=coverage
        if editor_mode=='input':
            out=frozen
        else:
            editor.prepare_source(frozen,('source',str(w)+'x'+str(h),str(geometry),'geometry-coverage-v1'),mask=coverage,cancelled=tone_cancelled)
            out=editor.apply_np(frozen,purpose='selection-view' if editor_mode=='view' else 'export',cancelled=tone_cancelled)
    # Presentation-only input/view bypass downstream finishing, but still pass
    # through all final source/asset validation below before publication.
    if editor_mode=='render':
        out=PhotoDetailStage(detail_recipe,scale=float(spec.scale),cancelled=tone_cancelled).apply_np(out)
        if grain_active(grain_recipe):
            from .photo_grain_native import apply_canvas
            out=apply_canvas(np.ascontiguousarray(out,dtype=np.float32),grain_recipe,source_size=(w,h),geometry=geometry,cancelled=tone_cancelled)
        out=ExtendedToneStage(tone_recipe,cancelled=tone_cancelled).finish_np(out)
    verify_semantic_source(spec)
    verify_body_source(spec)
    verify_hair_source(spec)
    if support is not None: spec.provenance_result=np.all(support>=.999999,axis=2)
    if bits == 16 and not spec.float_output:
        out = quantize16_np(out)
    elif floating and not spec.float_output:
        out = np.clip(np.rint(out*255.),0,255).astype(np.uint8)
    if group_source_stamp is not None and file_stamp(spec.local_mask_source_path) != group_source_stamp:
        raise ExportError('Independent local-grade source changed during rendering')
    finish_sky(spec)
    finish_id_background(spec)
    from .studio_background_state import active as studio_active
    if studio_active(spec.studio_background) and list(file_stamp(spec.studio_background_path)) != spec.studio_background_stamp:
        raise ExportError('背景源图在完整出片过程中变化')
    if recovery_source_stamp is not None and file_stamp(spec.effect_recovery_path) != recovery_source_stamp:
        raise ExportError('效果恢复源图在渲染过程中变化，停止导出')
    if manual_source_stamp is not None and file_stamp(spec.manual_liquify_path) != manual_source_stamp:
        raise ExportError("手动液化源图在渲染过程中变化，停止导出")
    peak_bytes = int(delta.numel() * 4) if delta is not None else 0
    from .body_pose_render import export_outcome
    body_outcome=export_outcome(people_prepared,out,(w,h))
    return out, {
        "body_pose":body_outcome,
        "bits": bits, "warp_precision": "float64" if bits == 16 else "float32",
        "w": out_w, "h": out_h, "px": out_w * out_h, "src_mb": round(h * w * 3 * src_u8.dtype.itemsize / 1e6, 2),
        "src_w": w, "src_h": h, "scale": scale,
        "upscale_backend": spec.upscale_backend if scale > 1 else None,
        "upscale_ms": round(upscale_ms, 2), "sharpen_ms": round(sharpen_ms, 2),
        "sharpen_amount": float(spec.sharpen_amount),
        "tile": int(tile), "tiles": len(rects), "margin_px": int(margin),
        "deform_peak_px": round(peak, 3), "total_ms": round((time.perf_counter() - t_function) * 1000, 1),
        "field_ms": round(field_ms, 1),
        "optics": optics_facts, "optics_admission_bytes": optical_budget,
        "manual_liquify_field_ms": round(manual_field_ms, 1),
        "manual_liquify_peak_px": round(manual_peak, 3),
        "manual_liquify_field_cpu_bytes": (0 if spec.manual_liquify_field is None else int(spec.manual_liquify_field.nbytes)),
        "manual_liquify_tile_estimate_bytes": manual_tile_budget,
        "sky_replacement_cpu_bytes": sky_bytes(spec),
        "sky_replacement_tile_estimate_bytes": sky_tile_budget,
        "id_background_preparation_estimate_bytes": id_background_admission,
        # 这一层的"重画掩膜"成本单独报：它与形变解场是两种一次性的钱，混在
        # field_ms 里就看不出该优化谁（导出账单里每一段都要能归因，否则只是把没说的话当作没事）
        "enhance_field_ms": round(enhance_ms, 1),
        "enhance": dict(spec.enhance or {}),
        "lip_makeup": dict(lip_layer.facts) if lip_layer is not None else {},
        "lip_makeup_full_resolution": lip_layer is not None,
        "brow_shape": brow_field.facts if brow_field else {},
        "brow_shape_full_resolution": brow_field is not None,
        "nose_shape": nose_field.facts if nose_field else {},
        "nose_shape_full_resolution": nose_field is not None,
        "eye_shape": eye_field.facts if eye_field else {},
        "eye_shape_full_resolution": eye_field is not None,
        "mouth_shape": mouth_field.facts if mouth_field else {},
        "mouth_shape_full_resolution": mouth_field is not None,
        "lip_makeup_bytes": lip_layer.resident_bytes() if lip_layer is not None else 0,
        "facial_wrinkles": dict(wrinkle_layer.facts) if wrinkle_layer is not None else {},
        "facial_wrinkle_full_resolution": wrinkle_layer is not None,
        "facial_wrinkle_bytes": wrinkle_layer.resident_bytes() if wrinkle_layer is not None else 0,
        "fabric_amount": spec.fabric_amount,
        "per_tile_ms": round(ms / max(len(rects), 1), 2),
        "seg_ms": {**{k: round(v, 2) for k, v in seg.items()},
                   **{k: round(v, 2) for k, v in io.items()}},
        "delta_cpu_mb": round(peak_bytes / 2**20, 1),
        "local_grade_groups": len(spec.local_grade_fields),
        "local_grade_mask_cpu_bytes": sum(int(item['weight'].nbytes) for item in spec.local_grade_fields),
        "effect_recovery_targets": [item['target'] for item in spec.effect_recovery_fields],
        "effect_recovery_mask_cpu_bytes": sum(int(item['weight'].nbytes) for item in spec.effect_recovery_fields),
        "channel": spec.channel, **repair_stats, **geometry_facts,
        "people":None if people_prepared is None else {"full_resolution":True,"prepare_ms":round(people_prepare_ms,2),
            "faces":[row["face_ref"] for row in people_prepared.plan["entries"]],
            "facts":people_prepared.facts,"overlap_pixels":people_prepared.geometry.overlap_pixels,
            "overlap_policy":people_prepared.plan["overlap_policy"],"selection_independent":True,"refused_count":0},
    }


def resample_field(arr: np.ndarray, out_hw: tuple, *, uint8: bool = False) -> np.ndarray:
    """把代理档上的掩膜/笔迹重采样到导出尺寸。双线性，不最近邻。

    为什么不是最近邻：笔迹覆盖度是一个**连续量**（uint8 的 0..255 是羽化后的覆盖度，
    不是二值抠图），最近邻在 6× 放大下会把羽化边拆成 6 px 宽的硬块，修容会在脸上
    留下马赛克。而双线性恰好是“同一个连续场在不同网格上取值”的正确做法。

    半径不跟着缩放：`light_radius` 是**图像像素**上的带限半径，导出尺寸下它物理上就
    变小了（代理 960 宽与满幅 6000 宽是同一半径的不同视直径）。本轮不拿“比例缩放半径”
    冒充产品口径：那会改变预览看上去的修容软硬。账单里如实报出缩放因子。

    走 torch 而不是 PIL：掩膜是 float32，`Image.fromarray` 不接 float 模式；而这里的
    两种 dtype 本来就要插值同一个连续场，用一个算子而不是两条实做。
    """
    if torch is None:
        raise ExportError("重采样需要 torch（装 rocm/cuda/cpu 任一变体）")
    import torch.nn.functional as NF        # 局部导入：模块顶层那个 torch 可能是 None
    a = np.asarray(arr)
    oh, ow = int(out_hw[0]), int(out_hw[1])
    if a.ndim == 2:
        stack = a[None]
    elif a.ndim == 3 and a.shape[0] != 3:      # (K,H,W)：逐通道
        stack = a
    else:
        raise ExportError(f"只能重采样 (H,W) 或 (K,H,W) 的场，得到 {a.shape}")
    if (a.shape[-2], a.shape[-1]) == (oh, ow):
        return a.copy()
    t = torch.from_numpy(np.ascontiguousarray(stack, dtype=np.float32))[:, None]
    up = NF.interpolate(t, size=(oh, ow), mode="bilinear", align_corners=False)
    up = up[:, 0]
    if uint8:
        up = up.round().clamp_(0.0, 255.0)
        out = up.to(torch.uint8).numpy()
    else:
        out = up.numpy().astype(np.float32)
    return out[0] if a.ndim == 2 else out


def _icc_facts(icc: bytes | None) -> dict:
    """ICC 的可验回执：长度 + 那一份字节的 sha256。

    为什么必须有 sha256（而只有长度不够）：实测 littleCMS 的 `createProfile("sRGB")`
    **把建档那一刻的日期写进 profile 头部**（年/月/日/时/分/秒六个 uint16）。于是同一
    台机器两个子进程给出的字节不一样（588 B，sha256 分别 c827bf… 与 a82481…），而
    上一版记的“进程内稳定”只在**同一秒内**成立：一次批量导出里隔十秒的两张，嵌的
    就是两份不同的档（本轮端到端用例拿“重试产物该等于快照那一份”的字节对拍响的就
    是这个）。现在由 `_srgb_bytes()` 在本进程里只建一次并冻住：同一次会话内同参数
    导出逐字节可重现，而跨进程仍如实带着各自的建档时间。
    能证的只有“事件里报的那份字节，就是文件里的那份”，这需要哈希而不是长度。
    产物的语义正确性另由“它是 sRGB built-in”与读回可解码来证（见 COLOR-001 的口径）。
    """
    if not icc:
        return {"icc_bytes": 0, "icc_sha256": None}
    import hashlib
    return {"icc_bytes": len(icc), "icc_sha256": hashlib.sha256(icc).hexdigest()}


_SRGB_CACHE: bytes | None = None


def _srgb_bytes() -> bytes:
    """sRGB 档在本进程里只建一次并冻住。

    不冻的代价不是“好看一点”而是具体的：littleCMS 把建档那一刻的秒写进 profile 头部，
    于是同一张图、同一套设置，在本会话里导出两次会得到两份不同的字节——“重试的产物
    等于快照那一份”这种逐字节判据永远立不住（本轮就是端到端用例响出来的），而批量
    导出每张还多付一次建档。缓存只处理“同进程”，不伪造型产物的时间：跨进程那两份
    仍各自带着自己的建档时间，所以下游比对产物一律解码比像素，不比跳进程的字节。
    """
    global _SRGB_CACHE
    if _SRGB_CACHE is None:
        from PIL import ImageCms
        _SRGB_CACHE = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return _SRGB_CACHE


def _profile_bytes(name: str, source: bytes | None = None) -> bytes | None:
    """取输出 ICC。只给能真拿到档的选项，拿不到的**明确拒并说缺什么**。

    为什么不烘一个“看起来像”的 profile 充 AdobeRGB/P3：嵌错的 ICC 比不嵌更坏——
    读方会拿错的那份去转色，结果是颜色真的变了而文件里写着另一个名字。
    COLOR-002 要的就是这个口径：“展示使用的输入假设/错误；不静默声称准确还原”。

    - srgb：Pillow/littleCMS 内建档（实测 588 B），不依赖任何系统资产；本进程内
      只建一次（见 `_srgb_bytes()`），否则同一次会话里每张图嵌的都是自己那一秒的档；
    - source：透传源文件自己那份（没有源档时报错，而不是默默不嵌）；
    - adobergb / display_p3：需要一个真实的 .icc 文件路径。本层不绑 ghostscript 那种
      系统目录（发行物不该依赖一个不确定存在的资产），调用方递路径即可。
    """
    # 关键字归一只用于内置名（none/source/srgb 本就该大小写不敏感）；
    # 但用户递进来的真实 .icc **路径**必须按原样处理——Linux 文件系统区分大小写，
    # 对路径调 .lower() 会让 "MyProfile.icc" 找不存在的 "myprofile.icc"，
    # 于是把一份真实存在的档当成未知内置名而拒（P2-1）。
    key = (name or "srgb").lower()
    if key in (None, "", "none"):
        return None
    if key == "source":
        if not source:
            raise ExportError("output_profile=source 但源文件没有 ICC："
                              "这条口径不能默默退成“不嵌”，请改选 srgb 或给一个 profile 文件")
        return bytes(source)
    if key == "srgb":
        return _srgb_bytes()
    # 路径分支：用原始 name（不 lower），存在与读取都用它。
    if name and os.path.isfile(name):             # 也接受直接给路径（大小写敏感）
        with open(name, "rb") as f:
            return f.read()
    raise ExportError(
        f"output_profile={name!r} 本层不带该档（内置只有 sRGB）。"
        f"要么改用 srgb / source，要么把一个真实的 .icc 文件路径递进来——"
        f"不嵌一份名字对、内容错的档。")


# P1-3（F03）：导出像素的工作空间经核实是 sRGB 编码的显示参考 8-bit——decode 的非 RAW 路径走
# _to_working_srgb 显式输入转换，RAW 路径也归到 sRGB 显示域；工作空间为 sRGB，默认
# embed sRGB ICC 而不转色才是恒等。于是给一个「与 sRGB 不同的」输出档时，必须真把像素
# sRGB→目标档转一遍再嵌档：只贴标签会让色管读者拿错空间解释同一批 sRGB 数值，颜色就飘了
# ——这正是 F03「ICC 只写标签、不做转换」的口径。
#
# 渲染意图默认 relative_colorimetric + 黑点补偿（与 Photoshop「转换为配置文件」默认一致；
# 依据见 ADR-0023，已定档为首版默认）。要整体改口径只改 RENDERING_INTENT_DEFAULT 一处——
# 转换机制本身与意图选择无关。小整数取自 littleCMS 规范（PIL 12.3 实测一致）：
# perceptual=0、relative_colorimetric=1、saturation=2、absolute_colorimetric=3；BPC flag=8192。
RENDERING_INTENT_DEFAULT = "relative_colorimetric"
_INTENT_CODES = {"perceptual": 0, "relative_colorimetric": 1,
                 "saturation": 2, "absolute_colorimetric": 3}
_FLAG_BLACKPOINT = 8192


def _convert_srgb_to_profile(img, target_icc: bytes | None, *,
                             intent: str = RENDERING_INTENT_DEFAULT):
    """把处于 sRGB 工作空间的 PIL 图转到 target_icc，返回 (新图, 生效意图名)。

    · target 为空、或与内置 sRGB 档字节相同 → 原样返回（恒等：不动像素、不引入一次舍入），
      意图名报 "srgb_identity"——默认导出（output_profile=srgb）因此与改动前逐字节一致。
    · 否则用 littleCMS（PIL.ImageCms）建 sRGB→target 变换并应用；除绝对色度外都开黑点补偿。
    口径与嵌档处严格对齐：write_file 对所有 RGB 光栅格式（jpg/jpeg/png/tif/tiff/webp）都
    嵌 icc_profile，于是每一种都必须先转色——漏掉任一种就是 F03「只贴标签不转色」在该格式复活。
    """
    from PIL import ImageCms
    from io import BytesIO
    if not target_icc or target_icc == _srgb_bytes():
        return img, "srgb_identity"
    if intent not in _INTENT_CODES:
        raise ExportError(f"未知渲染意图 {intent!r}（可用：{sorted(_INTENT_CODES)}）")
    src = ImageCms.createProfile("sRGB")
    dst = ImageCms.ImageCmsProfile(BytesIO(bytes(target_icc)))
    flags = 0 if intent == "absolute_colorimetric" else _FLAG_BLACKPOINT
    xf = ImageCms.buildTransform(src, dst, "RGB", "RGB",
                                 renderingIntent=_INTENT_CODES[intent], flags=flags)
    return ImageCms.applyTransform(img, xf, inPlace=False), intent


_EXIF_ORIENT_TAG = 0x0112        # Orientation：像素在解码层已经按它摆过了
_EXIF_GPS_TAG = 0x8825           # GPSInfo 指针


def _tiff_compression(name: str) -> str:
    """注册表里 tiff_compression 是 none|deflate|lzw（中性 deflate），翻成 Pillow 的名字。

    中性定成 deflate 而不是原来写死的 lzw：这一格在冻结的注册表里中性就是 deflate
    （ADR-0003）。真图实测（engine/tests/fixtures 那张 1.31 MP 人像，同一份 sRGB ICC）：
    none 3.93 MB / 31.3 ms，deflate 1.55 MB / 132.1 ms，lzw 1.96 MB / 51.9 ms，三者读回都
    逐字节一致——deflate 比 lzw 小 21%，代价是编码时间 2.5×。批量导出时这笔时间是要不要
    换的选择题，所以三个值都开出来而不是只留一个。名字认不出的一律拒：把 "zip" 默默当成
    deflate 会让导出清单里写着用户没选过的那个名字。
    """
    key = (name or "deflate").lower()
    table = {"none": "none", "deflate": "tiff_deflate", "lzw": "tiff_lzw"}
    if key not in table:
        raise ExportError(f"tiff_compression={name!r} 不可用（可用：none / deflate / lzw）")
    return key, table[key]


def _filter_exif(exif, include_gps: bool) -> tuple[bytes | None, dict]:
    """按开关产出要写的 EXIF 字节，同时交出两项可验事实。

    返回 (字节或 None, {"gps_written": …, "orientation_dropped": …})。

    这里不靠“从数组新建图本来就没 EXIF”来保证不泄位——那是不作数偶然成立，
    一旦接上源元数据透传就失效。写法是正面删，且三个细节都是定下来的：

    1. **判有无 GPS 只看“键在不在”，不调 `get_ifd(0x8825)`**。Pillow 的 `get_ifd` 会把解出来的
       子 IFD 缓存进一个私有 `_ifds`，而 `tobytes()` 会遍历 `_ifds` 并把“不在 items 里”的子 IFD
       重新写回去——删了指针也可能被缓存反写回来。实测三种写法都得出了“GPS 没写出”的结果，
       但那取决于缓存时序，不能当依据；不调它就不会有缓存。
    2. **Orientation 永远删**，与 GPS 开关无关。解码时已经按它把像素摆正了（见 decode.py 的
       exif_transpose），把 274 透传出去等于让读方再转一次——那正是 COLOR-003 里
       “输出无二次方向错误”点名的坑。
    3. 在一份**新载入的副本**上操作，不修改调用方递进来的对象：同一份 source_exif 会在一批
       导出里被用很多次，就地 pop 会让第一张之后的每一张都“莫名少了”那些字段。

    损坏的 EXIF 不默默丢弃也不默默重写：报 ExportError，这是 COLOR-002 的“展示…错误”。
    """
    facts = {"gps_written": False, "orientation_dropped": False}
    if exif is None:
        return None, facts
    from PIL import Image
    if isinstance(exif, Image.Exif):
        raw = bytes(exif.tobytes())
    elif isinstance(exif, (bytes, bytearray)):
        raw = bytes(exif)
    else:
        raise ExportError(f"source_exif 类型不可用：{type(exif).__name__}"
                          "（只接 Pillow Image.Exif 或 EXIF 字节）")
    if not raw:
        return None, facts
    ex = Image.Exif()
    try:
        ex.load(raw)
    except Exception as e:
        raise ExportError(f"源 EXIF 解析失败（{type(e).__name__}: {e}）："
                          "不默默丢也不默默重写，拿它当“没有元数据”导出是把错误藏起来") from None
    had_gps = _EXIF_GPS_TAG in ex
    had_orient = _EXIF_ORIENT_TAG in ex
    if had_orient:
        ex.pop(_EXIF_ORIENT_TAG, None)
    if had_gps and not include_gps:
        ex.pop(_EXIF_GPS_TAG, None)
    out = bytes(ex.tobytes())
    facts["gps_written"] = bool(had_gps and include_gps)
    facts["orientation_dropped"] = bool(had_orient)
    return (out or None), facts


def _check_policy(conflict_policy) -> str:
    """策略名先解析成枚举，认不出的直接拒。

    这个函数存在的理由是“校验必须与文件是否存在无关”：把拒写埋在冲突分支里，
    一个拼错的 conflict_policy 在目标为空时会被静默当成 skip_and_report 通过，
    批量导出一百张全新文件时一次错都不会报——那是比覆盖更坏的行为（它让调用方
    相信自己设了保护）。测试 test_overwrite_policy_is_rejected_as_a_category_error
    抓到的就是这个。
    """
    policy = (conflict_policy or "skip_and_report").lower()
    if policy not in ("skip_and_report", "recheck"):
        raise ExportError(f"conflict_policy={conflict_policy!r} 不可用"
                          f"（可用：skip_and_report / recheck；没有 overwrite 是有意的，"
                          f"见 ADR-0003 与 EXPORT-001 的“无无提示覆盖”）")
    return policy


def resolve_target(path: str, conflict_policy: str = "skip_and_report") -> tuple[str | None, str | None]:
    """落盘前解目标名。返回 (要写的路径或 None=跳过, 原因)。

    枚举里没有 overwrite 不是遗漏，是 EXPORT-001 的“无无提示覆盖”要求的直接体现
    （ADR-0003）。两个选项都不许盖掉已有文件：
      - skip_and_report：不写，把冲突作为结果交回去（批量跑完后这一条最容易被读到）；
      - recheck：不写旧文件，改用一个可追溯的唯一名继续写（撞名不丢产物，
        也不动别人的成果），并在回报里记录改名前后的对应关系。
    """
    policy = _check_policy(conflict_policy)
    from .export_destination_runtime import resolve
    frozen = resolve(path)
    if frozen is not None: return frozen
    if not os.path.lexists(path):
        return path, None
    if policy == "skip_and_report":
        return None, f"目标已存在，按 skip_and_report 跳过：{path}"
    if policy == "recheck":
        base, ext = os.path.splitext(path)
        for i in range(1, 10000):
            cand = f"{base}-{i:04d}{ext}"
            if not os.path.exists(cand):
                return cand, f"目标已存在，按 recheck 改用唯一名：{path} → {cand}"
        return None, f"目标已存在且 recheck 在 9999 个候选名里都没找到空位：{path}"


def _atomic_write(path: str, data: bytes) -> None:
    """Canonical descriptor-relative no-clobber publication for all export codecs."""
    from .export_destination_commit import commit_encoded_bytes
    from .export_destination_runtime import create_missing
    commit_encoded_bytes(os.path.abspath(path), data, create_missing=create_missing())


def write_file(rgb: np.ndarray, path: str, *, quality: int = 95,
               output_profile: str = "srgb", source_icc: bytes | None = None,
               source_exif=None, metadata_include_gps: bool = False,
               conflict_policy: str = "skip_and_report",
               tiff_compression: str = "deflate") -> dict:
    """落盘。jpg/webp 按质量、png/tif 无损。扩展名决定格式，不接受"看着像"的猜测。

    quality 越界是**拒**而不是夹：默默夹到 1 会交出一张体积小得反常的图，
    而调用方拿到的事件里写的还是他给的那个数。（与 set_strength 那条同一个理由。）
    """
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext not in FORMATS:
        raise ExportError(f"不支持的导出格式：{ext or '(无扩展名)'}（可用 {sorted(set(FORMATS))}）")
    try:
        q = int(quality)
    except (TypeError, ValueError):
        raise ExportError(f"quality={quality!r} 不是整数") from None
    if not 1 <= q <= 100:
        raise ExportError(f"quality={q} 越界（需要 1~100）")
    _check_policy(conflict_policy)   # 参数校验全部前置：一张 3 MP 的编码不该为一个拼错的字符串而白做
    comp_key, comp_pillow = _tiff_compression(tiff_compression)
    from PIL import Image                         # 校验完了才碰编码器：拒绝不需要 PIL
    t0 = time.perf_counter()
    img = Image.fromarray(np.ascontiguousarray(rgb), "RGB")
    kw = {}
    icc = _profile_bytes(output_profile, source_icc)
    # Input decoding normalizes pixels to sRGB. "source" selects the original
    # target profile, not unconverted source pixels; it needs the same transform.
    color_intent = None
    color_converted = False
    if icc:
        img, color_intent = _convert_srgb_to_profile(img, icc)
        color_converted = color_intent != "srgb_identity"
    if icc:
        kw["icc_profile"] = icc
    exif, exif_facts = _filter_exif(source_exif, bool(metadata_include_gps))
    if exif:
        kw["exif"] = exif
    if ext in ("jpg", "jpeg", "webp"):
        kw["quality"] = q
        if ext in ("jpg", "jpeg"):
            kw["subsampling"] = 0         # 4:4:4：修过色的图不能靠省色度换体积
    elif ext == "png":
        # PNG 的压缩档位是 0–9，与 JPEG 的 1–100 不同语义：这里把 quality 当"肯出多少力"
        # 映射。上限 6 不是拍脑袋：真图（3.06 MP 照片）实测 level 1/3/6/7/9 =
        # 198/290/804/1132/5469 ms，产物 3.20/3.00/2.67/2.64/2.56 MiB——7–9 档
        # 花 1.4–6.8× 的时间只换 3–4% 体积。而 quality=95 旧映射恰好落在最费的那一档：
        # 一百张 PNG 就是 9 分钟纯编码。不暴露 7–9 是一个可改的产品决定，
        # 不是一个未量过的默认值。
        kw["compress_level"] = min(6, q // 10)
    if ext in ("tif", "tiff"):
        kw["compression"] = comp_pillow
    # 先在内存里编码成字节，再走原子提交：编码失败不会留下一个名字对、内容没写完的文件
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format=_PIL_FORMAT.get(ext, ext.upper()), **kw)
    target, reason = resolve_target(path, conflict_policy)
    verifiable = {**_icc_facts(icc),
                  "icc_source": str(output_profile),
                  # P1-3 可审计事实：到底有没有真转色、用的哪个渲染意图。只贴标签不转色
                  # 会报 color_converted=false——行级写进导出清单，色管读者能反查这一句不是空话。
                  "color_converted": color_converted,
                  "color_intent": color_intent,
                  "gps_written": exif_facts["gps_written"],
                  "orientation_dropped": exif_facts["orientation_dropped"],
                  "exif_bytes": len(exif) if exif else 0,
                  # 质量口径的版本化自证（FORMAT-001）：本产品的 quality 是**我们自己的**
                  # 1~100 线性量表，直接交给编码器（JPEG/WebP）、按注释里那条实测曲线
                  # 映射到 PNG 压缩档（无损，与观感无关）、对 TIFF 不进编码。
                  # 与任何竞品的 0~14 档**不存在等价关系**，所以不写换算表、也不许在
                  # 事件里留下能被读成“等价”的字段。encoder_quality 记的是真正递给
                  # 编码器的那个数（无损格式为 None）：报出去的值与实际递出的值不一致时，
                  # 导出清单里就得看得出来。
                  "quality_mapping_version": QUALITY_MAPPING_VERSION,
                  "encoder_quality": (q if ext in ("jpg", "jpeg", "webp") else None),
                  # 报的是注册表里那个名字（deflate），不是 Pillow 的内部名（tiff_deflate）：
                  # 导出清单是给人看的，它该说用户选过的那个词
                  "tiff_compression": comp_key if ext in ("tif", "tiff") else None,
                  "tiff_compression_tag": {"none": 1, "deflate": 8, "lzw": 5}[comp_key]
                                          if ext in ("tif", "tiff") else None}
    if target is None:
        # 跳过的结果也要带全这一堆字段：事件形状不一致时，UI 那边就会在同一批里
        # 一会儿拿到 undefined 一会儿拿到值，而前者不报错
        return {"path": path, "format": ext, "skipped": True, "reason": reason,
                "conflict_policy": conflict_policy, "bytes": 0, "write_ms": 0.0,
                "quality": int(quality), "renamed_from": None,
                "compress_level": None, **verifiable}
    _atomic_write(target, buf.getvalue())
    ms = (time.perf_counter() - t0) * 1000.0
    return {"path": target, "format": ext, "bytes": os.path.getsize(target),
            "write_ms": round(ms, 1), "quality": int(quality),
            "skipped": False,
            # 可验字段：嵌了什么 ICC、GPS 到底在不在输出里、方向标有没有拆掉、
            # 冲突时改了名没有。只报“我做了什么”而不容许读方反查，等于没有证据。
            "renamed_from": None if target == path else path,
            "conflict_policy": conflict_policy,
            # PNG 实际用的压缩档位（其他格式为 None，不缺键）：回报里写 quality=95
            # 而文件是按 level 6 写的，两者对不上时必须看得出来，否则写盘耗时
            # 与体积就成了无从反推的谜
            "compress_level": kw.get("compress_level"),
            **verifiable}


# ------------------------------------------------------------------ 16-bit 母档直通（M9-e）
#
# 为什么单独一条路，而不是给 export_image 加一个 dtype 分支：export_image 的整条链
# （图层、掩膜、放大、锐化、色阶）都在 uint8 上算。把 16-bit 塞进去要么先降到 8 再升
# 回 16（那是假 16-bit，比不做更坏），要么每层另写一套 16-bit 数学（那是另一个里程
# 碑）。“直通”就是直通：母档解出来什么样就写什么样；图层上有东西时只能拒，不能假装做过。
#
# 为什么不叫 Pillow 保存：实测 `Image.fromarray` 直接拒 uint16 的三通道数组
# （Cannot handle this data type: (1, 1, 3), <u2），而它自己的 16-bit 路径只有单通道
# I;16。Baseline TIFF 的 interleaved 16bpc RGB 是最普通的落盘形状，写它不需第三个依赖。

_TIFF16_TAGS = (0x100, 0x101, 0x102, 0x103, 0x106, 0x111, 0x115, 0x116, 0x117, 0x128)
_TIFF16_ICC_TAG = 0x8773                          # ICCProfile = 34675（0x8711 是 34577，不是它）
#  这一处曾写成 0x8711：自写自读那份发现不了，Pillow 把标签原样收下但不认，
#  info 里没有 icc_profile 才暴露——“独立读方”这层交叉对拍就是为这种错留的。


def write_tiff16(rgb: np.ndarray, path: str, *, output_profile: str = "srgb",
                 source_icc: bytes | None = None,
                 conflict_policy: str = "skip_and_report",
                 metadata_include_gps: bool = False,
                 tiff_compression: str = "none") -> dict:
    """写RGB16 TIFF；none保留基线布局，Deflate/LZW使用可逆Predictor 2。

    条目按 tag 升序（TIFF 的硬要求，不是风格）；超过 4 字节的值（BitsPerSample 三个
    SHORT、ICCProfile 整份档）另存一处，条目里只放偏移。只写必需的那十一个 tag：多余的
    不是不能写，而每多一个就多一处与读回那一侧对不上的可能。

    d2c 的四个口径在这条路上也要成立，不能只在 8-bit 那侧做完就算交工：
    ICC 嵌进真 tag、冲突不静默覆盖、落盘走原子提交；GPS 则**明确拒**而不
    是默默忽略——16-bit 母档这一层没实现源元数据透传，接不了就得说出来
    （DoD-3 “未接通功能显式禁用并说明原因”，留一个按下去不响的开关是最坏的一种）。
    """
    import struct
    if rgb.dtype != np.uint16 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ExportError(f"16-bit 直通需要 uint16 的三通道数组，收到 "
                          f"dtype={rgb.dtype} shape={getattr(rgb, 'shape', None)}")
    key, _ = _tiff_compression(tiff_compression)
    if metadata_include_gps:
        raise ExportError("16-bit 母档直通不写 EXIF/GPS：这条路径只携带自己生成的那几个 "
                          "TIFF tag，透传源元数据尚未实现。要带 GPS 请走常规导出；"
                          "这里不接一个“按了不响”的开关。")
    policy = _check_policy(conflict_policy)
    icc = _profile_bytes(output_profile, source_icc)
    arr = np.ascontiguousarray(rgb)
    h, w = int(arr.shape[0]), int(arr.shape[1])
    compression_tag = {"none": 1, "deflate": 8, "lzw": 5}[key]
    if key != "none":
        import io
        import tifffile
        buffer = io.BytesIO()
        # Predictor 2 is reversible horizontal differencing. It changes the
        # stored representation, not the decoded uint16 samples.
        tifffile.imwrite(buffer, arr, photometric="rgb", planarconfig="contig",
                         byteorder="<", compression=compression_tag, predictor=2,
                         rowsperstrip=min(h, 256), iccprofile=icc, metadata=None,
                         software="LumaRetouch")
        blob = buffer.getvalue()
    else:
        data = arr.tobytes()
        tags = list(_TIFF16_TAGS) + ([_TIFF16_ICC_TAG] if icc else [])
        n = len(tags)
        bps_at = 8 + 2 + 12 * n + 4                  # BitsPerSample 三个 SHORT 的位置
        icc_at = bps_at + 6
        strip_at = icc_at + (len(icc) if icc else 0)
        ent = []

        def short(v): return struct.pack("<H", v) + b"\x00\x00"
        def long(v): return struct.pack("<I", v)

        ent.append(struct.pack("<HHI", 0x100, 4, 1) + long(w))   # ImageWidth
        ent.append(struct.pack("<HHI", 0x101, 4, 1) + long(h))   # ImageLength
        ent.append(struct.pack("<HHI", 0x102, 3, 3) + long(bps_at))
        ent.append(struct.pack("<HHI", 0x103, 3, 1) + short(1))   # Compression=None
        ent.append(struct.pack("<HHI", 0x106, 3, 1) + short(2))   # PhotometricInterp=RGB
        ent.append(struct.pack("<HHI", 0x111, 4, 1) + long(strip_at))
        ent.append(struct.pack("<HHI", 0x115, 3, 1) + short(3))   # SamplesPerPixel
        ent.append(struct.pack("<HHI", 0x116, 3, 1) + short(h))   # RowsPerStrip（单 strip）
        ent.append(struct.pack("<HHI", 0x117, 4, 1) + long(len(data)))
        ent.append(struct.pack("<HHI", 0x128, 3, 1) + short(1))   # PlanarConfiguration=Chunky
        if icc:
            ent.append(struct.pack("<HHI", _TIFF16_ICC_TAG, 7, len(icc)) + long(icc_at))
        blob = (b"II" + struct.pack("<HI", 42, 8)
                + struct.pack("<H", n) + b"".join(ent) + struct.pack("<I", 0)
                + struct.pack("<HHH", 16, 16, 16) + (icc or b"") + data)
    # 与 8-bit 那侧同一套提交：先解目标名再落盘，名字与内容都不能“碰运气”
    target, reason = resolve_target(path, policy)
    if target is None:
        return {"path": path, "format": "tif", "bits": 16, "w": w, "h": h,
                "skipped": True, "reason": reason, "conflict_policy": policy,
                "bytes": 0, "write_ms": 0.0, "gps_written": False,
                "renamed_from": None, "quality_mapping_version": QUALITY_MAPPING_VERSION,
                "encoder_quality": None,        # 直通不进编码器：这一格给 None 而不是 0
                **_icc_facts(icc)}
    t0 = time.perf_counter()
    _atomic_write(target, blob)
    return {"path": target, "format": "tif", "bits": 16, "w": w, "h": h,
            "bytes": os.path.getsize(target),
            "write_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "skipped": False,
            **_icc_facts(icc),
            "icc_source": str(output_profile),
            "gps_written": False,          # 本层不写 EXIF，这一句是可验的而不是声明
            "exif_bytes": 0,
            "renamed_from": None if target == path else path,
            "quality_mapping_version": QUALITY_MAPPING_VERSION,
            "encoder_quality": None,
            "conflict_policy": policy, "tiff_compression": key,
            "tiff_compression_tag": compression_tag}


def read_tiff16(path: str) -> np.ndarray:
    """把 write_tiff16 写出的那种文件读回数组（独立一份实现，与写侧互相对拍）。

    为什么在同一个模块里再写一份读的：要证的不是“Pillow 能打开”，而是“落盘的字节就是
    我手里那份 16-bit 数据”。只拿自写自读当证据是循环论证，所以这里同时把形状与
    位深都重新核对一遍，不满足就报错，不是降级读。"""
    import tifffile
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        if int(page.compression) != 1:
            if (len(tf.pages) != 1 or page.dtype != np.dtype("uint16")
                    or page.samplesperpixel != 3 or int(page.photometric) != 2
                    or int(page.imagewidth) * int(page.imagelength) > 120_000_000):
                raise ExportError("不是受支持的单页RGB16 TIFF")
            arr = page.asarray()
            if int(page.planarconfig) == 2:
                arr = arr.transpose(1, 2, 0)
            return np.ascontiguousarray(arr, dtype=np.uint16)
    import struct
    with open(path, "rb") as f:
        b = f.read()
    if b[:2] != b"II":
        raise ExportError("不是小端 TIFF")
    magic, ifd_at = struct.unpack_from("<HI", b, 2)
    if magic != 42:
        raise ExportError(f"TIFF magic 不是 42而是 {magic}")
    n = struct.unpack_from("<H", b, ifd_at)[0]
    tags = {}
    for i in range(n):
        o = ifd_at + 2 + i * 12
        tag, typ, cnt = struct.unpack_from("<HHI", b, o)
        raw = b[o + 8: o + 12]
        if typ == 3:                                   # SHORT
            tags[tag] = struct.unpack_from("<H", raw, 0)[0] if cnt == 1 else None
        elif typ == 4:                                 # LONG
            tags[tag] = struct.unpack_from("<I", raw, 0)[0]
        else:
            tags[tag] = None
    if tags.get(0x102) is None:
        at = struct.unpack_from("<I", b, ifd_at + 2 + 12 * [i for i in range(n)
                          if struct.unpack_from("<H", b, ifd_at + 2 + i * 12)[0] == 0x102][0] + 8)[0]
        if struct.unpack_from("<HHH", b, at) != (16, 16, 16):
            raise ExportError("BitsPerSample 不是三个 16")
    if tags.get(0x115) != 3 or tags.get(0x106) != 2 or tags.get(0x103) != 1 or tags.get(0x128) != 1:
        raise ExportError(f"不是无压缩 interleaved RGB：{tags}")
    h, w = int(tags[0x101]), int(tags[0x100])
    at, nb = int(tags[0x111]), int(tags[0x117])
    if nb != w * h * 3 * 2:
        raise ExportError(f"strip 字节数 {nb} 与 {w}×{h}×3×2 对不上")
    return np.frombuffer(b[at:at + nb], dtype=np.uint16).reshape(h, w, 3)


def read_tiff16_icc(path: str) -> bytes | None:
    """从 write_tiff16 的产物里取回 ICCProfile 的字节（没有那么返回 None）。

    为什么不拿 Pillow 开一下看看 info 里有没有 icc_profile：那只能证明“有人读得懂”，
    证不了 tag 里的偏移指向的就是我递进去的那一段。本函数只按条目里的
    (type=7, count, offset) 把字节拼出来，给调用方逐字节比对——嵌错的 ICC 比不嵌更坏，
    所以“嵌对了”得能独立反查。
    """
    import struct
    with open(path, "rb") as f:
        b = f.read()
    ifd_at = struct.unpack_from("<I", b, 4)[0]
    n = struct.unpack_from("<H", b, ifd_at)[0]
    for i in range(n):
        o = ifd_at + 2 + i * 12
        tag, typ, cnt = struct.unpack_from("<HHI", b, o)
        if tag == _TIFF16_ICC_TAG:
            if typ != 7:
                raise ExportError(f"ICCProfile 条目 type 不是 UNDEFINED(7) 而是 {typ}")
            if cnt <= 4:                      # 短于 4 字节的值直放在条目里，不是偏移
                return b[o + 8: o + 8 + cnt] or None
            at = struct.unpack_from("<I", b, o + 8)[0]
            return b[at: at + cnt]
    return None


def _rgb16_readback_facts(reference: np.ndarray, actual: np.ndarray, *,
                          chunk_pixels: int = 1 << 18) -> dict:
    """Exact readback statistics with bounded temporary comparison/histograms.

    uint16 has only 65536 possible codes: accumulate presence histograms instead
    of sorting full channels. The source/readback arrays are still full-sized;
    this bounds verification temporaries, not the entire export working set.
    low8_nonzero_px retains its legacy name but counts RGB components, not pixels.
    """
    if actual.dtype != np.uint16 or actual.ndim != 3 or actual.shape[2] != 3:
        raise ValueError("readback statistics require (H,W,3) uint16")
    if reference.dtype != np.uint16:
        raise ValueError("readback reference must be uint16")
    budget = int(chunk_pixels)
    if budget <= 0:
        raise ValueError("chunk_pixels must be positive")
    h, w = actual.shape[:2]
    if not h or not w:
        raise ValueError("readback image must be nonempty")
    columns = min(w, budget)
    rows = max(1, budget // columns)
    present = np.zeros((3, 65536), dtype=bool)
    same_shape = reference.shape == actual.shape
    difference = 0 if same_shape else -1
    low8 = 0
    for y in range(0, h, rows):
        for x in range(0, w, columns):
            block = actual[y:y + rows, x:x + columns]
            if same_shape:
                delta = reference[y:y + rows, x:x + columns].astype(np.int32)
                np.subtract(delta, block, out=delta)
                np.abs(delta, out=delta)
                difference = max(difference, int(delta.max()))
            for c in range(3):
                present[c] |= np.bincount(block[..., c].reshape(-1), minlength=65536) > 0
            low8 += int(np.count_nonzero(block & 0xFF))
    return {"readback_max_diff": difference,
            "levels_per_channel": [int(np.count_nonzero(p)) for p in present],
            "low8_nonzero_px": low8}


def _write_verified_rgb16(arr, out_path, *, target_icc, conflict_policy,
                          metadata_include_gps, tiff_compression):
    info = write_tiff16(arr, out_path, output_profile="source" if target_icc else "none",
                        source_icc=target_icc, conflict_policy=conflict_policy,
                        metadata_include_gps=metadata_include_gps,
                        tiff_compression=tiff_compression)
    if info.get("skipped"):
        return {**info, "readback_max_diff": None, "levels_per_channel": None,
                "low8_nonzero_px": None, "readback_ms": 0.0, "verification_ms": 0.0,
                "icc_readback_bytes": None, "icc_readback_matches": None}
    t_wr = time.perf_counter()
    back = read_tiff16(info["path"])
    t_rd = time.perf_counter()
    facts = _rgb16_readback_facts(arr, back)
    icc_back = read_tiff16_icc(info["path"]) or b""
    icc_want = target_icc or b""
    t_verified = time.perf_counter()
    if facts["readback_max_diff"] != 0 or icc_back != icc_want:
        raise ExportError(
            f"16-bit 导出读回验证失败：像素最大差={facts['readback_max_diff']}，"
            f"ICC一致={icc_back == icc_want}。文件保留供检查，不作为成功出片：{info['path']}")
    return {**info, **facts, "icc_readback_bytes": len(icc_back),
            "icc_readback_matches": (icc_back == icc_want) if icc_want else None,
            "readback_ms": round((t_rd - t_wr) * 1000, 2),
            "verification_ms": round((t_verified - t_rd) * 1000, 2)}


def export_master_16bit(path: str, out_path: str, *, device: str | None = None,
                        output_profile: str = "srgb",
                        conflict_policy: str = "skip_and_report",
                        metadata_include_gps: bool = False,
                        tiff_compression: str = "none", verify_source=None) -> dict:
    """16-bit 母档直通导出：满幅解一次 → 写 16-bit TIFF → 读回逐字节自证。

    三个自证读数缺一个都不算“保真”：
    * readback_max_diff 必须 0（无损这一句得有人核对，不能只写在注释里）；
    * levels_per_channel 必须远大于 256（否则所谓 16-bit 其实只有 8-bit 的内容）；
    * low8_nonzero_px 必须 >0（防的是“8-bit 数据左移 8 位补零”那张假 16-bit 图：
      它位数看起来对、每通道取值也过 256 个，但低 8 位全是 0）。
    另外报 source（谁解的）：16-bit 只应该来自真解码那两支，预览那一支在这里必须拒。
    """
    from . import decode as D
    t0 = time.perf_counter()
    d = D.load_full(path, device=device, want_bits=16)
    if verify_source is not None: verify_source()  # Fence before any output publication.
    t_dec = time.perf_counter()
    arr = d.rgb
    src = (d.raw or {}).get("source")
    if arr.dtype != np.uint16:
        raise ExportError(f"这张图没有 16-bit 母档（解出来是 {arr.dtype}，source={src}）："
                          "16-bit 直通只对真带 16-bit 数据的 RAW 成立，"
                          "不拿 8-bit 左移补零冒充。要 8-bit 出片请用常规导出。")
    if (d.raw or {}).get("used_preview"):
        raise ExportError("16-bit 直通的像素来自相机内嵌预览（source=libraw_preview）："
                          "预览不参与出片这条分界不许在导出这一层破")
    ms = lambda a, b: round((b - a) * 1000.0, 2)      # noqa: E731
    target_icc = _profile_bytes(output_profile, d.source_icc)
    color_converted = False
    t_color = time.perf_counter()
    if target_icc:
        from .color16 import convert_rgb16
        # TIFF pixels retain their source encoding; LibRaw output is configured
        # as sRGB. No-profile RGB follows the same explicit sRGB assumption as
        # the normal input path. Conversion never stages through uint8.
        input_icc = d.source_icc or _srgb_bytes()
        color_converted = input_icc != target_icc
        arr = convert_rgb16(arr, input_icc, target_icc)
    color_ms = ms(t_color, time.perf_counter())
    info = _write_verified_rgb16(arr, out_path, target_icc=target_icc,
                                 conflict_policy=conflict_policy,
                                 metadata_include_gps=metadata_include_gps,
                                 tiff_compression=tiff_compression)
    return {**info, "src_w": d.src_w, "src_h": d.src_h, "src_format": d.fmt,
            "source": src, "bits": 16, "icc_source": str(output_profile),
            "color_converted": color_converted, "color_conversion_ms": color_ms,
            "decode_ms": ms(t0, t_dec), "total_ms": ms(t0, time.perf_counter()),
            "pipeline": "passthrough_rgb16", "notes": list(d.notes)}


def render_edited_rgb16(decoded, spec: ExportSpec, *, device: str = "cpu",
                        tile: int = DEFAULT_TILE, crop_rect=(0.0, 0.0, 1.0, 1.0),
                        rotation_degrees: float = 0.0, output_profile: str = "srgb",
                        progress=None):
    """Shared high-precision render/ICC path. Returns pixels, ICC and facts; no file IO."""
    creative_source = spec.creative_base is not None
    if not creative_source and (decoded.rgb.dtype != np.uint16 or (decoded.raw or {}).get("used_preview")):
        raise ExportError("16-bit 编辑需要真实 uint16 源，不接受8-bit显示代理")
    from .color16 import convert_rgb16
    working_icc = _srgb_bytes()
    target_icc = _profile_bytes(output_profile, decoded.source_icc)
    t_color = time.perf_counter()
    source = decoded.rgb
    input_converted = False
    if decoded.source_icc and not creative_source:
        source = convert_rgb16(source, decoded.source_icc, working_icc)
        input_converted = decoded.source_icc != working_icc
    input_color_ms = (time.perf_counter() - t_color) * 1000
    frame, render_stats = export_image16(source, spec, device=device, tile=tile,
                                         crop_rect=crop_rect, rotation_degrees=rotation_degrees, progress=progress)
    t_color = time.perf_counter()
    output_converted = bool(target_icc and target_icc != working_icc)
    if output_converted:
        frame = convert_rgb16(frame, working_icc, target_icc)
    color_ms = input_color_ms + (time.perf_counter() - t_color) * 1000
    return frame, target_icc, { "src_w": spec.creative_base['width'] if creative_source else decoded.src_w,
            "src_h": spec.creative_base['height'] if creative_source else decoded.src_h,
            "src_format": 'creative-linear-rgba-f32' if creative_source else decoded.fmt,
            "source": 'creative_composite' if creative_source else (decoded.raw or {}).get("source"),
            "bits": 16, "icc_source": str(output_profile),
            "color_converted": input_converted or output_converted,
            "color_conversion_ms": round(color_ms, 2),
            "render_stats": render_stats, "pipeline": "float32_rgb16",
            "working_color_space": "sRGB", "decoded_bits": 32 if creative_source else 16,
            # LibRaw output_bps describes the developed RGB, not the sensor file bit depth.
            "source_bits": (int(decoded.src_bits)
                            if (decoded.raw or {}).get("source") in (None, "tiff16") else None),
            "notes": list(decoded.notes) + (["创意合成原件以完整float32输入编辑；仅最终编码为RGB16，未使用显示代理"] if creative_source else ["真实RGB16源经float32或更高精度编辑；显示uint8缓冲不作为导出输入"])}


def export_edited_16bit(decoded, spec: ExportSpec, out_path: str, *,
                         device: str = "cpu", tile: int = DEFAULT_TILE,
                         crop_rect=(0.0, 0.0, 1.0, 1.0), rotation_degrees: float = 0.0,
                         output_profile: str = "srgb", conflict_policy: str = "skip_and_report",
                         metadata_include_gps: bool = False, tiff_compression: str = "none",
                         decode_ms: float = 0.0) -> dict:
    """Decoded true RGB16 -> working sRGB -> float edits/geometry -> RGB16 TIFF.

    Source and destination ICC conversion use RGB16 LittleCMS, never Pillow RGB8.
    Display proxy bytes are not accepted as source data. This does not establish
    scene-linear HDR, wide-gamut editing, GPU quality, or an unlimited RAM budget.
    """
    decode_ms = float(decode_ms)
    if not math.isfinite(decode_ms) or decode_ms < 0:
        raise ExportError("decode_ms 必须是有限非负数")
    t0 = time.perf_counter()
    frame, target_icc, facts = render_edited_rgb16(
        decoded, spec, device=device, tile=tile, crop_rect=crop_rect,
        rotation_degrees=rotation_degrees, output_profile=output_profile)
    info = _write_verified_rgb16(frame, out_path, target_icc=target_icc,
                                 conflict_policy=conflict_policy,
                                 metadata_include_gps=metadata_include_gps,
                                 tiff_compression=tiff_compression)
    return {**info, **facts, "decode_ms": decode_ms,
            "total_ms": round(decode_ms + (time.perf_counter() - t0) * 1000, 2)}
