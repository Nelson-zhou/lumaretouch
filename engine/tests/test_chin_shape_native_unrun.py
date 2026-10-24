# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No build, execution or photographic acceptance claimed.

Stubs exercise boundary contracts, not numerical acceptance. Installed-core
fixtures skip without the independently installed library, never build/download.
"""
import ctypes as C
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import chin_shape_native as boundary
from lumaretouch_engine import chin_shape_state as state


def fixture():
    return (np.array([[65.0, 80.0], [15.0, 103.0]], dtype=np.float64),
            np.array([50.0, 60.0, 1.0, 0.0, 0.0, 1.0,
                      40.0, 25.0, 50.0, 1.0, 1.0], dtype=np.float64))


class RecordingNative:
    """Private-output fixture writer, not an alternate deformation algorithm."""
    def __init__(self, output=None, status=0, on_enter=None):
        self.output = np.asarray([[-0.5, 0], [0.5, 0]] if output is None else output,
                                 dtype=np.float64)
        self.status, self.on_enter = status, on_enter
        self.inputs, self.pointers, self.calls = [], [], 0

    def lrt_chin_shape_evaluate_v1(self, points, points_len, params, params_len,
                                  count, output, output_len):
        self.calls += 1
        if self.on_enter:
            self.on_enter()
        pairs = ((points, points_len), (params, params_len))
        self.inputs = [np.ctypeslib.as_array(pointer, shape=(length,)).copy()
                       for pointer, length in pairs]
        self.pointers = [C.cast(pointer, C.c_void_p).value for pointer, _ in pairs]
        assert params_len == 11 and output_len == count * 2 == self.output.size
        C.memmove(output, self.output.ctypes.data, self.output.nbytes)
        return self.status


class ChinShapeBoundaryContracts(TestCase):
    def test_readonly_independent_snapshots_and_noncontiguous_input_ownership(self):
        for original in fixture():
            view = original[::-1]
            expected = view.copy()
            snapshot = boundary._snapshot(view)
            self.assertTrue(snapshot.flags.owndata and snapshot.flags.c_contiguous)
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

    def test_exact_dtype_shapes_and_bounds_before_copy_or_load(self):
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

    def test_every_nonfinite_value_refuses_even_when_neutral(self):
        for index, array in enumerate(fixture()):
            for offset in range(array.size):
                for bad in (np.nan, np.inf, -np.inf):
                    args = list(fixture())
                    args[1][9:11] = 0
                    args[index].flat[offset] = bad
                    with patch.object(boundary, 'native') as native:
                        with self.assertRaises(ValueError):
                            boundary.evaluate(*args)
                        native.assert_not_called()

    def test_invalid_axes_height_exact_width_ratio_and_bilateral_amounts(self):
        for index, bad in ((2, 0), (2, 1.000001), (4, 1e-8), (6, 0), (6, -1),
                           (7, 0), (7, 50), (8, 24), (8, 50.0001),
                           (9, -1.01), (9, 1.01), (10, -1.01), (10, 1.01)):
            points, params = fixture()
            params[index] = bad
            with patch.object(boundary, 'native') as native:
                with self.assertRaises(ValueError):
                    boundary.evaluate(points, params)
                native.assert_not_called()

    def test_canonical_frame_accepts_roundoff_not_skew_and_both_handednesses(self):
        self.assertEqual(boundary.canonical_frame((1 + 1e-12, 0), (1e-12, 1 - 1e-12)),
                         ((1.0, 0.0), (-0.0, 1.0)))
        self.assertEqual(boundary.canonical_frame((0.6, 0.8), (0.8, -0.6)),
                         ((0.6, 0.8), (0.8, -0.6)))
        for right, down in (((1, 0), (1e-8, 1)), ((0, 0), (0, 1)),
                            ((np.inf, 0), (0, 1)), ((True, 0), (0, 1)),
                            ((1,), (0, 1)), (('1', 0), (0, 1))):
            with self.assertRaises(ValueError):
                boundary.canonical_frame(right, down)

    def test_every_error_discards_private_output(self):
        for status in (1, 2, 3, 4, 5, 6, 123):
            fake = RecordingNative([[12, 34], [56, 78]], status=status)
            expected = ValueError if status in (1, 2, 3, 4) else RuntimeError
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaises(expected):
                    boundary.evaluate(*fixture())

    def test_nonfinite_axial_wrong_sign_zero_motion_and_amplitude_refuse(self):
        invalid = [[[bad, 0], [0.5, 0]] for bad in (np.nan, np.inf, -np.inf)]
        invalid += [[[-0.5, 0.01], [0.5, 0]], [[0.5, 0], [0.5, 0]],
                    [[-5, 0], [0.5, 0]], [[0, 0], [0.5, 0]]]
        for output in invalid:
            with patch.object(boundary, 'native', return_value=RecordingNative(output)):
                with self.assertRaises(RuntimeError):
                    boundary.evaluate(*fixture())

    def test_exact_positive_zero_neutral_side_center_and_every_support_edge(self):
        for mode in ('neutral', 'zero_side', 'upper', 'center', 'lateral', 'bottom', 'above'):
            points, params = fixture()
            if mode == 'neutral':
                params[9:11] = 0
            elif mode == 'zero_side':
                params[9] = 0
                points[...] = [[65, 80], [75, 100]]
            elif mode == 'upper':
                points[...] = [[65, 60], [15, 60]]
            elif mode == 'center':
                points[...] = [[50, 80], [50, 100]]
            elif mode == 'lateral':
                points[...] = [[100, 80], [0, 80]]
            elif mode == 'bottom':
                points[...] = [[65, 120], [15, 121]]
            else:
                points[...] = [[65, 59], [15, -100]]
            for bad in (0.01, -0.0):
                with patch.object(boundary, 'native',
                                  return_value=RecordingNative([[bad, 0], [0, 0]])):
                    with self.assertRaises(RuntimeError):
                        boundary.evaluate(points, params)
            with patch.object(boundary, 'native',
                              return_value=RecordingNative([[0, 0], [0, 0]])):
                result = boundary.evaluate(points, params)
            self.assertFalse(np.any(result.view(np.uint64)))

    def test_direct_neutral_still_requires_core_without_substitution(self):
        points, params = fixture()
        params[9:11] = 0
        with patch.object(boundary, 'native', side_effect=RuntimeError('missing native')):
            with self.assertRaisesRegex(RuntimeError, 'missing native'):
                boundary.evaluate(points, params)

    def test_capability_checks_loading_not_anatomical_or_quality_acceptance(self):
        for error in (RuntimeError('ABI'), OSError('load'), AttributeError('symbol')):
            with patch.object(boundary, 'native', side_effect=error):
                self.assertFalse(boundary.available())
                result = state.capability()
            self.assertFalse(result['chin_shape_available'])
            self.assertTrue(result['chin_shape_reason'])
        with patch.object(boundary, 'native', return_value=object()):
            self.assertEqual(state.capability(), {'chin_shape_available': True,
                                                 'chin_shape_reason': None})

    def test_loader_requires_exact_abi_and_versioned_symbol(self):
        class Symbol:
            def __init__(self, value):
                self.value = value
            def __call__(self):
                return self.value
        for lib in (SimpleNamespace(lrt_chin_shape_abi=Symbol(2)),
                    SimpleNamespace(lrt_chin_shape_abi=Symbol(1))):
            boundary.native.cache_clear()
            try:
                with patch.object(boundary.Path, 'is_file', return_value=True), \
                        patch.object(boundary.C, 'CDLL', return_value=lib):
                    with self.assertRaises(RuntimeError):
                        boundary.native()
            finally:
                boundary.native.cache_clear()
        lib = SimpleNamespace(lrt_chin_shape_abi=Symbol(1),
                              lrt_chin_shape_evaluate_v1=Symbol(0))
        try:
            with patch.object(boundary.Path, 'is_file', return_value=True), \
                    patch.object(boundary.C, 'CDLL', return_value=lib):
                self.assertIs(boundary.native(), lib)
            self.assertEqual(lib.lrt_chin_shape_evaluate_v1.argtypes,
                             [boundary.P, C.c_size_t] * 2 +
                             [C.c_size_t, boundary.P, C.c_size_t])
            self.assertEqual(lib.lrt_chin_shape_evaluate_v1.restype, C.c_int32)
        finally:
            boundary.native.cache_clear()


class ChinShapeStateContracts(TestCase):
    def test_exact_traceability_portable_state_and_native_free_neutral(self):
        self.assertEqual(state.OP, 'lnx.chin_shape.v1')
        self.assertEqual(state.CONTROL_ID, 'LNX-REF-PC-32466-C-ed7837df9a')
        self.assertEqual(state.neutral(), {'version': 1, 'linked': True, 'left': 0.0, 'right': 0.0})
        self.assertEqual(state.check(None), state.neutral())
        self.assertEqual(state.WIDTH_GAIN, 0.08)
        self.assertEqual(state.TAIL_FACTOR, 0.5)
        with patch.object(boundary, 'native', side_effect=AssertionError('must not load')):
            self.assertFalse(state.active(None))
            self.assertFalse(state.active({'version': 1, 'linked': True, 'left': -0.0, 'right': 0.0}))
            for amount in (-1, -0.25, 0.25, 1):
                self.assertTrue(state.active({'version': 1, 'linked': False, 'left': amount, 'right': 0}))

    def test_independent_adjustment_link_equality_and_no_hidden_averaging(self):
        original = state.neutral()
        linked = state.adjust(original, 'left', 0.3)
        self.assertEqual((linked['left'], linked['right']), (0.3, 0.3))
        independent = state.link(linked, False)
        adjusted = state.adjust(independent, 'right', -0.7)
        self.assertEqual((adjusted['left'], adjusted['right']), (0.3, -0.7))
        with self.assertRaises(ValueError):
            state.link(adjusted, True)
        with self.assertRaises(ValueError):
            state.check({**adjusted, 'linked': True})
        self.assertEqual(original, state.neutral())
        self.assertIsNot(state.preset(adjusted), adjusted)
        self.assertIsNot(state.neutral(), state.neutral())
        for side in ('', 'screen_left', None):
            with self.assertRaises(ValueError):
                state.adjust(original, side, 1)
        for linked in (1, 0, None, 'true'):
            with self.assertRaises(ValueError):
                state.link(original, linked)

    def test_unknown_versions_keys_coercions_boolean_and_nonfinite_amounts_refuse(self):
        for side in ('left', 'right'):
            for bad in (True, np.float64(0.1), np.int32(1), None, '0.2',
                        np.nan, np.inf, -np.inf, -1.01, 1.01, 10**1000):
                with self.assertRaises(ValueError):
                    state.check({**state.neutral(), 'linked': False, side: bad})
        for version in (True, 1.0, 0, 2, None):
            with self.assertRaises(ValueError):
                state.check({**state.neutral(), 'version': version})
        for linked in (1, 0, None, 'true'):
            with self.assertRaises(ValueError):
                state.check({**state.neutral(), 'linked': linked})
        for extra in ('amount', 'face_id', 'landmarks', 'cache', 'path', 'mask',
                      'height', 'tail', 'inner_x', 'outer_x'):
            with self.assertRaises(ValueError):
                state.check({**state.neutral(), extra: 'forbidden'})
        for missing in state.neutral():
            value = state.neutral()
            del value[missing]
            with self.assertRaises(ValueError):
                state.check(value)


class InstalledChinShapeCoreContracts(TestCase):
    """Skip without a separately installed library; never build/download."""
    def setUp(self):
        if not boundary.available():
            self.skipTest('Chin-shape Rust core unavailable; no implicit build or fallback')

    def test_signed_independent_core_targets_and_true_inverse(self):
        _, params = fixture()
        source = np.array([[30, 80], [70, 80], [50, 100]], dtype=np.float64)
        for left, right in ((1, 1), (-1, -1), (1, -1), (0, 1), (-0.25, 0.7)):
            params[9:11] = [left, right]
            shifts = np.array([[0.8 * right, 0], [-0.8 * left, 0], [0, 0]], dtype=np.float64)
            target = source + shifts
            delta = boundary.evaluate(target, params)
            np.testing.assert_allclose(delta, shifts, rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(target - delta, source, rtol=1e-13, atol=1e-13)
            self.assertFalse(np.any(delta[:, 1].view(np.uint64)))
            naive = -(0.08 * (target[:2, 0] - params[0])) * [right, left] * 0.5
            for index, amount in enumerate((right, left)):
                if amount:
                    self.assertGreater(abs(delta[index, 0] - naive[index]), 1e-7)

    def test_asymmetric_center_continuity_one_sided_slopes_and_no_crossing(self):
        _, params = fixture()
        params[:2] = 0
        params[9:11] = [1, -1]
        for epsilon in (1e-3, 1e-6, 1e-9, 1e-12):
            source = np.array([[epsilon, 40], [-epsilon, 40], [0, 40]], dtype=np.float64)
            target = source.copy()
            target[:2, 0] *= [0.92, 1.08]
            delta = boundary.evaluate(target, params)
            np.testing.assert_allclose(target - delta, source, rtol=1e-13, atol=1e-25)
            self.assertGreater((target - delta)[0, 0], 0)
            self.assertLess((target - delta)[1, 0], 0)
            self.assertFalse(np.any(delta[2].view(np.uint64)))

    def test_roll_translation_scaling_and_both_handednesses(self):
        points, params = fixture()
        reference = boundary.evaluate(points, params)
        for sign in (-1, 1):
            transformed = params.copy()
            transformed[:2] = [300, 400]
            transformed[2:6] = [0.6, 0.8, -0.8 * sign, 0.6 * sign]
            transformed[6:9] *= 3
            right, down = boundary.canonical_frame(transformed[2:4], transformed[4:6])
            matrix = np.array([right, down], dtype=np.float64)
            query = transformed[:2] + 3 * (points - params[:2]) @ matrix
            delta = boundary.evaluate(query, transformed)
            np.testing.assert_allclose(delta, 3 * reference @ matrix, rtol=1e-11, atol=1e-11)

    def test_tiny_motion_weights_outer_edge_and_underflow_refusal(self):
        _, params = fixture()
        params[:2] = 0
        params[7:9] = [1e300, 2e300]
        params[9] = np.nextafter(0.0, 1.0)
        point = np.array([[0.5e300, 20]], dtype=np.float64)
        delta = boundary.evaluate(point, params)
        expected = -((0.08 * point[0, 0]) * params[9]) * 0.5
        self.assertLess(delta[0, 0], 0)
        np.testing.assert_allclose(delta[0, 0], expected, rtol=1e-13, atol=0)
        np.testing.assert_array_equal(point - delta, point)
        _, params = fixture()
        params[:2] = 0
        params[6] = 1
        point = np.array([[1, 1e-50]], dtype=np.float64)
        delta = boundary.evaluate(point, params)
        self.assertLess(delta[0, 0], 0)
        np.testing.assert_array_equal(point - delta, point)
        for height, v in ((1, 1e-200), (1e300, 1e-100)):
            params[6] = height
            with self.assertRaises(ValueError):
                boundary.evaluate(np.array([[1, v]], dtype=np.float64), params)
        params[6] = 1
        near = np.nextafter(params[8], 0.0)
        delta = boundary.evaluate(np.array([[near, 1], [params[8], 1]], dtype=np.float64), params)
        self.assertLess(delta[0, 0], 0)
        self.assertFalse(np.any(delta[1].view(np.uint64)))

    def test_float32_conversion_does_not_promise_visible_pixel_change(self):
        points, params = fixture()
        params[9:11] = 1e-8
        delta = boundary.evaluate(points, params)
        self.assertLess(delta[0, 0], 0)
        self.assertNotEqual((points - delta)[0, 0], points[0, 0])
        np.testing.assert_array_equal((points - delta).astype(np.float32), points.astype(np.float32))

    def test_ffi_lengths_alias_values_and_late_underflow_are_atomic(self):
        points, params = fixture()
        output = np.full_like(points, 77)
        lib = boundary.native()
        status = lib.lrt_chin_shape_evaluate_v1(
            points.ctypes.data_as(boundary.P), points.size - 1,
            *boundary._pair(params), len(points), *boundary._pair(output))
        self.assertEqual(status, 1)
        np.testing.assert_array_equal(output, np.full_like(points, 77))
        before = points.copy()
        status = lib.lrt_chin_shape_evaluate_v1(
            *boundary._pair(points), *boundary._pair(params), len(points), *boundary._pair(points))
        self.assertEqual(status, 1)
        np.testing.assert_array_equal(points, before)
        params[9] = np.nan
        status = lib.lrt_chin_shape_evaluate_v1(
            *boundary._pair(points), *boundary._pair(params), len(points), *boundary._pair(output))
        self.assertEqual(status, 2)
        np.testing.assert_array_equal(output, np.full_like(points, 77))
        params[9] = np.nextafter(0.0, 1.0)
        points[...] = [[50, 80], [51, 80]]
        status = lib.lrt_chin_shape_evaluate_v1(
            *boundary._pair(points), *boundary._pair(params), len(points), *boundary._pair(output))
        self.assertEqual(status, 4)
        np.testing.assert_array_equal(output, np.full_like(points, 77))
