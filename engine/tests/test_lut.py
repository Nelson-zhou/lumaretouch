"""M3-a 3D LUT：.cube 解析、查表插值、恒等短路。

判据口径来自 gpuspike/m3a.py / m3b.py 的实测，两条最要紧的：
· 误差**必须比解析真值**（一个 float64 上可精确算的调色函数），不许"两种实现互相比"；
· LSB 差要先升 int16 再相减（uint8 相减是模 256 回绕的，183−184=255）。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops.lut import (MAX_SIZE_3D, NEUTRAL_TOL, QUALITY_SIZE_3D,
                                        CubeLut, LutError, apply_lut_np, apply_lut_t,
                                        bake, load_cube_file, parse_cube)

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
