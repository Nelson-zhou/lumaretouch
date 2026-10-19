"""M3-b 肤色定向：算子两臂互拍 + 常驻层契约。

判据口径来自 gpuspike/m3d.py（定架构）与 m3e.py（直接量本文件这两个臂），三条最要紧的：

· **窗外逐字节**不是“近似相等”：输出是 `x + (out − x)·w`，w=0 处这个式子在 IEEE 里
  精确等于 x。这一条由逐位比对（不是 LSB 比对）来钉。
· **窗内的方向与幅度必须与解析期望对上**，而且期望要**夹域**：亮到顶的像素 v·(1+dv)
  会被夹住，那里位移本来就比线性期望小。拿未夹域的线性式当期望会量出 0.044 的假残差
  （m3e 第一轮就这么错过一次），夹域后 w=1 的像素残差是 4.1e-06——float32 精度。
· 两臂是**两种独立写法**（numpy 分段选择式 vs torch 的 mod/abs/clamp 紧凑式）。
  抄一遍式子互相比等于没比：扇区偏移错一位（0/4/2 写成 0/2/4）在肤色这种窄色相区里
  几乎看不出来。

层的部分（后半节）照 test_lut.py 的形状写：常驻层要管的是算子管不到的四件事——
缓存失效边界、提交点原子性、链上位置、事件形状。那四处 M1-3c / M2-a2 / M2-b / M3-a2
各栽过一次。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops.grade import (DH_LIMIT, DS_LIMIT, DV_LIMIT, GradeError, feather_np,
                                         H_IN_HI, H_IN_LO, H_OUT_HI, H_OUT_LO, S_HI, S_LO,
                                         V_HI, V_LO, check_params, grade_np, grade_t,
                                         hsv_to_rgb_np, is_identity, rgb_to_hsv_np,
                                         skin_weight_np)
from lumaretouch_engine.ops.lut import QUALITY_SIZE_3D, bake

H, W = 41, 57


def to_u8(a):
    """LSB 差必须先升 int16：uint8 相减是模 256 回绕的（183−184=255）。"""
    return np.rint(np.clip(a, 0.0, 1.0) * 255.0).astype(np.int16)


def sample_hw3() -> np.ndarray:
    """一张**按窗口构造**的 (H,W,3) float64：窗内、扫边界、窗外、暗部各占一条。

    不能只拿均匀噪声当靶：窗口是色相/饱和/明度的三段门限，随机噪声落在窗外的概率
    极高，"窗外逐字节"那条就会因为"全图都在窗外"而恒真。这里每个区域为什么在这
    是写在构造里的。
    """
    def row(h, s, v):
        hsv = np.stack([np.full((1, W), h), np.full((1, W), s), np.full((1, W), v)], axis=-1)
        return hsv_to_rgb_np(np.broadcast_to(hsv, (1, W, 3)))

    r_full = row(0.055, 0.35, 0.72)                        # w=1：色相在带内、s/v 过阈
    r_sweep = hsv_to_rgb_np(np.stack([
        np.linspace(0.020, 0.130, W)[None, :],             # 穿过升入带与退出带两条边界
        np.full((1, W), 0.35), np.full((1, W), 0.72)], axis=-1))
    r_green = row(0.300, 0.50, 0.60)                       # 色相在窗口之外（绿）
    r_gray = row(0.055, 0.02, 0.70)                        # 饱和不过阈（白墙/过曝）
    r_dark = row(0.055, 0.35, 0.03)                        # 明度不过阈（阴影里的黑衣）
    rng = np.random.default_rng(5)
    r_noisy = np.clip(r_full[0] + rng.random((1, W, 3)) * 0.02, 0.0, 1.0)
    a = np.concatenate([r_full, r_sweep, r_green, r_gray, r_dark, r_noisy], axis=0)
    # 上面拼出来 6 行，剩下的高度用不同权重的肤色铺满（保证 w 是连续的，不是只有 0/1）
    extra = hsv_to_rgb_np(np.stack([
        np.linspace(0.030, 0.095, (H - 6) * W)[None, :].reshape(H - 6, W),
        np.linspace(0.10, 0.60, (H - 6) * W)[None, :].reshape(H - 6, W),
        np.linspace(0.25, 0.85, (H - 6) * W)[None, :].reshape(H - 6, W)], axis=-1))
    return np.concatenate([a, extra], axis=0).astype(np.float64)


def to_nchw(a):
    """(H,W,3) float64 → (1,3,H,W) float32（生产张量的形状与位宽）。"""
    return np.ascontiguousarray(a.astype(np.float32).transpose(2, 0, 1)[None])


def weight_of(a):
    return skin_weight_np(rgb_to_hsv_np(np.clip(np.asarray(a, dtype=np.float64), 0.0, 1.0)))


@pytest.fixture()
def layer():
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline

    rng = np.random.default_rng(7)
    base = (0.30 + 0.45 * (np.arange(W, dtype=np.float64) / (W - 1))[None, :]
            + 0.12 * np.sin(np.arange(H, dtype=np.float64) / 3.0)[:, None])
    skin = np.clip(np.stack([base, base * 0.92, base * 0.80], axis=-1), 0.0, 1.0)
    rgb = np.rint(np.clip(skin + rng.random((H, W, 3)) * 0.06, 0.0, 1.0) * 255.0).astype(np.uint8)
    return make_pipeline("cpu", W, H, rgb), rgb


# ==================================================== 算子层：窗口与两臂
def test_window_bounds_are_the_measured_ones():
    """窗口边界是总工那张真图分区域量出来的，改一个数就得同步改跑靶判据。

    脸心 95.2% 命中、红发 14.6%、绿贝雷 10.5%、背景树叶 11.8%（m3d/m3e B 节）：
    "只框住皮肤"这句话的证据是这份分区命中率，不是全图覆盖率 30%。
    """
    assert (H_IN_LO, H_IN_HI) == (0.025, 0.045)
    assert (H_OUT_LO, H_OUT_HI) == (0.100, 0.125)
    assert (S_LO, S_HI) == (0.08, 0.16)
    assert (V_LO, V_HI) == (0.10, 0.20)


def test_hsv_roundtrip_is_exact_enough_for_a_reference_arm():
    """Δ=0 时 HSV 往返的残差必须在 float64 精度内，否则"参考臂"本身不可用。"""
    x = sample_hw3()
    back = hsv_to_rgb_np(rgb_to_hsv_np(x))
    assert float(np.abs(back - x).max()) < 1e-12


def test_skin_weight_is_one_inside_and_zero_outside(sample_hw3_data):
    """构造出来的四个区域必须各自落在预期的权重档上。

    这条是后面所有"窗外逐字节"判据的前提：如果随机噪声抽不到窗外像素，那条判据
    就只是"全图都在窗外"的同义反复。
    """
    w = weight_of(sample_hw3_data)
    assert w[:1].mean() > 0.99, "构造的满权重肤色区没落进窗口"
    assert w[2:3].mean() < 1e-6, "绿区应当整条在窗外"
    assert w[3:4].mean() < 1e-6, "灰区（饱和不过阈）应当整条在窗外"
    assert w[4:5].mean() < 1e-6, "暗区（明度不过阈）应当整条在窗外"
    # 扫边界那一行必须同时给出 0、1 与中间值：C¹ 过渡带不是硬阈值
    mid = w[1:2]
    assert (mid > 0.05).any() and (mid < 0.05).any() and ((mid > 0.02) & (mid < 0.98)).any()


@pytest.fixture()
def sample_hw3_data():
    return sample_hw3()


def test_numpy_arm_matches_clamped_analytic_expectation(sample_hw3_data):
    """w=1 的像素上，实测位移必须等于**夹域后的**解析期望。

    期望式与实现同式没意义（那是自证）；这里对的是"移动量等于多少"这个独立写出来的
    闭合式：Δs = clip(s(1+ds·w)) − s，Δv 同理，Δh = dh·w（取最近回绕）。只看 w 恰好
    等于 1 的像素：混了 (1−w) 份原值就会少 (1−w) 份位移，那部分残差是定义造成的不是
    错（m3e 在 f32 上取 w≥0.9999 量到 4.1e-06，止于此）。在 float64 参考臂上，w=1 那堆
    应当残差 1e-12。
    """
    x = sample_hw3_data
    dh, ds, dv = 0.012, -0.35, 0.28
    # feather=False：这条测的是"混色式 + HSV 正逆变换"这个解析闭包，权重必须是逐点那份；
    # 羽化是空间低通，掺进来只会让这条判据变成"测我自己写的卷积"。羽化单独有判据。
    got = grade_np(x, dh, ds, dv, feather=False)
    hsv = rgb_to_hsv_np(np.clip(x, 0.0, 1.0))
    w = weight_of(x)
    full = w == 1.0
    assert full.sum() > 0, "样本里没有满权重像素，这条判据会恒真"
    exp_h = (hsv[..., 0] + dh * w) % 1.0
    exp_s = np.clip(hsv[..., 1] * (1.0 + ds * w), 0.0, 1.0)
    exp_v = np.clip(hsv[..., 2] * (1.0 + dv * w), 0.0, 1.0)
    out_hsv = rgb_to_hsv_np(np.clip(got, 0.0, 1.0))
    res_h = float(np.abs(((out_hsv[..., 0] - exp_h + 0.5) % 1.0) - 0.5)[full].max())
    res_s = float(np.abs(out_hsv[..., 1] - exp_s)[full].max())
    res_v = float(np.abs(out_hsv[..., 2] - exp_v)[full].max())
    assert max(res_h, res_s, res_v) < 1e-12, (res_h, res_s, res_v)


def _dilate(mask, r: int):
    """把布尔掩码沿横竖各扩 r 像素（补 False，不环绕）。独立于被测实现写。"""
    p = np.pad(mask, r, constant_values=False)
    h, w = mask.shape
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= p[r + dy:r + dy + h, r + dx:r + dx + w]
    return out


def test_pixels_outside_the_window_are_byte_identical(sample_hw3_data):
    """窗外逐字节不动——**关掉羽化时是任何 w=0 像素**，默认羽化时是"离边界 2 px 以上"。

    `0·有限 = 0`、`x + 0 = x`：这是结构性保证，不是调出来的容差。混色式一旦写成
    "先算完再按 mask 挑"，这条立刻碎，而 LSB 判据可能还看不出来。

    口径为什么收窄：权重是逐像素按颜色窗口算的，不羽化就在图像上硬跳，真人像上
    脸会一块一块分层（用户报"冷白人都分层了"，实测满权重前景里 17.9% 是边界像素、
    相邻像素权重差最大 1.000）。羽化核 [1,2,1]/4 横竖各一次的支撑半径是 2，所以
    逐位不变的承诺只能覆盖到离窗口 2 px 以外——边界那一圈本来就该是过渡而不是台阶。
    """
    x = sample_hw3_data
    w = weight_of(x)
    zero = np.isclose(w, 0.0)
    assert zero.sum() > 0
    strict = grade_np(x, 0.012, -0.35, 0.28, feather=False)
    assert np.array_equal(strict[zero], x[zero]), "窗外像素被改动了（混色式写错了）"


def test_pixels_far_from_the_window_boundary_survive_feathering():
    """羽化后仍然逐位不变的范围：离肤色窗口 2 px 以外。样本自己造，要有一大片远窗外。

    这份判据不能拿 sample_hw3_data 当输入：那份样本的窗外像素**全部**挤在窗口 2 px 以内，
    `far` 会空集，断言就退化成恒真——所以这里造一张左肤右绿、右侧留足宽度的图。
    """
    x = np.zeros((60, 120, 3), np.float64)
    x[:, :40] = (0.85, 0.62, 0.50)        # 肤色窗内
    x[:, 60:] = (0.42, 0.72, 0.30)        # 黄绿，窗外，且离边界 20 px 以上
    x[:, 40:60] = np.linspace(0.85, 0.42, 20)[None, :, None] * np.array([1.0, 0.9, 0.85])
    zero = np.isclose(weight_of(x), 0.0)
    far = zero & ~_dilate(~zero, 2)
    assert far.sum() > 500, f"样本里「远窗外」只有 {far.sum()} 个像素，判据会退化"
    assert np.array_equal(grade_np(x, 0.012, -0.35, 0.28)[far], x[far]), \
        "离肤色边界 2 px 以外的像素被改动了"


def test_feather_spreads_the_weight_step_over_pixels_instead_of_flipping():
    """羽化的正判据：色相硬跨窗口边界时，权重必须摊开，不能一像素翻完。

    反向门在前半段：不羽化时这道缝就是 1 px 内从满权重跳到 0——那正是"分层"的形状。
    """
    x = np.zeros((40, 60, 3), np.float64)
    x[:, :30] = (0.85, 0.62, 0.50)        # 色相落在肤色窗内
    x[:, 30:] = (0.42, 0.72, 0.30)        # 偏黄绿，窗外
    raw = weight_of(x)
    assert raw.max() > 0.9 and raw.min() < 0.1, "样本没造出窗内/窗外两侧"
    step = float(np.abs(np.diff(raw, axis=1)).max())
    assert step > 0.9, f"这条判据依赖样本里有硬跳，实际只有 {step:.3f}"
    sm = float(np.abs(np.diff(feather_np(raw), axis=1)).max())
    # [1,2,1]/4 跨 0→1 阶跃的最坏跳变正好是 0.5（0.25 → 0.75），所以判据是"不超过一半"，
    # 写成严格小于会在自己的算式上翻车——第一次就是这么红的。
    assert sm <= step / 2.0 + 1e-12, f"羽化没把最大逐像素跳变压下去：{step:.3f} → {sm:.3f}"
    # 过渡要真的摊开：缝上一列里既非满值也非零值的像素至少 3 个
    seam = feather_np(raw)[:, 26:36]
    mid = ((seam > 0.02) & (seam < 0.98)).sum()
    assert mid >= 3, f"过渡只摊在 {mid} 个像素上，仍然是台阶"


def test_torch_arm_returns_the_same_object_for_identity(sample_hw3_data):
    """全零参数与 amount=0 走结构短路：一个算子都不跑，返回的就是入参那个对象。

    "算出来恰好一样"与"没算"在字节上无法区分，但在成本上差一整帧：拖别的滑块时
    这层必须是零成本，那只能由短路保证。
    """
    torch = pytest.importorskip("torch")
    t = torch.from_numpy(to_nchw(sample_hw3_data))
    assert grade_t(t, 0.0, 0.0, 0.0) is t
    assert grade_t(t, 0.012, -0.35, 0.28, amount=0.0) is t
    assert is_identity(0.0, 0.0, 0.0) is True
    assert is_identity(0.012, 0.0, 0.0) is False
    assert is_identity(0.0, 0.0, 0.0, amount=0.0) is True, "强度 0 也是“没活”"


def test_two_arms_agree_continuously_and_flip_only_on_quantization_edges(sample_hw3_data):
    """两臂必须先在**连续域**上对得上，量化差才能归给“边界翻牌”。

    只报“最大 1 LSB”会把两份真正不同的算法当成对得上（差 0.4 LSB 也始终是 1 LSB）：
    所以先卡连续差 <1e-3 LSB（float32 取样的精度量级），再卡“所有翻牌都发生在离
    .5 边界 1e-3 LSB 以内的像素上”。m3e 在真图上量的 1.7e-06 翻牌占比就是这条的副产物；
    本用例的样本里有整行完全相同的颜色，抽中格点比真图多得多，所以不能直接卡占比。
    """
    torch = pytest.importorskip("torch")
    x = sample_hw3_data
    ref = grade_np(x, 0.012, -0.35, 0.28)
    got = grade_t(torch.from_numpy(to_nchw(x)), 0.012, -0.35, 0.28)[0].permute(1, 2, 0)
    got = got.numpy().astype(np.float64)
    cont = float(np.abs(got - ref).max() * 255.0)
    assert cont < 1e-3, f"两臂在连续域差了 {cont:.2e} LSB：这不是精度，是算法差"
    d = np.abs(to_u8(got) - to_u8(ref))
    assert int(d.max()) <= 1, f"两臂差了 {int(d.max())} LSB：不是精度问题"
    tb = np.clip(ref, 0.0, 1.0) * 255.0
    edge = np.abs(tb - np.floor(tb) - 0.5) < 1e-3
    stray = int((np.abs(d) > 0)[~edge].sum())
    assert stray == 0, f"{stray} 个像素不在量化边界上却翻了牌：两臂真的不一样"
    # “权重为 0 的像元一动不动”这条结构性保证在两臂上都得成立，但判据要按**算子里
    # 真正用的那份权重**来取，两个细节都会把断言指错地方（运行时 venv 里这条红就是
    # 同时踩了这两个：dev venv 没 torch，importorskip 让它从来没跑过）：
    #   ① grade_np/grade_t 都过 feather_np（[1,2,1]/4），羽化后 w=0 的像元才真是
    #      “不动”，只看羽化前的 weight_of 会把紧贴肤色的窗外像元也算成“该不动”；
    #   ② 算子先 clip 到 [0,1] 再算，窗外像元的“原值”是 clip 后的那份，不是 x 本身。
    # torch 收到的是 f32，所以跟 f32 那份比。
    w = feather_np(weight_of(x))
    zero = np.isclose(w, 0.0)
    assert zero.sum() > 0, "样本里没有 w=0 的像元：这条断言变成了空转"
    assert np.array_equal(got[zero], np.clip(np.asarray(x, dtype=np.float32), 0.0, 1.0)[zero])


def test_amount_scales_the_move_monotonically(sample_hw3_data):
    """混入比例单调：0 逐字节、1 全量，中间档的位移量必须一档比一档大。

    方向也要卡：如果 amount 只缩了位移的大小却没保持符号，"强度"就退化成了噪声。
    """
    x = sample_hw3_data
    dh, ds, dv = 0.012, -0.35, 0.28
    inside = weight_of(x) > 0.5
    full = grade_np(x, dh, ds, dv)
    moves = []
    for a in (0.0, 0.25, 0.5, 0.75, 1.0):
        out = grade_np(x, dh, ds, dv, amount=a)
        if a == 0.0:
            assert np.array_equal(out, np.clip(x, 0.0, 1.0)), "amount=0 却没还原"
        moves.append(float(np.abs(out - np.clip(x, 0.0, 1.0))[inside].mean()))
    assert all(b > a for a, b in zip(moves, moves[1:])), moves
    assert moves[-1] > 0.0


@pytest.mark.parametrize("bad", [
    (-0.06, 0.0, 0.0), (0.0, -0.61, 0.0), (0.0, 0.0, 0.61), (0.0, 0.0, float("nan")),
    (0.0, 0.0, float("inf")), ("abc", 0.0, 0.0), (None, 0.0, 0.0), (0.0, {}, 0.0),
])
def test_bad_params_are_rejected(bad):
    """非有限/越界/非数一律 GradeError：NaN 比大小恒 False，不拦就会被当"合法"提交。"""
    with pytest.raises(GradeError):
        check_params(*bad)


@pytest.mark.parametrize("amount", [-0.01, 1.01, float("nan"), float("inf"), "x"])
def test_bad_amount_is_rejected(amount):
    with pytest.raises(GradeError):
        check_params(0.0, 0.0, 0.0, amount=amount)


def test_check_params_coerces_and_returns_the_canonical_tuple():
    """整数进、浮点出，四个数一个 tuple 返回：协议层与常驻层共用同一个口径。"""
    got = check_params(0, -0.5, 0.5, amount=1)
    assert got == (0.0, -0.5, 0.5, 1.0)
    assert all(isinstance(v, float) for v in got)


def test_limits_are_the_documented_ones():
    """硬边界写进常量、也写进上报（UI 滑块的夹取范围由引擎说，不由前端抄）。"""
    assert (DH_LIMIT, DS_LIMIT, DV_LIMIT) == (0.05, 0.60, 0.60)
    check_params(-DH_LIMIT, -DS_LIMIT, -DV_LIMIT)      # 边界本身是合法的
    with pytest.raises(GradeError):
        check_params(DH_LIMIT + 1e-9, 0.0, 0.0)


def test_grade_t_rejects_a_wrong_shaped_tensor():
    torch = pytest.importorskip("torch")
    with pytest.raises(GradeError):
        grade_t(torch.zeros((1, 4, 5, 5)), 0.01, 0.0, 0.0)
    with pytest.raises(GradeError):
        grade_t(torch.zeros((5, 5, 3)), 0.01, 0.0, 0.0)


def test_batch_of_two_matches_two_single_calls(sample_hw3_data):
    """batch>1 现在是支持的，而且逐图各算自己的窗口——把它钉成判据。

    为的是 M4 的分块导出：分块一旦走 batch，必须保证第二块不会用第一块的肤色判定。
    这里量的就是“batch=2 与两次 batch=1 逐字节相同”；哪天改成广播实现，这条会碎。
    """
    torch = pytest.importorskip("torch")
    t = torch.from_numpy(to_nchw(sample_hw3_data))
    both = grade_t(torch.cat([t, t.flip(3)], dim=0), 0.012, -0.35, 0.28)
    one = grade_t(t, 0.012, -0.35, 0.28)
    other = grade_t(torch.flip(t, dims=[3]), 0.012, -0.35, 0.28)
    assert torch.equal(both[0:1], one) and torch.equal(both[1:2], other), \
        "batch 里两张图互相串了肤色判定"


# ==================================================== 常驻层：契约与链位
def test_no_grade_is_byte_identical_to_plain_chain(layer):
    """没设参数时，接了层的通路必须与"只有磨皮"逐字节相同，而且 grade_ms 为 0。"""
    pipe, _rgb = layer
    pipe.render(0.55)
    with_layer = pipe.read_back()[..., :3].copy()
    plain = (1.0 - 0.55) * pipe.base() + 0.55 * pipe.retouched
    pipe.pack(plain)
    assert np.array_equal(with_layer, pipe.read_back()[..., :3])
    assert pipe.last_grade_ms == 0.0
    assert pipe.has_grade() is False


def test_setting_grade_lights_the_layer_and_every_frame_runs_it(layer):
    torch = pytest.importorskip("torch")
    pipe, _rgb = layer
    info = pipe.set_grade(0.006, -0.14, 0.05)
    assert info["grade_lit"] is True and info["grade_set"] is True
    pipe.render(0.5)
    first = pipe.read_back()[..., :3].copy()
    assert pipe.last_grade_ms > 0.0, "点火了却没跑：那一层只存在于上报里"
    # 与直接调算子逐字节对齐：层没有多干一份活，也没有少干
    mixed = (1.0 - 0.5) * pipe.base() + 0.5 * pipe.retouched
    direct = grade_t(mixed, 0.006, -0.14, 0.05)
    assert torch.equal(pipe.retouch(0.5), direct)
    pipe.pack(direct)
    assert np.array_equal(pipe.read_back()[..., :3], first)


def test_grade_amount_zero_is_byte_identical_and_skips_the_kernel(layer):
    """强度 0 逐字节回原图、而且 0 ms：它走的是短路，不是“算出来恰好一样”。"""
    pipe, _rgb = layer
    pipe.render(0.5)                        # 定向还没点火：这一帧就是“只有磨皮”
    expect = pipe.read_back()[..., :3].copy()
    pipe.set_grade(0.006, -0.14, 0.05)
    pipe.render(0.5)
    assert pipe.last_grade_ms > 0.0
    assert not np.array_equal(pipe.read_back()[..., :3], expect), "点火了却没动画面"
    pipe.set_grade_amount(0.0)
    assert pipe.has_grade() is False
    pipe.render(0.5)
    assert pipe.last_grade_ms == 0.0
    assert np.array_equal(pipe.read_back()[..., :3], expect), "强度 0 却没逐字节还原"
    pipe.set_grade_amount(1.0)
    pipe.render(0.5)
    assert not np.array_equal(pipe.read_back()[..., :3], expect), "重新开火却没动画面"


def test_setting_grade_invalidates_no_filter_cache(layer):
    # 验收用例引用：RENDER-007（链尾层不该作废上游缓存（带反向对照））
    """定向与调色同构：在链尾，所以它不该作废任何上游缓存——带反向对照。"""
    from lumaretouch_engine.vram import DEFAULT_RADIUS

    pipe, _rgb = layer
    pipe.prepare()
    assert pipe.last_filter_ms > 0.0, "首次没真算，后面的“不重算”就没有对照"
    pipe.retouch(0.5)
    assert pipe.last_filter_ms == 0.0 and pipe.last_bands_ms == 0.0
    pipe.set_grade(0.012, -0.35, 0.28)
    pipe.retouch(0.6)
    assert pipe.last_filter_ms == 0.0 and pipe.last_bands_ms == 0.0, \
        "设了肤色参数却重跑了滤波：它被写进了缓存键"
    pipe.retouch(0.6, radius=DEFAULT_RADIUS + 3)
    assert pipe.last_filter_ms > 0.0, "改了半径也不重算：这个计数器是死的"


def test_grade_sits_after_the_lut_layer(layer):
    """链尾顺序写成可观测判据：定向在表之后，而且反过来必须看得出差别。

    拿一张"几乎不动"的表去比顺序，两臂逐字节相同，那句"我们在链尾"就什么也没证明。
    这里用 ×0.75 的压暗表 + ds/dv 大动作量：m3e E 节在真图上量到两阶差 11–12 LSB。
    """
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops.lut import apply_lut_t

    pipe, _rgb = layer
    cube = bake(lambda x: np.clip(x * 0.75, 0.0, 1.0), QUALITY_SIZE_3D,
                title="dim", source="test:dim")
    pipe.clear_lut()
    pipe.clear_grade()
    pre = pipe.retouch(0.5)                          # 只有形变在链尾
    pipe.set_lut(cube, 1.0)
    after_lut = pipe.retouch(0.5)                    # lut(deform(…))
    pipe.set_grade(0.0, -0.5, 0.5)
    got = pipe.retouch(0.5)                          # grade(lut(deform(…)))
    assert torch.equal(got, grade_t(after_lut, 0.0, -0.5, 0.5)), \
        "got 不是 grade(lut(…))：链尾顺序与声明不一致"
    wrong = apply_lut_t(grade_t(pre, 0.0, -0.5, 0.5), cube)     # 定向 → 表
    assert not torch.equal(got, wrong), \
        "换顺序也看不出差别：这条顺序判据是空的（表太软或定向没生效）"


@pytest.mark.parametrize("bad", [(0.0, 0.0, 0.7, None), (0.9, 0.0, 0.0, None),
                                 (0.0, 0.0, float("nan"), None), (0.0, 0.0, 0.0, 1.5),
                                 ("x", 0.0, 0.0, None)])
def test_illegal_grade_is_rejected_before_any_state_write(layer, bad):
    """非法参数整条拒，四个字段一个也不动（与 set_lut / set_strength 同一条铁律）。"""
    pipe, _rgb = layer
    pipe.set_grade(0.006, -0.14, 0.05)
    snap = (pipe.grade_params, pipe.grade_amount, pipe.last_grade_ms)
    with pytest.raises(GradeError):
        pipe.set_grade(*bad[:3], amount=1.0 if bad[3] is None else bad[3])
    assert (pipe.grade_params, pipe.grade_amount, pipe.last_grade_ms) == snap


def test_the_three_grade_arms_return_the_same_key_set(layer):
    pipe, _rgb = layer
    a = pipe.set_grade(0.006, -0.14, 0.05)
    b = pipe.set_grade_amount(0.5)
    c = pipe.clear_grade()
    assert set(a) == set(b) == set(c), f"事件形状漂了：{(set(a) ^ set(b)) | (set(a) ^ set(c))}"
    for k in ("grade_dh", "grade_ds", "grade_dv", "grade_amount", "grade_set", "grade_lit",
              "grade_limits", "bytes_grade", "device", "layer_recomputed"):
        assert k in a, k
    assert a["layer_recomputed"] is True and b["layer_recomputed"] is False
    assert a["grade_limits"] == [DH_LIMIT, DS_LIMIT, DV_LIMIT]
    assert c["grade_dh"] == 0.0 and c["grade_lit"] is False


def test_grade_holds_no_vram_but_still_reports_the_bill(layer):
    """全图作用域下这一层不持有张量，账单恒为 0：报 0 而不是不报，"查过"才是这句话的内容。

    COLOR-004 起 brush 作用域会常驻一份 (1,1,H,W) 掩膜权重，那一笔由下面那两条钉：
    拿 0 当"报而不藏"的例子仍然成立，但它不再是这句话的全部。
    """
    pipe, _rgb = layer
    assert pipe.grade_resident_bytes() == 0
    info = pipe.set_grade(0.006, -0.14, 0.05)
    assert info["bytes_grade"] == 0
    pipe.render(0.5)
    assert pipe.grade_resident_bytes() == 0


def test_non_finite_output_is_refused_and_the_frame_keeps_the_old_bytes(layer, monkeypatch):
    """产出非有限值时报错，而且不能把 NaN 包进常驻帧（uint8 化会把 NaN 洗成"正常数"）。"""
    torch = pytest.importorskip("torch")
    from lumaretouch_engine import vram

    pipe, _rgb = layer
    pipe.set_grade(0.006, -0.14, 0.05)
    pipe.render(0.5)
    good = pipe.read_back()[..., :3].copy()

    def boom(t, dh, ds, dv, amount=1.0):
        return torch.full_like(t, float("nan"))

    monkeypatch.setattr(vram, "grade_t", boom)
    with pytest.raises(ValueError):
        pipe.render(0.5)
    assert np.array_equal(pipe.read_back()[..., :3], good)


def test_replay_commits_the_same_params_on_a_new_session(layer):
    """换设备重建会话时，定向层重放的就是那四个数（它不认任何缓存结果）。"""
    from lumaretouch_engine.vram import make_pipeline

    pipe, rgb = layer
    pipe.set_grade(0.006, -0.14, 0.05, amount=0.7)
    pipe.render(0.45)
    graded = pipe.read_back()[..., :3].copy()
    p2 = make_pipeline("cpu", W, H, rgb)
    info = p2.set_grade(0.006, -0.14, 0.05, amount=0.7)
    p2.render(0.45)
    assert np.array_equal(p2.read_back()[..., :3], graded)
    assert info["grade_amount"] == 0.7 and info["grade_lit"] is True


def test_warm_device_actually_runs_the_grade_kernel(monkeypatch):
    """预热必须真跑过定向内核：调色那次预热只证了 grid_sample(3d)，盖不到这组 elementwise。

    拿计数器包住 grade_t，而不是拿"预热返了个正数"当证据：后者对任何空实现都成立。
    """
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("没 GPU：预热路径本身就不该跑，测它没意义")
    from lumaretouch_engine import vram

    calls = []
    real = vram.grade_t

    def spy(t, dh, ds, dv, amount=1.0):
        calls.append((float(dh), float(ds), float(dv), float(amount), str(t.device)))
        return real(t, dh, ds, dv, amount=amount)

    monkeypatch.setattr(vram, "grade_t", spy)
    ms = vram.warm_device("cuda")
    assert ms > 0.0, f"预热返 0 就等于没预热，但事件会报 engine_warm：{ms}"
    assert calls, "预热一句也没跑肤色定向：那句“已预热”是假的"
    assert any(abs(dh) > 0 or abs(ds) > 0 or abs(dv) > 0 for dh, ds, dv, _a, _d in calls), \
        f"预热用的是全零参数，结构短路让它恒真：{calls}"
    assert all(dev.startswith("cuda") for _dh, _ds, _dv, _a, dev in calls), calls


# ==================================================== COLOR-004：局部调色（作用域/区域）
# 冻结件那三条 then：「蒙版外变化在定义边缘范围内；撤销恢复；无明显色边」。这里只管
# 库层能自证的那两条（蒙版外逐字节恒等、边界邻域跳变有界），“撤销恢复”是命令层语义，
# 端到端那一臂在 test_acceptance_p1.py。
def _half_mask(left: bool = True) -> np.ndarray:
    """代理帧坐标的阶跃区域：左（或右）一半盖住，其余不盖。"""
    m = np.zeros((H, W), dtype=np.uint8)
    half = W // 2
    if left:
        m[:, :half] = 255
    else:
        m[:, half:] = 255
    return m


def test_scope_all_is_byte_identical_to_the_pre_color_004_behaviour(layer):
    """scope=all 必须是旧行为本身，逐字节而不是“差不多”。

    这一条是整个改动的地基：作用域是新加的旋钮，它不能改动已经签过收的
    全图定向（那四个数的语义、内核、链上位置）。拿 `is not None` 当短路条件不算证据，
    因为混式在 w=1 也能回到 graded —— 那是浮点巧合而不是承诺。
    """
    pipe, _rgb = layer
    pipe.set_grade(0.006, -0.14, 0.05, amount=0.8)
    pipe.render(0.0)
    full = pipe.read_back()[..., :3].copy()
    # 挂一份“只盖左半”的区域但把作用域留在 all：它不该参与任何一像素
    pipe.set_grade_mask(_half_mask(), mode="replace")
    assert pipe.grade_scope == "all"
    pipe.render(0.0)
    assert np.array_equal(pipe.read_back()[..., :3], full), \
        "区域挂了而作用域还是 all，画面就动了——“没生效”与“生效了”必须与 scope 一致"
    info = pipe.set_grade_scope("all")
    assert info["grade_scope"] == "all" and info["grade_scopes"] == ["all", "skin", "brush"]


def _ungraded_frame(pipe):
    """判据的对照面：这一层没点火时的那一帧（磨皮也不点火，所以差只属于定向层）。"""
    pipe.clear_grade()
    pipe.render(0.0)
    return pipe.read_back()[..., :3].copy()


def test_local_grade_leaves_outside_the_region_byte_identical(layer):
    """蒙版外逐字节恒等（判据一）。用位相等而不是 LSB 差：这条承诺是结构性的。

    写成混式 (1-w)·t + w·out 而不是“先混色再乘”，正是为了让它在 w=0 处无条件成立。
    对照帧必须在**点火之前**取：先 set_grade 再 render 拿到的“基帧”是全图调过色的，
    那时这条判据比的就不是“蒙版外”而是“蒙版内外谁都不许变”（本仓踩过的那类自伤判据）。
    """
    pipe, _rgb = layer
    base = _ungraded_frame(pipe)
    pipe.set_grade(0.006, -0.14, 0.05, amount=1.0)
    pipe.set_grade_mask(_half_mask(left=True), mode="replace")
    info = pipe.set_grade_scope("brush")
    assert info["mask_px"] == H * (W // 2), info
    pipe.render(0.0)
    got = pipe.read_back()[..., :3]
    right = slice(W // 2, W)
    assert np.array_equal(got[:, right], base[:, right]), "蒙版外像素被改了"
    left = slice(0, W // 2)
    assert not np.array_equal(got[:, left], base[:, left]), "蒙版内一点没动：局部调色是假的"


def test_local_grade_boundary_has_no_hard_color_step(layer):
    """无明显色边（判据三）：羽化必须把“层效应”的台阶摊开，而不是只让画面动起来。

    比的是**差场** d = |点火帧 − 基帧| 的相邻跳变，不是画面本身的相邻差：这张合成图
    有一条跨 57 列的水平渐变与 ±0.06 的噪声，画面差里混着它自己的结构，拿它当对照就
    把“羽化有没有摊开台阶”问成了“这张图哪里有边缘”（上一版就是这么错的：羽化那臂
    量到 19、硬边那臂量到 15，判据整个反了）。
    """
    from lumaretouch_engine.ops.inpaint import feather_np

    pipe, _rgb = layer
    base = _ungraded_frame(pipe).astype(np.int16)
    hard = np.zeros((H, W), np.uint8)
    hard[:, :W // 2] = 255

    pipe.set_grade(0.006, -0.14, 0.05, amount=1.0)
    pipe.set_grade_mask(hard, mode="replace")
    pipe.set_grade_scope("brush")
    pipe.render(0.0)
    d_hard = np.abs(pipe.read_back()[..., :3].astype(np.int16) - base)

    soft_u8 = np.rint(np.clip(feather_np((hard > 0).astype(np.float32), 3), 0.0, 1.0)
                      * 255.0).astype(np.uint8)
    pipe.set_grade_mask(soft_u8, mode="replace")
    pipe.render(0.0)
    d_soft = np.abs(pipe.read_back()[..., :3].astype(np.int16) - base)
    # 盒式羽化的支撑半径就是 r：再往外必须逐字节为 0（“局部”两字的另一半）
    assert int(d_soft[:, W // 2 + 3:].max()) == 0, "羽化支撑之外还有变化：那不再是局部"

    jump_hard = int(np.abs(np.diff(d_hard, axis=1)).max())
    jump_soft = int(np.abs(np.diff(d_soft, axis=1)).max())
    peak = int(d_soft.max())
    assert peak > 0, "点火了却没有层效应：那这三条判据全部恒真"
    assert jump_soft < jump_hard, f"羽化没摊开台阶：{jump_soft} vs {jump_hard}"
    assert jump_soft <= peak, f"边界那一跳超过了整片区域的变化幅度（振铃）：{jump_soft} vs {peak}"


def test_scope_without_the_underlying_mask_is_refused_and_changes_nothing(layer):
    """skin 没 precompute、brush 没区域 → 整条拒，不留半截状态（不许静默退回全图）。"""
    pipe, _rgb = layer
    pipe.set_grade(0.006, -0.14, 0.05)
    snap = (pipe.grade_scope, pipe.grade_mask, pipe.grade_params, pipe.grade_amount)
    with pytest.raises(ValueError, match="precompute"):
        pipe.set_grade_scope("skin")
    with pytest.raises(ValueError, match="一笔"):
        pipe.set_grade_scope("brush")
    with pytest.raises(ValueError, match="作用域"):
        pipe.set_grade_scope("everything")
    assert (pipe.grade_scope, pipe.grade_mask, pipe.grade_params, pipe.grade_amount) == snap


def test_grade_mask_shape_dtype_and_empty_are_all_refused(layer):
    """区域是代理帧坐标：尺寸不对、位宽不对、全空都得拒（拿原图坐标递过来就是静默错位）。"""
    pipe, _rgb = layer
    pipe.set_grade(0.006, -0.14, 0.05)
    for bad in (np.zeros((H + 1, W), np.uint8), np.zeros((H, W), np.float32),
                np.zeros((H, W), np.uint8)):
        with pytest.raises(ValueError):
            pipe.set_grade_mask(bad, mode="replace")
    assert pipe.grade_mask is None
    with pytest.raises(ValueError, match="mode"):
        pipe.set_grade_mask(_half_mask(), mode="union")


def test_brush_mask_add_takes_union_and_replace_takes_this_stroke(layer):
    """第二笔不该擦掉第一笔（add 取并集），而“重新画”语义（replace）得能真的重来。"""
    pipe, _rgb = layer
    a = np.zeros((H, W), np.uint8); a[:, :4] = 255
    b = np.zeros((H, W), np.uint8); b[:, -4:] = 255
    pipe.set_grade_mask(a, mode="replace")
    pipe.set_grade_mask(b, mode="add")
    assert int(pipe.grade_mask[:, :4].min()) == 255 and int(pipe.grade_mask[:, -4:].min()) == 255
    assert pipe.grade_mask.mean() < 200, "add 把整张图都涂满了：那是“取大”而不是“累加”"
    pipe.set_grade_mask(b, mode="replace")
    assert int(pipe.grade_mask[:, :4].max()) == 0, "replace 没抹掉上一笔"


def test_brush_scope_resides_a_mask_and_clearing_it_releases_the_memory(layer):
    """brush 时真的常驻一份权重（账单非 0），清掉区域后账单回 0、作用域退回 all。"""
    pipe, _rgb = layer
    pipe.set_grade(0.006, -0.14, 0.05)
    pipe.set_grade_mask(_half_mask(), mode="replace")
    assert pipe.grade_resident_bytes() == 0, "没切作用域不该上显存"
    info = pipe.set_grade_scope("brush")
    assert info["bytes_grade"] == H * W * 4, f"掩膜权重没常驻：{info['bytes_grade']}"
    cleared = pipe.clear_grade_mask()
    assert cleared["grade_scope"] == "all" and cleared["mask_px"] == 0
    assert pipe.grade_resident_bytes() == 0
    assert pipe.grade_params == (0.006, -0.14, 0.05), "清区域不该把参数也抹了"


def test_clear_grade_keeps_the_region_the_user_painted(layer):
    """滑块归零不该顺手抹掉用户拿笔涂出来的东西（params 与 region 的分工）。"""
    pipe, _rgb = layer
    pipe.set_grade(0.006, -0.14, 0.05)
    pipe.set_grade_mask(_half_mask(), mode="replace")
    pipe.set_grade_scope("brush")
    info = pipe.clear_grade()
    assert info["grade_lit"] is False
    assert info["grade_scope"] == "brush" and info["mask_px"] == H * (W // 2)
    assert pipe.grade_mask is not None
    # 关掉整层后画面逐字节回到基帧（那一层没点火，区域也就无从生效）
    pipe.render(0.0)
    off = pipe.read_back()[..., :3].copy()
    pipe.set_grade(0.006, -0.14, 0.05)
    pipe.render(0.0)
    assert not np.array_equal(pipe.read_back()[..., :3], off), "重新开火后区域丢了"
