"""Authored wrapper contracts, UNRUN. Requires normal engine test environment.

No tests or imports were executed as part of the source-only delivery.
Rust numerical cases live in lib.rs and are also UNRUN.
"""
import numpy as np
import pytest

from lumaretouch_engine import spill_removal_native as spill


def fields(delta, confidence):
    return {'delta': np.asarray(delta, dtype=np.float32),
            'confidence': np.asarray(confidence, dtype=np.float32),
            'encoding': spill.ENCODING, 'render_scale': 1.0,
            'domain_shape': np.asarray(confidence).shape, 'estimator': spill.ESTIMATOR}


def test_zero_strength_has_exact_fields_and_no_native_load(monkeypatch):
    monkeypatch.setattr(spill, 'native', lambda: pytest.fail('Neutral must not load native'))
    original = np.full((3, 4, 3), 0.3, dtype=np.float32)
    alpha = np.full((3, 4), 0.5, dtype=np.float32)
    before = alpha.copy()
    prepared = spill.prepare(original, alpha, strength=0)
    assert not prepared['delta'].any()
    assert not prepared['confidence'].any()
    assert np.array_equal(alpha, before)
    assert not prepared['delta'].flags.writeable
    assert not prepared['confidence'].flags.writeable
    assert np.array_equal(spill.apply_fields(original, prepared), original)


@pytest.mark.parametrize('bad', [np.nan, np.inf, -0.01, 1.01])
def test_analysis_refuses_nonfinite_or_hdr_even_when_neutral(bad):
    original = np.full((1, 1, 3), bad, dtype=np.float32)
    with pytest.raises(ValueError, match='finite SDR'):
        spill.prepare(original, np.ones((1, 1), dtype=np.float32), strength=0)


def test_alpha_source_and_current_are_not_mutated():
    current = np.array([[[0.3, 0.5, 0.4]]], dtype=np.float32)
    before = current.copy()
    prepared = fields([[[0.02, -0.01, 0.0]]], [[0.5]])
    d_before = prepared['delta'].copy()
    q_before = prepared['confidence'].copy()
    actual = spill.apply_fields(current, prepared)
    assert np.allclose(actual, current + prepared['delta'] * 0.5, atol=1e-7)
    assert np.array_equal(current, before)
    assert np.array_equal(prepared['delta'], d_before)
    assert np.array_equal(prepared['confidence'], q_before)


def test_current_edit_offset_survives_and_strength_is_not_squared():
    first = np.array([[[0.20, 0.40, 0.30]]], dtype=np.float32)
    edited = first + np.float32(0.1)
    prepared = fields([[[0.04, -0.02, 0.0]]], [[0.25]])
    a = spill.apply_fields(first, prepared)
    b = spill.apply_fields(edited, prepared)
    assert np.allclose(b - a, edited - first, atol=1e-7)
    assert np.allclose(a - first, [[[0.01, -0.005, 0.0]]], atol=1e-7)


def test_one_common_gamut_step_preserves_luminance_without_rgb_clamp():
    delta = np.array([[[0.1, -(0.2126 * 0.1 + 0.0722 * 0.05) / 0.7152, 0.05]]], dtype=np.float32)
    current = np.array([[[0.99, 0.30, 0.40]]], dtype=np.float32)
    prepared = fields(delta, [[1.0]])
    actual = spill.apply_fields(current, prepared)
    assert np.isfinite(actual).all() and np.all((actual >= 0) & (actual <= 1))
    change = actual - current
    ratio = change[0, 0] / delta[0, 0]
    assert np.max(ratio) - np.min(ratio) < 2e-6
    assert abs(float(np.dot(change[0, 0], [0.2126, 0.7152, 0.0722]))) < 1e-7


def test_neutral_erasure_and_edited_hdr_pixels_remain_bit_exact():
    current = np.array([[[1.2, 0.2, 0.3], [-0.1, 0.2, 0.3], [0.3, 0.4, 0.5]]], dtype=np.float32)
    prepared = fields([[[0.1, -0.1, 0], [0.1, -0.1, 0], [0.1, -0.1, 0]]], [[1, 1, 0]])
    assert np.array_equal(spill.apply_fields(current, prepared), current)


def test_full_prepared_field_crop_matches_tile_application_exactly():
    current = np.full((5, 7, 3), 0.4, dtype=np.float32)
    delta = np.broadcast_to(np.array([0.03, -0.01, 0.02], dtype=np.float32), current.shape).copy()
    prepared = fields(delta, np.full((5, 7), 0.7, dtype=np.float32))
    whole = spill.apply_fields(current, prepared)
    tiles = []
    for start, end in [(0, 2), (2, 5)]:
        crop = dict(prepared, delta=delta[start:end], confidence=prepared['confidence'][start:end],
                    domain_shape=(end - start, 7))
        tiles.append(spill.apply_fields(current[start:end], crop))
    assert np.array_equal(whole, np.concatenate(tiles, axis=0))


def test_cancelled_prepare_and_apply_publish_no_result(monkeypatch):
    monkeypatch.setattr(spill, 'native', lambda: pytest.fail('Cancelled before native'))
    source = np.full((3, 3, 3), 0.3, dtype=np.float32)
    with pytest.raises(InterruptedError):
        spill.prepare(source, np.ones((3, 3), dtype=np.float32), cancelled=lambda: True)
    prepared = fields(np.zeros_like(source), np.zeros((3, 3), dtype=np.float32))
    with pytest.raises(InterruptedError):
        spill.apply_fields(source, prepared, cancelled=lambda: True)


def test_24mp_standalone_estimate_is_bounded_but_not_shared_admission():
    assert spill.memory_estimate((4000, 6000)) == 64 * 24_000_000 + 67_108_864
    assert spill.memory_estimate((4000, 6000)) < spill.MAX_BYTES
    with pytest.raises(ValueError):
        spill.memory_estimate((65536, 65536))


@pytest.mark.parametrize('field', ['delta', 'confidence'])
def test_nonfinite_field_is_rejected(field):
    current = np.full((1, 1, 3), 0.3, dtype=np.float32)
    prepared = fields([[[0.1, 0, 0]]], [[1]])
    prepared[field].flat[0] = np.nan
    with pytest.raises(ValueError, match='finite'):
        spill.apply_fields(current, prepared)
