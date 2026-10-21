"""全局影调四项：对比度 / 高光 / 阴影 / 饱和度。

为什么它挂在曝光层而不是另开一层：这四项与 EV 一样是**逐点、无位置、无掩膜**的
整图变换，共用同一条“中性短路 + 一次性提交 + 出帧失败回滚”的链。另开一个
`cmd_tone` 只会多一份文档状态、多一处工程序列化、多一个切图忘迁移的坑，而画面
上的次序仍是它后面紧跟 LUT。

量程与语义（原创扩展，未写进 P0 注册表）：
  · contrast/highlights/shadows/saturation 都是 -100…100，0 = 关；
  · 正对比度以 0.5 为支点拉开，负对比度压平；
  · 高光/阴影是亮度门控的加减，正 = 提亮，负 = 回收；
  · 饱和度 -100 = 全灰。

中性必须逐字节恒等：四项全 0 时 `apply_exposure` 根本不进这一层（短路在调用方），
而非中性路径在 0 处也由算式给出恒等（加权项系数为 0）。
"""
from __future__ import annotations

import numpy as np

from ..optional_dependencies import optional_module

torch = optional_module("torch")

TONE_LIMIT = 100.0

__all__ = ["TONE_LIMIT", "check_tone", "is_identity", "tone_np", "tone_t"]


def check_tone(contrast: float = 0.0, highlights: float = 0.0,
               shadows: float = 0.0, saturation: float = 0.0) -> tuple:
    vals = (float(contrast), float(highlights), float(shadows), float(saturation))
    for v, name in zip(vals, ("contrast", "highlights", "shadows", "saturation")):
        if not np.isfinite(v):
            raise ValueError(f"tone.{name} 是 NaN/Inf")
        if abs(v) > TONE_LIMIT:
            raise ValueError(f"tone.{name}={v} 越界（需要 [-{TONE_LIMIT:.0f}, "
                             f"{TONE_LIMIT:.0f}]）")
    return vals


def is_identity(contrast: float = 0.0, highlights: float = 0.0,
                shadows: float = 0.0, saturation: float = 0.0) -> bool:
    c, h, s, sa = check_tone(contrast, highlights, shadows, saturation)
    return c == 0.0 and h == 0.0 and s == 0.0 and sa == 0.0


def _smooth_np(x, lo: float, hi: float):
    """0…1 的 smoothstep；lo==hi 时退化成阶跃（调用方不会给这种值）。"""
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def tone_np(x, contrast: float = 0.0, highlights: float = 0.0,
            shadows: float = 0.0, saturation: float = 0.0):
    """CPU 真值臂：gamma 编码 0…1，返回同形状 float64。

    收两种布局：(…,3) 与 (N,3,H,W)。后者是 vram 的帧张量布局，通道轴不在最后；
    先搬到最后一维算完再搬回去，两臂不各写一套。
    """
    c, h, s, sa = check_tone(contrast, highlights, shadows, saturation)
    a = np.asarray(x, dtype=np.float64)
    four = a.ndim == 4 and a.shape[1] == 3
    base = np.transpose(a, (0, 2, 3, 1)) if four else a
    base = np.clip(base, 0.0, 1.0)
    cn, hn, sn, san = c / TONE_LIMIT, h / TONE_LIMIT, s / TONE_LIMIT, sa / TONE_LIMIT

    out = (base - 0.5) * (1.0 + cn) + 0.5
    out = np.clip(out, 0.0, 1.0)

    if hn != 0.0 or sn != 0.0:
        y = (0.2126 * out[..., 0:1] + 0.7152 * out[..., 1:2]
             + 0.0722 * out[..., 2:3])
        wh = _smooth_np(y, 0.45, 1.0) * hn * 0.35
        ws = (1.0 - _smooth_np(y, 0.0, 0.6)) * sn * 0.35
        out = np.clip(out + wh + ws, 0.0, 1.0)

    if san != 0.0:
        y = (0.2126 * out[..., 0:1] + 0.7152 * out[..., 1:2]
             + 0.0722 * out[..., 2:3])
        out = np.clip(y + (out - y) * (1.0 + san), 0.0, 1.0)
    return np.transpose(out, (0, 3, 1, 2)) if four else out


def tone_t(x, contrast: float = 0.0, highlights: float = 0.0,
           shadows: float = 0.0, saturation: float = 0.0):
    """GPU 生产臂：与 tone_np 同一组式子。"""
    if torch is None:                  # pragma: no cover
        raise RuntimeError("tone_t 需要 torch；纯 numpy 环境请用 tone_np")
    c, h, s, sa = check_tone(contrast, highlights, shadows, saturation)
    cn, hn, sn, san = (c / TONE_LIMIT, h / TONE_LIMIT,
                       s / TONE_LIMIT, sa / TONE_LIMIT)
    four = x.ndim == 4 and x.shape[1] == 3
    base = x.double().permute(0, 2, 3, 1) if four else x.double()
    base = base.clamp(0.0, 1.0)
    out = ((base - 0.5) * (1.0 + cn) + 0.5).clamp(0.0, 1.0)

    if hn != 0.0 or sn != 0.0:
        y = (0.2126 * out[..., 0:1] + 0.7152 * out[..., 1:2]
             + 0.0722 * out[..., 2:3])
        wh = _smooth_t(y, 0.45, 1.0) * (hn * 0.35)
        ws = (1.0 - _smooth_t(y, 0.0, 0.6)) * (sn * 0.35)
        out = (out + wh + ws).clamp(0.0, 1.0)

    if san != 0.0:
        y = (0.2126 * out[..., 0:1] + 0.7152 * out[..., 1:2]
             + 0.0722 * out[..., 2:3])
        out = (y + (out - y) * (1.0 + san)).clamp(0.0, 1.0)
    if four:
        out = out.permute(0, 3, 1, 2)
    return out.to(x.dtype)


def _smooth_t(x, lo: float, hi: float):
    t = ((x - lo) / (hi - lo)).clamp(0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
