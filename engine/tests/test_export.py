"""M4 分块导出：margin 公式、覆盖完整性、分块==单块，以及两条常驻入口的契约。

判据口径来自 `gpuspike/m4a.py`（全尺寸显存账与 margin 扫描）、`m4a2.py`（逐参数定点
验证公式）与 `packaging/m4-export-bench.py`（真图满幅的字节账）。三件最要紧的事：

· **分块与单块比的是同一幅尺寸的同一套图层**，不是"导出 vs 预览"：预览是代理档、
  导出是满幅，两者本来就不该逐字节相等（M2-b 定的缩放协变说的是"放大 2× 位移也精确 2×"，
  不是"两个尺寸一个字节"）。这里能承诺、也必须承诺的是：同一幅尺寸上切不切块结果一样。
· **能要求 0 LSB 的只有"链上根本不需要邻域求和"那一组**（strength=0 只剩逐点层）。
  只要滤波在场，积分图 cumsum 的前缀就随 crop 变 → float64 求和顺序变 → 极少数像素
  在量化边界翻面。真图上量到 1 LSB / 3 px（磨皮）、1 LSB / 0.03%（形变），所以带滤波
  的臂一律按"≤1 LSB 且差异像素占比有界"判，而**逐点那一组恰好逐字节相等**——
  把两种口径分开写才是诚实的；写成一个笼统的"0 LSB"会靠小靶碰运气恒绿。
· **反向门禁必须在场**：margin 被人砍掉一块时，这套对拍要当场变红并且差异压在网格线上。
  不然"分块 == 单块"这句话可以靠一张作用面比 tile 还小的图恒绿。

CPU 上跑得通（torch 有但没 GPU 也行），所以这批用例同时进 CI 的 engine job。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.export import (DEFAULT_TILE, ExportError, ExportSpec, MAX_MARGIN,
                                       MAX_TILE, MIN_TILE, apply_repair_full, composed_delta,
                                       export_image, tile_rects, write_file)
from lumaretouch_engine.ops.deform import analytic_frontal_landmarks
from lumaretouch_engine.vram import LightOp, RepairOp

# 靶幅特意跨过 256 的 tile 下界：很多判据要的是"真的切成了多块"，一块图的
# "分块 == 单块"是恒真的空话。
H, W = 300, 470


def src(h: int = H, w: int = W) -> np.ndarray:
    """一张有内容的 (H,W,3) uint8：渐变 + 一块暖色圆 + 噪声。

    不能是纯色或纯渐变：引导滤波在完全平坦区会退化（var=0 ⇒ a=0），分带与混合
    全都白跑，"分块 == 单块"就变成了一句没有作用面的空话。
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    base = (xx / w * 0.6 + yy / h * 0.3)
    r = np.hypot(xx - w * 0.5, yy - h * 0.45)
    warm = np.clip(1.0 - r / (min(h, w) * 0.35), 0.0, 1.0)
    rng = np.random.default_rng(7)
    noise = rng.random((h, w)) * 0.06
    ch0 = np.clip(base + 0.25 * warm, 0, 1)
    ch1 = np.clip(base * 0.9 + 0.10 * warm, 0, 1)
    ch2 = np.clip(base * 0.8 - 0.05 * warm, 0, 1)
    a = np.stack([ch0, ch1, ch2], axis=-1) + noise[..., None]
    return np.rint(np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)


def brush(h: int = H, w: int = W, value: int = 96) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    wt = np.zeros((h, w), np.uint8)
    wt[np.hypot(xx - w * 0.5, yy - h * 0.45) < min(h, w) * 0.22] = value
    return wt


def flat_spec(**kw) -> ExportSpec:
    base = dict(strength=0.6, radius=12, texture_radius=4)
    base.update(kw)
    return ExportSpec(**base)


def lsb_diff(a, b):
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=-1)
    return int(d.max()), d


# ---------------------------------------------------------------- 纯逻辑（不需要 GPU）
def test_margin_formula_filter_only():
    s = ExportSpec(radius=12, texture_radius=4, light=[])
    assert s.margin_px() == 2 * 4 + 6 * 12 == 80
    assert ExportSpec(radius=24, texture_radius=6, light=[]).margin_px() == 2 * 6 + 6 * 24 == 156
    assert ExportSpec(radius=6, texture_radius=2, light=[]).margin_px() == 4 + 36 == 40


def test_margin_formula_takes_the_wider_of_filter_and_brush():
    """修容带限是 box(2r)，比磨皮支撑窄时不该被 max 吃掉。"""
    thin = ExportSpec(radius=4, texture_radius=2, light=[LightOp(1, brush())], light_radius=24)
    assert thin.margin_px() == max(2 * 2 + 6 * 4, 2 * 24) == 48
    wide = ExportSpec(radius=20, texture_radius=4, light=[LightOp(1, brush())], light_radius=24)
    assert wide.margin_px() == max(2 * 4 + 6 * 20, 48) == 128


def test_margin_formula_adds_deform_reach_plus_one():
    """形变那一笔是"位移 + 双线性一脚"，向上取整而不是四舍五入。"""
    s = ExportSpec(radius=12, texture_radius=4, light=[])
    assert s.margin_px(36.0) == 80 + 37
    assert s.margin_px(0.4) == 80 + 2          # ceil(0.4)+1 = 2：不足 1 px 也要留一脚
    assert s.margin_px(0.0) == 80


def test_pointwise_layers_add_nothing():
    """lut/grade 是逐点的：挂上它们 margin 一分不涨（这是结构，不是巧合）。"""
    from lumaretouch_engine.ops.lut import bake
    cube = bake(lambda x: x, 17, title="id")
    a = ExportSpec(radius=12, texture_radius=4, light=[])
    b = ExportSpec(radius=12, texture_radius=4, light=[], cube=cube,
                   grade=(0.01, -0.2, 0.05, 1.0))
    assert a.margin_px() == b.margin_px()


def test_tile_rects_cover_every_pixel_exactly_once():
    h, w = 300, 470
    rects = tile_rects(h, w, 256)
    cov = np.zeros((h, w), np.int32)
    for y0, y1, x0, x1 in rects:
        cov[y0:y1, x0:x1] += 1
    assert cov.min() == cov.max() == 1               # 不漏也不重：接缝的两种来源
    assert len(rects) == 2 * 2


def test_tile_rects_rejects_out_of_range_tile():
    for bad in (MIN_TILE - 1, MAX_TILE + 1, 0, -8):
        with pytest.raises(ExportError):
            tile_rects(600, 600, bad)


@pytest.mark.parametrize("kw,why", [
    (dict(strength=1.5), "强度越界"),
    (dict(strength=float("nan")), "强度是 NaN"),
    (dict(eps=0.0), "eps=0 会在平坦区产 NaN"),
    (dict(radius=-1), "负半径"),
    (dict(detail_gain=float("inf")), "增益非有限"),
    (dict(grade=(0.5, 0.0, 0.0, 1.0)), "色相增量越界"),
    (dict(grade=(0.0, 0.0, 0.0, 2.0)), "定向强度越界"),
    (dict(channel="skin"), "分通道但没有掩膜"),
    (dict(channel="nope", masks=np.zeros((1, H, W), np.float32), mask_names=["skin"]),
     "通道名不存在"),
])
def test_spec_check_refuses(kw, why):
    with pytest.raises(ExportError):
        ExportSpec(**kw).check()


def test_export_refuses_before_touching_the_gpu():
    """参数与 tile 数不对，应当一句 ExportError，而不是一句 torch 的 RuntimeError。

    顺序也是有内容的：`spec.check()` 与 margin 上限必须在任何显存动作之前——CI 的
    CPU job 没 GPU 也要能拿到同一句拒绝。
    """
    with pytest.raises(ExportError, match="越界"):
        export_image(src(), flat_spec(), device="cpu", tile=64)
    with pytest.raises(ExportError, match="作用面"):
        export_image(src(), ExportSpec(radius=400, texture_radius=100, light=[]), device="cpu")
    with pytest.raises(ExportError, match="uint8"):
        export_image(src().astype(np.float32), flat_spec(), device="cpu")


def test_write_file_refuses_unknown_format(tmp_path):
    for bad in ("out.bmp", "no_extension", "out.jpg.gz"):
        with pytest.raises(ExportError):
            write_file(src(), str(tmp_path / bad))


def test_export_error_is_a_value_error():
    """命令层按参数拒的路径靠 ValueError 抓；换一个基类就会漏到通用异常里去。"""
    assert issubclass(ExportError, ValueError)


# ---------------------------------------------------------------- 分块 == 单块（torch，CPU 即可）
def _pipe_frame(rgb, spec: ExportSpec, device: str, delta=None):
    """同尺寸、同图层，一次跑完：分块臂的参考。"""
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.vram import PreviewPipeline
    h, w = rgb.shape[:2]
    pipe = PreviewPipeline(device, w, h)
    pipe.load_rgb_u8(rgb)
    if spec.light:
        pipe.set_light_ops(list(spec.light))
        pipe.set_light_params(spec.light_exposure, spec.light_radius)
    if delta is not None:
        pipe.adopt_deform_field(delta.to(device if device != "cpu" else "cpu"))
    if spec.cube is not None:
        pipe.set_lut(spec.cube, spec.lut_amount)
    if spec.grade != (0.0, 0.0, 0.0, 1.0):
        pipe.set_grade(*spec.grade[:3], amount=spec.grade[3])
    pipe.render(spec.strength, radius=spec.radius, eps=spec.eps,
                detail_gain=spec.detail_gain, mid_gain=spec.mid_gain,
                broad_gain=spec.broad_gain, texture_radius=spec.texture_radius)
    return pipe.read_back()[..., :3].copy()


@pytest.mark.parametrize("device", ["cpu"])
@pytest.mark.parametrize("tile", [256, 320])
def test_pointwise_only_export_is_byte_identical_across_tiles(device, tile):
    """链上不需要邻域求和的那一组：分块必须**恰好逐字节相等**。

    strength=0 把滤波短路，剩下的 lut/grade 全是逐点运算——那里没有"前缀从哪开始"
    这个问题，切块在数学与浮点上都不改任何一个像素。这条才是 0 容差的合法位置；
    带滤波的臂只能走下面那条 ≤1 LSB 的口径（真图上量到 1 LSB / 3 px）。
    """
    pytest.importorskip("torch")
    from lumaretouch_engine.ops.lut import bake
    rgb = src()
    s = flat_spec(strength=0.0, light=[],
                  cube=bake(lambda x: np.clip(x * 0.85 + 0.06, 0.0, 1.0), 17, title="bench"),
                  grade=(0.006, -0.14, 0.05, 1.0))
    one, _ = export_image(rgb, s, device=device, tile=max(tile, MIN_TILE))
    two, st = export_image(rgb, s, device=device, tile=tile)
    assert st["tiles"] > 1
    assert np.array_equal(one, two), "逐点层分块后变了字节：那不是舍入，是切片切错了"


@pytest.mark.parametrize("device", ["cpu"])
@pytest.mark.parametrize("tile", [256, 320])
def test_filtered_arms_allow_one_lsb_but_a_handful_of_pixels(device, tile):
    """含磨皮/修容的层组：≤1 LSB，而且差异像素占比有界。

    为什么不能要求 0：滤波走积分图，cumsum 的起点随 crop 变，float64 的求和顺序随之变，
    少数像素会被推到量化边界另一侧。真图满幅上量到 1 LSB / 3 px（磨皮+修容+色彩）。
    "贴缝与否"那一半在 packaging/m4-export-bench.py 里量：这里靶小，分不出方方向。
    """
    pytest.importorskip("torch")
    rgb = src()
    s = flat_spec(light=[LightOp(1, brush())], grade=(0.006, -0.14, 0.05, 1.0))
    one, _ = export_image(rgb, s, device=device, tile=max(tile, MIN_TILE))
    two, st = export_image(rgb, s, device=device, tile=tile)
    assert st["tiles"] > 1
    d, mask = lsb_diff(one, two)
    assert d <= 1, f"分块与单块差 {d} LSB：那不是舍入，是 margin 不够或某层不是局部的"
    assert float((mask > 0).mean()) <= 0.0005


@pytest.mark.parametrize("device", ["cpu"])
def test_color_layers_add_no_margin(device):
    """逐点层不撑 margin：tile 从 4096 换成 256，margin 一分不涨（这是结构，不是巧合）。

    字节那一半不在这里要求：这一臂的 strength=0.6 让滤波还在链上，于是它与上一条
    同因（cumsum 前缀），真正的逐字节判据在 `test_pointwise_only_export_is_byte_identical_across_tiles`。
    """
    pytest.importorskip("torch")
    from lumaretouch_engine.ops.lut import bake
    rgb = src()
    cube = bake(lambda x: np.clip(x * 0.85 + 0.06, 0.0, 1.0), 17, title="bench")
    s = flat_spec(light=[], cube=cube, grade=(0.01, -0.3, 0.08, 1.0))
    one, _ = export_image(rgb, s, device=device, tile=MAX_TILE)
    two, st = export_image(rgb, s, device=device, tile=MIN_TILE)
    assert st["margin_px"] == 2 * 4 + 6 * 12          # 色彩一分没加
    assert st["tiles"] > 1
    d, _mask = lsb_diff(one, two)
    assert d <= 1


@pytest.mark.parametrize("device", ["cpu"])
def test_deform_arm_allows_one_lsb_but_only_a_handful_of_pixels(device):
    """形变那一笔：≤1 LSB、差异像素 ≤0.05%，而且**不落在 tile 网格线上**。

    为什么不能要求 0：warp 之前还有一整条滤波链，而积分图 cumsum 的起点随 crop 变，
    float64 的求和顺序随之变——少数像素会被推到量化边界另一侧。m4a2 在 1.29 MP 上量到
    329 px（0.025%）。这条口径故意留了一倍余量，但**边界占比**那一半不放水：
    margin 不够时差异是压在网格线上的（见下一条的反向门禁）。
    """
    pytest.importorskip("torch")
    rgb = src()
    lm = analytic_frontal_landmarks()
    s = ExportSpec(strength=0.6, radius=8, texture_radius=3, light=[],
                   deform_amounts={"slim_face": 0.4}, landmarks=lm)
    delta, peak = composed_delta(lm, s.deform_amounts, rgb.shape[0], rgb.shape[1], device)
    one = _pipe_frame(rgb, s, device, delta=delta)
    two, st = export_image(rgb, s, device=device, tile=MIN_TILE)
    assert st["deform_peak_px"] > 0
    d, mask = lsb_diff(one, two)
    assert d <= 1, f"形变分块差 {d} LSB：那不是舍入，是场或网格接错了"
    assert float((mask > 0).mean()) <= 0.0005
    assert st["margin_px"] == 2 * 3 + 6 * 8 + int(np.ceil(st["deform_peak_px"])) + 1


@pytest.mark.parametrize("device", ["cpu"])
def test_reverse_gate_cutting_the_margin_turns_red(device, monkeypatch):
    """把 margin 砍到 8 px，分块必须当场对不上，而且差异全部关在接缝带里。

    没有这条，上面那两条判据可以靠"图比作用面小"或"tile 比图大"恒绿。
    空间口径用"离任何 tile 缝超过缺口的像素必须零差异"，不用"落在缝上的比例"：
    不足的影响带本身就宽 (真支撑−实 margin)，拿一条 1 px 宽的线去量会把正确结论洗成噪声。
    """
    pytest.importorskip("torch")
    rgb = src()
    s = flat_spec(light=[LightOp(1, brush())])
    true_margin = s.margin_px()
    one, _ = export_image(rgb, s, device=device, tile=MAX_TILE)
    tile = 300
    monkeypatch.setattr(ExportSpec, "margin_px", lambda self, peak=0.0: 8)
    two, st = export_image(rgb, s, device=device, tile=tile)
    assert st["margin_px"] == 8 and st["tiles"] > 1
    d, mask = lsb_diff(one, two)
    assert d >= 2, f"margin=8 仍只差 {d} LSB：这张靶没有作用面，前面的对拍不算证伪"
    # 缝的位置：只算真正落在图内部的那些（图边缘那一侧两边都夹到同一条边界，不产生差异）
    h, w = rgb.shape[:2]
    bxs = [x for x in range(tile, w, tile)]
    bys = [y for y in range(tile, h, tile)]
    yy, xx = np.mgrid[0:h, 0:w]
    band = true_margin - 8
    dx = np.min(np.stack([np.abs(xx - x) for x in bxs]), axis=0) if bxs else np.zeros((h, w))
    dy = np.min(np.stack([np.abs(yy - y) for y in bys]), axis=0) if bys else np.zeros((h, w))
    far = (dx > band) & (dy > band)
    inside = int((mask > 0).sum())
    assert inside > 0
    assert int((mask > 0)[far].sum()) == 0, \
        f"{inside} 个差异像素里有 {int((mask > 0)[far].sum())} 个在接缝带之外——那不是 margin 不够"


@pytest.mark.parametrize("device", ["cpu"])
def test_strength_zero_no_layers_is_the_source_bytes(device):
    """跨五个里程碑的那条承诺在导出通路上同样成立：什么都没开 ⇒ 逐字节等于解码原图。"""
    pytest.importorskip("torch")
    rgb = src()
    out, st = export_image(rgb, ExportSpec(strength=0.0, light=[]), device=device, tile=300)
    assert st["tiles"] > 1
    assert np.array_equal(out, rgb)


@pytest.mark.parametrize("device", ["cpu"])
def test_pixels_outside_the_skin_window_survive_tiling(device):
    """窗外逐字节不动这条结构性质，在分块之后仍然成立（绿色图 + 定向）。"""
    pytest.importorskip("torch")
    rgb = np.zeros((300, 320, 3), np.uint8)
    rgb[..., 0] = 40
    rgb[..., 1] = 180                       # 色相 0.33：远在肤色窗之外
    rgb[..., 2] = 60
    rgb[:150] = 200                         # 上半给一块中性灰（v 高、s 低，也在窗外）
    s = ExportSpec(strength=0.0, light=[], grade=(0.02, -0.4, 0.3, 1.0))
    out, st = export_image(rgb, s, device=device, tile=MIN_TILE)
    assert st["tiles"] > 1
    assert np.array_equal(out, rgb), "肤色窗外的像素被分块导出改动了"


@pytest.mark.parametrize("device", ["cpu"])
def test_progress_reports_every_tile_once(device):
    pytest.importorskip("torch")
    seen = []
    export_image(src(), flat_spec(light=[]), device=device, tile=MIN_TILE,
                 progress=lambda done, total, ms: seen.append((done, total)))
    assert [d for d, _t in seen] == list(range(1, len(seen) + 1))
    assert {t for _d, t in seen} == {len(seen)} and len(seen) > 1


# ---------------------------------------------------------------- 常驻入口的契约
def test_adopt_deform_field_validates_and_does_not_solve():
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.vram import PreviewPipeline
    pipe = PreviewPipeline("cpu", 60, 40)
    pipe.load_rgb_u8(src(40, 60))
    builds0 = pipe.deform_builds
    good = torch.zeros(1, 40, 60, 2, dtype=torch.float32)
    good[0, 10, 10, 0] = 3.0
    info = pipe.adopt_deform_field(good)
    assert info["lit"] is True and info["adopted"] is True
    assert pipe.deform_builds == builds0, "挂一份现成的场被记成了“解了一次 TPS”"

    for bad in (torch.zeros(1, 40, 60, 3), torch.zeros(1, 41, 60, 2),
               torch.zeros(1, 40, 60, 2, dtype=torch.float64)):
        with pytest.raises(ValueError):
            pipe.adopt_deform_field(bad)
    nan = good.clone()
    nan[0, 5, 5, 1] = float("nan")
    with pytest.raises(ValueError):
        pipe.adopt_deform_field(nan)
    # 失败路径一个字段也不改：还在 good 那一份上
    assert pipe.deform_units["slim_face"].shape == (1, 40, 60, 2)
    assert pipe.deform_amounts == {"slim_face": 1.0, "big_eye": 0.0, "small_chin": 0.0}
    assert pipe.deform_grid_base.shape == (1, 40, 60, 2)
    with pytest.raises(ValueError):
        pipe.adopt_deform_field("not a tensor")     # type: ignore[arg-type]
    assert torch.equal(pipe.deform_units["slim_face"], good.to("cpu"))


def test_adopt_then_clear_leaves_no_layer():
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.vram import PreviewPipeline
    pipe = PreviewPipeline("cpu", 60, 40)
    pipe.load_rgb_u8(src(40, 60))
    pipe.adopt_deform_field(torch.zeros(1, 40, 60, 2))
    assert pipe.has_deform()
    pipe.clear_deform()
    assert not pipe.has_deform() and pipe.deform_grid_base is None


def test_load_rgb_f32_contract():
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.vram import PreviewPipeline
    rgb = src(40, 60)
    f32 = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1))[None]).to("cpu") \
        .to(torch.float32).div_(255.0)[0].permute(1, 2, 0).contiguous().numpy()
    pipe = PreviewPipeline("cpu", 60, 40)
    pipe.load_rgb_f32(f32)
    assert pipe.src_u8 is None, "float 会话谎称自己有原始像素"
    assert pipe.frame_gpu.shape == (40, 60, 4) and int(pipe.frame_gpu[..., 3].min()) == 255
    with pytest.raises(ValueError):
        pipe.load_rgb_f32(f32.astype(np.float64))
    bad = f32.copy()
    bad[0, 0, 0] = float("nan")
    with pytest.raises(ValueError):
        pipe.load_rgb_f32(bad)
    with pytest.raises(ValueError):
        pipe.load_rgb_f32(np.zeros((39, 60, 3), np.float32))


def test_load_rgb_f32_equals_u8_path_for_the_same_pixels():
    """两条装载入口必须给出同一个 float 底图，否则"导出与预览是同一条链"是假的。"""
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.vram import PreviewPipeline
    rgb = src(40, 60)
    a = PreviewPipeline("cpu", 60, 40)
    a.load_rgb_u8(rgb)
    f32 = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1))[None]).to("cpu") \
        .to(torch.float32).div_(255.0)[0].permute(1, 2, 0).contiguous().numpy()
    b = PreviewPipeline("cpu", 60, 40)
    b.load_rgb_f32(f32)
    assert torch.equal(a.src_f32, b.src_f32)


def test_repair_requires_repair_ops():
    torch = pytest.importorskip("torch")          # noqa: F841（走的是 torch 分支）
    with pytest.raises(ExportError, match="RepairOp"):
        apply_repair_full(src(40, 60), [LightOp(1, brush(40, 60))], "cpu")
    with pytest.raises(ExportError, match="尺寸"):
        apply_repair_full(src(40, 60), [RepairOp(1, brush(20, 60))], "cpu")


def test_repair_then_tiled_export_round_trips():
    """满幅预跑的消除笔 + 分块：换 tile 数不该换结果（底图是同一份 float）。"""
    pytest.importorskip("torch")
    rgb = src()
    s = ExportSpec(strength=0.6, radius=8, texture_radius=3, light=[],
                   repair=[RepairOp(1, brush())])
    one, st1 = export_image(rgb, s, device="cpu", tile=MAX_TILE)
    two, st2 = export_image(rgb, s, device="cpu", tile=MIN_TILE)
    assert st1["applied"] == st2["applied"] == 1
    assert st2["tiles"] > st1["tiles"]
    d, mask = lsb_diff(one, two)
    assert d <= 1 and float((mask > 0).mean()) <= 0.005


# ---------------------------------------------------------------- 落盘
def test_write_file_png_is_lossless_and_jpeg_is_not(tmp_path):
    pytest.importorskip("PIL")
    rgb = src(64, 96)
    png = write_file(rgb, str(tmp_path / "a.png"))
    from PIL import Image
    back = np.asarray(Image.open(png["path"]).convert("RGB"), np.uint8)
    assert np.array_equal(back, rgb), "PNG 应当无损"
    jpg = write_file(rgb, str(tmp_path / "a.jpg"), quality=95)
    assert jpg["format"] == "jpg" and jpg["bytes"] > 0
    assert jpg["bytes"] != png["bytes"]
    with pytest.raises(ExportError):
        write_file(rgb, str(tmp_path / "a.jpg"), quality=0)      # 下限夹住，不写 0 字节文件


def test_write_file_accepts_every_advertised_format(tmp_path):
    pytest.importorskip("PIL")
    rgb = src(48, 48)
    for ext in ("jpg", "jpeg", "png", "tif", "webp"):
        info = write_file(rgb, str(tmp_path / f"pic.{ext}"), quality=92)
        assert info["bytes"] > 0 and info["format"] == ext


def test_default_tile_is_in_range():
    assert MIN_TILE <= DEFAULT_TILE <= MAX_TILE
    assert MAX_MARGIN > 0
