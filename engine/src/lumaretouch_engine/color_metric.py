"""色度度量：sRGB(8-bit) → CIELab → CIEDE2000（工程上判"色差"的唯一实现）。

为什么要有这一份而不是"看着差不多"：ADR-0003 把色彩链的质量门禁冻结成
**ΔE00 ≤ 2.0** 这一条数字，而仓库里此前没有任何一处真的算过它——阈值写进了决策文档，
测量却没人实现，等于那条门禁一直是纸面的。本模块把"能判"补上，供
`engine/tests/test_portrait_skin_quality.py`（PORTRAIT-002 的自动化那半）与色彩回归使用。

口径（全部按公开标准，不自创）：
• sRGB → 线性 → XYZ：d65 原点、IEC 61966-2-1 的分段传输函数；
• XYZ → Lab：CIELAB 1976，白点取 D65（sRGB 的白点本身就是 D65，不另换）；
• ΔE00：Sharma 等人的 CIEDE2000 公式（带 RT 旋转项），实现为 numpy 逐像素向量化。
  τ 那一项的 30° 指数、G 的 25 次方项这些常数全部按原文写死，不做"近似版"：
  ΔE 的判据就是那一条数字，近似一处整条门禁就没意义了。

只接 uint8 的 RGB/RGBA 图：这一层是用来**验收画面**的，输入必须是屏幕上真出来的那一版像素，
不是引擎内部的 float——拿 float 判会把"看不看得出的差"算成"数学上的差"。
"""
from __future__ import annotations

import numpy as np

D65_XYZ = np.array([95.047, 100.0, 108.883], dtype=np.float64)
# sRGB 传输函数（IEC 61966-2-1）写成形如它原文的那两个常数，不先除再乘：
# 上一版这里写的是 (c + 0.055/12.92) / (1 - 0.055/12.92)，看着像“归一化”，
# 实际上把整条曲线偏了一个常数（Lab 会错到 ΔE 看得出来的量）。
_SRGB_GAMMA = 2.4
_SRGB_BREAK = 0.04045
_SRGB_SCALE = 12.92
_SRGB_OFFSET = 0.055
_SRGB_DENOM = 1.055

_RGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
], dtype=np.float64)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """(...,3) 的 uint8（或 0..255 的 float）→ (...,3) 的 Lab float64。"""
    a = np.asarray(rgb, dtype=np.float64)
    if a.shape[-1] != 3:
        raise ValueError(f"要的是 (…,3) 的 RGB，得到 {a.shape}")
    c = a[..., :3] / 255.0
    lin = np.where(c <= _SRGB_BREAK, c / _SRGB_SCALE,
                   ((c + _SRGB_OFFSET) / _SRGB_DENOM) ** _SRGB_GAMMA)
    xyz = lin @ _RGB_TO_XYZ.T * 100.0
    t = xyz / D65_XYZ
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(t > eps, np.cbrt(t), (kappa * t + 16.0) / 116.0)
    L = 116.0 * f[..., 1] - 16.0
    a_ = 500.0 * (f[..., 0] - f[..., 1])
    b_ = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a_, b_], axis=-1)


def delta_e00(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """逐像素 CIEDE2000（kL=kC=kH=1，标准图形评估条件）。输入是 `srgb_to_lab` 的形状。"""
    x, y = np.asarray(lab1, dtype=np.float64), np.asarray(lab2, dtype=np.float64)
    if x.shape != y.shape or x.shape[-1] != 3:
        raise ValueError(f"两幅 Lab 的形状必须一致且最后一维是 3：{x.shape} vs {y.shape}")
    L1, a1, b1 = x[..., 0], x[..., 1], x[..., 2]
    L2, a2, b2 = y[..., 0], y[..., 1], y[..., 2]

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cb = (C1 + C2) / 2.0
    Cb7 = Cb ** 7
    G = 0.5 * (1.0 - np.sqrt(Cb7 / (Cb7 + 25.0 ** 7)))
    a1p, a2p = (1.0 + G) * a1, (1.0 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180.0, dhp - 360.0, dhp)
    dhp = np.where(dhp < -180.0, dhp + 360.0, dhp)
    dHp = 2.0 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2.0))

    Lbp = (L1 + L2) / 2.0
    Cbp = (C1p + C2p) / 2.0
    hbp = h1p + h2p
    hbp = hbp / 2.0
    # 平均色相：两边跨度超过 180° 时要把那一侧加 360 再取中（Sharma 原文的分支）。
    far = np.abs(h1p - h2p) > 180.0
    sum_lt_360 = (h1p + h2p) < 360.0
    hbp = np.where(far & sum_lt_360, hbp + 180.0, hbp)
    hbp = np.where(far & ~sum_lt_360, hbp - 180.0, hbp)

    T = (1.0 - 0.17 * np.cos(np.radians(hbp - 30.0))
         + 0.24 * np.cos(np.radians(2.0 * hbp))
         + 0.32 * np.cos(np.radians(3.0 * hbp + 6.0))
         - 0.20 * np.cos(np.radians(4.0 * hbp - 63.0)))
    d_theta = 30.0 * np.exp(-(((hbp - 275.0) / 25.0) ** 2))
    Cbp7 = Cbp ** 7
    RC = 2.0 * np.sqrt(Cbp7 / (Cbp7 + 25.0 ** 7))
    SL = 1.0 + (0.015 * (Lbp - 50.0) ** 2) / np.sqrt(20.0 + (Lbp - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cbp
    SH = 1.0 + 0.015 * Cbp * T
    RT = -np.sin(np.radians(2.0 * d_theta)) * RC

    return np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2
                   + RT * (dCp / SC) * (dHp / SH))


def de00_of_rgb(rgb1: np.ndarray, rgb2: np.ndarray) -> np.ndarray:
    """两幅 uint8 RGB 的逐像素 ΔE00（最常用的入口）。"""
    return delta_e00(srgb_to_lab(rgb1), srgb_to_lab(rgb2))


def de00_stats(rgb1: np.ndarray, rgb2: np.ndarray, mask: np.ndarray | None = None) -> dict:
    """ΔE00 的 mean / p50 / p95 / max。`mask` 是布尔图（判哪一片像素）。

    报中位数与 p95 而不是只报均值：磨皮这类"大多数像素没动、少数动得厉害"的操作，
    均值会被摊薄成一个好看的数，而用户看见的恰好是那少数像素。
    """
    d = de00_of_rgb(rgb1, rgb2)
    if mask is not None:
        m = np.asarray(mask, dtype=bool)
        if not m.any():
            raise ValueError("mask 里没有 True：一片都不判的测量没有意义")
        d = d[m]
    d = np.asarray(d, dtype=np.float64).ravel()
    return {"n": int(d.size), "mean": round(float(d.mean()), 4),
            "p50": round(float(np.percentile(d, 50)), 4),
            "p95": round(float(np.percentile(d, 95)), 4),
            "max": round(float(d.max()), 4)}


def high_pass_energy(rgb: np.ndarray) -> np.ndarray:
    """逐像素高频能量（4 邻域拉普拉斯的绝对值，灰度上算）。

    用它判"蜡像感"：磨皮把高频压平之后，剩下的纹理能量就是这一项。核与归一都写死，
    不在两处用不同的核——两处的"高频"必须是同一个定义。
    """
    a = np.asarray(rgb, dtype=np.float64)[..., :3].mean(axis=-1)
    lap = (4.0 * a
           - np.roll(a, 1, axis=0) - np.roll(a, -1, axis=0)
           - np.roll(a, 1, axis=1) - np.roll(a, -1, axis=1))
    return np.abs(lap)
