# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN boundary/state fixtures; no product imports were executed.

The zero-field/copy-only fake checks protocol and publication, NOT numerical
acceptance. Actual source-reference/guided/chroma/Y mathematics live in authored
Rust fixtures. Real photos, compiler, native ABI and test collection are UNRUN.
"""
import ctypes

import numpy as np
import pytest

from lumaretouch_engine import skin_evenness_native as evenness
from lumaretouch_engine import skin_evenness_state as state


class Protocol:
    def lrt_skin_evenness_prepare_v1(self, source, source_len, coverage, coverage_len,
                                    width, height, amount, radius, output, output_len,
                                    cancel, context):
        assert source_len == 3*width*height
        assert coverage_len == width*height and output_len == 2*width*height
        assert 0 <= amount <= 1 and 4 <= radius <= 256
        if cancel(context):
            return 4
        ctypes.memset(output, 0, output_len*ctypes.sizeof(ctypes.c_float))
        return 0

    def lrt_skin_evenness_apply_v1(self, current, current_len, shift, shift_len,
                                  width, height, output, output_len, cancel, context):
        assert current_len == output_len == 3*width*height
        assert shift_len == 2*width*height
        if cancel(context):
            return 4
        ctypes.memmove(output, current, current_len*ctypes.sizeof(ctypes.c_float))
        return 0


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setattr(evenness, '_available_estimate', lambda: 16*1024**3)
    monkeypatch.setattr(evenness, 'native', lambda: Protocol())


def inputs():
    return (np.full((12, 16, 3), 0.4, dtype=np.float32),
            np.ones((12, 16), dtype=np.float32))


def test_exact_one_axis_portable_intent():
    assert state.OP == 'lnx.skin_evenness.v1'
    assert state.VERSION == 1
    assert state.CONTROL_ID == 'LNX-REF-PC-32465-C-60b7c0e3d1'
    assert state.KEYS == ('amount',)
    assert state.neutral() == {'version': 1, 'amount': 0.0}
    assert state.check(None) == state.neutral()
    assert state.active({'version': 1, 'amount': 0.2})
    assert not state.active({'version': 1, 'amount': -0.0})
    for bad in [True, float('nan'), float('inf'), -0.01, 1.01, 10**1000, np.float32(0.2)]:
        with pytest.raises(ValueError):
            state.check({'version': 1, 'amount': bad})
    for bad in [{'version': True, 'amount': 0}, {'version': 2, 'amount': 0},
                {'version': 1}, {'version': 1, 'amount': 0, 'radius': 4},
                {'version': 1, 'amount': 0, 'reference': [0.4, 0.3]},
                {'version': 1, 'amount': 0, 'skin': {'broad': 1}}]:
        with pytest.raises(ValueError):
            state.check(bad)
    one, two = state.neutral(), state.neutral()
    one['amount'] = 1
    assert two['amount'] == 0


def test_neutral_strided_snapshots_are_independent_owned_and_bit_exact(protocol):
    source, mask = inputs()
    source = source[:, ::2]
    mask = mask[:, ::2]
    source[0, 0, 0] = -0.0
    before = source.copy()
    field = evenness.prepare(source, mask, -0.0, radius=4)
    assert field.shape == (12, 8, 2)
    assert field.dtype == np.float32 and field.flags.owndata and field.flags.c_contiguous
    assert not field.flags.writeable
    assert np.all(field.view(np.uint32) == 0)
    output = evenness.apply(source, field)
    assert output.flags.owndata and output.flags.c_contiguous and output.flags.writeable
    assert not np.shares_memory(output, source)
    assert not np.shares_memory(field, mask)
    assert np.array_equal(output.view(np.uint32), before.view(np.uint32))
    assert np.array_equal(source.view(np.uint32), before.view(np.uint32))


def test_source_and_current_snapshots_are_taken_before_native_call(protocol, monkeypatch):
    source, mask = inputs()
    owned_source, owned_mask = source.copy(), mask.copy()
    class Inspect(Protocol):
        def lrt_skin_evenness_prepare_v1(self, *args):
            assert ctypes.addressof(args[0].contents) != source.ctypes.data
            assert ctypes.addressof(args[2].contents) != mask.ctypes.data
            source.fill(0.8)
            mask.fill(0.0)
            assert np.array_equal(np.ctypeslib.as_array(args[0], shape=(source.size,)), owned_source.ravel())
            assert np.array_equal(np.ctypeslib.as_array(args[2], shape=(mask.size,)), owned_mask.ravel())
            return super().lrt_skin_evenness_prepare_v1(*args)
    monkeypatch.setattr(evenness, 'native', lambda: Inspect())
    field = evenness.prepare(source, mask, 0.0, radius=4)
    assert np.all(field == 0)


def test_strict_amount_radius_image_and_two_component_field_contract(protocol):
    source, mask = inputs()
    for radius in [True, 3, 257, 4.0, np.int32(4)]:
        with pytest.raises(ValueError):
            evenness.prepare(source, mask, 0, radius=radius)
    for amount in [True, float('nan'), float('inf'), -0.01, 1.01, 10**1000]:
        with pytest.raises(ValueError):
            evenness.prepare(source, mask, amount, radius=4)
    for bad in [source.astype(np.float64), source.astype('>f4'), source[..., :2], source.tolist()]:
        with pytest.raises(ValueError):
            evenness.prepare(bad, mask, 0, radius=4)
    for bad in [mask.astype(np.float64), mask[..., None], mask[:3]]:
        with pytest.raises(ValueError):
            evenness.prepare(source, bad, 0, radius=4)
    for bad in [float('nan'), float('inf'), -0.001, 1.001]:
        invalid_source = source.copy()
        invalid_source[0, 0, 0] = bad
        with pytest.raises(ValueError, match='finite SDR'):
            evenness.prepare(invalid_source, mask, 0, radius=4)
        invalid_mask = mask.copy()
        invalid_mask[0, 0] = bad
        with pytest.raises(ValueError, match='finite SDR'):
            evenness.prepare(source, invalid_mask, 0, radius=4)
    for bad in [np.zeros_like(source), np.zeros((*mask.shape, 2), dtype=np.float64),
                np.full((*mask.shape, 2), 0.09, dtype=np.float32),
                np.full((*mask.shape, 2), np.nan, dtype=np.float32)]:
        with pytest.raises(ValueError):
            evenness.apply(source, bad)
    with pytest.raises(TypeError):
        evenness.prepare(source, mask, 0, radius=4, cancelled=False)
    with pytest.raises(TypeError):
        evenness.apply(source, np.zeros((*mask.shape, 2), dtype=np.float32), cancelled=None)


def test_estimates_are_pure_and_keep_independent_32m_ceiling(monkeypatch):
    monkeypatch.setattr(evenness, 'native', lambda: pytest.fail('Must not load native'))
    monkeypatch.setattr(evenness, '_available_estimate', lambda: pytest.fail('Must not query live memory'))
    assert evenness.memory_estimate((4000, 8000)) == 112*32_000_000+8*1024**2
    assert evenness.application_memory_estimate((4000, 8000)) == 44*32_000_000+8*1024**2
    assert evenness.NATIVE_SCRATCH_BYTES_PER_PIXEL == 88
    assert evenness.TOTAL_BYTES_PER_PIXEL == 128
    for shape in [(4001, 8000), (6000, 6000)]:
        with pytest.raises(MemoryError):
            evenness.memory_estimate(shape)
    for shape in [(3, 3, 3), (True, 3), (0, 3), (65_537, 3), (3, 3.0)]:
        with pytest.raises(ValueError):
            evenness.memory_estimate(shape)


def test_preflight_and_missing_core_do_not_fall_back_even_when_neutral(monkeypatch):
    source, mask = inputs()
    shift = np.zeros((*mask.shape, 2), dtype=np.float32)
    monkeypatch.setattr(evenness, 'native', lambda: pytest.fail('Must refuse before native'))
    with pytest.raises(InterruptedError):
        evenness.prepare(source, mask, 1, radius=4, cancelled=lambda: True)
    monkeypatch.setattr(evenness, '_available_estimate', lambda: 0)
    with pytest.raises(MemoryError):
        evenness.prepare(source, mask, 1, radius=4)
    with pytest.raises(MemoryError):
        evenness.apply(source, shift)
    def absent():
        raise RuntimeError('Skin evenness Rust core is not installed; no fallback was applied')
    monkeypatch.setattr(evenness, 'native', absent)
    monkeypatch.setattr(evenness, '_available_estimate', lambda: 16*1024**3)
    assert not evenness.available()
    cap = state.capability()
    assert set(cap) == {'skin_evenness_available', 'skin_evenness_reason'}
    assert not cap['skin_evenness_available'] and cap['skin_evenness_reason']
    with pytest.raises(RuntimeError, match='no fallback'):
        evenness.prepare(source, mask, 0, radius=4)
    with pytest.raises(RuntimeError, match='no fallback'):
        evenness.apply(source, shift)


def test_callback_exceptions_and_distinct_reference_context_refusals():
    def broken():
        raise LookupError('callback failed')
    callback, errors = evenness._callback(broken)
    assert callback(None) == 1 and callback(None) == 1
    with pytest.raises(LookupError, match='callback failed'):
        evenness._result(4, lambda: False, errors)
    for code, expected in [(1, ValueError), (2, ValueError), (3, ValueError),
                           (4, InterruptedError), (5, MemoryError), (6, RuntimeError)]:
        with pytest.raises(expected):
            evenness._result(code, lambda: False, [])
    with pytest.raises(ValueError, match='own-face source reference'):
        evenness._result(7, lambda: False, [])
    with pytest.raises(ValueError, match='guided context'):
        evenness._result(8, lambda: False, [])


def test_corrupt_prepared_field_is_discarded(protocol, monkeypatch):
    source, mask = inputs()
    mask[0, 0] = 0.0
    class Corrupt(Protocol):
        def lrt_skin_evenness_prepare_v1(self, *args):
            status = super().lrt_skin_evenness_prepare_v1(*args)
            args[8][0] = 0.02
            return status
    monkeypatch.setattr(evenness, 'native', lambda: Corrupt())
    for amount in [0, 1]:
        with pytest.raises(RuntimeError, match='unsupported'):
            evenness.prepare(source, mask, amount, radius=4)
    class Unbounded(Protocol):
        def lrt_skin_evenness_prepare_v1(self, *args):
            status = super().lrt_skin_evenness_prepare_v1(*args)
            args[8][2] = 0.09
            args[8][3] = 0.09
            return status
    monkeypatch.setattr(evenness, 'native', lambda: Unbounded())
    with pytest.raises(RuntimeError, match='unbounded'):
        evenness.prepare(source, mask, 1, radius=4)


def test_current_luminance_and_neutral_bits_are_independently_checked(protocol, monkeypatch):
    source, mask = inputs()
    shift = np.zeros((*mask.shape, 2), dtype=np.float32)
    class Corrupt(Protocol):
        def lrt_skin_evenness_apply_v1(self, *args):
            status = super().lrt_skin_evenness_apply_v1(*args)
            args[6][0] = 0.8
            return status
    monkeypatch.setattr(evenness, 'native', lambda: Corrupt())
    before = source.copy()
    with pytest.raises(RuntimeError, match='neutral'):
        evenness.apply(source, shift)
    shift[0, 0] = [0.02, 0.01]
    with pytest.raises(RuntimeError, match='current linear luminance'):
        evenness.apply(source, shift)
    assert np.array_equal(source, before)
    class Nonfinite(Protocol):
        def lrt_skin_evenness_apply_v1(self, *args):
            status = super().lrt_skin_evenness_apply_v1(*args)
            args[6][0] = float('nan')
            return status
    monkeypatch.setattr(evenness, 'native', lambda: Nonfinite())
    with pytest.raises(RuntimeError, match='invalid SDR'):
        evenness.apply(source, shift)


def test_late_cancellation_never_publishes_private_native_result(protocol, monkeypatch):
    source, mask = inputs()
    shift = np.zeros((*mask.shape, 2), dtype=np.float32)
    cancel = [False]
    class Late(Protocol):
        def lrt_skin_evenness_apply_v1(self, *args):
            result = super().lrt_skin_evenness_apply_v1(*args)
            cancel[0] = True
            return result
    monkeypatch.setattr(evenness, 'native', lambda: Late())
    before = source.copy()
    with pytest.raises(InterruptedError):
        evenness.apply(source, shift, cancelled=lambda: cancel[0])
    assert np.array_equal(source, before)
