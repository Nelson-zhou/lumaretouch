# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No build, execution or photographic acceptance claimed.

Stubs verify boundary contracts, not deformation. Installed-core fixtures skip
without the separately built library and never download/compile a replacement.
"""
import ctypes as C
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import lower_face_native as boundary
from lumaretouch_engine import lower_face_state as state


def fixture():
    return (np.array([[50.0, 80.0], [85.0, 103.0]], dtype=np.float64),
            np.array([50.0, 60.0, 1.0, 0.0, 0.0, 1.0,
                      40.0, 25.0, 50.0, 0.5, 1.0], dtype=np.float64))


class RecordingNative:
    """Private-output fixture writer, not an alternate inverse implementation."""
    def __init__(self, output=None, status=0, on_enter=None):
        self.output = (np.zeros((2, 2), dtype=np.float64) if output is None
                       else np.asarray(output, dtype=np.float64))
        self.status, self.on_enter = status, on_enter
        self.inputs, self.pointers, self.calls = [], [], 0

    def lrt_lower_face_evaluate_v1(self, points, points_len, params, params_len,
                                  count, output, output_len):
        self.calls += 1
        if self.on_enter:
            self.on_enter()
        pairs = ((points, points_len), (params, params_len))
        self.inputs = [np.ctypeslib.as_array(pointer, shape=(length,)).copy()
                       for pointer, length in pairs]
        self.pointers = [C.cast(pointer, C.c_void_p).value for pointer, _ in pairs]
        assert output_len == count * 2 == self.output.size
        C.memmove(output, self.output.ctypes.data, self.output.nbytes)
        return self.status


class LowerFaceBoundaryContracts(TestCase):
    def test_independent_readonly_snapshots_and_noncontiguous_inputs(self):
        for original in fixture():
            view = original[::-1]
            expected = view.copy()
            snapshot = boundary._snapshot(view)
            self.assertTrue(snapshot.flags.owndata)
            self.assertTrue(snapshot.flags.c_contiguous)
            self.assertFalse(snapshot.flags.writeable)
            self.assertFalse(np.shares_memory(snapshot, original))
            original[...] = 99
            np.testing.assert_array_equal(snapshot, expected)
        arrays = tuple(array[::-1].copy()[::-1] for array in fixture())
        before = tuple(array.copy() for array in arrays)
        def mutate_callers():
            for array in arrays:
                array[...] = 99
        fake = RecordingNative(on_enter=mutate_callers)
        with patch.object(boundary, 'native', return_value=fake):
            output = boundary.evaluate(*arrays)
        self.assertEqual(fake.calls, 1)
        for index, expected in enumerate(before):
            np.testing.assert_array_equal(fake.inputs[index], expected.ravel())
            self.assertNotEqual(fake.pointers[index], arrays[index].ctypes.data)
            self.assertFalse(np.shares_memory(output, arrays[index]))
        self.assertEqual(output.shape, (2, 2))
        self.assertEqual(output.dtype, np.float64)
        self.assertTrue(output.flags.owndata and output.flags.writeable and output.flags.c_contiguous)

    def test_all_shapes_dtypes_and_batch_limits_refuse_before_copying_or_loading(self):
        invalid = []
        for index in range(2):
            for dtype in (np.float32, np.int32, np.bool_, np.complex128, object, '>f8'):
                args = list(fixture())
                args[index] = args[index].astype(dtype)
                if args[index].dtype != np.float64:
                    invalid.append(args)
            for replacement in (fixture()[index].tolist(), fixture()[index][..., None]):
                args = list(fixture())
                args[index] = replacement
                invalid.append(args)
        for count in (0, boundary.MAX_POINTS + 1):
            invalid.append((np.empty((count, 2), dtype=np.float64), fixture()[1]))
        for length in (0, 10, 12):
            invalid.append((fixture()[0], np.empty(length, dtype=np.float64)))
        for args in invalid:
            with patch.object(boundary, '_snapshot') as snapshot, \
                    patch.object(boundary, 'native') as native:
                with self.assertRaises(ValueError):
                    boundary.evaluate(*args)
                snapshot.assert_not_called()
                native.assert_not_called()

    def test_nonfinite_everywhere_refuses_even_for_neutral(self):
        for index, array in enumerate(fixture()):
            for offset in range(array.size):
                for bad in (np.nan, np.inf, -np.inf):
                    args = list(fixture())
                    args[1][10] = 0.0
                    args[index].flat[offset] = bad
                    with patch.object(boundary, 'native') as native:
                        with self.assertRaises(ValueError):
                            boundary.evaluate(*args)
                        native.assert_not_called()

    def test_invalid_frame_height_widths_tail_and_signed_amount_never_load(self):
        for index, bad in ((2, 0), (2, 1.000001), (4, 1e-8), (6, 0), (6, -1),
                           (7, 0), (7, 50), (8, 24), (9, 0.249), (9, 1.001),
                           (10, -1.01), (10, 1.01)):
            points, params = fixture()
            params[index] = bad
            with patch.object(boundary, 'native') as native:
                with self.assertRaises(ValueError):
                    boundary.evaluate(points, params)
                native.assert_not_called()

    def test_canonical_frame_accepts_roundoff_not_skew_and_preserves_handedness(self):
        self.assertEqual(boundary.canonical_frame((1 + 1e-12, 0), (1e-12, 1 - 1e-12)),
                         ((1.0, 0.0), (-0.0, 1.0)))
        self.assertEqual(boundary.canonical_frame((0.6, 0.8), (0.8, -0.6)),
                         ((0.6, 0.8), (0.8, -0.6)))
        for right, down in (((1, 0), (1e-8, 1)), ((0, 0), (0, 1)),
                            ((np.inf, 0), (0, 1)), ((True, 0), (0, 1)),
                            ((1,), (0, 1)), (('1', 0), (0, 1))):
            with self.assertRaises(ValueError):
                boundary.canonical_frame(right, down)

    def test_every_error_status_discards_private_output(self):
        for status in (1, 2, 3, 4, 5, 6, 123):
            fake = RecordingNative([[12, 34], [56, 78]], status=status)
            expected = ValueError if status in (1, 2, 3, 4) else RuntimeError
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaises(expected):
                    boundary.evaluate(*fixture())

    def test_nonfinite_lateral_wrong_sign_and_out_of_bound_outputs_are_discarded(self):
        invalid = [[[bad, 0], [0, 0]] for bad in (np.nan, np.inf, -np.inf)]
        invalid += [[[0.01, 0], [0, 0]], [[0, -0.1], [0, 0]], [[0, 4], [0, 0]]]
        for output in invalid:
            with patch.object(boundary, 'native', return_value=RecordingNative(output)):
                with self.assertRaises(RuntimeError):
                    boundary.evaluate(*fixture())

    def test_neutral_upper_and_all_support_edges_require_exact_positive_zero(self):
        for mode in ('neutral', 'upper', 'lateral', 'bottom', 'above'):
            points, params = fixture()
            if mode == 'neutral':
                params[10] = 0.0
            elif mode == 'upper':
                points[...] = [[50, 60], [60, 60]]
            elif mode == 'lateral':
                points[...] = [[100, 80], [0, 80]]
            elif mode == 'bottom':
                points[...] = [[50, 120], [50, 121]]
            else:
                points[...] = [[50, 59], [50, -100]]
            for bad in (0.01, -0.0):
                with patch.object(boundary, 'native',
                                  return_value=RecordingNative([[0, bad], [0, 0]])):
                    with self.assertRaises(RuntimeError):
                        boundary.evaluate(points, params)
            with patch.object(boundary, 'native', return_value=RecordingNative()):
                result = boundary.evaluate(points, params)
            self.assertFalse(np.any(result.view(np.uint64)))

    def test_direct_neutral_still_requires_core_without_fallback(self):
        points, params = fixture()
        params[10] = 0.0
        with patch.object(boundary, 'native', side_effect=RuntimeError('missing native')):
            with self.assertRaisesRegex(RuntimeError, 'missing native'):
                boundary.evaluate(points, params)

    def test_capability_checks_loading_not_file_existence(self):
        for error in (RuntimeError('ABI'), OSError('load'), AttributeError('symbol')):
            with patch.object(boundary, 'native', side_effect=error):
                self.assertFalse(boundary.available())
                result = state.capability()
            self.assertFalse(result['lower_face_available'])
            self.assertTrue(result['lower_face_reason'])
        with patch.object(boundary, 'native', return_value=object()):
            self.assertEqual(state.capability(), {'lower_face_available': True,
                                                 'lower_face_reason': None})

    def test_loader_verifies_exact_abi_and_versioned_symbol(self):
        class Symbol:
            def __init__(self, value):
                self.value = value
            def __call__(self):
                return self.value
        for lib in (SimpleNamespace(lrt_lower_face_abi=Symbol(2)),
                    SimpleNamespace(lrt_lower_face_abi=Symbol(1))):
            boundary.native.cache_clear()
            try:
                with patch.object(boundary.Path, 'is_file', return_value=True), \
                        patch.object(boundary.C, 'CDLL', return_value=lib):
                    with self.assertRaises(RuntimeError):
                        boundary.native()
            finally:
                boundary.native.cache_clear()
        lib = SimpleNamespace(lrt_lower_face_abi=Symbol(1),
                              lrt_lower_face_evaluate_v1=Symbol(0))
        try:
            with patch.object(boundary.Path, 'is_file', return_value=True), \
                    patch.object(boundary.C, 'CDLL', return_value=lib):
                self.assertIs(boundary.native(), lib)
            self.assertEqual(lib.lrt_lower_face_evaluate_v1.argtypes,
                             [boundary.P, C.c_size_t] * 2 +
                             [C.c_size_t, boundary.P, C.c_size_t])
            self.assertEqual(lib.lrt_lower_face_evaluate_v1.restype, C.c_int32)
        finally:
            boundary.native.cache_clear()


class LowerFaceStateContracts(TestCase):
    def test_exact_traceability_signed_portable_state_and_native_free_neutral(self):
        self.assertEqual(state.OP, 'lnx.lower_face.v1')
        self.assertEqual(state.CONTROL_ID, 'LNX-REF-PC-32466-C-1ae8316994')
        self.assertEqual(state.neutral(), {'version': 1, 'amount': 0.0})
        self.assertEqual(state.check(None), state.neutral())
        self.assertEqual(state.LENGTH_GAIN, 0.08)
        self.assertEqual(state.TAIL, 0.5)
        with patch.object(boundary, 'native', side_effect=AssertionError('must not load')):
            self.assertFalse(state.active(None))
            self.assertFalse(state.active({'version': 1, 'amount': -0.0}))
            for amount in (-1, -0.25, 0.25, 1):
                self.assertTrue(state.active({'version': 1, 'amount': amount}))
                self.assertEqual(state.check({'version': 1, 'amount': amount})['amount'], amount)

    def test_check_and_preset_do_not_mutate_or_keep_caller_objects(self):
        original = {'version': 1, 'amount': 0.5}
        result = state.preset(original)
        self.assertIsNot(result, original)
        result['amount'] = -1
        self.assertEqual(original['amount'], 0.5)
        self.assertIsNot(state.neutral(), state.neutral())

    def test_bad_versions_amounts_and_geometry_keys_refuse(self):
        for bad in (True, np.float64(0.1), np.int32(1), None, '0.2',
                    np.nan, np.inf, -np.inf, -1.01, 1.01, 10**1000):
            with self.assertRaises(ValueError):
                state.check({'version': 1, 'amount': bad})
        for bad in (True, 1.0, 0, 2, None):
            with self.assertRaises(ValueError):
                state.check({'version': bad, 'amount': 0})
        for extra in ('face_id', 'landmarks', 'cache', 'path', 'mask', 'linked', 'tail', 'height'):
            value = state.neutral()
            value[extra] = 'forbidden'
            with self.assertRaises(ValueError):
                state.check(value)


class InstalledLowerFaceCoreContracts(TestCase):
    """Skip without a separately installed library. Never build/download."""
    def setUp(self):
        if not boundary.available():
            self.skipTest('Lower-face Rust core unavailable; no implicit build or fallback')

    def test_true_chin_inverse_both_signs_not_forward_delta(self):
        _, params = fixture()
        for amount in (-1, -0.25, 0.25, 1):
            params[10] = amount
            shift = 0.08 * params[6] * amount
            source = np.array([[50, 100]], dtype=np.float64)
            target = source + [[0, shift]]
            delta = boundary.evaluate(target, params)
            np.testing.assert_allclose(delta, [[0, shift]], rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(target - delta, source, rtol=1e-13, atol=1e-13)

    def test_zero_edges_neutral_and_tiny_representable_physical_delta(self):
        _, params = fixture()
        points = np.array([[50, 60], [50, 120], [100, 80], [0, 80]], dtype=np.float64)
        self.assertFalse(np.any(boundary.evaluate(points, params).view(np.uint64)))
        params[10] = 0
        self.assertFalse(np.any(boundary.evaluate(fixture()[0], params).view(np.uint64)))
        params[:2] = 0
        params[6] = 1e300
        params[10] = np.nextafter(0.0, 1.0)
        delta = boundary.evaluate(np.array([[0, 0.5e300]], dtype=np.float64), params)
        expected = ((0.08 * params[6]) * params[10]) * 0.5
        self.assertGreater(delta[0, 1], 0)
        np.testing.assert_allclose(delta[0, 1], expected, rtol=1e-13, atol=0)

    def test_ffi_failures_and_alias_leave_destination_untouched(self):
        points, params = fixture()
        output = np.full_like(points, 77)
        lib = boundary.native()
        status = lib.lrt_lower_face_evaluate_v1(
            points.ctypes.data_as(boundary.P), points.size - 1,
            *boundary._pair(params), len(points), *boundary._pair(output))
        self.assertEqual(status, 1)
        np.testing.assert_array_equal(output, np.full_like(points, 77))
        before = points.copy()
        status = lib.lrt_lower_face_evaluate_v1(
            *boundary._pair(points), *boundary._pair(params), len(points), *boundary._pair(points))
        self.assertEqual(status, 1)
        np.testing.assert_array_equal(points, before)
        params[10] = np.nan
        status = lib.lrt_lower_face_evaluate_v1(
            *boundary._pair(points), *boundary._pair(params), len(points), *boundary._pair(output))
        self.assertEqual(status, 2)
        np.testing.assert_array_equal(output, np.full_like(points, 77))
