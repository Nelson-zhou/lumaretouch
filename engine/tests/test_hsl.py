"""八色 HSL：分段窗口、量程与两条臂的判据。"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops import hsl as HS

ZERO = (0.0,) * 24


def _red(n=16):
    return np.tile(np.array([0.8, 0.1, 0.1]), (n, n, 1))


def _blue(n=16):
    return np.tile(np.array([0.1, 0.1, 0.8]), (n, n, 1))


def _bands(band, *, dh=0.0, ds=0.0, dl=0.0):
    b = list(ZERO)
    b[band * 3:band * 3 + 3] = [dh, ds, dl]
    return tuple(b)


def test_zero_bands_are_identity_and_length_is_checked():
    x = np.random.default_rng(3).random((8, 9, 3))
    assert np.allclose(HS.hsl_np(x, ZERO), x, atol=1e-12)
    assert HS.is_identity(ZERO)
    with pytest.raises(ValueError):
        HS.check_hsl((0.0,) * 23)


def test_red_saturation_minus_hundred_becomes_gray_and_blue_is_untouched():
    red = _red()
    out = HS.hsl_np(red, _bands(0, ds=-100))
    assert np.ptp(out, axis=-1).max() < 1e-9, "红段 -100 饱和度没有把红变成灰"
    blue = _blue()
    keep = HS.hsl_np(blue, _bands(0, ds=-100))
    assert np.allclose(keep, blue, atol=1e-9), "红段的滑块动了蓝像素（窗口漏了）"


def test_hue_shift_moves_red_toward_orange_and_leaves_green():
    red = _red()
    out = HS.hsl_np(red, _bands(0, dh=30))
    # 红 (h=0) 往 +30° 转之后绿通道上升、蓝通道保持低位
    assert out[..., 1].mean() > red[..., 1].mean() + 0.05
    assert out[..., 2].mean() < 0.2
    green = np.tile(np.array([0.1, 0.8, 0.1]), (16, 16, 1))
    assert np.allclose(HS.hsl_np(green, _bands(0, dh=30)), green, atol=1e-9)


def test_luminance_band_brightens_only_that_band():
    red = _red()
    out = HS.hsl_np(red, _bands(0, dl=50))
    assert out.mean() > red.mean() + 0.05
    blue = _blue()
    assert np.allclose(HS.hsl_np(blue, _bands(0, dl=50)), blue, atol=1e-9)


def test_gray_pixels_are_not_touched_by_any_band():
    gray = np.full((8, 8, 3), 0.5)
    for band in range(8):
        out = HS.hsl_np(gray, _bands(band, dh=60, ds=100, dl=100))
        assert np.allclose(out, gray, atol=1e-12), f"第 {band} 段动了无彩像素"


def test_limits_are_rejected():
    with pytest.raises(ValueError):
        HS.check_hsl(_bands(0, dh=61))
    with pytest.raises(ValueError):
        HS.check_hsl(_bands(0, ds=101))
    with pytest.raises(ValueError):
        HS.check_hsl((float("nan"),) * 24)


def test_four_dimensional_layout_round_trips():
    x = np.random.default_rng(4).random((1, 3, 5, 7))
    y = HS.hsl_np(x, _bands(1, ds=30))
    assert y.shape == x.shape
    z = HS.hsl_np(np.transpose(x, (0, 2, 3, 1)), _bands(1, ds=30))
    assert np.allclose(y, np.transpose(z, (0, 3, 1, 2)))


def test_engine_registers_the_layer_in_both_lists():
    """图层要同时进 HANDLED 与 EDIT_CMDS（上一轮曝光只改一边，撤销纹丝不动）。"""
    from lumaretouch_engine.server import Engine
    assert "hsl" in Engine.HANDLED
    assert "hsl" in Engine.EDIT_CMDS
    assert "_hsl" in Engine.DOC_FIELDS
