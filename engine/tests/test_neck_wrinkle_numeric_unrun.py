# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic fixtures, NOT runtime or portrait acceptance.

Future authorized execution must separately build/install the derivative. Tests
requiring that core skip honestly if it is absent; a skip is not acceptance.
"""
import math
import numpy as np
import pytest
from lumaretouch_engine import neck_wrinkle_measure as neck


def inputs(n=128):
    rgb = np.full((n, n, 3), 0.58, dtype=np.float32)
    return rgb, np.ones((n, n), dtype=np.float32), np.zeros((n, n), dtype=bool)


def ready(monkeypatch):
    if not neck.available():
        pytest.skip('Separately built neck ABI unavailable; no numerical acceptance')
    # This is fixture isolation, not production permission to bypass cgroup admission.
    monkeypatch.setattr(neck, '_available_estimate', lambda: 4*1024**3)


def measure(rgb, weight, protect, **kwargs):
    return neck.measure(rgb, weight, protect, line_half_width_px=2.0,
                        byte_budget=4*1024**3, **kwargs)


def test_plan_is_pure_composed_and_counts_retained_eligibility(monkeypatch):
    monkeypatch.setattr(neck._native, 'native', lambda: pytest.fail('Plan loaded native backend'))
    p = neck.plan((128, 128), 2.0, (0, 0, 128, 128))
    assert p['dependency_radius_px'] == 27
    assert p['retained_bytes'] == 5*128*128
    assert p['required_work_bytes'] == (34+80+15)*128*128+8*1024**2


def test_zero_is_identity_even_without_arrays_or_backend(monkeypatch):
    monkeypatch.setattr(neck._native, 'native', lambda: pytest.fail('Neutral loaded native backend'))
    current = object()
    assert neck.apply(current, None, amount=0.0) is current


@pytest.mark.parametrize('amount', [True, False, float('nan'), float('inf'), -0.1, 1.1])
def test_amount_strict(amount):
    with pytest.raises(ValueError):
        neck.apply(object(), None, amount=amount)


@pytest.mark.parametrize('scale', [True, 1.39, 12.01, float('nan'), float('inf')])
def test_scale_refuses_instead_of_clamping(scale):
    with pytest.raises(neck.NeckWrinkleScaleError):
        neck.plan((128, 128), scale, (0, 0, 128, 128))


def test_alpha_shape_budget_and_absent_support_refuse_before_backend():
    rgb, weight, protect = inputs()
    with pytest.raises(ValueError):
        measure(np.ones((128, 128, 4), np.float32), weight, protect)
    with pytest.raises(neck.NeckWrinkleContextError):
        measure(rgb, weight*0, protect)
    with pytest.raises(MemoryError):
        neck.measure(rgb, weight, protect, line_half_width_px=2, byte_budget=1)
    with pytest.raises(InterruptedError):
        measure(rgb, weight, protect, cancelled=lambda: True)


def test_flat_valid_context_distinct_from_no_support(monkeypatch):
    ready(monkeypatch)
    rgb, weight, protect = inputs()
    prepared = measure(rgb, weight, protect)
    assert prepared.facts['supported_pixels'] > 0
    assert prepared.facts['changed_pixels'] == 0
    assert prepared.facts['status'] == 'no_detected_wrinkle_lines'
    assert prepared.facts['runtime_quality_accepted'] is False
    assert np.count_nonzero(prepared.eligible_mask) == prepared.facts['supported_pixels']
    assert prepared.log_gain.dtype == np.float32 and prepared.log_gain.flags.c_contiguous
    assert prepared.eligible_mask.dtype == np.bool_ and prepared.eligible_mask.flags.c_contiguous
    with pytest.raises(ValueError):
        prepared.log_gain.setflags(write=True)
    with pytest.raises(ValueError):
        prepared.eligible_mask.setflags(write=True)
    facts = prepared.facts
    facts['changed_pixels'] = 9000
    assert prepared.facts['changed_pixels'] == 0


def test_valley_and_protected_adversarial_invariance(monkeypatch):
    ready(monkeypatch)
    rgb, weight, protect = inputs(192)
    y = np.arange(192, dtype=np.float32)[:, None]
    rgb[:] = (0.58-0.11*np.exp(-((y-96)/2)**2/2))[..., None]
    protect[80:112, 80:112] = True
    changed = rgb.copy()
    changed[protect] = (1.0, 0.0, 0.7)
    a, b = measure(rgb, weight, protect), measure(changed, weight, protect)
    assert np.array_equal(a.log_gain, b.log_gain)
    assert np.array_equal(a.eligible_mask, b.eligible_mask)
    assert a.facts['changed_pixels'] > 0
    assert not np.any(a.log_gain[protect])
    assert not np.any(a.eligible_mask[protect])
    assert a.facts['maximum_proposed_lightness_lift'] <= 6.0
    assert a.facts['maximum_log_gain'] <= math.log(1.25)+1e-8


def test_context_rejection_is_not_a_no_signal_success(monkeypatch):
    ready(monkeypatch)
    rgb, weight, protect = inputs()
    weight[:] = 0
    weight[60:68, 30:98] = 1
    with pytest.raises(neck.NeckWrinkleContextError):
        measure(rgb, weight, protect)


def test_current_linear_common_gain_headroom_and_exact_neutral(monkeypatch):
    ready(monkeypatch)
    current = np.array([[[0.4, 0.2, 0.1], [1.0, 0.2, -0.0], [0.0, -0.0, 0.0],
                         [0.99, 0.4, 0.2], [0.3, 0.4, -0.0]]], dtype=np.float32)
    field = np.full((1, 5), math.log(1.25), dtype=np.float32)
    field[0, 4] = 0
    result = neck.apply(current, field, amount=1)
    np.testing.assert_array_equal(result[0, [1, 2, 4]].view(np.uint32), current[0, [1, 2, 4]].view(np.uint32))
    np.testing.assert_allclose(result[0, 0]/current[0, 0], [1.25]*3, rtol=1e-6)
    gains = result[0, 3]/current[0, 3]
    np.testing.assert_allclose(gains, np.full(3, gains[0]), rtol=1e-6)
    assert np.max(result) <= 1


def test_arbitrary_tile_slices_equal_one_full_current_composition(monkeypatch):
    ready(monkeypatch)
    rgb, weight, protect = inputs()
    y = np.arange(128, dtype=np.float32)[:, None]
    rgb[:] = (0.58-0.11*np.exp(-((y-64)/2)**2/2))[..., None]
    prepared = measure(rgb, weight, protect)
    # The current stage is deliberately different from source: no source patch.
    current = np.full_like(rgb, (0.3, 0.2, 0.15))
    full = neck.apply(current, prepared.log_gain, amount=0.7)
    tiled = current.copy()
    for top, bottom in ((0, 37), (37, 91), (91, 128)):
        for left, right in ((0, 23), (23, 85), (85, 128)):
            tiled[top:bottom, left:right] = neck.apply(current[top:bottom, left:right],
                prepared.log_gain[top:bottom, left:right], amount=0.7)
    np.testing.assert_array_equal(tiled.view(np.uint32), full.view(np.uint32))


def test_hdr_nonfinite_and_nonfloat32_never_clipped(monkeypatch):
    ready(monkeypatch)
    for value in (float('nan'), float('inf'), -0.01, 1.01):
        rgb, weight, protect = inputs()
        rgb[0, 0, 0] = value
        with pytest.raises(ValueError):
            measure(rgb, weight, protect)
    rgb, weight, protect = inputs()
    with pytest.raises(ValueError):
        measure(rgb.astype(np.float64), weight, protect)
