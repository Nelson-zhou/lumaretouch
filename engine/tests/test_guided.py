"""算子正确性：numpy 参考实现 vs torch 生产实现。

M0 只要求「GPU 与 CPU 数值一致」——不一致就不许把 GPU 内核接进交互链路。
"""

from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops.guided import (bands_np, combine_np, guided_np, _box_np,
                                           retouch_np, frequency_split_np)

RNG = np.random.default_rng(20261016)


def box_bruteforce(x: np.ndarray, r: int) -> np.ndarray:
    """朴素窗口循环，作为 _box_np 的绝对参照（小图才跑得动）。"""
    b, c, h, w = x.shape
    p = np.pad(x, ((0, 0), (0, 0), (r, r), (r, r)), mode="reflect")
    out = np.empty_like(x)
    k = 2 * r + 1
    for i in range(h):
        for j in range(w):
            out[:, :, i, j] = p[:, :, i:i + k, j:j + k].sum(axis=(2, 3)) / float(k * k)
    return out


@pytest.mark.parametrize("r", [1, 3, 6])
def test_box_matches_bruteforce(r):
    x = RNG.random((1, 3, 24, 32), dtype=np.float32)
    assert np.abs(_box_np(x, r) - box_bruteforce(x, r)).max() < 1e-5


def test_guided_with_huge_eps_equals_double_box():
    """eps→∞ 时 a→0、b→mean，输出应退化为对均值再滤一次。"""
    x = RNG.random((1, 3, 48, 64), dtype=np.float32)
    got = guided_np(x, 4, eps=1e6)
    want = _box_np(_box_np(x, 4), 4)
    assert np.abs(got - want).max() < 1e-4


def test_guided_preserves_hard_edge():
    """保边是本算法的立身之本：阶跃边界两侧必须仍然分明。"""
    x = np.zeros((1, 3, 64, 64), np.float32)
    x[:, :, :, 32:] = 0.8
    out = guided_np(x, 8, eps=1e-4)
    jump = out[0, 0, 32, 32] - out[0, 0, 32, 31]
    flat = out[0, 0, 10, 50] - out[0, 0, 10, 40]
    assert jump > 0.6, f"边缘被抹平了：jump={jump:.3f}"
    assert abs(flat) < 1e-3


def test_retouch_strength_zero_is_identity():
    x = RNG.random((1, 3, 40, 40), dtype=np.float32)
    assert np.abs(retouch_np(x, 0.0) - x).max() < 1e-7


def test_frequency_split_reconstructs_original():
    x = RNG.random((1, 3, 40, 40), dtype=np.float32)
    low, high = frequency_split_np(x, 5, 1e-3)
    assert np.abs((low + high) - x).max() < 1e-6


def test_slider_actually_changes_the_image():
    """滑块必须真有效——防住“相加项被写坏以致整条链变成空操作”这类退位。

    白噪声上“去斑”测不出东西（噪声的局部方差远大于 eps），所以这里用结构图：
    带内容（斑）的那张图在默认位上必须被明显改动。
    """
    x, _, _ = _skin_like(side=129)
    delta = np.abs(retouch_np(x, 1.0) - x).mean()
    assert delta > 1e-3, f"强度拉几乎没变化（delta={delta:.2e}），滑块是空的"


def test_strength_is_monotonic():
    x, _, _ = _skin_like(side=129)
    d1 = np.abs(retouch_np(x, 0.3) - x).mean()
    d2 = np.abs(retouch_np(x, 0.9) - x).mean()
    assert d2 > d1 > 0, f"强度不单调：s=0.3→{d1:.4f}, s=0.9→{d2:.4f}"


def _skin_like(side=193, seed=20261016):
    """已知成分的皮肤替身：平坦底色 + 中带高斯斑 + 细带颗粒 + 一条硬边缘。

    为什么需要它：白噪声图上 `a = var/(var+eps) ≈ 1`，导向滤波本来就不平滑它，
    拿噪声图测“去斑/保孔”永远是空门禁（这个坑 M1 已经踩过一次，写在了 _box_t 的
    注释里）。只有把**已知幅度、已知尺度**的两条带写进同一张图，才能问出
    “这带被留住了几成”。返回 (img, 斑, 孔) 三个 float64 (1,1,H,W)。
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float64)
    base = 0.62 + 0.03 * np.sin(2 * np.pi * xx / (side * 0.9)) + 0.05 * (yy / side)
    blemish = np.zeros((side, side))
    for _ in range(18):
        cy, cx = rng.integers(15, side - 15, 2)
        rad = float(rng.uniform(9.0, 14.0))
        blemish += float(rng.normal(0.0, 0.035)) * np.exp(
            -((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * rad * rad))
    pore = rng.normal(0.0, 0.013, size=(side, side)) * rng.random((side, side)) ** 0.5
    img = np.clip(base + blemish + pore, 0, 1)
    b3 = np.ascontiguousarray(img[None, None])
    return b3, np.ascontiguousarray(blemish[None, None]), np.ascontiguousarray(pore[None, None])


def _band_gain(out, blemish, pore):
    """在已知注入成分上做最小二乘，读回“这条带被留住了几成”。"""
    o = np.asarray(out)[0, 0].ravel()
    ones = np.ones(o.size)
    X = np.stack([ones, _flat_base(o.size), blemish.ravel(), pore.ravel()], 1)
    beta, *_ = np.linalg.lstsq(X, o, rcond=None)
    return float(beta[3]), float(beta[2])


_BASE_CACHE = {}


def _flat_base(n):
    """回归里的底色项：与 _skin_like 用的同一个公式（side 当参数缓存）。"""
    side = int(round((n) ** 0.5))
    if side not in _BASE_CACHE:
        yy, xx = np.mgrid[0:side, 0:side].astype(np.float64)
        _BASE_CACHE[side] = (0.62 + 0.03 * np.sin(2 * np.pi * xx / (side * 0.9))
                             + 0.05 * (yy / side)).ravel()
    return _BASE_CACHE[side]


def test_bands_partition_is_algebraically_exact():
    """四条带相加必须逐点回到原图——这是“带增益”这个词能成立的前提。

    如果哪天有人把某一band 的定义改了而没同步补上，恒等先碎，三个滑块就变成
    三个互相抵消的系数，数值上再也说不清“保留了 多少肌理”。
    """
    x = RNG.random((1, 3, 64, 80), dtype=np.float32)
    base, broad, mid, tex = bands_np(x, 6, 6e-4, 4)
    assert np.abs((base + broad + mid + tex) - x).max() < 1e-5, "四带之和不是原图"
    assert np.abs(combine_np(base, broad, mid, tex, 1.0, 1.0, 1.0) - x).max() < 1e-5


def test_texture_band_gain_is_the_pore_knob():
    """M2-a 的核心数值主张：detail_gain 只动细带，而且 =1.0 时毛孔基本全留。

    实测默认位 (broad=0, mid=0, tex=1)：孔增益 0.99、斑增益 0.40。这条就是
    “质感磨皮不是塑料脸”的可复现证据，也是 plan 决策 6“高频层保留 100% 能量”
    第一次被量出来而不是被写在文档里。
    """
    x, blemish, pore = _skin_like()
    base, broad, mid, tex = bands_np(x.astype(np.float64), 12, 6e-4, 4)
    pk0, bl0 = _band_gain(x, blemish, pore)
    assert abs(pk0 - 1.0) < 0.02 and abs(bl0 - 1.0) < 0.02, f"回归自校不准：{pk0} {bl0}"

    out = combine_np(base, broad, mid, tex, 0.0, 0.0, 1.0)
    pk, bl = _band_gain(out, blemish, pore)
    assert pk > 0.95, f"默认位把毛孔削到 {pk:.3f}，磨皮变成了模糊"
    assert bl < 0.55, f"默认位只把色斑压到 {bl:.3f}，磨皮根本没干活"

    # 细带增益拉到 0 就应当真的把毛孔抹掉：证明这个旋钮不是装饰
    pk_flat, _ = _band_gain(combine_np(base, broad, mid, tex, 0.0, 0.0, 0.0), blemish, pore)
    assert pk_flat < 0.10, f"tex 增益归零后毛孔还剩 {pk_flat:.3f}，旋钮是空的"


def test_linear_texture_band_beats_the_guided_residual():
    """为什么要用线性高通取纹理带，而不是像 M1-3c 那样取 guided 的残差。

    guided 本身就是收缩算子，残差里只带着部分毛孔幅度；dg=1.0 在那条链上是假的。
    本条把两种取法放在一起比：线性带必须明显更保孔。
    """
    x, blemish, pore = _skin_like()
    xd = x.astype(np.float64)
    # 线性带（rf=4）
    base, broad, mid, tex = bands_np(xd, 12, 6e-4, 4)
    pk_lin, bl_lin = _band_gain(combine_np(base, broad, mid, tex, 0.0, 0.0, 1.0), blemish, pore)
    # guided 残差当纹理带（rf=0 ⇒ blur=原图、tex=0，等价于 M1-3c 那条链）
    low1 = guided_np(xd, 12, 6e-4)
    low2 = guided_np(low1, 24, 2.4e-3)
    pk_old, bl_old = _band_gain(low2 + (xd - low1) * 1.0, blemish, pore)
    assert pk_lin > pk_old + 0.05, f"线性带没更保孔：{pk_lin:.3f} vs {pk_old:.3f}"
    assert bl_lin < bl_old, f"线性带没更去斑：{bl_lin:.3f} vs {bl_old:.3f}"


def test_box_accumulator_is_exact_enough_for_cpu_gpu_parity():
    """积分图的累加器必须是 float64，否则小窗口那趟会把两边各自算错。

    float32 累加时 672×848 上 r=4 单趟就有 2.2e-03 的绝对错（约半 LSB），且 CPU/GPU
    各自往不同方向错——透到 tex 带上就是系统性半 LSB 偏移，而“最大差”仍然只 1 LSB，
    恰好是会被验收口径掩盖的那一类。

    本条不是拿“现在的实现”与“现在的实现”自证：它把**旧写法**（累加器跟输入同精度）
    当场复现出来，先证明这个坑在本尺寸下真能踩到（>1e-3），再证明现实现不在坑里。
    不这么做的话，改了累加器之后这条测试会变成恒真，下次谁把它改回去也不会红。

    尺寸必须是产品代理档（672×848）：前缀和的量级与**行长**成正比，129×129 上旧写法
    只差 4.7e-05（实测），拿小图定这条门禁就是空的。
    """
    yy, xx = np.mgrid[0:848, 0:672].astype(np.float64)
    # 亮区为主（肤色均值 ~0.65）：前缀和的量级就是这个数乘上行宽
    x = np.ascontiguousarray(
        np.stack([(0.65 + 0.02 * np.sin(2 * np.pi * xx / 300) + 0.001 * ((xx * 7 + yy * 13) % 11)
                  - 0.005)] * 3)[None])
    x32 = np.ascontiguousarray(x.astype(np.float32))

    def box_f32acc(img, r):
        """旧写法：累加器就用输入自己的 float32（这个参照必须手写，不能叫库自己当参照）。"""
        p = np.pad(img, ((0, 0), (0, 0), (r, r), (r, r)), mode="reflect")
        cs = np.cumsum(np.cumsum(p, axis=2), axis=3)
        c = np.zeros(p.shape[:2] + (p.shape[2] + 1, p.shape[3] + 1), dtype=cs.dtype)
        c[:, :, 1:, 1:] = cs
        k = 2 * r + 1
        tot = c[:, :, k:, k:] - c[:, :, :-k, k:] - c[:, :, k:, :-k] + c[:, :, :-k, :-k]
        return tot / float(k * k)

    errs = {}
    for r in (4, 12, 24):
        truth = _box_np(x, r)                      # float64 输入 + float64 累加 = 本库的真值
        now = _box_np(x32, r).astype(np.float64)
        old = box_f32acc(x32, r).astype(np.float64)
        # 真值与 float32 输入自身舍入的差在 1e-7 量级，所以这个容差只卡累加器
        assert float(np.abs(now - truth).max()) < 2e-5, f"r={r} 现实现偏离真值"
        errs[r] = float(np.abs(old - truth).max())
        assert errs[r] > 1e-4, f"r={r} 旧写法没报错：这条门禁是空的"
    # 真正 decisive 的是小窗口：前缀和与行长成正比、除的却是 k²，所以窗口越小相对错越大
    assert errs[4] > 1e-3, f"r=4 旧写法只错 {errs[4]:.2e}，tex 带的取法不依赖累加器精度"
    assert errs[4] > errs[12] > errs[24], f"误差没随窗口缩小而放大：{errs}"


def test_guided_gain_stays_bounded_on_smoothed_input():
    """`a = var/(var+eps)` 必须夹住：方差算成负数时它会爆。

    数学上方差非负，但 `mean_ii − mean_i²` 是两个大数相减，平坦区会得到小负值；
    落到 −eps 附近就是除以零量。实测把一张预先盒式平滑过的图喂进去（M2-a 分带
    就是这么送的），不夹零时 a 能到 +232（rf=4）甚至 +1.5e+04（rf=8），且占 12%～22%
    的像素——a 直接乘在图上，那就是几十 LSB 的错。
    """
    x, _, _ = _skin_like(side=193)
    for rf in (0, 4, 8, 16):
        blur = _box_np(x, rf)
        out = guided_np(blur, 12, 6e-4)
        assert np.abs(out).max() <= 1.0 + 1e-6, f"rf={rf} 导向滤波产出越界：{np.abs(out).max():.3f}"
        assert np.isfinite(out).all()


def test_detail_gain_zero_yields_lowpass_only():
    """精确组成关系：三个增益全 0 且强度 1 时，输出必须恰好等于 base 带。

    （白噪声上用“方差必须下降”断言是错的：噪声局部方差远大于 eps，
    导向滤波的 a=var/(var+eps)≈1，本来就不会平滑它。）
    """
    x = RNG.random((1, 3, 64, 64), dtype=np.float32)
    base, broad, mid, tex = bands_np(x, 6, 6e-4, 4)
    out = retouch_np(x, 1.0, radius=6, detail_gain=0.0, mid_gain=0.0, broad_gain=0.0)
    assert np.abs(out - base).max() < 1e-5, "三增益归零不等于只剩 base"
    assert np.abs(base - guided_np(guided_np(_box_np(x, 4), 6, 6e-4), 12, 2.4e-3)).max() < 1e-5


def test_band_gains_are_linear_independent_knobs():
    """三个增益各自只动自己那条带：叠加关系必须是线性的。

    这条是 UI 上“匀肤/细节/肌理”三个滑块互相不打架的根据：
    out(bg,mg,dg) − out(0,0,0) 必须恰好等于 bg·broad + mg·mid + dg·tex。
    """
    x = RNG.random((1, 3, 64, 64), dtype=np.float32)
    base, broad, mid, tex = bands_np(x, 6, 6e-4, 4)
    for bg, mg, dg in ((0.3, 0.0, 0.0), (0.0, 0.45, 0.0), (0.0, 0.0, 0.7), (0.2, 0.5, 0.9)):
        out = retouch_np(x, 1.0, radius=6, detail_gain=dg, mid_gain=mg, broad_gain=bg)
        want = base + broad * bg + mid * mg + tex * dg
        assert np.abs(out - want).max() < 1e-5, f"({bg},{mg},{dg}) 带间串了"


def test_torch_matches_numpy_within_tolerance():
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("无 GPU 可用")
    from lumaretouch_engine.ops.guided import make_tensor, retouch_t, to_numpy_chw

    x = RNG.random((128, 160, 3), dtype=np.float32)
    chw = x.transpose(2, 0, 1)[None]
    ref = retouch_np(chw, strength=0.6, radius=10, eps=6e-4)

    t = make_tensor(x, "cuda")
    out = to_numpy_chw(retouch_t(t, strength=0.6, radius=10, eps=6e-4))
    diff = np.abs(out.transpose(2, 0, 1)[None] - ref).max()
    assert diff < 2e-3, f"GPU 与 CPU 结果不一致，max diff={diff:.2e}"


def test_gpu_cpu_parity_at_product_proxy_size():
    """产品代理档（672×848）上的 GPU/CPU 对拍。

    上面那条只在 128×160 的噪声图上比，那个组合下端到端差才 2.5e-4，看着很紧。
    真实照片的平坦皮区会让 `a = var/(var+eps)` 除以小量，把累加噪声放大一个量级；
    而 672×848 恰好就是产品默认像素预算。门禁定在小图上等于没定。

    M2-a 把积分图的累加器改成 float64 之后，这个差的量级变了：两边算的是同一个
    精确和（float32 尾数 24 位、元素数 ~1e6，加起来仍落在 float64 的精确区间里），
    只是各自舍回 float32。实测 float 差从 3.34e-03 降到 **1.19e-07**，
    且差异子像素占比从 1.4% 降到 **0.00%**。
    容差跟着收紧而不是原地不动——不然这条门禁就盖不住“把累加器改回去”那种退化。
    真正的验收口径仍是量化后的字节：最大 ≤1 LSB、且不同子像素占比 <0.5%。
    """
    import os

    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("无 GPU 可用")
    from lumaretouch_engine.decode import load_rgb
    from lumaretouch_engine.ops.guided import make_tensor, retouch_np, retouch_t

    jpg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tests", "fixtures", "portrait-1024x1280.jpg")
    if not os.path.isfile(jpg):
        pytest.skip("缺测试人像，先跑 packaging/make-test-portrait.py")
    d = load_rgb(jpg)                      # 产品默认 4K 预算：1024×1280 原幅不缩
    assert (d.h, d.w) == (1280, 1024), f"fixture 预算变了：{d.w}x{d.h}"

    chw = np.ascontiguousarray(d.rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
    f32 = d.rgb.astype(np.float32) / 255.0          # make_tensor 只收 [0,1] 浮点（uint8 会被拒）
    q = lambda a: (np.clip(a, 0, 1) * 255).astype(np.uint8).astype(np.int16)  # noqa: E731
    for s in (0.3, 0.85):
        ref = retouch_np(chw, strength=s)
        out = retouch_t(make_tensor(f32, "cuda"), strength=s)[0].cpu().numpy()
        fdiff = float(np.abs(out - ref).max())
        bdiff = np.abs(q(out) - q(ref))          # 比的是两个实现，不是“输出 vs 原图”
        ratio = float((bdiff > 0).mean())
        assert fdiff < 5e-7, f"s={s} 产品档 float 差 {fdiff:.2e}，超出实测水平（1.2e-7）的余量"
        assert bdiff.max() <= 1, f"s={s} 量化后差 {int(bdiff.max())} LSB，超出验收口径"
        assert ratio < 0.005, f"s={s} 有 {ratio:.1%} 子像素在差，不能拿“最大 1 LSB”当安全"


def test_make_tensor_rejects_uint8():
    """make_tensor 必须拒收 uint8。

    它只做转置与搬运、不除 255，所以传错尺子时不报错、静默给出一张 0..255 的图：
    实测与参考实现最大差 2.5e+02（等于整幅图全黑与全白的差别）。写探针的人连着踩过
    两次，说明这条路本身就该封掉而不是靠人记住。
    """
    pytest.importorskip("torch")
    from lumaretouch_engine.ops.guided import make_tensor

    with pytest.raises(TypeError, match="float32"):
        make_tensor(np.zeros((8, 8, 3), dtype=np.uint8), "cpu")
    with pytest.raises(TypeError, match="255"):
        make_tensor(np.zeros((8, 8, 3), dtype=np.int32), "cpu")
    # 浮点仍然正常
    ok = make_tensor(np.zeros((8, 8, 3), dtype=np.float32), "cpu")
    assert ok.shape == (1, 3, 8, 8) and ok.dtype.is_floating_point
