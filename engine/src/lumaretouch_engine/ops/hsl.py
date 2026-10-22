"""八色 HSL：按色相分段改「色相 / 饱和度 / 明亮度」，逐点、无位置、无掩膜。

为什么与 `tone.py` 分开：影调四项是**整图统一**的曲线，八色 HSL 是**按颜色分段**
的窗口变换（红/橙/黄/绿/青/蓝/紫/洋红各一组）。两者都挂在曝光层里（见
`ops/exposure.py` 的链上位置），但核算是两件事：把它们塞进同一个函数会让
“改一个橙色滑块”读到整幅的对比度算式，量一次就要拆一次。

口径（原创扩展，注册在 registry-extensions.json；像素算法保持兼容）：
  · UI 沿用“八色 HSL”名称，实际计算空间是 HSV，不是真 HSL；
  · 八个色相中心：0/30/60/120/180/240/280/320 度；权重是围绕中心的 smoothstep 窗，
    半宽 45°，相邻段在交界处平滑过渡（不硬切，硬切会在肤色上切出一条边）；
    权重**不做归一化**：一个色相落在某段中心时，那一段拿满自己的量（-100 饱和度
    就真是灰），交界处两段各出一半。归一化会把“红 -100”摊给橙色，用户拉到头
    也去不干净；
  · 每段三个量：dh 色相偏移（-60…60 度）、ds 饱和度（-100…100，-100 = 灰）、
    dl 明亮度（-100…100）；
  · 中性（24 个数全 0）由调用方短路，逐字节恒等；非中性路径在 0 处也按算式恒等；
  · 无彩像素（s≈0）不参与任何分段：给灰色像素“红原色明亮度”加值是把色标当
    亮度滑杆用，用户从画面上找不到对应关系。

收两种布局：(…,3) 与 (N,3,H,W)——与 tone/exposure 同一约定，两臂（CPU 真值 /
GPU 生产）不各写一套式子。
"""
from __future__ import annotations

import numpy as np

from ..optional_dependencies import optional_module

torch = optional_module("torch")

BAND_NAMES = ("红", "橙", "黄", "绿", "青", "蓝", "紫", "洋红")
BAND_CENTERS = (0.0, 30.0, 60.0, 120.0, 180.0, 240.0, 280.0, 320.0)
HUE_LIMIT = 60.0                       # 度
SAT_LIMIT = 100.0
LUM_LIMIT = 100.0
BAND_HALF_WIDTH = 45.0                 # 度：窗口半宽
CHROMA_GATE = 0.06                     # HSV 饱和度低于它就当无彩，不参与分段

__all__ = ["BAND_NAMES", "BAND_CENTERS", "HUE_LIMIT", "SAT_LIMIT", "LUM_LIMIT",
           "check_hsl", "is_identity", "hsl_np", "hsl_t"]


def check_hsl(bands) -> tuple:
    """24 个数（8 段 × dh/ds/dl）整组校验：NaN/Inf/越界一律拒，不夹取。"""
    vals = tuple(float(v) for v in bands)
    if len(vals) != 24:
        raise ValueError(f"HSL 需要 24 个数（8 段 × 3），收到 {len(vals)} 个")
    for i, v in enumerate(vals):
        if not np.isfinite(v):
            raise ValueError(f"HSL 第 {i // 3 + 1} 段（{BAND_NAMES[i // 3]}）是 "
                             "NaN/Inf")
        lim = HUE_LIMIT if i % 3 == 0 else (
            SAT_LIMIT if i % 3 == 1 else LUM_LIMIT)
        if abs(v) > lim:
            raise ValueError(f"HSL 第 {i // 3 + 1} 段（{BAND_NAMES[i // 3]}）"
                             f"{('色相', '饱和度', '明亮度')[i % 3]}={v} 越界"
                             f"（需要 [-{lim:.0f}, {lim:.0f}]）")
    return vals


def is_identity(bands) -> bool:
    return all(v == 0.0 for v in check_hsl(bands))


def _weights_np(h: np.ndarray) -> np.ndarray:
    """(…,8) 的未归一化分段权重；最后一维与 BAND_CENTERS 对齐。"""
    deg = h * 360.0
    ws = []
    for c in BAND_CENTERS:
        d = np.abs(deg - c)
        d = np.minimum(d, 360.0 - d)
        t = np.clip(1.0 - d / BAND_HALF_WIDTH, 0.0, 1.0)
        ws.append(t * t * (3.0 - 2.0 * t))
    return np.stack(ws, axis=-1)


def _weights_t(h, i: int):
    deg = h * 360.0
    d = (deg - BAND_CENTERS[i]).abs()
    d = torch.minimum(d, 360.0 - d)
    t = (1.0 - d / BAND_HALF_WIDTH).clamp(0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _rgb_to_hsv_np(base):
    mx = base.max(axis=-1)
    mn = base.min(axis=-1)
    d = mx - mn
    r, g, b = base[..., 0], base[..., 1], base[..., 2]
    h = np.zeros_like(mx)
    nz = d > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        hr = ((g - b) / np.where(nz, d, 1.0)) % 6.0
        hg = (b - r) / np.where(nz, d, 1.0) + 2.0
        hb = (r - g) / np.where(nz, d, 1.0) + 4.0
    h = np.where(nz & (mx == r), hr, np.where(nz & (mx == g), hg,
                                              np.where(nz, hb, 0.0))) / 6.0
    s = np.where(mx > 0, d / np.where(mx > 0, mx, 1.0), 0.0)
    return h % 1.0, np.clip(s, 0.0, 1.0), np.clip(mx, 0.0, 1.0)


def _hsv_to_rgb_np(h, s, v):
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    i = i.astype(np.int64) % 6
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4], [v, q, p, p, t], v)
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4], [t, v, v, q, p], p)
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4], [p, p, t, v, v], q)
    return np.stack([r, g, b], axis=-1)


def hsl_np(x, bands):
    """CPU 真值臂：gamma 编码 0…1，返回同形状 float64。"""
    vals = check_hsl(bands)
    a = np.asarray(x, dtype=np.float64)
    four = a.ndim == 4 and a.shape[1] == 3
    base = np.transpose(a, (0, 2, 3, 1)) if four else a
    base = np.clip(base, 0.0, 1.0)
    h, s, v = _rgb_to_hsv_np(base)
    gate = np.clip(s / CHROMA_GATE, 0.0, 1.0)
    w = _weights_np(h) * gate[..., None]
    coef = np.asarray(vals, dtype=np.float64).reshape(8, 3)
    dh = np.clip((w * coef[:, 0]).sum(axis=-1), -HUE_LIMIT, HUE_LIMIT)
    ds = np.clip((w * coef[:, 1]).sum(axis=-1), -SAT_LIMIT, SAT_LIMIT)
    dl = np.clip((w * coef[:, 2]).sum(axis=-1), -LUM_LIMIT, LUM_LIMIT)
    h2 = (h + dh / 360.0) % 1.0
    s2 = np.clip(s * (1.0 + ds / SAT_LIMIT), 0.0, 1.0)
    v2 = np.clip(v * (1.0 + dl / LUM_LIMIT), 0.0, 1.0)
    # 没有分量的像素原样递回：HSV 往返对无彩像素不做任何事，但少一次乘加就少一份
    # 浮点噪声（“掩膜外逐字节不变”的同一条纪律）。
    out = np.where((gate > 0)[..., None], _hsv_to_rgb_np(h2, s2, v2), base)
    return np.transpose(out, (0, 3, 1, 2)) if four else out


def _rgb_to_hsv_t(base):
    mx = base.max(dim=-1).values
    mn = base.min(dim=-1).values
    d = mx - mn
    r, g, b = base[..., 0], base[..., 1], base[..., 2]
    eps = torch.clamp(d, min=1e-12)
    hr = torch.remainder((g - b) / eps, 6.0)
    hg = (b - r) / eps + 2.0
    hb = (r - g) / eps + 4.0
    nz = d > 0
    h = torch.where(nz & (mx == r), hr, torch.where(nz & (mx == g), hg,
                                                   torch.where(nz, hb,
                                                               torch.zeros_like(mx)))) / 6.0
    s = torch.where(mx > 0, d / torch.clamp(mx, min=1e-12),
                    torch.zeros_like(mx))
    return h % 1.0, s.clamp(0.0, 1.0), mx.clamp(0.0, 1.0)


def _hsv_to_rgb_t(h, s, v):
    i = torch.floor(h * 6.0)
    f = h * 6.0 - i
    i = i.to(torch.int64) % 6
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    r = torch.where(i == 0, v, torch.where(i == 1, q, torch.where(
        i == 2, p, torch.where(i == 3, p, torch.where(i == 4, t, v)))))
    g = torch.where(i == 0, t, torch.where(i == 1, v, torch.where(
        i == 2, v, torch.where(i == 3, q, torch.where(i == 4, p, p)))))
    b = torch.where(i == 0, p, torch.where(i == 1, p, torch.where(
        i == 2, t, torch.where(i == 3, v, torch.where(i == 4, v, q)))))
    return torch.stack([r, g, b], dim=-1)


def hsl_t(t, bands):
    """GPU 生产臂：与 hsl_np 同一组式子。"""
    if torch is None:                  # pragma: no cover
        raise RuntimeError("hsl_t 需要 torch；纯 numpy 环境请用 hsl_np")
    vals = check_hsl(bands)
    four = t.ndim == 4 and t.shape[1] == 3
    base = t.double().permute(0, 2, 3, 1) if four else t.double()
    base = base.clamp(0.0, 1.0)
    h, s, v = _rgb_to_hsv_t(base)
    gate = (s / CHROMA_GATE).clamp(0.0, 1.0)
    acc = [torch.zeros_like(h), torch.zeros_like(h), torch.zeros_like(h)]
    for i in range(8):
        w = _weights_t(h, i) * gate
        for j in range(3):
            acc[j] = acc[j] + w * vals[i * 3 + j]
    dh = acc[0].clamp(-HUE_LIMIT, HUE_LIMIT)
    ds = acc[1].clamp(-SAT_LIMIT, SAT_LIMIT)
    dl = acc[2].clamp(-LUM_LIMIT, LUM_LIMIT)
    h2 = torch.remainder(h + dh / 360.0, 1.0)
    s2 = (s * (1.0 + ds / SAT_LIMIT)).clamp(0.0, 1.0)
    v2 = (v * (1.0 + dl / LUM_LIMIT)).clamp(0.0, 1.0)
    changed = _hsv_to_rgb_t(h2, s2, v2)
    out = torch.where((gate > 0).unsqueeze(-1), changed, base)
    if four:
        out = out.permute(0, 3, 1, 2)
    return out.to(t.dtype)
