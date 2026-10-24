# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: portable state and shared-native boundary contracts.

Fixed-output doubles are not a deformation solver. Installed-core cases skip
when the existing shared core is absent; none compile, download or substitute
a library. Numerical fixtures are not source anatomy or photographic evidence.
"""
import ctypes as C
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import mid_face_native as shared
from lumaretouch_engine import philtrum_native as boundary
from lumaretouch_engine import philtrum_state as state


def fixture():
    # Hypothetically admitted origin/H/extent only; the runtime must measure
    # all nose/lip/retained points rather than adopting these example values.
    return (np.array([[50.0, 84.0], [65.0, 100.0]], dtype=np.float64),
            np.array([50.0, 80.0, 1.0, 0.0, 0.0, 1.0,
                      8.0, 20.0, 40.0, 6.0, 2.5, 1.0], dtype=np.float64))


class RecordingNative:
    """Writes supplied constants; never calculates a forward or inverse map."""
    def __init__(self, output=None, status=0, on_enter=None):
        self.output = (np.zeros((2, 2), dtype=np.float64) if output is None
                       else np.asarray(output, dtype=np.float64))
        self.status, self.on_enter = status, on_enter
        self.calls, self.inputs, self.pointers = 0, [], []

    def lrt_mid_face_evaluate_v1(self, points, points_len, params, params_len,
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


class PhiltrumStateContracts(TestCase):
    def test_exact_control_operation_and_native_free_portable_signed_state(self):
        self.assertEqual(state.OP, 'lnx.philtrum.v1')
        self.assertEqual(state.CONTROL_ID, 'LNX-REF-PC-32466-C-2605502c27')
        self.assertEqual(state.VERSION, 1)
        self.assertEqual(state.POLICY, 'monotone-head-axis-nose-safe-philtrum-length-v1')
        self.assertEqual((state.LENGTH_GAIN, state.TAIL_FACTOR), (0.08, 0.5))
        self.assertEqual((state.MIN_TAIL, state.MAX_TAIL), (0.25, 4.0))
        self.assertEqual((state.MIN_PLATEAU_END, state.MAX_PLATEAU_END), (1.25, 8.0))
        self.assertEqual(state.neutral(), {'version': 1, 'amount': 0.0})
        with patch.object(shared, 'native', side_effect=AssertionError('must not load')):
            self.assertEqual(state.check(None), state.neutral())
            self.assertFalse(state.active(None))
            self.assertFalse(state.active({'version': 1, 'amount': -0.0}))
            for amount in (-1, -0.125, 0.125, 1):
                original = {'version': 1, 'amount': amount}
                result = state.preset(original)
                self.assertIsNot(result, original)
                self.assertIs(type(result['amount']), float)
                self.assertEqual(result['amount'], amount)
                self.assertTrue(state.active(result))
                result['amount'] = 0.0
                self.assertEqual(original['amount'], amount)
        self.assertIsNot(state.neutral(), state.neutral())

    def test_strict_keys_versions_and_amounts_never_coerce_or_capture_geometry(self):
        for bad in (True, np.float64(0.2), np.int32(1), None, '0.2',
                    np.nan, np.inf, -np.inf, -1.01, 1.01, 10**1000):
            with self.subTest(amount=bad):
                with self.assertRaisesRegex(ValueError, '人中'):
                    state.check({'version': 1, 'amount': bad})
        for bad in (True, 1.0, 0, 2, None):
            with self.assertRaisesRegex(ValueError, '人中'):
                state.check({'version': bad, 'amount': 0})
        for key in ('face_id', 'landmarks', 'path', 'cache', 'mask', 'height',
                    'tail', 'plateau_end', 'nose', 'lips', 'linked', 'left', 'right'):
            with self.assertRaisesRegex(ValueError, '人中'):
                state.check({**state.neutral(), key: 'not portable'})
        for value in ({}, {'version': 1}, [], (), 0):
            with self.assertRaisesRegex(ValueError, '人中'):
                state.check(value)


class PhiltrumBridgeContracts(TestCase):
    def test_constants_and_capability_reuse_actual_shared_loader(self):
        self.assertEqual((boundary.MAX_POINTS, boundary.PARAMS_LEN), (65536, 12))
        self.assertEqual((boundary.GAIN, boundary.TAIL_FACTOR), (0.08, 0.5))
        self.assertEqual((boundary.MIN_TAIL, boundary.MAX_TAIL), (0.25, 4.0))
        self.assertEqual((boundary.MIN_PLATEAU_END, boundary.MAX_PLATEAU_END), (1.25, 8.0))
        self.assertEqual(boundary.MIN_FORWARD_DERIVATIVE, 0.4)
        for error in (RuntimeError('ABI'), OSError('load'), AttributeError('symbol')):
            with patch.object(shared, 'native', side_effect=error):
                self.assertFalse(boundary.available())
                capability = state.capability()
            self.assertEqual(capability['philtrum_available'], False)
            self.assertIn('人中', capability['philtrum_reason'])
            self.assertIn('共用的中庭 Rust', capability['philtrum_reason'])
        with patch.object(shared, 'native', return_value=object()):
            self.assertEqual(state.capability(), {'philtrum_available': True,
                                                 'philtrum_reason': None})

    def test_real_loader_checks_shared_abi_and_symbol_not_a_philtrum_binary(self):
        class Symbol:
            def __init__(self, value):
                self.value = value
            def __call__(self):
                return self.value
        for lib in (SimpleNamespace(lrt_mid_face_abi=Symbol(2)),
                    SimpleNamespace(lrt_mid_face_abi=Symbol(1))):
            shared.native.cache_clear()
            try:
                with patch.object(shared.Path, 'is_file', return_value=True), \
                        patch.object(shared.C, 'CDLL', return_value=lib) as loader:
                    self.assertFalse(boundary.available())
                    self.assertTrue(loader.call_args.args[0].endswith('/bin/liblrt_mid_face.so'))
            finally:
                shared.native.cache_clear()
        lib = SimpleNamespace(lrt_mid_face_abi=Symbol(1),
                              lrt_mid_face_evaluate_v1=Symbol(0))
        shared.native.cache_clear()
        try:
            with patch.object(shared.Path, 'is_file', return_value=True), \
                    patch.object(shared.C, 'CDLL', return_value=lib):
                self.assertTrue(boundary.available())
                self.assertEqual(state.capability()['philtrum_available'], True)
            self.assertEqual(lib.lrt_mid_face_evaluate_v1.argtypes,
                             [shared.P, C.c_size_t] * 2 +
                             [C.c_size_t, shared.P, C.c_size_t])
            self.assertEqual(lib.lrt_mid_face_evaluate_v1.restype, C.c_int32)
        finally:
            shared.native.cache_clear()

    def test_canonical_frame_preserves_shared_roundoff_and_handedness_policy(self):
        self.assertEqual(boundary.canonical_frame((1 + 1e-12, 0), (1e-12, 1 - 1e-12)),
                         ((1.0, 0.0), (-0.0, 1.0)))
        self.assertEqual(boundary.canonical_frame((0.6, 0.8), (0.8, -0.6)),
                         ((0.6, 0.8), (0.8, -0.6)))
        for right, down in (((1, 0), (1e-8, 1)), ((0, 0), (0, 1)),
                            ((np.inf, 0), (0, 1)), ((True, 0), (0, 1)),
                            ((1,), (0, 1)), (('1', 0), (0, 1))):
            with self.assertRaisesRegex(ValueError, '人中'):
                boundary.canonical_frame(right, down)

    def test_shapes_dtypes_and_batch_bounds_refuse_before_any_snapshot_or_native(self):
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
        for length in (0, 11, 13):
            invalid.append((fixture()[0], np.empty(length, dtype=np.float64)))
        for args in invalid:
            with patch.object(shared, '_snapshot') as snapshot, patch.object(shared, 'native') as native:
                with self.assertRaisesRegex(ValueError, '人中'):
                    boundary.evaluate(*args)
                snapshot.assert_not_called()
                native.assert_not_called()

    def test_derived_tail_is_exact_for_each_measured_plateau_and_not_replaced(self):
        for plateau in (1.25, 1.5, 2.0, 3.3, 6.0, np.nextafter(8.0, 0.0), 8.0):
            for amount in (0.0, 1.0):
                points, params = fixture()
                params[9], params[11] = plateau, amount
                expected_tail = max(0.25, 0.5 * (float(params[9]) - 1.0))
                params[10] = expected_tail
                before = params.copy()
                marker = object()
                def record(got_points, got_params):
                    self.assertIs(got_points, points)
                    np.testing.assert_array_equal(got_params.view(np.uint64), before.view(np.uint64))
                    return marker
                with patch.object(shared, 'evaluate', side_effect=record):
                    self.assertIs(boundary.evaluate(points, params), marker)
                np.testing.assert_array_equal(params, before)
                for wrong in (np.nextafter(expected_tail, 0.0),
                              np.nextafter(expected_tail, np.inf), 4.0):
                    params[10] = wrong
                    rejected = params.copy()
                    with patch.object(shared, 'evaluate') as evaluate:
                        with self.assertRaisesRegex(ValueError, '人中'):
                            boundary.evaluate(points, params)
                        evaluate.assert_not_called()
                    np.testing.assert_array_equal(params, rejected)

    def test_plateau_bounds_and_short_gap_are_refused_not_renormalized(self):
        # Pure numerical ratios, not a claim about typical clinical dimensions.
        for extent, height in ((40.0, 4.0), (1.0, 1.0), (64.0001, 8.0),
                               (np.nextafter(64.0, np.inf), 8.0),
                               (np.nextafter(10.0, 0.0), 8.0)):
            points, params = fixture()
            params[6], params[9] = height, extent / height
            params[10] = max(0.25, 0.5 * (params[9] - 1.0))
            before = params.copy()
            with patch.object(shared, 'evaluate') as evaluate, patch.object(shared, 'native') as native:
                with self.assertRaisesRegex(ValueError, '人中.*plateau_end'):
                    boundary.evaluate(points, params)
                evaluate.assert_not_called()
                native.assert_not_called()
            np.testing.assert_array_equal(params, before)

    def test_policy_uses_private_snapshot_not_mutable_caller_or_rewritten_values(self):
        points, params = fixture()
        before = params.copy()
        marker = object()
        def record(got_points, got_params):
            self.assertIs(got_points, points)
            self.assertFalse(np.shares_memory(params, got_params))
            self.assertFalse(got_params.flags.writeable)
            params[6], params[9], params[10], params[11] = 80.0, 2.0, 0.5, -1.0
            np.testing.assert_array_equal(got_params, before)
            return marker
        with patch.object(shared, 'evaluate', side_effect=record) as evaluate:
            self.assertIs(boundary.evaluate(points, params), marker)
            self.assertEqual(evaluate.call_count, 1)

    def test_tail_policy_reads_snapshot_after_copy_not_subsequently_changed_caller(self):
        points, params = fixture()
        before = params.copy()
        validate = shared._parameters
        marker = object()
        def validate_after_copy(got_params):
            self.assertFalse(np.shares_memory(params, got_params))
            params[9], params[10] = 2.0, 4.0
            return validate(got_params)
        def record(got_points, got_params):
            np.testing.assert_array_equal(got_params, before)
            return marker
        with patch.object(shared, '_parameters', side_effect=validate_after_copy), \
                patch.object(shared, 'evaluate', side_effect=record):
            self.assertIs(boundary.evaluate(points, params), marker)

    def test_shared_snapshots_abi_and_owned_output_are_inherited(self):
        arrays = tuple(array[::-1].copy()[::-1] for array in fixture())
        before = tuple(array.copy() for array in arrays)
        def mutate_callers():
            for array in arrays:
                array[...] = 99.0
        fake = RecordingNative([[0.0, 0.25], [0.0, 0.125]], on_enter=mutate_callers)
        with patch.object(shared, 'native', return_value=fake):
            output = boundary.evaluate(*arrays)
        self.assertEqual(fake.calls, 1)
        for index, expected in enumerate(before):
            np.testing.assert_array_equal(fake.inputs[index], expected.ravel())
            self.assertNotEqual(fake.pointers[index], arrays[index].ctypes.data)
            self.assertFalse(np.shares_memory(output, arrays[index]))
        self.assertEqual(output.shape, (2, 2))
        self.assertEqual(output.dtype, np.float64)
        self.assertTrue(output.flags.owndata and output.flags.writeable and output.flags.c_contiguous)

    def test_readonly_inputs_are_accepted_without_modification(self):
        points, params = fixture()
        expected = (points.copy(), params.copy())
        points.setflags(write=False)
        params.setflags(write=False)
        with patch.object(shared, 'native', return_value=RecordingNative()):
            output = boundary.evaluate(points, params)
        np.testing.assert_array_equal(points, expected[0])
        np.testing.assert_array_equal(params, expected[1])
        self.assertTrue(output.flags.writeable)
        self.assertFalse(np.shares_memory(output, points))

    def test_nonfinite_inputs_refuse_everywhere_even_for_direct_neutral(self):
        for index, array in enumerate(fixture()):
            for offset in range(array.size):
                for bad in (np.nan, np.inf, -np.inf):
                    args = list(fixture())
                    args[1][11] = 0.0
                    args[index].flat[offset] = bad
                    with patch.object(shared, 'native') as native:
                        with self.assertRaisesRegex(ValueError, '人中'):
                            boundary.evaluate(*args)
                        native.assert_not_called()

    def test_invalid_frame_height_widths_range_and_tail_never_load(self):
        for index, bad in ((2, 0), (2, 1.000001), (4, 1e-8), (6, 0), (6, -1),
                           (7, 0), (7, 40), (8, 19), (9, 1.249), (9, 8.001),
                           (10, 0.249), (10, 4.001), (11, -1.01), (11, 1.01)):
            points, params = fixture()
            params[index] = bad
            with patch.object(shared, 'native') as native:
                with self.assertRaisesRegex(ValueError, '人中'):
                    boundary.evaluate(points, params)
                native.assert_not_called()

    def test_every_native_failure_discards_output_and_names_philtrum(self):
        for status in (1, 2, 3, 4, 5, 6, 123):
            expected = ValueError if status in (1, 2, 3, 4) else RuntimeError
            with patch.object(shared, 'native', return_value=RecordingNative(status=status)):
                with self.assertRaisesRegex(expected, '人中共用的中庭 Rust'):
                    boundary.evaluate(*fixture())

    def test_nonfinite_lateral_wrong_sign_and_excessive_outputs_are_discarded(self):
        invalid = [[[bad, 0], [0, 0]] for bad in (np.nan, np.inf, -np.inf)]
        invalid += [[[0.01, 0], [0, 0]], [[0, -0.1], [0, 0]], [[0, 0.65], [0, 0]]]
        for output in invalid:
            with patch.object(shared, 'native', return_value=RecordingNative(output)):
                with self.assertRaisesRegex(RuntimeError, '人中'):
                    boundary.evaluate(*fixture())
        points, params = fixture()
        params[11] = -1.0
        with patch.object(shared, 'native', return_value=RecordingNative([[0, 0.1], [0, 0]])):
            with self.assertRaisesRegex(RuntimeError, '人中'):
                boundary.evaluate(points, params)

    def test_neutral_nose_halfplane_and_support_edges_require_positive_zero(self):
        for mode in ('neutral', 'upper', 'lateral', 'bottom', 'above'):
            points, params = fixture()
            if mode == 'neutral':
                params[11] = 0.0
            elif mode == 'upper':
                points[...] = [[50, 80], [60, 80]]
            elif mode == 'lateral':
                points[...] = [[90, 84], [10, 84]]
            elif mode == 'bottom':
                points[...] = [[50, 148], [50, 149]]
            else:
                points[...] = [[50, 79], [50, -100]]
            for bad in (0.01, -0.0):
                with patch.object(shared, 'native', return_value=RecordingNative([[0, bad], [0, 0]])):
                    with self.assertRaisesRegex(RuntimeError, '人中'):
                        boundary.evaluate(points, params)
            with patch.object(shared, 'native', return_value=RecordingNative()):
                output = boundary.evaluate(points, params)
            self.assertFalse(np.any(output.view(np.uint64)))

    def test_direct_neutral_still_requires_shared_core_without_fallback(self):
        points, params = fixture()
        params[11] = 0.0
        with patch.object(shared, 'native', side_effect=RuntimeError('中庭 Rust 核心未安装')):
            with self.assertRaisesRegex(RuntimeError, '人中共用的中庭 Rust'):
                boundary.evaluate(points, params)


class InstalledSharedCorePhiltrumContracts(TestCase):
    """Planned installed-core cases only. Skip absent core, never build/download."""
    def setUp(self):
        if not boundary.available():
            self.skipTest('Shared philtrum Rust core unavailable; no build or fallback')

    def test_lips_lowerface_plateau_translates_rigidly_in_both_directions(self):
        _, params = fixture()
        sources = np.array([[35, 88], [50, 96], [65, 120], [60, 128]], dtype=np.float64)
        for amount in (-1.0, -0.25, 0.25, 1.0):
            params[11] = amount
            shift = (0.08 * params[6]) * amount
            targets = sources + [[0.0, shift]]
            delta = boundary.evaluate(targets, params)
            np.testing.assert_allclose(delta, np.tile([0.0, shift], (4, 1)), rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(targets - delta, sources, rtol=1e-13, atol=1e-13)
            np.testing.assert_allclose(np.diff(targets, axis=0), np.diff(sources, axis=0),
                                       rtol=1e-13, atol=1e-13)
            np.testing.assert_array_equal(delta, shared.evaluate(targets, params))
            self.assertEqual(np.sign(delta[0, 1]), np.sign(amount))
            if amount < 0:
                self.assertLess(targets[0, 1], params[1] + params[6])

    def test_nose_safe_interval_is_distinct_from_eye_to_nose_midface(self):
        _, philtrum = fixture()
        midface = philtrum.copy()
        midface[1], midface[6], midface[9], midface[10] = 40.0, 40.0, 2.0, 0.5
        nose_points = np.array([[45, 68], [50, 75], [55, 80]], dtype=np.float64)
        self.assertFalse(np.any(boundary.evaluate(nose_points, philtrum).view(np.uint64)))
        self.assertTrue(np.all(shared.evaluate(nose_points, midface)[:, 1] > 0.0))
        # The shared ABI intentionally has no anatomy labels. Runtime selection
        # must prove the measured gap rather than pass eye-to-nose geometry here.

    def test_measured_nose_to_lip_interval_changes_additively_not_by_midface_ratio(self):
        _, params = fixture()
        nose = np.array([[50.0, 75.0]], dtype=np.float64)
        lip = np.array([[50.0, 90.0]], dtype=np.float64)
        original_interval = lip[0, 1] - nose[0, 1]
        self.assertNotEqual(original_interval, params[6])
        for amount in (-1.0, -0.25, 0.25, 1.0):
            params[11] = amount
            shift = (0.08 * params[6]) * amount
            target = lip + [[0, shift]]
            np.testing.assert_allclose(target - boundary.evaluate(target, params), lip,
                                       rtol=1e-13, atol=1e-13)
            self.assertFalse(np.any(boundary.evaluate(nose, params).view(np.uint64)))
            self.assertAlmostEqual(target[0, 1] - nose[0, 1], original_interval + shift)

    def test_mid_rise_known_source_target_requires_true_inverse_not_negated_forward(self):
        _, params = fixture()
        source = np.array([[50.0, 84.0]], dtype=np.float64)
        for amount in (-1.0, -0.25, 0.25, 1.0):
            params[11] = amount
            # S(.5)=.5 is an analytic fixture, not an alternate inverse solver.
            shift = ((0.08 * params[6]) * amount) * 0.5
            target = source + [[0.0, shift]]
            delta = boundary.evaluate(target, params)
            np.testing.assert_allclose(delta, [[0.0, shift]], rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(target - delta, source, rtol=1e-13, atol=1e-13)
            self.assertGreater(abs(target[0, 1] - source[0, 1]), 0.0)

    def test_support_edges_neutral_and_tiny_representable_physical_shift(self):
        _, params = fixture()
        points = np.array([[50, 80], [50, 148], [90, 84], [10, 84]], dtype=np.float64)
        self.assertFalse(np.any(boundary.evaluate(points, params).view(np.uint64)))
        params[11] = 0.0
        self.assertFalse(np.any(boundary.evaluate(fixture()[0], params).view(np.uint64)))
        params[:2], params[6] = 0.0, 1e300
        params[11] = np.nextafter(0.0, 1.0)
        delta = boundary.evaluate(np.array([[0, 0.5e300]], dtype=np.float64), params)
        expected = ((0.08 * params[6]) * params[11]) * 0.5
        self.assertGreater(delta[0, 1], 0.0)
        np.testing.assert_allclose(delta[0, 1], expected, rtol=1e-13, atol=0.0)

    def test_roll_scaling_translation_and_both_handednesses_share_same_inverse(self):
        points, params = fixture()
        reference = boundary.evaluate(points, params)
        for right, down in (((0.6, 0.8), (-0.8, 0.6)), ((0.6, 0.8), (0.8, -0.6))):
            matrix = np.array([right, down], dtype=np.float64)
            for scale in (0.5, 2.0):
                offset = np.array([120.0, -70.0], dtype=np.float64)
                transformed = params.copy()
                transformed[:2] = scale * params[:2] @ matrix + offset
                transformed[2:4], transformed[4:6] = right, down
                transformed[6:9] *= scale
                queries = scale * points @ matrix + offset
                actual = boundary.evaluate(queries, transformed)
                np.testing.assert_allclose(actual, scale * reference @ matrix,
                                           rtol=1e-11, atol=1e-12)
