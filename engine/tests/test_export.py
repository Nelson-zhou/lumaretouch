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
    # 验收用例引用：TASK-005（分块参数不合法当场拒（不静默改小输出尺寸））
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
    # 验收用例引用：RENDER-005（分块与单块：逐点层那组必须恰好逐字节相等（接缝 0 LSB））
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
    # 验收用例引用：RENDER-005（带邻域求和那一组按冻结口径判：≤1 LSB 且差异不落在网格线上）
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


def test_png_compress_level_is_capped_and_reported(tmp_path):
    """quality→PNG 档位的映射：单调、有上限、而且报得出来。

    上限不是风格：真图（3.06 MP）实测 level 6→9 是 804→5469 ms 换 2.67→2.56 MiB，
    而旧映射 `q // 10` 让 quality=95（导出面板的默认）正好落在最费的那一档：
    一百张 PNG 就是九分钟纯编码。这条用例钉住的是"不再默默跌进 7–9"。
    """
    pytest.importorskip("PIL")
    from PIL import Image

    rgb = src(64, 96)
    levels = []
    for q in (10, 30, 60, 95, 100):
        info = write_file(rgb, str(tmp_path / f"p{q}.png"), quality=q)
        assert info["compress_level"] == min(6, q // 10), info
        assert info["compress_level"] <= 6, f"quality={q} 又跌回 7–9 档了"
        levels.append(info["compress_level"])
        assert np.array_equal(np.asarray(Image.open(info["path"]).convert("RGB"), np.uint8),
                              rgb), "改档位不改无损语义：PNG 必须仍能逐字节解回原图"
    assert levels == sorted(levels), f"quality 越高档位反而越低：{levels}"
    jpg = write_file(rgb, str(tmp_path / "x.jpg"), quality=90)
    assert jpg["compress_level"] is None, "非 PNG 格式没这个旋钮，但要键不要缺键"


def test_write_file_accepts_every_advertised_format(tmp_path):
    pytest.importorskip("PIL")
    rgb = src(48, 48)
    for ext in ("jpg", "jpeg", "png", "tif", "webp"):
        info = write_file(rgb, str(tmp_path / f"pic.{ext}"), quality=92)
        assert info["bytes"] > 0 and info["format"] == ext


def test_default_tile_is_in_range():
    assert MIN_TILE <= DEFAULT_TILE <= MAX_TILE
    assert MAX_MARGIN > 0


# ------------------------------------------------------------------ M9-e 16-bit 母档直通
#
# 这一节的判据只认三种说法：逐字节相等、每通道档位数量、低 8 位有没有内容。
# 刻意**不拿 Pillow 当保真判据**：它能打开我们写的 16-bit TIFF，但读回来是 8-bit 的
# mode='RGB'（实测），拿它比就等于拿"被降过样的那份"当尺子——差值恒 0 恰恰说明尺子坏了。
# 保真靠 read_tiff16 那份独立实现与写侧对拍，同时留一条反例（8-bit 左移补零的假 16-bit）
# 证明这几个读数真的会红。

def test_tiff16_roundtrip_is_byte_exact():
    from lumaretouch_engine.export import read_tiff16, write_tiff16
    a = (np.random.default_rng(11).integers(0, 65536, (37, 53, 3))).astype(np.uint16)
    import os
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "a.tif")
    info = write_tiff16(a, p)
    back = read_tiff16(p)
    assert back.shape == a.shape and back.dtype == np.uint16, back.shape
    assert np.array_equal(back, a), "落盘字节与内存里的母档不一致"
    # 头部布局按字段算而不是拍脑袋留一个魔术数：8(签名) + 2(条目数) + 12×条目数
    # + 4(下一 IFD) + 6(BitsPerSample) + ICC 本体。条目数 = 10 个基础 tag（+1 当嵌了 ICC）。
    # 不嵌 ICC 时必须还是原来的 140：那一条旧不变量不能在新参数旁边默默飘移
    assert info["bytes"] == 37 * 53 * 3 * 2 + 140 + 12 + info["icc_bytes"], info["bytes"]
    bare = write_tiff16(a, os.path.join(os.path.dirname(p), "bare.tif"), output_profile="none")
    assert bare["icc_bytes"] == 0 and bare["bytes"] == 37 * 53 * 3 * 2 + 140, bare


def test_tiff16_rejects_non_16bit_input(tmp_path):
    """uint8 不许"升"成 16-bit：左移补零出来的是一张位数对、内容只有 8-bit 的假件。"""
    from lumaretouch_engine.export import ExportError, write_tiff16
    a = np.zeros((8, 8, 3), dtype=np.uint8)
    with pytest.raises(ExportError, match="uint16"):
        write_tiff16(a, str(tmp_path / "x.tif"))


def test_low_bits_detector_catches_padded_fake(tmp_path):
    """反例必须在场：把 8-bit 内容左移补零伪装成 16-bit，读数要认出低 8 位全 0。

    没有这一条，上面那两个"真 16-bit"的用例可以靠一张实际只有 8-bit 内容的图恒绿。
    """
    from lumaretouch_engine.export import read_tiff16, write_tiff16
    real = (np.random.default_rng(5).integers(0, 65536, (16, 16, 3))).astype(np.uint16)
    fake = (real >> 8 << 8).astype(np.uint16)
    write_tiff16(fake, str(tmp_path / "fake.tif"))
    back = read_tiff16(str(tmp_path / "fake.tif"))
    assert int(np.count_nonzero(back & 0xFF)) == 0, "补零件的低 8 位竟然有内容？判据失效"
    write_tiff16(real, str(tmp_path / "real.tif"))
    assert int(np.count_nonzero(read_tiff16(str(tmp_path / "real.tif")) & 0xFF)) > 0


import os as _os
from lumaretouch_engine.ops import libraw as _LR    # noqa: E402

needs_libraw = pytest.mark.skipif(
    not _LR.available(), reason="机器上没有系统 LibRaw（libraw_r.so）：16-bit 母档那一臂不适用")


@needs_libraw
@pytest.mark.skipif(not _os.path.isfile(_LR.PROBE_DNG),
                    reason="缺 raw-probe.dng：重跑 packaging/make-raw-probe.py")
def test_probe_dng_master_is_really_16bit(tmp_path):
    """基线那一臂只出 8-bit：要 16-bit 就必须换后端，且 source 要说得出是谁解的。

    这一条钉的是 M9-e 之前真正的那个问题：load_full(want_bits=16) 会先走自研读侧并把
    uint8 当成结果交回来。所以既要求 dtype，也要求 source / bits 这两个名字同方向。
    """
    from lumaretouch_engine.decode import load_full
    d8 = load_full(_LR.PROBE_DNG)
    assert d8.rgb.dtype == np.uint8 and (d8.raw or {}).get("source") == "self_dng", \
        (d8.rgb.dtype, (d8.raw or {}).get("source"))
    d16 = load_full(_LR.PROBE_DNG, want_bits=16)
    assert d16.rgb.dtype == np.uint16, d16.rgb.dtype
    assert (d16.raw or {}).get("source") == "libraw", d16.raw
    assert (d16.raw or {}).get("bits") == 16, d16.raw
    assert int(d16.rgb.max()) > 255, "16-bit 写法的数据全窓在 8-bit 范围内：白电平没拉开"
    assert (d16.raw or {}).get("used_preview") is False, "16-bit 不能来自内嵌预览"


@needs_libraw
@pytest.mark.skipif(not _os.path.isfile(_LR.PROBE_DNG), reason="缺 raw-probe.dng")
def test_master_16bit_export_is_faithful_and_names_its_source(tmp_path):
    from lumaretouch_engine.export import export_master_16bit
    out = str(tmp_path / "m.tif")
    r = export_master_16bit(_LR.PROBE_DNG, out)
    assert r["bits"] == 16 and r["source"] == "libraw", r
    assert r["readback_max_diff"] == 0, "落盘与内存母档不逐字节相等"
    assert all(x > 256 for x in r["levels_per_channel"]), r["levels_per_channel"]
    assert r["low8_nonzero_px"] > 0, "低 8 位全零：这是补零伪装的假 16-bit"
    # 无压缩：除头部与嵌进去的 ICC 之外全是母档字节。条目数从 10 变 11（多一个 ICCProfile）
    assert r["bytes"] == r["w"] * r["h"] * 3 * 2 + 140 + 12 + r["icc_bytes"], r
    assert r["icc_bytes"] > 0 and r["icc_readback_matches"] is True, \
        "报的 ICC 与 tag 偏移指向的字节不是同一份：这等于没嵌"
    assert r["src_format"] == "DNG", r


def test_master_16bit_refuses_non_raw(tmp_path):
    """没有 16-bit 母档就拒，不降级：交一张 8-bit 内容的 TIFF 却报 bits=16 是骗人。"""
    from lumaretouch_engine.export import export_master_16bit
    src = "engine/tests/fixtures/portrait-1024x1280.jpg"
    if not _os.path.isfile(src):
        src = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                            "tests/fixtures/portrait-1024x1280.jpg")
    if not _os.path.isfile(src):
        pytest.skip("缺 fixture 图")
    with pytest.raises(ValueError, match="16-bit 直通只对相机 RAW 成立"):
        export_master_16bit(src, str(tmp_path / "nope.tif"))


# ------------------------------------------------------------------ P1-2 换底进导出
# 报告里那一条「换底只在预览生效，没进入实际导出」是「所见非所出」里最难看出的一种：
# 前景仍在原位，只是背后的色没变，缩略图上一时看不出。判据必须盯到导出文件的像素，
# 不能只信事件里的 `bg_active=true`。三条单元：参数半截拒、区域像素真换了、
# 分块与整幅在纯逐点链上逐字节同一（否则「换底进导出」只是把预览的错复制到多个 tile）。
@pytest.mark.parametrize("kw, why", [
    (dict(bg_matte=np.zeros((16, 16), np.uint8)), "带 matte 却没带 ref"),
    (dict(bg_ref=(1.0, 0.0, 0.0)), "带 ref 却没 matte"),
    (dict(bg_matte=np.zeros((16, 16, 3), np.uint8), bg_ref=(1.0, 0.0, 0.0)), "matte 非 (H,W)"),
    (dict(bg_matte=np.zeros((16, 16), np.uint8), bg_ref=(0.5, 0.0, 0.0, 0.0)), "ref 不是三分量"),
    (dict(bg_matte=np.zeros((16, 16), np.uint8), bg_ref=(1.5, 0.0, 0.0)), "ref 越界"),
    (dict(bg_matte=np.zeros((16, 16), np.uint8), bg_ref=(float("nan"), 0.0, 0.0)), "ref 非有限"),
])
def test_export_spec_refuses_half_or_bad_background(kw, why):
    """半截或形状/取值不合法的换底参数一律 ExportError，不进入合成写盘。"""
    with pytest.raises(ExportError, match=r"换底|bg_"):
        ExportSpec(**kw).check()


def test_export_applies_background_at_correct_regions():
    """背景区（matte=0）在导出文件里应当真的变成 bg_ref，前景区（matte=255）逐字节保留原片。

    64×64 灰底 + 上半 matte=0 / 下半 matte=255 + 红背景。上半输出必须贴近 (255,0,0)，
    下半输出必须与源片 128 逐字节同一。只看 `bg_ms>0` 是不够的：那一层可能被挂上但没进合成
    链，账单照样能算出来。
    """
    pytest.importorskip("torch")
    s = np.full((64, 64, 3), 128, np.uint8)
    matte = np.zeros((64, 64), np.uint8)
    matte[32:, :] = 255
    spec = ExportSpec(strength=0.0, light=[], radius=4, texture_radius=2,
                      bg_matte=matte, bg_ref=(1.0, 0.0, 0.0))
    out, bill = export_image(s, spec, device="cpu", tile=MAX_TILE)
    top = out[:24].astype(np.int16)
    bot = out[40:].astype(np.int16)
    assert np.abs(top - np.array([255, 0, 0], np.int16)).max() <= 1, \
        f"背景区没被换成红底（上半平均：{top.reshape(-1,3).mean(axis=0)}）"
    assert np.array_equal(bot, np.full(bot.shape, 128, np.int16)), \
        f"前景区被误动（下半平均：{bot.reshape(-1,3).mean(axis=0)}）"
    # bg_ms 要归因到那一层；不进 seg 表说明 apply_background 没被跑到
    assert float(bill["seg_ms"]["bg"]) > 0.0, "账单里 bg 段是 0：这层没真的跑 composite_t"


def test_export_background_tiles_match_full_image():
    """同一份换底参数在 tile=MAX 与 tile=MIN 下逐字节同一（纯逐点链，strength=0）。

    composite_t 是逐点线性光混合，邻域求和不参与；这一条与
    `test_pointwise_only_export_is_byte_identical_across_tiles` 同规，专测「tile 切分时 matte
    与 bg_ref 都逐块传对了」。上一版没有把 matte 分块切给 pipe，就会在这里响：两块之间的
    背景接缝会留下可见的位移。
    """
    pytest.importorskip("torch")
    s = src(200, 300)
    yy, xx = np.mgrid[0:200, 0:300]
    matte = np.where(((xx - 150) ** 2 + (yy - 100) ** 2) < 60 ** 2, 255, 0).astype(np.uint8)
    spec = ExportSpec(strength=0.0, light=[], radius=4, texture_radius=2,
                      bg_matte=matte, bg_ref=(0.0, 1.0, 0.0))
    one, _ = export_image(s, spec, device="cpu", tile=MAX_TILE)
    two, _ = export_image(s, spec, device="cpu", tile=MIN_TILE)
    assert np.array_equal(one, two), \
        (f"分块与整幅不一致（最大差异 "
         f"{int(np.abs(one.astype(np.int16)-two.astype(np.int16)).max())}）：换底遮罩 tile 局部坐标没对好")
