# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN protocol and scalar-intent fixtures, never imported here.

Zero-field protocol doubles test ownership/boundaries, not chromatic mathematics
or native parity. Original numerical and pre-refactor parity fixtures live in
core/skin_evenness/tests.rs and also remain uncompiled and unexecuted.
"""
import ctypes
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import body_face_match_native as match
from lumaretouch_engine import body_face_match_state as state
from lumaretouch_engine import body_face_match_project as project
from lumaretouch_engine import skin_evenness_native as original


class Protocol:
    def lrt_body_face_match_prepare_v1(self, body, body_len, body_weight, body_weight_len,
                                      body_width, body_height, face, face_len,
                                      face_weight, face_weight_len, face_width, face_height,
                                      amount, radius, output, output_len, cancel, context):
        assert body_len == 3*body_width*body_height
        assert body_weight_len == body_width*body_height
        assert face_len == 3*face_width*face_height
        assert face_weight_len == face_width*face_height
        assert output_len == 2*body_width*body_height
        assert 0 <= amount <= 1 and 4 <= radius <= 256
        if cancel(context):
            return 4
        ctypes.memset(output, 0, output_len*ctypes.sizeof(ctypes.c_float))
        return 0


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setattr(match, '_available_estimate', lambda: 16*1024**3)
    monkeypatch.setattr(match, 'native', lambda: Protocol())


def inputs():
    return (np.full((16, 24, 3), 0.4, dtype=np.float32),
            np.ones((16, 24), dtype=np.float32),
            np.full((9, 13, 3), 0.5, dtype=np.float32),
            np.ones((9, 13), dtype=np.float32))


def test_distinct_portable_scalar_intent_rejects_reference_and_source_data():
    assert state.OP == 'lnx.body_face_match.v1'
    assert state.VERSION == 1 and state.CONTROL_ID == 'LNX-REF-PC-32465-C-d8b09012a9'
    assert state.KEYS == ('amount',)
    assert state.check(None) == state.neutral() == {'version': 1, 'amount': 0.0}
    assert state.active({'version': 1, 'amount': .2})
    assert not state.active({'version': 1, 'amount': -0.0})
    for bad in [True, float('nan'), float('inf'), -.01, 1.01, 10**1000, np.float32(.2)]:
        with pytest.raises(ValueError):
            state.check({'version': 1, 'amount': bad})
    for bad in [{'version': True, 'amount': 0}, {'version': 2, 'amount': 0},
                {'version': 1}, {'version': 1, 'amount': 0, 'radius': 4},
                {'version': 1, 'amount': 0, 'face_reference': [0.3, 0.2]},
                {'version': 1, 'amount': 0, 'body_mask': []}]:
        with pytest.raises(ValueError):
            state.check(bad)
    one, two = state.neutral(), state.neutral()
    one['amount'] = 1
    assert two['amount'] == 0
    project.validate_leaf('/amount', .25)
    for path in ['/radius', '/face_reference', '/source', '/body_mask']:
        with pytest.raises(ValueError):
            project.validate_leaf(path, .25)


def test_two_distinct_strided_grids_produce_only_readonly_owned_body_field(protocol):
    body, body_weight, face, face_weight = inputs()
    body, body_weight = body[:, ::2], body_weight[:, ::2]
    face, face_weight = face[::-1], face_weight[::-1]
    snapshots = [a.copy() for a in (body, body_weight, face, face_weight)]
    field = match.prepare(body, body_weight, face, face_weight, 0, radius=4)
    assert field.shape == (16, 12, 2) and field.dtype == np.float32
    assert field.flags.owndata and field.flags.c_contiguous and not field.flags.writeable
    assert np.all(field.view(np.uint32) == 0)
    for array, before in zip((body, body_weight, face, face_weight), snapshots):
        assert not np.shares_memory(field, array)
        assert np.array_equal(array.view(np.uint32), before.view(np.uint32))


def test_every_native_input_is_an_independent_snapshot_before_call(protocol, monkeypatch):
    arrays = inputs()
    before = [a.copy() for a in arrays]
    class Inspect(Protocol):
        def lrt_body_face_match_prepare_v1(self, *args):
            for at, array, snapshot in zip([0, 2, 6, 8], arrays, before):
                assert ctypes.addressof(args[at].contents) != array.ctypes.data
                array.fill(.9)
                assert np.array_equal(np.ctypeslib.as_array(args[at], shape=(array.size,)), snapshot.ravel())
            return super().lrt_body_face_match_prepare_v1(*args)
    monkeypatch.setattr(match, 'native', lambda: Inspect())
    assert np.all(match.prepare(*arrays, 0, radius=4) == 0)


def test_both_rgb_and_coverage_arrays_are_strict_even_when_neutral(protocol):
    original_arrays = inputs()
    for at in range(4):
        for invalid in [float('nan'), float('inf'), -.01, 1.01]:
            arrays = [a.copy() for a in original_arrays]
            arrays[at].flat[0] = invalid
            with pytest.raises(ValueError, match='finite SDR'):
                match.prepare(*arrays, 0, radius=4)
        for invalid in [original_arrays[at].astype(np.float64),
                        original_arrays[at].astype('>f4'), original_arrays[at].tolist()]:
            arrays = list(original_arrays); arrays[at] = invalid
            with pytest.raises(ValueError):
                match.prepare(*arrays, 0, radius=4)
    for at in [0, 2]:
        arrays = list(original_arrays); arrays[at] = arrays[at][..., :2]
        with pytest.raises(ValueError):
            match.prepare(*arrays, 0, radius=4)
    for at in [1, 3]:
        arrays = list(original_arrays); arrays[at] = arrays[at][:3]
        with pytest.raises(ValueError):
            match.prepare(*arrays, 0, radius=4)
    for amount in [True, float('nan'), float('inf'), -.01, 1.01, 10**1000]:
        with pytest.raises(ValueError):
            match.prepare(*original_arrays, amount, radius=4)
    for radius in [True, 3, 257, 4.0, np.int32(4)]:
        with pytest.raises(ValueError):
            match.prepare(*original_arrays, 0, radius=radius)
    with pytest.raises(TypeError):
        match.prepare(*original_arrays, 0, radius=4, cancelled=False)


def test_combined_estimate_is_pure_counts_both_grids_and_rejects_aggregate_overflow(monkeypatch):
    monkeypatch.setattr(match, 'native', lambda: pytest.fail('Must not load native'))
    monkeypatch.setattr(match, '_available_estimate', lambda: pytest.fail('Must not query live memory'))
    assert match.memory_estimate((4000, 4000), (4000, 4000)) == (112+24)*16_000_000+8*1024**2
    assert match.memory_estimate((16, 24), (9, 13)) == 112*384+24*117+8*1024**2
    assert match.NATIVE_BODY_BYTES_PER_PIXEL == 112 and match.NATIVE_FACE_BYTES_PER_PIXEL == 24
    assert match.TOTAL_BODY_BYTES_PER_PIXEL == 128 and match.TOTAL_FACE_BYTES_PER_PIXEL == 40
    with pytest.raises(MemoryError):
        match.memory_estimate((4000, 8000), (1, 1))
    for invalid in [(0, 3), (3, 65_537), (True, 3), (3, 3.0), (3, 3, 3)]:
        with pytest.raises(ValueError):
            match.memory_estimate(invalid, (9, 13))
        with pytest.raises(ValueError):
            match.memory_estimate((16, 24), invalid)


def test_old_abi1_library_does_not_advertise_new_optional_capability(monkeypatch):
    match.native.cache_clear()
    try:
        monkeypatch.setattr(original, 'native', lambda: SimpleNamespace())
        assert original.available()  # Existing loader success does not prove the optional symbol.
        assert not match.available()
        capability = state.capability()
        assert set(capability) == {'body_face_match_available', 'body_face_match_reason'}
        assert not capability['body_face_match_available'] and capability['body_face_match_reason']
        with pytest.raises(RuntimeError, match='extension.*no fallback'):
            match.native()
        optional = SimpleNamespace(lrt_body_face_match_prepare_v1=SimpleNamespace())
        monkeypatch.setattr(original, 'native', lambda: optional)
        assert match.available()
        assert len(optional.lrt_body_face_match_prepare_v1.argtypes) == 18
        assert optional.lrt_body_face_match_prepare_v1.restype is ctypes.c_int
    finally:
        match.native.cache_clear()


def test_preflight_and_missing_extension_refuse_neutral_without_fallback(monkeypatch):
    arrays = inputs()
    monkeypatch.setattr(match, 'native', lambda: pytest.fail('Must refuse before native'))
    with pytest.raises(InterruptedError):
        match.prepare(*arrays, 0, radius=4, cancelled=lambda: True)
    monkeypatch.setattr(match, '_available_estimate', lambda: 0)
    with pytest.raises(MemoryError):
        match.prepare(*arrays, 0, radius=4)
    def absent():
        raise RuntimeError('Body-face match extension missing; no fallback')
    monkeypatch.setattr(match, '_available_estimate', lambda: 16*1024**3)
    monkeypatch.setattr(match, 'native', absent)
    with pytest.raises(RuntimeError, match='no fallback'):
        match.prepare(*arrays, 0, radius=4)


def test_body_and_face_shortage_status_and_context_are_not_silent_noops(protocol, monkeypatch):
    arrays = inputs()
    before = [a.copy() for a in arrays]
    for code, expected in [(1, ValueError), (2, ValueError), (3, ValueError),
                           (4, InterruptedError), (5, MemoryError), (6, RuntimeError),
                           (7, ValueError), (8, ValueError)]:
        class Refused(Protocol):
            def lrt_body_face_match_prepare_v1(self, *args):
                return code
        monkeypatch.setattr(match, 'native', lambda: Refused())
        with pytest.raises(expected):
            match.prepare(*arrays, 1, radius=4)
    with pytest.raises(ValueError, match='own-body support or own-face reference'):
        match._result(7, lambda: False, [])
    with pytest.raises(ValueError, match='body-source guided context'):
        match._result(8, lambda: False, [])
    for a, b in zip(arrays, before):
        assert np.array_equal(a, b)


def test_callback_exceptions_and_late_cancellation_discard_private_results(protocol, monkeypatch):
    def broken():
        raise LookupError('callback failed')
    callback, errors = original._callback(broken)
    assert callback(None) == 1 and callback(None) == 1
    with pytest.raises(LookupError, match='callback failed'):
        match._result(4, lambda: False, errors)
    cancelled = [False]
    class Late(Protocol):
        def lrt_body_face_match_prepare_v1(self, *args):
            result = super().lrt_body_face_match_prepare_v1(*args)
            cancelled[0] = True
            return result
    monkeypatch.setattr(match, 'native', lambda: Late())
    with pytest.raises(InterruptedError):
        match.prepare(*inputs(), 1, radius=4, cancelled=lambda: cancelled[0])


def test_invalid_field_and_nonzero_neutral_or_protected_body_output_are_discarded(protocol, monkeypatch):
    arrays = inputs(); arrays[1][0, 0] = 0.0
    class Protected(Protocol):
        def lrt_body_face_match_prepare_v1(self, *args):
            result = super().lrt_body_face_match_prepare_v1(*args)
            args[14][0] = .02
            return result
    monkeypatch.setattr(match, 'native', lambda: Protected())
    for amount in [0, 1]:
        with pytest.raises(RuntimeError, match='unsupported'):
            match.prepare(*arrays, amount, radius=4)
    for invalid in [float('nan'), float('inf'), .09]:
        class Unbounded(Protocol):
            def lrt_body_face_match_prepare_v1(self, *args):
                result = super().lrt_body_face_match_prepare_v1(*args)
                args[14][2] = invalid
                args[14][3] = invalid
                return result
        monkeypatch.setattr(match, 'native', lambda: Unbounded())
        with pytest.raises(RuntimeError, match='unbounded'):
            match.prepare(*arrays, 1, radius=4)


def test_application_is_existing_current_luminance_implementation_not_second_solver():
    assert match.apply is original.apply
    assert match.application_memory_estimate is original.application_memory_estimate
