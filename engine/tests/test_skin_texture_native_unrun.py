# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN boundary/state fixtures; no product imports were executed.

The copy-only protocol fake tests transport, not the numerical algorithm. Rust
fixtures remain uncompiled/unrun, and all real-image acceptance remains open.
"""
import ctypes

import numpy as np
import pytest

from lumaretouch_engine import skin_texture_native as texture
from lumaretouch_engine import skin_texture_state as state


class CopyOnlyProtocol:
    def lrt_skin_texture_apply_v1(self, current, current_len, reference, reference_len,
                                 coverage, coverage_len, width, height, amount, clarity,
                                 radius, output, output_len, cancel, context):
        assert current_len == reference_len == output_len == 3 * width * height
        assert coverage_len == width * height
        assert -1 <= amount <= 1 and 0 <= clarity <= 1 and 4 <= radius <= 256
        assert ctypes.addressof(current.contents) != ctypes.addressof(reference.contents)
        if cancel(context):
            return 4
        ctypes.memmove(output, current, current_len * ctypes.sizeof(ctypes.c_float))
        return 0


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setattr(texture, '_available_estimate', lambda: 16 * 1024**3)
    monkeypatch.setattr(texture, 'native', lambda: CopyOnlyProtocol())


def test_exact_two_axis_portable_recipe():
    assert state.OP == 'lnx.skin_texture.v1'
    assert state.KEYS == ('texture', 'clarity')
    assert state.neutral() == {'version': 1, 'texture': 0.0, 'clarity': 0.0}
    assert state.check(None) == state.neutral()
    assert state.active({'version': 1, 'texture': -1, 'clarity': 0})
    assert state.active({'version': 1, 'texture': 0, 'clarity': 1})
    assert not state.active({'version': 1, 'texture': -0.0, 'clarity': -0.0})
    for key, bad in [('texture', True), ('texture', float('nan')), ('texture', float('inf')),
                     ('texture', -1.01), ('texture', 1.01), ('texture', 10**1000),
                     ('clarity', True), ('clarity', -0.01), ('clarity', 1.01),
                     ('clarity', float('nan')), ('clarity', np.float32(0.5))]:
        recipe = state.neutral()
        recipe[key] = bad
        with pytest.raises(ValueError):
            state.check(recipe)
    for bad in [{'version': True, 'texture': 0, 'clarity': 0}, {'version': 1, 'texture': 0},
                {'version': 2, 'texture': 0, 'clarity': 0},
                {'version': 1, 'texture': 0, 'clarity': 0, 'radius': 4},
                {'version': 1, 'texture': 0, 'clarity': 0, 'mask': []}]:
        with pytest.raises(ValueError):
            state.check(bad)
    a, b = state.neutral(), state.neutral()
    a['texture'] = 1
    assert b['texture'] == 0


def test_neutral_strided_snapshots_are_owned_independent_and_bit_exact(protocol):
    source = np.full((6, 8, 3), 0.3, dtype=np.float32)[:, ::2]
    source[0, 0, 0] = -0.0
    mask = np.ones((6, 8), dtype=np.float32)[:, ::2]
    before = source.copy()
    output = texture.apply(source, mask, -0.0, 0.0, reference_rgb=source, radius=4)
    assert output.flags.owndata and output.flags.c_contiguous and output.flags.writeable
    assert not np.shares_memory(output, source)
    assert np.array_equal(output.view(np.uint32), source.view(np.uint32))
    assert np.array_equal(before.view(np.uint32), source.view(np.uint32))


def test_original_reference_controls_radius_and_pixel_contract_are_strict(protocol):
    source = np.full((5, 5, 3), 0.3, dtype=np.float32)
    mask = np.ones((5, 5), dtype=np.float32)
    with pytest.raises(TypeError):
        texture.apply(source, mask, 0, 0, radius=4)
    for radius in [True, 3, 257, 4.0, np.int32(4)]:
        with pytest.raises(ValueError):
            texture.apply(source, mask, 0, 0, reference_rgb=source, radius=radius)
    for amount, clarity in [(True, 0), (0, True), (1.01, 0), (-1.01, 0),
                            (0, -0.01), (0, 1.01), (float('nan'), 0), (0, 10**1000)]:
        with pytest.raises(ValueError):
            texture.apply(source, mask, amount, clarity, reference_rgb=source, radius=4)
    for bad in [source.astype(np.float64), source[..., :2], np.zeros((4, 5, 3), dtype=np.float32)]:
        with pytest.raises(ValueError):
            texture.apply(source, mask, 0, 0, reference_rgb=bad, radius=4)
    for bad in [float('nan'), float('inf'), -0.01, 1.01]:
        reference = source.copy()
        reference[0, 0, 0] = bad
        with pytest.raises(ValueError, match='finite SDR'):
            texture.apply(source, mask, 0, 0, reference_rgb=reference, radius=4)
        invalid_mask = mask.copy()
        invalid_mask[0, 0] = bad
        with pytest.raises(ValueError, match='finite SDR'):
            texture.apply(source, invalid_mask, 0, 0, reference_rgb=source, radius=4)


def test_memory_estimate_pure_and_documented_peak(monkeypatch):
    monkeypatch.setattr(texture, 'native', lambda: pytest.fail('Estimate must not load native'))
    monkeypatch.setattr(texture, '_available_estimate', lambda: pytest.fail('Estimate must not read cgroup'))
    assert texture.memory_estimate((4000, 6000)) == 112 * 24_000_000 + 8 * 1024**2
    assert texture.NATIVE_SCRATCH_BYTES_PER_PIXEL == 72
    assert texture.TOTAL_BYTES_PER_PIXEL == 140
    for shape in [(6000, 6000), (4000, 8000)]:
        with pytest.raises(MemoryError):
            texture.memory_estimate(shape)
    for shape in [(3, 3, 3), (True, 3), (0, 3), (3, 65_537)]:
        with pytest.raises(ValueError):
            texture.memory_estimate(shape)


def test_preflight_cancellation_resource_and_unavailable_core_never_fall_back(monkeypatch):
    source = np.full((5, 5, 3), 0.3, dtype=np.float32)
    mask = np.ones((5, 5), dtype=np.float32)
    monkeypatch.setattr(texture, 'native', lambda: pytest.fail('Must refuse before loading'))
    with pytest.raises(InterruptedError):
        texture.apply(source, mask, 1, 1, reference_rgb=source, radius=4, cancelled=lambda: True)
    monkeypatch.setattr(texture, '_available_estimate', lambda: 0)
    with pytest.raises(MemoryError):
        texture.apply(source, mask, 1, 1, reference_rgb=source, radius=4)
    def absent():
        raise RuntimeError('Skin texture Rust core is not installed; no fallback was applied')
    monkeypatch.setattr(texture, 'native', absent)
    monkeypatch.setattr(texture, '_available_estimate', lambda: 16 * 1024**3)
    assert not texture.available()
    cap = state.capability()
    assert set(cap) == {'skin_texture_available', 'skin_texture_reason'}
    assert not cap['skin_texture_available'] and cap['skin_texture_reason']
    with pytest.raises(RuntimeError, match='no fallback'):
        texture.apply(source, mask, 0, 0, reference_rgb=source, radius=4)


def test_callback_errors_reraise_outside_ffi_and_native_codes_are_explicit():
    def broken():
        raise LookupError('callback failed')
    callback, errors = texture._callback(broken)
    assert callback(None) == 1
    with pytest.raises(LookupError, match='callback failed'):
        texture._result(4, lambda: False, errors)
    for code, exception in [(1, ValueError), (2, ValueError), (3, ValueError),
                            (4, InterruptedError), (5, MemoryError), (6, RuntimeError)]:
        with pytest.raises(exception):
            texture._result(code, lambda: False, [])


def test_invalid_or_protected_output_is_discarded(protocol, monkeypatch):
    source = np.full((5, 5, 3), 0.3, dtype=np.float32)
    mask = np.ones((5, 5), dtype=np.float32)
    mask[0, 0] = 0.0
    class CorruptProtocol(CopyOnlyProtocol):
        def lrt_skin_texture_apply_v1(self, *args):
            result = super().lrt_skin_texture_apply_v1(*args)
            output = args[11]
            output[0] = 0.7
            return result
    monkeypatch.setattr(texture, 'native', lambda: CorruptProtocol())
    with pytest.raises(RuntimeError, match='unsupported'):
        texture.apply(source, mask, 1, 1, reference_rgb=source, radius=4)
    class NonfiniteProtocol(CopyOnlyProtocol):
        def lrt_skin_texture_apply_v1(self, *args):
            result = super().lrt_skin_texture_apply_v1(*args)
            args[11][4] = float('nan')
            return result
    monkeypatch.setattr(texture, 'native', lambda: NonfiniteProtocol())
    with pytest.raises(RuntimeError, match='invalid SDR'):
        texture.apply(source, mask, 1, 1, reference_rgb=source, radius=4)
