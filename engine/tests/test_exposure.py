"""ops/exposure.py：中性恒等、两臂对拍、越界拒绝、方向符号。

中性那条是全模块最硬的承诺（frozen registry 的 identity 容差写 0），所以这里的判据是
**量化到 uint16 后逐字节相等**，而不是 np.allclose——allclose 会放过 1e-16 的红入，
而红入在别的模块里可能就是不可见的，在这个模块里是违约。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops import exposure as ex


def _u16(a: np.ndarray) -> np.ndarray:
    """自己的量化判据，不复用引擎里的量化器：拿被验对象的工具去验它，
    工具错时两边会一起错。这里只要“round 到 16-bit 整数格点”这一条语义。"""
    return np.rint(np.clip(a, 0.0, 1.0) * 65535.0).astype(np.uint64)


def _grad(h: int = 37, w: int = 53) -> np.ndarray:
    """非对称梯度样本：避免对称图让"通道搞反"这类错看起来是对的。

    必须 broadcast 完再 stack：三个通道形状不一样（(1,w)/(h,1)/(h,w)）时 np.stack 直接
    报 all input arrays must have the same shape——这个坑我自己踩了一次，7 条用例
    全红在一个夹具上，看起来像模块写坏了。red herring 的代价比 bug 本身大。
    """
    yy = np.linspace(0.03, 0.97, h)[:, None]
    xx = np.linspace(0.05, 0.95, w)[None, :]
    r = np.broadcast_to(xx, (h, w))
    g = np.broadcast_to(yy, (h, w))
    b = (xx + yy) % 1.0
    return np.stack([r, g, b], axis=-1).astype(np.float64)   # (h,w,3)


# ------------------------------------------------------------------ 中性恒等
def test_neutral_op_is_within_1lsb_after_quantization():
    """op 级中性：量化到 16-bit 后最大偏差必须 ≤ 1 LSB。

    口径写在 ops/exposure.py：“逐字节恒等（容差 0）”由**链上未点火短路**保证，
    而这里量的是“sRGB 传递函数解析往返 + 双精度”落在整数格点上的真实红入。
    把两个口径混成一条的话，要么测不到真行为，要么要模块假称自己逐位相等。
    """
    x = _grad()
    out = ex.exposure_np(x, 0.0, 0.0, 0.0)
    a = np.abs(_u16(out).astype(np.int64) - _u16(x).astype(np.int64))
    assert int(a.max()) <= 1, f"中性 op 级往返超过 1 LSB：{int(a.max())}"


def test_neutral_gains_are_exactly_one_not_just_close():
    """这个断言针对我犯过的错：CAT 写成 M⁻¹·diag·M 时 shift=0 给的不是单位阵。

    只比 allclose 会放过它；比 `== 1.0` 才守得住"恒等由算式给出"这句话。
    """
    g = ex.wb_gains(0.0, 0.0)
    assert g.shape == (3,)
    assert np.all(g == 1.0), f"shift=0 的增益必须精确等于 1.0，得到 {g!r}"
    assert ex.ev_gain(0.0) == 1.0


# ------------------------------------------------------------------ 量程与非法值
@pytest.mark.parametrize("bad", [12.0, -12.0, float("nan"), float("inf"), "x", None])
def test_illegal_ev_is_rejected_not_clamped(bad):
    """拒绝而不是夹取：夹取会让坏配方看起来正常，而画面不是用户要的那张。"""
    with pytest.raises(ValueError):
        ex.exposure_np(_grad(), bad, 0.0, 0.0)


@pytest.mark.parametrize("bad", [3000.0, float("nan"), -7000.0])
def test_out_of_range_kelvin_shift_rejected(bad):
    with pytest.raises(ValueError):
        ex.exposure_np(_grad(), 0.0, bad, 0.0)


@pytest.mark.parametrize("bad", [1.5, float("inf")])
def test_out_of_range_tint_rejected(bad):
    with pytest.raises(ValueError):
        ex.exposure_np(_grad(), 0.0, 0.0, bad)


def test_boundary_values_are_accepted():
    """量程端点本身合法（BOUNDARY 用例要的是端点不崩，不是端点被拒）。"""
    for ev in (ex.EV_LIMIT, -ex.EV_LIMIT):
        o = ex.exposure_np(_grad(), ev, 0.0, 0.0)
        assert np.all(np.isfinite(o)) and o.min() >= 0.0 and o.max() <= 1.0
    for dk in (ex.TEMP_LIMIT_K, -ex.TEMP_LIMIT_K):
        assert np.all(np.isfinite(ex.wb_gains(dk, 0.0)))
    for t in (ex.TINT_LIMIT, -ex.TINT_LIMIT):
        assert np.all(np.isfinite(ex.wb_gains(0.0, t)))


# ------------------------------------------------------------------ 方向语义
def test_positive_ev_doubles_linear_light_not_gamma_value():
    """1 EV = 线性光翻倍。**不是**输出像素翻倍。

    这条用例自己错过一次：它先写于“拿 gamma 值直接乘”的版本，当时比值确实是 2.0；
    加了线性化后它变红，红得对——因为错的不是实现而是这条断言的口径。
    量在 gamma 域里的“翻倍”实际只相当于 +0.45 档，那才是错的东西。
    """
    x = _grad()
    up = ex.exposure_np(x, 1.0, 0.0, 0.0)
    assert up.mean() > x.mean()
    lo_in = ex._lin_np(x)
    lo_out = ex._lin_np(up)
    keep = (lo_in > 0.02) & (lo_out < 0.98)      # 剔掉黑端与将被夹住的高光
    ratio = lo_out[keep] / lo_in[keep]
    assert np.allclose(ratio, 2.0, rtol=1e-4), \
        f"1 EV 应让线性光翻倍，实测 {ratio.min():.4f}–{ratio.max():.4f}"
    # 反向：gamma 域比值应接近 2**(1/2.4)≈1.33而不是 2
    g = _grad()
    gm = (g > 0.05) & (ex.exposure_np(g, 1.0, 0.0, 0.0) < 0.99)
    enc = (up[gm] / x[gm])
    assert 1.2 < enc.mean() < 1.55, f"gamma 域比值异常：{enc.mean():.3f}"


def test_positive_kelvin_shift_compensates_toward_cooler():
    """符号口径（实测钉死，别按"暖/冷"字面猜）：

    temperature_shift 的语义是**目标白**的色温。+800 K = 目标白 D7300（更蓝），
    于是 R 增益降到 0.954、B 抬到 1.081 —— 画面被补偿得**偏冷**。
    直觉里"拉高色温=变暖"说的是光源本身，而不是这个滑杆；UI 文案必须按这里的口径写，
    否则用户看到的方向与标签相反。第一版断言就是这么反着写的，实测数据把它纠正了。
    """
    g_hi = ex.wb_gains(+800.0, 0.0)
    g_lo = ex.wb_gains(-800.0, 0.0)
    assert g_hi[0] < 1.0 < g_hi[2], f"+800 K 应压 R 抬 B，得到 {g_hi}"
    assert g_lo[0] > 1.0 > g_lo[2], f"−800 K 应抬 R 压 B，得到 {g_lo}"


def test_positive_tint_is_magenta_not_green():
    """正=洋红：M 通道（绿）受抑、R/B 相对抬升。反过来 UI 就是反的。"""
    g = ex.wb_gains(0.0, +0.5)      # 实测 [1.0605, 0.9775, 0.9677]
    assert g[1] < 1.0 and g[0] > 1.0, f"正 tint 必须压绿抬红（洋红方向），得到 {g}"
    gn = ex.wb_gains(0.0, -0.5)
    assert gn[1] > 1.0 and gn[0] < 1.0, f"负 tint 必须抬绿压红（绿方向），得到 {gn}"


def test_gain_vector_is_monotonic_in_temperature_shift():
    """同一支 R/B 增益比必须随偏移单调——不单调说明 cct_xy 的分段在交界处跳了。"""
    ks = np.linspace(-1900, 1900, 39)
    ratios = [ex.wb_gains(float(k), 0.0)[0] / ex.wb_gains(float(k), 0.0)[2] for k in ks]
    d = np.diff(ratios)
    assert np.all(d < 0), (f"R/B 增益比应随目标色温升高单调下降"
                    f"（实测 +800 K 时 R 0.954/B 1.081）；最小步 {d.max():.3e}")


def test_cct_xy_matches_published_illuminant_chromaticities():
    """锚点对账：这三组是 CIE 公布的标准色度坐标，不是我自己算出来的参考。

    为什么必须有这条：cct_xy 的第一个版本错在拄错了分段系数，而它错得很“安静”——
    到 7000 K 以上才爆。拿公布值一对，拄错当场就红。
    D75 用 7347 K 而不是 7500 K：那是 D75 的相关色温本身（命名里的 75 是序列名，不是 CCT）。
    """
    for k, want in ((5000.0, (0.3457, 0.3585)),      # D50
                    (6500.0, (0.3127, 0.3290)),      # D65
                    (7347.0, (0.2990, 0.3149))):     # D75
        got = ex.cct_xy(k)
        # 容差 3e-3 不是随手放的：D75 的公布坐标对应的 CCT 在 7347 K 附近，
        # 而 D 系列参数化本身在高位端只给到 10⁻³ 量级的准确度。
        # 拿更紧的容差会测到“公式超出自己的适用域”，而不是测到抄错。
        assert abs(got[0] - want[0]) < 3e-3 and abs(got[1] - want[1]) < 3e-3, \
            f"{k} K 得 {got}，公布值 {want}——系数抄错或分段用错"


def test_below_daylight_domain_is_rejected_not_guessed():
    """低于 4003 K 必须拒。黑体轨迹那段我第一版拄错了，现在宁缺不假。"""
    with pytest.raises(ValueError, match="日光轨迹|不在本层可算域"):
        ex.cct_xy(2856.0)
    with pytest.raises(ValueError):
        ex.wb_gains(0.0, 0.0, ref_k=3000.0)


def test_daylight_sub_branch_discontinuity_is_immaterial_to_gains():
    """CIE 日光轨迹的 x 分两段，在 7000 K 处有 0.004 的不连续——那是标准本身的性质。

    所以这里不假装“xy 连续”，而是问真正要紧的东西：滑杆经过 7000 K 时，
    最细粒度（25 K）的增益变化必须与相邻步同一量级。若把子式合并成一段会改变
    这个跳变量，那时候这条就该红。
    """
    a = ex.cct_xy(6999.0)
    b = ex.cct_xy(7001.0)
    jump = abs(a[0] - b[0])
    assert jump < 0.01, f"7000 K 处 x 跳了 {jump:.4f}，不是标准那个 0.004 量级"
    # 25 K 一格的增益差应当连续（不跨段）；跨段那一格允许比相邻步大，但必须有限且小
    base = ex.wb_gains(500.0, 0.0)
    step = ex.wb_gains(525.0, 0.0)
    d = np.max(np.abs(step / base - 1.0))
    # 实测 2.0%：D 轨迹在 7000 K 附近对色温本就很敏感，这是标准的性质不是实现的红入。
    # 阈值放 3%（比实测留有余量），它守的是"不要出现 10% 级的台阶"，不是"必须平滑"。
    assert d < 0.03, f"25 K 一格动了 {d:.3%}，超出可接受的灵敏度"


# ------------------------------------------------------------------ 两臂对拍
def test_torch_arm_matches_numpy_arm():
    torch = pytest.importorskip("torch")
    x = _grad()
    t = torch.from_numpy(x.transpose(2, 0, 1)[None, :, :, :].copy()).double()
    for ev, dk, tint in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 600.0, 0.0),
                         (-0.5, -900.0, 0.3), (2.0, 1500.0, -0.7)):
        a = ex.exposure_np(x, ev, dk, tint)
        b = ex.exposure_t(t, ev, dk, tint)[0].numpy().transpose(1, 2, 0)
        d = np.abs(_u16(a).astype(np.int64) - _u16(b).astype(np.int64))
        assert d.max() <= 1, f"两臂在 ({ev},{dk},{tint}) 差 {d.max()} LSB（>1 说明算式分家）"


def test_torch_arm_neutral_returns_same_object_via_apply_helper():
    """apply_exposure_t 在中性时必须**原样返回同一个张量**（不复制、不过算子）。

    这是显存与带宽的承诺；同时它也必须与"过一遍算式"的结果逐字节相同——两条在下面对拍。
    """
    torch = pytest.importorskip("torch")
    t = torch.rand(1, 3, 8, 8, dtype=torch.float32)
    before = t.clone()
    assert ex.apply_exposure_t(t, None) is t
    assert ex.apply_exposure_t(t, {"ev": 0.0, "temperature_shift": 0.0,
                                   "tint_shift": 0.0}) is t
    assert torch.equal(t, before)
    # 短路路径与算式路径必须给出同样的数
    ran = ex.exposure_t(t, 0.0, 0.0, 0.0)
    assert torch.equal(ran, t)


def test_apply_helper_passes_through_only_when_all_three_neutral():
    torch = pytest.importorskip("torch")
    t = torch.ones(1, 3, 4, 4, dtype=torch.float64) * 0.5
    for p in ({"ev": 0.1}, {"temperature_shift": 100.0}, {"tint_shift": 0.1}):
        assert ex.apply_exposure_t(t, p) is not t, f"{p} 不该走短路"


# ---------------------------------------------------------------- 链上接线（d3b）
# 这一组测的是“接进了管线”，不是“模块自己对”。只有模块用例的话，链里没插进去
# 也能全绿——那正是 DoD-3 “假滑块”会出现的位置。


def _pipeline():
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import PreviewPipeline
    rng = np.random.default_rng(7)
    img = (rng.random((40, 60, 3)) * 200 + 20).astype(np.uint8)
    pipe = PreviewPipeline("cpu", 60, 40)
    pipe.load_rgb_u8(img)
    return pipe, img


def test_pipeline_neutral_is_byte_identical_to_unlit():
    """链上未点火必须逐字节相同（容差 0，ADR-0003 的 identity 口径就在这里）。"""
    p1, img = _pipeline()
    p2, _ = _pipeline()
    st = p2.set_exposure(0.0, 0.0, 0.0)
    assert st["exposure_set"] is False, "全中性却把层报成已点火"
    a = p1.render(0.0, radius=3, eps=1e-3)
    b = p2.render(0.0, radius=3, eps=1e-3)
    assert np.array_equal(p1.read_back(), p2.read_back()), "中性提交改变了画面"


def test_pipeline_positive_ev_actually_brightens_the_frame():
    """反向门：这条必须有。它红了就是“滑块接上了但不作数”——项目禁的那类假控件。"""
    p1, img = _pipeline()
    p2, _ = _pipeline()
    p1.render(0.0, radius=3, eps=1e-3)
    before = p1.read_back()
    st = p2.set_exposure(1.0, 0.0, 0.0)
    assert st["exposure_set"] is True
    p2.render(0.0, radius=3, eps=1e-3)
    after = p2.read_back()
    assert after.mean() > before.mean() + 8, \
        f"+1 EV 几乎没亮（{before.mean():.1f} → {after.mean():.1f}）：要么没接进链，要么被夹死了"
    assert p2.last_exposure_ms > 0.0, "点火了却没计时：分段账单会漏掉这一层"


def test_pipeline_rejects_out_of_range_without_leaving_half_state():
    """被拒的命令整条不留痕：参数越界不能把层置成半截状态。"""
    pipe, _ = _pipeline()
    with pytest.raises(ValueError):
        pipe.set_exposure(99.0, 0.0, 0.0)
    assert pipe.exposure_params == (0.0, 0.0, 0.0), "被拒后残留了部分提交的参数"
    assert pipe.has_exposure() is False
    st = pipe.exposure_state()
    assert st["exposure_limits"] == [5.0, 2000.0, 1.0], "量程没由引擎报出去（UI 会自己拄一份）"


def test_export_spec_carries_exposure_and_matches_preview_bytes():
    """导出口径：同一个 Exposure + 同一份 PreviewPipeline，导出与预览必须同数。

    这条是“所见即所出”的可执行形式。如果导出走的是另一套实现（而不是复用同一个
    管线），它一定会在这里红——那比事后发现颜色不匹配便宜得多。
    """
    pipe_a, img = _pipeline()
    pipe_a.render(0.0, radius=3, eps=1e-3)
    preview = pipe_a.read_back()

    pipe_b, _ = _pipeline()
    pipe_b.set_exposure(1.0, 0.0, 0.0)
    pipe_b.render(0.0, radius=3, eps=1e-3)
    exposed = pipe_b.read_back()
    assert not np.array_equal(preview, exposed)

    from lumaretouch_engine.export import ExportSpec, export_image
    spec = ExportSpec(strength=0.0, radius=3, eps=1e-3, detail_gain=0.0,
                      mid_gain=0.0, broad_gain=0.0, exposure=(1.0, 0.0, 0.0))
    spec.check()
    # tile 下限是引擎自己的口径（256~4096），图幅小于 tile 时它该正常出单块
    pixels, bill = export_image(img, spec, device="cpu", tile=256)
    # read_back 是 (H,W,4)（带 alpha），导出交回的是 (H,W,3)：按导出侧同一口径截断，
    # 而不是拿形状不同当作“数值不一致”放过去
    assert np.array_equal(pixels, exposed[..., :3]), \
        "导出与预览不同数：导出没有复用同一层，或链序不一致"
    # 账单里必须有 exposure 段：漏了它，导出耗时的归属就会把这层的成本摊给别人
    seg = bill["seg_ms"]
    assert "exposure" in seg, f"分段账单没有曝光段：{sorted(seg)}"
