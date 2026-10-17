"""M2-a2 仿中性灰修容：算子语义 + 常驻层接入。

判据不是许愿值，全部来自 gpuspike/m2db2.py 在真图（雀斑 + 树叶碎光影）上的实测口径。
这一节最要紧的是那几条**反向门禁**：乘性曝光很容易写成"看着像修容、其实是拿笔刷一块色"，
只有"错实现必须让某条断言变红"才能把这种漂移拦住。
"""

from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops.guided import _box_np
from lumaretouch_engine.ops.light import (DB_EXPOSURE_LIMIT, DEFAULT_DB_EXPOSURE,
                                          DEFAULT_DB_RADIUS, _lin_np, _slin_np,
                                          dodge_burn_np, dodge_burn_t)
from lumaretouch_engine.quant import quantize_np

H, W = 96, 128
LIN_EPS = 1e-6


def chw(a: np.ndarray) -> np.ndarray:
    """(H,W) 或 (H,W,C) → (1,C,H,W)。"""
    if a.ndim == 2:
        return np.ascontiguousarray(a[None, None])
    return np.ascontiguousarray(a.transpose(2, 0, 1))[None]


def skin() -> np.ndarray:
    """一张有结构、有纹理、有低频光影的“皮肤”，(H,W,3) uint8。

    不能拿纯噪声当靶：噪声没有低频，修容的“只动光影”这条就无从判起。
    seed 必须在函数内部：用模块级 RNG 的话每调一次图就变了，
    “造图”与“比对原图”两处各调一次就会拿到两张不同的脸。
    """
    rng = np.random.default_rng(20261016)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    base = 0.55 + 0.18 * (xx / W) + 0.10 * np.sin(2 * np.pi * yy / (H * 0.6))
    g = np.clip(base + rng.normal(0.0, 0.02, size=(H, W)), 0.0, 1.0)
    return quantize_np(g)[..., None].repeat(3, axis=2)


def disc(h, w, cy, cx, rad, value=1.0) -> np.ndarray:
    """硬边圆盘笔刷——产品真实输入的形状（mask_from_rle 出来的就是硬边 0/1）。"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    m = ((yy - h * cy) ** 2 + (xx - w * cx) ** 2) <= (w * rad) ** 2
    f = np.zeros((h, w))
    f[m] = value
    return f


def lin(a):
    """分析用的线性光换算（不是产品件，只给判据当基准）。

    与产品同一对函数的往返恒等另有专门一条测，不能拿自抄的一份去测自己。
    """
    a = np.clip(np.asarray(a, dtype=np.float64), 0.0, 1.0)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def img64():
    return skin().astype(np.float64) / 255.0


# ============================================================ 算子：恒等与短路
def test_empty_field_is_byte_exact_identity():
    """空场必须一个算子都不跑、逐字节回原图。

    不短路的话 `srgb(linear(x))` 的往返会在格点附近抖级——"没画修容 ⇒ 上屏等于解码
    原图"这条承诺就会被一个纯数值伪证打破。
    """
    x = chw(skin().astype(np.float32) / 255.0)
    z = np.zeros((1, 1, H, W), dtype=np.float32)
    out = dodge_burn_np(x, z, exposure=DEFAULT_DB_EXPOSURE, radius=DEFAULT_DB_RADIUS)
    assert np.array_equal(quantize_np(out[0].transpose(1, 2, 0)), skin())


def test_zero_exposure_is_byte_exact_identity():
    x = chw(skin().astype(np.float32) / 255.0)
    f = chw(disc(H, W, 0.5, 0.4, 0.2))
    out = dodge_burn_np(x, f, exposure=0.0, radius=DEFAULT_DB_RADIUS)
    assert np.array_equal(quantize_np(out[0].transpose(1, 2, 0)), skin())


def test_gamma_roundtrip_is_identity_on_uint8_lattice():
    """往返恒等是"短路之外也不该出错"的兜底：量化用四舍五入后它才成立。

    这条同时是给 M3 曲线/LUT 定的地基——那两边会复用同一对 _lin_np/_slin_np，
    往返不恒等的 gamma 约定不能拿来当产品色管。
    """
    v = np.arange(256, dtype=np.uint8)
    # 测的是产品那一对函数，不是测试自己抄的副本
    assert np.array_equal(quantize_np(_slin_np(_lin_np(v / 255.0))), v)


# ================================================= 算子：光影按档数精确移动
def test_exposure_moves_linear_light_by_exactly_that_many_stops():
    """逐像素线性光比值应当精确等于 2^(exposure·带限场)。

    只在"场有作用 + 原值不近黑 + 结果没被夹到满"的像素上比：把被夹的像素算进来，
    就是拿 mask 的选择性偏差冒充算法误差（探针第一版就是这么把 0.2% 看成 3.7% 的）。
    """
    x = chw(skin().astype(np.float32) / 255.0)
    f = chw(disc(H, W, 0.5, 0.4, 0.2))
    x64 = img64()
    for e in (0.3, 0.6, 1.0, -0.6):
        out = dodge_burn_np(x, field=f, exposure=e, radius=DEFAULT_DB_RADIUS)
        arr = out[0].transpose(1, 2, 0).astype(np.float64)
        ws = _box_np(f, DEFAULT_DB_RADIUS)[0, 0]
        want = np.power(2.0, e * ws)
        Li, Lo = lin(x64), lin(arr)
        m = (np.abs(ws) > 0.05)[..., None] & (Li > 1e-3) & (Lo < 1.0 - 1e-6)
        assert m.sum() > 0.05 * H * W * 3, "样本太少，这条判据是空的"
        got = Lo[m] / Li[m]
        med = float(np.median(got / np.repeat(want[..., None], 3, axis=2)[m]))
        assert abs(med - 1.0) < 1e-5, f"e={e} 时档数偏了 {med:.6f}，不是精确乘曝光"


def test_srgb_domain_multiply_would_fail_this_gate():
    """反向门禁：把同一个乘子直接作用在 sRGB 编码值上，必须被上面的判据抓住。

    "在线性光下做"不是行话：编码值上乘 2^0.6 实际只提了不到 0.6 档，而且**提几档
    取决于底色**——暗部几乎不动、亮部过冲。这条测试证明上一条不是恒真的。
    """
    x64 = img64()
    f = disc(H, W, 0.5, 0.4, 0.2)
    ws = _box_np(chw(f), DEFAULT_DB_RADIUS)[0, 0]
    want = np.power(2.0, 0.6 * ws)
    wr = np.repeat(want[..., None], 3, axis=2)
    naive = np.clip(x64 * wr, 0.0, 1.0)
    Li, Lo = lin(x64), lin(naive)
    m = (wr > 1.05) & (Li > 3e-4) & (Lo < 1.0 - 1e-6) & (Li < 0.90)
    drift = np.log2(Lo[m] / Li[m]) - np.log2(wr[m])
    assert float(np.percentile(np.abs(drift), 90)) > 0.05, \
        "sRGB 域乘的档数误差没测出来——那'线性光'这条判据就是空的"


# ============================================== 算子：笔触必须被带限抹平
def test_brush_edge_is_bandlimited_but_center_still_works():
    """中性灰的立身之本：边缘看不见、盘心照样到位。

    r=0（不带限）时笔触硬边直接印到图上，那就是"拿笔刷一块色"。这条判据同时
    要求盘心改动不缩水——只压边缘不压效果，两者都得满足。
    """
    x = chw(skin().astype(np.float32) / 255.0)
    f = disc(H, W, 0.5, 0.4, 0.2)
    fc = chw(f)
    ref = quantize_np(x[0].transpose(1, 2, 0)).astype(np.int32)

    def jumps(radius):
        out = dodge_burn_np(x, field=fc, exposure=0.6, radius=radius)
        d = quantize_np(out[0].transpose(1, 2, 0)).astype(np.int32) - ref
        row = d[int(H * 0.5), :, 0]
        edge = int(np.abs(np.diff(row)).max())
        center = int(np.abs(d[int(H * 0.5), int(W * 0.4)]).max())
        return edge, center

    edge_hard, center_hard = jumps(0)
    edge_ok, center_ok = jumps(DEFAULT_DB_RADIUS)
    # 不带限时笔触边界上一步就是几十分度（硬边直接印到图上）；带限后同一位置
    # 的跳变必须降一个数量级。拿“边缘 vs 盘心”比不行：r=0 时两者本来就同量级。
    assert edge_hard > 3 * edge_ok, \
        f"带限没压住笔触边缘：r=0 是 {edge_hard} LSB，r={DEFAULT_DB_RADIUS} 仍有 {edge_ok} LSB"
    assert edge_ok <= 1.5 * center_ok, \
        f"r={DEFAULT_DB_RADIUS} 边缘跳变 {edge_ok} 仍是盘心 {center_ok} 的 {edge_ok / max(center_ok, 1):.1f} 倍"
    assert center_ok >= 0.6 * center_hard, "带限把盘心效果也一起削没了"


# ==================================================== 算子：多笔叠加的产品语义
def test_strokes_sum_linearly_and_saturate():
    """三条语义一次钉死：抵消、线性累加、饱和。

    为什么不是逐笔应用 dodge_burn：那样 gain 会指数乘起来，三笔 0.6 档就是 3.5 倍，
    脸直接烧穿；而且"拖强度滑块时效果随笔数漂"。场累加把上限钉在 exposure 上。
    """
    x = chw(skin().astype(np.float32) / 255.0)
    base = skin()
    w = chw(disc(H, W, 0.5, 0.4, 0.2))
    half = chw(0.5 * disc(H, W, 0.5, 0.4, 0.2))

    def bytes_of(field, e=0.6):
        return quantize_np(dodge_burn_np(x, field=field, exposure=e,
                                         radius=DEFAULT_DB_RADIUS)[0].transpose(1, 2, 0))

    assert np.array_equal(bytes_of(w - w), base), "一正一负没回到原图：场不是线性累加"
    assert np.array_equal(bytes_of(w - half), bytes_of(half)), "(+1)+(-0.5) 与单支 (+0.5) 不同"
    assert np.array_equal(bytes_of(np.clip(w + w, -1.0, 1.0)), bytes_of(w)), \
        "同向两笔超出了一笔的效果：档数上限没钉在 exposure 上"


# ========================================================== 算子：参数与形状守卫
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"),
                                 DB_EXPOSURE_LIMIT + 0.5, -(DB_EXPOSURE_LIMIT + 0.5)])
def test_illegal_exposure_is_rejected(bad):
    x = chw(skin().astype(np.float32) / 255.0)
    f = chw(disc(H, W, 0.5, 0.4, 0.2))
    with pytest.raises(ValueError):
        dodge_burn_np(x, field=f, exposure=bad, radius=DEFAULT_DB_RADIUS)


def test_illegal_radius_is_rejected():
    x = chw(skin().astype(np.float32) / 255.0)
    f = chw(disc(H, W, 0.5, 0.4, 0.2))
    with pytest.raises(ValueError):
        dodge_burn_np(x, field=f, exposure=0.6, radius=-1)


def test_field_shape_must_match_image_not_be_broadcast():
    """探针直接撞出来的真缺陷：(1,1,1,W) 的场会被 numpy/torch 静默广播成整幅。

    "在眉毛上扫了一下"变成"全图提亮半档"——语义完全错，一个异常也不抛。尺寸差 1
    才会报错，差一整维反而合法，所以只能显式守卫。
    """
    x = chw(skin().astype(np.float32) / 255.0)
    for bad in (np.zeros((1, 1, 1, W)), np.zeros((1, 1, H - 1, W)), np.zeros((1, 1, H, W + 1))):
        with pytest.raises(ValueError):
            dodge_burn_np(x, field=bad, exposure=0.6, radius=DEFAULT_DB_RADIUS)


def test_none_field_is_rejected_not_silently_ignored():
    """None 当"没画过"看，会把调用方的坐标 bug 静默吞成一个"看起来正常"的帧。"""
    x = chw(skin().astype(np.float32) / 255.0)
    with pytest.raises(ValueError):
        dodge_burn_np(x, field=None, exposure=0.6, radius=DEFAULT_DB_RADIUS)


def test_nan_field_produces_non_finite_output_the_layer_will_refuse():
    """算子本身不为 NaN 场兜底（场由引擎从 uint8 构造，天然有限），但产出必须可判。

    这里要的是"非有限值确实出现在输出里"这个事实——常驻层靠它决定不写缓存。
    """
    x = chw(skin().astype(np.float32) / 255.0)
    bad = np.full((1, 1, H, W), np.nan)
    out = dodge_burn_np(x, field=bad, exposure=0.6, radius=DEFAULT_DB_RADIUS)
    assert not np.isfinite(out).all()


# ================================================================== GPU 侧
def test_torch_matches_numpy_without_systematic_offset():
    """验收口径是**均值偏移**，不是"最大 1 LSB"。

    后者正是让 −0.686 LSB 那个产品级 bug 溜过去的口径：68.6% 像素同方向差 1 级，
    最大值仍然只有 1 LSB，看上去完全合规。噪声的均值是 0，有方向才是病。
    """
    torch = pytest.importorskip("torch")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    rgb = skin()
    x32 = chw(rgb.astype(np.float32) / 255.0)
    f = chw(disc(H, W, 0.5, 0.4, 0.2))
    xt = torch.from_numpy(np.ascontiguousarray(x32)).to(dev)
    ft = torch.from_numpy(np.ascontiguousarray(f.astype(np.float32))).to(dev)
    for e, r in ((0.6, 24), (1.2, 24), (-0.6, 12), (0.3, 48), (1.5, 8)):
        g = dodge_burn_t(xt, ft, exposure=e, radius=r)[0].cpu().numpy().transpose(1, 2, 0)
        c = dodge_burn_np(x32, field=f, exposure=e, radius=r)[0].transpose(1, 2, 0)
        d = quantize_np(g).astype(np.int32) - quantize_np(c).astype(np.int32)
        assert int(np.abs(d).max()) <= 1, f"e={e} r={r} 差到 {d.max()} LSB"
        assert abs(float(d.mean())) <= 0.02, f"e={e} r={r} 有 {d.mean():+.4f} LSB 系统偏移"
        assert float((d != 0).mean()) < 0.001, f"e={e} r={r} 有 {(d != 0).mean():.2%} 像素在差"


def test_torch_empty_field_is_byte_exact_identity():
    torch = pytest.importorskip("torch")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    rgb = skin()
    x32 = chw(rgb.astype(np.float32) / 255.0)
    xt = torch.from_numpy(np.ascontiguousarray(x32)).to(dev)
    zt = torch.zeros((1, 1, H, W), device=dev)
    out = dodge_burn_t(xt, zt, exposure=0.6, radius=24)[0].cpu().numpy().transpose(1, 2, 0)
    assert np.array_equal(quantize_np(out), rgb)


def test_module_imports_without_torch():
    """CI 的 engine job 只装 numpy：ops.light 与 quant 都得能被 import。"""
    import subprocess
    import sys

    code = ("import sys; sys.modules['torch']=None;"
            "import importlib;"
            "m=importlib.import_module('lumaretouch_engine.ops.light');"
            "q=importlib.import_module('lumaretouch_engine.quant');"
            "print(m.torch is None, q.torch is None)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "True True" in r.stdout


# ================================================ 常驻层：修容作为独立调整层
# 这一节量的是"接进产品通路之后还成不成立"。算子对不代表层对：层要管缓存键、
# 作废时机、重放与显存账单，而那几处正是 M1-3c / M1-4 各栽过一次的地方。
@pytest.fixture()
def layer():
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline

    rgb = skin()
    return make_pipeline("cpu", W, H, rgb), rgb


def _stroke(cy=0.5, cx=0.4, rad=0.2, sign=1, peak=255):
    from lumaretouch_engine.vram import LightOp

    w = (disc(H, W, cy, cx, rad) * (peak / 255.0))
    return LightOp(op_id=1, weight=quantize_np(w), sign=sign)


def test_no_light_layer_is_byte_identical_to_plain_mix(layer):
    """没画修容时，接了层的通路必须与"只有磨皮"时逐字节相同。

    这是那条承诺的落地形式：层不能因为"挂了但空着"就改变任何一个字节。
    """
    pipe, rgb = layer
    pipe.render(0.55)
    with_layer = pipe.read_back()[..., :3].copy()
    plain = (1.0 - 0.55) * pipe.base() + 0.55 * pipe.retouched
    pipe.pack(plain)
    assert np.array_equal(with_layer, pipe.read_back()[..., :3])


def test_dragging_strength_never_recomputes_the_light_layer(layer):
    """拖 strength 时两份 db 结果都必须命中常驻——这是 M1-3c 零推理的延伸。"""
    pipe, _rgb = layer
    pipe.add_light(_stroke(sign=1))
    pipe.add_light(_stroke(cy=0.3, sign=-1))
    pipe.retouch(0.2)
    assert pipe.last_light_ms > 0.0, "首次没真算，后面的「不重算」就没有对照"
    for s in (0.25, 0.4, 0.55, 0.7, 0.95):
        pipe.retouch(s)
        assert pipe.last_light_ms == 0.0, f"strength={s} 这一帧重跑了 db，热路径被拖回重算"


def test_band_gain_sliders_reuse_the_light_field_but_reapply_the_layer(layer):
    """拖磨皮的带增益：分带命中、成品重算、db(成品) 也必须跟着重算一次。

    第三条是 M2-a2 新出现的耦合——成品变了，盖在它上面的修容结果就是旧的。
    不重算会拿到上一组成品的 db 结果，字节对拍当场要红。
    """
    pipe, _rgb = layer
    pipe.add_light(_stroke())
    pipe.retouch(0.5, mid_gain=0.4)
    pipe.retouch(0.5, mid_gain=0.9)
    assert pipe.last_bands_ms == 0.0, "只改增益却重跑了分带"
    assert pipe.last_light_ms > 0.0, "成品变了而 db(成品) 没跟着重算，拿到的是旧成品的结果"
    pipe.retouch(0.6, mid_gain=0.9)
    assert pipe.last_light_ms == 0.0


def test_changing_light_params_recomputes_once_then_caches(layer):
    pipe, _rgb = layer
    pipe.add_light(_stroke())
    pipe.retouch(0.5)
    pipe.set_light_params(1.2, DEFAULT_DB_RADIUS)
    pipe.retouch(0.5)
    assert pipe.last_light_ms > 0.0, "改了曝光却没重算，帧里还是旧档数"
    pipe.retouch(0.5)
    assert pipe.last_light_ms == 0.0


def test_undo_and_redo_return_the_same_bytes(layer):
    """非破坏重放：撤销再重做必须回到逐字节相同的那一帧。"""
    pipe, _rgb = layer
    pipe.add_light(_stroke(sign=1))
    pipe.add_light(_stroke(cy=0.3, sign=-1))
    pipe.render(0.5)
    two = pipe.read_back()[..., :3].copy()
    pipe.undo_light()
    pipe.render(0.5)
    one = pipe.read_back()[..., :3].copy()
    pipe.redo_light()
    pipe.render(0.5)
    assert np.array_equal(pipe.read_back()[..., :3], two)
    assert not np.array_equal(one, two), "两笔与一笔一模一样，笔迹没进图层"
    info = pipe.clear_light()
    assert info["ops"] == 0 and not info["lit"]
    pipe.render(0.0)
    assert np.array_equal(pipe.read_back()[..., :3], skin()), "清层之后没回到解码原图"


def test_non_finite_result_is_not_written_into_the_cache(layer):
    """缓存里的 NaN 会长期作恶：`(1-0)*NaN` 仍是 NaN，strength=0 恒等当场失效。"""
    import torch

    from lumaretouch_engine.vram import LightOp

    pipe, _rgb = layer
    pipe.add_light(LightOp(op_id=1, weight=quantize_np(disc(H, W, 0.5, 0.4, 0.2)), sign=1))
    pipe.light_field_gpu = torch.full((1, 1, H, W), float("nan"))
    pipe.light_version += 1
    with pytest.raises(ValueError):
        pipe.lighten_source()
    assert pipe.light_src is None, "非有限值已经写进常驻缓存了"


def test_illegal_stroke_is_rejected_without_leaving_a_half_layer(layer):
    """被拒的一笔必须整条不留痕：图层数量、版本号、缓存都不能动。"""
    import numpy as _np

    from lumaretouch_engine.vram import LightOp

    pipe, _rgb = layer
    pipe.add_light(_stroke())
    before = (len(pipe.light_ops), pipe.light_version, pipe.light_field_gpu is not None)
    bad = LightOp(op_id=2, weight=_np.zeros((H + 3, W), dtype=_np.uint8), sign=1)
    with pytest.raises(ValueError):
        pipe.add_light(bad)
    assert (len(pipe.light_ops), pipe.light_version, pipe.light_field_gpu is not None) == before
    bad2 = LightOp(op_id=2, weight=_np.ones((H, W), dtype=_np.uint8) * 200, sign=3)
    with pytest.raises(ValueError):
        pipe.add_light(bad2)
    assert len(pipe.light_ops) == before[0]


def test_replay_rebuilds_the_same_layer_on_a_new_session(layer):
    """换设备/重建会话靠重放：只存输入，不存结果。"""
    pipe, rgb = layer
    ops = [_stroke(sign=1), _stroke(cy=0.3, sign=-1)]
    for i, op in enumerate(ops):
        pipe.add_light(type(op)(op_id=i + 1, weight=op.weight, sign=op.sign))
    pipe.render(0.4)
    want = pipe.read_back()[..., :3].copy()

    from lumaretouch_engine.vram import make_pipeline

    fresh = make_pipeline("cpu", W, H, rgb)
    fresh.set_light_params(DEFAULT_DB_EXPOSURE, DEFAULT_DB_RADIUS)
    fresh.set_light_ops(ops)
    fresh.render(0.4)
    assert np.array_equal(fresh.read_back()[..., :3], want)


def test_light_resident_bytes_counts_everything_it_should(layer):
    """零推理换来的显存必须能看见，不能只报快了多少。"""
    pipe, _rgb = layer
    assert pipe.light_resident_bytes() == 0
    pipe.add_light(_stroke())
    with_field = pipe.light_resident_bytes()
    assert with_field > 0
    pipe.retouch(0.5)
    with_both = pipe.light_resident_bytes()
    # 场 + 两份 db 结果 + CPU 侧画笔：一份 db 是 (1,3,H,W) float32
    one = 3 * H * W * 4
    assert with_both >= with_field + 2 * one, \
        f"两份 db 常驻只报了 {with_both - with_field} 字节，少于一份 {one}"


def test_load_new_image_drops_the_previous_strokes(layer):
    """换图必须清层：上一张脸的笔迹坐标与新图毫无关系。"""
    pipe, _rgb = layer
    pipe.add_light(_stroke())
    pipe.retouch(0.5)
    pipe.load_rgb_u8(skin()[::-1].copy())
    assert pipe.light_ops == [] and pipe.light_field_gpu is None
    assert pipe.light_resident_bytes() == 0
    pipe.render(0.0)
    assert np.array_equal(pipe.read_back()[..., :3], skin()[::-1].copy())


def test_warm_device_actually_runs_the_light_kernels(monkeypatch):
    """预热里必须真的跑过 db 内核，不是只在注释里写了“已预热”。

    真窗口实测：没有这条预热时，冷进程第一笔修容 light_ms 68.64 ms、后续 3.3 ms——
    那 65 ms 是 sRGB↔linear / 带限 box / pow 这组内核的首次加载。钱付在哪就要在哪钉住：
    拿计数器包住 dodge_burn_t，源码里把预热那一段删掉就会红。
    """
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("没 GPU：预热路径本身就不该跑，测它没意义")
    from lumaretouch_engine import vram

    calls = []
    real = vram.dodge_burn_t

    def spy(img, field, exposure=0.6, radius=24):
        calls.append((float(exposure), int(radius)))
        return real(img, field, exposure=exposure, radius=radius)

    monkeypatch.setattr(vram, "dodge_burn_t", spy)
    ms = vram.warm_device("cuda")
    assert ms > 0.0, f"预热返 0 就等于没预热，但事件会报 engine_warm：{ms}"
    # 两份操作数各跑一次：源图（strength=0 那一半）与磨皮成品（strength=1 那一半）
    assert len(calls) >= 2, f"预热只跑了 {len(calls)} 次 db，修容内核没全加载"
    assert all(e == vram.DEFAULT_DB_EXPOSURE and r == vram.DEFAULT_DB_RADIUS
               for e, r in calls), f"预热用的不是产品默认参数：{calls}"


def test_warm_device_on_cpu_reports_no_warm():
    """没 GPU 时说 0 ms：调用方据此不发 engine_warm，不发一个“预热了 0 ms”的假绿。"""
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import warm_device

    assert warm_device("cpu") == 0.0


def test_zero_field_pixels_are_byte_identical_with_a_live_field():
    """画了修容之后，“场恰好为零”的像素仍必须逐字节不动。

    口径得卡在 **场恰好为零**而不是“我画的圆盘外”：带限场有合法拖尾，圆盘外一段
    距离内 ws ≠ 0（真图代理档实测：三支笔之外仍有 0.30% 像素 ws ≠ 0，|ws| 最大
    0.0087 → 增益 1.0036 → 1 LSB）。上一轮拿圆外当笔外，把一个正确行为测成了缺陷。
    守卫本身是必要的（下一那条测它），但只能拿 ws==0 去量它，否则量的是两件事。
    """
    img = chw(skin().astype(np.float32) / 255.0)
    f = chw(disc(H, W, 0.3, 0.5, 0.06))          # disc 吃的是归一化坐标与半径，不是像素
    for r in (6, 24):
        out = dodge_burn_np(img, f, exposure=0.6, radius=r)
        ws = _box_np(f.astype(np.float64), r)
        zero = ws[0, 0] == 0.0
        assert float(zero.sum()) > 0.3 * H * W, f"r={r} 时场铺满了整幅，这条没在验零增益区"
        a = quantize_np(out)[0].astype(np.int32)
        b = quantize_np(img)[0].astype(np.int32)
        d = np.abs(a - b).max(axis=0)
        assert int(d[zero].max()) == 0, f"r={r}：场为零的地方差了 {int(d[zero].max())} LSB"
        # 拖尾确实存在：不然“卡在圆外”的错口径下次还会让人改代码
        inside = f[0, 0] > 0
        assert int(((~zero) & ~inside).sum()) > 0, f"r={r}：带限场没有拖尾，这条口径退化了"


def test_gpu_round_trip_is_exact_on_all_256_levels():
    """GPU float32 的 sRGB 往返必须在 256 个格点上逐字节恒等。

    这条是上面那条“零增益区不动”在 GPU 上的地基：gain = 2^0 = 1.0 时生产实现
    走的就是 `_slin_t(_lin_t(v))`。CPU 那边 test_light 早就钉了同样的 256 档往返，
    但生产跑的是 float32——不钉这一条，“恒等”就只是 CPU 的性质。
    """
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops.light import _lin_t, _slin_t

    levels = torch.arange(256, dtype=torch.float32) / 255.0
    want = torch.arange(256, dtype=torch.uint8)
    for dev in (["cpu"] if not torch.cuda.is_available() else ["cpu", "cuda"]):
        v = levels.to(dev)[None, :, None, None]
        back = _slin_t(_lin_t(v))
        q = (back.clamp(0.0, 1.0) * 255.0).round().to(torch.uint8)[0, :, 0, 0].cpu()
        assert torch.equal(q, want), \
            f"{dev} 上往返在格点边界抖了：{(q != want).nonzero().flatten().tolist()}"


def test_gpu_zero_field_pixels_are_byte_identical(layer):
    """GPU 生产实现：场为零的像素逐字节等于入参（float32 下也必须成立）。"""
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops.light import dodge_burn_t

    _pipe, rgb = layer
    f = disc(H, W, 0.3, 0.5, 0.06)
    fc = np.ascontiguousarray(f[None, None])
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    src = torch.from_numpy(
        np.ascontiguousarray(rgb.astype(np.float32).transpose(2, 0, 1) / 255.0))[None].to(dev)
    out = dodge_burn_t(src, torch.from_numpy(fc.astype(np.float32)).to(dev), 0.6, 24)
    zero = _box_np(fc.astype(np.float64), 24)[0, 0] == 0.0

    def u8(t):
        return ((t.clamp(0.0, 1.0) * 255.0).round().to(torch.uint8)
                [0].permute(1, 2, 0).cpu().numpy().astype(np.int32))

    d = np.abs(u8(out) - u8(src)).max(axis=2)
    assert int(d[zero].max()) == 0, f"{dev} 上零增益区差了 {int(d[zero].max())} LSB"


def test_zero_gain_guard_is_load_bearing_on_the_torch_path():
    """`_zero_gain_hold` 不是装饰：拿卡在 ×255 的 .5 边界上的操作数，裸往返会翻整级。

    为什么单测要自己造靶：生产通路两个操作数（`img` 与磨皮成品 `retouched`）都是管线
    中间值，不在 256 个格点上；float32 的 sRGB 往返会把它们挪开最后一位，落在 .5
    边界上时 round-half-to-even 就倒向另一边。真图代理档（57 万像素）实测有 0.0045%
    的“场恰好为零”像素被这样重量化（m2-dnb-bench 1e），但 96×128 的随机皮肤上
    一个也没撞上——不造靶这条判据在单测尺寸上是恒真的。
    """
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops.light import _lin_t, _slin_t, dodge_burn_t

    v = (torch.arange(255, dtype=torch.float32) + 0.5) / 255.0
    img = v[None, None, :, None].repeat(1, 3, 1, 1).contiguous()      # (1,3,255,1)
    f = torch.zeros((1, 1, 255, 1))
    f[0, 0, 128, 0] = 1.0                                             # 只有一格有笔
    zero = torch.ones(255, dtype=torch.bool)
    zero[128] = False
    for dev in (["cpu"] if not torch.cuda.is_available() else ["cpu", "cuda"]):
        it, ft = img.to(dev), f.to(dev)
        z = zero.to(dev)
        q0 = (it.clamp(0.0, 1.0) * 255.0).round().to(torch.uint8)

        def flip(t):
            d = ((t.clamp(0.0, 1.0) * 255.0).round().to(torch.uint8)
                 - q0).abs()[0].amax(dim=0)[:, 0]
            return int(d[z].max()), int((d[z] > 0).sum())

        held = flip(dodge_burn_t(it, ft, 0.6, 0))
        naive = flip(_slin_t(_lin_t(it)))
        assert held == (0, 0), f"{dev} 上零增益区仍被重量化：最大 {held[0]} LSB、{held[1]} 个点"
        assert naive[1] > 0, (
            f"{dev} 上裸往返一个点都不翻（{naive}），守卫就成了白写的——"
            "要么靶造得不对，要么实现变了，两种都得重看这条判据")


# ==================================================== 常驻层契约（M2-a2 审查落地）
def _pipe():
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline
    return make_pipeline("cpu", W, H, skin())


def test_set_light_params_returns_exactly_the_commit_key_set():
    """五种 action 共用 light_done 一个事件名：params 那条的键集必须与建层那条一样。

    上一版 set_light_params 只回 {exposure, radius, ops, lit}，painted_px /
    field_peak / light_build_ms / redo_pending 全缺，而 UI 的 LightInfo 把它们声明
    成必存字段 —— 用户拖一下"修容档数"松手，App 读 lastLight.field_peak.toFixed()
    就 TypeError。谎报发生在 JSON 边界上，TS 编译期抓不到，所以这条只能在引擎侧钉。
    """
    p = _pipe()
    committed = p._commit_light([], [])
    params = p.set_light_params(0.8, 12)
    assert set(params) == set(committed), \
        f"两条臂的键集不同：只 params 有 {set(params) - set(committed)}，" \
        f"只建层有 {set(committed) - set(params)}"
    for k in ("painted_px", "field_peak", "light_build_ms", "redo_pending"):
        assert isinstance(params[k], (int, float)), f"{k} 不是数字：{params[k]!r}"
    assert params["exposure"] == 0.8 and params["radius"] == 12, params
    assert params["layer_recomputed"] is False and committed["layer_recomputed"] is True


def test_set_light_params_rejects_non_finite_exposure_before_writing_state():
    """NaN 不许进常驻参数：`exposure != 0.0` 对 NaN 为真，于是"生效"判据当场失真。

    后果不是报错而是每帧在渲染期抛 ValueError、会话卡死而 light_done 永不出现——
    现场与病因隔了两个模块。命令层拦了 NaN，库层不拦就是"只认调用方守规矩"。
    """
    p = _pipe()
    before = (float(p.light_exposure), int(p.light_radius))
    for bad in (float("nan"), float("inf"), -float("inf"), DB_EXPOSURE_LIMIT + 1):
        with pytest.raises(ValueError):
            p.set_light_params(bad, 24)
        with pytest.raises(ValueError):
            p.set_light_params(0.6, -1)
    assert (float(p.light_exposure), int(p.light_radius)) == before, "被拒的参数写进了状态"
    p.light_exposure = float("nan")
    assert p.has_light() is False, "NaN 曝光被判成'生效'：lit 这条自证失效"


def test_light_add_rolls_back_params_when_the_layer_build_fails(monkeypatch):
    """建层抛异常时参数必须一起退回：不许留下"参数新、图层旧、事件没发"。

    上一版只 except ValueError（生产路径上几乎走不到），任何 RuntimeError / OOM 都会
    冒到主循环：self._light 已是新值、db 缓存被丢、一笔没加、light_done 从没发出，
    而宿主侧 status.light 还停在上一条 payload —— 上报里曝光变了而画面按旧曝光渲染。
    这条与 cmd_set_strength 那次花钱换来的教训同形："先全量校验、后一次性提交"
    不是注释，得真的回得去。
    """
    pytest.importorskip("torch")
    from lumaretouch_engine import server as srv

    events = []
    monkeypatch.setattr(srv, "emit", lambda ev: events.append(dict(ev)))
    eng = srv.Engine("t-light-rollback")
    eng.device = "cpu"
    pipe = _pipe()
    eng._vram = pipe
    eng._src_rgb = skin()
    eng._image_loaded = True

    class FakeShm:
        w, h = W, H
    eng.shm = FakeShm()
    before = dict(eng._light)

    def boom(op):
        raise RuntimeError("显存不够")
    monkeypatch.setattr(pipe, "add_light", boom)
    eng.cmd_light({"action": "add", "rle": [[H // 3, W // 3, 8, 255]], "sign": 1,
                   "exposure": 1.5, "radius": 8})
    assert eng._light == before, f"建层失败后引擎侧参数没回滚：{eng._light}"
    assert (float(pipe.light_exposure), int(pipe.light_radius)) == \
        (before["exposure"], before["radius"]), "常驻层的参数也没回滚"
    assert pipe.light_ops == [], "被拒的一笔不许留在图层里"
    assert any(e["event"] == "error" and "回滚" in e["error"] for e in events), events
    assert not any(e["event"] == "light_done" for e in events), "整条拒绝却发了成功事件"


def test_layer_recomputed_and_filter_cached_are_two_different_names():
    """库层的"本层重算了"与 cmd 层的"滤波命中缓存"不许共用一个键名。

    字典字面量后写覆盖先写：`{**info, "cached": ...}` 会把 info 里的 cached 静默吃掉，
    于是其中一个永远送不出来而报表看着仍自洽。bench_done 的 light/deform 已经栽过
    一次（改名 light_state/deform_state），这两条是同一次事故的另两个现场。
    """
    p = _pipe()
    info = p._commit_light([], [])
    assert "layer_recomputed" in info and "cached" not in info, \
        f"库层不许再发 cached 这个泛用名：{sorted(info)}"
    assert "filter_cached" not in info, "滤波那条只属于 cmd 层，别在这里抢名字"
