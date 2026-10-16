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


def mix_masked(img, retouched, strength, weight):
    """按掩膜加权混合：`effective = strength · weight`，再在 img / retouched 之间插值。

    写成这个形式而不是先混图再乘强度，是为了让 **strength=0 逐字节恒等** 这件事在
    数学上无条件成立：weight 只能取值在 [0,1]，`0.0 * x` 对有限浮点数恒为 0，
    `(1-0)*img + 0*retouched` 就是 img 本身。掩膜再离谱也不能破坏验收口径③。
    """
    w = strength * weight
    return (1.0 - w) * img + w * retouched


def filter_np(img: np.ndarray, radius: int = 12, eps: float = 6e-4,
              detail_gain: float = 0.85) -> np.ndarray:
    """质感磨皮的**与 strength 无关**的那一半（参考实现）。

    拆出这一层的理由不是好看：`out` 完全不依赖 strength，所以“拖滑块”本质上只
    是对一个固定张量做线性插值。分开了才能缓存，也才能在测试里逐字证明
    「缓存路径 == 逐帧重算」（两者用的是同一个 `out` 与同一个混合式）。
    """
    low = guided_np(img, radius, eps)
    high = img - low
    low2 = guided_np(low, radius * 2, eps * 4.0)
    return low2 + high * detail_gain


def retouch_np(img: np.ndarray, strength: float, radius: int = 12,
               eps: float = 6e-4, detail_gain: float = 0.85) -> np.ndarray:
    """质感磨皮：低频二次均化去色斑，高频按 detail_gain 保留肌理。

    必须与 retouch_t 逐行同语义，否则 GPU/CPU 对拍没有意义。
    注意：detail_gain=1.0 且不做低频二次均化时，low+high 恒等于原图，
    滑块会变成空操作——这两个项必须同时在。
    """
    out = filter_np(img, radius, eps, detail_gain)
    return (1.0 - strength) * img + strength * out


def retouch_masked_np(img: np.ndarray, weight: np.ndarray, strength: float,
                      radius: int = 12, eps: float = 6e-4,
                      detail_gain: float = 0.85) -> np.ndarray:
    """逐像素强度的参考实现（CPU）：掩膜只在能达区域生效。

    weight 形状 (1,1,H,W) 或 (1,C,H,W)，值域 [0,1]。必须与 retouch_masked_t 同语义。
    """
    out = filter_np(img, radius, eps, detail_gain)
    return mix_masked(img, out, strength, weight)


# ------------------------------------------------------------------ torch 生产
def _box_t(x, r: int):
    """盒式滤波（积分图）：O(1)/像素、与半径无关，与 _box_np 逐句同语义。

    实测（RX 7600 XT / gfx1102）1280x800 单趟 0.73 ms；换成
    avg_pool2d(reflect_pad) 要 6.0 ms，且半径 12→60 时涨到 114 ms（本方 0.92 ms）。
    大窗口磨皮滑块只能走积分图这条路，否则半径一变帧率就崩。

    与 CPU 参考对拍（真图，累加顺序噪声）：672×848 r=12 是 5.5e-4，1024×1280 是 9.0e-4。
    但别把这个当成整条链的误差：guided 里 `a = var/(var+eps)` 在平坦区会除以小量，
    两趟串联后端到能到 3.2e-3（随机噪声图只有 2.5e-4，所以拿噪声图定门禁是弱门禁）。
    字节层面仍是 ≤1 LSB，那才是验收口径；产品尺寸上的对拍在 tests/test_guided.py 钉住。
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


def filter_t(img, radius: int = 12, eps: float = 6e-4, detail_gain: float = 0.85):
    """与 strength 无关的滤波链（GPU 生产版），与 filter_np 逐句同语义。

    这是 M1-3c 「拖滑块零推理」的全部依据：实测 672×848 这一句 4.48 ms，而把结果
    常驻后每帧只重算混合是 0.09 ms。缓存它不是一个近似——retouch_t 用的就是同一个
    张量与同一个表达式，因此逐字节相等（实测 14 个强度点全 0 LSB，含掩膜通道）。
    """
    low = guided_t(img, radius, eps)
    high = img - low
    low2 = guided_t(low, radius * 2, eps * 4.0)
    return low2 + high * detail_gain


def retouch_t(img, strength: float, radius: int = 12, eps: float = 6e-4,
              detail_gain: float = 0.85):
    return (1.0 - strength) * img + strength * filter_t(img, radius, eps, detail_gain)


def retouch_masked_t(img, weight, strength: float, radius: int = 12, eps: float = 6e-4,
                     detail_gain: float = 0.85):
    """GPU 生产版逐像素强度磨皮，与 retouch_masked_np 逐句同语义。

    掩膜只加权混合，不改滤波结果本身——所以 `filter_t` 那一份常驻缓存对全图与
    分通道两条路都适用，不必每个通道各存一张。
    """
    return mix_masked(img, filter_t(img, radius, eps, detail_gain), strength, weight)


def make_tensor(arr, device: str, dtype=None):
    """numpy (H,W,C) float32 → torch (1,C,H,W)。

    只收浮点。传 uint8 不报错而是静默产出一张 0..255 值域的图，后面的滤波就在全错
    的尺度上跑（实测与参考实现差 2.5e+02）——写探针的人已经连着踩过两次了，所以
    把它卡在这里而不是只写在文档里。调用方自己除 255（与 vram/_pipe_copyin 一致）。
    """
    if not _HAS_TORCH:
        raise RuntimeError("torch 未安装，无法走 GPU 通路")
    if not np.issubdtype(np.asarray(arr).dtype, np.floating):
        raise TypeError(f"make_tensor 只接受 float32/float64、值域 [0,1] 的图像，"
                        f"得到 {np.asarray(arr).dtype}；uint8 请先 astype(float32)/255.0")
    t = torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1)))[None]
    t = t.to(device=device, dtype=dtype or torch.float32)
    return t.contiguous()


def to_numpy_chw(t) -> np.ndarray:
    return t[0].detach().to("cpu", torch.float32).numpy().transpose(1, 2, 0)
