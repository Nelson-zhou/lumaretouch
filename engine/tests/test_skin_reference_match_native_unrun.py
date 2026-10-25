# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Neither these fixtures nor product imports were executed.

Protocol doubles test the boundary only, not the original Rust mathematics.
Tests using real_core require a separately authorized, installed native build;
skipped tests are not evidence of numerical acceptance or photographic quality.
"""
import ctypes as C
from dataclasses import FrozenInstanceError, replace
import math
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import skin_reference_match_native as match


def inputs():
    return (np.full((10, 12, 3), (.50, .40, .35), dtype=np.float32),
            np.ones((10, 12), dtype=np.float32),
            np.full((9, 17, 3), (.40, .30, .25), dtype=np.float32),
            np.ones((9, 17), dtype=np.float32))


class Protocol:
    """Identity application double, never an alternative numerical algorithm."""
    def __init__(self):
        self.fit_calls = 0
        self.apply_calls = 0

    def lrt_skin_reference_match_fit_v1(self, reference, reference_len, reference_weight,
                                      reference_weight_len, rw, rh, target, target_len,
                                      target_weight, target_weight_len, tw, th, limits,
                                      limits_len, transform, transform_len, diagnostics,
                                      diagnostics_len, cancel, context):
        self.fit_calls += 1
        assert reference_len == 3 * rw * rh and reference_weight_len == rw * rh
        assert target_len == 3 * tw * th and target_weight_len == tw * th
        assert (limits_len, transform_len, diagnostics_len) == (2, 4, 24)
        assert limits[0] == match.MAX_LOG_LUMINANCE and limits[1] == match.MAX_LOG_CHROMA
        if cancel(context):
            return 4
        transform[:] = (1., .1, .02, -.01)
        diagnostics[:] = (1., float(rw * rh), float(tw * th), float(rw * rh), float(tw * th),
                          float(rw * rh), float(tw * th), -1.9, .12, -.21,
                          -2., .1, -.2, .01, .01, .01, .01, .01, .01,
                          .1, .02, -.01, 0., 1.)
        return 0

    def lrt_skin_reference_match_apply_v1(self, current, current_len, coverage,
                                        coverage_len, width, height, transform,
                                        transform_len, amount, output, output_len,
                                        cancel, context):
        self.apply_calls += 1
        assert current_len == output_len == 3 * width * height
        assert coverage_len == width * height <= match.MAX_APPLY_PIXELS
        assert transform_len == 4 and tuple(transform) == (1., .1, .02, -.01)
        assert 0 < amount <= 1
        if cancel(context):
            return 4
        C.memmove(output, current, output_len * C.sizeof(C.c_float))
        return 0


@pytest.fixture
def protocol(monkeypatch):
    instance = Protocol()
    monkeypatch.setattr(match, 'native', lambda: instance)
    monkeypatch.setattr(match, '_available_estimate', lambda: 16 * 1024**3)
    return instance


@pytest.fixture
def real_core(monkeypatch):
    """A missing build is an explicit skip, never fake native acceptance."""
    try:
        lib = match.native()
    except RuntimeError as error:
        pytest.skip('Original skin-reference native build unavailable: ' + str(error))
    monkeypatch.setattr(match, '_available_estimate', lambda: 16 * 1024**3)
    return lib


def test_exact_header_types_and_all_required_symbols(monkeypatch):
    class Symbol:
        def __init__(self, result=None):
            self.result = result
        def __call__(self):
            return self.result
    library = SimpleNamespace(lrt_skin_reference_match_abi=Symbol(1),
                              lrt_skin_reference_match_fit_v1=Symbol(),
                              lrt_skin_reference_match_apply_v1=Symbol())
    match.native.cache_clear()
    try:
        monkeypatch.setattr(match.Path, 'is_file', lambda self: True)
        monkeypatch.setattr(match.C, 'CDLL', lambda path: library)
        assert match.native() is library and match.available()
        assert library.lrt_skin_reference_match_abi.argtypes == []
        assert library.lrt_skin_reference_match_abi.restype is C.c_uint32
        assert library.lrt_skin_reference_match_fit_v1.argtypes == [
            match.P, C.c_size_t, match.P, C.c_size_t, C.c_size_t, C.c_size_t,
            match.P, C.c_size_t, match.P, C.c_size_t, C.c_size_t, C.c_size_t,
            match.D, C.c_size_t, match.D, C.c_size_t, match.D, C.c_size_t,
            match.CANCEL, C.c_void_p]
        assert library.lrt_skin_reference_match_apply_v1.argtypes == [
            match.P, C.c_size_t, match.P, C.c_size_t, C.c_size_t, C.c_size_t,
            match.D, C.c_size_t, C.c_float, match.P, C.c_size_t, match.CANCEL, C.c_void_p]
        assert library.lrt_skin_reference_match_fit_v1.restype is C.c_int32
        assert library.lrt_skin_reference_match_apply_v1.restype is C.c_int32
        assert match.CANCEL._restype_ is C.c_int32
        assert match.CANCEL._argtypes_ == (C.c_void_p,)
        match.native.cache_clear()
        library.lrt_skin_reference_match_abi.result = 2
        assert not match.available()
        library.lrt_skin_reference_match_abi.result = 1
        del library.lrt_skin_reference_match_apply_v1
        assert not match.available()
    finally:
        match.native.cache_clear()


def test_missing_core_refuses_active_but_neutral_is_exact(monkeypatch):
    match.native.cache_clear()
    try:
        monkeypatch.setattr(match.Path, 'is_file', lambda self: False)
        monkeypatch.setattr(match, '_available_estimate', lambda: 16 * 1024**3)
        assert not match.available()
        with pytest.raises(RuntimeError, match='not installed.*no fallback'):
            match.fit(*inputs())
        current = np.array([[[-0., .3, .4], [1., 0., .7]]], dtype=np.float32)
        before = current.copy()
        output = match.apply(current)
        assert np.array_equal(output.view(np.uint32), before.view(np.uint32))
        assert output.flags.owndata and output.flags.c_contiguous
        assert not np.shares_memory(output, current)
        output.fill(.9)
        assert np.array_equal(current.view(np.uint32), before.view(np.uint32))
    finally:
        match.native.cache_clear()


def test_independent_strided_roi_shapes_and_immutable_tuple_result(protocol):
    reference, reference_weight, target, target_weight = inputs()
    reference, reference_weight = reference[::-1], reference_weight[::-1]
    target, target_weight = target[:, ::-1], target_weight[:, ::-1]
    arrays = (reference, reference_weight, target, target_weight)
    before = [value.copy() for value in arrays]
    result = match.fit(*arrays)
    assert result.reference_shape == (10, 12) and result.target_shape == (9, 17)
    assert type(result.transform) is tuple and len(result.transform) == 4
    assert type(result.diagnostics) is tuple and len(result.diagnostics) == 24
    assert result.checked() is result
    with pytest.raises(FrozenInstanceError):
        result.transform = (1., 0., 0., 0.)
    for value, original in zip(arrays, before):
        assert np.array_equal(value.view(np.uint32), original.view(np.uint32))


def test_each_source_pointer_has_private_snapshot(protocol, monkeypatch):
    arrays = inputs()
    originals = [value.copy() for value in arrays]
    class Inspect(Protocol):
        def lrt_skin_reference_match_fit_v1(self, *args):
            pointers = []
            for index, value, original in zip((0, 2, 6, 8), arrays, originals):
                pointers.append(C.addressof(args[index].contents))
                assert pointers[-1] != value.ctypes.data
                value.fill(.9)
                actual = np.ctypeslib.as_array(args[index], shape=(value.size,))
                assert np.array_equal(actual.view(np.uint32), original.ravel().view(np.uint32))
            assert len(set(pointers)) == 4
            return super().lrt_skin_reference_match_fit_v1(*args)
    monkeypatch.setattr(match, 'native', lambda: Inspect())
    assert match.fit(*arrays).transform == (1., .1, .02, -.01)


@pytest.mark.parametrize('index', range(4))
def test_fit_rejects_every_invalid_source_or_coverage(protocol, index):
    for bad in (math.nan, math.inf, -.01, 1.01):
        arrays = list(inputs())
        arrays[index].flat[0] = bad
        with pytest.raises(ValueError, match='finite SDR'):
            match.fit(*arrays)
    for dtype in (np.float64, '>f4'):
        arrays = list(inputs())
        arrays[index] = arrays[index].astype(dtype)
        with pytest.raises(ValueError):
            match.fit(*arrays)
    arrays = list(inputs())
    arrays[index] = arrays[index].tolist()
    with pytest.raises(ValueError):
        match.fit(*arrays)


def test_neutral_validates_current_and_optional_evidence_without_core(protocol, monkeypatch):
    measured = match.fit(*inputs())
    monkeypatch.setattr(match, 'native', lambda: pytest.fail('Neutral must not load the core'))
    current = np.full((3, 5, 3), .4, dtype=np.float32)
    coverage = np.ones((3, 5), dtype=np.float32)
    assert np.array_equal(match.apply(current, coverage, measured, -0.), current)
    for value in (math.nan, math.inf, -.01, 1.01):
        bad = current.copy()
        bad[0, 0, 0] = value
        with pytest.raises(ValueError):
            match.apply(bad)
        bad_coverage = coverage.copy()
        bad_coverage[0, 0] = value
        with pytest.raises(ValueError):
            match.apply(current, bad_coverage)
    for bad in (current.astype(np.float64), current[..., :2], current[:0], current.tolist()):
        with pytest.raises(ValueError):
            match.apply(bad)
    with pytest.raises(ValueError):
        match.apply(current, np.zeros((1, 1), dtype=np.float32))
    with pytest.raises(ValueError):
        match.apply(current, measured_fit=replace(measured, transform=(1., math.nan, 0., 0.)))
    with pytest.raises(ValueError):
        match.apply(current, measured_fit=(1., 0., 0., 0.))


def test_active_missing_evidence_is_not_a_neutral_success(protocol):
    current = inputs()[0]
    with pytest.raises(ValueError, match='requires reviewed coverage'):
        match.apply(current, amount=.5)
    with pytest.raises(ValueError):
        match.apply(current, inputs()[1], amount=.5)
    assert protocol.apply_calls == 0


def test_limits_controls_and_callbacks_are_strict(protocol):
    for limits in ((True, .1), (math.inf, .1), (-.1, .1), (.1, .36), (.7, .1), (.1,), None):
        with pytest.raises(ValueError):
            match.fit(*inputs(), limits=limits)
    for amount in (True, math.nan, math.inf, -.01, 1.01, 10**1000):
        with pytest.raises(ValueError):
            match.apply(inputs()[0], amount=amount)
    with pytest.raises(TypeError):
        match.fit(*inputs(), cancelled=False)
    with pytest.raises(TypeError):
        match.apply(inputs()[0], cancelled=False)


def test_pure_estimators_charge_caller_copies_full_output_and_native_stage(monkeypatch):
    monkeypatch.setattr(match, 'native', lambda: pytest.fail('No native load'))
    monkeypatch.setattr(match, '_available_estimate', lambda: pytest.fail('No live budget probe'))
    assert match.memory_estimate((10, 12), (9, 17)) == 16 * (120 + 153) + 262_144 + 8 * 1024**2
    assert match.memory_estimate((4000, 4000), (4000, 4000)) == 16 * 32_000_000 + 262_144 + 8 * 1024**2
    assert match.application_memory_estimate((10, 12)) == 40 * 120 + 4096 + 8 * 1024**2
    assert match.application_memory_estimate((10, 12), tiled=True, tile_rows=2) == 28 * 120 + 12 * 24 + 4096 + 8 * 1024**2
    assert match.application_memory_estimate((10, 12), neutral=True) == 16 * 120 + 8 * 1024**2
    with pytest.raises(MemoryError):
        match.memory_estimate((4000, 8000), (1, 1))
    with pytest.raises(MemoryError):
        match.application_memory_estimate((1024, 1025))
    with pytest.raises(MemoryError):
        match.application_memory_estimate((8000, 8000), tiled=True)
    for shape in ((0, 1), (1, 65_537), (True, 1), (1., 1), (1, 2, 3)):
        with pytest.raises(ValueError):
            match.memory_estimate(shape, (1, 1))
        with pytest.raises(ValueError):
            match.application_memory_estimate(shape)
    for rows in (0, True, 1., 87_382):
        with pytest.raises(ValueError):
            match.application_memory_estimate((10, 12), tiled=True, tile_rows=rows)


def test_resource_and_cancellation_refuse_before_copy_or_native(monkeypatch):
    monkeypatch.setattr(match, 'native', lambda: pytest.fail('No native call'))
    monkeypatch.setattr(match, '_snapshot', lambda *a: pytest.fail('No snapshot allocation'))
    monkeypatch.setattr(match, '_available_estimate', lambda: 0)
    with pytest.raises(MemoryError):
        match.fit(*inputs())
    with pytest.raises(MemoryError):
        match.apply(inputs()[0])
    with pytest.raises(InterruptedError):
        match.apply(inputs()[0], cancelled=lambda: True)
    monkeypatch.setattr(match, '_available_estimate', lambda: 16 * 1024**3)
    with pytest.raises(MemoryError):
        match.fit(*inputs(), byte_budget=0)
    for budget in (True, -1, 1., '1000'):
        with pytest.raises(ValueError):
            match.apply(inputs()[0], byte_budget=budget)


def test_current_not_source_used_and_all_inputs_are_snapshotted(protocol, monkeypatch):
    measured = match.fit(*inputs())
    current = np.full((4, 5, 3), .67, dtype=np.float32)[:, ::-1]
    coverage = np.ones((4, 5), dtype=np.float32)[:, ::-1]
    before = current.copy()
    before_coverage = coverage.copy()
    class Inspect(Protocol):
        def lrt_skin_reference_match_apply_v1(self, *args):
            assert C.addressof(args[0].contents) != current.ctypes.data
            assert C.addressof(args[2].contents) != coverage.ctypes.data
            current.fill(.2)
            coverage.fill(0.)
            assert np.array_equal(np.ctypeslib.as_array(args[0], shape=(current.size,)), before.ravel())
            assert np.array_equal(np.ctypeslib.as_array(args[2], shape=(coverage.size,)), before_coverage.ravel())
            return super().lrt_skin_reference_match_apply_v1(*args)
    monkeypatch.setattr(match, 'native', lambda: Inspect())
    output = match.apply(current, coverage, measured, .5)
    assert np.array_equal(output, before)
    assert output.flags.owndata and output.flags.c_contiguous
    assert not np.shares_memory(output, current)


def test_tiled_application_borrows_contiguous_snapshots_reuses_one_fit(protocol):
    measured = match.fit(*inputs())
    current = np.full((7, 13, 3), .6, dtype=np.float32)
    coverage = np.ones((7, 13), dtype=np.float32)
    output = match.apply_tiled(current, coverage, measured, .7, tile_rows=2)
    assert protocol.fit_calls == 1 and protocol.apply_calls == 4
    assert np.array_equal(output.view(np.uint32), current.view(np.uint32))
    assert output.flags.owndata and not np.shares_memory(current, output)


def test_later_tile_failure_discards_all_private_work(protocol, monkeypatch):
    measured = match.fit(*inputs())
    current = np.full((7, 13, 3), .6, dtype=np.float32)
    coverage = np.ones((7, 13), dtype=np.float32)
    before = current.copy()
    class LaterFailure(Protocol):
        def lrt_skin_reference_match_apply_v1(self, *args):
            if self.apply_calls == 1:
                return 3
            result = super().lrt_skin_reference_match_apply_v1(*args)
            args[9][0] = .7
            return result
    instance = LaterFailure()
    monkeypatch.setattr(match, 'native', lambda: instance)
    with pytest.raises(ValueError, match='numerical refusal'):
        match.apply_tiled(current, coverage, measured, 1., tile_rows=2)
    assert instance.apply_calls == 1
    assert np.array_equal(current.view(np.uint32), before.view(np.uint32))
    assert np.all(coverage == 1)


@pytest.mark.parametrize('status,exception', [(1, ValueError), (2, ValueError), (3, ValueError),
    (4, InterruptedError), (5, MemoryError), (6, RuntimeError), (7, ValueError),
    (8, ValueError), (9, ValueError), (10, ValueError), (123, ValueError)])
def test_native_statuses_never_become_success(protocol, monkeypatch, status, exception):
    measured = match.fit(*inputs())
    class Refused(Protocol):
        def lrt_skin_reference_match_fit_v1(self, *args):
            return status
        def lrt_skin_reference_match_apply_v1(self, *args):
            return status
    monkeypatch.setattr(match, 'native', lambda: Refused())
    with pytest.raises(exception):
        match.fit(*inputs())
    with pytest.raises(exception):
        match.apply(inputs()[0], inputs()[1], measured, 1.)


def test_callback_exceptions_are_contained_and_preserved():
    calls = []
    def broken():
        calls.append(1)
        raise LookupError('cancel provider failed')
    callback, errors = match._callback(broken)
    assert callback(None) == 1 and callback(None) == 1 and len(calls) == 1
    with pytest.raises(LookupError, match='cancel provider failed'):
        match._result(4, lambda: False, errors)


def test_late_cancellation_discards_native_success(protocol, monkeypatch):
    measured = match.fit(*inputs())
    stopped = [False]
    class Late(Protocol):
        def lrt_skin_reference_match_apply_v1(self, *args):
            result = super().lrt_skin_reference_match_apply_v1(*args)
            stopped[0] = True
            return result
    monkeypatch.setattr(match, 'native', lambda: Late())
    with pytest.raises(InterruptedError):
        match.apply(inputs()[0], inputs()[1], measured, 1., cancelled=lambda: stopped[0])


def test_invalid_native_fit_and_pixel_outputs_are_not_published(protocol, monkeypatch):
    measured = match.fit(*inputs())
    class CorruptFit(Protocol):
        def lrt_skin_reference_match_fit_v1(self, *args):
            result = super().lrt_skin_reference_match_fit_v1(*args)
            args[16][23] = .1
            return result
    monkeypatch.setattr(match, 'native', lambda: CorruptFit())
    with pytest.raises(RuntimeError, match='invalid fit/diagnostics'):
        match.fit(*inputs())
    class CorruptPixel(Protocol):
        def lrt_skin_reference_match_apply_v1(self, *args):
            result = super().lrt_skin_reference_match_apply_v1(*args)
            args[9][0] = math.nan
            return result
    monkeypatch.setattr(match, 'native', lambda: CorruptPixel())
    with pytest.raises(RuntimeError, match='invalid SDR'):
        match.apply(inputs()[0], inputs()[1], measured, 1.)
    class CorruptProtected(Protocol):
        def lrt_skin_reference_match_apply_v1(self, *args):
            result = super().lrt_skin_reference_match_apply_v1(*args)
            args[9][0] = .7
            return result
    monkeypatch.setattr(match, 'native', lambda: CorruptProtected())
    with pytest.raises(RuntimeError, match='protected/neutral'):
        match.apply(inputs()[0], np.zeros((10, 12), dtype=np.float32), measured, 1.)


def test_real_independent_fit_current_application_and_partition_bits(real_core):
    measured = match.fit(*inputs())
    assert measured.transform[1] > 0
    current = np.full((11, 19, 3), (.45, .36, .27), dtype=np.float32)
    current[0, 0] = (-0., 0., 0.)
    current[0, 1] = 1.
    coverage = np.ones((11, 19), dtype=np.float32)
    coverage[2:4, 3:6] = 0.
    before = current.copy()
    full = match.apply(current, coverage, measured, .8)
    tiled = match.apply_tiled(current, coverage, measured, .8, tile_rows=3)
    assert np.array_equal(full.view(np.uint32), tiled.view(np.uint32))
    assert np.array_equal(full[coverage == 0].view(np.uint32), before[coverage == 0].view(np.uint32))
    assert np.array_equal(full[0, :2].view(np.uint32), before[0, :2].view(np.uint32))
    assert not np.array_equal(full[5, 5], before[5, 5])
    assert np.array_equal(current.view(np.uint32), before.view(np.uint32))


def test_real_zero_shift_bit_identity_and_no_evidence_even_with_zero_limits(real_core):
    reference, reference_weight, target, target_weight = inputs()
    target[:] = reference[0, 0]
    measured = match.fit(reference, reference_weight, target, target_weight)
    assert measured.transform == (1., 0., 0., 0.)
    current = np.full((3, 7, 3), (.25, .5, .75), dtype=np.float32)
    current[0, 0, 0] = -0.
    output = match.apply(current, np.ones((3, 7), dtype=np.float32), measured, 1.)
    assert np.array_equal(output.view(np.uint32), current.view(np.uint32))
    with pytest.raises(ValueError, match='selected-reference evidence'):
        match.fit(reference, np.zeros_like(reference_weight), target, target_weight, limits=(0., 0.))
    with pytest.raises(ValueError, match='independent-target evidence'):
        match.fit(reference, reference_weight, target, np.zeros_like(target_weight), limits=(0., 0.))
