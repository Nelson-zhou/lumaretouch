# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: state/bridge contracts, not photographic acceptance.

Native doubles only write fixed private-output fixtures. They are not a Python
inverse solver. Installed-core cases skip when the already-shared core is absent;
none build, download or substitute a native library. No execution is claimed.
"""
import ctypes as C
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import chin_length_native as boundary
from lumaretouch_engine import chin_length_state as state
from lumaretouch_engine import lower_face_native as shared


def fixture():
    # An already-admitted example below-lips plane and H to chin, not anatomy
    # inference or an arbitrary height accepted on behalf of the runtime host.
    return (np.array([[50.0, 90.0], [50.0, 101.0]], dtype=np.float64),
            np.array([50.0, 80.0, 1.0, 0.0, 0.0, 1.0,
                      20.0, 15.0, 30.0, 0.5, 1.0], dtype=np.float64))


class RecordingNative:
    """Writes supplied constants; never calculates a deformation or inverse."""
    def __init__(self, output=None, status=0, on_enter=None):
        self.output = (np.zeros((2, 2), dtype=np.float64) if output is None
                       else np.asarray(output, dtype=np.float64))
        self.status, self.on_enter = status, on_enter
        self.calls, self.inputs, self.pointers = 0, [], []

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


class ChinLengthStateContracts(TestCase):
    def test_exact_identity_neutral_signed_amount_and_independent_presets(self):
        self.assertEqual(state.OP, 'lnx.chin_length.v1')
        self.assertEqual(state.CONTROL_ID, 'LNX-REF-PC-32466-C-44a42baef4')
        self.assertEqual(state.VERSION, 1)
        self.assertEqual((state.LENGTH_GAIN, state.TAIL), (0.08, 0.5))
        self.assertEqual(state.neutral(), {'version': 1, 'amount': 0.0})
        with patch.object(shared, 'native', side_effect=AssertionError('must not load')):
            self.assertEqual(state.check(None), state.neutral())
            self.assertFalse(state.active({'version': 1, 'amount': -0.0}))
            for amount in (-1, -0.125, 0.125, 1):
                original = {'version': 1, 'amount': amount}
                result = state.preset(original)
                self.assertIsNot(result, original)
                self.assertTrue(state.active(result))
                self.assertIs(type(result['amount']), float)
                self.assertEqual(result['amount'], amount)
                result['amount'] = 0.0
                self.assertEqual(original['amount'], amount)

    def test_strict_keys_versions_amounts_and_no_silent_conversion(self):
        for bad in (True, np.float64(0.2), np.int32(1), None, '0.2',
                    np.nan, np.inf, -np.inf, -1.01, 1.01, 10**1000):
            with self.subTest(amount=bad):
                with self.assertRaisesRegex(ValueError, '下巴长短'):
                    state.check({'version': 1, 'amount': bad})
        for bad in (True, 1.0, 0, 2, None):
            with self.assertRaisesRegex(ValueError, '下巴长短'):
                state.check({'version': bad, 'amount': 0})
        for key in ('face_id', 'landmarks', 'path', 'cache', 'mask', 'height',
                    'tail', 'linked', 'left', 'right'):
            with self.assertRaisesRegex(ValueError, '下巴长短'):
                state.check({**state.neutral(), key: 'not portable'})
        for value in ({}, {'version': 1}, [], (), 0):
            with self.assertRaisesRegex(ValueError, '下巴长短'):
                state.check(value)

    def test_neutral_coexistence_has_no_legacy_import_or_validation_dependency(self):
        original = state.neutral()
        with patch('builtins.__import__', side_effect=AssertionError('must not import')):
            result = state.check_coexistence(original, object())
        self.assertEqual(result, original)
        self.assertIsNot(result, original)

    def test_active_coexistence_uses_unchanged_legacy_checker_and_never_resets(self):
        from lumaretouch_engine.ops import deform as legacy
        recipe = {'version': 1, 'amount': -0.25}
        marker = object()
        with patch.object(legacy, 'check_amounts', return_value={'small_chin': 0.0}) as check:
            self.assertEqual(state.check_coexistence(recipe, marker), recipe)
            check.assert_called_once_with({'small_chin': marker})
        for amount in (-1.0, -0.25, 0.25, 1.0):
            with self.assertRaisesRegex(ValueError, '下巴长短'):
                state.check_coexistence(recipe, amount)
            self.assertEqual(recipe, {'version': 1, 'amount': -0.25})
        # The legacy checker remains authoritative, including its historical
        # coercion behavior. New state checking must not silently tighten it.
        self.assertEqual(state.check_coexistence(recipe, '0'), recipe)
        with patch.object(legacy, 'check_amounts', side_effect=ValueError('legacy validation')):
            with self.assertRaisesRegex(ValueError, 'legacy validation'):
                state.check_coexistence(recipe, 0.0)


class ChinLengthBridgeContracts(TestCase):
    def test_actual_shared_loader_controls_capability_without_new_module_probe(self):
        self.assertEqual((boundary.MAX_POINTS, boundary.PARAMS_LEN), (65536, 11))
        self.assertEqual((boundary.GAIN, boundary.TAIL), (0.08, 0.5))
        for error in (RuntimeError('ABI'), OSError('load'), AttributeError('symbol')):
            with patch.object(shared, 'native', side_effect=error):
                self.assertFalse(boundary.available())
                capability = state.capability()
            self.assertEqual(capability['chin_length_available'], False)
            self.assertIn('下巴长短', capability['chin_length_reason'])
            self.assertIn('共用', capability['chin_length_reason'])
        with patch.object(shared, 'native', return_value=object()):
            self.assertEqual(state.capability(), {'chin_length_available': True,
                                                 'chin_length_reason': None})

    def test_canonical_frame_uses_the_same_roundoff_and_handedness_policy(self):
        self.assertEqual(boundary.canonical_frame((1 + 1e-12, 0), (1e-12, 1 - 1e-12)),
                         ((1.0, 0.0), (-0.0, 1.0)))
        self.assertEqual(boundary.canonical_frame((0.6, 0.8), (0.8, -0.6)),
                         ((0.6, 0.8), (0.8, -0.6)))
        for right, down in (((1, 0), (1e-8, 1)), ((0, 0), (0, 1)),
                            ((np.inf, 0), (0, 1)), ((True, 0), (0, 1)),
                            ((1,), (0, 1)), (('1', 0), (0, 1))):
            with self.assertRaisesRegex(ValueError, '下巴长短'):
                boundary.canonical_frame(right, down)

    def test_shapes_dtypes_and_batch_bounds_refuse_before_snapshot_or_native(self):
        invalid = []
        for index in range(2):
            for dtype in (np.float32, np.int32, np.bool_, np.complex128, object, '>f8'):
                args = list(fixture())
                args[index] = args[index].astype(dtype)
                if args[index].dtype != np.float64:
                    invalid.append(args)
            for value in (fixture()[index].tolist(), fixture()[index][..., None]):
                args = list(fixture())
                args[index] = value
                invalid.append(args)
        for count in (0, boundary.MAX_POINTS + 1):
            invalid.append((np.empty((count, 2), dtype=np.float64), fixture()[1]))
        for length in (0, 10, 12):
            invalid.append((fixture()[0], np.empty(length, dtype=np.float64)))
        for args in invalid:
            with patch.object(shared, '_snapshot') as snapshot, patch.object(shared, 'native') as native:
                with self.assertRaisesRegex(ValueError, '下巴长短'):
                    boundary.evaluate(*args)
                snapshot.assert_not_called()
                native.assert_not_called()

    def test_fixed_tail_refuses_even_values_allowed_by_shared_abi_and_neutral(self):
        for tail in (0.25, 0.49999999999999994, 0.5000000000000001, 0.75, 1.0):
            for amount in (0.0, 1.0):
                points, params = fixture()
                params[9], params[10] = tail, amount
                before = params.copy()
                with patch.object(shared, 'evaluate') as evaluate:
                    with self.assertRaisesRegex(ValueError, '下巴长短.*0.5'):
                        boundary.evaluate(points, params)
                    evaluate.assert_not_called()
                np.testing.assert_array_equal(params, before)

    def test_tail_is_checked_on_private_snapshot_without_rewriting_parameters(self):
        points, params = fixture()
        before = params.copy()
        marker = object()
        def record(got_points, got_params):
            self.assertIs(got_points, points)
            self.assertFalse(np.shares_memory(params, got_params))
            self.assertFalse(got_params.flags.writeable)
            params[9], params[10] = 0.25, -1.0
            np.testing.assert_array_equal(got_params, before)
            return marker
        with patch.object(shared, 'evaluate', side_effect=record) as evaluate:
            self.assertIs(boundary.evaluate(points, params), marker)
            self.assertEqual(evaluate.call_count, 1)

    def test_snapshots_abi_and_owned_result_are_inherited_not_reimplemented(self):
        arrays = tuple(array[::-1].copy()[::-1] for array in fixture())
        before = tuple(array.copy() for array in arrays)
        def mutate_callers():
            for array in arrays:
                array[...] = 99.0
        fake = RecordingNative([[0.0, 0.5], [0.0, 0.125]], on_enter=mutate_callers)
        with patch.object(shared, 'native', return_value=fake):
            result = boundary.evaluate(*arrays)
        self.assertEqual(fake.calls, 1)
        for index, expected in enumerate(before):
            np.testing.assert_array_equal(fake.inputs[index], expected.ravel())
            self.assertNotEqual(fake.pointers[index], arrays[index].ctypes.data)
            self.assertFalse(np.shares_memory(result, arrays[index]))
        self.assertEqual(result.shape, (2, 2))
        self.assertEqual(result.dtype, np.float64)
        self.assertTrue(result.flags.owndata and result.flags.writeable and result.flags.c_contiguous)

    def test_nonfinite_frame_height_width_and_amount_refuse_before_loading(self):
        invalid = []
        for index, array in enumerate(fixture()):
            for offset in range(array.size):
                for bad in (np.nan, np.inf, -np.inf):
                    args = list(fixture())
                    args[1][10] = 0.0
                    args[index].flat[offset] = bad
                    invalid.append(args)
        for index, bad in ((2, 0), (2, 1.000001), (4, 1e-8), (6, 0), (6, -1),
                           (7, 0), (7, 30), (8, 14), (10, -1.01), (10, 1.01)):
            args = list(fixture())
            args[1][index] = bad
            invalid.append(args)
        for args in invalid:
            with patch.object(shared, 'native') as native:
                with self.assertRaisesRegex(ValueError, '下巴长短'):
                    boundary.evaluate(*args)
                native.assert_not_called()

    def test_status_and_postcondition_failures_discard_output_with_chin_name(self):
        for status in (1, 2, 3, 4, 5, 6, 123):
            expected = ValueError if status in (1, 2, 3, 4) else RuntimeError
            with patch.object(shared, 'native', return_value=RecordingNative(status=status)):
                with self.assertRaisesRegex(expected, '下巴长短'):
                    boundary.evaluate(*fixture())
        for output in ([[np.nan, 0], [0, 0]], [[0.01, 0], [0, 0]],
                       [[0, -0.1], [0, 0]], [[0, 2.0], [0, 0]]):
            with patch.object(shared, 'native', return_value=RecordingNative(output)):
                with self.assertRaisesRegex(RuntimeError, '下巴长短'):
                    boundary.evaluate(*fixture())

    def test_neutral_upper_and_support_edges_require_positive_zero_and_shared_core(self):
        for mode in ('neutral', 'upper', 'lateral', 'bottom', 'above'):
            points, params = fixture()
            if mode == 'neutral':
                params[10] = 0.0
            elif mode == 'upper':
                points[...] = [[50, 80], [60, 80]]
            elif mode == 'lateral':
                points[...] = [[80, 90], [20, 90]]
            elif mode == 'bottom':
                points[...] = [[50, 110], [50, 111]]
            else:
                points[...] = [[50, 79], [50, -100]]
            for bad in (0.01, -0.0):
                with patch.object(shared, 'native', return_value=RecordingNative([[0, bad], [0, 0]])):
                    with self.assertRaisesRegex(RuntimeError, '下巴长短'):
                        boundary.evaluate(points, params)
            with patch.object(shared, 'native', return_value=RecordingNative()):
                result = boundary.evaluate(points, params)
            self.assertFalse(np.any(result.view(np.uint64)))
        params[10] = 0.0
        with patch.object(shared, 'native', side_effect=RuntimeError('下庭 Rust 核心未安装')):
            with self.assertRaisesRegex(RuntimeError, '下巴长短共用的下庭 Rust'):
                boundary.evaluate(points, params)


class InstalledSharedCoreChinLengthContracts(TestCase):
    """Planned installed-core cases. Skip absent core, never build/download."""
    def setUp(self):
        if not boundary.available():
            self.skipTest('Shared chin-length Rust core unavailable; no build or fallback')

    def test_actual_chin_target_is_true_inverse_in_both_signed_directions(self):
        _, params = fixture()
        source = np.array([[50.0, 100.0]], dtype=np.float64)
        for amount in (-1.0, -0.25, 0.25, 1.0):
            params[10] = amount
            shift = (0.08 * params[6]) * amount
            target = source + [[0.0, shift]]
            delta = boundary.evaluate(target, params)
            np.testing.assert_allclose(delta, [[0.0, shift]], rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(target - delta, source, rtol=1e-13, atol=1e-13)
            np.testing.assert_array_equal(delta, shared.evaluate(target, params))

    def test_below_lips_interval_is_not_the_longer_nose_to_chin_interval(self):
        _, chin = fixture()
        lower = chin.copy()
        lower[1], lower[6] = 60.0, 40.0
        lips = np.array([[50.0, 75.0]], dtype=np.float64)
        np.testing.assert_array_equal(boundary.evaluate(lips, chin), np.zeros((1, 2)))
        self.assertGreater(shared.evaluate(lips, lower)[0, 1], 0.0)
        # Anatomy selection belongs to the runtime; the same numerical ABI
        # intentionally accepts either geometry and must not invent landmarks.

    def test_exact_support_zero_neutral_and_tiny_representable_delta(self):
        _, params = fixture()
        points = np.array([[50, 80], [50, 110], [80, 90], [20, 90]], dtype=np.float64)
        self.assertFalse(np.any(boundary.evaluate(points, params).view(np.uint64)))
        params[10] = 0.0
        self.assertFalse(np.any(boundary.evaluate(fixture()[0], params).view(np.uint64)))
        params[:2], params[6] = 0.0, 1e300
        params[10] = np.nextafter(0.0, 1.0)
        delta = boundary.evaluate(np.array([[0, 0.5e300]], dtype=np.float64), params)
        expected = ((0.08 * params[6]) * params[10]) * 0.5
        self.assertGreater(delta[0, 1], 0.0)
        np.testing.assert_allclose(delta[0, 1], expected, rtol=1e-13, atol=0.0)
