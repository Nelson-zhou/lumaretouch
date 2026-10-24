# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored wrapper/state fixtures, entirely UNRUN. No product imports executed.

Numerical behavior/FFI parity fixtures are in core/skin_gloss/tests.rs, also UNRUN. Tests here
use a protocol fake only for boundary/error paths, never as a runtime fallback.
"""
import ctypes

import numpy as np
import pytest

from lumaretouch_engine import skin_gloss_native as gloss
from lumaretouch_engine import skin_gloss_state as state


class CopyOnlyProtocol:
    def lrt_skin_gloss_apply_v1(self, current, current_len, reference, reference_len,
                               coverage, coverage_len, width, height, amount,
                               radius, output, output_len, cancel, context):
        assert current_len == reference_len == output_len == 3 * width * height
        assert coverage_len == width * height
        assert 2 <= radius <= 256
        if cancel(context):
            return 4
        ctypes.memmove(output, current, current_len * ctypes.sizeof(ctypes.c_float))
        return 0


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setattr(gloss, '_available_estimate', lambda: 16 * 1024**3)
    monkeypatch.setattr(gloss, 'native', lambda: CopyOnlyProtocol())


def test_exact_recipe_and_signed_amount():
    assert state.OP == 'lnx.skin_gloss.v1'
    assert state.neutral() == {'version': 1, 'amount': 0.0}
    assert state.check(None) == state.neutral()
    assert state.active({'version': 1, 'amount': -1})
    assert not state.active({'version': 1, 'amount': -0.0})
    for bad in [True, float('nan'), float('inf'), 1.01, -1.01, 10**1000]:
        with pytest.raises(ValueError):
            state.check({'version': 1, 'amount': bad})
    for bad in [{'version': True, 'amount': 0}, {'version': 1},
                {'version': 1, 'amount': 0, 'radius': 3}, {'version': 2, 'amount': 0}]:
        with pytest.raises(ValueError):
            state.check(bad)


def test_neutral_strided_snapshot_has_owned_exact_output(protocol):
    source = np.full((6, 8, 3), 0.3, dtype=np.float32)[:, ::2]
    source[0, 0, 0] = -0.0
    before = source.copy()
    mask = np.ones((6, 8), dtype=np.float32)[:, ::2]
    out = gloss.apply(source, mask, -0.0, reference_rgb=source, radius=2)
    assert out.flags.c_contiguous and out.flags.owndata
    assert np.array_equal(out.view(np.uint32), source.view(np.uint32))
    assert np.array_equal(before.view(np.uint32), source.view(np.uint32))
    assert not np.shares_memory(source, out)


def test_required_original_reference_and_strict_input_contract(protocol):
    source = np.full((3, 3, 3), 0.3, dtype=np.float32)
    mask = np.ones((3, 3), dtype=np.float32)
    with pytest.raises(TypeError):
        gloss.apply(source, mask, 0, radius=2)
    for radius in [True, 1, 257, 2.0, np.int32(2)]:
        with pytest.raises(ValueError):
            gloss.apply(source, mask, 0, reference_rgb=source, radius=radius)
    for bad in [source.astype(np.float64), source[..., :2], np.zeros((2, 3, 3), dtype=np.float32)]:
        with pytest.raises(ValueError):
            gloss.apply(source, mask, 0, reference_rgb=bad, radius=2)
    for bad in [float('nan'), float('inf'), -0.01, 1.01]:
        reference = source.copy()
        reference[0, 0, 0] = bad
        with pytest.raises(ValueError, match='finite SDR'):
            gloss.apply(source, mask, 0, reference_rgb=reference, radius=2)


def test_memory_estimate_is_pure_and_matches_documented_layout(monkeypatch):
    monkeypatch.setattr(gloss, 'native', lambda: pytest.fail('No core load for estimate'))
    monkeypatch.setattr(gloss, '_available_estimate', lambda: pytest.fail('No cgroup read for estimate'))
    assert gloss.memory_estimate((4000, 6000)) == 84 * 24_000_000 + 8 * 1024**2
    with pytest.raises(MemoryError):
        gloss.memory_estimate((6000, 6000))
    for shape in [(3, 3, 3), (True, 3), (0, 3)]:
        with pytest.raises(ValueError):
            gloss.memory_estimate(shape)


def test_cancellation_and_resource_refusal_precede_native_allocation(monkeypatch):
    source = np.full((3, 3, 3), 0.3, dtype=np.float32)
    mask = np.ones((3, 3), dtype=np.float32)
    monkeypatch.setattr(gloss, 'native', lambda: pytest.fail('Must refuse before loading'))
    with pytest.raises(InterruptedError):
        gloss.apply(source, mask, 1, reference_rgb=source, radius=2, cancelled=lambda: True)
    monkeypatch.setattr(gloss, '_available_estimate', lambda: 0)
    with pytest.raises(MemoryError):
        gloss.apply(source, mask, 1, reference_rgb=source, radius=2)


def test_callback_exception_is_reraised_outside_ffi():
    def broken():
        raise LookupError('caller callback failed')
    callback, errors = gloss._callback(broken)
    assert callback(None) == 1
    with pytest.raises(LookupError, match='caller callback failed'):
        gloss._result(4, lambda: False, errors)


def test_missing_native_is_explicit_even_when_neutral(monkeypatch):
    source = np.full((3, 3, 3), 0.3, dtype=np.float32)
    mask = np.ones((3, 3), dtype=np.float32)
    def absent():
        raise RuntimeError('Skin gloss Rust core is not installed; no fallback was applied')
    monkeypatch.setattr(gloss, 'native', absent)
    monkeypatch.setattr(gloss, '_available_estimate', lambda: 16 * 1024**3)
    assert not gloss.available()
    assert state.capability()['skin_gloss_available'] is False
    with pytest.raises(RuntimeError, match='no fallback'):
        gloss.apply(source, mask, 0, reference_rgb=source, radius=2)
