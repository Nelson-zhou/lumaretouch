"""真实图 → 预览代理帧：解码 + 按字节预算降采样。

两条从实测里长出来的规矩：
1. **代理档按像素总数定，不按长边定。** M1-1/M1-2 钉死的是「每帧字节」这个因子：
   960×600 = 576 kpx = 2.30 MB/帧 是实测 0 撞帧的点。竖构图如果按"长边 960"缩会得到
   768×960 = 2.95 MB，正好压在 3.3 MB 阈值边上——同一套代码在不同构图下落在不同的
   稳定性区间，是最难查的那种抖动。所以这里锁像素预算，构图只改长宽比。
2. **降采样在解码侧做，不把全尺寸图灌进显存再缩。** 12 MP 的 RGBA 是 51 MB/帧，shm 与
   D2H 都会当场被吃掉；预览要的是代理帧，精帧只在松手后按需出。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

# 与 M1-1/M1-2 实测点等像素：960×600 → 2.30 MB/帧（RGBA）
PROXY_PIXELS = 960 * 600
# 预算的上/下限：这个值直接决定 /dev/shm 大小与显存分配量，不能由调用方任意抬。
# shm 写满 tmpfs 是 SIGBUS 硬死，不是可报错的异常。
MIN_BUDGET = 64 * 64
MAX_BUDGET = 8_000_000          # ≈30.5 MB/帧，单帧上限，给精帧通道留余量
ALIGN = 8                       # 缩放后边长取 8 的倍数：对齐纹理块，也避开奇数边的半像素
EXIF_ORIENTATION = 0x0112
SWAPPED_ORIENTATIONS = {5, 6, 7, 8}     # 这几个方向值会把宽高对调


def clamp_budget(budget: int) -> int:
    """把外部传进来的像素预算接到合理区间（超限直接报错，不默默夹——夹了就不诚实）。"""
    b = int(budget)
    if not (MIN_BUDGET <= b <= MAX_BUDGET):
        raise ValueError(f"代理预算 {b} 越界（允许 {MIN_BUDGET}~{MAX_BUDGET} 像素）")
    return b


def proxy_size(w: int, h: int, budget: int = PROXY_PIXELS) -> tuple[int, int]:
    """保持长宽比缩到 budget 像素以内。小图原样返回（不放大、不重采样）。

    向下取整到 ALIGN 的倍数，所以 ow·oh ≤ (w·k)(h·k) = budget，天然不会越预算，
    不需要"超了就退一步"的循环。
    """
    if w <= 0 or h <= 0:
        raise ValueError(f"非法尺寸 {w}x{h}")
    if w * h <= budget:
        return w, h
    k = (budget / float(w * h)) ** 0.5
    ow = max(ALIGN, int(w * k) // ALIGN * ALIGN)
    oh = max(ALIGN, int(h * k) // ALIGN * ALIGN)
    if ow * oh > budget:        # 只可能在极小图 + 极小预算的组合下出现，兜底一次
        ow = max(ALIGN, ow - ALIGN)
        oh = max(ALIGN, oh - ALIGN)
    return ow, oh


@dataclass
class Decoded:
    """一次导入的产物：代理尺寸 RGB 与逐项耗时（ms）。"""
    rgb: np.ndarray                 # (h, w, 3) uint8，连续
    src_w: int                      # 已按 EXIF 方向摆正的源尺寸
    src_h: int
    fmt: str
    t_open_ms: float
    t_decode_ms: float
    t_orient_ms: float
    t_scale_ms: float
    t_total_ms: float
    draft_used: bool = False
    draft_size: tuple[int, int] | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def w(self) -> int:
        return int(self.rgb.shape[1])

    @property
    def h(self) -> int:
        return int(self.rgb.shape[0])

    def meta(self) -> dict:
        return {
            "src_w": self.src_w, "src_h": self.src_h, "w": self.w, "h": self.h,
            "format": self.fmt, "draft": self.draft_used, "draft_size": list(self.draft_size) if self.draft_size else None,
            "open_ms": round(self.t_open_ms, 2), "decode_ms": round(self.t_decode_ms, 2),
            "orient_ms": round(self.t_orient_ms, 2), "scale_ms": round(self.t_scale_ms, 2),
            "total_ms": round(self.t_total_ms, 2),
            "bytes_per_frame": self.w * self.h * 4, "notes": self.notes,
        }


def load_rgb(path: str, budget: int = PROXY_PIXELS) -> Decoded:
    """解码 Pillow 认得的图（M1-3a 只承诺 JPEG/PNG），返回代理尺寸 RGB。

    两个容易踩的点，都在这函数里处理掉了：
    * **EXIF 方向**：手机竖拍常常是「横图 + orientation=6」，不转就会横着上屏。方向值
      要先读出来，才能算对代理档的宽高，也才能给 libjpeg 正确的 draft 目标。
    * **不禁用解压炸弹保护**：Pillow 的 MAX_IMAGE_PIXELS 保持默认，超大像素数会抛
      DecompressionBombError，这是我们要的行为。
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图片不存在或不是普通文件: {path}")
    budget = clamp_budget(budget)
    ms = lambda a, b: (b - a) * 1000.0
    t0 = time.perf_counter()
    with Image.open(path) as im:
        fmt = im.format or "?"
        raw_w, raw_h = im.size
        orient = int(im.getexif().get(EXIF_ORIENTATION, 1) or 1)
        swap = orient in SWAPPED_ORIENTATIONS
        src_w, src_h = (raw_h, raw_w) if swap else (raw_w, raw_h)   # 摆正后的尺寸
        pw, ph = proxy_size(src_w, src_h, budget)
        # JPEG 的 DCT 缩放：libjpeg 能直接解出 1/2、1/4、1/8 尺寸。候选档是按**存储态**
        # 宽高算的（要两维都 ≥ 目标才选那一档），所以目标尺寸必须传回存储态方向：
        # 拿摆正后的 (pw,ph) 去请求竖构图，会把可用档拉低一级。实测 4000×3000 + orientation=6：
        # 传 (656,872) 只降到 1/2（解码 12.07 ms），传 (872,656) 能降到 1/4（6.43 ms）。
        draft_to = im.draft("RGB", (ph, pw) if swap else (pw, ph)) if fmt == "JPEG" else None
        t_d = time.perf_counter()
        im.load()
        t_o = time.perf_counter()
        if orient != 1:
            im = ImageOps.exif_transpose(im)          # 无 EXIF 时是空操作
        t_s = time.perf_counter()
        if im.mode != "RGB":
            im = im.convert("RGB")                    # 灰度/调色板/带 alpha 都先落到 RGB
        if im.size != (pw, ph):                       # draft 只能给到近似尺寸，补最后一步
            im = im.resize((pw, ph), Image.LANCZOS)
        arr = np.ascontiguousarray(np.asarray(im, dtype=np.uint8))
    t1 = time.perf_counter()
    assert arr.shape == (ph, pw, 3) and arr.dtype == np.uint8, "解码输出布局不符约定"
    # im.draft() 返的是 (mode, (x0, y0, x1, y1))，不是尺寸元组。把它直接和 (raw_w, raw_h)
    # 比会永远“不等”→ draft_used 恒为 True，报表上每一张都写着“已吃到 DCT 缩放”。
    # 真缩放与否只能看返回 box 的实际宽高。
    draft_size: tuple[int, int] | None = None
    if isinstance(draft_to, tuple) and len(draft_to) == 2 and isinstance(draft_to[1], (tuple, list)):
        x0, y0, x1, y1 = draft_to[1]
        draft_size = (int(round(x1 - x0)), int(round(y1 - y0)))
    d = Decoded(rgb=arr, src_w=src_w, src_h=src_h, fmt=fmt,
                t_open_ms=ms(t0, t_d), t_decode_ms=ms(t_d, t_o), t_orient_ms=ms(t_o, t_s),
                t_scale_ms=ms(t_s, t1), t_total_ms=ms(t0, t1),
                draft_used=bool(draft_size and draft_size != (raw_w, raw_h)),
                draft_size=draft_size)
    if d.draft_used:
        d.notes.append(f"libjpeg DCT 预缩到 {draft_size[0]}×{draft_size[1]}")
    if (src_w, src_h) == (pw, ph):
        d.notes.append("源图已在代理档以内，未缩放")
    if swap:
        d.notes.append(f"按 EXIF orientation={orient} 摆正过宽高")
    return d
