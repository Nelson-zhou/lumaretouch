"""AUTHORED / UNRUN: boundary fixtures are not native or visual acceptance."""
import ctypes as C
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import skin_colour_native as boundary


class CopyingNativeFixture:
    """A transport-only stub, not a colour algorithm or numerical proof."""
    def __init__(self):
        self.calls = 0
        self.controls = None
        self.inputs = []

    def lrt_skin_colour_apply_v1(self, source, source_len, coverage, coverage_len,
                                 width, height, temperature, tint,
                                 output, output_len, callback, context):
        self.calls += 1
        self.controls = (temperature, tint)
        self.inputs = [np.ctypeslib.as_array(source, shape=(source_len,)).copy(),
                       np.ctypeslib.as_array(coverage, shape=(coverage_len,)).copy()]
        C.memmove(output, source, source_len * C.sizeof(C.c_float))
        return 0


class SkinColourBridgeContracts(unittest.TestCase):
    def setUp(self):
        self.budget = patch.object(boundary, '_available_estimate', return_value=8 * 1024**3)
        self.budget.start()
        self.addCleanup(self.budget.stop)

    @staticmethod
    def source():
        return np.full((3, 5, 3), [0.72, 0.48, 0.32], np.float32)

    @staticmethod
    def coverage():
        return np.ones((3, 5), np.float32)

    def test_owned_immutable_snapshot_of_strided_mutable_base(self):
        source = self.source()
        view = source[:, ::-1]
        expected = view.copy()
        result = boundary._snapshot(view, view.shape, 'RGB', lambda: False)
        source[:] = 0
        np.testing.assert_array_equal(result, expected)
        self.assertTrue(result.flags.owndata)
        self.assertTrue(result.flags.c_contiguous)
        self.assertFalse(result.flags.writeable)
        self.assertFalse(np.shares_memory(result, source))

    def test_output_owned_and_inputs_untouched_controls_forwarded(self):
        source, coverage = self.source()[:, ::-1], self.coverage()[:, ::-1]
        before = source.copy()
        fake = CopyingNativeFixture()
        with patch.object(boundary, 'native', return_value=fake):
            result = boundary.apply(source, coverage, np.float32(-0.5), np.float64(0.75))
        self.assertEqual(fake.calls, 1)
        self.assertEqual(fake.controls, (-0.5, 0.75))
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(result.flags.owndata)
        self.assertTrue(result.flags.c_contiguous)
        self.assertTrue(result.flags.writeable)
        self.assertFalse(np.shares_memory(result, source))
        self.assertFalse(np.shares_memory(result, coverage))
        result[:] = 0
        np.testing.assert_array_equal(source, before)
        np.testing.assert_array_equal(coverage, self.coverage())

    def test_bad_controls_reject_before_native_or_copy(self):
        invalid = (True, np.bool_(False), '0.5', None, float('nan'), float('inf'),
                   -float('inf'), -1.001, 1.001, 10**1000)
        for value in invalid:
            for temperature, tint in ((value, 0), (0, value)):
                with patch.object(boundary, 'native') as loader, patch.object(boundary, '_snapshot') as snapshot:
                    with self.assertRaises(ValueError):
                        boundary.apply(self.source(), self.coverage(), temperature, tint)
                    loader.assert_not_called()
                    snapshot.assert_not_called()

    def test_bad_shapes_types_alpha_hdr_and_mask_reject_even_neutral(self):
        source, coverage = self.source(), self.coverage()
        pairs = [(source.astype(np.float64), coverage), (source.astype(np.float16), coverage),
                 (source, coverage.astype(np.float64)), (source, coverage[..., None]),
                 (source[..., :2], coverage), (np.ones((3, 5, 4), np.float32), coverage),
                 (source.tolist(), coverage), (source, coverage.tolist())]
        for invalid in (np.nan, np.inf, -np.inf, -0.01, 1.01):
            bad_source, bad_mask = source.copy(), coverage.copy()
            bad_source[-1, -1, -1], bad_mask[-1, -1] = invalid, invalid
            pairs.extend([(bad_source, np.zeros_like(coverage)), (source, bad_mask)])
        for rgb, mask in pairs:
            with patch.object(boundary, 'native') as loader:
                with self.assertRaises(ValueError):
                    boundary.apply(rgb, mask, 0, 0)
                loader.assert_not_called()

    def test_dimension_work_and_memory_limits_before_allocation(self):
        with patch.object(boundary, '_snapshot') as snapshot, patch.object(boundary, 'native') as loader:
            with self.assertRaises(ValueError):
                boundary.apply(np.empty((0, 1, 3), np.float32), np.empty((0, 1), np.float32), 0, 0)
            huge = np.broadcast_to(np.zeros((1, 1, 3), np.float32), (8001, 8000, 3))
            mask = np.broadcast_to(np.ones((1, 1), np.float32), (8001, 8000))
            with self.assertRaisesRegex(MemoryError, 'work budget'):
                boundary.apply(huge, mask, 1, 1)
            with patch.object(boundary, '_available_estimate', return_value=1):
                with self.assertRaises(MemoryError):
                    boundary.apply(self.source(), self.coverage(), 1, 1)
            with patch.object(boundary, '_available_estimate', side_effect=ValueError('budget unavailable')):
                with self.assertRaisesRegex(ValueError, 'budget unavailable'):
                    boundary.apply(self.source(), self.coverage(), 1, 1)
            snapshot.assert_not_called()
            loader.assert_not_called()

    def test_noncallable_or_cancelled_before_copy_and_during_wide_row(self):
        with patch.object(boundary, '_snapshot') as snapshot, patch.object(boundary, 'native') as loader:
            with self.assertRaises(TypeError):
                boundary.apply(self.source(), self.coverage(), 1, 1, cancelled=False)
            with self.assertRaises(InterruptedError):
                boundary.apply(self.source(), self.coverage(), 1, 1, cancelled=lambda: True)
            snapshot.assert_not_called()
            loader.assert_not_called()
        checks = 0
        def cancel():
            nonlocal checks
            checks += 1
            return checks >= 3
        source = np.full((1, 3 * boundary.COPY_PIXELS, 3), 0.5, np.float32)
        with self.assertRaises(InterruptedError):
            boundary._snapshot(source, source.shape, 'RGB', cancel)
        self.assertEqual(checks, 3)

    def test_callback_exceptions_are_captured_once_then_reraised_outside_c(self):
        checks = 0
        def broken():
            nonlocal checks
            checks += 1
            raise RuntimeError('cancellation provider failed')
        callback, errors = boundary._callback(broken)
        self.assertEqual(callback(None), 1)
        self.assertEqual(callback(None), 1)
        self.assertEqual(checks, 1)
        with self.assertRaisesRegex(RuntimeError, 'provider failed'):
            boundary._result(4, lambda: False, errors)

    def test_every_native_error_discards_private_output(self):
        class RefusingNative(CopyingNativeFixture):
            def lrt_skin_colour_apply_v1(self, *args):
                super().lrt_skin_colour_apply_v1(*args)
                return self.code
        for code, error in ((1, ValueError), (2, ValueError), (3, ValueError),
                            (4, InterruptedError), (5, MemoryError), (6, RuntimeError)):
            fake = RefusingNative()
            fake.code = code
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaises(error):
                    boundary.apply(self.source(), self.coverage(), 1, 1)

    def test_nonfinite_or_out_of_gamut_native_output_is_not_published(self):
        class BadNative(CopyingNativeFixture):
            def lrt_skin_colour_apply_v1(self, *args):
                super().lrt_skin_colour_apply_v1(*args)
                args[8][0] = self.value
                return 0
        for value in (float('nan'), float('inf'), -0.001, 1.001):
            fake = BadNative()
            fake.value = value
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaisesRegex(RuntimeError, 'invalid SDR output'):
                    boundary.apply(self.source(), self.coverage(), 1, 1)

    def test_native_cannot_change_neutral_or_zero_support_including_signed_zero(self):
        class BadNative(CopyingNativeFixture):
            def lrt_skin_colour_apply_v1(self, *args):
                super().lrt_skin_colour_apply_v1(*args)
                args[8][0] = 0.0
                return 0
        source = self.source()
        source[0, 0, 0] = -0.0
        for temperature, tint, mask in [(0, 0, self.coverage()), (1, 1, self.coverage() * 0)]:
            with patch.object(boundary, 'native', return_value=BadNative()):
                with self.assertRaisesRegex(RuntimeError, 'neutral or unsupported'):
                    boundary.apply(source, mask, temperature, tint)

    def test_cancellation_after_native_success_still_discards_result(self):
        state = {'cancelled': False}
        class CancellingNative(CopyingNativeFixture):
            def lrt_skin_colour_apply_v1(self, *args):
                super().lrt_skin_colour_apply_v1(*args)
                state['cancelled'] = True
                return 0
        with patch.object(boundary, 'native', return_value=CancellingNative()):
            with self.assertRaises(InterruptedError):
                boundary.apply(self.source(), self.coverage(), 1, 1,
                               cancelled=lambda: state['cancelled'])

    def test_missing_or_bad_native_never_falls_back_even_neutral(self):
        with patch.object(boundary, 'native', side_effect=RuntimeError('not installed')):
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                boundary.apply(self.source(), self.coverage(), 0, 0)
        for error in (RuntimeError('ABI mismatch'), OSError('broken library'), AttributeError('symbol missing')):
            with patch.object(boundary, 'native', side_effect=error):
                self.assertFalse(boundary.available())


NATIVE_PATH = Path(boundary.__file__).resolve().parent / 'bin/liblrt_skin_colour.so'


@unittest.skipUnless(NATIVE_PATH.is_file(), 'Native library absent; real-ABI fixtures remain UNRUN')
class SkinColourRealNativeContracts(unittest.TestCase):
    def setUp(self):
        self.budget = patch.object(boundary, '_available_estimate', return_value=8 * 1024**3)
        self.budget.start()
        self.addCleanup(self.budget.stop)

    @staticmethod
    def linear(rgb):
        value = rgb.astype(np.float64)
        return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055)**2.4)

    @classmethod
    def lab(cls, rgb):
        matrix = np.array([[0.4123907992659595, 0.35758433938387796, 0.1804807884018343],
                           [0.21263900587151036, 0.7151686787677559, 0.07219231536073371],
                           [0.01933081871559185, 0.11919477979462599, 0.9505321522496607]])
        xyz = cls.linear(rgb) @ matrix.T
        white = np.array([0.3127 / 0.3290, 1.0, (1 - 0.3127 - 0.3290) / 0.3290])
        relative = xyz / white
        delta = 6 / 29
        f = np.where(relative > delta**3, np.cbrt(relative), relative / (3 * delta**2) + 4 / 29)
        return np.stack((116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                         200 * (f[..., 1] - f[..., 2])), axis=-1)

    def test_real_neutral_outside_and_endpoints_are_bit_exact(self):
        source = np.array([[[-0.0, 0.5, 1.0], [-0.0, 0.0, -0.0], [1.0, 1.0, 1.0]]], np.float32)
        mask = np.ones((1, 3), np.float32)
        for weight, temperature, tint in ((mask, 0, 0), (mask * 0, 1, -1)):
            result = boundary.apply(source, weight, temperature, tint)
            np.testing.assert_array_equal(result.view(np.uint32), source.view(np.uint32))
        mask[0, 0] = 0
        for temperature in (-1, 1):
            for tint in (-1, 1):
                result = boundary.apply(source, mask, temperature, tint)
                np.testing.assert_array_equal(result.view(np.uint32), source.view(np.uint32))

    def test_real_control_signs_and_original_lab_scales(self):
        source = np.full((1, 1, 3), 0.5, np.float32)
        before = self.lab(source)
        for sign in (-1, 1):
            warm = boundary.apply(source, np.ones((1, 1), np.float32), sign, 0)
            tint = boundary.apply(source, np.ones((1, 1), np.float32), 0, sign)
            np.testing.assert_allclose(self.lab(warm) - before, [[[0, 0, sign * 8]]], rtol=0, atol=3e-5)
            np.testing.assert_allclose(self.lab(tint) - before, [[[0, sign * 6, 0]]], rtol=0, atol=3e-5)

    def test_real_saturated_skin_and_near_endpoint_gamut_lightness(self):
        source = np.array([[[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0],
                            [0, 1, 1], [1, 0, 1], [0.99999]*3, [0.00001]*3,
                            [0.2, 0.09, 0.04], [0.65, 0.36, 0.22], [0.96, 0.95, 0.93]]], np.float32)
        coverage = np.ones(source.shape[:2], np.float32)
        for temperature in (-1, 1):
            for tint in (-1, 1):
                result = boundary.apply(source, coverage, temperature, tint)
                self.assertTrue(np.isfinite(result).all())
                self.assertTrue(np.all((result >= 0) & (result <= 1)))
                np.testing.assert_allclose(self.lab(result)[..., 0], self.lab(source)[..., 0], rtol=0, atol=3e-5)

    def test_real_partial_coverage_in_linear_light_and_no_neighbour_effect(self):
        source = np.full((3, 5, 3), [0.72, 0.48, 0.32], np.float32)
        mask = np.ones((3, 5), np.float32)
        full = boundary.apply(source, mask, -1, 1)
        partial = boundary.apply(source, mask * 0.25, -1, 1)
        np.testing.assert_allclose(self.linear(partial), 0.75 * self.linear(source) + 0.25 * self.linear(full),
                                   rtol=0, atol=1e-7)
        changed = source.copy()
        changed[1, 2] = [1, 0, 0]
        rerendered = boundary.apply(changed, mask, -1, 1)
        other = np.ones((3, 5), dtype=bool)
        other[1, 2] = False
        np.testing.assert_array_equal(full[other].view(np.uint32), rerendered[other].view(np.uint32))
        again = boundary.apply(source, mask, -1, 1)
        np.testing.assert_array_equal(full.view(np.uint32), again.view(np.uint32))
