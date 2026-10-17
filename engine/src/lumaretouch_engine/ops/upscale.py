"""放大（M7）的确定性核心：Lanczos 重采样 + 轻度锐化 + 分块等价。

为什么和 `ops/realesrgan.py`（神经网络超分）分两个文件：与 matting/birefnet 同一
条分法，理由也一样——这一条是确定性算子，有闭式核、有逐字节不变式、有 CPU↔GPU↔
第三方（Pillow）三臂对拍；那条是神经网络，没有权重就没有任何"放大后质感如何"的
质量主张可写。混在一个函数里，报表就会把"重采样没算错"和"超分质量好"塌成同一个数。

分块为什么能做到**逐字节等于整幅**（这是这一层唯一硬的验收口径）：
Lanczos 是可分离的定带滤波——每个输出像素只由 `(输入下标, 权重)` 一对对有限项决定，
权重表按整幅的全局坐标一次算好。切块时把全局下标平移成块内下标、按同一顺序累加，
每个输出像素吃的项集与运算顺序都不变，所以分块结果与整幅**逐字节同一**，不是"近似
无可见接缝"。这与消除笔/形变那些"场按整幅活"的层正相反：那些切块会改变求解域，只能
按 bbox/条带记账（见 export.py 头部），本层不需要那种妥协，所以也不接受那种妥协。

锐化单独一层而不写进重采样里：`amount=0` 必须逐字节退回纯重采样，用户把滑块归零
时拿到的就该是那个可验证的东西，而不是"某个内置默认值"。
"""

from __future__ import annotations

import numpy as np

#: 允许的放大倍率：产品口径 1/2/3/4，再大就是像素数平方涨，导出会先撞内存
SCALES = (1, 2, 3, 4)
#: Lanczos 支撑半径（核宽 2a+1=7）。a=3 是通用"高质量放大"档
DEFAULT_A = 3
#: 分块的输入边长上限（每块按 tile×tile 源像素起算，输出面积再乘 scale²）
DEFAULT_TILE = 512
MIN_TILE = 8        # 下限只为挡住病态配置；等价性用例要靠小 tile 多切几块来跑。
MAX_TILE = 4096     # 产品默认档是 DEFAULT_TILE（“峰值只随 tile 走”那条口径归它管）
#: 单幅允许的最大边长（输出侧）：4× 一张 12000px 的图不是这一层该接的事
MAX_OUT_SIDE = 32768


def check_scale(scale) -> int:
    s = int(scale)
    if s not in SCALES:
        raise ValueError(f"放大倍率只支持 {SCALES}，收到 {scale!r}")
    return s


def _sinc(x):
    """归一化 sinc：sin(πx)/(πx)，x=0 处取 1。用 πx 的精确零点避免除零抖。"""
    y = np.pi * x
    out = np.ones_like(x, dtype=np.float64)
    nz = np.abs(x) > 1e-12
    out[nz] = np.sin(y[nz]) / y[nz]
    return out


def resample_weights(out_len: int, in_len: int, a: int = DEFAULT_A):
    """一维重采样表：`(idx (out_len,K) int64, w (out_len,K) float64)`。

    像素中心对齐（`pos = (i+0.5)·in/out − 0.5`），与 torch `align_corners=False` /
    Pillow 的半格口径同一族。权重按行归一（和为 1）——这一句是给"常值图放大后仍
    是那个常值"这条不变式兜底的：不归一，直流分量会按核截断误差漂掉零点几。
    越界的抽头折到边缘像素（replicate）：与整幅一起折、与分块一起折，口径唯一。
    """
    if out_len < in_len:
        raise ValueError(f"这一层只做放大或等比（out={out_len} < in={in_len}）")
    if in_len <= 0 or out_len > MAX_OUT_SIDE:
        raise ValueError(f"边长越界：in={in_len} out={out_len}（输出上限 {MAX_OUT_SIDE}）")
    K = 2 * a + 1
    pos = (np.arange(out_len, dtype=np.float64) + 0.5) * (in_len / out_len) - 0.5
    left = np.ceil(pos - a).astype(np.int64)
    idx = left[:, None] + np.arange(K, dtype=np.int64)[None, :]
    d = pos[:, None] - idx
    x = d / a
    # L(x) = sinc(x)·sinc(x/a)，|x|≥a 处为 0（写成乘积后本身也是 0，仍显式裁一次）
    w = _sinc(d) * _sinc(x)
    w = np.where(np.abs(d) < a, w, 0.0)
    s = w.sum(axis=1, keepdims=True)
    w = w / s
    return np.clip(idx, 0, in_len - 1), w


def _apply_axis_np(img, idx, w, axis):
    """按权重表沿一个轴重采样：axis=1 宽、axis=0 高（图是 (H,W,3) 三轴）。

    累加顺序与 GPU 路一致：两路只对同一个 k 序列求和，否则 float32/float64 的差
    就不只是精度差，而是不同串式子。权重掩形按轴长出来（(out,1,1) 或 (1,out,1)），
    写死成四轴会在 (H,W,3) 上广播不起来。
    """
    K = idx.shape[1]
    out = None
    for k in range(K):
        g = np.take(img, idx[:, k], axis=axis)
        sh = [1, 1, 1]
        sh[axis] = idx.shape[0]
        term = g * w[:, k].reshape(sh)
        out = term if out is None else out + term
    return out


def upscale_np(img, scale: int = 2, a: int = DEFAULT_A) -> np.ndarray:
    """CPU 参考路：(H,W,3) uint8 → (H·s,W·s,3) uint8，可分离 Lanczos。

    先放大后取整（float64 全程），只在出口 round + clip 一次——中间每步都取整会
    把误差放大 s² 倍，那是"看着还行"但逐字节对不上的典型来源。
    """
    s = check_scale(scale)
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"upscale_np 需要 (H,W,3)，得到 {img.shape}")
    h, w = img.shape[:2]
    x = img.astype(np.float64) / 255.0
    if s == 1:
        return img.copy()
    iw, ww = resample_weights(w * s, w, a)
    ih, wh = resample_weights(h * s, h, a)
    x = _apply_axis_np(x, iw, ww, 1)   # 横向：(H, w*s, 3)
    x = _apply_axis_np(x, ih, wh, 0)   # 纵向：(h*s, w*s, 3)
    return np.clip(np.rint(x * 255.0), 0, 255).astype(np.uint8)


def _idx_w_t(device, idx, w):
    """把一张 (idx, weight) 重采样表搬到目标设备上（索引 int64、权重 float32）。"""
    import torch
    return (torch.as_tensor(idx, dtype=torch.long, device=device),
            torch.as_tensor(w, dtype=torch.float32, device=device))


def _apply_axis_t(t, idx, w, axis):
    import torch
    K = idx.shape[1]
    out = None
    for k in range(K):
        g = torch.index_select(t, axis, idx[:, k])
        sh = [1, 1, 1, 1]
        sh[axis] = idx.shape[0]
        term = g * w[:, k].reshape(sh)
        out = term if out is None else out + term
    return out.contiguous()


def upscale_t(t, scale: int = 2, a: int = DEFAULT_A):
    """GPU 生产路：(B,3,H,W) [0,1] → (B,3,H·s,W·s) [0,1]。

    权重表在 CPU 上用 float64 算好后转 float32 上传：核系数是同一个数，两路只差
    累加精度，所以与 upscale_np 的出口对拍能压到 ≤1 LSB（乘 255 取整后）。
    """
    import torch
    s = check_scale(scale)
    if t.ndim != 4 or t.shape[1] != 3:
        raise ValueError(f"upscale_t 需要 (B,3,H,W)，得到 {tuple(t.shape)}")
    if s == 1:
        return t.clone()
    b, c, h, w = t.shape
    x = t.to(torch.float32)
    iw, ww = _idx_w_t(x.device, *resample_weights(w * s, w, a))
    ih, wh = _idx_w_t(x.device, *resample_weights(h * s, h, a))
    x = _apply_axis_t(x, iw, ww, 3)
    x = _apply_axis_t(x, ih, wh, 2)
    return x.clamp(0.0, 1.0)


def upscale_tiled_t(t, scale: int = 2, tile: int = DEFAULT_TILE, a: int = DEFAULT_A,
                    progress=None):
    """分块放大：显存峰值随 tile 走，结果与 upscale_t **逐字节同一**。

    做法是"全局权重表 + 块内下标平移"：每个输出像素的 `(输入下标, 权重)` 项集与
    累加顺序都不随切法改变，因此等价性是构造出来的，不是调参调出来的。
    `tile` 是**源**图的分块边长（输出块边长 = tile·s）。
    返回 `(out_tensor, info)`，info 里的 tiles/peak_px 是"峰值只随 tile 走"的账面。
    """
    import torch
    s = check_scale(scale)
    t_in = int(tile)
    if not (MIN_TILE <= t_in <= MAX_TILE):
        raise ValueError(f"tile={tile} 越界（允许 {MIN_TILE}~{MAX_TILE}）")
    if t.ndim != 4 or t.shape[1] != 3:
        raise ValueError(f"upscale_tiled_t 需要 (B,3,H,W)，得到 {tuple(t.shape)}")
    b, c, h, w = t.shape
    out_h, out_w = h * s, w * s
    if s == 1:
        return t.clone(), {"tile": t_in, "tiles": 1, "scale": 1, "peak_px": h * w}
    x = t.to(torch.float32)
    GW, GG = resample_weights(out_w, w, a), resample_weights(out_h, h, a)
    iw, ww = _idx_w_t(x.device, *GW)
    ih, wh = _idx_w_t(x.device, *GG)
    out = torch.empty((b, c, out_h, out_w), dtype=torch.float32, device=x.device)
    tiles = 0
    peak_px = 0
    for y0 in range(0, out_h, t_in * s):
        y1 = min(y0 + t_in * s, out_h)
        # 行方向用到的输入行范围从全局权重表反查（不猜）；列范围逐块反查，比按整行
        # 取并集少一大片内存
        gi = ih[y0:y1]
        cy0, cy1 = int(gi.min().item()), int(gi.max().item()) + 1
        for x0 in range(0, out_w, t_in * s):
            x1 = min(x0 + t_in * s, out_w)
            gij = iw[x0:x1]
            cx0, cx1 = int(gij.min().item()), int(gij.max().item()) + 1
            sub = x[:, :, cy0:cy1, cx0:cx1]
            # 全局下标平移成块内下标：idx − (cy0/cx0)，落在 [0, 子幅) 内
            liy = (iw[x0:x1] - cx0).contiguous()
            lix = (ih[y0:y1] - cy0).contiguous()
            seg = _apply_axis_t(sub, liy, ww[x0:x1], 3)
            seg = _apply_axis_t(seg, lix, wh[y0:y1], 2)
            out[:, :, y0:y1, x0:x1] = seg.clamp(0.0, 1.0)
            tiles += 1
            peak_px = max(peak_px, seg.numel() // (b * c) + (cy1 - cy0) * (cx1 - cx0))
            if progress is not None:
                progress(tiles, out_h, out_w, t_in)
    return out, {"tile": t_in, "tiles": tiles, "scale": s, "peak_px": int(peak_px)}


def gaussian_kernel1d(radius: float, dtype=np.float64):
    r = max(0.0, float(radius))
    if r <= 0.0:
        return np.ones(1, dtype=dtype)
    half = max(1, int(np.ceil(3.0 * r)))
    x = np.arange(-half, half + 1, dtype=np.float64)
    k = np.exp(-(x * x) / (2.0 * r * r))
    return (k / k.sum()).astype(dtype)


def blur_np(img, radius: float) -> np.ndarray:
    """可分离高斯（边缘复制）。锐化与"低频"的口径都用它，别混进别处的实现。

    两遍各自补自己那一边的边缘：补一次再用同一个 pad 去取第二遍，列数会少 pad 个
    （第一遍已经把外圈缩回去了），那是会直接报错的坑而不是能测出来的近似错。
    """
    k = gaussian_kernel1d(radius)
    if k.size == 1:
        return img.astype(np.float64)
    h, w = img.shape[:2]
    pad = k.size // 2
    x = img.astype(np.float64)
    p = np.pad(x, ((pad, pad), (0, 0), (0, 0)), mode="edge")
    y = np.zeros((h, w, x.shape[2]), dtype=np.float64)
    for j, kv in enumerate(k):
        y += kv * p[j:j + h]
    q = np.pad(y, ((0, 0), (pad, pad), (0, 0)), mode="edge")
    z = np.zeros((h, w, x.shape[2]), dtype=np.float64)
    for j, kv in enumerate(k):
        z += kv * q[:, j:j + w]
    return z


def unsharp_np(img, radius: float = 2.0, amount: float = 0.35, threshold: float = 0.01):
    """CPU 参考路锐化：`out = img + amount·(img − blur(img))`，带阈值门限。

    阈值是给噪点的：低于 threshold 的高频差值不放大，否则暗部噪点会被一起提出来。
    全部在归一化 [0,1] 浮点上做，出口一次取整。
    """
    if amount == 0.0:
        return img.copy()
    x = img.astype(np.float64) / 255.0
    d = x - blur_np(x, radius)
    if threshold > 0:
        d = np.where(np.abs(d) < threshold, 0.0, d)
    return np.clip(np.rint((x + amount * d) * 255.0), 0, 255).astype(np.uint8)


def unsharp_t(t, radius: float = 2.0, amount: float = 0.35, threshold: float = 0.01):
    """GPU 生产路：与 unsharp_np 同式（float32，replicate padding，可分离卷积）。"""
    import torch
    import torch.nn.functional as F
    if t.ndim != 4 or t.shape[1] != 3:
        raise ValueError(f"unsharp_t 需要 (B,3,H,W)，得到 {tuple(t.shape)}")
    if amount == 0.0:
        return t.clone()
    k = gaussian_kernel1d(radius)
    if k.size == 1:
        return t.clone()
    x = t.to(torch.float32)
    ker = torch.as_tensor(k, dtype=torch.float32, device=x.device)
    pad = int(k.size // 2)
    C = x.shape[1]
    kh = ker.view(1, 1, 1, -1).repeat(C, 1, 1, 1)
    kv = ker.view(1, 1, -1, 1).repeat(C, 1, 1, 1)
    bl = F.conv2d(F.pad(x, (pad, pad, 0, 0), mode="replicate"), kh, groups=C)
    bl = F.conv2d(F.pad(bl, (0, 0, pad, pad), mode="replicate"), kv, groups=C)
    d = x - bl
    if threshold > 0:
        d = torch.where(d.abs() < float(threshold), torch.zeros_like(d), d)
    return (x + float(amount) * d).clamp(0.0, 1.0)


class Plan:
    """一次放大的全局重采样计划：表算一遍，导出按块取用。

    为什么需要这个而不直接叫 upscale_np：导出已经有一套分块（为了把图层的作用域
    算清楚），它每块只拿到**渲染后的一个补丁**，整幅渲染图从未存在过。如果为了放大
    再把整幅拼起来，"峰值只随 tile 走"当场作废。Plan 让每块拿自己那块的全局行列权重，
    把下标平移到补丁坐标里算——于是分块导出与整幅放大逐字节同一，且不要求整幅驻留。

    调用方的契约（`region` 会硬性校）：补丁必须比目标框四周至少多包 `margin_px` 个
    源像素（= 核半径 a），否则抽头会越出补丁——那就是实现说谎，不是近似。
    """

    def __init__(self, in_h: int, in_w: int, scale: int = 2, a: int = DEFAULT_A):
        self.s = check_scale(scale)
        self.a = int(a)
        self.in_h, self.in_w = int(in_h), int(in_w)
        self.out_h, self.out_w = self.in_h * self.s, self.in_w * self.s
        self.margin_px = Plan.margin_for(self.s, self.a)
        self._iw, self._ww = (resample_weights(self.out_w, self.in_w, a)
                              if self.s > 1 else (None, None))
        self._ih, self._wh = (resample_weights(self.out_h, self.in_h, a)
                              if self.s > 1 else (None, None))

    @staticmethod
    def margin_for(scale: int, a: int = DEFAULT_A) -> int:
        """导出侧唯一要拿的口径：这一倍率需要多少源像素的边。`scale=1` 不要。"""
        return 0 if check_scale(scale) == 1 else int(a)

    def region(self, patch, oy0: int, oy1: int, ox0: int, ox1: int,
               cy0: int, cx0: int) -> np.ndarray:
        """补丁 → 输出坐标里 `[oy0:oy1] × [ox0:ox1]` 那一块（uint8）。

        oy*/ox* 是**输出**下标，cy0/cx0 是补丁在源图里的左上角。累加顺序与 `full`
        同一条 k 序列，所以两者逐字节等价不是“差不多”而是“同一个数”。
        """
        if self.s == 1:
            return np.ascontiguousarray(patch[oy0 - cy0:oy1 - cy0, ox0 - cx0:ox1 - cx0])
        if patch.ndim != 3 or patch.shape[2] != 3:
            raise ValueError(f"region 需要补丁 (h,w,3)，得到 {patch.shape}")
        ih = self._ih[oy0:oy1] - cy0
        iw = self._iw[ox0:ox1] - cx0
        ph, pw = patch.shape[:2]
        if ih.min() < 0 or ih.max() >= ph or iw.min() < 0 or iw.max() >= pw:
            raise ValueError(
                f"补丁不够宽：需要源行 [{int(self._ih[oy0:oy1].min())},"
                f"{int(self._ih[oy0:oy1].max())}] 落在补丁 [{cy0},{cy0 + ph}) 内——"
                f"分块导出得给放大留 margin_px={self.margin_px} 的边")
        x = patch.astype(np.float64) / 255.0
        x = _apply_axis_np(x, np.clip(iw, 0, pw - 1), self._ww[ox0:ox1], 1)
        x = _apply_axis_np(x, np.clip(ih, 0, ph - 1), self._wh[oy0:oy1], 0)
        return np.clip(np.rint(x * 255.0), 0, 255).astype(np.uint8)

    def full(self, img) -> np.ndarray:
        """整幅一次放大。与 `upscale_np` 同一路（不另开一份实现，免得两档各自腐化）。"""
        return upscale_np(img, self.s, self.a)


def unsharp_bands_np(img, radius: float = 2.0, amount: float = 0.35,
                     threshold: float = 0.01, band: int = 512) -> np.ndarray:
    """分带锐化一整张已拼好的输出图：结果与对全图直接 `unsharp_np` 逐字节同一。

    为什么能逐字节：这里切的是**已经完整的图**，每条带上方下方都拿真像素当 halo，
    只有图的真边缘才用 replicate——那与全图做时用的是同一圈边缘值，不是近似。
    为什么要分带：×4 的 20 MP 输出是一张 80 MP 的图，float64 整幅副本就是 1.9 GB，
    分带后峰值只随 band 走。
    """
    k = gaussian_kernel1d(radius)
    if k.size == 1 or amount == 0.0:
        return img.copy()
    pad = k.size // 2
    h, w = img.shape[:2]
    out = np.empty_like(img)
    for y0 in range(0, h, int(band)):
        y1 = min(y0 + int(band), h)
        cy0, cy1 = max(y0 - pad, 0), min(y1 + pad, h)
        # 带内每一行需要的 halo 从完整图里拿真像素；图缘那侧没有 halo 可拿，
        # 但 blur 在那里本来也是 replicate，两边同口径
        strip = img[cy0:cy1]
        # blur_np 吃的是归一到 [0,1] 的浮点（与 unsharp_np 同一口径），不是 uint8 原图：
        # 递错就是拿 0–255 的模糊去减 0–1 的原值，d 整片负尽、出口被括到 0——
        # 这条就是逐字节对拍报出来的（写这一层时真的错过一次）
        sub = strip.astype(np.float64) / 255.0
        bl = blur_np(sub, radius)
        d = sub - bl
        if threshold > 0:
            d = np.where(np.abs(d) < threshold, 0.0, d)
        q = np.clip(np.rint((sub + amount * d) * 255.0), 0, 255).astype(np.uint8)
        out[y0:y1] = q[y0 - cy0:y1 - cy0]
    return out


def scale_backends() -> dict:
    """能力上报（口径与 `raw_backends` / `lama` 守卫一致，不许混报）：

    * `baseline`——确定性、无需任何外部权重，装机即可用；
    * `weights_gated`——结构已在包里，但没有按 sha256 校验的权重就不接单，
      引擎**不会**把它降级成 lanczos 冒充"AI 超分"。

    为什么这一份是常量而 `birefnet.matting_backends` 是现场算的：两边的拦住条件不是
    同一件事。抠图那边只差权重（birefnet 已接进 cmd_background，权重一到就能跑），
    所以它是**机器事实**，得现场算；而 realesrgan 除权重之外还差一件——出片环路根本
    还没调用它（`export.py` / `cmd_export` 两处都明确拒）。那是**代码事实**，在任一台
    机器上都一样，拿环境去探只会探出一个假绿灯：权重放行的机器把“递上去必被拒”
    的后端列进装机即用档，比一直说“等权重”更坏。"""
    return {
        "baseline": ["lanczos3", "lanczos3_tiled", "unsharp"],
        # 两道门禁都在它前面：权重按 sha256 放行 **且** 接进出片环路。后者还没做，
        # 所以这一档不随环境变（文案里把两件事都说清，不让“装上权重就能用”的读法替它说话）。
        "weights_gated": ["realesrgan"],
    }