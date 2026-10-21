"""全局曝光（EV）与白平衡（开尔文偏移 + 色调偏移）——P0 注册表的 lnx.exposure / lnx.white_balance。

两臂约定与 ops/grade.py 一致：`*_np` 是 CPU 真值臂、`*_t` 是 GPU 生产臂，两者算式完全
相同，测试对拍。这条不是形式主义：白平衡的增益表里有一次矩阵求逆与三次除法，任何一侧
"顺手优化一下"都会让预览与导出分家，而分家的表现是颜色差几个 LSB，肉眼看不出来。

中性必须逐字节恒等（frozen registry 的 quality_thresholds.identity 容差是 0）。
这条不靠"到了中性就短路返回原张量"糊出来：短路会让"非中性路径在中性处也应当恒等"
这件事永远测不到。ev=0 时 gain=2**0=1.0 是 IEEE 精确值；白平衡的增益在 shift=0 时是
"同一个 float 除以自己的商"，也是精确 1.0（见 wb_gains 为什么不用 M⁻¹·diag·M 形式）。
恒等由算式本身给出，再由测试逐通道 uint16 比对钉住。

开尔文用**偏移**而不是绝对值（ADR-0003）：绝对值需要一个 as-shot 基准，而合成图、
无 EXIF 的 DNG 根本没有。因此本层的参考点是 D65（6500 K），偏移量作用在
`T0 + shift → T0` 的自适应上，其中 T0 由调用方给出（有 as-shot 就用它，没有就 6500）。
这条要写清楚，否则"开尔文偏移"在没基准时听起来像绝对值，而它不是。
"""
from __future__ import annotations

import math

import numpy as np

from .tone import check_tone, is_identity as tone_identity, tone_np, tone_t

# torch 只在生产臂里需要。CPU 真值环境（CI 主门禁的 engine venv）里没装它，
# 硬 import 会让整个模块导入失败、把十几条纯 numpy 用例一起拖红。
# 拿 None 占位而不是 try/except 到子函数里：哪里真的用了它，报错就在哪里说清。
from ..optional_dependencies import optional_module

torch = optional_module("torch")

EV_LIMIT = 5.0             # 冻结量程 [-5, 5]（P0-EXPOSURE）
TEMP_LIMIT_K = 2000.0      # 冻结量程 ±2000 K
TINT_LIMIT = 1.0           # 冻结量程 [-1, 1]，归一
REFERENCE_K = 6500.0       # 没有 as-shot 时的参考白

__all__ = ["ev_gain", "wb_gains", "check_params",
           "exposure_np", "exposure_t", "apply_exposure_t"]


# ---------------------------------------------------------------- 校验
def check_params(ev: float = 0.0, temp_shift_k: float = 0.0, tint_shift: float = 0.0,
                 ref_k: float = REFERENCE_K) -> tuple[float, float, float, float]:
    """四个入参全部有限且在冻结量程内，否则整条拒绝。

    拒绝而不是夹取：P0-*-BOUNDARY 用例的 then 写着"非法输入拒绝；不静默改变数值"。
    夹取会把"用户（或坏配方）要了 12 EV"变成"给了他 5 EV"，画面看起来正常而配方是假的。
    """
    out = []
    for v, name, lim in ((ev, "exposure.ev", EV_LIMIT),
                         (temp_shift_k, "white_balance.temperature_shift", TEMP_LIMIT_K),
                         (tint_shift, "white_balance.tint_shift", TINT_LIMIT),
                         (ref_k, "white_balance.reference_k", None)):
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{name} 非法：{v!r}（要有限数）") from None
        if not math.isfinite(f):
            raise ValueError(f"{name} 非法：{v!r}（NaN/Inf 不接受）")
        if lim is not None and abs(f) > lim:
            raise ValueError(f"{name} 越界：{f!r}（冻结量程 |x| ≤ {lim}，不夹取）")
        out.append(f)
    if not (1000.0 <= out[3] <= 40000.0):
        raise ValueError(f"参考白非法：{out[3]!r} K（需在 1000–40000 K）")
    return out[0], out[1], out[2], out[3]


def cct_xy(k: float) -> tuple[float, float]:
    """CCT → CIE 1931 xy，**仅适用 CIE 日光轨迹（D 系列）的 4003–25000 K**。

    这一条的实现过程值得记：第一版这里凭记忆写了日光轨迹与黑体轨迹（Kim et al.）
    两段拼接，两处都抄错——7000 K 以上串到了黑体轨迹的 y 式，而 Planckian 支路里
    把 u=10⁶/T 写成了 k/1000，得到 6e12 量级的 x。白平衡增益解出负数 RGB 才发现。

    所以现在**只实现能就地验证的那一段**。D 系列系数与锚点对账见
    test_exposure.py：D50 (0.3457, 0.3585)、D65 (0.3127, 0.3290)、D75 (0.2990, 0.3149)。
    低于 4003 K 不走“另一个记不清的多项式”，而是**报错并说清缺什么**。
    默认参考 D65 ± 2000 K 落在 4500–8500 K，全在日光轨迹内；域外发生在调用方
    拿了低色温 as-shot 又拉满偏移时，那种时候宁可不给效果也不能给一个假物理量。
    """
    if not (4003.0 <= k <= 25000.0):
        raise ValueError(
            f"色温 {k!r} K 不在本层可算域内（CIE 日光轨迹 4003–25000 K）。"
            f"低于 4003 K 需要黑体轨迹实现，本层没带——凭记忆抄的多项式会在分段交界处"
            f"解出负数增益，拒绝比猜好。要么把参考白拉回日光段，要么先用 as-shot 之外的"
            f"白平衡手段。")
    t = 1e3 / k
    if k <= 7000.0:
        x = 0.244063 + 0.09911 * t + 2.9678 * t * t - 4.6048 * t * t * t
    else:
        x = 0.237040 + 0.24748 * t + 1.9018 * t * t - 3.1558 * t * t * t
    # y_D 是**整条日光轨迹唯一的一条二次式**，不随分段变。本仓库的第一版在这里
    # 编了一个“7000 K 以上专用的 -4.6070x²+4.5111x-0.4439”，在 7001 K 上得 y=0.498
    # （应约 0.317）——那个 4.6070 其实是 x 式里 10⁹/T³ 的系数，被搬错了位置。
    # 错因不是算错，是把“分段”当成了“每段都有自己的一条 y”。
    y = -3.000 * x * x + 2.870 * x - 0.275
    return float(x), float(y)


def _xy_to_xyz(x: float, y: float) -> np.ndarray:
    y = max(y, 1e-9)
    return np.array([x / y, 1.0, (1.0 - x - y) / y], dtype=np.float64)


# Bradford 色适应矩阵（ICC v4 规范值）。上一版是把两份不同的 Bradford 混着抄：
# row0 col2 是老 Bradford 的 0.7502 位置（应为 0.2664），又写成 0.0831；
# row1 col1 抄成 1.7141（应为 1.7135）；row2 col2 抄成 1.0245（应为 1.0296）。
# wb_gains 的方向符号（+temp 压 R 抬 B、+tint 抬 R/B 压 G）由算式本身保证，所以旧的方向
# 断言不会红；但具体增益数字会挪 1–3%，出片白平衡的准确度靠这个。
# 与 raw.py 里 BRADFORD 同一出处、同一份值，两处不同就是「两个模块对同一件事给两个答案」。
# 来源：colour-science v0.4.7 `CAT_BRADFORD`、ICC.42019 附表、Lindbloom 参考页。
_M_BRADFORD = np.array([
    [ 0.8951000,  0.2664000, -0.1614000],
    [-0.7502000,  1.7135000,  0.0367000],
    [ 0.0389000, -0.0685000,  1.0296000]], dtype=np.float64)


def wb_gains(temp_shift_k: float = 0.0, tint_shift: float = 0.0,
             ref_k: float = REFERENCE_K) -> np.ndarray:
    """返回作用在**线性 RGB** 上的 (3,) 增益。

    形式是「目标白与源白的归一化 RGB 之比」：

        gains = norm(M⁻¹·cone(target)) / norm(M⁻¹·cone(source))

    选这个形式而不是 CAT 的标准写法 `M⁻¹·diag(m)·M`，是因为后者在 shift=0 时
    **不等于单位**：Bradford 矩阵不正交，Mᵀ·I·M 仍带矩阵乘的红入。这个模块的硬要求是
    “中性逐字节恒等（容差 0）”，所以恒等必须由算式本身给出：shift=0 且 tint=0 时两个
    cone 向量完全相同，同一个 float 除以自己的结果是**精确的 1.0**，不靠短路、不靠
    “1e-16 误差量化后应该看不出来”。

    tint_shift 是色温之外的绿–洋红正交轴，没有物理单位（所以它用归一 [-1,1] 而不是
    假装有个"tint 单位"）：它缩放 cone-response 的 L/M 两通道，符号约定
    **正=洋红、负=绿**，与主流工具的滑杆方向一致，写死在这里以免反过来。
    """
    _, dk, tint, rk = check_params(0.0, temp_shift_k, tint_shift, ref_k)

    def rgb_white(k: float, tint_amt: float) -> np.ndarray:
        x, y = cct_xy(k)
        cone = _M_BRADFORD @ _xy_to_xyz(x, y)
        # 洋红方向 = 抬 L 压 M；绿方向反之。每单位 10% 是标定值，不是物理常数
        cone = cone * np.array([1.0 + 0.10 * tint_amt,
                                1.0 - 0.10 * tint_amt,
                                1.0], dtype=np.float64)
        rgb = np.linalg.solve(_M_BRADFORD, cone)
        if not (np.all(np.isfinite(rgb)) and np.all(rgb > 0.0)):
            raise ValueError(f"色温 {k!r} K 解出的白点 RGB 不可用：{rgb!r}")
        return rgb / rgb.sum()

    src = rgb_white(rk, 0.0)                 # 源白：相机认为它是白
    tgt = rgb_white(rk + dk, tint)     # 目标白：滑杆想要的白
    with np.errstate(divide="ignore", invalid="ignore"):
        g = tgt / src
    if not (np.all(np.isfinite(g)) and np.all(g > 0.0)):
        raise ValueError(f"白平衡增益不可用：src={src!r} tgt={tgt!r} gains={g!r}")
    return g


def ev_gain(ev: float) -> float:
    """EV → 线性乘性增益 2**EV。ev=0 得到 IEEE 精确 1.0。"""
    e, _, _, _ = check_params(ev, 0.0, 0.0, REFERENCE_K)
    return 2.0 ** e


# ---------------------------------------------------------------- 两臂实现
# sRGB ↔ 线性。为什么必须过这一道：EV 与 von Kries 白平衡按定义都作用在**场景线性光**上，
# 而渲染链里常驻的那份张量是 gamma 编码的（ops/light.py 里自带的 _lin/_slin 一对就是证据）。
# 在 gamma 域上乘 2**EV 数学上也能跑，但它是“抬亮显示值”而不是“加一档曝光”：
# 中间调会多升 0.45 次幂那么多，高光提前死。写这一层不是为了学术正确，是为了
# “拉 1 EV 得到的结果与在 RAW 解码端乘两倍的结枓一致”这条可对账的口径。
_SRGB_GAMMA = 2.4
_SRGB_BREAK = 0.04045


def _lin_np(a: np.ndarray) -> np.ndarray:
    """sRGB → 线性。用掩码赋值而不是 np.where(…, s[hi]…)：后者会把两个长度不同的
    数组放在一起广播（np.where 的两个分支都会被完整求值，布尔索引后的短数组不会自动归位）。"""
    s = np.clip(a, 0.0, 1.0)
    out = np.empty_like(s)
    lo = s <= _SRGB_BREAK
    out[lo] = s[lo] / 12.92
    hi = ~lo
    out[hi] = ((s[hi] + 0.055) / 1.055) ** _SRGB_GAMMA
    return out


def _slin_np(a: np.ndarray) -> np.ndarray:
    l = np.clip(a, 0.0, 1.0)
    lo, hi = l <= 0.0031308, l > 0.0031308
    out = np.empty_like(l)
    out[lo] = 12.92 * l[lo]
    if np.any(hi):
        out[hi] = 1.055 * l[hi] ** (1.0 / _SRGB_GAMMA) - 0.055
    return out


def _lin_t(x):
    if torch is None:                  # pragma: no cover
        raise RuntimeError("生产臂需要 torch（当前环境只装了 numpy 真值臂）")
    s = x.clamp(0.0, 1.0)
    lo = s <= _SRGB_BREAK
    return torch.where(lo, s / 12.92, ((s + 0.055) / 1.055) ** _SRGB_GAMMA)


def _slin_t(x):
    l = x.clamp(0.0, 1.0)
    lo = l <= 0.0031308
    return torch.where(lo, 12.92 * l, 1.055 * l ** (1.0 / _SRGB_GAMMA) - 0.055)


def _gains(ev: float, temp_shift_k: float, tint_shift: float, ref_k: float) -> np.ndarray:
    return ev_gain(ev) * wb_gains(temp_shift_k, tint_shift, ref_k)


def exposure_np(x: np.ndarray, ev: float = 0.0, temp_shift_k: float = 0.0,
               tint_shift: float = 0.0, ref_k: float = REFERENCE_K,
               contrast: float = 0.0, highlights: float = 0.0,
               shadows: float = 0.0, saturation: float = 0.0) -> np.ndarray:
    """CPU 真值臂。x 形状 (…,3) 或 (1,3,H,W)，float，**gamma 编码**值。

    中性恒等的口径在这里要说清：sRGB 传递函数的往返是解析式，float 上给的不是
    逐位相同的数（量化到 8/16-bit 后实测 ≤ 1 LSB）。真正的“逐字节恒等（容差 0）”
    由链上那一层保证：未点火时 apply_exposure 直接递回原张量，不进这里。
    把这两件事分开写，是为了以后有人改链时能看出“短路不是装饰”。
    """
    a = np.asarray(x, dtype=np.float64)
    g = _gains(ev, temp_shift_k, tint_shift, ref_k)
    lin = _lin_np(a)
    if a.ndim >= 1 and a.shape[-1] == 3:
        out = _slin_np(lin * g)
    elif a.ndim == 4:
        out = _slin_np(lin * g.reshape(1, 3, 1, 1))
    else:
        raise ValueError(f"exposure_np 不知道这个形状的通道轴：{a.shape}")
    out = np.clip(out, 0.0, 1.0)
    if not tone_identity(contrast, highlights, shadows, saturation):
        out = tone_np(out, contrast, highlights, shadows, saturation)
    return out


def exposure_t(x, ev: float = 0.0, temp_shift_k: float = 0.0,
               tint_shift: float = 0.0, ref_k: float = REFERENCE_K,
               contrast: float = 0.0, highlights: float = 0.0,
               shadows: float = 0.0, saturation: float = 0.0):
    """GPU 生产臂，与 np 臂同一条算式（同样先线性化、算完再编码回去）。"""
    if torch is None:                  # pragma: no cover
        raise RuntimeError("exposure_t 需要 torch；纯 numpy 环境请用 exposure_np")
    g = _gains(ev, temp_shift_k, tint_shift, ref_k)
    t = torch.as_tensor(g, dtype=torch.float64, device=x.device)
    lin = _lin_t(x.double())
    view = t.view(1, 3, 1, 1) if x.ndim == 4 else t
    out = _slin_t(lin * view).clamp_(0.0, 1.0).to(x.dtype)
    if not tone_identity(contrast, highlights, shadows, saturation):
        out = tone_t(out, contrast, highlights, shadows, saturation)
    return out


def apply_exposure_t(x, params: dict | None):
    """链上的便捷入口：params 为 None 或全中性时**返回原张量对象本身**。

    这里允许短路，且必须允许：vram 链每一帧都过这一层，中性时复制一份 (1,3,H,W) 的
    float 张量是实打实的显存与带宽。与上面注释的关系是——短路只省算力，不改变数值；
    「非中性路径在 shift=0 处也恒等」由 test_exposure.py 在**关掉短路**的情况下测。
    """
    if not params:
        return x
    ev = float(params.get("ev", 0.0))
    dk = float(params.get("temperature_shift", 0.0))
    tint = float(params.get("tint_shift", 0.0))
    c = float(params.get("contrast", 0.0))
    h = float(params.get("highlights", 0.0))
    s = float(params.get("shadows", 0.0))
    sa = float(params.get("saturation", 0.0))
    if ev == 0.0 and dk == 0.0 and tint == 0.0 and tone_identity(c, h, s, sa):
        return x
    return exposure_t(x, ev, dk, tint, contrast=c, highlights=h,
                      shadows=s, saturation=sa)
