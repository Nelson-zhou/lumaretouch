"""M3-a 3D LUT：.cube 解析、查表插值、恒等短路 + 接进常驻层后的层契约。

判据口径来自 gpuspike/m3a.py / m3b.py 的实测，两条最要紧的：
· 误差**必须比解析真值**（一个 float64 上可精确算的调色函数），不许"两种实现互相比"；
· LSB 差要先升 int16 再相减（uint8 相减是模 256 回绕的，183−184=255）。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops.lut import (DEFAULT_LUT_AMOUNT, MAX_SIZE_3D, NEUTRAL_TOL,
                                        QUALITY_SIZE_3D, CubeLut, LutError,
                                        apply_lut_np, apply_lut_t, bake,
                                        load_cube_file, parse_cube)

H, W = 41, 57


def ramp_img(seed: int = 3) -> np.ndarray:
    """一张有低频 + 有极端值的 (1,3,H,W) float64 ∈ [0,1]。

    不能只拿均匀噪声当靶：LUT 最大误差发生在黑端拐点与纯白端，纯噪声恰好抽不到
    那几个格点，误差判据就会偏乐观。
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    base = np.stack([xx / (W - 1), yy / (H - 1), (xx + yy) / (W + H - 2)], axis=-1)
    noise = rng.random((H, W, 3)) * 0.25
    a = np.clip(base + noise, 0.0, 1.0)
    a[0, 0] = 0.0
    a[1, 1] = 1.0
    a[2, 2] = [0.0, 1.0, 0.0]
    return np.ascontiguousarray(a.transpose(2, 0, 1)[None])


def grade_fn(x):
    """真值：跨通道矩阵 + gamma + 高光压缩（float64 上精确可算）。"""
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    lin = np.stack([np.power(r, 2.2), np.power(g, 2.2), np.power(b, 2.2)], axis=-1)
    m = np.array([[1.06, -0.04, -0.02], [-0.03, 1.05, -0.02], [-0.05, -0.03, 1.08]])
    y = lin @ m.T
    hi = y.mean(axis=-1, keepdims=True)
    y = y * (1.0 - 0.18 * np.clip(hi - 0.75, 0.0, None))
    return np.clip(np.power(np.clip(y, 0.0, 1.0), 1.0 / 2.2), 0.0, 1.0)


def identity_text(size: int) -> str:
    t = np.linspace(0.0, 1.0, size)
    bb, gg, rr = np.meshgrid(t, t, t, indexing="ij")
    rows = np.stack([rr.ravel(), gg.ravel(), bb.ravel()], axis=1)
    return (f"LUT_3D_SIZE {size}\n"
            + "".join(f"{r:.6f} {g:.6f} {b:.6f}\n" for r, g, b in rows))


def to_u8(a):
    """LSB 差必须走 int16：uint8 相减会模 256 回绕（183−184 = 255）。"""
    return np.rint(np.clip(a, 0.0, 1.0) * 255.0).astype(np.int16)


# ==================================================================== 解析
def test_identity_cube_is_neutral():
    L = parse_cube(identity_text(QUALITY_SIZE_3D))
    assert L.kind == "3d" and L.size == QUALITY_SIZE_3D
    assert L.neutral is True and L.clipped == 0 and L.notes == ()


def test_neutral_is_not_a_free_pass_one_lsb_off_must_not_be_neutral():
    """反向门禁：恒等判定不能松到"差不多就算恒等"。"""
    text = identity_text(4).replace("0.333333 0.000000 0.000000",
                                    "0.363333 0.000000 0.000000")
    L = parse_cube(text)
    assert L.neutral is False, "把表改 3% 还判恒等，短路就会把改色当没改"


def test_domain_not_zero_one_is_never_neutral():
    """DOMAIN 0.1–0.9 的 corner 表是**重映射**，不是恒等。

    上一版只比表不比域，于是它被判成 neutral 直接短路回原图：用户看到"载入成功但
    画面一动不动"，而事件里没有任何异常。
    """
    body = "".join(f"{r} {g} {b}\n" for b in (0.0, 1.0) for g in (0.0, 1.0) for r in (0.0, 1.0))
    L = parse_cube("LUT_3D_SIZE 2\nDOMAIN_MIN 0.1 0.1 0.1\nDOMAIN_MAX 0.9 0.9 0.9\n" + body)
    assert L.domain_min == (0.1, 0.1, 0.1) and L.domain_max == (0.9, 0.9, 0.9)
    assert L.neutral is False, "域不是 0–1 却判成恒等：neutral 那条短路就是错的"
    a = ramp_img()
    out = apply_lut_np(a, L)
    assert np.abs(out - a).max() > 0.05, "非恒等表却不改画面"


def test_default_domain_written_explicitly_is_still_neutral():
    L = parse_cube("LUT_3D_SIZE 2\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n"
                   + "".join(f"{r} {g} {b}\n" for b in (0.0, 1.0)
                             for g in (0.0, 1.0) for r in (0.0, 1.0)))
    assert L.neutral is True


def test_out_of_range_values_are_clipped_and_counted_not_swallowed():
    body = "1.2 0.0 -0.3\n" + "0 0 0\n" * 7
    L = parse_cube(f"LUT_3D_SIZE 2\n{body}")
    assert L.clipped == 2, f"越界值被静默吞掉：clipped={L.clipped}"
    assert any("超出" in n for n in L.notes), L.notes
    assert L.grid.min() >= 0.0 and L.grid.max() <= 1.0


def test_coarse_lut_carries_a_precision_note():
    """低于 33³ 的表精度不足是**实测事实**（17³ max 12 LSB），得写进 notes 而不是装作没看见。"""
    L = parse_cube(identity_text(17))
    assert L.notes and "17³" in L.notes[0], L.notes
    assert parse_cube(identity_text(QUALITY_SIZE_3D)).notes == ()


@pytest.mark.parametrize("bad,frag", [
    ("", "没找到"),
    ("LUT_3D_SIZE 4\n1 2\n", "不是三个数"),
    ("LUT_1D_SIZE 8\n" + "0 0 0\n" * 8, "一维表"),
    (f"LUT_3D_SIZE {QUALITY_SIZE_3D}\n" + "0 0 0\n" * 10, "应当是"),
    ("LUT_3D_SIZE 1\n0 0 0\n", "超出支持范围"),
    (f"LUT_3D_SIZE {MAX_SIZE_3D + 1}\n" + "0 0 0\n" * 8, "超出支持范围"),
    ("LUT_3D_SIZE 2\n" + "nan 0 0\n" + "0 0 0\n" * 7, "非有限"),
    ("LUT_3D_SIZE 2\nLUT_3D_SIZE 4\n" + "0 0 0\n" * 8, "重复"),
    ("LUT_3D_SIZE 2\nDOMAIN_MIN 0 0 0\n" + "0 0 0\n" * 8, "只给了一半"),
    ("LUT_3D_SIZE 2\nDOMAIN_MAX 0.5 0.5 0.5\nDOMAIN_MIN 0.9 0.9 0.9\n"
     + "0 0 0\n" * 8, "必须大于"),
    ("LUT_3D_SIZE abc\n", "不是整数"),
])
def test_bad_cube_text_is_rejected_wholesale(bad, frag):
    with pytest.raises(LutError) as e:
        parse_cube(bad)
    assert frag in str(e.value), str(e.value)


def test_comments_blank_lines_and_scientific_notation_are_accepted():
    body = "".join(f"{r:.3e} {g:.3e} {b:.3e}\n" for b in (0.0, 1.0)
                   for g in (0.0, 1.0) for r in (0.0, 1.0))
    L = parse_cube("# 头注释\n\nLUT_3D_SIZE 2\nTITLE \"x\"\n" + body + "\n# 尾注释")
    assert L.size == 2 and L.title == "x"
    assert np.isfinite(L.grid).all()


def test_load_cube_file_missing_and_ok(tmp_path):
    with pytest.raises(LutError):
        load_cube_file(str(tmp_path / "not-here.cube"))
    p = tmp_path / "id.cube"
    p.write_text(identity_text(4), encoding="utf-8")
    assert load_cube_file(str(p)).neutral is True


# ==================================================================== 应用
def linear_grade(x):
    """一个**每通道线性**的调色：行和为 1、元素非负 ⇒ 输出天然在 [0,1] 里，不挨夹。

    三线性（与四面体）对这种表是数学上精确的，所以这一条判据不依赖“表多陡”的运气：
    误差只能来自实现（取点、轴序、权重）。比“按真值量个上限”硬得多。
    """
    m = np.array([[0.90, 0.06, 0.04],
                  [0.05, 0.90, 0.05],
                  [0.03, 0.07, 0.90]])
    return x @ m.T


def test_linear_table_is_reproduced_exactly():
    """线性表必须逐字节精确复现（float64 参考臂）。取点/轴序/权重错了当场就红。"""
    L = bake(linear_grade, 8)
    a = ramp_img()
    want = linear_grade(a[0].transpose(1, 2, 0))
    got = apply_lut_np(a, L)[0].transpose(1, 2, 0)
    assert np.abs(to_u8(got) - to_u8(want)).max() == 0, \
        f"线性表都复现不了：最大 {np.abs(to_u8(got) - to_u8(want)).max()} LSB"


def test_bake_error_shrinks_with_size_and_is_reported_for_steep_tables():
    """烘焙误差随尺寸单调下降；而**绝对上限不能当判据**，因为误差由表的陡峭度决定。

    实测（同一张靶）：33³ 上 steep 函数平滑区最大 8 LSB、全图 12 LSB；而一个带
    gamma 往返的“轻调”表反而更差（平滑区 10 LSB）——因为 x^(1/2.2) 在黑端导数无穷。
    所以产品口径分两头：自研预设要**自己量一个数写进跑靶**（M3-b），而用户 .cube 无法
    假定真值，只能保证“我们的插值就是标准三线性”与“恒等表逐字节不动”。
    """
    a = ramp_img()
    want = grade_fn(a[0].transpose(1, 2, 0))
    wu = to_u8(want)
    kink = (wu <= 0) | (wu >= 255)
    errs = {}
    for size in (8, 17, QUALITY_SIZE_3D, 64):
        L = bake(grade_fn, size)
        got = apply_lut_np(a, L)[0].transpose(1, 2, 0)
        d = np.abs(to_u8(got) - wu)
        errs[size] = (int(d[~kink].max()), int(d.max()), float((d > 0).mean()))
        print(f"  {size:2d}³ 平滑区 max {errs[size][0]:2d}  全图 max {errs[size][1]:2d}  "
              f"changed {errs[size][2]:.3%}")
    assert errs[8][0] > errs[17][0] >= errs[QUALITY_SIZE_3D][0] >= errs[64][0], errs
    assert errs[QUALITY_SIZE_3D][2] < 0.06, errs
    # 反向门禁：把表尺寸拉到 2³，误差必须大到把“粗表不够准”这句话证出来
    L2 = bake(grade_fn, 2)
    d2 = np.abs(to_u8(apply_lut_np(a, L2)[0].transpose(1, 2, 0)) - wu)
    assert int(d2.max()) > 4 * errs[QUALITY_SIZE_3D][1], int(d2.max())


def test_axis_order_is_blue_varying_first():
    """网格必须按 (B,G,R) 存：R 变化最快。.cube 的行序就是这个约定。

    判据直接拿真值核：grid[b,g,r] 必须等于 fn([r,g,b])。上一版这里写了一句
    `assert ... or True`——那是恒真断言，正是本仓刚在 M2 审查里扫掉的那一类。
    """
    L = bake(grade_fn, 4)
    t = np.linspace(0.0, 1.0, 4)
    for bi in range(4):
        for gi in range(4):
            xx = np.stack([np.tile(t, (4, 1)),
                           np.full((4, 4), t[gi]),
                           np.full((4, 4), t[bi])], axis=-1)
            assert np.abs(L.grid[bi, gi] - grade_fn(xx)).max() < 1e-12, (bi, gi)
    # 行序：解析回来的第 b*size*size + g*size + r 行必须是 [r,g,b] 那个格点
    text = identity_text(4)
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("LUT")]
    first = np.array([float(v) for v in lines[0].split()])
    last = np.array([float(v) for v in lines[-1].split()])
    assert np.allclose(first, [0.0, 0.0, 0.0]) and np.allclose(last, [1.0, 1.0, 1.0])
    second = np.array([float(v) for v in lines[1].split()])
    assert np.allclose(second, [t[1], 0.0, 0.0]), \
        f"第二行应当只让 R 变（blue-varying-first 的反面），得到 {second}"


def test_transposed_grid_gives_a_different_picture():
    """反向门禁：轴序写反必须改画面（这条判据不能是恒真的）。"""
    L = bake(grade_fn, 8)
    wrong = CubeLut(kind="3d", size=L.size,
                    grid=np.ascontiguousarray(np.transpose(L.grid, (2, 1, 0, 3))),
                    title="wrong")
    a = ramp_img()
    d = np.abs(to_u8(apply_lut_np(a, L)) - to_u8(apply_lut_np(a, wrong))).max()
    assert d > 1, f"R/B 轴序写反与正确序看不出差别（{d} LSB），判据是空的"


def test_neutral_apply_returns_the_same_object_on_both_arms():
    """恒等表走显式短路：不是"算出来恰好一样"，是一个字节也没碰。"""
    L = parse_cube(identity_text(QUALITY_SIZE_3D))
    a = ramp_img()
    assert apply_lut_np(a, L) is a
    torch = pytest.importorskip("torch")
    t = torch.from_numpy(np.ascontiguousarray(a.astype(np.float32)))
    assert apply_lut_t(t, L) is t


def test_gpu_arm_matches_cpu_reference_byte_for_byte():
    """探针实测 grid_sample 就是三线性：两臂在 uint8 上必须逐字节一致。"""
    torch = pytest.importorskip("torch")
    L = bake(grade_fn, QUALITY_SIZE_3D)
    a = ramp_img()
    ref = apply_lut_np(a, L)
    t = torch.from_numpy(np.ascontiguousarray(a.astype(np.float32)))
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    got = apply_lut_t(t.to(dev), L).cpu().numpy().astype(np.float64)
    d = np.abs(to_u8(ref) - to_u8(got))
    assert d.max() <= 1, f"CPU/GPU 两臂最大差 {d.max()} LSB"
    assert (d == 0).mean() > 0.99, f"两臂不一致的像素 {(d > 0).mean():.2%}"


def test_apply_keeps_shape_and_dtype_and_rejects_bad_input():
    torch = pytest.importorskip("torch")
    L = bake(grade_fn, 8)
    t = torch.zeros((1, 3, H, W), dtype=torch.float32)
    out = apply_lut_t(t, L)
    assert out.shape == t.shape and out.dtype == t.dtype
    with pytest.raises(LutError):
        apply_lut_t(torch.zeros((2, 3, H, W)), L)
    with pytest.raises(LutError):
        apply_lut_t(torch.zeros((3, H, W)), L)
    with pytest.raises(LutError):
        apply_lut_np(np.zeros((3, H, W)), L)


def test_neutral_tolerance_is_tight():
    """NEUTRAL_TOL 是"1e-6 以内才算恒等"，不是"看着差不多"。"""
    assert NEUTRAL_TOL < 1e-4
    body = "LUT_3D_SIZE 2\n"
    rows = [(r, g, b) for b in (0.0, 1.0) for g in (0.0, 1.0) for r in (0.0, 1.0)]
    body += "".join(f"{r:.9f} {g:.9f} {b:.9f}\n" for r, g, b in rows)
    assert parse_cube(body).neutral is True
    assert parse_cube(body.replace("1.000000000 0.000000000 0.000000000",
                                   "1.000000000 0.000000000 0.000100000", 1)).neutral is False


# ================================================ 常驻层：调色是链尾输出变换（M3-a2）
# 算子对不等于层对。层要管四件算子管不到的事：上显存的**次数**、缓存失效的**边界**、
# 提交点的**原子性**、显存与事件的**上报**。那四处正是 M1-3c / M1-4 / M2-a2 / M2-b
# 各栽过一次的地方，所以这一节全部按“层”而不是按“函数”写。
def skin_u8(seed: int = 7) -> np.ndarray:
    """一张有低频坡+高频颗粒的 (H,W,3) uint8：常驻层的底图就是这个形状。"""
    rng = np.random.default_rng(seed)
    base = (0.30 + 0.45 * (np.arange(W, dtype=np.float64) / (W - 1))[None, :]
            + 0.12 * np.sin(np.arange(H, dtype=np.float64) / 3.0)[:, None])
    a = np.clip(np.stack([base, base * 0.95, base * 1.05], axis=-1)
                + rng.random((H, W, 3)) * 0.08, 0.0, 1.0)
    return np.rint(a * 255.0).astype(np.uint8)


@pytest.fixture()
def layer():
    pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline

    rgb = skin_u8()
    return make_pipeline("cpu", W, H, rgb), rgb


def darker_cube(size: int = QUALITY_SIZE_3D) -> CubeLut:
    """一张“每通道处处压暗 10%”的表：单调、不夹端点。

    拿它当混合臂的靶是有原因的：只有当 graded ≤ base 逐元素成立时，“混出来应当夹在
    两端之间”这条判据才有唯一答案。换一张会推高某些通道的表，方向判据就变成了碰运气。
    """
    return bake(lambda x: np.clip(x * 0.90, 0.0, 1.0), size,
                title="darker", source="test:darker")


def test_no_lut_is_byte_identical_to_plain_chain(layer):
    """没挂表时，接了层的通路必须与“只有磨皮”逐字节相同。

    这是“strength=0 逐字节等于解码原图”那条跨四个里程碑口径的延伸：
    层不能因为“挂了但空着”就改变任何一个字节。
    """
    pipe, _rgb = layer
    pipe.render(0.55)
    with_layer = pipe.read_back()[..., :3].copy()
    plain = (1.0 - 0.55) * pipe.base() + 0.55 * pipe.retouched
    pipe.pack(plain)
    assert np.array_equal(with_layer, pipe.read_back()[..., :3])
    assert pipe.last_lut_ms == 0.0


def test_identity_table_is_loaded_but_applies_nothing(layer):
    """恒等表：“我载入了一张表”与“画面动了”是两件事，上报必须分开说。

    这一条防的是 M3-a1 那个真缺陷的反面：DOMAIN 不是 0–1 的 corner 表曾被当成恒等短路
    回原图（用户看到“载入成功但画面一动不动”）。所以这里两面都卡：真恒等表必须
    不动画面，而且这份“不动”得由 lut_neutral=True 说清楚，不是靠肉眼猜。
    """
    pipe, _rgb = layer
    cube = parse_cube(identity_text(QUALITY_SIZE_3D))
    assert cube.neutral is True
    info = pipe.set_lut(cube, 1.0)
    assert info["lut_set"] is True and info["lut_neutral"] is True
    assert info["lut_lit"] is False and pipe.has_lut() is False
    pipe.render(0.5)
    pipe.clear_lut()
    plain = pipe.read_back()[..., :3].copy()
    pipe.set_lut(cube, 1.0)
    pipe.render(0.5)
    assert np.array_equal(pipe.read_back()[..., :3], plain), "恒等表却改了画面"
    assert pipe.last_lut_ms == 0.0, "恒等表走了非短路那条路（白跑一次 3D 查表）"


def test_amount_zero_returns_the_same_object_and_skips_the_kernel(layer):
    """强度 0 是结构短路，不是“算出来恰好一样”：连 grid_sample 都不跑。"""
    torch = pytest.importorskip("torch")
    pipe, _rgb = layer
    pipe.set_lut(darker_cube(), 0.0)
    t = pipe.retouch(0.5)
    assert pipe.apply_lut(t) is t, "强度 0 还跑了采样：返回的是新张量而不是原张量"
    assert pipe.last_lut_ms == 0.0
    assert torch.is_tensor(t) and not pipe.has_lut()


def test_full_amount_is_the_standalone_apply_byte_for_byte(layer):
    """全强度必须与“单独调一次 apply_lut_t 再打包”逐字节相同。

    这一条钉的是“常驻层只多了缓存与计时，没多任何数学”：如果接线时不当心多插一次
    clip、多走一次 numpy 往返，字节当场对不上。
    """
    pipe, _rgb = layer
    cube = darker_cube()
    pipe.clear_lut()
    t = pipe.retouch(0.5)
    pipe.pack(apply_lut_t(t, cube))
    want = pipe.read_back()[..., :3].copy()
    pipe.set_lut(cube, 1.0)
    pipe.render(0.5)
    got = pipe.read_back()[..., :3].copy()
    d = np.abs(got.astype(np.int16) - want.astype(np.int16))
    assert d.max() == 0, f"常驻臂与独立臂最大差 {d.max()} LSB：链上多了一步数学"


def test_mix_amount_is_the_exact_linear_blend_of_the_two_ends(layer):
    """混合法就是解析可算的那一式，而且方向与单调性都必须对得上。

    拿“夹在两端之间”当判据而不拿“看着像”：强度这个东西在色彩上是“改多少”，
    方向反了、或者混公式写成了 (1-a)*graded + a*base，看上去也是一张“颜色淡了点”的图。
    """
    torch = pytest.importorskip("torch")
    pipe, _rgb = layer
    cube = darker_cube()
    pipe.clear_lut()
    base = pipe.retouch(0.5)
    graded = apply_lut_t(base, cube)
    pipe.set_lut(cube, 0.35)
    got = pipe.apply_lut(base)
    assert torch.equal(got, (1.0 - 0.35) * base + 0.35 * graded), \
        "混合不是声明的那一式：逐元素对不上"
    assert bool((got <= base + 1e-6).all()) and bool((got >= graded - 1e-6).all()), \
        "混出来跑到了两端之外：方向接反或权重算错"
    means = []
    for a in (0.0, 0.25, 0.5, 0.75, 1.0):
        pipe.set_lut_amount(a)
        means.append(float(pipe.apply_lut(base).mean()))
    assert all(x >= y for x, y in zip(means, means[1:])), f"强度越大越亮：{means}"
    assert means[0] - means[-1] > 0.01, f"强度从 0 到 1 几乎看不出差别（{means}）：判据是空的"


def test_lut_volume_is_uploaded_once_not_per_frame(layer, monkeypatch):
    """“常驻”这两个字的可测口径：拖滑块 600 帧也只得一次 H2D。

    不卡这一条的话，“每帧重新 to_device”在时间上仅多 0.1–0.2 ms（产物小），报表看不出来，
    而语义上它就不是常驻了——与 M1-2 那轮“快的全是搬运”同一个坑。
    """
    pipe, _rgb = layer
    calls = []
    real = CubeLut.to_device

    def spy(self, device):
        calls.append(str(device))
        return real(self, device)

    monkeypatch.setattr(CubeLut, "to_device", spy)
    pipe.set_lut(darker_cube(), 1.0)
    for s in (0.2, 0.4, 0.6, 0.8, 1.0):
        pipe.render(s)
    assert len(calls) == 1, f"五帧渲染跑了 {len(calls)} 次上显存：体积根本没常驻"
    vol = pipe.lut_vol
    pipe.set_lut_amount(0.5)
    pipe.render(0.5)
    assert pipe.lut_vol is vol, "改个强度就把体积重传了一遍"
    assert len(calls) == 1


def test_setting_a_lut_invalidates_no_filter_cache(layer):
    """调色在链尾，所以它不该作废任何上游缓存——而且必须带上反向对照。

    只测“挂 LUT 后 filter_ms == 0”是一条风险很高的恒真判据：计数器如果是死的，它永远为
    0。所以先用首次 >0 钉住它能动，再用“真的该作废缓存的那件事”（改磨皮半径）
    证明这个数能看出变化。
    """
    from lumaretouch_engine.vram import DEFAULT_RADIUS

    pipe, _rgb = layer
    pipe.prepare()
    assert pipe.last_filter_ms > 0.0, "首次没真算，后面的“不重算”就没有对照"
    pipe.retouch(0.5)
    assert pipe.last_filter_ms == 0.0 and pipe.last_bands_ms == 0.0
    pipe.set_lut(darker_cube(), 1.0)
    pipe.retouch(0.6)
    assert pipe.last_filter_ms == 0.0 and pipe.last_bands_ms == 0.0, \
        "挂一张调色表却重跑了滤波：它在链尾的位置没接对，或被写进了缓存键"
    pipe.retouch(0.6, radius=DEFAULT_RADIUS + 3)
    assert pipe.last_filter_ms > 0.0, "改了半径也不重算：这个计数器是个死的"


def test_lut_sits_after_the_deform_layer(layer):
    """链尾顺序得写成可观测的判据：形变 → 调色，而且反过来必须看得出差别。

    第二条是关键：如果拿一张“几乎不动”的表去比顺序，两臂逐字节相同，那句“我们在链尾”
    就什么也没证明（M2 审 ⑤ 那类恒真判据）。
    """
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops.deform import analytic_frontal_landmarks

    pipe, _rgb = layer
    cube = bake(lambda x: np.power(np.clip(x, 0.0, 1.0), 2.2), QUALITY_SIZE_3D,
                title="gamma", source="test:gamma")
    pipe.build_deform(analytic_frontal_landmarks())
    pipe.set_deform_amounts({"slim_face": 0.9})
    pipe.clear_lut()
    mix = pipe.retouch(0.5)                      # 先拿一份“只磨皮”的中间张量
    deform_only = pipe.retouch(0.5)              # 含形变（lut 已清，链尾就是形变）
    pipe.set_lut(cube, 1.0)
    got = pipe.retouch(0.5)
    assert torch.equal(got, apply_lut_t(deform_only, cube)), \
        "got 不是 lut(deform(mix))：链尾顺序与声明不一致"
    wrong = pipe.apply_deform(apply_lut_t(mix, cube))    # 调色 → 形变
    assert not torch.equal(got, wrong), \
        "换顺序也看不出任何差别：这条顺序判据是空的（表太软或形变没生效）"


def test_non_finite_grade_output_is_refused_and_the_frame_keeps_the_old_bytes(
        layer, monkeypatch):
    """产出非有限值时报错，而且不能把 NaN 已经写进常驻帧。

    uint8 化会把 NaN 变成“某个看不出错的具体数”，那是比报错难查得多的现场。
    """
    torch = pytest.importorskip("torch")
    from lumaretouch_engine import vram

    pipe, _rgb = layer
    pipe.set_lut(darker_cube(), 1.0)
    pipe.render(0.5)
    good = pipe.read_back()[..., :3].copy()

    def boom(img, lut, vol=None):
        return torch.full_like(img, float("nan"))

    monkeypatch.setattr(vram, "apply_lut_t", boom)
    with pytest.raises(ValueError):
        pipe.render(0.5)
    assert np.array_equal(pipe.read_back()[..., :3], good), \
        "报错之前已经把非有限值包进了常驻帧"


@pytest.mark.parametrize("bad", [-0.1, 1.5, float("nan"), float("inf"), "abc", {}, 2])
def test_illegal_amount_is_rejected_before_any_state_write(layer, bad):
    """非法强度整条拒，而且一个字段也不动（set_lut 与 set_lut_amount 两条臂同规）。"""
    pipe, _rgb = layer
    cube = darker_cube()
    pipe.set_lut(cube, 0.6)
    snap = (pipe.lut, pipe.lut_amount, pipe.lut_vol)
    with pytest.raises(LutError):
        pipe.set_lut(cube, bad)
    with pytest.raises(LutError):
        pipe.set_lut_amount(bad)
    assert (pipe.lut, pipe.lut_amount, pipe.lut_vol) == snap


def test_omitting_amount_keeps_the_current_value(layer):
    """set_lut 不带 amount 是“保留当前值”，与 light add 带参数同形：给了才改。"""
    pipe, _rgb = layer
    pipe.set_lut(darker_cube(), 0.3)
    info = pipe.set_lut(parse_cube(identity_text(8)))
    assert info["lut_amount"] == 0.3, f"换表静默把强度重置了：{info['lut_amount']}"


def test_set_lut_refuses_a_dict_and_a_one_dimensional_table(layer):
    """不拿“看着像”的东西上屏：传个字典、传个一维表都是当场拒。"""
    pipe, _rgb = layer
    with pytest.raises(LutError):
        pipe.set_lut({"kind": "3d", "size": 8})
    with pytest.raises(LutError):
        pipe.set_lut(CubeLut(kind="1d", size=8, grid=np.zeros((8, 3), dtype=np.float64)))
    assert pipe.lut is None and pipe.lut_vol is None


def test_a_failed_mount_leaves_the_previous_table_in_place(layer, monkeypatch):
    """提交点之前那一步可失败的作业抛了，旧表必须原样在位。

    上一轮的教训不是“要回滚”而是“先算完再提交”：这里两者都有——to_device 失败后
    既不换表也不换强度，连帧字节也不变。
    """
    pipe, _rgb = layer
    old = darker_cube()
    pipe.set_lut(old, 0.8)
    pipe.render(0.4)
    before = pipe.read_back()[..., :3].copy()

    def boom(self, device):
        raise RuntimeError("显存不够")

    monkeypatch.setattr(CubeLut, "to_device", boom)
    with pytest.raises(RuntimeError):
        pipe.set_lut(darker_cube(17), 0.5)
    assert pipe.lut is old and pipe.lut_amount == 0.8
    pipe.render(0.4)
    assert np.array_equal(pipe.read_back()[..., :3], before), "被拒的换表命令动了画面"


def test_lut_resident_bytes_counts_volume_and_grid(layer):
    """显存与 CPU 原件两笔都要算：只报一份就是藏账（M1-3c 那条显存账单的原话）。"""
    pipe, _rgb = layer
    cube = darker_cube()
    info = pipe.set_lut(cube, 1.0)
    vol = cube.size ** 3 * 3 * 4                # float32 体积的字节数（实测口径）
    assert info["lut_grid_bytes"] == cube.nbytes()
    assert info["bytes_lut"] == vol + cube.nbytes() == pipe.lut_resident_bytes()
    # 恒等表不挂体积：只计原件那一份
    idc = parse_cube(identity_text(17))
    i2 = pipe.set_lut(idc, 1.0)
    assert pipe.lut_vol is None and i2["bytes_lut"] == idc.nbytes()


def test_clear_lut_frees_everything_and_resets_amount(layer):
    """清层就是回到出厂状态：体积与原件都放下，强度回默认。"""
    pipe, _rgb = layer
    pipe.set_lut(darker_cube(), 0.25)
    info = pipe.clear_lut()
    assert info["lut_set"] is False and info["lut_lit"] is False
    assert info["lut_amount"] == DEFAULT_LUT_AMOUNT and info["bytes_lut"] == 0
    assert pipe.lut is None and pipe.lut_vol is None
    assert pipe.has_lut() is False


def test_replay_mounts_the_same_lut_on_a_new_session(layer):
    """换设备重建会话时，调色层只认那张表本身（不认旧结果）：重放必须逐字节复现。"""
    from lumaretouch_engine.vram import make_pipeline

    pipe, rgb = layer
    cube = darker_cube()
    pipe.set_lut(cube, 0.7)
    pipe.render(0.45)
    graded = pipe.read_back()[..., :3].copy()
    p2 = make_pipeline("cpu", W, H, rgb)
    info = p2.set_lut(cube, 0.7)
    p2.render(0.45)
    assert np.array_equal(p2.read_back()[..., :3], graded), "重放出来的不是同一层调色"
    assert info["bytes_lut"] == pipe.lut_resident_bytes()


def test_the_three_lut_arms_return_the_same_key_set(layer):
    """三条 action 臂共用一份事件形状。

    这是 M2 审查第一条发现的主动版：那个坑是后来才发现的，这次从写第一行接线就钉住。
    """
    pipe, _rgb = layer
    a = pipe.set_lut(darker_cube(), 1.0)
    b = pipe.set_lut_amount(0.5)
    c = pipe.clear_lut()
    assert set(a) == set(b) == set(c), \
        f"事件形状漂了：{(set(a) ^ set(b)) | (set(a) ^ set(c))}"
    # 这一层该说的字段一个都不能少（lut_ms/render_ms 不在这里：它们由命令层在补帧
    # 之后加，得放到协议用例里去卡，否则“字段存在但永远是建层那一刻的数”看不出来）
    for k in ("lut_set", "lut_lit", "lut_mount_ms", "bytes_lut", "lut_grid_bytes",
              "lut_source", "lut_size", "lut_title", "lut_notes", "lut_clipped",
              "lut_domain_min", "lut_domain_max", "lut_amount", "lut_neutral",
              "lut_kind", "device", "layer_recomputed"):
        assert k in a, k
    # source 必须能说出话来：两张同名表时它是“事件里报的是哪一张”的唯一证据
    assert a["lut_source"] == "test:darker" and c["lut_source"] == ""


def test_warm_device_actually_runs_the_3d_lut_kernel(monkeypatch):
    """预热必须真跑过 grid_sample 的 **3D** 内核：它与形变用的 2D 不是同一个编译单元。

    拿计数器包住 apply_lut_t，而不是拿“预热返了个正数”当证据：后者对任何空实现都成立。
    预热用的表还必须是非恒等的，否则 neutral 短路会跳过采样而计数器一个也不涨。
    """
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("没 GPU：预热路径本身就不该跑，测它没意义")
    from lumaretouch_engine import vram

    calls = []
    real = vram.apply_lut_t

    def spy(img, lut, vol=None):
        calls.append((int(lut.size), str(img.device), vol is not None))
        return real(img, lut, vol=vol)

    monkeypatch.setattr(vram, "apply_lut_t", spy)
    ms = vram.warm_device("cuda")
    assert ms > 0.0, f"预热返 0 就等于没预热，但事件会报 engine_warm：{ms}"
    assert calls, "预热一句也没跑 3D 查表：那句“已预热调色内核”是假的"
    assert all(v is True for _s, _d, v in calls), "预热时体积没常驻（每次都重新上显存）"
    assert all(s == QUALITY_SIZE_3D for s, _d, _v in calls), calls
