"""AUTHORED / UNRUN. No build, numerical, visual or product acceptance claim."""
import ctypes as C
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import sclera_purify_native as boundary


class CopyingNativeFixture:
    """Boundary-only stub, not a replacement image algorithm or native proof."""
    def __init__(self):
        self.calls = 0
        self.inputs = []
        self.radius = None

    def lrt_sclera_purify_apply_v1(self, source, source_len, coverage, coverage_len,
                                  width, height, amount, radius,
                                  output, output_len, callback, context):
        self.calls += 1
        self.radius = radius
        self.inputs = [np.ctypeslib.as_array(source, shape=(source_len,)).copy(),
                       np.ctypeslib.as_array(coverage, shape=(coverage_len,)).copy()]
        C.memmove(output, source, source_len * C.sizeof(C.c_float))
        return 0


class ScleraPurifyBridgeContracts(unittest.TestCase):
    def setUp(self):
        self.budget = patch.object(boundary, '_available_estimate', return_value=8 * 1024**3)
        self.budget.start()
        self.addCleanup(self.budget.stop)

    def source(self):
        return np.full((9, 9, 3), [0.76, 0.68, 0.56], np.float32)

    def mask(self):
        return np.ones((9, 9), np.float32)

    def test_owned_read_only_snapshots_do_not_follow_base_mutation(self):
        source = self.source()
        view = source[:, ::-1]
        snapshot = boundary._snapshot(view, view.shape, 'RGB', lambda: False)
        before = view.copy()
        source[:] = 0
        np.testing.assert_array_equal(snapshot, before)
        self.assertTrue(snapshot.flags.owndata)
        self.assertTrue(snapshot.flags.c_contiguous)
        self.assertFalse(snapshot.flags.writeable)
        self.assertFalse(np.shares_memory(snapshot, source))

    def test_result_is_owned_strided_source_unchanged_and_radius_explicit(self):
        source, mask = self.source()[:, ::-1], self.mask()[:, ::-1]
        before = source.copy()
        fake = CopyingNativeFixture()
        with patch.object(boundary, 'native', return_value=fake):
            result = boundary.apply(source, mask, 0.5, np.int64(3))
        self.assertEqual(fake.calls, 1)
        self.assertEqual(fake.radius, 3)
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(result.flags.owndata)
        self.assertTrue(result.flags.c_contiguous)
        self.assertTrue(result.flags.writeable)
        self.assertFalse(np.shares_memory(result, source))
        self.assertFalse(np.shares_memory(result, mask))
        result[:] = 0
        np.testing.assert_array_equal(source, before)
        np.testing.assert_array_equal(mask, self.mask())

    def test_invalid_amount_and_radius_never_load_native(self):
        amounts = (True, np.bool_(False), '0.5', None, float('nan'),
                   float('inf'), -0.001, 1.001, 10**1000)
        radii = (True, np.bool_(True), '2', 2.0, 1.5, None, 0, -1, 33, 10**1000)
        for amount, radius in [(value, 2) for value in amounts] + [(0.5, value) for value in radii]:
            with patch.object(boundary, 'native') as loader:
                with self.assertRaises(ValueError):
                    boundary.apply(self.source(), self.mask(), amount, radius)
                loader.assert_not_called()
        self.assertEqual(boundary._radius(32), 32)

    def test_wrong_shape_dtype_alpha_hdr_and_invalid_mask_fail_even_neutral(self):
        source, mask = self.source(), self.mask()
        pairs = [(source.astype(np.float64), mask), (source.astype(np.float16), mask),
                 (source, mask.astype(np.float64)), (source, mask[..., None]),
                 (source[..., :2], mask),
                 (np.ones((9, 9, 4), np.float32), mask)]
        for invalid in (np.nan, np.inf, -np.inf, -0.001, 1.001):
            bad_source, bad_mask = source.copy(), mask.copy()
            bad_source[-1, -1, -1] = invalid
            bad_mask[-1, -1] = invalid
            pairs.extend([(bad_source, np.zeros_like(mask)), (source, bad_mask)])
        for rgb, coverage in pairs:
            with patch.object(boundary, 'native') as loader:
                with self.assertRaises(ValueError):
                    boundary.apply(rgb, coverage, 0, 2)
                loader.assert_not_called()

    def test_dimensions_work_and_memory_fail_before_snapshot(self):
        with patch.object(boundary, '_snapshot') as snapshot, patch.object(boundary, 'native') as loader:
            with self.assertRaises(ValueError):
                boundary.apply(np.empty((0, 1, 3), np.float32), np.empty((0, 1), np.float32), 0.5, 2)
            # Broadcasted storage avoids allocating an oversized authored fixture.
            huge = np.broadcast_to(np.zeros((1, 1, 3), np.float32), (1000, 1000, 3))
            mask = np.broadcast_to(np.ones((1, 1), np.float32), (1000, 1000))
            with self.assertRaisesRegex(MemoryError, 'work budget'):
                boundary.apply(huge, mask, 0.5, 32)
            with patch.object(boundary, '_available_estimate', return_value=1):
                with self.assertRaises(MemoryError):
                    boundary.apply(self.source(), self.mask(), 0.5, 2)
            with patch.object(boundary, '_available_estimate', side_effect=ValueError('budget unavailable')):
                with self.assertRaisesRegex(ValueError, 'budget unavailable'):
                    boundary.apply(self.source(), self.mask(), 0.5, 2)
            snapshot.assert_not_called()
            loader.assert_not_called()

    def test_cancel_before_allocation_noncallable_and_during_copy(self):
        with patch.object(boundary, '_snapshot') as snapshot, patch.object(boundary, 'native') as loader:
            with self.assertRaises(InterruptedError):
                boundary.apply(self.source(), self.mask(), 0.5, 2, cancelled=lambda: True)
            with self.assertRaises(TypeError):
                boundary.apply(self.source(), self.mask(), 0.5, 2, cancelled=False)
            snapshot.assert_not_called()
            loader.assert_not_called()
        checks = 0
        def cancel():
            nonlocal checks
            checks += 1
            return checks >= 3
        large = np.full((4, 4096, 3), 0.5, np.float32)
        with self.assertRaises(InterruptedError):
            boundary._snapshot(large, large.shape, 'RGB', cancel)

    def test_callback_exceptions_do_not_cross_c_abi(self):
        def broken():
            raise RuntimeError('cancellation provider failed')
        callback, errors = boundary._callback(broken)
        self.assertEqual(callback(None), 1)
        with self.assertRaisesRegex(RuntimeError, 'provider failed'):
            boundary._result(4, lambda: False, errors)

    def test_all_errors_discard_partly_written_output(self):
        class RefusingNative(CopyingNativeFixture):
            def lrt_sclera_purify_apply_v1(self, *args):
                super().lrt_sclera_purify_apply_v1(*args)
                return self.code
        for code, error in ((1, ValueError), (2, ValueError), (3, ValueError),
                            (4, InterruptedError), (5, MemoryError), (6, RuntimeError)):
            fake = RefusingNative()
            fake.code = code
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaises(error):
                    boundary.apply(self.source(), self.mask(), 0.5, 2)

    def test_bad_native_output_is_not_published(self):
        class InvalidNative(CopyingNativeFixture):
            def lrt_sclera_purify_apply_v1(self, *args):
                super().lrt_sclera_purify_apply_v1(*args)
                args[8][0] = float('nan')
                return 0
        with patch.object(boundary, 'native', return_value=InvalidNative()):
            with self.assertRaisesRegex(RuntimeError, 'invalid SDR output'):
                boundary.apply(self.source(), self.mask(), 0.5, 2)

    def test_missing_native_never_falls_back_even_neutral(self):
        with patch.object(boundary, 'native', side_effect=RuntimeError('not installed')):
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                boundary.apply(self.source(), self.mask(), 0, 2)
        for error in (RuntimeError('ABI mismatch'), OSError('broken library'), AttributeError('symbol missing')):
            with patch.object(boundary, 'native', side_effect=error):
                self.assertFalse(boundary.available())

    def test_misbehaving_native_cannot_change_zero_amount_or_zero_coverage(self):
        class ChangingNative(CopyingNativeFixture):
            def lrt_sclera_purify_apply_v1(self, *args):
                super().lrt_sclera_purify_apply_v1(*args)
                args[8][0] = 0.1
                return 0
        for amount, coverage in [(0, self.mask()), (1, np.zeros((9, 9), np.float32))]:
            with patch.object(boundary, 'native', return_value=ChangingNative()):
                with self.assertRaisesRegex(RuntimeError, 'neutral or unsupported'):
                    boundary.apply(self.source(), coverage, amount, 2)

    def test_signed_zero_change_is_detected_in_bitwise_guard(self):
        class LosingSignNative(CopyingNativeFixture):
            def lrt_sclera_purify_apply_v1(self, *args):
                super().lrt_sclera_purify_apply_v1(*args)
                args[8][0] = 0.0
                return 0
        source = self.source()
        source[0, 0, 0] = -0.0
        with patch.object(boundary, 'native', return_value=LosingSignNative()):
            with self.assertRaisesRegex(RuntimeError, 'neutral or unsupported'):
                boundary.apply(source, self.mask(), 0, 2)


NATIVE_PATH = Path(boundary.__file__).resolve().parent / 'bin/liblrt_sclera_purify.so'


@unittest.skipUnless(NATIVE_PATH.is_file(), 'Native binary absent; real-ABI fixtures remain UNRUN')
class ScleraPurifyRealNativeContracts(unittest.TestCase):
    def setUp(self):
        self.budget = patch.object(boundary, '_available_estimate', return_value=8 * 1024**3)
        self.budget.start()
        self.addCleanup(self.budget.stop)

    @staticmethod
    def linear(rgb):
        values = rgb.astype(np.float64)
        return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055)**2.4)

    @classmethod
    def luminance(cls, rgb):
        return cls.linear(rgb) @ np.array([0.2126, 0.7152, 0.0722])

    def test_neutral_outside_and_insufficient_donors_are_exact(self):
        source = np.full((9, 9, 3), [0.76, 0.68, 0.56], np.float32)
        source[0, 0, 0] = -0.0
        weight = np.ones((9, 9), np.float32)
        for mask, amount in [(weight, 0), (weight * 0, 1), (weight * 0.749, 1)]:
            result = boundary.apply(source, mask, amount, 2)
            np.testing.assert_array_equal(result.view(np.uint32), source.view(np.uint32))
        weight[4, 4] = 0
        result = boundary.apply(source, weight, 1, 2)
        np.testing.assert_array_equal(result[4, 4].view(np.uint32), source[4, 4].view(np.uint32))

    def test_dark_speck_lifts_and_broad_shadow_is_not_brightened(self):
        source = np.full((17, 17, 3), 0.8, np.float32)
        source[8, 8] = 0.55
        weight = np.ones((17, 17), np.float32)
        result = boundary.apply(source, weight, 1, 2)
        delta = self.luminance(result)[8, 8] - self.luminance(source)[8, 8]
        self.assertGreater(delta, 0)
        self.assertLessEqual(delta, 0.045 + 1e-7)
        self.assertLess(result[8, 8, 0], source[8, 7, 0])
        source[:, :8] = 0.45
        source[8, 8] = 0.8
        result = boundary.apply(source, weight, 1, 3)
        np.testing.assert_array_equal(result.view(np.uint32), source.view(np.uint32))

    def test_colour_only_preserves_fine_linear_luminance_and_feather(self):
        source = np.full((9, 9, 3), [0.76, 0.68, 0.56], np.float32)
        source[::2] += 0.003
        weight = np.ones((9, 9), np.float32)
        full = boundary.apply(source, weight, 1, 2)
        np.testing.assert_allclose(self.luminance(full), self.luminance(source), atol=1e-7, rtol=0)
        self.assertLess(np.ptp(full[4, 4]), np.ptp(source[4, 4]))
        weight[4, 4] = 0.5
        half = boundary.apply(source, weight, 1, 2)
        np.testing.assert_allclose(self.linear(half[4, 4]),
                                   (self.linear(source[4, 4]) + self.linear(full[4, 4])) * 0.5,
                                   atol=1e-7, rtol=0)

    def test_low_confidence_pixels_are_targets_not_donors(self):
        source = np.full((9, 9, 3), 0.8, np.float32)
        weight = np.ones((9, 9), np.float32)
        source[4, 4] = 0.55
        weight[4, 4] = 0.5
        result = boundary.apply(source, weight, 1, 2)
        self.assertGreater(result[4, 4, 0], source[4, 4, 0])
        # A sub-threshold target is excluded from EVERY neighbour's statistics.
        changed = source.copy()
        changed[4, 4] = 0.0
        second = boundary.apply(changed, weight, 1, 2)
        select = np.ones((9, 9), bool)
        select[4, 4] = False
        np.testing.assert_array_equal(result[select].view(np.uint32), second[select].view(np.uint32))

    def test_torch_explicit_staging_and_numpy_share_one_kernel(self):
        try:
            import torch
        except ImportError:
            self.skipTest('Torch unavailable; host parity is not established')
        source = np.full((9, 9, 3), [0.76, 0.68, 0.56], np.float32)
        weight = np.ones((9, 9), np.float32)
        direct = boundary.apply(source, weight, 0.7, 2)
        staged = boundary.apply(torch.from_numpy(source.copy()).cpu().numpy(),
                                 torch.from_numpy(weight.copy()).cpu().numpy(), 0.7, 2)
        np.testing.assert_array_equal(direct.view(np.uint32), staged.view(np.uint32))

    def test_real_abi_rejects_alias_before_writing(self):
        source = np.full((9, 9, 3), 0.7, np.float32)
        weight = np.ones((9, 9), np.float32)
        before = source.copy()
        callback = boundary.CANCEL(lambda _context: 0)
        code = boundary.native().lrt_sclera_purify_apply_v1(
            source.ctypes.data_as(boundary.P), source.size,
            weight.ctypes.data_as(boundary.P), weight.size, 9, 9, 1, 2,
            source.ctypes.data_as(boundary.P), source.size, callback, None)
        self.assertEqual(code, 1)
        np.testing.assert_array_equal(source, before)
