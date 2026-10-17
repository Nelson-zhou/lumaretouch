"""M3-b 内置预设：结构、可说话的上报、以及"表复现色彩观"的那 2 LSB。

预设 = 一张烘焙的色彩观表 + 三个肤色定向参数。两半的精度口径不同（见 ops/presets.py
头部），所以这里分开卡：

· 表的复现误差按**预设自己声明的 look_lsb** 卡，样本是"全色域随机点 + 8 个角点 +
  一条肤色色相扫"——不能只抽均匀噪声，黑端拐点与纯白端才是插值误差最大的地方
  （test_lut.py 同一条理由）。
· 定向的方向按**符号**卡：奶油必须往黄一侧偏、降饱和、提亮；冷白必须降更多饱和、
  提亮更多、色相往红一侧回。数字改了判据就得改，所以这里每个期望都写了出处。

这一节不测 GPU 通路（那是 test_grade.py 与跑靶的事）：预设的数值定义是纯 numpy 的，
在 CPU 上就能把它问清楚。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops.grade import (DH_LIMIT, DS_LIMIT, DV_LIMIT, check_params,
                                          grade_np, hsv_to_rgb_np, rgb_to_hsv_np,
                                          skin_weight_np)
from lumaretouch_engine.ops.lut import QUALITY_SIZE_3D, apply_lut_np
from lumaretouch_engine.ops.presets import (COOL_LOOK_LSB, COOL_MATRIX, CREAMY_LOOK_LSB,
                                            CREAMY_MATRIX, PRESETS, PresetError, get_preset,
                                            names, preset_grade, preset_lut)


def to_u8(a):
    return np.rint(np.clip(a, 0.0, 1.0) * 255.0).astype(np.int16)


def gamut_samples(seed: int = 20261016) -> np.ndarray:
    """(N,1,3) 的采样点：全域随机 + 8 个角点 + 一条肤色色相扫 + 一条灰轴。

    角点与灰轴不是凑数：抬黑/滚降/饱和缩放这些步骤在纯黑、纯白与中性灰上最容易
    露出定义错误（比如行和不为 1 的矩阵会把灰推成有色）。
    """
    rng = np.random.default_rng(seed)
    pts = [rng.random((20000, 3))]
    pts.append(np.stack(np.meshgrid([0.0, 1.0], [0.0, 1.0], [0.0, 1.0], indexing="ij"), -1)
               .reshape(-1, 3))
    gray = np.linspace(0.0, 1.0, 257)[:, None]
    pts.append(np.concatenate([gray, gray, gray], axis=-1))
    hue = np.linspace(0.02, 0.13, 120)[:, None]
    pts.append(hsv_to_rgb_np(np.concatenate(
        [hue, np.full((120, 1), 0.35), np.full((120, 1), 0.72)], axis=-1)))
    return np.concatenate(pts, axis=0)[:, None, :]


def apply_table(x_hw3, cube):
    a = np.ascontiguousarray(np.asarray(x_hw3, dtype=np.float64).transpose(2, 0, 1)[None])
    return apply_lut_np(a, cube)[0].transpose(1, 2, 0)


def gray_ramp() -> np.ndarray:
    t = np.linspace(0.0, 1.0, 513)[:, None]
    return np.concatenate([t, t, t], axis=-1)[:, None, :]


# ------------------------------------------------------------------ 结构与上报
def test_preset_names_are_the_two_product_looks():
    assert names() == ["coolwhite", "creamy"]
    assert set(PRESETS) == {"coolwhite", "creamy"}


def test_unknown_preset_name_is_a_preset_error_not_a_key_error():
    """错名字要当参数拒接（ValueError 族），不是把内部键错漏给调用方。"""
    with pytest.raises(PresetError):
        get_preset("nope")
    with pytest.raises(ValueError):          # PresetError 必须是 ValueError 的子类
        get_preset("")
    with pytest.raises(PresetError):
        preset_lut("奶油")                    # 中文名不是键名：键是英文标识
    with pytest.raises(PresetError):
        preset_grade("Kodak")


def test_preset_lut_reports_who_it_is():
    """source / title 必须能说出话来：报表与"载入成功但画面没动"那类问题靠它分辨。"""
    for name in names():
        p = get_preset(name)
        cube = preset_lut(name)
        assert cube.source == f"preset:{name}", cube.source
        assert cube.title == p.title and cube.title, cube.title
        assert cube.size == QUALITY_SIZE_3D == p.size
        assert cube.kind == "3d"
        assert cube.clipped == 0, f"预设的色彩观越界 {cube.clipped} 个值：某一步没夹域"
        assert cube.neutral is False, "预设烘出恒等表 = 定义没生效"
        assert cube.nbytes() == QUALITY_SIZE_3D ** 3 * 3 * 8


def test_the_two_presets_are_actually_different():
    """两个预设不能是同一份定义换了名字——那"两款预设"就是假的。"""
    a, b = get_preset("creamy"), get_preset("coolwhite")
    assert preset_grade(a.name) != preset_grade(b.name)
    assert not np.allclose(np.asarray(CREAMY_MATRIX), np.asarray(COOL_MATRIX))
    ca, cb = preset_lut(a.name), preset_lut(b.name)
    assert not np.allclose(ca.grid, cb.grid), "两张色彩观表逐值相同：预设只有一个"


# ------------------------------------------------------------------ 数值定义
@pytest.mark.parametrize("matrix", [CREAMY_MATRIX, COOL_MATRIX])
def test_color_matrices_row_sum_is_one(matrix):
    """行和为 1 不是审美而是度量：不然矩阵自己就在改明度，"亮度只由 tone 段负责"散了。"""
    m = np.asarray(matrix, dtype=np.float64)
    assert np.allclose(m.sum(axis=1), 1.0, atol=1e-12), m.sum(axis=1)


def test_creamy_keeps_neutral_gray_neutral():
    """奶油那款在中性灰上必须保持中性（矩阵行和 1 + 抬黑是各通道同量）。"""
    got = get_preset("creamy").look(gray_ramp())
    spread = float(np.abs(got - got[..., 0:1]).max())
    assert spread < 1e-12, f"中性灰被染上了 {spread:.2e} 的色度"


def test_coolwhite_lifts_blue_in_the_shadows_only_and_stays_mild():
    """冷白的 LIFT 是"阴影加一点青"：蓝-红差必须在暗部最大、亮部归零，且幅度 ≤4 LSB。

    这不是装饰性判据：如果抬底写成了常数加，高光也会被推青；如果权重写反了，画面
    会往暖走——两款都是"看起来正常但方向错"，肉眼在小图上很难当场发现。
    """
    ramp = gray_ramp()
    got = get_preset("coolwhite").look(ramp)
    br = (got[..., 2] - got[..., 0])[:, 0]                  # 蓝减红，沿灰轴
    assert float(br[0]) > 0.0, f"最暗处应当偏青，实测 {float(br[0]):.5f}"
    assert float(br[-1]) == pytest.approx(0.0, abs=1e-12), "最亮处不该还有加性青偏"
    assert np.all(np.diff(br) <= 1e-12), "青偏应当随亮度单调收掉，不是中段最大"
    assert float(br.max()) * 255.0 <= 4.0, f"青偏 {float(br.max()) * 255.0:.2f} LSB 过头"


@pytest.mark.parametrize("name", ["creamy", "coolwhite"])
def test_look_is_monotone_on_the_gray_axis(name):
    """灰轴单调不减：抬黑/滚降/饱和缩放任何一步写反方向，这里就碎。

    非单调的色调曲线会在暗部渐变里留下真实的台阶（比 banding 更糟：那是数据错）。
    """
    ramp = gray_ramp()
    got = get_preset(name).look(ramp)[:, 0]
    d = np.diff(got, axis=0)
    assert float(d.min()) > -1e-12, f"灰轴上有回头段：最小差分 {float(d.min()):.3e}"
    assert float(got[:, 0].max()) <= 1.0 and float(got[:, 0].min()) >= 0.0


@pytest.mark.parametrize("name", ["creamy", "coolwhite"])
def test_baked_table_reproduces_the_look_within_the_declared_lsb(name):
    """33³ 表复现色彩观的上限就是预设自带的 look_lsb（gpuspike/m3e.py A 节量的 2）。

    判据用"量化差 ≤ look_lsb"而不是"连续差"：上屏的字节才是产品口径；而 look_lsb
    写死在资产里，改数字必须同时改跑靶，不许一边放宽一边说"实测差不多"。
    """
    p = get_preset(name)
    truth = p.look(gamut_samples())
    got = apply_table(gamut_samples(), preset_lut(name))
    d = np.abs(to_u8(got) - to_u8(truth))
    assert int(d.max()) <= p.look_lsb, \
        f"表复现差 {int(d.max())} LSB，超过预设声明的 {p.look_lsb}：烘焙尺寸或定义变了"
    # 连续误差也报个数（不卡上限）：它才说明误差是插值本身、不是取点/轴序错
    assert float(np.abs(got - truth).max()) < (p.look_lsb + 1) / 255.0


def test_declared_look_lsb_is_the_measured_two():
    """两个数都是 m3e A 节的实测上限（真图与全域量化最大都 2 LSB）。"""
    assert CREAMY_LOOK_LSB == COOL_LOOK_LSB == 2
    assert get_preset("creamy").look_lsb == CREAMY_LOOK_LSB
    assert get_preset("coolwhite").look_lsb == COOL_LOOK_LSB


# ------------------------------------------------------------------ 定向那三个数
@pytest.mark.parametrize("name", ["creamy", "coolwhite"])
def test_preset_grade_params_pass_the_hard_limits(name):
    """预设自己必须先过 check_params：产品资产不该在提交那一刻被引擎拒掉。"""
    dh, ds, dv = preset_grade(name)
    vals = check_params(dh, ds, dv)
    assert vals == (dh, ds, dv, 1.0)
    assert abs(dh) <= DH_LIMIT and abs(ds) <= DS_LIMIT and abs(dv) <= DV_LIMIT
    assert dh != 0.0 or ds != 0.0 or dv != 0.0, "预设的定向是零：那层只是装饰"


def test_preset_directions_match_the_product_words():
    """奶油"往黄偏、降饱和、提亮"，冷白"往红回、降更多饱和、提亮更多"。

    这两句话是产品口径，就得是可测的：ds 都为负（都降饱和）、dv 都为正（都提亮）、
    dh 符号相反，且冷白的降/提幅度更大。
    """
    cdh, cds, cdv = preset_grade("creamy")
    ldh, lds, ldv = preset_grade("coolwhite")
    assert cdh > 0.0 and ldh < 0.0, (cdh, ldh)
    assert cds < 0.0 and lds < 0.0 and abs(lds) > abs(cds), (cds, lds)
    assert cdv > 0.0 and ldv > 0.0 and ldv > cdv, (cdv, ldv)


def test_skin_pixels_move_the_declared_way():
    """把奶油的定向打在肤色像素上：s 必须降、v 必须升；窗外逐字节不动。"""
    def patch(h, s, v):
        hsv = np.concatenate([np.full((4, 8, 1), h), np.full((4, 8, 1), s),
                              np.full((4, 8, 1), v)], axis=-1)
        return hsv_to_rgb_np(hsv)

    skin = patch(0.055, 0.35, 0.72)
    green = patch(0.30, 0.50, 0.60)
    dh, ds, dv = preset_grade("creamy")
    got = grade_np(skin, dh, ds, dv)
    before, after = rgb_to_hsv_np(skin), rgb_to_hsv_np(np.clip(got, 0.0, 1.0))
    assert float((after[..., 1] - before[..., 1]).mean()) < 0.0, "说降饱和却没降"
    assert float((after[..., 2] - before[..., 2]).mean()) > 0.0, "说提亮却没提"
    w = skin_weight_np(rgb_to_hsv_np(np.clip(skin, 0.0, 1.0)))
    assert float(w.mean()) > 0.99, "这块样本应当整片在窗口内"
    out_green = grade_np(green, dh, ds, dv)
    assert np.array_equal(out_green, np.clip(green, 0.0, 1.0)), "绿区被肤色定向改了"


def test_preset_assets_do_not_depend_on_any_third_party_lut():
    """clean-room 自查：预设表里不许出现"从外部素材抄来"的形状——它必须是本仓烘的。

    这条看起来多余，实际防的是很现实的一次走偏：有人为了"效果更像某厂商"把第三方
    .cube 的 grid 直接塞进 presets.py。source 前缀 `preset:` 与 title 是中文这件事
    就是它的可测边界。
    """
    for name in names():
        cube = preset_lut(name)
        assert cube.source.startswith("preset:")
        assert any("越界" in n or "尺寸" in n for n in cube.notes) or cube.notes == ()
        assert all(0.0 <= v <= 1.0 for v in cube.grid.reshape(-1))
