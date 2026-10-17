"""M4 全尺寸分块导出：把预览那条链按 tile 切块跑满幅，显存峰值只随 tile 走。

为什么必须分块（`gpuspike/m4a.py` A 组实测，RX 7600 XT 16 GiB）：整幅一次跑的峰值
**约 84 MiB / 每 MB 源图**——2.1 MB 要 209 MiB，33.3 MB 要 2 786 MiB，而 71.4 MB
（6000×3968）直接 HIP OOM（"Tried to allocate 4.26 GiB"）。预览靠代理档把这件事躲掉了，
导出没有"代理"可躲：用户要的就是那 2400 万像素。分块之后峰值只由 tile 面积决定
（D 组：2150 宽与 6000 宽的 tile512 峰值同为 125.3 MiB），这才是"防爆显存"的实证口径。两笔不在这条口径里，各自单独记账
（`packaging/m4-export-bench.py` 第 5 节）：形变场按行带求值，峰值只随 `_FIELD_BAND_PX`
走，代价是场按整幅活在系统内存；消除笔按洞的 bbox 满幅预跑，峰值随 bbox 走（切 tile
去解它会换掉 levels 与 bbox，那才是真的错）。

margin 从哪来（`m4a2.py` 逐参数定点验证，不是推算）：
    分带     blur=box(rf) → low1=guided(blur, r) → base=guided(low1, 2r)
             每层 box 跨 2r，所以支撑 = 2·rf + 6·r
    修容     box(db_radius) → 2·r_db
    形变     warp 采样的位移 + 双线性那一脚 → ceil(peak|delta|) + 1
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

import math
import os
import time
from dataclasses import dataclass, field

import numpy as np

try:
    import torch
except Exception:                    # 与 ops.* 同一约定：没装 torch 也要能 import
    torch = None

from .ops.deform import (analytic_frontal_landmarks, controls, face_frame,
                         support_radii, tps_field_from_state, tps_solve)
from .ops.grade import GradeError, check_params
from .ops.inpaint import hole_extent, levels_for, mask_bbox, inpaint_t, crop_apply_t
from .ops.lut import DEFAULT_LUT_AMOUNT, LutError, check_amount
from .ops.upscale import Plan as UpscalePlan
from .ops.upscale import check_scale, unsharp_bands_np
from .vram import LightOp, PreviewPipeline, RepairOp

DEFAULT_TILE = 1024
MIN_TILE = 256
MAX_TILE = 4096
# margin 的上限：它按公式算出来是"支撑有多宽"，但如果一个参数把支撑推到比 tile 还大，
# 分块就没有意义了（每块的有效区是负的）。这时当场拒绝，而不是默默出一个糊图。
MAX_MARGIN = 2048
# 形变场的逐带求值预算（像素数）。拿它除以图宽得到带高，于是带的显存量按这个常数走
# 而不是按图幅走。稠密求值的开销量在 (像素数 × 控制点数) 的 float64 U 矩阵上，所以
# 这一笔比看上去的大：1<<15 在 100 个控制点上是 ≈26 MiB（实测），而 1<<18 要 234 MiB，
# 会把整幅求值变成峰值的主人（那正是小块 tile 分块的意义被顶掉）。
_FIELD_BAND_PX = 1 << 15

FORMATS = ("jpg", "jpeg", "png", "tif", "tiff", "webp")
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
    # 放大（M7）：输出倍率与出片锐化。为什么不在预览会话里做而在导出做：预览的
    # 幅面是代理档（屏幕就这么大），用户要的 2×/4× 只在出片那一刻存在。
    scale: int = 1
    upscale_backend: str = "lanczos3"
    sharpen_amount: float = 0.0
    sharpen_radius: int = 2
    sharpen_threshold: float = 0.01

    def check(self) -> None:
        """参数在进入昂贵通路之前先过一遍唯一校验口径（与各层 setter 同源）。"""
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

    # ---- margin：由参数算，不是量出来一个数写死 ----
    def margin_px(self, deform_peak_px: float = 0.0) -> int:
        m = max(2 * int(self.texture_radius) + 6 * int(self.radius),
                2 * int(self.light_radius) if self.light else 0)
        if deform_peak_px:
            m += int(math.ceil(deform_peak_px)) + 1
        # 放大要的是 Lanczos 的支撑半径：补丁得比目标框四周多包 a 个源像素，
        # 否则抽头越出补丁——那不是近似，是拿不存在的数据编值
        if int(self.scale) > 1:
            m = max(m, UpscalePlan.margin_for(int(self.scale)))
        return m


def tile_rects(h: int, w: int, tile: int) -> list:
    """有效区矩形（不含 margin）。最后一块允许变小，不重复覆盖也不留缝。"""
    t = int(tile)
    if not (MIN_TILE <= t <= MAX_TILE):
        raise ExportError(f"tile={tile} 越界（允许 {MIN_TILE}~{MAX_TILE}）")
    return [(y0, min(y0 + t, h), x0, min(x0 + t, w))
            for y0 in range(0, h, t) for x0 in range(0, w, t)]


class _MaskCarrier:
    """给 PreviewPipeline.load_face 用的最小载体：导出器没有 precompute 对象，只有数组。

    为什么不直接塞 `masks_gpu`：`load_face` 里那两条"字节必须与原件等量"的校验是这个
    仓库对跨设备张量唯一的抓手，绕开它等于自己重写一遍校验。
    """

    def __init__(self, arr, landmarks):
        self._arr = np.ascontiguousarray(arr, dtype=np.float32)
        self.landmarks = np.ascontiguousarray(landmarks, dtype=np.float32)

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


def apply_repair_full(src_u8: np.ndarray, ops: list, device: str):
    """消除笔在**满幅**上按洞的 bbox 逐笔跑一次，返回 (H,W,3) float32 底图。

    为什么不在 tile 里跑：inpaint 是多尺度求解（`levels_for(hole_extent, box_h, box_w)`
    按洞的 bbox 定层数），tile 一切就把洞切碎，层数与 bbox 都变了——那不是一个能用
    margin 修好的边界效应。而它天生只需要洞周围那一圈，本来就不贵。
    与 `PreviewPipeline._commit_repair` 同一条重放顺序与同一批算子（逐笔而不是并集：
    并集会让第二笔的周围含上第一笔的旧坑）。
    """
    h, w = src_u8.shape[:2]
    for op in ops:
        if not isinstance(op, RepairOp):
            raise ExportError(f"消除笔图层必须是 RepairOp，得到 {type(op).__name__}："
                              "weight 需是导出尺寸的 (H,W) uint8")
    arr = np.ascontiguousarray(src_u8.transpose(2, 0, 1))[None]
    cur = torch.from_numpy(arr).to(device).to(torch.float32).div_(255.0)
    boxes = []
    t0 = time.perf_counter()
    for op in ops:
        wsub_np = op.weight.astype(np.float32) / 255.0
        if wsub_np.shape[:2] != (h, w):
            raise ExportError(f"消除笔掩膜尺寸 {wsub_np.shape[:2]} != 导出尺寸 {(h, w)}")
        p = dict(op.params)
        box = mask_bbox(wsub_np, pad=int(p.get("pad", 32)), grow=float(p.get("grow", 1.5)))
        if box is None:
            continue
        y0, y1, x0, x1 = box
        lv = levels_for(hole_extent(wsub_np), y1 - y0, x1 - x0)
        sub = cur[..., y0:y1, x0:x1]
        wsub = torch.from_numpy(np.ascontiguousarray(wsub_np[None, None, y0:y1, x0:x1])).to(device)
        fill = inpaint_t(sub, wsub, levels=lv,
                         smooth_iters=int(p.get("smooth_iters", 1)),
                         refine_iters=int(p.get("refine_iters", 6)),
                         kappa=float(p.get("kappa", 0.06)))
        cur = crop_apply_t(cur, box, fill)
        boxes.append([int(v) for v in box])
    ms = (time.perf_counter() - t0) * 1000.0
    out = cur[0].permute(1, 2, 0).cpu().numpy().astype(np.float32)
    del cur
    if torch.cuda.is_available() and str(device).startswith("cuda"):
        torch.cuda.empty_cache()
    if not np.isfinite(out).all():
        raise ExportError("消除笔满幅结果含非有限值，已拒绝进入导出")
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
                 tile: int = DEFAULT_TILE, progress=None) -> tuple:
    """满幅分块导出。返回 ((H,W,3) uint8, 账单 dict)。

    progress 每块回调一次 (done, total, tile_ms)，批量导出靠它算百分比。
    """
    if src_u8.ndim != 3 or src_u8.shape[2] != 3 or src_u8.dtype != np.uint8:
        raise ExportError(f"导出要 (H,W,3) uint8，得到 {src_u8.shape} {src_u8.dtype}")
    spec.check()
    # 纯校验全部排在 torch 守卫之前：没装 torch 的环境也要拿到同一句参数拒绝，
    # 而不是先被"导出需要 torch"抢掉——那样 CI 的 CPU job 根本测不到这些分支。
    h, w = src_u8.shape[:2]
    rects = tile_rects(h, w, tile)
    if spec.margin_px(0.0) > MAX_MARGIN:
        # 不需要 torch 就能算出来的那一半：半径把作用面撑爆这件事与有没有 GPU 无关
        raise ExportError(f"这组参数的作用面宽到 margin={spec.margin_px(0.0)} px"
                          f"（超过 {MAX_MARGIN}），换更大的 tile 或调小磨皮/修容半径")
    if torch is None:
        raise ExportError("导出需要 torch（装 rocm/cuda/cpu 任一变体）")
    delta, peak = (None, 0.0)
    field_ms = 0.0
    if spec.deform_amounts:
        t_f = time.perf_counter()
        delta, peak = composed_delta(spec.landmarks, spec.deform_amounts, h, w, device)
        field_ms = (time.perf_counter() - t_f) * 1000.0
    margin = spec.margin_px(peak)
    if margin > MAX_MARGIN:
        raise ExportError(f"这组参数的作用面宽到 margin={margin} px（超过 {MAX_MARGIN}），"
                          "换更大的 tile 或调小磨皮/修容半径")
    base_f = None
    repair_stats = {}
    if spec.repair:
        base_f, repair_stats = apply_repair_full(src_u8, spec.repair, device)
    if spec.channel is not None and base_f is not None:
        # load_face 要求会话持有原始像素（掩膜尺寸对得上才能挂），而 float 底图那条形
        # 式下 src_u8 是 None。与其在那里抛一句与导出无关的 RuntimeError，不如在这里
        # 说清楚：这一对组合本轮没做，不是默默降级成不分通道。
        raise ExportError("分通道导出还不接受满幅消除笔底图（掩膜装载需要原始像素）："
                          "请分开通道与消除笔，或等这条通路补齐")
    scale = int(spec.scale)
    plan = UpscalePlan(h, w, scale)          # 表只算一次，每块取自己那一段
    out_h, out_w = plan.out_h, plan.out_w
    out = np.zeros((out_h, out_w, 3), np.uint8)
    seg = {"filter": 0.0, "light": 0.0, "deform": 0.0, "lut": 0.0, "grade": 0.0}
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
        pipe = PreviewPipeline(device, tw, th)
        if base_f is not None:
            pipe.load_rgb_f32(np.ascontiguousarray(base_f[cy0:cy1, cx0:cx1]))
        else:
            pipe.load_rgb_u8(src_u8[cy0:cy1, cx0:cx1])
        t_c = time.perf_counter()
        io["setup"] += (t_c - t0) * 1000.0
        if spec.light:
            sub = _crop_ops(spec.light, (cy0, cx0, cy1, cx1), LightOp)
            if sub:
                # 先挂笔迹再改参数：set_light_params 自己会把两份 db 缓存作废，
                # 导出器不该去碰那几个字段（“能只改两条的三条状态”是 M2 审过的病）
                pipe.set_light_ops(sub)
                pipe.set_light_params(spec.light_exposure, spec.light_radius)
        if delta is not None and spec.deform_amounts:
            pipe.adopt_deform_field(delta[:, cy0:cy1, cx0:cx1].contiguous().to(device))
        if spec.cube is not None:
            pipe.set_lut(spec.cube, spec.lut_amount)
        if spec.grade != (0.0, 0.0, 0.0, 1.0):
            pipe.set_grade(*spec.grade[:3], amount=spec.grade[3])
        if spec.channel is not None and spec.masks is not None:
            carrier = _MaskCarrier(spec.masks[:, cy0:cy1, cx0:cx1], spec.landmarks)
            carrier._carrier_names = list(spec.mask_names)
            pipe.load_face(carrier)
        pipe.render(spec.strength, radius=spec.radius, eps=spec.eps,
                    detail_gain=spec.detail_gain, mid_gain=spec.mid_gain,
                    broad_gain=spec.broad_gain, texture_radius=spec.texture_radius,
                    channel=spec.channel if spec.masks is not None else None)
        t_r = time.perf_counter()
        got = pipe.read_back()[..., :3]
        if scale == 1:
            out[y0:y1, x0:x1] = got[y0 - cy0:y1 - cy0, x0 - cx0:x1 - cx0]
        else:
            # 把本块有数区渲染结果按全局权重表放大到输出坐标里对应那一段。
            # 不是"先拼整幅再放大"——那会把峰值从 tile 拉回图幅；也不比 0：
            # 同一串 (下标, 权重) 同一累加顺序，与整幅 `plan.full` 逐字节同一
            t_u = time.perf_counter()
            out[y0 * scale:y1 * scale, x0 * scale:x1 * scale] = plan.region(
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
    ms = (time.perf_counter() - t_all) * 1000.0
    sharpen_ms = 0.0
    if float(spec.sharpen_amount) > 0.0:
        # 出片锐化排在放大之后、且切的是已经完整的输出图：带 halo 拿真像素，
        # 只有图的真边缘才用 replicate——所以与整图直锐逐字节同一，不拿近似当默认
        t_s = time.perf_counter()
        out = unsharp_bands_np(out, radius=float(spec.sharpen_radius),
                               amount=float(spec.sharpen_amount),
                               threshold=float(spec.sharpen_threshold))
        sharpen_ms = (time.perf_counter() - t_s) * 1000.0
    peak_bytes = int(delta.numel() * 4) if delta is not None else 0
    return out, {
        "w": out_w, "h": out_h, "px": out_w * out_h, "src_mb": round(h * w * 3 / 1e6, 2),
        "src_w": w, "src_h": h, "scale": scale,
        "upscale_backend": spec.upscale_backend if scale > 1 else None,
        "upscale_ms": round(upscale_ms, 2), "sharpen_ms": round(sharpen_ms, 2),
        "sharpen_amount": float(spec.sharpen_amount),
        "tile": int(tile), "tiles": len(rects), "margin_px": int(margin),
        "deform_peak_px": round(peak, 3), "total_ms": round(ms, 1),
        "field_ms": round(field_ms, 1),
        "per_tile_ms": round(ms / max(len(rects), 1), 2),
        "seg_ms": {**{k: round(v, 2) for k, v in seg.items()},
                   **{k: round(v, 2) for k, v in io.items()}},
        "delta_cpu_mb": round(peak_bytes / 2**20, 1),
        "channel": spec.channel, **repair_stats,
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


def write_file(rgb: np.ndarray, path: str, *, quality: int = 95) -> dict:
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
    from PIL import Image                         # 校验完了才碰编码器：拒绝不需要 PIL
    t0 = time.perf_counter()
    img = Image.fromarray(np.ascontiguousarray(rgb), "RGB")
    kw = {}
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
        kw["compression"] = "tiff_lzw"
    img.save(path, **kw)
    ms = (time.perf_counter() - t0) * 1000.0
    return {"path": path, "format": ext, "bytes": os.path.getsize(path),
            "write_ms": round(ms, 1), "quality": int(quality),
            # PNG 实际用的压缩档位（其他格式为 None，不缺键）：回报里写 quality=95
            # 而文件是按 level 6 写的，两者对不上时必须看得出来，否则写盘耗时
            # 与体积就成了无从反推的谜
            "compress_level": kw.get("compress_level")}
