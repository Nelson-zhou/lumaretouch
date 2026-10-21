"""裁剪/旋转（`lnx.crop.v1`）的两臂对拍与恒等自证。

三条硬口径，都是《P0参数注册表.json》+ ADR-0003 直接要的：
① 中性（全画幅 + 0°）逐字节恒等，容差 0；
② 90° 整数倍无损——它走转置而不是插值，所以允许逐像素精确相等；
③ 两臂同算式：连续域差 <1e-3 LSB，量化后 ≤1 LSB，且翻牌只发生在量化边界。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops.geometry import (
    GeometryError, check, crop_np, crop_rotate_np, crop_rotate_t, is_identity,
    out_size, rotate_np,
)

torch = pytest.importorskip("torch")


def _photo(h=40, w=56):
    """低频 + 细节的混合样本：纯噪声在两臂之间只会比出插值精度，纯渐变测不出边界翻牌。"""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    base = 0.25 + 0.5 * xs / (w - 1) + 0.12 * np.sin(ys / 3.0)
    rgb = np.stack([base, base * 0.92, 1.0 - base * 0.8], axis=-1)
    rgb = np.clip(rgb + (((xs * 7 + ys * 13) % 5) / 90.0)[..., None], 0.0, 1.0)
    return np.rint(rgb * 255.0).astype(np.uint8)


def _to_hw3_f32(a):
    return torch.from_numpy(np.ascontiguousarray(a.astype(np.float32) / 255.0))


# ------------------------------------------------------------------ 恒等与校验
def test_neutral_returns_the_same_object_not_a_copy():
    """中性必须"没算"，不是"算出来恰好一样"——预览链每一帧都要过这里。"""
    a = _photo()
    assert crop_rotate_np(a, [0.0, 0.0, 1.0, 1.0], 0.0) is a
    t = _to_hw3_f32(a)
    assert crop_rotate_t(t, [0.0, 0.0, 1.0, 1.0], 0.0) is t
    assert is_identity([0.0, 0.0, 1.0, 1.0], 0.0) is True


def test_ranges_follow_the_frozen_registry():
    """量程逐条按注册表：rect 逐坐标 [0,1] 且 x0<x1;y0<y1，角度 [-180,180]。"""
    with pytest.raises(GeometryError, match="越界"):
        check([0.0, -0.01, 0.5, 0.5], 0.0)
    with pytest.raises(GeometryError, match="x0<x1"):
        check([0.5, 0.0, 0.5, 0.9], 0.0)          # 零宽：不是一张"很窄的图"，是非法输入
    with pytest.raises(GeometryError, match="y0<y1"):
        check([0.0, 0.4, 0.9, 0.4], 0.0)
    with pytest.raises(GeometryError, match="越界"):
        check([0.0, 0.0, 1.0, 1.0], 181.0)
    with pytest.raises(GeometryError, match="4 个数"):
        check([0.0, 0.0, 1.0], 0.0)
    # ±180 是闭区间端点，合法且不是恒等
    assert is_identity([0.0, 0.0, 1.0, 1.0], 180.0) is False


def test_nan_is_refused_not_propagated():
    """NaN 角度不会"渲染成不旋转"，而是把整帧污染成 NaN——必须在入口就拒。"""
    with pytest.raises(GeometryError):
        check([0.0, 0.0, 1.0, 1.0], float("nan"))
    with pytest.raises(GeometryError):
        check([0.0, float("nan"), 1.0, 1.0], 0.0)


# ------------------------------------------------------------------ 裁剪
def test_crop_is_exact_pixel_slicing_without_resampling():
    a = _photo()
    c = crop_rotate_np(a, [0.25, 0.25, 0.75, 0.75], 0.0)
    assert c.shape == (20, 28, 3), c.shape        # 56×40 取 [0.25,0.75]² → 28×20
    # 剪出来的每一行都必须在原图里逐字节存在：插值过的行不可能与源行完全相同
    assert (c == a[10:30, 14:42]).all(), "裁剪带了重采样：这不是剪，是重新画"


def test_out_size_agrees_with_the_produced_array():
    """预览与导出共用一个尺寸算法；这里把两边都对上，防"报的 B 与像素不是同一张"。"""
    a = _photo(40, 56)
    for rect, deg in (([0.1, 0.2, 0.9, 0.8], 0.0), ([0.0, 0.0, 1.0, 1.0], 30.0),
                      ([0.2, 0.1, 0.8, 0.9], 90.0), ([0.0, 0.0, 1.0, 1.0], -90.0),
                      ([0.3, 0.3, 0.7, 0.7], 17.5)):
        out = crop_rotate_np(a, rect, deg)
        ow, oh = out_size(56, 40, rect, deg)
        assert (out.shape[1], out.shape[0]) == (ow, oh), (rect, deg, out.shape, (ow, oh))


def test_quarter_turn_is_lossless():
    """90° 整数倍走转置：无损意味着与 np.rot90 逐字节相同，而不是"看起来差不多"。"""
    a = _photo()
    assert np.array_equal(rotate_np(a, 90.0), np.ascontiguousarray(np.rot90(a, -1)))
    assert np.array_equal(rotate_np(a, -90.0), np.ascontiguousarray(np.rot90(a, 1)))
    assert np.array_equal(rotate_np(a, 180.0), np.ascontiguousarray(np.rot90(a, 2)))
    assert rotate_np(a, 90.0).shape == (a.shape[1], a.shape[0], 3)


# ------------------------------------------------------------------ 两臂对拍
@pytest.mark.parametrize("rect,deg", [
    ([0.0, 0.0, 1.0, 1.0], 0.0),
    ([0.2, 0.1, 0.8, 0.9], 0.0),
    ([0.2, 0.1, 0.8, 0.9], 90.0),
    ([0.15, 0.2, 0.85, 0.7], 23.0),
    ([0.0, 0.0, 1.0, 1.0], -37.5),
])
def test_two_arms_agree_across_the_board(rect, deg):
    a = _photo()
    np_out = crop_rotate_np(a, rect, deg, uint8=False).astype(np.float64) / 255.0
    t_out = crop_rotate_t(_to_hw3_f32(a), rect, deg, uint8=False).numpy().astype(np.float64)
    assert np_out.shape == t_out.shape, (np_out.shape, t_out.shape)
    cont = float(np.abs(np_out - t_out).max()) * 255.0
    assert cont < 1e-3, f"两臂连续域差 {cont:.2e} LSB：这是算法差，不是精度"
    d = np.abs(np.rint(np.clip(np_out, 0, 1) * 255) - np.rint(np.clip(t_out, 0, 1) * 255))
    assert int(d.max()) <= 1, f"两臂量化后差 {int(d.max())} LSB"


def test_torch_arm_uint8_matches_numpy_arm_within_one_lsb():
    """生产臂交回 uint8 时也要与真值臂对得上（导出用的就是这个形状）。"""
    a = _photo()
    n = crop_rotate_np(a, [0.1, 0.15, 0.9, 0.85], 15.0)
    # 生产臂收到 uint8 张量才交回 uint8；给它 0..1 的 float 还要它"变成 uint8"
    # 是测试的臆想，不是实现该做的事（那样等于偷偷改了数据类型）
    t = crop_rotate_t(torch.from_numpy(np.ascontiguousarray(a)), [0.1, 0.15, 0.9, 0.85], 15.0)
    assert t.dtype == torch.uint8, t.dtype
    got = t.numpy()
    assert got.shape == n.shape
    assert int(np.abs(got.astype(np.int16) - n.astype(np.int16)).max()) <= 1


def test_rotation_actually_moves_pixels_and_fills_outside_with_zero():
    """反向门禁：万一两臂都算成"原样返回"，上面那些对拍会全绿。这条确认它真的转了。"""
    a = np.zeros((20, 40, 3), np.uint8)
    a[:, 20:40] = 255                        # 右半边白：旋转后黑白分界必须不再是竖直的
    out = crop_rotate_np(a, [0.0, 0.0, 1.0, 1.0], 45.0)
    assert out.shape[0] > 0 and out.shape[1] > 0
    row = out[out.shape[0] // 2]
    assert not np.all(row == row[0]), "45° 之后还是整行同色——等于没转"
    assert out.min() == 0 and out.max() > 0, "画布外应当补 0，而画面里仍有非零像素"


@pytest.mark.parametrize("angle", [-179.9, -90.1, -89.9, -0.1, 0.1, 89.9, 90.1, 179.9])
def test_legacy_snap_dimensions_and_pixels_agree_on_both_sides(angle):
    # Large enough for the old bounding-box calculation to differ by pixels.
    # Preserve legacy rendered pixels; only the incorrect reported size changes.
    a = _photo(256, 1024)
    rect = [0.1, 0.125, 0.9, 0.875]
    cropped = crop_np(a, rect)
    expected = np.ascontiguousarray(np.rot90(cropped, int(round(-angle / 90)) % 4))
    actual = crop_rotate_np(a, rect, angle)
    native = crop_rotate_t(torch.from_numpy(a), rect, angle).numpy()
    assert out_size(1024, 256, rect, angle) == (expected.shape[1], expected.shape[0])
    assert np.array_equal(actual, expected)
    assert np.array_equal(native, expected)


@pytest.mark.parametrize("angle", [-90.5, -89.5, -0.5, 0.5, 89.5, 90.5])
def test_exact_half_degree_remains_interpolated(angle):
    from lumaretouch_engine.ops.geometry import _snapped_quarter_turn
    assert _snapped_quarter_turn(angle) is None
    a = _photo(64, 96)
    rect = [0., 0., 1., 1.]
    actual = crop_rotate_np(a, rect, angle)
    native = crop_rotate_t(torch.from_numpy(a), rect, angle).numpy()
    assert out_size(96, 64, rect, angle) == (actual.shape[1], actual.shape[0])
    assert native.shape == actual.shape
    assert np.abs(native.astype(np.int16) - actual.astype(np.int16)).max() <= 1
