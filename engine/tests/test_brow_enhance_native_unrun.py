# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored state/native-boundary fixtures. ALL UNRUN, no product imports executed.

The copy-only protocol tests snapshots/errors only. Actual original numerical
behavior fixtures are in core/brow_enhance/tests.rs; those also remain UNRUN.
"""
import ctypes

import numpy as np
import pytest

from lumaretouch_engine import brow_enhance_native as brow
from lumaretouch_engine import brow_enhance_state as state


class CopyOnlyProtocol:
    def lrt_brow_enhance_apply_v1(self, source, source_len, target, target_len,
                                 reference, reference_len, width, height, amount,
                                 radius, output, output_len, cancel, context):
        assert source_len == output_len == 3 * width * height
        assert target_len == reference_len == width * height
        assert 2 <= radius <= 128
        if cancel(context):
            return 4
        ctypes.memmove(output, source, source_len * ctypes.sizeof(ctypes.c_float))
        return 0


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setattr(brow, '_available_estimate', lambda: 16 * 1024**3)
    monkeypatch.setattr(brow, 'native', lambda: CopyOnlyProtocol())


def arrays():
    source = np.full((6, 8, 3), 0.3, dtype=np.float32)
    target = np.zeros((6, 8), dtype=np.float32)
    reference = np.zeros((6, 8), dtype=np.float32)
    target[3:5, 2:6] = 1
    reference[:2] = 1
    return source, target, reference


def test_exact_recipe_signed_sides_and_independent_neutral_objects():
    assert state.OP == 'lnx.brow_enhance.v1'
    assert state.CONTROL_ID == 'LNX-REF-PC-32471-C-18765fa8ea'
    expected = {'version': 1, 'linked': True, 'left': 0.0, 'right': 0.0}
    assert state.neutral() == state.check(None) == expected
    assert state.neutral() is not state.neutral()
    assert state.active({'version': 1, 'linked': False, 'left': -1, 'right': 1})
    assert not state.active({'version': 1, 'linked': False, 'left': -0.0, 'right': 0})
    assert state.preset(expected) == expected and state.preset(expected) is not expected
    assert state.side_active({'version': 1, 'linked': False, 'left': -0.2, 'right': 0}, 'left')
    with pytest.raises(ValueError):
        state.side_active(expected, 'screen-left')


def test_recipe_rejects_extra_keys_wrong_types_versions_and_linked_disagreement():
    neutral = state.neutral()
    for bad in [True, float('nan'), float('inf'), -1.01, 1.01, 10**1000, np.float32(0.2), '0.2']:
        with pytest.raises(ValueError):
            state.check({**neutral, 'linked': False, 'left': bad})
    for bad in [{**neutral, 'version': True}, {**neutral, 'version': 2},
                {**neutral, 'linked': 1}, {**neutral, 'radius': 3},
                {**neutral, 'source_hash': 'not-portable'}, {'version': 1},
                {**neutral, 'left': 0.2, 'right': 0.3}, []]:
        with pytest.raises(ValueError):
            state.check(bad)


def test_neutral_strided_snapshot_is_owned_and_bit_exact(protocol):
    source, target, reference = arrays()
    source[0, 0, 0] = -0.0
    source, target, reference = source[:, ::2], target[:, ::2], reference[:, ::2]
    before = source.copy()
    out = brow.apply(source, target, -0.0, reference_coverage=reference, radius=4)
    assert out.flags.c_contiguous and out.flags.owndata
    assert np.array_equal(out.view(np.uint32), source.view(np.uint32))
    assert np.array_equal(before.view(np.uint32), source.view(np.uint32))
    assert not np.shares_memory(source, out)


def test_mandatory_reference_and_strict_shape_dtype_radius_amount(protocol):
    source, target, reference = arrays()
    with pytest.raises(TypeError):
        brow.apply(source, target, 0, radius=4)
    for radius in [True, 1, 129, 3.0, np.int32(3)]:
        with pytest.raises(ValueError):
            brow.apply(source, target, 0, reference_coverage=reference, radius=radius)
    for amount in [True, np.bool_(True), float('nan'), float('inf'), 1.01, -1.01, 10**1000, '0']:
        with pytest.raises(ValueError):
            brow.apply(source, target, amount, reference_coverage=reference, radius=4)
    for bad in [reference.astype(np.float64), reference[1:], reference[..., None], reference.tolist()]:
        with pytest.raises(ValueError):
            brow.apply(source, target, 0, reference_coverage=bad, radius=4)
    for bad in [source.astype(np.float64), source[..., :2], source[..., :1], source.tolist()]:
        with pytest.raises(ValueError):
            brow.apply(bad, target, 0, reference_coverage=reference, radius=4)


def test_nonfinite_and_out_of_sdr_are_rejected_even_neutral(protocol):
    for position in range(3):
        for bad in [float('nan'), float('inf'), -0.01, 1.01]:
            inputs = list(arrays())
            inputs[position].flat[0] = bad
            with pytest.raises(ValueError, match='finite SDR'):
                brow.apply(inputs[0], inputs[1], 0, reference_coverage=inputs[2], radius=4)


def test_overlap_is_rejected_before_native_even_neutral(monkeypatch):
    source, target, reference = arrays()
    reference[3, 2] = 0.001
    monkeypatch.setattr(brow, '_available_estimate', lambda: 16 * 1024**3)
    monkeypatch.setattr(brow, 'native', lambda: pytest.fail('Overlap must fail before loading'))
    with pytest.raises(ValueError, match='disjoint'):
        brow.apply(source, target, 0, reference_coverage=reference, radius=4)


def test_memory_estimate_is_pure_and_keeps_32m_cap(monkeypatch):
    monkeypatch.setattr(brow, 'native', lambda: pytest.fail('No load during estimate'))
    monkeypatch.setattr(brow, '_available_estimate', lambda: pytest.fail('No live read during estimate'))
    assert brow.memory_estimate((4000, 6000)) == 76 * 24_000_000 + 8 * 1024**2
    assert brow.memory_estimate((4000, 8000)) == 76 * 32_000_000 + 8 * 1024**2
    with pytest.raises(MemoryError):
        brow.memory_estimate((6000, 6000))
    for shape in [(True, 3), (0, 3), (3, 3, 3), (65_537, 1), ('3', 3)]:
        with pytest.raises(ValueError):
            brow.memory_estimate(shape)


def test_resource_and_initial_cancellation_refuse_before_native(monkeypatch):
    source, target, reference = arrays()
    monkeypatch.setattr(brow, 'native', lambda: pytest.fail('Must refuse before loading'))
    with pytest.raises(InterruptedError):
        brow.apply(source, target, 1, reference_coverage=reference, radius=4, cancelled=lambda: True)
    monkeypatch.setattr(brow, '_available_estimate', lambda: 0)
    with pytest.raises(MemoryError):
        brow.apply(source, target, 1, reference_coverage=reference, radius=4)
    with pytest.raises(TypeError):
        brow.apply(source, target, 0, reference_coverage=reference, radius=4, cancelled=False)


def test_callback_exception_is_reraised_outside_ffi():
    def broken():
        raise LookupError('caller callback failed')
    callback, errors = brow._callback(broken)
    assert callback(None) == 1
    assert callback(None) == 1
    assert len(errors) == 1
    with pytest.raises(LookupError, match='caller callback failed'):
        brow._result(4, lambda: False, errors)


@pytest.mark.parametrize('code,kind', [(1, ValueError), (2, ValueError), (3, ValueError),
                                      (4, InterruptedError), (5, MemoryError),
                                      (6, RuntimeError), (7, ValueError)])
def test_native_refusal_never_returns_private_output(monkeypatch, code, kind):
    class Refusal:
        def lrt_brow_enhance_apply_v1(self, *args):
            args[10][0] = 0.9  # Deliberate invalid private scratch, never published.
            return code
    source, target, reference = arrays()
    before = source.copy()
    monkeypatch.setattr(brow, 'native', lambda: Refusal())
    monkeypatch.setattr(brow, '_available_estimate', lambda: 16 * 1024**3)
    with pytest.raises(kind):
        brow.apply(source, target, 1, reference_coverage=reference, radius=4)
    assert np.array_equal(source.view(np.uint32), before.view(np.uint32))


def test_bad_native_sdr_protection_and_sign_are_rejected(monkeypatch):
    for bad, where in [(float('nan'), 0), (1.01, 0), (0.2, 0), (0.4, 3*(3*8+2))]:
        class Corrupt(CopyOnlyProtocol):
            def lrt_brow_enhance_apply_v1(self, *args):
                super().lrt_brow_enhance_apply_v1(*args)
                args[10][where] = bad
                return 0
        source, target, reference = arrays()
        monkeypatch.setattr(brow, 'native', lambda: Corrupt())
        monkeypatch.setattr(brow, '_available_estimate', lambda: 16 * 1024**3)
        with pytest.raises(RuntimeError):
            brow.apply(source, target, 1, reference_coverage=reference, radius=4)


def test_native_cannot_mutate_original_inputs_through_independent_snapshots(monkeypatch):
    class SnapshotProtocol(CopyOnlyProtocol):
        def lrt_brow_enhance_apply_v1(self, *args):
            source_pointer, _, target_pointer, _, reference_pointer = args[:5]
            assert ctypes.addressof(source_pointer.contents) != original.ctypes.data
            assert ctypes.addressof(target_pointer.contents) != target.ctypes.data
            assert ctypes.addressof(reference_pointer.contents) != reference.ctypes.data
            return super().lrt_brow_enhance_apply_v1(*args)
    original, target, reference = arrays()
    monkeypatch.setattr(brow, 'native', lambda: SnapshotProtocol())
    monkeypatch.setattr(brow, '_available_estimate', lambda: 16 * 1024**3)
    out = brow.apply(original, target, 0, reference_coverage=reference, radius=4)
    assert np.array_equal(original.view(np.uint32), out.view(np.uint32))


def test_missing_native_is_explicit_even_when_neutral(monkeypatch):
    def absent():
        raise RuntimeError('Brow enhancement Rust core is not installed; no fallback was applied')
    source, target, reference = arrays()
    monkeypatch.setattr(brow, 'native', absent)
    monkeypatch.setattr(brow, '_available_estimate', lambda: 16 * 1024**3)
    assert not brow.available()
    assert state.capability()['brow_enhance_available'] is False
    assert state.capability()['brow_enhance_reason']
    with pytest.raises(RuntimeError, match='no fallback'):
        brow.apply(source, target, 0, reference_coverage=reference, radius=4)
