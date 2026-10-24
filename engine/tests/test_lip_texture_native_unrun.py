# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored state/wrapper fixtures, entirely UNRUN. No product import executed.

The copy protocol exercises boundary ownership/error paths, not the algorithm;
it is never a runtime fallback. Real numerical/ABI fixtures live in the original
Rust crate. A separately authorized installed-library smoke fixture is below.
"""
import ctypes

import numpy as np
import pytest

from lumaretouch_engine import lip_texture_native as texture
from lumaretouch_engine import lip_texture_state as state


class CopyOnlyProtocol:
    def lrt_lip_texture_apply_v1(self, source, source_len, coverage, coverage_len,
                               width, height, amount, across_x, across_y, radius,
                               output, output_len, cancel, context):
        assert source_len == output_len == 3 * width * height
        assert coverage_len == width * height
        assert 1 <= radius <= 12
        assert abs(np.hypot(across_x, across_y) - 1) <= 0.0001
        if cancel(context):
            return 4
        ctypes.memmove(output, source, source_len * ctypes.sizeof(ctypes.c_float))
        return 0


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setattr(texture, '_available_estimate', lambda: 16 * 1024**3)
    monkeypatch.setattr(texture, 'native', lambda: CopyOnlyProtocol())


def inputs():
    return np.full((9, 11, 3), 0.3, np.float32), np.ones((9, 11), np.float32)


def test_exact_portable_intent_and_capability_names(monkeypatch):
    assert state.OP == 'lnx.lip_texture.v1'
    assert state.VERSION == 1
    assert state.CONTROL_ID == 'LNX-REF-PC-32464-C-b6315c40ca'
    assert state.neutral() == {'version': 1, 'amount': 0.0}
    assert state.check(None) == state.neutral()
    assert state.check({'version': 1, 'amount': 1}) == {'version': 1, 'amount': 1.0}
    assert not state.active({'version': 1, 'amount': -0.0})
    assert state.active({'version': 1, 'amount': 0.5})
    for bad in [True, float('nan'), float('inf'), -0.01, 1.01, 10**1000, '0.5']:
        with pytest.raises(ValueError):
            state.check({'version': 1, 'amount': bad})
    for bad in [{'version': True, 'amount': 0}, {'version': 2, 'amount': 0},
                {'version': 1}, {'version': 1, 'amount': 0, 'radius': 1},
                {'version': 1, 'amount': 0, 'mask': []}]:
        with pytest.raises(ValueError):
            state.check(bad)
    monkeypatch.setattr(texture, 'available', lambda: False)
    assert set(state.capability()) == {'lip_texture_available', 'lip_texture_reason'}
    assert not state.capability()['lip_texture_available']
    assert state.capability()['lip_texture_reason']
    monkeypatch.setattr(texture, 'available', lambda: True)
    assert state.capability() == {'lip_texture_available': True, 'lip_texture_reason': None}


def test_neutral_strided_snapshots_are_independent_and_preserve_rgb16_low_bits(protocol):
    codes = np.arange(9 * 22 * 3, dtype=np.uint16).reshape(9, 22, 3) + 30000
    source = (codes.astype(np.float32) / np.float32(65535))[:, ::2]
    source[0, 0, 0] = -0.0
    mask = np.ones((9, 22), np.float32)[:, ::2]
    before = source.copy()
    result = texture.apply(source, mask, -0.0, across=(1.0, 0.0), radius=1)
    assert result.dtype == np.float32 and result.flags.owndata and result.flags.c_contiguous
    assert not np.shares_memory(result, source)
    assert not np.shares_memory(result, mask)
    assert np.array_equal(result.view(np.uint32), before.view(np.uint32))
    assert np.array_equal(source.view(np.uint32), before.view(np.uint32))
    assert len(np.unique(result[1:].reshape(-1))) > 256


def test_snapshot_source_and_coverage_are_separate_even_when_inputs_alias(protocol, monkeypatch):
    source, _ = inputs()
    mask = source[:, :, 0]
    expected_source, expected_mask = source.copy(), mask.copy()

    class Observe(CopyOnlyProtocol):
        def lrt_lip_texture_apply_v1(self, *args):
            rgb, count, cov, n, *_ = args
            assert ctypes.addressof(rgb.contents) != source.ctypes.data
            assert ctypes.addressof(cov.contents) != mask.ctypes.data
            assert ctypes.addressof(rgb.contents) != ctypes.addressof(cov.contents)
            assert np.array_equal(np.ctypeslib.as_array(rgb, (count,)), expected_source.ravel())
            assert np.array_equal(np.ctypeslib.as_array(cov, (n,)), expected_mask.ravel())
            # Original mutation after snapshot completion cannot change the inputs
            # retained by the native call. Real callers must not mutate mid-copy.
            source.fill(0.9)
            return super().lrt_lip_texture_apply_v1(*args)

    monkeypatch.setattr(texture, 'native', lambda: Observe())
    result = texture.apply(source, mask, 0, across=(1, 0), radius=1)
    assert np.array_equal(result, expected_source)


def test_strict_amount_axis_radius_alpha_hdr_and_dtype_even_when_neutral(protocol):
    source, mask = inputs()
    for amount in [True, np.bool_(False), float('nan'), float('inf'), 10**1000, -0.01, 1.01]:
        with pytest.raises(ValueError):
            texture.apply(source, mask, amount, across=(1, 0), radius=1)
    for axis in [None, (1,), (1, 0, 0), (True, 0), (0, 0), (2, 0), (float('nan'), 0), np.array([1, 0])]:
        with pytest.raises(ValueError):
            texture.apply(source, mask, 0, across=axis, radius=1)
    for radius in [True, 0, 13, 1.0, np.int64(1)]:
        with pytest.raises(ValueError):
            texture.apply(source, mask, 0, across=(1, 0), radius=radius)
    for bad in [source.astype(np.float64), source.astype(np.uint16), source[:, :, :2],
                np.zeros((9, 11, 4), np.float32), source.astype('>f4')]:
        with pytest.raises(ValueError):
            texture.apply(bad, mask, 0, across=(1, 0), radius=1)
    for bad_value in [float('nan'), float('inf'), -0.01, 1.01]:
        bad = source.copy()
        bad[0, 0, 0] = bad_value
        with pytest.raises(ValueError):
            texture.apply(bad, mask, 0, across=(1, 0), radius=1)
        bad_mask = mask.copy()
        bad_mask[0, 0] = bad_value
        with pytest.raises(ValueError):
            texture.apply(source, bad_mask, 0, across=(1, 0), radius=1)
    with pytest.raises(TypeError):
        texture.apply(source, mask, 0, across=(1, 0), radius=1, cancelled=False)
    with pytest.raises(TypeError):
        texture.apply(source, mask, 0, radius=1)


def test_memory_estimate_is_pure_and_global_limit_is_not_relaxed(monkeypatch):
    def forbidden():
        raise AssertionError('Pure estimate must not load native or inspect live memory')
    monkeypatch.setattr(texture, 'native', forbidden)
    monkeypatch.setattr(texture, '_available_estimate', forbidden)
    assert texture.MAX_PIXELS == 32_000_000
    assert texture.memory_estimate((3, 4)) == 12 * 56 + 8 * 1024**2
    assert texture.memory_estimate((8000, 4000)) == 32_000_000 * 56 + 8 * 1024**2
    for bad in [None, (3,), (3, 4, 3), (True, 3), (0, 3), (-1, 3), (65537, 1), (1.0, 3)]:
        with pytest.raises(ValueError):
            texture.memory_estimate(bad)
    with pytest.raises(MemoryError):
        texture.memory_estimate((8001, 4000))


def test_memory_refusal_precedes_all_snapshot_allocation_and_loading(monkeypatch):
    source, mask = inputs()
    monkeypatch.setattr(texture, '_available_estimate', lambda: 0)
    monkeypatch.setattr(texture, '_snapshot', lambda *args: pytest.fail('Snapshot after refusal'))
    monkeypatch.setattr(texture, 'native', lambda: pytest.fail('Load after refusal'))
    with pytest.raises(MemoryError):
        texture.apply(source, mask, 0, across=(1, 0), radius=1)


def test_cancelled_or_failed_native_output_is_private_and_discarded(protocol, monkeypatch):
    source, mask = inputs()
    before = source.copy()

    class Failure(CopyOnlyProtocol):
        def __init__(self, code):
            self.code = code

        def lrt_lip_texture_apply_v1(self, *args):
            args[10][0] = 0.75
            return self.code

    for code, error in [(1, ValueError), (2, ValueError), (3, ValueError),
                        (4, InterruptedError), (5, MemoryError), (6, RuntimeError)]:
        monkeypatch.setattr(texture, 'native', lambda code=code: Failure(code))
        with pytest.raises(error):
            texture.apply(source, mask, 1, across=(1, 0), radius=1)
        assert np.array_equal(source, before)


def test_callback_exception_is_not_swallowed_by_ctypes(protocol, monkeypatch):
    source, mask = inputs()
    phase = [False]
    failure = LookupError('intentional cancellation-provider error')

    def cancelled():
        if phase[0]:
            raise failure
        return False

    class CallbackFailure(CopyOnlyProtocol):
        def lrt_lip_texture_apply_v1(self, *args):
            phase[0] = True
            assert args[12](args[13]) == 1
            return 4

    monkeypatch.setattr(texture, 'native', lambda: CallbackFailure())
    with pytest.raises(LookupError) as raised:
        texture.apply(source, mask, 1, across=(1, 0), radius=1, cancelled=cancelled)
    assert raised.value is failure


def test_invalid_native_output_and_protected_pixel_changes_are_rejected(protocol, monkeypatch):
    source, mask = inputs()

    class Invalid(CopyOnlyProtocol):
        def __init__(self, value):
            self.value = value

        def lrt_lip_texture_apply_v1(self, *args):
            super().lrt_lip_texture_apply_v1(*args)
            args[10][0] = self.value
            return 0

    for value in [float('nan'), 1.1, 0.1, 0.4]:
        monkeypatch.setattr(texture, 'native', lambda value=value: Invalid(value))
        with pytest.raises(RuntimeError):
            texture.apply(source, mask, 0, across=(1, 0), radius=1)
    monkeypatch.setattr(texture, 'native', lambda: Invalid(0.1))
    with pytest.raises(RuntimeError, match='darkening'):
        texture.apply(source, mask, 1, across=(1, 0), radius=1)
    mask[0, 0] = 0
    monkeypatch.setattr(texture, 'native', lambda: Invalid(0.4))
    with pytest.raises(RuntimeError):
        texture.apply(source, mask, 1, across=(1, 0), radius=1)


def test_missing_library_is_truthful_and_neutral_does_not_sneak_in_a_fallback(monkeypatch):
    texture.native.cache_clear()
    monkeypatch.setattr(texture.Path, 'is_file', lambda _path: False)
    monkeypatch.setattr(texture, '_available_estimate', lambda: 16 * 1024**3)
    assert not texture.available()
    source, mask = inputs()
    with pytest.raises(RuntimeError, match='not installed'):
        texture.apply(source, mask, 0, across=(1, 0), radius=1)
    texture.native.cache_clear()


def test_installed_native_chromatic_smoke_no_build_no_download():
    if not texture.available():
        pytest.skip('Authored fixture requires separately built ABI1 library; no runtime build')
    linear = np.empty((41, 41, 3), np.float32)
    linear[:] = [0.34, 0.11, 0.07]
    linear[:, 20] *= np.float32(0.82)
    source = np.where(linear <= 0.0031308, 12.92 * linear,
                      1.055 * linear ** (1.0 / 2.4) - 0.055).astype(np.float32)
    out = texture.apply(source, np.ones((41, 41), np.float32), 1,
                        across=(1, 0), radius=1)
    assert np.all(out[20, 20] > source[20, 20])
    assert np.array_equal(out[:, :19], source[:, :19])
