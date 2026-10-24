# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No native, numerical, image or product acceptance claimed.

Stub fixtures exercise ownership/refusal contracts, not the Rust deformation.
Installed-core fixtures never compile or download a missing native library.
"""
import ctypes as C
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import face_size_native as boundary
from lumaretouch_engine import face_size_state as state


def fixture():
    return (np.array([[70.0, 45.0], [30.0, 75.0]], dtype=np.float64),
            np.array([50.0, 60.0, 1.0, 0.0, 0.0, -1.0,
                      40.0, 60.0, 1.0, 2.0, 0.94], dtype=np.float64))


class RecordingNative:
    """Fixture writer, deliberately not another deformation implementation."""
    def __init__(self, output=None, status=0, on_enter=None):
        self.output = (np.zeros((2, 2), dtype=np.float64) if output is None
                       else np.asarray(output, dtype=np.float64))
        self.status = status
        self.on_enter = on_enter
        self.inputs = []
        self.pointers = []
        self.calls = 0

    def lrt_face_size_evaluate_v1(self, points, points_len, params, params_len,
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


class FaceSizeBoundaryContracts(TestCase):
    def test_snapshots_own_contiguous_readonly_storage_without_caller_aliases(self):
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

    def test_noncontiguous_inputs_are_copied_before_native_releases_gil(self):
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
        self.assertTrue(output.flags.owndata)
        self.assertTrue(output.flags.writeable)
        self.assertTrue(output.flags.c_contiguous)

    def test_all_shapes_dtypes_and_batch_bounds_reject_before_copying_or_loading(self):
        invalid = []
        for index in range(2):
            for dtype in (np.float32, np.int32, np.bool_, np.complex128, object, '>f8'):
                args = list(fixture())
                args[index] = args[index].astype(dtype)
                if args[index].dtype == np.float64:
                    continue  # The opposite-endian case is platform-dependent.
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

    def test_nonfinite_input_in_every_position_refuses_even_if_neutral(self):
        for index, array in enumerate(fixture()):
            for offset in range(array.size):
                for bad in (np.nan, np.inf, -np.inf):
                    args = list(fixture())
                    args[1][10] = 1.0
                    args[index].flat[offset] = bad
                    with patch.object(boundary, 'native') as native:
                        with self.assertRaises(ValueError):
                            boundary.evaluate(*args)
                        native.assert_not_called()

    def test_invalid_frames_extents_scales_support_and_foldrisk_never_load_native(self):
        for index, bad in ((2, 0), (2, 1.00001), (4, 0.1), (6, 0), (7, -1),
                           (8, 0), (8, 2), (9, 0.9), (9, 1.01),
                           (10, 0.939), (10, 1.061)):
            points, params = fixture()
            params[index] = bad
            with patch.object(boundary, 'native') as native:
                with self.assertRaises(ValueError):
                    boundary.evaluate(points, params)
                native.assert_not_called()

    def test_status_failure_never_publishes_private_output(self):
        for status in (1, 2, 3, 4, 5, 6, 123):
            fake = RecordingNative([[12, 34], [56, 78]], status=status)
            expected = ValueError if status in (1, 2, 3, 4) else RuntimeError
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaises(expected):
                    boundary.evaluate(*fixture())

    def test_nonfinite_native_output_is_discarded(self):
        for bad in (np.nan, np.inf, -np.inf):
            fake = RecordingNative([[bad, 0], [0, 0]])
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaises(RuntimeError):
                    boundary.evaluate(*fixture())

    def test_neutral_center_and_outside_must_have_exact_positive_zero(self):
        for mode in ('neutral', 'center', 'outside'):
            points, params = fixture()
            if mode == 'neutral':
                params[10] = 1.0
            elif mode == 'center':
                points[...] = params[:2]
            else:
                points[...] = [[130, 60], [50, 180]]
            for bad in (0.01, -0.0):
                fake = RecordingNative([[bad, 0], [0, 0]])
                with patch.object(boundary, 'native', return_value=fake):
                    with self.assertRaises(RuntimeError):
                        boundary.evaluate(points, params)
            with patch.object(boundary, 'native', return_value=RecordingNative()):
                result = boundary.evaluate(points, params)
            self.assertFalse(np.any(result.view(np.uint64)))

    def test_missing_core_refuses_direct_neutral_calls_without_fallback(self):
        points, params = fixture()
        params[10] = 1.0
        with patch.object(boundary, 'native', side_effect=RuntimeError('missing native')):
            with self.assertRaisesRegex(RuntimeError, 'missing native'):
                boundary.evaluate(points, params)

    def test_capability_probes_loading_not_file_presence(self):
        for error in (RuntimeError('ABI'), OSError('load'), AttributeError('symbol')):
            with patch.object(boundary, 'native', side_effect=error):
                self.assertFalse(boundary.available())
                result = state.capability()
            self.assertFalse(result['face_size_available'])
            self.assertTrue(result['face_size_reason'])
        with patch.object(boundary, 'native', return_value=object()):
            self.assertEqual(state.capability(), {'face_size_available': True,
                                                'face_size_reason': None})

    def test_loader_requires_exact_abi_and_versioned_evaluator(self):
        class Symbol:
            def __init__(self, value):
                self.value = value
            def __call__(self):
                return self.value
        libraries = (SimpleNamespace(lrt_face_size_abi=Symbol(2)),
                     SimpleNamespace(lrt_face_size_abi=Symbol(1)))
        for lib in libraries:
            boundary.native.cache_clear()
            try:
                with patch.object(boundary.Path, 'is_file', return_value=True), \
                        patch.object(boundary.C, 'CDLL', return_value=lib):
                    with self.assertRaises(RuntimeError):
                        boundary.native()
            finally:
                boundary.native.cache_clear()
        lib = SimpleNamespace(lrt_face_size_abi=Symbol(1),
                              lrt_face_size_evaluate_v1=Symbol(0))
        try:
            with patch.object(boundary.Path, 'is_file', return_value=True), \
                    patch.object(boundary.C, 'CDLL', return_value=lib):
                self.assertIs(boundary.native(), lib)
            self.assertEqual(lib.lrt_face_size_evaluate_v1.argtypes,
                             [boundary.P, C.c_size_t] * 2 +
                             [C.c_size_t, boundary.P, C.c_size_t])
            self.assertEqual(lib.lrt_face_size_evaluate_v1.restype, C.c_int32)
        finally:
            boundary.native.cache_clear()


class FaceSizeStateContracts(TestCase):
    def test_traceability_portable_schema_and_local_signed_scale_policy(self):
        self.assertEqual(state.OP, 'lnx.face_size.v1')
        self.assertEqual(state.CONTROL_ID, 'LNX-REF-PC-32466-C-728fc62cdd')
        self.assertEqual(state.neutral(), {'version': 1, 'amount': 0.0})
        self.assertEqual(state.check(None), state.neutral())
        with patch.object(boundary, 'native', side_effect=AssertionError('must not load')):
            self.assertFalse(state.active(None))
            self.assertFalse(state.active({'version': 1, 'amount': -0.0}))
            self.assertTrue(state.active({'version': 1, 'amount': 0.25}))
        self.assertEqual(state.scale_for_amount(1), 0.94)
        self.assertEqual(state.scale_for_amount(0), 1.0)
        self.assertEqual(state.scale_for_amount(-1), 1.06)

    def test_state_checks_and_presets_never_mutate_or_retain_caller_object(self):
        value = {'version': 1, 'amount': 0.5}
        result = state.preset(value)
        self.assertIsNot(result, value)
        result['amount'] = -1
        self.assertEqual(value['amount'], 0.5)

    def test_bad_amounts_versions_and_unknown_geometry_fields_refuse(self):
        for bad in (True, np.float64(0.1), np.int32(1), None, '0.2',
                    np.nan, np.inf, -np.inf, -1.01, 1.01, 10**1000):
            with self.assertRaises(ValueError):
                state.check({'version': 1, 'amount': bad})
            with self.assertRaises(ValueError):
                state.scale_for_amount(bad)
        for bad in (True, 1.0, 0, 2, None):
            with self.assertRaises(ValueError):
                state.check({'version': bad, 'amount': 0})
        for extra in ('face_id', 'landmarks', 'cache', 'path', 'mask', 'linked', 'scale'):
            value = state.neutral()
            value[extra] = 'forbidden'
            with self.assertRaises(ValueError):
                state.check(value)


class InstalledFaceSizeCoreContracts(TestCase):
    """Skip without a separately installed library; never build or download."""
    def setUp(self):
        if not boundary.available():
            self.skipTest('Face-size Rust core unavailable; no implicit build or fallback')

    def test_uniform_inverse_core_both_axes_both_signs_and_no_identity_pins(self):
        points, params = fixture()
        for scale in (0.94, 1.06):
            params[10] = scale
            delta = boundary.evaluate(points, params)
            expected_source = params[:2] + (points - params[:2]) / scale
            np.testing.assert_allclose(points - delta, expected_source, rtol=1e-13, atol=1e-13)
            self.assertTrue(np.all(np.any(delta != 0, axis=1)))

    def test_quintic_midpoint_and_exact_neutral_outside_behavior(self):
        _, params = fixture()
        points = np.array([[110, 60], [130, 60], [50, 180], [50, 60]], dtype=np.float64)
        delta = boundary.evaluate(points, params)
        self.assertAlmostEqual(delta[0, 0], (1 - 1 / 0.94) * 0.5 * 60)
        self.assertFalse(np.any(delta[1:].view(np.uint64)))
        params[10] = 1
        self.assertFalse(np.any(boundary.evaluate(points, params).view(np.uint64)))

    def test_ffi_errors_and_writable_alias_leave_destination_untouched(self):
        points, params = fixture()
        output = np.full_like(points, 77)
        lib = boundary.native()
        status = lib.lrt_face_size_evaluate_v1(
            points.ctypes.data_as(boundary.P), points.size - 1,
            *boundary._pair(params), len(points), *boundary._pair(output))
        self.assertEqual(status, 1)
        np.testing.assert_array_equal(output, np.full_like(points, 77))
        before = points.copy()
        status = lib.lrt_face_size_evaluate_v1(
            *boundary._pair(points), *boundary._pair(params), len(points), *boundary._pair(points))
        self.assertEqual(status, 1)
        np.testing.assert_array_equal(points, before)
