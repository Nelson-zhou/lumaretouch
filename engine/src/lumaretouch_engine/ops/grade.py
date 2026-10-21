"""肤色定向调色（M3-b）：只在肤色窗口内动的 HSL 调整。

为什么它**不**走 3D LUT（`gpuspike/m3d.py` 定架构，`m3e.py` 直接量本文件的两个臂）：

    同一组参数烘进表：17³ 连续 10.2–12.9 / 量化 10–13 LSB，改动 26–28% 像素
                    33³ 连续  6.8–9.3 / 量化  7–9 LSB，改动  9–10% 像素
                    64³ 连续  4.8–6.2 / 量化  5–6 LSB，改动  3.5–4.0% 像素
    逐帧内核：与 float64 参考最大 1 LSB，而且只出现在贴量化边界的那 1.7e-6 像素上；
             在 w≥0.9999 的像素上，回算的 Δh/Δs/Δv 与夹域期望残差 ≤4.1e-06（float32 精度）。

原因是色相窗口在 RGB 空间里是一条**陡峭的边界**（同一个色相值在低饱和与高饱和处
含义完全不同），三线性插值跟不上它——而一张"平滑的色彩观"表在 33³ 上只差 2 LSB。
所以本层的分工是：**色彩观走表（ops/lut.py），肤色定向走内核（本文件）**，预设 =
一张表 + 三个数，两层各自独立、各自可关。

banding 不是选型理由（m3e 的 D 节把它证伪了）：沿穿过色相/饱和窗口边界的扇形
扫描量化后相邻样本跳级最大都是 1、≥ 2 的位置数为 0，两臂都没留下可见台阶。真正的
差别只是表路径沿那条线有 3.3–5.8 LSB 的连续偏差。（m3d 的 D 节用线性坡量二阶差分，
两臂都是 0.000，那个靶本身无效。）

窗口口径（都在真图上量过，见 skin_weight 的注释）：色相 0.025–0.045 升入、
0.100–0.125 退出，饱和与明度各一条 smoothstep 下界。总工那张图（红发 + 雀斑 +
绿贝雷 + 树叶）上：脸心 95.2% 命中、红发 14.6%、绿帽 10.5%、背景树叶 11.8%——
"只框住皮肤"这件事是分区域量出来的，不是看全图覆盖率 30% 就宣称成立。

两条结构性保证（不是经验值）：

1. **窗外逐字节等于输入**：输出是 `x + (out − x)·w`，w=0 处这个式子在 IEEE 下精确
   等于 x（`0·有限 = 0`、`x + 0 = x`）。全零参数再叠一层结构短路，一个算子都不跑。
2. **零改动不许留半截状态**：参数先过 `check_params`（有限 + 范围）再写进常驻层，
   与 set_strength / set_deform_amounts / set_lut 同一条铁律。

它在渲染链上的位置是链尾（`apply_grade(apply_lut(apply_deform(…)))`），不是随手选的：
它与“定向在表之前”差 11–12 LSB / 4.7–8.7% 像素（乘性量与表里的饱和缩放不交换），而
窗口放在表之前时，用户看到的皮肤有 0.11% 滑块管不到、另有 1.20% 被误管（m3e E 节）。
"所见即所调"要求窗口找的是屏幕上那份颜色。
"""
from __future__ import annotations

import math

import numpy as np

from ..optional_dependencies import optional_module

torch = optional_module("torch")


# ---- 窗口边界：真图分区域量出来的，不是猜的 ----
H_IN_LO, H_IN_HI = 0.025, 0.045         # 升入肤色（橙黄下沿）
H_OUT_LO, H_OUT_HI = 0.100, 0.125       # 退出肤色（往黄绿去）
S_LO, S_HI = 0.08, 0.16                 # 太淡的不算皮肤（白墙、过曝）
V_LO, V_HI = 0.10, 0.20                 # 太暗的不算皮肤（阴影里的黑衣服）
# 三个增量的硬边界：dh 是“色相移动占整圈的比例”，ds/dv 是相对乘性量。
# 边界取这么大不是"允许用户这么调"，而是超出这个量任何值都会把画面推到非自然色彩，
# 而产品口径是"影楼预设"，不是实验场。协议层另有更窄的滑块范围。
DH_LIMIT = 0.05
DS_LIMIT = 0.60
DV_LIMIT = 0.60


class GradeError(ValueError):
    """参数非法或产出非有限值。整条拒绝，不留半截状态。"""


def check_params(dh, ds, dv, *, amount: float = 1.0) -> tuple:
    """四个数的唯一校验口径（协议层与常驻层共用）。

    NaN 比大小恒为 False，不先拦就会被当成"合法"写进常驻层，然后每帧渲染才抛——
    现场与病因隔两个模块。这是 M1-3c/M2-a2/M3-a2 三次付过学费的同一条。
    """
    try:
        vals = (float(dh), float(ds), float(dv), float(amount))
    except (TypeError, ValueError):
        raise GradeError(f"肤色定向参数必须是有限数：dh={dh!r} ds={ds!r} dv={dv!r} "
                         f"amount={amount!r}") from None
    dh_, ds_, dv_, am_ = vals
    if not all(math.isfinite(v) for v in vals):
        raise GradeError(f"肤色定向参数含非有限值：{vals}")
    for name, v, lim in (("dh", dh_, DH_LIMIT), ("ds", ds_, DS_LIMIT), ("dv", dv_, DV_LIMIT)):
        if not -lim <= v <= lim:
            raise GradeError(f"{name}={v} 超出范围 [{-lim}, {lim}]")
    if not 0.0 <= am_ <= 1.0:
        raise GradeError(f"amount={am_} 超出范围 [0, 1]")
    return dh_, ds_, dv_, am_


def smoothstep(x, lo: float, hi: float):
    """C¹ 连续的窗口边：硬阈值会在窗口边界留下一条可见的接缝（"半张脸变色"）。"""
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------- numpy 参考臂
def rgb_to_hsv_np(x):
    """标准 HSV（与 matplotlib 同式）：h∈[0,1)，s,v∈[0,1]，最后一维是 RGB。"""
    x = np.asarray(x, dtype=np.float64)
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    maxc = x.max(-1)
    minc = x.min(-1)
    diff = maxc - minc
    safe = np.where(diff > 0, diff, 1.0)
    v = maxc
    s = np.where(maxc > 0, diff / np.where(maxc > 0, maxc, 1.0), 0.0)
    rc = (maxc - r) / safe
    gc = (maxc - g) / safe
    bc = (maxc - b) / safe
    h = np.where(diff <= 0, 0.0,
                 np.where(maxc == r, bc - gc,
                          np.where(maxc == g, 2.0 + rc - bc, 4.0 + gc - rc)))
    h = (h / 6.0) % 1.0
    return np.stack([h, s, v], axis=-1)


def hsv_to_rgb_np(hsv):
    """分段选择式反变换。它是产品内核 `hsv_to_rgb_t` 的对拍靶（两条独立写法）。"""
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = (i % 6).astype(np.int64)
    r = np.where(i == 0, v, np.where(i == 1, q, np.where(i == 2, p,
                 np.where(i == 3, p, np.where(i == 4, t, v)))))
    g = np.where(i == 0, t, np.where(i == 1, v, np.where(i == 2, v,
                 np.where(i == 3, q, np.where(i == 4, p, p)))))
    b = np.where(i == 0, p, np.where(i == 1, p, np.where(i == 2, t,
                 np.where(i == 3, v, np.where(i == 4, v, q)))))
    return np.stack([r, g, b], axis=-1)


def skin_weight_np(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    wh = smoothstep(h, H_IN_LO, H_IN_HI) * (1.0 - smoothstep(h, H_OUT_LO, H_OUT_HI))
    return wh * smoothstep(s, S_LO, S_HI) * smoothstep(v, V_LO, V_HI)


def feather_np(w):
    """对肤色权重做 3×3 二项式低通（可分离 [1,2,1]/4 横竖各一次）。

    为什么必须羽化：w 是**逐像素**按颜色窗口算出来的，色相一过界就整块翻转。真人像上
    实测（443×553，冷白预设）：w>0.5 的前景里 **17.9% 是边界像素**、相邻像素权重差的
    **p95=0.223、最大 1.000**、只有 7.2% 的像素能满额进窗——窗内窗外在图像上碎成一片
    一片，放大显示就是用户报的"人脸分层"。颜色空间里的 smoothstep 平滑救不了这个：
    它保证的是"同色同权重"，而图像上的斑块要的是"相邻像素权重别跳"。

    口径变化要写清楚：羽化前承诺"窗外逐字节不变"，羽化后只在**离肤色边界 2 px 以上**
    成立（3×3 核两次 = 支撑半径 2）。边界那一圈本来就该是过渡，不是台阶。

    边缘用 replicate（边缘复制）而不是补零：补零会在图像四边凭空压出一圈权重下降带。
    """
    return _binom1_np(_binom1_np(w, axis=-1), axis=-2)


def _binom1_np(a, axis):
    """沿一根轴做 [1,2,1]/4，边缘 replicate（np.take 夹索引，等价于边缘复制且不补零）。"""
    n = a.shape[axis]
    i = np.arange(n)
    lo = np.take(a, np.maximum(i - 1, 0), axis=axis)
    hi = np.take(a, np.minimum(i + 1, n - 1), axis=axis)
    return (lo + 2.0 * a + hi) / 4.0


def grade_np(x, dh: float, ds: float, dv: float, amount: float = 1.0, *, feather: bool = True):
    """解析真值臂：收 (…,3) 的 float64，返回同形状。"""
    dh, ds, dv, am = check_params(dh, ds, dv, amount=amount)
    x = np.asarray(x, dtype=np.float64)
    base = np.clip(x, 0.0, 1.0)
    hsv = rgb_to_hsv_np(base)
    wraw = skin_weight_np(hsv)
    if feather:
        wraw = feather_np(wraw)
    w = (wraw * am)[..., None]
    h2 = (hsv[..., 0:1] + dh * w) % 1.0
    s2 = np.clip(hsv[..., 1:2] * (1.0 + ds * w), 0.0, 1.0)
    v2 = np.clip(hsv[..., 2:3] * (1.0 + dv * w), 0.0, 1.0)
    out = hsv_to_rgb_np(np.concatenate([h2, s2, v2], axis=-1))
    # 定向 = 加权混合，不是"改完再说"：w=0 处这个式子在 IEEE 里精确等于原值
    return np.clip(base + (out - base) * w, 0.0, 1.0)


# ---------------------------------------------------------------- torch 生产臂
def rgb_to_hsv_t(t):
    """(N,3,H,W) → (h, s, v)，每个是 (N,H,W)。与 numpy 臂逐句同式。"""
    r, g, b = t[:, 0], t[:, 1], t[:, 2]
    maxc = t.amax(1)
    minc = t.amin(1)
    diff = maxc - minc
    safe = torch.where(diff > 0, diff, torch.ones_like(diff))
    v = maxc
    s = torch.where(maxc > 0, diff / torch.where(maxc > 0, maxc, torch.ones_like(maxc)),
                    torch.zeros_like(diff))
    rc = (maxc - r) / safe
    gc = (maxc - g) / safe
    bc = (maxc - b) / safe
    h = torch.where(diff <= 0, torch.zeros_like(diff),
                    torch.where(maxc == r, bc - gc,
                                torch.where(maxc == g, 2.0 + rc - bc, 4.0 + gc - rc)))
    return (h / 6.0) % 1.0, s, v


def hsv_to_rgb_t(h, s, v):
    """紧凑式反变换（mod/abs/clamp 三条），与 numpy 的分段选择式**是两种写法**。

    这不是为了好看：两条独立实现互相比，才是"公式接对了"的证据。只写一份的话，
    扇区偏移抄错一位（0/4/2 写成 0/2/4）在肤色这种窄色相区里几乎看不出来。
    """
    h6 = h * 6.0

    def chan(off):
        k = torch.abs((h6 + off) % 6.0 - 3.0) - 1.0
        return k.clamp(0.0, 1.0)

    rgb = torch.stack([chan(0.0), chan(4.0), chan(2.0)], dim=1)
    return v.unsqueeze(1) * (1.0 - s.unsqueeze(1) * (1.0 - rgb))


def smoothstep_t(x, lo: float, hi: float):
    tt = ((x - lo) / (hi - lo)).clamp(0.0, 1.0)
    return tt * tt * (3.0 - 2.0 * tt)


def skin_weight_t(h, s, v):
    wh = smoothstep_t(h, H_IN_LO, H_IN_HI) * (1.0 - smoothstep_t(h, H_OUT_LO, H_OUT_HI))
    return wh * smoothstep_t(s, S_LO, S_HI) * smoothstep_t(v, V_LO, V_HI)


def feather_t(w):
    """torch 臂的羽化：与 feather_np **同一条算式**（[1,2,1]/4 横竖各一次、边缘 replicate）。

    分两份实现只是因为索引 API 不同；两臂逐点一致由 test_grade 的对拍钉住。
    """
    n_h, n_w = w.shape[-2], w.shape[-1]
    iw = torch.arange(n_w, device=w.device)
    w = (torch.index_select(w, -1, (iw - 1).clamp(0, n_w - 1)) + 2.0 * w
         + torch.index_select(w, -1, (iw + 1).clamp(0, n_w - 1))) / 4.0
    ih = torch.arange(n_h, device=w.device)
    return (torch.index_select(w, -2, (ih - 1).clamp(0, n_h - 1)) + 2.0 * w
            + torch.index_select(w, -2, (ih + 1).clamp(0, n_h - 1))) / 4.0


def grade_t(t, dh: float, ds: float, dv: float, amount: float = 1.0, *, feather: bool = True):
    """生产内核：(N,3,H,W) float32 进、同形状出；离肤色边界 2 px 以上精确递回原值。"""
    if torch is None:
        raise RuntimeError("grade_t 需要 torch")
    if t.ndim != 4 or t.shape[1] != 3:
        raise GradeError(f"grade_t 需要 (N,3,H,W)，得到 {tuple(t.shape)}")
    dh, ds, dv, am = check_params(dh, ds, dv, amount=amount)
    if am == 0.0 or (dh == 0.0 and ds == 0.0 and dv == 0.0):
        return t                    # 结构短路：一个算子也不跑
    base = t.clamp(0.0, 1.0)
    h, s, v = rgb_to_hsv_t(base)
    wraw = skin_weight_t(h, s, v)
    if feather:
        wraw = feather_t(wraw)
    w = (wraw * am).unsqueeze(1)
    h2 = (h.unsqueeze(1) + dh * w) % 1.0
    s2 = (s.unsqueeze(1) * (1.0 + ds * w)).clamp(0.0, 1.0)
    v2 = (v.unsqueeze(1) * (1.0 + dv * w)).clamp(0.0, 1.0)
    out = hsv_to_rgb_t(h2[:, 0], s2[:, 0], v2[:, 0])
    # 与 numpy 臂同一条混合式：w=0 处 (t + (out − t)·0) 精确等于 t
    return (t + (out - t) * w).clamp(0.0, 1.0)


def is_identity(dh, ds, dv, amount: float = 1.0) -> bool:
    """这一层到底有没有活。校验过才算数：非法值不是"没活"，是"要拒"。"""
    dh, ds, dv, am = check_params(dh, ds, dv, amount=amount)
    return am == 0.0 or (dh == 0.0 and ds == 0.0 and dv == 0.0)
