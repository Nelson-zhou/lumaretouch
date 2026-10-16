"""保边滤波与频域分离——质感磨皮的算法底座。

约定：图像以 float32、shape (B,C,H,W)、值域 [0,1] 表示。
numpy 版是**参考实现**（跑在 CPU，用于对拍），torch 版是**生产实现**（GPU）。
两者结果必须在容差内一致，否则 GPU 内核不许上生产。
"""

from __future__ import annotations

import numpy as np

try:
    import torch
    import torch.nn.functional as F
    _HAS_TORCH = True
except Exception:  # torch 未装（M0 纯通路阶段允许）
    torch = None
    F = None
    _HAS_TORCH = False


# ---------------------------------------------------------------- numpy 参考
def _box_np(x: np.ndarray, r: int) -> np.ndarray:
    """盒式滤波，O(1)/像素、与半径无关（积分图实现）。"""
    if r <= 0:
        return x
    p = np.pad(x, ((0, 0), (0, 0), (r, r), (r, r)), mode="reflect")
    cs = np.cumsum(np.cumsum(p, axis=2), axis=3)
    # 积分图必须补一圈零边界，否则窗口和的下标推不出来
    c = np.zeros(p.shape[:2] + (p.shape[2] + 1, p.shape[3] + 1), dtype=cs.dtype)
    c[:, :, 1:, 1:] = cs
    k = 2 * r + 1
    total = c[:, :, k:, k:] - c[:, :, :-k, k:] - c[:, :, k:, :-k] + c[:, :, :-k, :-k]
    return total / float(k * k)


def guided_np(img: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """自导向的快速导向滤波（He et al. 2010 的 O(1) 近似版）。"""
    mean_i = _box_np(img, radius)
    mean_ii = _box_np(img * img, radius)
    var_i = mean_ii - mean_i * mean_i
    a = var_i / (var_i + eps)
    b = mean_i - a * mean_i
    return _box_np(a, radius) * img + _box_np(b, radius)


def frequency_split_np(img: np.ndarray, radius: int, eps: float):
    low = guided_np(img, radius, eps)
    return low, img - low


def _mix_masked(img, retouched, strength, weight):
    """按掩膜加权混合：`effective = strength · weight`，再在 img / retouched 之间插值。

    写成这个形式而不是先混图再乘强度，是为了让 **strength=0 逐字节恒等** 这件事在
    数学上无条件成立：weight 只能取值在 [0,1]，`0.0 * x` 对有限浮点数恒为 0，
    `(1-0)*img + 0*retouched` 就是 img 本身。掩膜再离谱也不能破坏验收口径③。
    """
    w = strength * weight
    return (1.0 - w) * img + w * retouched


def retouch_np(img: np.ndarray, strength: float, radius: int = 12,
               eps: float = 6e-4, detail_gain: float = 0.85) -> np.ndarray:
    """质感磨皮：低频二次均化去色斑，高频按 detail_gain 保留肌理。

    必须与 retouch_t 逐行同语义，否则 GPU/CPU 对拍没有意义。
    注意：detail_gain=1.0 且不做低频二次均化时，low+high 恒等于原图，
    滑块会变成空操作——这两个项必须同时在。
    """
    low = guided_np(img, radius, eps)
    high = img - low
    low2 = guided_np(low, radius * 2, eps * 4.0)
    out = low2 + high * detail_gain
    return (1.0 - strength) * img + strength * out


def retouch_masked_np(img: np.ndarray, weight: np.ndarray, strength: float,
                      radius: int = 12, eps: float = 6e-4,
                      detail_gain: float = 0.85) -> np.ndarray:
    """逐像素强度的参考实现（CPU）：掩膜只在能达区域生效。

    weight 形状 (1,1,H,W) 或 (1,C,H,W)，值域 [0,1]。必须与 retouch_masked_t 同语义。
    """
    low = guided_np(img, radius, eps)
    high = img - low
    low2 = guided_np(low, radius * 2, eps * 4.0)
    out = low2 + high * detail_gain
    return _mix_masked(img, out, strength, weight)


# ------------------------------------------------------------------ torch 生产
def _box_t(x, r: int):
    """盒式滤波（积分图）：O(1)/像素、与半径无关，与 _box_np 逐句同语义。

    实测（RX 7600 XT / gfx1102）1280x800 单趟 0.73 ms；换成
    avg_pool2d(reflect_pad) 要 6.0 ms，且半径 12→60 时涨到 114 ms（本方 0.92 ms）。
    大窗口磨皮滑块只能走积分图这条路，否则半径一变帧率就崩。
    与 CPU 参考实现对拍最大偏差 5.5e-4（float32 累加噪声），在 1e-3 允差内。
    """
    if r <= 0:
        return x
    k = 2 * r + 1
    h, w = x.shape[-2], x.shape[-1]
    p = F.pad(x, (r, r, r, r), mode="reflect")
    ii = torch.cumsum(torch.cumsum(p, dim=-2), dim=-1)
    # 补一圈零边界，窗口和就是四个角直接相减：br - tr - bl + tl
    ii = F.pad(ii, (1, 1, 1, 1), mode="constant", value=0)
    br = ii[..., k:k + h, k:k + w]
    tr = ii[..., :h, k:k + w]
    bl = ii[..., k:k + h, :w]
    tl = ii[..., :h, :w]
    return (br - tr - bl + tl) / float(k * k)


def guided_t(img, radius: int, eps: float):
    mean_i = _box_t(img, radius)
    mean_ii = _box_t(img * img, radius)
    var_i = mean_ii - mean_i * mean_i
    a = var_i / (var_i + eps)
    b = mean_i - a * mean_i
    return _box_t(a, radius) * img + _box_t(b, radius)


def retouch_t(img, strength: float, radius: int = 12, eps: float = 6e-4,
              detail_gain: float = 0.85):
    low = guided_t(img, radius, eps)
    high = img - low
    low2 = guided_t(low, radius * 2, eps * 4.0)
    out = low2 + high * detail_gain
    return (1.0 - strength) * img + strength * out


def retouch_masked_t(img, weight, strength: float, radius: int = 12, eps: float = 6e-4,
                     detail_gain: float = 0.85):
    """GPU 生产版逐像素强度磨皮，与 retouch_masked_np 逐句同语义。

    这一条是 M1-3b 以掩膜常驻显存、M1-3c 拖滑块只改系数的算法底座：
    半径/强度/掩膜都是张量入参，不需重新上传源图。
    """
    low = guided_t(img, radius, eps)
    high = img - low
    low2 = guided_t(low, radius * 2, eps * 4.0)
    out = low2 + high * detail_gain
    return _mix_masked(img, out, strength, weight)


def make_tensor(arr, device: str, dtype=None):
    """numpy (H,W,C) float32 → torch (1,C,H,W)。"""
    if not _HAS_TORCH:
        raise RuntimeError("torch 未安装，无法走 GPU 通路")
    t = torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1)))[None]
    t = t.to(device=device, dtype=dtype or torch.float32)
    return t.contiguous()


def to_numpy_chw(t) -> np.ndarray:
    return t[0].detach().to("cpu", torch.float32).numpy().transpose(1, 2, 0)
