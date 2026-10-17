"""CFA 插值（去马赛克）——RAW 进显卡的第一站。

约定与 guided.py 同一条：numpy 版是**参考实现**（跑在 CPU，用于对拍），torch 版是
**生产实现**（(B,C,H,W)、float32）。两者必须在 ≤1 LSB 内一致，否则不许上生产。

为什么用「邻域均值 + 站位掩膜」而不是更花哨的 AHD/拉普拉斯：
* 判据说了算。产品代理档只有 576 kpx（M1-1 钉的字节预算），在这个尺寸上双线性与
  梯度校正版的差别被降采样吃掉了一半，而多出来的两遍梯度归约要在每帧热路径上付费；
  RAW 的解码是一次性成本，可它也要付。先按量得到的误差选最便宜的那个，把「边缘
  zippering 到什么程度」写成跑靶读数而不是凭印象升级算法。
* 站位掩膜必须与像素**一起**做边缘复制填充：只填像素不填掩膜，边界一圈就会把
  「这一格是什么颜色」和「这一格的值是多少」配错对，报出一圈绿/紫描边。
"""

from __future__ import annotations

import numpy as np

try:
    import torch
    import torch.nn.functional as F
    _HAS_TORCH = True
except Exception:  # torch 未装（CI 的 engine job 只装 numpy + pytest）
    torch = None
    F = None
    _HAS_TORCH = False


def pattern_channels(pattern, dims) -> int:
    """CFAPattern 里出现的颜色个数（3=RGB 族，4=RGBE/CMYK 族）。"""
    return int(max(pattern)) + 1


def site_map(pattern, dims, h: int, w: int, phase=(0, 0)) -> np.ndarray:
    """(h, w) 的整数站位图：每个像素是哪个颜色。原点 = ActiveArea 左上角（规范写死）。

    `phase` 是「这一帧裁剪后，(0,0) 其实站在排阵的哪一格」：DefaultCropOrigin 不是
    (0,0)（或 ActiveArea 不是整幅）时，裁片的第一行/列并不是排阵的起始色。相位丢了
    就是红蓝互换——真图上量到的是 mean|Δ| 53 LSB 与逐通道 ±100 的均值偏移，
    而图像看上去「只是有点奇怪」。

    不能用 `np.roll` 实现相位：roll 是把裁片自己的首行接到尾行（`full[(r+py) % h]`），
    只有当 h 正好是排阵周期整数倍时才与真排阵一致；奇数宽高（真机的 ActiveArea/DefaultCrop 很常见）
    会把最后一行/列的站位接错。改成多铺一份再按相位切。
    """
    ph, pw = int(dims[0]), int(dims[1])
    if ph <= 0 or pw <= 0:
        raise ValueError(f"CFARepeatPatternDim 非法：{dims}")
    p = np.array(pattern, dtype=np.uint8).reshape(ph, pw)
    if p.shape != (ph, pw):
        raise ValueError(f"CFAPattern 长度 {len(pattern)} 与 RepeatPatternDim {dims} 不符")
    py, px = int(phase[0]) % ph, int(phase[1]) % pw
    big = np.tile(p, (int(np.ceil((h + py) / ph)), int(np.ceil((w + px) / pw))))
    return big[py:py + h, px:px + w]


def demosaic_np(lin: np.ndarray, pattern, dims, dtype=np.float64, phase=(0, 0)) -> np.ndarray:
    """(H, W, 1) 的 mosaic → (H, W, C) 三/四色。双线性：邻域内同色点取均值。

    邻域窗口是 (2·ph−1)×(2·pw−1)，所以对 2×2 的 Bayer 就是 3×3（每个色有 2~4 个
    邻居）；对 2×4 / 4×2 的四色排阵自动扩到对应的窗。窗口外的像素按边缘复制。
    """
    if lin.ndim != 3 or lin.shape[2] != 1:
        raise ValueError(f"demosaic_np 要 (H,W,1) 的 mosaic，得到 {lin.shape}")
    h, w = lin.shape[0], lin.shape[1]
    ph, pw = int(dims[0]), int(dims[1])
    ch = pattern_channels(pattern, dims)
    x = lin[..., 0].astype(dtype)
    sites = site_map(pattern, dims, h, w, phase)
    ky, kx = ph - 1, pw - 1
    xp = np.pad(x, ((ky, ky), (kx, kx)), mode="edge")
    sp = np.pad(sites, ((ky, ky), (kx, kx)), mode="edge")
    out = np.zeros((h, w, ch), dtype=dtype)
    for c in range(ch):
        num = np.zeros((h, w), dtype=dtype)
        den = np.zeros((h, w), dtype=dtype)
        for dy in range(2 * ph - 1):
            for dx in range(2 * pw - 1):
                sel = sp[dy:dy + h, dx:dx + w] == c
                if not sel.any():
                    continue
                num += xp[dy:dy + h, dx:dx + w] * sel
                den += sel
        out[..., c] = np.where(den > 0, num / np.maximum(den, 1), 0.0)
    return out


def demosaic_t(t, pattern, dims, phase=(0, 0)):
    """torch 版：深度可分离卷积一次算完所有色，(B,1,H,W) → (B,C,H,W)。

    与 numpy 版同一条式子：num = conv(x·mask_c, ones)，den = conv(mask_c, ones)，
    out = num/den。填充同样用 replicate，像素与掩膜一起填。
    """
    if not _HAS_TORCH:
        raise RuntimeError("没装 torch，demosaic_t 不可用（请用 demosaic_np 参考实现）")
    if t.dim() != 4 or t.shape[1] != 1:
        raise ValueError(f"demosaic_t 要 (B,1,H,W)，得到 {tuple(t.shape)}")
    b, _, h, w = t.shape
    ph, pw = int(dims[0]), int(dims[1])
    ch = pattern_channels(pattern, dims)
    sites = site_map(pattern, dims, h, w, phase)
    mask = torch.from_numpy((sites[:, :, None] == np.arange(ch, dtype=np.uint8)[None, None, :])
                            .astype("float32")).permute(2, 0, 1)[None].to(t.device)
    mask = mask.expand(b, -1, -1, -1)                      # (B,C,H,W)
    ky, kx = ph - 1, pw - 1
    xp = F.pad(t, (kx, kx, ky, ky), mode="replicate")
    mp = F.pad(mask, (kx, kx, ky, ky), mode="replicate")
    ones = torch.ones((ch, 1, 2 * ph - 1, 2 * pw - 1), device=t.device, dtype=t.dtype)
    num = F.conv2d(xp * mp, ones, groups=ch)
    den = F.conv2d(mp, ones, groups=ch)
    return num / den.clamp_min(1.0)


def decimate_np(lin: np.ndarray, pattern, dims, f: int, dtype=np.float64,
                phase=(0, 0)) -> np.ndarray:
    """不插值的降采样：按 f×f 块把每个颜色各自的样本求均值 → (H/f, W/f, C)。

    为什么需要它：代理档与缩略图不该为一张 24 MP 的 mosaic 跑一遍全幅 demosaic
    （CPU 上那是秒级的一次性成本），而块内均值与先插值再缩放**光度上等价**：
    每个颜色的样本一个不落地进了它该去的那个输出像素。2×2 Bayer 取 f=2 时，一个
    块正好是 R,G,G,B 各一个——不猜、不插。
    """
    if lin.ndim != 3 or lin.shape[2] != 1:
        raise ValueError(f"decimate_np 要 (H,W,1)，得到 {lin.shape}")
    h, w = lin.shape[0], lin.shape[1]
    ch = pattern_channels(pattern, dims)
    sites = site_map(pattern, dims, h, w, phase)
    x = lin[..., 0].astype(dtype)
    bh, bw = h // f, w // f
    if bh < 1 or bw < 1:
        raise ValueError(f"降采样因子 {f} 比画面还大（{h}×{w}）")
    xb = x[:bh * f, :bw * f].reshape(bh, f, bw, f).transpose(0, 2, 1, 3)
    sb = sites[:bh * f, :bw * f].reshape(bh, f, bw, f).transpose(0, 2, 1, 3)
    out = np.zeros((bh, bw, ch), dtype=dtype)
    for c in range(ch):
        sel = (sb == c).astype(dtype)
        den = sel.sum(axis=(2, 3))
        num = (xb[:, :, :, :] * sel).sum(axis=(2, 3))
        out[..., c] = np.where(den > 0, num / np.maximum(den, 1e-12), 0.0)
    return out


def decimate_t(t, pattern, dims, f: int, phase=(0, 0)):
    """torch 版的 decimate_np：pool(x·mask)/pool(mask)，(B,1,H,W) → (B,C,H/f,W/f)。"""
    if not _HAS_TORCH:
        raise RuntimeError("没装 torch，decimate_t 不可用")
    b, s, h, w = t.shape
    if s != 1:
        raise ValueError(f"decimate_t 要 (B,1,H,W)，得到 {tuple(t.shape)}")
    ch = pattern_channels(pattern, dims)
    sites = site_map(pattern, dims, h, w, phase)
    mask = torch.from_numpy((sites[:, :, None] == np.arange(ch, dtype=np.uint8)[None, None, :])
                            .astype("float32")).permute(2, 0, 1)[None].to(t.device)
    mask = mask.expand(b, -1, -1, -1)
    num = F.avg_pool2d(t * mask, f, f)
    den = F.avg_pool2d(mask, f, f)
    return num / den.clamp_min(1e-12)


def apply_matrix_np(cam: np.ndarray, mat: np.ndarray) -> np.ndarray:
    """(...,n) @ (3,n).T ——行向量约定的矩阵乘，CPU 与 GPU 用同一个写法。"""
    return cam @ np.asarray(mat, dtype=np.float64).T


def apply_matrix_t(t, mat):
    return t @ torch.as_tensor(mat, dtype=t.dtype, device=t.device).T
