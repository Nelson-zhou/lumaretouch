# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: portable eye-symmetry and shared-native contracts.

Fixed-output doubles never compute eye deformation. Installed-core cases skip
when the existing shared library is absent; no build/download/fallback occurs.
These fixtures are not measured-source, photographic or product acceptance.
"""
import ctypes as C
import math
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import eye_shape_native as shared
from lumaretouch_engine import eye_symmetry_native as boundary
from lumaretouch_engine import eye_symmetry_state as state


def fixture():
    # Synthetic source-space points only, not source anatomy admission.
    return (np.array([[30., 50.], [70., 50.], [50., 56.],
                      [50., 44.], [50., 50.], [53., 50.]], dtype=np.float64),
            np.array([1., 0., 0., -1., 50., 50., 50., 50., 40., 12.],
                     dtype=np.float64))


class RecordingNative:
    """Writes supplied constants only, never implements a native control."""
    def __init__(self, output=None, status=0, on_enter=None):
        self.output = (np.zeros((6, 2), dtype=np.float64) if output is None
                       else np.asarray(output, dtype=np.float64))
        self.status, self.on_enter = status, on_enter
        self.calls, self.inputs, self.pointers = 0, [], []

    def lrt_eye_shape_controls(self, points, roles, count, frame, values, output):
        self.calls += 1
        if self.on_enter:
            self.on_enter()
        pairs = ((points, count * 2), (roles, count * 2),
                 (frame, 10), (values, 10))
        self.inputs = [np.ctypeslib.as_array(pointer, shape=(length,)).copy()
                       for pointer, length in pairs]
        self.pointers = [C.cast(pointer, C.c_void_p).value for pointer, _ in pairs]
        assert self.output.shape == (count, 2)
        C.memmove(output, self.output.ctypes.data, self.output.nbytes)
        return self.status


class EyeSymmetryStateContracts(TestCase):
    def test_exact_operation_ids_and_native_free_portable_state(self):
        self.assertEqual(state.OP, 'lnx.eye_symmetry.v1')
        self.assertEqual(state.VERSION, 1)
        self.assertEqual(state.CONTROL_IDS, {
            'family': 'LNX-REF-PC-32470-C-2745ac86f5',
            'horizontal': 'LNX-REF-PC-32470-C-a86e5c0175',
            'size': 'LNX-REF-PC-32470-C-4601eb7797',
            'reference': 'LNX-REF-PC-32470-C-118aa67e04',
        })
        self.assertEqual(state.POLICY,
                         'independent-head-axis-level-polygon-opening-area-v1')
        expected = {'version': 1, 'horizontal': 0.0, 'size': 0.0,
                    'reference': 'auto'}
        with patch.object(shared, 'native', side_effect=AssertionError('must not load')):
            self.assertEqual(state.neutral(), expected)
            self.assertEqual(state.check(None), expected)
            for reference in ('auto', 'left', 'right'):
                recipe = {**expected, 'reference': reference}
                self.assertFalse(state.active(recipe))
                copied = state.preset(recipe)
                self.assertEqual(copied, recipe)
                self.assertIsNot(copied, recipe)
                for key in ('horizontal', 'size'):
                    for amount in (0.125, 1):
                        result = state.check({**recipe, key: amount})
                        self.assertTrue(state.active(result))
                        self.assertIs(type(result[key]), float)
                self.assertFalse(state.active({**recipe, 'horizontal': -0.0}))
        self.assertIsNot(state.neutral(), state.neutral())

    def test_strict_strength_types_and_finite_bounds(self):
        class FloatSubclass(float):
            pass
        for key in ('horizontal', 'size'):
            for bad in (True, False, np.float64(.5), np.int32(1),
                        FloatSubclass(.5), None, '.5', np.nan, np.inf,
                        -np.inf, -.0001, 1.0001, 10**1000):
                with self.subTest(key=key, value=bad):
                    with self.assertRaisesRegex(ValueError, '眼睛对称'):
                        state.check({**state.neutral(), key: bad})

    def test_exact_keys_version_and_scalar_reference_never_capture_donor(self):
        class DictSubclass(dict):
            pass
        class StringSubclass(str):
            pass
        for bad in (True, 1.0, 0, 2, np.int64(1), None):
            with self.assertRaisesRegex(ValueError, '眼睛对称'):
                state.check({**state.neutral(), 'version': bad})
        for bad in ('Left', 'larger', '', True, None, 0, ['left'],
                    {'side': 'left'}, StringSubclass('left')):
            with self.assertRaisesRegex(ValueError, '眼睛对称'):
                state.check({**state.neutral(), 'reference': bad})
        for key in ('face_id', 'source_id', 'landmarks', 'donor', 'area',
                    'scale', 'shift', 'axis', 'path', 'cache', 'mask',
                    'linked', 'left', 'right', 'width', 'height'):
            with self.assertRaisesRegex(ValueError, '眼睛对称'):
                state.check({**state.neutral(), key: 'not portable'})
        for bad in ({}, {'version': 1}, [], (), 0, DictSubclass(state.neutral())):
            with self.assertRaisesRegex(ValueError, '眼睛对称'):
                state.check(bad)
        for missing in state.neutral():
            recipe = state.neutral()
            del recipe[missing]
            with self.assertRaisesRegex(ValueError, '眼睛对称'):
                state.check(recipe)


class EyeSymmetryBridgeContracts(TestCase):
    def test_capability_uses_actual_shared_loader_and_identifies_shared_core(self):
        self.assertEqual((boundary.MAX_POINTS, boundary.FRAME_LEN), (256, 10))
        self.assertEqual((boundary.SIZE_GAIN, boundary.POSITION_GAIN), (.12, .08))
        self.assertEqual(boundary.MAX_DISPLACEMENT_GAIN, .30)
        self.assertEqual(boundary.FRAME_TOLERANCE, 1e-6)
        for error in (RuntimeError('眼形 Rust ABI 不匹配'),
                      OSError('load'), AttributeError('symbol')):
            with patch.object(shared, 'native', side_effect=error):
                self.assertFalse(boundary.available())
                capability = state.capability()
                self.assertFalse(capability['eye_symmetry_available'])
                self.assertIn('眼睛对称共用的眼形 Rust', capability['eye_symmetry_reason'])
        with patch.object(shared, 'native', return_value=object()):
            self.assertEqual(state.capability(), {'eye_symmetry_available': True,
                                                  'eye_symmetry_reason': None})

    def test_real_loader_checks_abi_and_control_symbol_not_just_a_path(self):
        class Symbol:
            def __init__(self, value):
                self.value = value
            def __call__(self):
                return self.value
        bad_libraries = (SimpleNamespace(),
                         SimpleNamespace(lrt_eye_shape_abi=Symbol(2)),
                         SimpleNamespace(lrt_eye_shape_abi=Symbol(1)))
        for library in bad_libraries:
            shared.native.cache_clear()
            try:
                with patch.object(shared.Path, 'is_file', return_value=True), \
                        patch.object(shared.C, 'CDLL', return_value=library) as load:
                    self.assertFalse(boundary.available())
                    self.assertTrue(load.call_args.args[0].endswith('/bin/liblrt_eye_shape.so'))
            finally:
                shared.native.cache_clear()
        library = SimpleNamespace(lrt_eye_shape_abi=Symbol(1),
                                  lrt_eye_shape_controls=Symbol(0))
        shared.native.cache_clear()
        try:
            with patch.object(shared.Path, 'is_file', return_value=True), \
                    patch.object(shared.C, 'CDLL', return_value=library):
                self.assertTrue(boundary.available())
            self.assertEqual(library.lrt_eye_shape_controls.argtypes,
                             [shared.P, shared.P, C.c_size_t,
                              shared.P, shared.P, shared.P])
            self.assertEqual(library.lrt_eye_shape_controls.restype, C.c_int)
        finally:
            shared.native.cache_clear()

    def test_absent_file_or_load_error_is_not_a_python_fallback(self):
        for exists, error in ((False, None), (True, OSError('unloadable'))):
            shared.native.cache_clear()
            try:
                with patch.object(shared.Path, 'is_file', return_value=exists), \
                        patch.object(shared.C, 'CDLL', side_effect=error) as load:
                    self.assertFalse(boundary.available())
                    with self.assertRaises((RuntimeError, OSError)):
                        boundary.controls(*fixture(), scale=1., shift=0.)
                    if not exists:
                        load.assert_not_called()
            finally:
                shared.native.cache_clear()

    def test_shapes_dtypes_and_counts_refuse_before_copy_or_native(self):
        invalid = []
        for index in (0, 1):
            for dtype in (np.float32, np.int32, np.bool_, np.complex128, object, '>f8'):
                args = list(fixture())
                args[index] = args[index].astype(dtype)
                if args[index].dtype != np.float64 or not args[index].dtype.isnative:
                    invalid.append(args)
            for value in (fixture()[index].tolist(), fixture()[index][..., None],
                          fixture()[index].view(np.ma.MaskedArray)):
                args = list(fixture())
                args[index] = value
                invalid.append(args)
        for count in (0, 257):
            invalid.append((np.zeros((count, 2), np.float64), fixture()[1]))
        for length in (0, 9, 11):
            invalid.append((fixture()[0], np.zeros(length, np.float64)))
        for args in invalid:
            with patch.object(boundary, '_snapshot') as snapshot, \
                    patch.object(shared, 'native') as native:
                with self.assertRaisesRegex(ValueError, '眼睛对称'):
                    boundary.controls(*args, scale=1., shift=0.)
                snapshot.assert_not_called()
                native.assert_not_called()

    def test_only_exact_size_position_slots_and_zero_roles_are_delegated(self):
        points, frame = fixture()
        captured = []
        def record(p, roles, f, values):
            captured.extend((p, roles, f, values))
            self.assertFalse(any(a.flags.writeable for a in captured))
            self.assertTrue(all(a.flags.c_contiguous for a in captured))
            self.assertFalse(np.shares_memory(p, points))
            self.assertFalse(np.shares_memory(f, frame))
            np.testing.assert_array_equal(p, points)
            np.testing.assert_array_equal(f, frame)
            np.testing.assert_array_equal(roles, np.zeros_like(points))
            expected = np.zeros(10, np.float64)
            expected[0] = (1.06 - 1.) / .12
            expected[9] = .8 / (.08 * 40.)
            np.testing.assert_array_equal(values, expected)
            return np.zeros_like(p)
        with patch.object(shared, 'controls', side_effect=record) as native_controls:
            result = boundary.controls(points, frame, scale=1.06, shift=.8)
        self.assertEqual(native_controls.call_count, 1)
        self.assertEqual(result.shape, points.shape)
        self.assertFalse(any(np.shares_memory(result, a) for a in captured))

    def test_private_snapshots_survive_caller_mutation_at_native_entry(self):
        arrays = tuple(array[::-1].copy()[::-1] for array in fixture())
        before = tuple(array.copy() for array in arrays)
        def mutate_callers():
            for array in arrays:
                array[...] = 99.
        fake = RecordingNative(on_enter=mutate_callers)
        with patch.object(shared, 'native', return_value=fake):
            output = boundary.controls(*arrays, scale=1., shift=0.)
        self.assertEqual(fake.calls, 1)
        np.testing.assert_array_equal(fake.inputs[0], before[0].ravel())
        np.testing.assert_array_equal(fake.inputs[2], before[1])
        self.assertNotEqual(fake.pointers[0], arrays[0].ctypes.data)
        self.assertNotEqual(fake.pointers[2], arrays[1].ctypes.data)
        self.assertTrue(output.flags.owndata and output.flags.writeable and output.flags.c_contiguous)
        self.assertEqual(output.dtype, np.float64)

    def test_readonly_and_overlapping_inputs_are_independently_snapshotted(self):
        points, original_frame = fixture()
        storage = np.zeros(22, np.float64)
        storage[:12] = points.ravel()
        # This frame overlaps the last source point. The altered point is still
        # finite and the fixture is identity, so no source-anatomy claim follows.
        storage[10:20] = original_frame
        points, frame = storage[:12].reshape(6, 2), storage[10:20]
        before = points.copy(), frame.copy()
        storage.setflags(write=False)
        points.setflags(write=False)
        frame.setflags(write=False)
        fake = RecordingNative()
        with patch.object(shared, 'native', return_value=fake):
            output = boundary.controls(points, frame, scale=1., shift=0.)
        np.testing.assert_array_equal(points, before[0])
        np.testing.assert_array_equal(frame, before[1])
        self.assertNotEqual(fake.pointers[0], fake.pointers[2])
        self.assertFalse(np.shares_memory(output, storage))
        self.assertTrue(output.flags.writeable)

    def test_nonfinite_input_or_invalid_frame_refuses_even_for_identity(self):
        invalid = []
        for index, array in enumerate(fixture()):
            for offset in range(array.size):
                for bad in (np.nan, np.inf, -np.inf):
                    args = list(fixture())
                    args[index].flat[offset] = bad
                    invalid.append(args)
        for index, value in ((0, 0.), (0, 1.00001), (2, .0001),
                             (8, .999), (9, .999), (8, 0.), (9, -1.)):
            points, frame = fixture()
            frame[index] = value
            invalid.append((points, frame))
        for args in invalid:
            with patch.object(shared, 'native') as native:
                with self.assertRaisesRegex(ValueError, '眼睛对称'):
                    boundary.controls(*args, scale=1., shift=0.)
                native.assert_not_called()

    def test_scalar_types_bounds_and_underflow_refuse_without_clipping(self):
        for key in ('scale', 'shift'):
            for bad in (True, False, None, '1', np.float64(1),
                        np.int32(1), np.nan, np.inf, -np.inf, 10**1000):
                values = {'scale': 1., 'shift': 0., key: bad}
                with patch.object(shared, 'controls') as delegate:
                    with self.assertRaisesRegex(ValueError, '眼睛对称'):
                        boundary.controls(*fixture(), **values)
                    delegate.assert_not_called()
        for scale, shift in ((.879, 0.), (1.121, 0.), (1., 3.201), (1., -3.201)):
            with patch.object(shared, 'controls') as delegate:
                with self.assertRaisesRegex(ValueError, '眼睛对称'):
                    boundary.controls(*fixture(), scale=scale, shift=shift)
                delegate.assert_not_called()
        points, frame = fixture()
        frame[8] = 1e200
        with patch.object(shared, 'controls') as delegate:
            with self.assertRaisesRegex(ValueError, '丢失非零位移'):
                boundary.controls(points, frame, scale=1., shift=float(np.nextafter(0., 1.)))
            delegate.assert_not_called()

    def test_converted_float_endpoints_are_strict_and_never_clamped(self):
        for factor in (.88, np.nextafter(.88, 1.).item(),
                       np.nextafter(1.12, 1.).item(), 1.12):
            derived = (factor - 1.) / .12
            fake = RecordingNative()
            with patch.object(shared, 'native', return_value=fake):
                if abs(derived) > 1.:
                    with self.assertRaisesRegex(ValueError, '换算后的共享控制超界'):
                        boundary.controls(*fixture(), scale=factor, shift=0.)
                    self.assertEqual(fake.calls, 0)
                else:
                    boundary.controls(*fixture(), scale=factor, shift=0.)
                    self.assertEqual(fake.inputs[3][0], derived)

    def test_native_status_is_atomic_failure_not_missing_zero_displacement(self):
        for status in (1, 2, 3, 4, 5):
            fake = RecordingNative(np.full((6, 2), .25), status=status)
            with patch.object(shared, 'native', return_value=fake):
                with self.assertRaisesRegex(ValueError, f'眼睛对称.*{status}'):
                    boundary.controls(*fixture(), scale=1., shift=.8)
                self.assertEqual(fake.calls, 1)
        for scale, shift in ((1., 0.), (1.06, .8)):
            # The boundary cannot infer source-level symmetry from zero output.
            # Target correctness of a nonidentity request is a host audit.
            fake = RecordingNative()
            with patch.object(shared, 'native', return_value=fake):
                result = boundary.controls(*fixture(), scale=scale, shift=shift)
            np.testing.assert_array_equal(result, np.zeros((6, 2)))
            self.assertEqual(fake.calls, 1)

    def test_bad_output_shape_dtype_finite_bound_or_identity_is_refused(self):
        bad_arrays = (np.zeros((6, 1), np.float64), np.zeros((6, 2), np.float32),
                      np.full((6, 2), np.nan), np.full((6, 2), np.inf),
                      np.full((6, 2), 13.), [[0., 0.]] * 6)
        for result in bad_arrays:
            with patch.object(shared, 'controls', return_value=result):
                with self.assertRaises((ValueError, RuntimeError)):
                    boundary.controls(*fixture(), scale=1., shift=.8)
        with patch.object(shared, 'controls', return_value=np.full((6, 2), .01)):
            with self.assertRaisesRegex(RuntimeError, '恒等控制'):
                boundary.controls(*fixture(), scale=1., shift=0.)

    def test_published_output_is_owned_even_when_delegate_returns_input_view(self):
        view = np.zeros((12, 2), np.float64)[::2]
        view.setflags(write=False)
        with patch.object(shared, 'controls', return_value=view):
            result = boundary.controls(*fixture(), scale=1., shift=0.)
        self.assertFalse(np.shares_memory(result, view))
        self.assertTrue(result.flags.owndata and result.flags.writeable and result.flags.c_contiguous)


class EyeSymmetryInstalledCoreContracts(TestCase):
    def setUp(self):
        if not boundary.available():
            self.skipTest('AUTHORED / UNRUN: shared eye core absent; never built or substituted')

    def test_exact_identity_requires_real_native_and_is_exact_zero(self):
        result = boundary.controls(*fixture(), scale=1., shift=0.)
        np.testing.assert_array_equal(result, np.zeros((6, 2), np.float64))

    def test_signed_translation_and_isotropic_scale_are_not_spacing_or_lid_height(self):
        points, frame = fixture()
        for shift in (-.8, .8):
            result = boundary.controls(points, frame, scale=1., shift=shift)
            np.testing.assert_allclose(result, np.tile([0., -shift], (6, 1)),
                                       rtol=0., atol=2e-14)
        for scale in (.94, 1.06):
            result = boundary.controls(points, frame, scale=scale, shift=0.)
            expected = (points - frame[4:6]) * (scale - 1.)
            np.testing.assert_allclose(result, expected, rtol=1e-14, atol=2e-14)
            np.testing.assert_array_equal(result[4], [0., 0.])
            self.assertGreater(abs(result[0, 0]), 0.)
            self.assertGreater(abs(result[2, 1]), 0.)

    def test_roll_mirror_uniform_scale_translation_covariance(self):
        points, frame = fixture()
        original = boundary.controls(points, frame, scale=1.06, shift=.8)
        angle = .37
        rotation = np.array([[math.cos(angle), -math.sin(angle)],
                             [math.sin(angle), math.cos(angle)]], np.float64)
        for mirror in (np.eye(2), np.diag([-1., 1.])):
            linear = rotation @ mirror
            for units in (.75, 2.):
                translation = np.array([103., -27.])
                moved_points = points @ linear.T * units + translation
                moved_frame = frame.copy()
                moved_frame[:2] = linear @ frame[:2]
                moved_frame[2:4] = linear @ frame[2:4]
                moved_frame[4:6] = linear @ frame[4:6] * units + translation
                moved_frame[6:8] = linear @ frame[6:8] * units + translation
                moved_frame[8:] *= units
                result = boundary.controls(moved_points, moved_frame,
                                           scale=1.06, shift=.8 * units)
                np.testing.assert_allclose(result, original @ linear.T * units,
                                           rtol=2e-13, atol=2e-13)

    def test_point_count_limits_do_not_require_any_new_native_interface(self):
        _, frame = fixture()
        for count in (1, 256):
            points = np.tile(frame[4:6], (count, 1))
            result = boundary.controls(points, frame, scale=1., shift=.8)
            self.assertEqual(result.shape, (count, 2))
            np.testing.assert_allclose(result, np.tile([0., -.8], (count, 1)),
                                       rtol=0., atol=2e-14)
