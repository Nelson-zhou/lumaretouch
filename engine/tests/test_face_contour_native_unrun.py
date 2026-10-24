# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No native, numerical, visual or product acceptance claim.

Boundary stubs verify host validation, not the Rust algorithm. The installed-core
fixture class requires the separately built library and never builds/downloads it.
"""
import ctypes as C
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import face_contour_native as boundary
from lumaretouch_engine import face_contour_state as state


def fixture():
    return (np.array([[80.0, 40.0], [20.0, 40.0]], dtype=np.float64),
            np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64),
            np.array([1.0, -1.0], dtype=np.float64),
            np.array([1.0, 0.0, 0.0, -1.0, 50.0, 60.0, 100.0], dtype=np.float64),
            np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64))


class RecordingNative:
    """Fixed fixture output only, not a second contour implementation."""
    def __init__(self, result=None, status=0, on_enter=None):
        self.result = (np.array([[3.5, 0.0], [-3.5, 0.0]], dtype=np.float64)
                       if result is None else np.asarray(result, dtype=np.float64))
        self.status = status
        self.on_enter = on_enter
        self.inputs = []
        self.pointers = []
        self.calls = 0

    def lrt_face_contour_controls_v1(
            self, points, points_len, roles, roles_len, sides, sides_len,
            frame, frame_len, values, values_len, count, output, output_len):
        self.calls += 1
        if self.on_enter:
            self.on_enter()
        pairs = ((points, points_len), (roles, roles_len), (sides, sides_len),
                 (frame, frame_len), (values, values_len))
        self.inputs = [np.ctypeslib.as_array(pointer, shape=(length,)).copy()
                       for pointer, length in pairs]
        self.pointers = [C.cast(pointer, C.c_void_p).value for pointer, _ in pairs]
        assert count * 2 == output_len == self.result.size
        C.memmove(output, self.result.ctypes.data, self.result.nbytes)
        return self.status


class FaceContourBoundaryContracts(TestCase):
    def test_snapshots_are_owned_contiguous_read_only_and_independent(self):
        arrays = fixture()
        for original in arrays:
            view = original[::-1]
            expected = view.copy()
            snapshot = boundary._snapshot(view)
            self.assertTrue(snapshot.flags.owndata)
            self.assertTrue(snapshot.flags.c_contiguous)
            self.assertFalse(snapshot.flags.writeable)
            self.assertFalse(np.shares_memory(snapshot, original))
            original[...] = 99
            np.testing.assert_array_equal(snapshot, expected)

    def test_noncontiguous_inputs_have_independent_native_snapshots(self):
        arrays = tuple(array[::-1].copy()[::-1] for array in fixture())
        before = tuple(array.copy() for array in arrays)
        def mutate_callers():
            for array in arrays:
                array[...] = 99
        fake = RecordingNative(on_enter=mutate_callers)
        with patch.object(boundary, 'native', return_value=fake):
            result = boundary.controls(*arrays)
        self.assertEqual(fake.calls, 1)
        for index, expected in enumerate(before):
            np.testing.assert_array_equal(fake.inputs[index], expected.ravel())
            self.assertNotEqual(fake.pointers[index], arrays[index].ctypes.data)
            self.assertFalse(np.shares_memory(result, arrays[index]))
        self.assertEqual(result.dtype, np.float64)
        self.assertTrue(result.flags.owndata)
        self.assertTrue(result.flags.c_contiguous)
        self.assertTrue(result.flags.writeable)

    def test_input_shapes_and_dtypes_fail_before_any_snapshot_or_native_load(self):
        invalid = []
        for index in range(5):
            for dtype in (np.float32, np.int32, np.bool_, np.complex128, object):
                args = list(fixture())
                args[index] = args[index].astype(dtype)
                invalid.append(args)
            args = list(fixture())
            args[index] = args[index].tolist()
            invalid.append(args)
            args = list(fixture())
            args[index] = args[index][..., None]
            invalid.append(args)
        for count in (0, 257):
            args = list(fixture())
            args[0] = np.empty((count, 2), dtype=np.float64)
            invalid.append(args)
        for args in invalid:
            with self.subTest(shapes=[getattr(a, 'shape', None) for a in args]):
                with patch.object(boundary, '_snapshot') as snapshot, \
                        patch.object(boundary, 'native') as native:
                    with self.assertRaises(ValueError):
                        boundary.controls(*args)
                    snapshot.assert_not_called()
                    native.assert_not_called()

    def test_nonfinite_every_input_is_rejected_even_when_controls_are_neutral(self):
        for index in range(5):
            for bad in (np.nan, np.inf, -np.inf):
                args = list(fixture())
                args[4][...] = 0
                args[index].flat[-1] = bad
                with patch.object(boundary, 'native') as native:
                    with self.assertRaises(ValueError):
                        boundary.controls(*args)
                    native.assert_not_called()

    def test_ranges_frame_and_absolute_budget_reject_before_native_load(self):
        invalid = []
        for index, offset, bad in ((1, 0, -0.01), (1, 0, 1.01),
                                   (2, 0, 0), (2, 0, 0.5), (2, 0, 2),
                                   (4, 0, -1.01), (4, 0, 1.01),
                                   (3, 0, 0), (3, 3, 0), (3, 6, 0), (3, 6, -1)):
            args = list(fixture())
            args[index].flat[offset] = bad
            invalid.append(args)
        args = list(fixture())
        args[3][2:4] = [1, 0]
        invalid.append(args)
        args = list(fixture())
        args[1][...] = 1
        args[4][...] = 1
        invalid.append(args)  # .105 absolute, despite .035 signed resultant.
        for args in invalid:
            with patch.object(boundary, 'native') as native:
                with self.assertRaises(ValueError):
                    boundary.controls(*args)
                native.assert_not_called()

    def test_nonzero_status_never_publishes_private_native_output(self):
        for status in (1, 2, 3, 4, 5, 123):
            fake = RecordingNative(status=status)
            error = ValueError if status in (1, 2, 3, 4) else RuntimeError
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaises(error):
                    boundary.controls(*fixture())
            self.assertEqual(fake.calls, 1)

    def test_malformed_native_output_is_never_published(self):
        for output in ([[np.nan, 0], [0, 0]], [[np.inf, 0], [0, 0]],
                       [[8.01, 0], [0, 0]], [[0, 0.25], [0, 0]]):
            with patch.object(boundary, 'native', return_value=RecordingNative(output)):
                with self.assertRaises(RuntimeError):
                    boundary.controls(*fixture())

    def test_zero_recipe_and_zero_roles_must_return_exact_positive_zero(self):
        for neutral_index in (1, 4):
            args = list(fixture())
            args[neutral_index][...] = 0
            for invalid in ([[0.1, 0], [0, 0]], [[-0.0, 0], [0, 0]]):
                with patch.object(boundary, 'native', return_value=RecordingNative(invalid)):
                    with self.assertRaises(RuntimeError):
                        boundary.controls(*args)
            with patch.object(boundary, 'native', return_value=RecordingNative(np.zeros((2, 2)))):
                result = boundary.controls(*args)
            self.assertFalse(np.any(result))
            self.assertFalse(np.any(np.signbit(result)))

    def test_missing_native_never_falls_back_even_for_direct_neutral_call(self):
        args = list(fixture())
        args[4][...] = 0
        with patch.object(boundary, 'native', side_effect=RuntimeError('missing native')):
            with self.assertRaisesRegex(RuntimeError, 'missing native'):
                boundary.controls(*args)

    def test_available_uses_loader_not_file_presence_and_capability_is_honest(self):
        for failure in (RuntimeError('bad ABI'), OSError('bad library'), AttributeError('missing symbol')):
            with patch.object(boundary, 'native', side_effect=failure):
                self.assertFalse(boundary.available())
                capability = state.capability()
            self.assertFalse(capability['face_contour_available'])
            self.assertTrue(capability['face_contour_reason'])
        with patch.object(boundary, 'native', return_value=object()):
            self.assertTrue(boundary.available())
            self.assertEqual(state.capability(), {
                'face_contour_available': True, 'face_contour_reason': None})

    def test_loader_requires_exact_abi_and_versioned_symbol(self):
        class Symbol:
            def __init__(self, value):
                self.value = value
            def __call__(self):
                return self.value
        for library in (SimpleNamespace(lrt_face_contour_abi=Symbol(2)),
                        SimpleNamespace(lrt_face_contour_abi=Symbol(1))):
            boundary.native.cache_clear()
            try:
                with patch.object(boundary.Path, 'is_file', return_value=True), \
                        patch.object(boundary.C, 'CDLL', return_value=library):
                    with self.assertRaises(RuntimeError):
                        boundary.native()
            finally:
                boundary.native.cache_clear()
        library = SimpleNamespace(lrt_face_contour_abi=Symbol(1),
                                  lrt_face_contour_controls_v1=Symbol(0))
        try:
            with patch.object(boundary.Path, 'is_file', return_value=True), \
                    patch.object(boundary.C, 'CDLL', return_value=library):
                self.assertIs(boundary.native(), library)
            self.assertEqual(library.lrt_face_contour_controls_v1.argtypes,
                             [boundary.P, C.c_size_t] * 5 +
                             [C.c_size_t, boundary.P, C.c_size_t])
            self.assertEqual(library.lrt_face_contour_controls_v1.restype, C.c_int32)
        finally:
            boundary.native.cache_clear()


class FaceContourStateContracts(TestCase):
    def test_version_operation_order_and_traceability_ids(self):
        self.assertEqual(state.OP, 'lnx.face_contour.v1')
        self.assertEqual(state.KEYS, ('temple', 'cheekbone', 'jaw'))
        self.assertEqual(state.SIDES, ('left', 'right'))
        self.assertEqual(state.CONTROL_IDS, {
            'temple': 'LNX-REF-PC-32466-C-94bf91612d',
            'cheekbone': 'LNX-REF-PC-32466-C-d24d97d234',
            'jaw': 'LNX-REF-PC-32466-C-3bc7e245b7'})
        self.assertFalse(state.active(None))
        self.assertEqual(state.check(None), state.neutral())

    def test_unlink_relink_and_next_explicit_linked_adjustment(self):
        original = state.neutral()
        recipe = state.link(original, 'temple', False)
        recipe = state.adjust(recipe, 'temple', 'left', 0.4)
        recipe = state.adjust(recipe, 'temple', 'right', -0.2)
        linked = state.link(recipe, 'temple', True)
        self.assertEqual(linked['temple'], {'linked': True, 'left': 0.4, 'right': -0.2})
        adjusted = state.adjust(linked, 'temple', 'right', 0.3)
        self.assertEqual(adjusted['temple'], {'linked': True, 'left': 0.3, 'right': 0.3})
        self.assertEqual(original, state.neutral())
        self.assertEqual(recipe['temple'], {'linked': False, 'left': 0.4, 'right': -0.2})
        self.assertEqual(linked['temple']['left'], 0.4)
        self.assertEqual(adjusted['cheekbone'], state.neutral()['cheekbone'])

    def test_each_setting_and_return_value_is_independent(self):
        recipe = state.neutral()
        result = state.preset(recipe)
        result['jaw']['left'] = 1
        self.assertEqual(recipe, state.neutral())
        self.assertEqual(result['temple']['left'], 0)
        self.assertTrue(state.side_active(result, 'left'))
        self.assertFalse(state.side_active(result, 'right'))

    def test_invalid_scalar_never_mutates_input(self):
        for bad in (True, np.float64(0.1), np.int32(1), None, '0.2',
                    np.nan, np.inf, -np.inf, -1.01, 1.01, 10**1000):
            recipe = state.neutral()
            with self.assertRaises(ValueError):
                state.adjust(recipe, 'jaw', 'left', bad)
            self.assertEqual(recipe, state.neutral())

    def test_unknown_keys_identity_cache_and_nonboolean_link_are_rejected(self):
        for extra in ('face_id', 'landmarks', 'cache', 'path', 'mask'):
            recipe = state.neutral()
            recipe[extra] = 'forbidden'
            with self.assertRaises(ValueError):
                state.check(recipe)
        for bad_version in (True, 1.0, 0, 2, None):
            recipe = state.neutral()
            recipe['version'] = bad_version
            with self.assertRaises(ValueError):
                state.check(recipe)
        for linked in (1, 0, None, 'true'):
            with self.assertRaises(ValueError):
                state.link(None, 'temple', linked)
        with self.assertRaises(ValueError):
            state.adjust(None, 'temple', 'viewer_left', 0.2)
        with self.assertRaises(ValueError):
            state.adjust(None, 'chin_3d', 'left', 0.2)


class InstalledFaceContourCoreContracts(TestCase):
    """Actual-core fixtures, skipped if no separately packaged library exists."""
    def setUp(self):
        if not boundary.available():
            self.skipTest('Face-contour Rust core unavailable; no implicit build or fallback')

    def test_subject_sign_gain_neutral_and_rotated_lateral_motion(self):
        args = list(fixture())
        np.testing.assert_allclose(boundary.controls(*args), [[3.5, 0], [-3.5, 0]], atol=1e-12)
        args[1][...] = [[0, 1, 0], [0, 1, 0]]
        args[4][...] = [0, 0, 1, 1, 0, 0]
        np.testing.assert_allclose(boundary.controls(*args), [[-3.5, 0], [3.5, 0]], atol=1e-12)
        args[4][...] = 0
        self.assertFalse(np.any(boundary.controls(*args).view(np.uint64)))
        args = list(fixture())
        args[3][:4] = [0.6, 0.8, 0.8, -0.6]
        result = boundary.controls(*args)
        np.testing.assert_allclose(result, [[2.1, 2.8], [-2.1, -2.8]], atol=1e-12)

    def test_ffi_wrong_length_and_alias_refuse_without_mutation(self):
        p, r, s, f, v = fixture()
        output = np.full_like(p, 77)
        lib = boundary.native()
        status = lib.lrt_face_contour_controls_v1(
            p.ctypes.data_as(boundary.P), p.size - 1, *boundary._pair(r),
            *boundary._pair(s), *boundary._pair(f), *boundary._pair(v), len(p),
            *boundary._pair(output))
        self.assertEqual(status, 1)
        np.testing.assert_array_equal(output, np.full_like(p, 77))
        before = p.copy()
        status = lib.lrt_face_contour_controls_v1(
            *boundary._pair(p), *boundary._pair(r), *boundary._pair(s),
            *boundary._pair(f), *boundary._pair(v), len(p), *boundary._pair(p))
        self.assertEqual(status, 1)
        np.testing.assert_array_equal(p, before)
