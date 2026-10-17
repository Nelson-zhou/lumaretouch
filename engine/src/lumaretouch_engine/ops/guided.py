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


# ---------------------------------------------------- M2-a 四条带与产品默认值
# 带定义见 bands_np / bands_t。这四个数是探针量出来的，不是抄来的：
# `gpuspike/m2probe4.py` 在「已知成分合成图」（平坦底色 + 半径 9~14 高斯斑 +
# σ=0.013 毛孔颗粒 + 0.06 阶跃硬边缘）上做最小二乘回归，直接读出每条带的增益。
# 默认位 (broad=0, mid=0, tex=1) 的实测：**孔 0.992 / 斑 0.402 / 边 0.861**。
# 同图上传统盒式模糊（r=4…16）是 孔 0.004~0.013 / 斑 0.72~0.98 —— 毛孔全灭而色斑
# 几乎没去掉，选择性 0.01 vs 本方 2.47。这就是「质感磨皮」与「塑料脸」的分界。
DEFAULT_RADIUS = 12
DEFAULT_EPS = 6e-4
DEFAULT_TEXTURE_RADIUS = 4
DEFAULT_BROAD_GAIN = 0.0
DEFAULT_MID_GAIN = 0.0
DEFAULT_DETAIL_GAIN = 1.0


# ---------------------------------------------------------------- numpy 参考
def _box_np(x: np.ndarray, r: int) -> np.ndarray:
    """盒式滤波，O(1)/像素、与半径无关（积分图实现，**累加器用 float64**）。

    为什么累加器不能用输入自己的精度：积分图的四角相减是“两个大数相减得一个小数”，
    窗口越小相对误差越大（积到的前缀和与 N 成正比，除的却是 k²）。实测 672×848 产品档：
    float32 累加时 r=4 单趟就有 2.2e-03 的绝对错（半个 LSB），r=12 是 5.1e-04，
    r=24 是 1.8e-04；换成 float64 累加后 CPU 与 GPU **逐位相同**（0.00e+00）——
    因为输入是 float32（尾数 24 位）、元素数 ~1e6，它们的和在 float64 里是**精确**的，
    两边只是同一个精确结果各自舍入到 float32。这不是“误差变小”，是把误差源掐了。
    """
    if r <= 0:
        return x
    p = np.pad(x, ((0, 0), (0, 0), (r, r), (r, r)), mode="reflect")
    # 不管输入是 float32 还是 float64，累加器一律 float64：上面说的那个精确性论证
    # 对两者都成立（float64 输入时前缀和只可能溢出在 2^53 以上，产品尺寸远达不到）。
    cs = np.cumsum(np.cumsum(p, axis=2, dtype=np.float64), axis=3, dtype=np.float64)
    # 积分图必须补一圈零边界，否则窗口和的下标推不出来
    c = np.zeros(p.shape[:2] + (p.shape[2] + 1, p.shape[3] + 1), dtype=cs.dtype)
    c[:, :, 1:, 1:] = cs
    k = 2 * r + 1
    total = c[:, :, k:, k:] - c[:, :, :-k, k:] - c[:, :, k:, :-k] + c[:, :, :-k, :-k]
    return (total / float(k * k)).astype(x.dtype)


def guided_np(img: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """自导向的快速导向滤波（He et al. 2010 的 O(1) 近似版）。"""
    mean_i = _box_np(img, radius)
    mean_ii = _box_np(img * img, radius)
    # 方差在数学上非负，但 `mean_ii − mean_i²` 是两个大数相减，浮点下会算出负数。
    # 不夹零的话 `a = var/(var+eps)` 在 var ≈ −eps 时除以小量：实测把一张预先盒式
    # 平滑过的图（M2-a 的分带就会这么送）喂进去，a 能到 −66 / +232（rf=4）甚至 +1.5e+04
    # （rf=8），而这些像素占 12%～22%。a 乘在图上，那就是几十 LSB 的错。
    # 夹零同时把 a 限死在 [0,1)，既修了语义也修了 CPU/GPU 分叉。
    var_i = np.maximum(mean_ii - mean_i * mean_i, 0.0)
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


def bands_np(img: np.ndarray, radius: int = DEFAULT_RADIUS, eps: float = DEFAULT_EPS,
             texture_radius: int = DEFAULT_TEXTURE_RADIUS):
    """把图精确分成四条带，返回 (base, broad, mid, tex)。

    `img = base + broad + mid + tex` 是**代数恒等**（增益全 1 必须回到原图），
    所以这三条增益是有物理意义的旋钮，不是一堆互相抵消的系数。

      tex   = img − box(img, rf)          细带：毛孔 / 绒毛 / 最细的边缘
      mid   = blur − guided(blur, r, eps) 中带：瑕疵、边缘锐度（保边滤波的残差）
      broad = low1 − guided(low1, 2r, 4eps) 低频带：大面积色斑、光影不均
      base  = 二次均化后的基色

    为什么 tex 必须用**线性**高通而不是 M1-3c 那样取 guided 的残差：
    guided 本身就是收缩算子——皮肤平坦区局部方差 ~2.3e-4 对 eps=6e-4 时
    `a = var/(var+eps) ≈ 0.27`，于是残差里只带着 0.27~0.73 的毛孔幅度，
    `detail_gain=1.0` 这句话当场变成假的（实测孔增益 0.835，且斑也只去掉 0.600）。
    把 guided 放到「已经去掉纹理的 blur」上，它的收缩就碰不到 tex：
    同一个默认位实测 0.992 / 0.402 —— **更保孔、更去斑，是双赢而不是取舍**。
    """
    rf = int(texture_radius)
    blur = _box_np(img, rf)
    tex = img - blur
    low1 = guided_np(blur, radius, eps)
    mid = blur - low1
    base = guided_np(low1, radius * 2, eps * 4.0)
    return base, low1 - base, mid, tex


def combine_np(base, broad, mid, tex, broad_gain: float, mid_gain: float,
               detail_gain: float):
    """按增益重组。纯逐点乘加，所以能单独成为一层缓存（分带贵、重组便宜）。"""
    return base + broad * float(broad_gain) + mid * float(mid_gain) + tex * float(detail_gain)


def filter_np(img: np.ndarray, radius: int = DEFAULT_RADIUS, eps: float = DEFAULT_EPS,
              detail_gain: float = DEFAULT_DETAIL_GAIN, mid_gain: float = DEFAULT_MID_GAIN,
              broad_gain: float = DEFAULT_BROAD_GAIN,
              texture_radius: int = DEFAULT_TEXTURE_RADIUS) -> np.ndarray:
    """质感磨皮的**与 strength 无关**的那一半（参考实现）。"""
    return combine_np(*bands_np(img, radius, eps, texture_radius),
                      broad_gain, mid_gain, detail_gain)


def retouch_np(img: np.ndarray, strength: float, radius: int = DEFAULT_RADIUS,
               eps: float = DEFAULT_EPS, detail_gain: float = DEFAULT_DETAIL_GAIN,
               mid_gain: float = DEFAULT_MID_GAIN, broad_gain: float = DEFAULT_BROAD_GAIN,
               texture_radius: int = DEFAULT_TEXTURE_RADIUS) -> np.ndarray:
    """质感磨皮：四条带分频重组，再按 strength 与原图线性插值（CPU 参考）。

    必须与 retouch_t 逐行同语义，否则 GPU/CPU 对拍没有意义。
    """
    out = filter_np(img, radius, eps, detail_gain, mid_gain, broad_gain, texture_radius)
    return (1.0 - strength) * img + strength * out


def retouch_masked_np(img: np.ndarray, weight: np.ndarray, strength: float,
                      radius: int = DEFAULT_RADIUS, eps: float = DEFAULT_EPS,
                      detail_gain: float = DEFAULT_DETAIL_GAIN,
                      mid_gain: float = DEFAULT_MID_GAIN,
                      broad_gain: float = DEFAULT_BROAD_GAIN,
                      texture_radius: int = DEFAULT_TEXTURE_RADIUS) -> np.ndarray:
    """逐像素强度的参考实现（CPU）：掩膜只在能达区域生效。

    weight 形状 (1,1,H,W) 或 (1,C,H,W)，值域 [0,1]。必须与 retouch_masked_t 同语义。
    """
    out = filter_np(img, radius, eps, detail_gain, mid_gain, broad_gain, texture_radius)
    return mix_masked(img, out, strength, weight)


# ------------------------------------------------------------------ torch 生产
def _box_t(x, r: int):
    """盒式滤波（积分图）：O(1)/像素、与半径无关，与 _box_np 逐句同语义。

    实测（RX 7600 XT / gfx1102）1280x800 单趟 0.73 ms；换成
    avg_pool2d(reflect_pad) 要 6.0 ms，且半径 12→60 时涨到 114 ms（本方 0.92 ms）。
    大窗口磨皮滑块只能走积分图这条路，否则半径一变帧率就崩。

    累加器强制 float64（与 _box_np 同步改）：不只为精度——产品档上 9 趟积分图，
    float32 累加时 CPU 与 GPU 的单趟差就有 2.1e-03（r=4），直接透到 tex 带上就是
    系统性半 LSB 偏移（实测“差异子像素占比”从 1.4% 跳到 2.9%，而最大值仍然只 1 LSB，
    正好是那种会被“最大 1 LSB”掩盖的情状）。夹成 float64 后两边逐位相同，
    而且**反而更快**（产品档 9 趟 11.44 → 7.43 ms：torch 的 dtype= 累加躲开了一个
    中间张量）。两个方向都赢，这不是权衡。
    """
    if r <= 0:
        return x
    k = 2 * r + 1
    h, w = x.shape[-2], x.shape[-1]
    p = F.pad(x, (r, r, r, r), mode="reflect")
    ii = p.cumsum(dim=-2, dtype=torch.float64).cumsum(dim=-1, dtype=torch.float64)
    # 补一圈零边界，窗口和就是四个角直接相减：br - tr - bl + tl
    ii = F.pad(ii, (1, 1, 1, 1), mode="constant", value=0)
    br = ii[..., k:k + h, k:k + w]
    tr = ii[..., :h, k:k + w]
    bl = ii[..., k:k + h, :w]
    tl = ii[..., :h, :w]
    return ((br - tr - bl + tl) / float(k * k)).to(x.dtype)


def guided_t(img, radius: int, eps: float):
    mean_i = _box_t(img, radius)
    mean_ii = _box_t(img * img, radius)
    # 与 guided_np 逐句同语义：方差必须夹零，否则 a 无界（见那边的注释）。
    var_i = (mean_ii - mean_i * mean_i).clamp_min(0.0)
    a = var_i / (var_i + eps)
    b = mean_i - a * mean_i
    return _box_t(a, radius) * img + _box_t(b, radius)


def bands_t(img, radius: int = DEFAULT_RADIUS, eps: float = DEFAULT_EPS,
            texture_radius: int = DEFAULT_TEXTURE_RADIUS):
    """四条带精确划分（GPU 生产版），与 bands_np 逐句同语义。"""
    rf = int(texture_radius)
    blur = _box_t(img, rf)
    tex = img - blur
    low1 = guided_t(blur, radius, eps)
    mid = blur - low1
    base = guided_t(low1, radius * 2, eps * 4.0)
    return base, low1 - base, mid, tex


def combine_t(base, broad, mid, tex, broad_gain: float, mid_gain: float,
              detail_gain: float):
    """逐点乘加重组：与 combine_np 同式。分带只依赖 (r, eps, rf)，
    所以拖“匀肤/细节/肌理”三个滑块时只需要重跑这一句（实测产品档 0.5 ms 量级），
    不必回到 4.5 ms 的分带。"""
    return base + broad * float(broad_gain) + mid * float(mid_gain) + tex * float(detail_gain)


def filter_t(img, radius: int = DEFAULT_RADIUS, eps: float = DEFAULT_EPS,
             detail_gain: float = DEFAULT_DETAIL_GAIN, mid_gain: float = DEFAULT_MID_GAIN,
             broad_gain: float = DEFAULT_BROAD_GAIN,
             texture_radius: int = DEFAULT_TEXTURE_RADIUS):
    """与 strength 无关的滤波链（GPU 生产版），与 filter_np 逐句同语义。

    这是 M1-3c 「拖滑块零推理」的全部依据：实测 672×848 这一句 4.48 ms，而把结果
    常驻后每帧只重算混合是 0.09 ms。缓存它不是一个近似——retouch_t 用的就是同一个
    张量与同一个表达式，因此逐字节相等（实测 14 个强度点全 0 LSB，含掩膜通道）。
    """
    return combine_t(*bands_t(img, radius, eps, texture_radius),
                     broad_gain, mid_gain, detail_gain)


def retouch_t(img, strength: float, radius: int = DEFAULT_RADIUS, eps: float = DEFAULT_EPS,
              detail_gain: float = DEFAULT_DETAIL_GAIN, mid_gain: float = DEFAULT_MID_GAIN,
              broad_gain: float = DEFAULT_BROAD_GAIN,
              texture_radius: int = DEFAULT_TEXTURE_RADIUS):
    return (1.0 - strength) * img + strength * filter_t(
        img, radius, eps, detail_gain, mid_gain, broad_gain, texture_radius)


def retouch_masked_t(img, weight, strength: float, radius: int = DEFAULT_RADIUS,
                     eps: float = DEFAULT_EPS, detail_gain: float = DEFAULT_DETAIL_GAIN,
                     mid_gain: float = DEFAULT_MID_GAIN,
                     broad_gain: float = DEFAULT_BROAD_GAIN,
                     texture_radius: int = DEFAULT_TEXTURE_RADIUS):
    """GPU 生产版逐像素强度磨皮，与 retouch_masked_np 逐句同语义。

    掩膜只加权混合，不改滤波结果本身——所以 `filter_t` 那一份常驻缓存对全图与
    分通道两条路都适用，不必每个通道各存一张。
    """
    return mix_masked(img, filter_t(img, radius, eps, detail_gain, mid_gain,
                                    broad_gain, texture_radius), strength, weight)


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
