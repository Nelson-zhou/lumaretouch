"""帧生成：M0 用合成帧跑通路，M1 换成真实解码输出。"""

from __future__ import annotations

import numpy as np


def synthetic(w: int, h: int, phase: float) -> np.ndarray:
    """横向渐变 + 一条随 phase 移动的高对比带 + 四角定位块。

    选这个图形的理由：渐变能暴露量化/色带，移动带能在不做像素比对的情况下
    靠肉眼确认「画面真的在动」，四角块确认没有上下翻转（Linux 与 WebKit 的
    纹理原点不同，这个坑一定会踩）。
    """
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    base = (0.25 + 0.65 * x) * (0.6 + 0.4 * y)

    band_center = ((phase * 0.35) % 1.2 - 0.1) * w
    dist = np.abs(np.arange(w, dtype=np.float32)[None, :] - band_center)
    band = np.exp(-(dist / (w * 0.02)) ** 2) * (1.0 - y)

    img = np.clip(base + band, 0.0, 1.0)
    rgb = np.stack([img, img * 0.85 + 0.1 * y, img * 0.7 + 0.25 * y], axis=-1)

    out = (np.clip(rgb, 0, 1) * 255.0).astype(np.uint8)
    k = max(8, min(w, h) // 24)
    for r, c in ((0, 0), (0, w - k), (h - k, 0), (h - k, w - k)):
        out[r:r + k, c:c + k] = (255, 0, 0) if (r == 0 and c == 0) else (0, 255, 255)
    return out


_RGBA_CACHE: dict[tuple[int, int], np.ndarray] = {}


def test_frame(w: int, h: int, seq: int) -> np.ndarray:
    """跑靶用测帧：整帧内容按尺寸只生成一次，每帧只改写左上角的序号色块。

    理由是通路测量与画面内容无关：上一版每帧重算合成图形，1280x800 要 17.7 ms，
    直接变成引擎侧 40 fps 的假瓶颈，把显示通路的真实成本遮掉了。
    序号色块保证「帧真的在换」仍可被肉眼和像素比对证实，而每帧仍然完整
    写 4~10 MB 进共享内存，被测路径一点没少。
    """
    buf = _RGBA_CACHE.get((w, h))
    if buf is None:
        rgb = synthetic(w, h, 0)
        buf = np.empty((h, w, 4), dtype=np.uint8)
        buf[:, :, :3] = rgb
        buf[:, :, 3] = 255
        _RGBA_CACHE[(w, h)] = buf
    s = seq & 0xFF
    # 16x16 块的蓝色通道逐帧轮转：旧帧没刷到新帧时一眼就能看出来
    buf[16:32, 16:32, 2] = s
    buf[16:32, 16:32, 0] = 255 - s
    return buf
