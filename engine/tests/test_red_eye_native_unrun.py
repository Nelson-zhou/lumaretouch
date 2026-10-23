"""AUTHORED / UNRUN. No build, native, numerical or visual acceptance evidence."""
import ctypes as C
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import red_eye_native as boundary


class CopyingNativeFixture:
    """Boundary-only stub, not a Python red-eye implementation."""
    def __init__(self):
        self.inputs = []
        self.calls = 0

    def lrt_red_eye_apply_v1(self, source, source_len, weight, weight_len,
                             width, height, amount, output, output_len,
                             callback, context):
        self.calls += 1
        self.inputs = [np.ctypeslib.as_array(source, shape=(source_len,)).copy(),
                       np.ctypeslib.as_array(weight, shape=(weight_len,)).copy()]
        self.dimensions = (width, height)
        self.amount = amount
        C.memmove(output, source, source_len * C.sizeof(C.c_float))
        return 0


class RedEyeBridgeContracts(unittest.TestCase):
    def setUp(self):
        self.budget = patch.object(boundary, '_available_estimate', return_value=8 * 1024**3)
        self.budget.start()
        self.addCleanup(self.budget.stop)

    def source(self):
        return np.array([[[0.9, 0.1, 0.2], [0.7, 0.6, 0.4]]], dtype=np.float32)

    def support(self):
        return np.ones((1, 2), np.float32)

    def test_owned_read_only_snapshots_do_not_follow_base_mutation(self):
        original = self.source()
        source = original[:, ::-1]
        frozen = boundary._snapshot(source, source.shape, 'RGB', lambda: False)
        expected = source.copy()
        original[:] = 0
        np.testing.assert_array_equal(frozen, expected)
        self.assertTrue(frozen.flags.owndata)
        self.assertTrue(frozen.flags.c_contiguous)
        self.assertFalse(frozen.flags.writeable)
        self.assertFalse(np.shares_memory(frozen, original))

    def test_strided_inputs_produce_owned_result_without_mutating_either_input(self):
        source = self.source()[:, ::-1]
        weight = self.support()[:, ::-1]
        before = source.copy()
        fake = CopyingNativeFixture()
        with patch.object(boundary, 'native', return_value=fake):
            result = boundary.apply(source, weight, 0.25)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(fake.amount, 0.25)
        self.assertEqual(fake.dimensions, (2, 1))
        np.testing.assert_array_equal(fake.inputs[0], source.reshape(-1))
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(result.flags.c_contiguous)
        self.assertTrue(result.flags.owndata)
        self.assertTrue(result.flags.writeable)
        self.assertFalse(np.shares_memory(result, source))
        self.assertFalse(np.shares_memory(result, weight))
        result[:] = 0
        np.testing.assert_array_equal(source, before)
        np.testing.assert_array_equal(weight, self.support())

    def test_invalid_amount_never_loads_native(self):
        for amount in (True, np.bool_(False), '0.5', None, float('nan'),
                       float('inf'), -0.01, 1.01, 10**1000):
            with self.subTest(amount=str(amount)[:30]):
                with patch.object(boundary, 'native') as loader:
                    with self.assertRaises(ValueError):
                        boundary.apply(self.source(), self.support(), amount)
                    loader.assert_not_called()

    def test_numpy_scalar_amounts_are_accepted_without_a_second_control(self):
        fake = CopyingNativeFixture()
        for amount in (np.float32(0.5), np.float64(0.25), np.int32(1), 0):
            with patch.object(boundary, 'native', return_value=fake):
                boundary.apply(self.source(), self.support(), amount)
            self.assertEqual(fake.amount, float(amount))

    def test_dtypes_shapes_and_invalid_pixels_fail_before_native_even_when_neutral(self):
        source, weight = self.source(), self.support()
        invalid_pairs = [(source.astype(np.float64), weight),
                         (source, weight.astype(np.float64)),
                         (source, np.ones((1, 2, 1), np.float32)),
                         (source[:, :, :2], weight),
                         (source.tolist(), weight),
                         (source, weight.tolist())]
        for value in (np.nan, np.inf, -np.inf, -0.001, 1.001):
            bad_source = source.copy()
            bad_source[0, 0, 0] = value
            bad_weight = weight.copy()
            bad_weight[0, 0] = value
            invalid_pairs.extend([(bad_source, np.zeros_like(weight)), (source, bad_weight)])
        for rgb, mask in invalid_pairs:
            with patch.object(boundary, 'native') as loader:
                with self.assertRaises(ValueError):
                    boundary.apply(rgb, mask, 0.0)
                loader.assert_not_called()

    def test_zero_oversized_and_budget_refusal_before_allocation_or_native(self):
        with patch.object(boundary, '_snapshot') as snapshot, patch.object(boundary, 'native') as loader:
            with self.assertRaises(ValueError):
                boundary.apply(np.empty((0, 1, 3), np.float32), np.empty((0, 1), np.float32), 0.5)
            huge = np.broadcast_to(np.zeros((1, 1, 3), np.float32), (8192, 8192, 3))
            mask = np.broadcast_to(np.ones((1, 1), np.float32), (8192, 8192))
            with self.assertRaises(MemoryError):
                boundary.apply(huge, mask, 0.5)
            with patch.object(boundary, '_available_estimate', return_value=1):
                with self.assertRaises(MemoryError):
                    boundary.apply(self.source(), self.support(), 0.5)
            with patch.object(boundary, '_available_estimate', side_effect=ValueError('budget unavailable')):
                with self.assertRaisesRegex(ValueError, 'budget unavailable'):
                    boundary.apply(self.source(), self.support(), 0.5)
            snapshot.assert_not_called()
            loader.assert_not_called()

    def test_cancel_before_allocation_and_noncallable_cancel(self):
        with patch.object(boundary, '_snapshot') as snapshot, patch.object(boundary, 'native') as loader:
            with self.assertRaises(InterruptedError):
                boundary.apply(self.source(), self.support(), 0.5, cancelled=lambda: True)
            with self.assertRaises(TypeError):
                boundary.apply(self.source(), self.support(), 0.5, cancelled=False)
            snapshot.assert_not_called()
            loader.assert_not_called()

    def test_cancel_during_snapshot_copy(self):
        checks = 0
        def cancel():
            nonlocal checks
            checks += 1
            return checks >= 3
        source = np.full((4, 4096, 3), 0.5, np.float32)
        with self.assertRaises(InterruptedError):
            boundary._snapshot(source, source.shape, 'RGB', cancel)

    def test_callback_exception_is_preserved_without_crossing_abi(self):
        def broken():
            raise RuntimeError('cancellation provider failed')
        callback, errors = boundary._callback(broken)
        self.assertEqual(callback(None), 1)
        with self.assertRaisesRegex(RuntimeError, 'provider failed'):
            boundary._result(4, lambda: False, errors)

    def test_nonzero_status_never_publishes_partial_output(self):
        class RefusingNative(CopyingNativeFixture):
            def lrt_red_eye_apply_v1(self, *args):
                super().lrt_red_eye_apply_v1(*args)
                return self.code
        for code, error in ((1, ValueError), (2, ValueError), (3, ValueError),
                            (4, InterruptedError), (5, MemoryError), (6, RuntimeError)):
            fake = RefusingNative()
            fake.code = code
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaises(error):
                    boundary.apply(self.source(), self.support(), 0.5)

    def test_invalid_native_output_and_red_only_contract_breaks_are_not_published(self):
        class CorruptNative(CopyingNativeFixture):
            def lrt_red_eye_apply_v1(self, *args):
                super().lrt_red_eye_apply_v1(*args)
                args[7][self.channel] = self.value
                return 0
        cases = ((0, float('nan'), 1.0, 0.5, 'invalid SDR output'),
                 (1, 0.2, 1.0, 0.5, 'red-only'),
                 (0, 1.0, 1.0, 0.5, 'red-only'),
                 (0, 0.8, 0.0, 0.5, 'neutral or unsupported'),
                 (0, 0.8, 1.0, 0.0, 'neutral or unsupported'))
        for channel, value, support, amount, message in cases:
            fake = CorruptNative()
            fake.channel, fake.value = channel, value
            with patch.object(boundary, 'native', return_value=fake):
                with self.assertRaisesRegex(RuntimeError, message):
                    boundary.apply(self.source(), self.support() * support, amount)

    def test_cancellation_after_native_success_still_discards_output(self):
        completed = False
        class CompletedNative(CopyingNativeFixture):
            def lrt_red_eye_apply_v1(self, *args):
                nonlocal completed
                result = super().lrt_red_eye_apply_v1(*args)
                completed = True
                return result
        with patch.object(boundary, 'native', return_value=CompletedNative()):
            with self.assertRaises(InterruptedError):
                boundary.apply(self.source(), self.support(), 1.0, cancelled=lambda: completed)

    def test_missing_library_is_no_fallback_even_for_neutral_amount(self):
        with patch.object(boundary, 'native', side_effect=RuntimeError('not installed')):
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                boundary.apply(self.source(), self.support(), 0.0)

    def test_available_checks_abi_and_symbols_not_only_path(self):
        for error in (RuntimeError('ABI mismatch'), OSError('broken library'), AttributeError('missing symbol')):
            with patch.object(boundary, 'native', side_effect=error):
                self.assertFalse(boundary.available())
        with patch.object(boundary, 'native', return_value=CopyingNativeFixture()):
            self.assertTrue(boundary.available())


NATIVE_PATH = Path(boundary.__file__).resolve().parent / 'bin/liblrt_red_eye.so'


@unittest.skipUnless(NATIVE_PATH.is_file(), 'Native binary absent; authored real-ABI fixtures remain UNRUN')
class RedEyeRealNativeContracts(unittest.TestCase):
    def setUp(self):
        self.budget = patch.object(boundary, '_available_estimate', return_value=8 * 1024**3)
        self.budget.start()
        self.addCleanup(self.budget.stop)

    def test_neutral_support_neutral_colour_and_catchlights_are_bit_exact(self):
        source = np.array([[[-0.0, 0.0, 0.0], [0.5, 0.5, 0.5],
                            [1.0, 0.9, 0.8], [0.9, 0.1, 0.2]]], np.float32)
        weight = np.ones((1, 4), np.float32)
        neutral = boundary.apply(source, weight, 0)
        np.testing.assert_array_equal(neutral.view(np.uint32), source.view(np.uint32))
        unsupported = boundary.apply(source, np.zeros_like(weight), 1)
        np.testing.assert_array_equal(unsupported.view(np.uint32), source.view(np.uint32))
        output = boundary.apply(source, weight, 1)
        np.testing.assert_array_equal(output[:, :3].view(np.uint32), source[:, :3].view(np.uint32))
        np.testing.assert_array_equal(output[:, :, 1:].view(np.uint32), source[:, :, 1:].view(np.uint32))
        self.assertAlmostEqual(float(output[0, 3, 0]), 0.15, places=6)

    def test_dominance_over_both_channels_and_dark_noise_exclusion(self):
        source = np.array([[[0.9, 0.7, 0.1], [0.9, 0.1, 0.7],
                            [0.07, 0.0, 0.0]]], np.float32)
        output = boundary.apply(source, np.ones((1, 3), np.float32), 1)
        np.testing.assert_array_equal(output.view(np.uint32), source.view(np.uint32))

    def test_amount_and_support_are_independent_linear_blend_factors(self):
        source = np.array([[[0.9, 0.1, 0.2]]], np.float32)
        weight = np.ones((1, 1), np.float32)
        full = boundary.apply(source, weight, 1)
        half_amount = boundary.apply(source, weight, 0.5)
        half_support = boundary.apply(source, weight * 0.5, 1)
        np.testing.assert_array_equal(half_amount.view(np.uint32), half_support.view(np.uint32))
        np.testing.assert_allclose(half_amount, 0.5 * (source + full), atol=1e-7)
        self.assertLessEqual(float(full[0, 0, 0]), float(source[0, 0, 0]))
        self.assertGreaterEqual(float(full[0, 0, 0]), 0.1499999)

    def test_natural_red_false_positive_is_an_explicit_limitation(self):
        source = np.array([[[0.3, 0.04, 0.03]]], np.float32)
        output = boundary.apply(source, np.ones((1, 1), np.float32), 1)
        self.assertLess(output[0, 0, 0], source[0, 0, 0])
        np.testing.assert_array_equal(output[:, :, 1:].view(np.uint32), source[:, :, 1:].view(np.uint32))

    def test_numpy_and_explicit_torch_staging_share_one_native_result(self):
        try:
            import torch
        except ImportError:
            self.skipTest('Torch unavailable; host parity is not established')
        source = np.array([[[0.9, 0.1, 0.2], [0.6, 0.2, 0.1]]], np.float32)
        weight = np.array([[0.8, 0.25]], np.float32)
        direct = boundary.apply(source, weight, 0.7)
        tensor = torch.from_numpy(source.copy())
        tensor_weight = torch.from_numpy(weight.copy())
        staged = boundary.apply(tensor.detach().cpu().numpy(),
                                tensor_weight.detach().cpu().numpy(), 0.7)
        np.testing.assert_array_equal(direct.view(np.uint32), staged.view(np.uint32))

    def test_real_abi_rejects_output_alias_before_writing(self):
        source = np.array([[[0.9, 0.1, 0.2]]], np.float32)
        weight = np.ones((1, 1), np.float32)
        before = source.copy()
        callback = boundary.CANCEL(lambda _context: 0)
        code = boundary.native().lrt_red_eye_apply_v1(
            source.ctypes.data_as(boundary.P), source.size,
            weight.ctypes.data_as(boundary.P), weight.size,
            1, 1, 1, source.ctypes.data_as(boundary.P), source.size, callback, None)
        self.assertEqual(code, 1)
        np.testing.assert_array_equal(source.view(np.uint32), before.view(np.uint32))
