"""消除笔（点修/祛瑕）的修补算子：多尺度归一化卷积填充 + 各向异性扩散精修。

为什么这一轮不直接把生成式模型放上来（与决策 6/15 一致）：
* **交互热路径不许有推理**——这条已经被 M1-3c 用数据钉死（滤波挪出热路径换来 ≥59 fps）。
  消除笔是**事件驱动**：只在松手那一刻算一次，算完结果常驻，拖滑块期间不再重算。
* 权重不入库（决策 9），本机也不能下载。所以先把**能当场证伪的确定性算子**做扎实：
  它有独立的 CPU 参考实现（float64）、有可量化的还原精度、有逐字节不变式；
  生成式后端（LaMa）走 `ops/lama.py` 的同一个接口与同一个事件调度，权重到位即插。

约定与 ops/guided 完全一致：图像 float32、(B,C,H,W)、值域 [0,1]；
`weight` 是 (B,1,H,W) 的修补覆盖度 [0,1]（画笔羽化后的结果），**不是二值抠图**。

三条必须成立的不变式（全部有对应用例）：
1. `weight=0` 时输出与输入**逐字节相等**——与 strength=0 恒等同一条承诺，靠同一个
   混合式 `(1-w)*fill + w*img` 保证（IEEE 里 `0*有限值 = 0`）；前提是 fill 有限，
   所以产出非有限值当场拒绝，绝不写进常驻缓存（M1-3c 的 eps=0 教训）。
2. 未被画笔覆盖的像素在 fill 里也逐字节等于原值：push-pull 的每一层都用已知像素钉住，
   扩散步每步重新钉。
3. numpy 参考与 torch 生产必须同语义——池化/上采样都用 reshape 与 repeat 这种
   **无插值歧义**的写法，两版逐句对得上，不是"看着差不多"。
"""

from __future__ import annotations

import math

import numpy as np

try:
    import torch
    import torch.nn.functional as F
    _HAS_TORCH = True
except Exception:          # 与 ops.guided 同一约定：没装 torch 也要能 import
    torch = None
    F = None
    _HAS_TORCH = False

from .guided import _box_np, _box_t, mix_masked      # 同一套积分图盒式滤波，不另写一份

# 归一化卷积的除零保护：w 是覆盖度的补（已知度），池化后会变小
_W_EPS = 1e-6


def auto_levels(h: int, w: int, min_side: int = 4) -> int:
    """金字塔层数：缩到短边不小于 min_side 为止，并夹在 [1, 8]。

    层数太少，大洞的核心区域收不到远距离信息（填成一片糊）；太多则小痘印也要跑八层，
    事件驱动的那一次成本白付。所以按图幅给，而不是固定值。
    """
    side = max(min(h, w), 2)
    lv = int(math.floor(math.log2(side / float(min_side)))) if side >= min_side * 2 else 0
    return max(1, min(8, lv))


def hole_extent(weight: np.ndarray) -> int:
    """覆盖区的最大边长（像素）；无覆盖返 0。

    收 (H,W) 也收 (…,H,W)（内部辅助函数，调用方手里常常是带批次维的那份）：
    只批 2 维会把 `ValueError: too many values to unpack` 这种无信息堆栈留给调用方。
    """
    a = np.asarray(weight) > 0
    if a.ndim > 2:
        a = a.reshape((-1,) + a.shape[-2:]).any(axis=0)
    ys, xs = np.nonzero(a)
    if ys.size == 0:
        return 0
    return int(max(ys.max() - ys.min() + 1, xs.max() - xs.min() + 1))


def levels_for(hole_px: int, crop_h: int, crop_w: int) -> int:
    """金字塔层数由**洞的尺寸**定，而不是由裁块或整幅的尺寸定。

    这不是理论推导而是实测归因出来的（探针 5）：半径 50 的洞在 251×251 裁块上
    按 `auto_levels(裁块)`=5 跑，孔内 MAE 从 10.78 跳到 61.32 LSB（悬崖）；
    换成整幅层数 7 就是 11.47。原因是金字塔要把洞缩到≈单像素，边界信息才能
    一路传到洞中心；层数不够时最粗层比洞还大，中心只能拿到 0/0 附近的无信号值。

    上限是 `ceil(log2(裁块短边))`——再深裁块就缩没了，而不是 `auto_levels(裁块)`：
    后者正是把质量坑踩出来的那个写法（251 裁块上 auto=5、而洞需要 7）。
    """
    need = int(math.ceil(math.log2(max(int(hole_px), 2))))
    cap = int(math.ceil(math.log2(max(min(int(crop_h), int(crop_w)), 2))))
    return max(1, min(need, cap))


# ------------------------------------------------------------------ numpy 参考
def _pad_even_np(x: np.ndarray, value: float) -> np.ndarray:
    """奇数尺寸补到偶数（池化要两两配对）。右/下各补一行一列。"""
    h, w = x.shape[-2], x.shape[-1]
    ph, pw = h % 2, w % 2
    if not (ph or pw):
        return x
    return np.pad(x, ((0, 0), (0, 0), (0, ph), (0, pw)), mode="constant", constant_values=value)


def _pool2_np(x: np.ndarray) -> np.ndarray:
    """2×2 非重叠均值池化（reshape 写法：与 torch 版逐元素同序，无插值歧义）。"""
    b, c, h, w = x.shape
    return x.reshape(b, c, h // 2, 2, w // 2, 2).mean(axis=(3, 5))


def _up2_np(x: np.ndarray, h: int, w: int) -> np.ndarray:
    """双线性 2× 上采样后裁回目标尺寸（补齐的那半格不要）。

    采样坐标公式与 torch 的 `align_corners=False` 逐字一致：
    `src = (dst + 0.5) * scale - 0.5`，夹到 [0, n-1]，`w = src - floor(src)`。
    为什么不用最近邻：实测最近邻会在孔里留下 2^k 的方块状条纹（半径 8 的痘印
    在 levels=8 下就是 64 px 方块），双线性能把这个消除掉。
    """
    ih, iw = x.shape[-2], x.shape[-1]
    yv = np.clip((np.arange(h, dtype=np.float64) + 0.5) * (ih / h) - 0.5, 0, ih - 1)
    xv = np.clip((np.arange(w, dtype=np.float64) + 0.5) * (iw / w) - 0.5, 0, iw - 1)
    y0 = np.floor(yv).astype(np.int64); y1 = np.minimum(y0 + 1, ih - 1)
    x0 = np.floor(xv).astype(np.int64); x1 = np.minimum(x0 + 1, iw - 1)
    fy = (yv - y0).astype(x.dtype); fx = (xv - x0).astype(x.dtype)
    # 广播得手动整形：fy 是 (h,)，直接乘到 (B,C,h,w) 会对齐到最后一维 w 上去
    fxs = fx.reshape(*([1] * (x.ndim - 1)), -1)
    fys = fy.reshape(*([1] * (x.ndim - 2)), -1, 1)
    hx = x[..., x0] * (1.0 - fxs) + x[..., x1] * fxs            # 先横向： (B,C,ih,w)
    return hx[..., y0, :] * (1.0 - fys) + hx[..., y1, :] * fys   # 再纵向： (B,C,h,w)


def _pm_step_np(out: np.ndarray, known_img: np.ndarray, weight: np.ndarray,
                k: float, dt: float) -> np.ndarray:
    """一步 Perona–Malik 各向异性扩散（边梯度决定电导），再把已知像素钉回去。

    电导按**边**算而不是按像素算：`c_E = exp(-(|x[i,j+1]-x[i,j]|/k)^2)`。按像素算会
    在同一个像素的四个方向上用同一个电导，跨边与不跨边分不清，扩散会把原图边缘拖平。
    边界用复制边界（与 _box 同一思路），不引入新的黑边。
    """
    p = np.pad(out, ((0, 0), (0, 0), (1, 1), (1, 1)), mode="edge")
    dE = p[..., 1:-1, 2:] - out
    dW = p[..., 1:-1, :-2] - out
    dS = p[..., 2:, 1:-1] - out
    dN = p[..., :-2, 1:-1] - out
    kk = max(float(k), 1e-6)
    flux = ((np.exp(-(np.abs(dE) / kk) ** 2) * dE) + (np.exp(-(np.abs(dW) / kk) ** 2) * dW)
            + (np.exp(-(np.abs(dS) / kk) ** 2) * dS) + (np.exp(-(np.abs(dN) / kk) ** 2) * dN))
    out = out + dt * flux
    return weight * out + (1.0 - weight) * known_img


def _diffuse_np(fill: np.ndarray, known: np.ndarray, weight: np.ndarray,
                kappa: float, iters: int, dt: float) -> np.ndarray:
    """孔内各向异性扩散（显式 Jacobi），已知像素每步钉回原值。

    dt 必须 ≤ 0.25：四邻域显式格式超过这个值就发散（实测 dt=0.3 时孔内出现振荡条纹）。
    """
    if not 0.0 < float(dt) <= 0.25:
        raise ValueError(f"refine_dt={dt} 不在 (0, 0.25]：四邻域显式扩散会发散")
    out = fill
    for _ in range(iters):
        out = _pm_step_np(out, known, weight, kappa, dt)
    return out


def inpaint_np(img: np.ndarray, weight: np.ndarray, levels: int = 0,
               smooth_iters: int = 1, refine_iters: int = 2,
               refine_dt: float = 0.24, kappa: float = 0.06) -> np.ndarray:
    """修补的**参考实现**（CPU，建议传 float64）。与 inpaint_t 逐句同语义。

    返回的不是 fill 本身，而是 `(1-weight)*fill + weight*img` 之后的成图：
    这样 weight=0 的像素逐字节等于 img（不变式 1 由表达式给出，不靠后处理）。
    """
    img = np.asarray(img)
    weight = np.asarray(weight)
    if img.ndim != 4 or weight.ndim != 4 or weight.shape[0] != img.shape[0] or weight.shape[1] != 1:
        raise ValueError(f"形状应为 img (B,C,H,W) 与 weight (B,1,H,W)，得到 {img.shape}/{weight.shape}")
    if not (float(weight.min()) >= 0.0 and float(weight.max()) <= 1.0):
        raise ValueError(f"weight 必须在 [0,1]（画笔覆盖度），实际 [{float(weight.min())}, {float(weight.max())}]")
    if img.dtype != weight.dtype:
        raise ValueError(f"img 与 weight 必须同精度（参考实现建议 float64）：{img.dtype}/{weight.dtype}")
    b, c, h, w = img.shape
    lv = int(levels) if int(levels) > 0 else levels_for(hole_extent(weight), h, w)
    known = 1.0 - weight                      # 已知度：与画笔覆盖互补

    # ---- push：逐层做覆盖度加权均值（归一化卷积），层数由图幅决定
    xs, ws = [img * known], [known]
    for _ in range(lv):
        xp, wp = xs[-1], ws[-1]
        if xp.shape[-2] <= 2 or xp.shape[-1] <= 2:
            break
        xs.append(_pool2_np(_pad_even_np(xp, 0.0)))
        ws.append(_pool2_np(_pad_even_np(wp, 0.0)))
        if xs[-1].shape[-2] <= 2 or xs[-1].shape[-1] <= 2:
            break
    n = len(xs) - 1

    # ---- pull：从最粗层回推，每层先用已知值钉住，再在孔内跑几轮热扩散
    cur_out = xs[n] / np.maximum(ws[n], _W_EPS)        # 最粗层没有更粗的可借，直接归一化
    for k in range(n - 1, -1, -1):
        xk, wk = xs[k], ws[k]
        known_val = xk / np.maximum(wk, _W_EPS)
        up = _up2_np(cur_out, xk.shape[-2], xk.shape[-1])
        fill = (1.0 - wk) * up + wk * known_val
        for _ in range(max(int(smooth_iters), 0)):
            fill = (1.0 - wk) * _box_np(fill, 1) + wk * known_val
        cur_out = fill
    fill = cur_out

    # ---- refine：全分辨率各向异性扩散，只在孔内，跨不过原图边缘
    it = max(int(refine_iters), 0)
    if it:
        fill = _diffuse_np(fill, img, weight, kappa, it, refine_dt)
    if not np.isfinite(fill).all():
        raise ValueError("修补产出非有限值，拒绝返回（常驻缓存一旦被写坏会长期作恶）")
    # weight 就是画笔覆盖度：覆盖处取 fill，未覆盖处逐字节取原图。写反了会得到
    # “痘印永远擦不掉”（探针里实测过：孔内 MAE 恰为 0），所以这一行必须有测试钉住。
    return weight * fill + (1.0 - weight) * img


# ------------------------------------------------------------------ torch 生产
def _pad_even_t(x, value: float):
    h, w = x.shape[-2], x.shape[-1]
    ph, pw = h % 2, w % 2
    if not (ph or pw):
        return x
    return F.pad(x, (0, pw, 0, ph), mode="constant", value=value)


def _pool2_t(x):
    b, c, h, w = x.shape
    return x.reshape(b, c, h // 2, 2, w // 2, 2).mean(dim=(3, 5))


def _up2_t(x, h: int, w: int):
    """双线性上采样到 (h,w)，与 _up2_np 同一采样公式（align_corners=False）。"""
    return F.interpolate(x.float(), size=(h, w), mode="bilinear", align_corners=False).to(x.dtype)


def _pm_step_t(out, known_img, weight, k: float, dt: float):
    p = F.pad(out, (1, 1, 1, 1), mode="replicate")
    dE = p[..., 1:-1, 2:] - out
    dW = p[..., 1:-1, :-2] - out
    dS = p[..., 2:, 1:-1] - out
    dN = p[..., :-2, 1:-1] - out
    kk = max(float(k), 1e-6)
    flux = ((torch.exp(-(dE.abs() / kk) ** 2) * dE) + (torch.exp(-(dW.abs() / kk) ** 2) * dW)
            + (torch.exp(-(dS.abs() / kk) ** 2) * dS) + (torch.exp(-(dN.abs() / kk) ** 2) * dN))
    out = out + dt * flux
    return weight * out + (1.0 - weight) * known_img


def _diffuse_t(fill, known, weight, kappa: float, iters: int, dt: float):
    if not 0.0 < float(dt) <= 0.25:
        raise ValueError(f"refine_dt={dt} 不在 (0, 0.25]：四邻域显式扩散会发散")
    out = fill
    for _ in range(iters):
        out = _pm_step_t(out, known, weight, kappa, dt)
    return out


def inpaint_t(img, weight, levels: int = 0, smooth_iters: int = 1, refine_iters: int = 2,
              refine_dt: float = 0.24, kappa: float = 0.06):
    """修补的**生产实现**（GPU）。与 inpaint_np 逐句同语义，同一组超参。

    事件驱动：一次调用 = 一次完整的多尺度填充 + 扩散，产出有限值才允许写常驻。
    """
    if not _HAS_TORCH:
        raise RuntimeError("torch 未安装，无法走 GPU 修补通路")
    if img.ndim != 4 or weight.ndim != 4 or weight.shape[1] != 1 or weight.shape[0] != img.shape[0]:
        raise ValueError(f"形状应为 img (B,C,H,W) 与 weight (B,1,H,W)，得到 {img.shape}/{weight.shape}")
    if not (float(weight.min()) >= 0.0 and float(weight.max()) <= 1.0):
        raise ValueError(f"weight 必须在 [0,1]（画笔覆盖度），实际 [{float(weight.min())}, {float(weight.max())}]")
    b, c, h, w = img.shape
    # 洞的尺寸跨批/跨通道取**并集**，与 numpy 参考实现的 `hole_extent` 同一句：
    # 只取 weight[0,0] 会在 B>1 或多通道权重下与参考实现悄悄分叉（而两边的文档
    # 写的都是“逐句同语义”）。B=1 时两种归约完全等价。
    m = weight > 0
    if m.ndim > 2:
        m = m.reshape((-1,) + tuple(m.shape[-2:])).any(dim=0)
    nz = torch.nonzero(m)
    hole = int(max(nz[:, 0].max() - nz[:, 0].min() + 1, nz[:, 1].max() - nz[:, 1].min() + 1)) \
        if nz.numel() else 0
    lv = int(levels) if int(levels) > 0 else levels_for(hole, h, w)
    known = 1.0 - weight

    xs, ws = [img * known], [known]
    for _ in range(lv):
        xp, wp = xs[-1], ws[-1]
        if xp.shape[-2] <= 2 or xp.shape[-1] <= 2:
            break
        xs.append(_pool2_t(_pad_even_t(xp, 0.0)))
        ws.append(_pool2_t(_pad_even_t(wp, 0.0)))
        if xs[-1].shape[-2] <= 2 or xs[-1].shape[-1] <= 2:
            break
    n = len(xs) - 1

    cur_out = xs[n] / torch.clamp(ws[n], min=_W_EPS)      # 最粗层直接归一化
    for k in range(n - 1, -1, -1):
        xk, wk = xs[k], ws[k]
        known_val = xk / torch.clamp(wk, min=_W_EPS)
        up = _up2_t(cur_out, xk.shape[-2], xk.shape[-1])
        fill = (1.0 - wk) * up + wk * known_val
        for _ in range(max(int(smooth_iters), 0)):
            fill = (1.0 - wk) * _box_t(fill, 1) + wk * known_val
        cur_out = fill
    fill = cur_out

    it = max(int(refine_iters), 0)
    if it:
        fill = _diffuse_t(fill, img, weight, kappa, it, refine_dt)
    if not torch.isfinite(fill).all():
        raise ValueError("修补产出非有限值，拒绝返回（常驻缓存一旦被写坏会长期作恶）")
    return weight * fill + (1.0 - weight) * img


# ------------------------------------------------------------------ 掩膜工具
def mask_bbox(weight: np.ndarray, pad: int = 32, grow: float = 1.5) -> tuple | None:
    """从覆盖度算“需要重算的矩形”（含边距），无覆盖时返 None。

    为什么必须裁块：一次点击只盖几十像素，而 push-pull 要跑整幅金字塔。
    实测 2400×1600 整幅跑“平滑1+PM6”要 114 ms，而裁到痘印周围只几毫秒——
    事件驱动的“一次”能不能做到无感，全看这一步。

    边距不是可有可无的：金字塔会把远处信息带进来，边距太小等于让模型拿更少的
    上下文猜同一个洞，质量会实测变差。取 `max(pad, grow × 洞的最大半径)`：
    小洞用固定下限，大洞按比例扩，两者都不会把边距当质量牺牲。
    """
    a = np.asarray(weight)
    if a.ndim > 2:
        a = a.reshape((-1,) + a.shape[-2:]).max(axis=0)
    if a.ndim != 2:
        raise ValueError(f"mask_bbox 要 (H,W)（或可压成 (H,W)）的覆盖度，得到 {np.asarray(weight).shape}")
    ys, xs = np.nonzero(a > 0)
    if ys.size == 0:
        return None
    h, w = a.shape
    r = max(int(ys.max() - ys.min()), int(xs.max() - xs.min())) / 2.0
    m = int(max(pad, grow * r))
    return (max(0, int(ys.min()) - m), min(h, int(ys.max()) + 1 + m),
            max(0, int(xs.min()) - m), min(w, int(xs.max()) + 1 + m))


def crop_apply_t(img, box, fill):
    """把裁块结果写回整幅：裁块内未覆盖的像素本来就逐字节等于原值，所以写回安全。"""
    y0, y1, x0, x1 = box
    out = img.clone()
    out[..., y0:y1, x0:x1] = fill
    return out


def feather_np(mask: np.ndarray, radius: int = 2) -> np.ndarray:
    """把二值画笔覆盖软化成连续的羽化覆盖度（与 face.skin_mask_np 同一手法：盒式 + 截断）。

    羽化是为了消除"贴边一圈硬接缝"，但它不改不变式 1：0 覆盖处仍是 0。
    """
    m = np.asarray(mask)
    if m.ndim != 2:
        raise ValueError(f"feather_np 要 (H,W) 的二值/覆盖度画笔，得到 {m.shape}；"
                         "带批次维的张量请先取 [0, 0]")
    m = (m > 0).astype(np.float32)
    r = max(int(radius), 0)
    if r == 0:
        return m
    soft = _box_np(m[None, None], r)[0, 0] * (2.0 * r + 1) ** 2 / 2.0
    return np.clip(soft, 0.0, 1.0)


def mask_to_rle(weight: np.ndarray) -> list:
    """(H,W) 覆盖度（0..255 uint8 或 0..1 float）→ 行程编码 [[y, x0, len, value255], ...]。

    控制通道是 JSON lines，二值 mask 里绝大多数是空白，逐像素传等于把 2 MB 塞进文本行；
    只传"有笔的地方"，一次痘印点击通常是几十条行程。

    为什么不是逐像素循环：上一版是 `for y / while x` 的双层 Python 循环，实测
    在 672×848 上 79 ms、1024×1280 上 187 ms（打靶里那个“解码”分段几乎全是它），
    比修补本身还贵一个量级。现在向量化成“找行内变化点”，成本降到毫秒级且与图幅
    线性。UI 侧（brush.ts）是同构算法，那边也有同样的坑，一并改掉。
    """
    a = np.asarray(weight)
    if a.dtype != np.uint8:
        a = np.clip(a, 0.0, 1.0).astype(np.float32)
        a = np.round(a * 255.0).astype(np.uint8)
    if a.ndim != 2:
        raise ValueError(f"mask_to_rle 要 (H,W) 的覆盖度，得到 {a.shape}")
    h, w = a.shape
    if w == 0 or h == 0:
        return []
    # 行程起点：行首“与非 0 不等”，其余“与本行前一个像素不等”。这样同一段内值必恒定，
    # 而且行程永不跨行（行首总是一个新段的开始，哪怕上一行末尾恰好同值）。
    head = np.empty((h, w), dtype=bool)
    head[:, 0] = a[:, 0] != 0
    head[:, 1:] = a[:, 1:] != a[:, :-1]
    flat = a.reshape(-1)
    idx = np.flatnonzero(head.reshape(-1))
    if idx.size == 0:
        return []
    y = idx // w
    nxt = np.append(idx[1:], h * w)
    same_row = (nxt // w) == y                     # 下一个起点还在本行 → 行程到它为止
    ends = np.where(same_row, nxt, (y + 1) * w)    # 否则直到行尾
    vals = flat[idx].astype(int)
    lens = ends - idx
    keep = vals != 0
    return [[int(yy), int(xx), int(ll), int(vv)]
            for yy, xx, ll, vv in zip(y[keep], idx[keep] % w, lens[keep], vals[keep])]


def mask_from_rle(rle: list, h: int, w: int) -> np.ndarray:
    """RLE → (H,W) uint8 覆盖度。越界与非法值当场拒绝，不静默截断。"""
    if h <= 0 or w <= 0:
        raise ValueError(f"掩膜尺寸非法: {h}x{w}")
    a = np.zeros((h, w), dtype=np.uint8)
    for i, run in enumerate(rle):
        if len(run) != 4:
            raise ValueError(f"第 {i} 条码不是 [y, x, len, value] 四元组: {run!r}")
        y, x, ln, v = (int(run[0]), int(run[1]), int(run[2]), int(run[3]))
        if not (0 <= y < h):
            raise ValueError(f"第 {i} 条码越界：y={y} 不在 [0,{h})")
        if not (0 <= x < w) or ln <= 0 or x + ln > w:
            raise ValueError(f"第 {i} 条码越界：x={x} len={ln} 超出 [0,{w})")
        if not (0 <= v <= 255):
            raise ValueError(f"第 {i} 条码值非法：{v} 不在 [0,255]")
        a[y, x:x + ln] = v
    return a


def rle_byte_cost(rle: list) -> int:
    """给报表用：这条命令在 JSON lines 上大概占多少字节（压缩比的决定性证据）。"""
    return sum(24 for _ in rle)
