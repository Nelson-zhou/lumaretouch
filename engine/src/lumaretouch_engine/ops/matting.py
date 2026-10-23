"""抠图/换底的确定性核心：线性光 alpha 合成 + 色键遮罩。

为什么和 `ops/birefnet.py`（神经网络抠图）分两个文件：这两条路**证据强度完全不同**。
这一条是确定性算子——给定 alpha 遮罩，`换底 = α·前景 + (1-α)·背景` 有闭式解、有
逐字节不变式（α=1 必须原样等于前景、α=0 必须原样等于背景）、有 CPU↔GPU 对拍；那条
是神经网络，没有权重就没有任何「抠得准」的质量主张可写。把两者塞进同一个函数、同
一个事件字段，报表就会把「合成对了」和「抠得准」混成一个数——这正是本仓最贵那个坑
的形状。所以本文件只对**合成与色键**负责，抠得准不准归 birefnet 的权重门禁。

合成为什么在线性光下做：sRGB 值不是光量的线性表示，直接在 sRGB 域做 `α·fg+(1-α)·bg`
会在半透明边缘（发丝、羽化过渡）出现暗边/亮边，因为两种编码值的加权 ≠ 光量的加权。
先在 _lin（→线性）里混合、再 _slin（→sRGB）回来，才是物理正确的 over 合成。这与
`ops/light.py` 的 dodge/burn 走线性光是同一个理由，也复用同一对转换函数。
"""

from __future__ import annotations

import numpy as np

from .light import _lin_np, _slin_np  # 线性光 ↔ sRGB：与修容层同一串式子，不另发明一套口径


def _as_alpha_f(a, dtype):
    """把 alpha 归一到 [0,1] 浮点：支持 uint8(0..255) 与已在 [0,1] 的浮点。"""
    if a.dtype == np.uint8 or (hasattr(a, "max") and not isinstance(a, float) and _looks_uint8(a)):
        a = a.astype(dtype) / 255.0
    else:
        a = a.astype(dtype)
    return a


def _looks_uint8(a) -> bool:
    try:
        return int(a.max()) > 1.0
    except Exception:
        return False


def _check_shapes(fg, alpha, bg):
    if fg.ndim != 3 or fg.shape[2] != 3:
        raise ValueError(f"前景应为 (H,W,3)，得到 {fg.shape}")
    if alpha.shape != fg.shape[:2]:
        raise ValueError(f"alpha 形状 {alpha.shape} 与前景 {fg.shape[:2]} 不符")
    if isinstance(bg, np.ndarray):
        if bg.shape == (3,):
            return
        if bg.shape != fg.shape:
            raise ValueError(f"背景应为 (3,) 或 (H,W,3)，得到 {bg.shape}")
    else:
        raise TypeError(f"背景应为 ndarray（单色 (3,) 或整幅 (H,W,3)），得到 {type(bg).__name__}")


def _to_unit(a) -> np.ndarray:
    """uint8(0..255) → [0,1] 浮点；已是浮点则只 clip。与 _as_alpha_f 同一口径。"""
    a = np.asarray(a)
    if a.dtype == np.uint8:
        return a.astype(np.float64) / 255.0
    return np.clip(a.astype(np.float64), 0.0, 1.0)


def composite_np(fg: np.ndarray, alpha, bg) -> np.ndarray:
    """线性光 over 合成：`out = α·fg + (1-α)·bg`，返回 uint8 (H,W,3)。

    fg/bg 可为 uint8(0..255) 或 [0,1] 浮点；alpha 可为 uint8 或 [0,1]。都先归一到
    [0,1] 再进线性光转换。

    不变式（有对应用例钉死）：
    * α≡255 → 逐字节等于 fg；α≡0 → 逐字节等于 bg（单色时铺满）。
    * 半透明在**线性域**混合：α=0.5、fg=白、bg=黑 → 线性中值 0.5 编码回 sRGB≈188，
      而不是 sRGB 域直接平均得到的 128。这一档之差就是「有没有在线性光下合成」的证据。
    """
    _check_shapes(fg, alpha, bg)
    a = np.clip(_as_alpha_f(np.asarray(alpha), np.float64), 0.0, 1.0)[..., None]
    fg_lin = _lin_np(_to_unit(fg))
    if isinstance(bg, np.ndarray) and bg.ndim == 3:
        bg_lin = _lin_np(_to_unit(bg))
    else:
        bg_lin = np.tile(_lin_np(_to_unit(np.asarray(bg)).reshape(1, 1, 3)),
                         (fg.shape[0], fg.shape[1], 1))
    out_lin = a * fg_lin + (1.0 - a) * bg_lin
    return np.clip(_slin_np(out_lin) * 255.0, 0.0, 255.0).round().astype(np.uint8)


# ---------------------------------------------------------------- torch 生产路
def _lin_t(a):
    import torch
    return torch.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055).pow(2.4))


def _slin_t(a):
    import torch
    return torch.where(a <= 0.0031308, a * 12.92, 1.055 * a.clamp_min(1e-12).pow(1.0 / 2.4) - 0.055)


def composite_linear_fields_t(rgb, alpha, linear_background):
    """Shared ID/derived-common float composition; never clip edited radiance.

    RGB is encoded sRGB, background is linear sRGB; alpha is straight coverage.
    Fully opaque foreground is bit-preserved. Source admission is separate.
    """
    import torch
    a = alpha.clamp(0, 1)
    linear = torch.where(rgb <= 0.04045, rgb / 12.92,
                         ((rgb + 0.055) / 1.055).clamp_min(0).pow(2.4))
    mixed = linear * a + linear_background * (1 - a)
    encoded = torch.where(mixed <= 0.0031308, mixed * 12.92,
                          1.055 * mixed.clamp_min(0).pow(1 / 2.4) - 0.055)
    return torch.where(a >= 1, rgb, encoded)


def composite_t(fg, alpha, bg):
    """GPU 生产路：与 composite_np 同一串式子（float32 在线性光下合成）。

    入参都按 (B,3,H,W) / (B,1,H,W) 的 [0,1] **sRGB 编码值**（就是常驻管线里张量的
    实际布局），bg 为 (B,3,H,W) 或可广播的 (3,)/(1,3,1,1)。返回同样 [0,1] 的合成结果，
    且已在线性域混合后编码回 sRGB——与 composite_np 的差别只在没乘 255/取整，便于逐
    像素对拍（乘 255 再 round 就应等于 composite_np，误差 ≤1 LSB）。
    """
    import torch

    if fg.ndim != 4 or fg.shape[1] != 3:
        raise ValueError(f"composite_t 前景应为 (B,3,H,W)，得到 {tuple(fg.shape)}")
    a = alpha if alpha.ndim == 4 else alpha.unsqueeze(1)
    a = _alpha_f_t(a).clamp(0.0, 1.0)
    fg_lin = _lin_t(fg.to(torch.float32).clamp(0.0, 1.0))
    if isinstance(bg, torch.Tensor) and bg.ndim == 4:
        bg_lin = _lin_t(bg.to(torch.float32).clamp(0.0, 1.0))
    else:
        arr = (bg.detach().cpu().numpy() if isinstance(bg, torch.Tensor) else np.asarray(bg))
        b = torch.tensor(arr, dtype=torch.float32, device=fg.device).clamp(0.0, 1.0)
        bg_lin = _lin_t(b.reshape(1, 3, 1, 1))
    mix_lin = a * fg_lin + (1.0 - a) * bg_lin
    return _slin_t(mix_lin.clamp(0.0, 1.0))


def _alpha_f_t(a):
    import torch

    if a.dtype in (torch.uint8, torch.int32, torch.int64):
        return a.to(torch.float32) / 255.0
    return a.to(torch.float32)


def composite_quantize_t(result_0_1):
    """把 composite_t 的 [0,1] sRGB 结果量化成 uint8（常驻管线出帧用）。"""
    import torch

    return (result_0_1.clamp(0.0, 1.0) * 255.0).round().clamp(0.0, 255.0).to(torch.uint8)


# ---------------------------------------------------------------- 色键（确定性抠图）
def key_matte_np(img: np.ndarray, ref=None, tol: float = 0.12, softness: float = 0.10,
                 samples: int = 8) -> np.ndarray:
    """色键遮罩：与背景参考色的欧氏距离越大越像前景（alpha→1）。近单色背景（影楼蓝箱、
    纯白/纯灰底）的确定性抠底就走这条——不依赖任何模型，可复算、可对拍。

    `ref` 不给时，取四条边中若干像素的中位数当背景色（影楼底几乎总是占满边框）。
    `tol` 是「多大色差以内算背景」，`softness` 是硬边到软边的过渡宽度（>0 才有羽化，
    避免锯齿）。返回 float64 [0,1] 的 alpha。

    这不是「万能抠图」：复杂背景下色键会把前景里的相近颜色也抠掉。所以自动抠图的正解
    是 `birefnet`（权重放行后），色键只是零依赖、可测、能立刻出厂的基础档。
    """
    x = _to_unit(img)                                     # uint8 → [0,1]（与合成同口径）
    if ref is None:
        ref = _edge_median(x, samples=samples)
    ref = np.asarray(ref, dtype=np.float64).reshape(3)
    d = np.sqrt(((x - ref[None, None, :]) ** 2).sum(axis=2))
    # smoothstep(tol, tol+softness)：距离 ≤ tol 归 0（背景），≥ tol+softness 归 1（前景）
    hi = tol + max(softness, 1e-6)
    t = np.clip((d - tol) / (hi - tol), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _edge_median(x: np.ndarray, samples: int = 8) -> np.ndarray:
    """边框像素中位数当背景色：影楼纯色底铺满边，中位数比角点稳（角上可能有黑边/杂点）。"""
    h, w = x.shape[:2]
    samples = max(1, int(samples))
    ys = np.linspace(0, h - 1, samples).astype(int)
    xs = np.linspace(0, w - 1, samples).astype(int)
    edge = np.concatenate([
        x[ys, 0], x[ys, w - 1], x[0, xs], x[h - 1, xs],
    ], axis=0)
    return np.median(edge, axis=0)
