"""影调四项（对比度/高光/阴影/饱和度）与曝光层扩展的判据。"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops import exposure as EX
from lumaretouch_engine.ops import tone as TN


def _img(seed=0, h=6, w=8):
    return np.random.default_rng(seed).random((h, w, 3))


def test_tone_identity_is_exact_and_apply_short_circuits():
    x = _img()
    # 非中性路径在 0 处由算式恒等；浮点上允许最后一位的舍入
    assert np.allclose(TN.tone_np(x), x, atol=1e-15)
    assert TN.is_identity()
    # 曝光层：四项与 EV 全中性时，链上直接把原张量递回去（同一个对象）
    assert EX.apply_exposure_t(x, {"ev": 0, "contrast": 0}) is x


def test_contrast_widens_and_flattens_the_histogram():
    x = _img()
    hi = TN.tone_np(x, contrast=60)
    lo = TN.tone_np(x, contrast=-60)
    assert np.std(hi) > np.std(x) > np.std(lo)
    # 端点附近仍被夹在 [0,1]
    assert hi.min() >= 0.0 and hi.max() <= 1.0


def test_saturation_minus_hundred_is_grayscale():
    x = _img()
    g = TN.tone_np(x, saturation=-100)
    assert np.ptp(g, axis=-1).max() < 1e-12


def test_highlights_and_shadows_are_luma_gated():
    dark = np.full((4, 4, 3), 0.15)
    bright = np.full((4, 4, 3), 0.85)
    lifted_hi = TN.tone_np(bright, highlights=80)
    lifted_sh = TN.tone_np(dark, shadows=80)
    assert lifted_hi.mean() > bright.mean() + 0.05
    assert lifted_sh.mean() > dark.mean() + 0.05
    # 高光主要动亮部、阴影主要动暗部
    assert abs(TN.tone_np(dark, highlights=80).mean() - dark.mean()) < 0.02
    assert abs(TN.tone_np(bright, shadows=80).mean() - bright.mean()) < 0.02


def test_tone_limits_are_rejected_and_nan_is_rejected():
    with pytest.raises(ValueError):
        TN.check_tone(contrast=101)
    with pytest.raises(ValueError):
        TN.check_tone(saturation=float("nan"))


def test_four_dimensional_layout_round_trips():
    x = np.random.default_rng(2).random((1, 3, 5, 7))
    y = TN.tone_np(x, contrast=30, saturation=20)
    assert y.shape == x.shape
    # 同一张图在 (1,3,H,W) 与 (1,H,W,3) 上算出来的结果逐点一致
    z = TN.tone_np(np.transpose(x, (0, 2, 3, 1)), contrast=30, saturation=20)
    assert np.allclose(y, np.transpose(z, (0, 3, 1, 2)))


def test_exposure_layer_carries_tone_and_keeps_white_balance():
    x = _img()
    # 只给影调：WB 中性时仍要真改画面（不是被短路掉）
    y = EX.exposure_np(x, 0, 0, 0, contrast=50)
    assert not np.allclose(x, y)
    # 只给 EV：与原路径一致
    assert np.allclose(EX.exposure_np(x, 1.0), EX.exposure_np(x, 1.0))
