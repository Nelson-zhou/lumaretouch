"""AUTHORED / UNRUN: edited-sink admission and real-existing-ABI parity cases.

Small synthetic samples exercise contracts, not genuine-photo or RSS acceptance.
Real-native cases explicitly skip when the packaged ABI is unavailable; no stub
stands in for transfer math. Merely authoring/parsing these tests runs none of them.
"""
import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from lumaretouch_engine import creative_edited_capture_sink as bounded


class EditedSinkAdmissionContracts(unittest.TestCase):
    def test_plan_charges_input_sink_and_three_simultaneous_transfer_blocks(self):
        import numpy as np
        for dtype in (np.float32, np.float64):
            source = np.zeros((3, 7, 3), dtype=dtype)
            plan = bounded.inspect_rgb_sink(source)
            self.assertEqual((plan.width, plan.height), (7, 3))
            self.assertEqual(plan.source_bytes, source.nbytes)
            self.assertEqual(plan.source_storage_bytes, source.nbytes)
            self.assertEqual(plan.sink_bytes, 21 * 16)
            self.assertEqual(plan.block_workspace_bytes, 21 * (16 + 16 + 16))
            self.assertEqual(plan.peak_bytes, source.nbytes + 21 * (16 + 48)
                             + bounded.ARRAY_WORKSPACE_RESERVE + bounded.METADATA_RESERVE)
            self.assertEqual(plan.freeze_bytes_after_source_release,
                             2 * plan.sink_bytes + bounded.METADATA_RESERVE)
            self.assertFalse(plan.runtime_verified)
            self.assertIn('conservative-native-reserves', plan.bounds_kind)

    def test_exact_budget_admits_and_one_byte_less_refuses_before_native(self):
        import numpy as np
        source = np.zeros((2, 3, 3), dtype=np.float32)
        peak = bounded.inspect_rgb_sink(source).peak_bytes
        self.assertEqual(bounded.inspect_rgb_sink(source, max_bytes=peak).peak_bytes, peak)
        with patch('lumaretouch_engine.creative_layer_native.native') as native, patch.object(
                bounded, 'bytearray', create=True) as allocate:
            with self.assertRaises(bounded.EditedCaptureBudgetExceeded):
                bounded.capture_rgb_sink(source, max_bytes=peak - 1)
            native.assert_not_called()
            allocate.assert_not_called()

    def test_strided_views_charge_retained_float64_owner_not_just_the_crop(self):
        import numpy as np
        owner = np.zeros((12, 16, 3), dtype=np.float64)
        for source in (owner[2:5, 3:8], owner[::-2, ::-3], owner.transpose(1, 0, 2)):
            plan = bounded.inspect_rgb_sink(source)
            self.assertEqual(plan.source_bytes, source.nbytes)
            self.assertEqual(plan.source_storage_bytes, owner.nbytes)

    def test_buffer_backing_charges_unused_bytes(self):
        import numpy as np
        for storage in (bytes(480), bytearray(480)):
            source = np.frombuffer(storage, dtype='=f4', count=12, offset=12).reshape(2, 2, 3)
            plan = bounded.inspect_rgb_sink(source)
            self.assertEqual(plan.source_bytes, 48)
            self.assertEqual(plan.source_storage_bytes, 480)

    def test_invalid_shape_dtype_and_budget_never_load_native(self):
        import numpy as np
        swapped = '>f4' if sys.byteorder == 'little' else '<f4'
        invalid = [None, [[[0.0, 0.0, 0.0]]], np.zeros((2, 3), dtype=np.float32),
                   np.zeros((2, 3, 4), dtype=np.float32), np.zeros((2, 3, 1), dtype=np.float32),
                   np.zeros((0, 3, 3), dtype=np.float32), np.zeros((2, 0, 3), dtype=np.float32),
                   np.zeros((1, 1, 3), dtype=swapped)]
        invalid += [np.zeros((1, 1, 3), dtype=dtype)
                    for dtype in (np.uint8, np.uint16, np.float16, np.int32, np.bool_)]
        with patch('lumaretouch_engine.creative_layer_native.native') as native:
            for source in invalid:
                with self.subTest(shape=getattr(source, 'shape', None), dtype=getattr(source, 'dtype', None)):
                    with self.assertRaises(ValueError):
                        bounded.capture_rgb_sink(source)
            source = np.zeros((1, 1, 3), dtype=np.float32)
            for maximum in (True, 0, -1, 1.0, bounded.MAX_WORK_BYTES + 1):
                with self.assertRaises(ValueError):
                    bounded.capture_rgb_sink(source, max_bytes=maximum)
            native.assert_not_called()

    def test_pixel_cap_without_allocating_a_large_raster(self):
        import numpy as np
        # Shape-only rejection fixture, NOT a full-size image or memory test.
        source = np.broadcast_to(np.zeros((1, 1, 3), dtype=np.float32),
                                 (bounded.MAX_SOURCE_PIXELS + 1, 1, 3))
        with patch('lumaretouch_engine.creative_layer_native.native') as native:
            with self.assertRaisesRegex(ValueError, 'pixel budget'):
                bounded.capture_rgb_sink(source, max_bytes=bounded.MAX_WORK_BYTES)
            native.assert_not_called()

    def test_unknown_backing_owner_and_ndarray_subclass_fail_closed(self):
        import numpy as np
        source = np.zeros((2, 3, 3), dtype=np.float32)
        unsafe = np.lib.stride_tricks.as_strided(source, shape=source.shape, strides=source.strides)
        with self.assertRaisesRegex(ValueError, 'backing-storage'):
            bounded.inspect_rgb_sink(unsafe)

        class Subclass(np.ndarray):
            pass

        with self.assertRaises(ValueError):
            bounded.inspect_rgb_sink(source.view(Subclass))

    def test_invalid_internal_block_bound_refuses_before_allocation(self):
        import numpy as np
        source = np.zeros((1, 1, 3), dtype=np.float32)
        with patch('lumaretouch_engine.creative_layer_native.native') as native:
            for size in (True, 0, -1, bounded.MAX_TILE_PIXELS + 1):
                with patch.object(bounded, 'BLOCK_PIXELS', size):
                    with self.assertRaisesRegex(ValueError, 'ABI cap'):
                        bounded.capture_rgb_sink(source)
            native.assert_not_called()

    def test_precancel_does_not_load_native_or_examine_source(self):
        with patch('lumaretouch_engine.creative_layer_native.native') as native:
            with self.assertRaises(InterruptedError):
                bounded.capture_rgb_sink(object(), cancelled=lambda: True)
            native.assert_not_called()

    def test_cancel_after_staging_prevents_first_native_call(self):
        import numpy as np
        source = np.ones((2, 3, 3), dtype=np.float32)
        state = {'cancel': False}
        real_empty = np.empty

        def cancel_after_allocation(shape, *args, **kwargs):
            result = real_empty(shape, *args, **kwargs)
            state['cancel'] = True
            return result

        # This sentinel has no native method. Reaching it would fail the test.
        with patch('lumaretouch_engine.creative_layer_native.native', return_value=object()), patch(
                'numpy.empty', side_effect=cancel_after_allocation):
            with self.assertRaises(InterruptedError):
                bounded.capture_rgb_sink(source, cancelled=lambda: state['cancel'])
        self.assertTrue((source == 1.0).all())

    def test_freeze_is_a_separate_phase_not_implicitly_admitted(self):
        import numpy as np
        source = np.zeros((4, 5, 3), dtype=np.float32)
        # Small arithmetic fixture only. Production allowances remain unchanged.
        with patch.object(bounded, 'BLOCK_PIXELS', 1), patch.object(
                bounded, 'ARRAY_WORKSPACE_RESERVE', 0), patch.object(bounded, 'METADATA_RESERVE', 0):
            plan = bounded.inspect_rgb_sink(source, max_bytes=608)
        self.assertEqual(plan.peak_bytes, 608)
        self.assertEqual(plan.freeze_bytes_after_source_release, 640)
        self.assertGreater(plan.freeze_bytes_after_source_release, plan.max_bytes)

    def test_native_rejection_routes_error_without_mutating_source(self):
        import numpy as np
        from lumaretouch_engine.creative_layer_native import CreativeLayerNativeRejected
        source = np.ones((2, 3, 3), dtype=np.float32)
        before = source.tobytes()

        class RejectNative:
            def lrt_creative_linearize_extended_rgba(self, src, dst, length):
                return 3

        # Error-routing stub only. It does not implement replacement colour math.
        with patch('lumaretouch_engine.creative_layer_native.native', return_value=RejectNative()):
            with self.assertRaises(CreativeLayerNativeRejected) as caught:
                bounded.capture_rgb_sink(source)
        self.assertEqual(caught.exception.code, 3)
        self.assertEqual(source.tobytes(), before)

    def test_source_only_uses_existing_native_transfer_without_freeze_or_publication(self):
        tree = ast.parse(Path(bounded.__file__).read_text())
        attrs = {node.func.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        names = {node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertIn('lrt_creative_linearize_extended_rgba', attrs)
        self.assertFalse(attrs & {'power', 'where', 'clip', 'nan_to_num', 'astype',
                                 'linearize_extended_rgba', 'intern', 'export_float'})
        self.assertFalse(names & {'bytes', 'make_asset'})


class EditedSinkRealNativeParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from lumaretouch_engine.creative_layer_native import native, CreativeLayerNativeUnavailable
        try:
            cls.library = native()
        except CreativeLayerNativeUnavailable as exc:
            raise unittest.SkipTest(f'Existing packaged creative-layer ABI unavailable: {exc}')

    def _compare(self, source, block=7):
        import numpy as np
        from lumaretouch_engine.creative_layer_native import linearize_extended_rgba
        before = source.tobytes(order='C')
        # Exact old boundary, including f64-to-f32 assignment. Full-size baseline
        # allocations here are deliberately tiny and test-only, not production.
        rgba = np.empty((*source.shape[:2], 4), dtype=np.float32)
        rgba[:, :, :3] = source
        rgba[:, :, 3] = 1.0
        expected = linearize_extended_rgba(rgba).astype('<f4', copy=False).tobytes(order='C')
        with patch.object(bounded, 'BLOCK_PIXELS', block):
            result = bounded.capture_rgb_sink(source)
        self.assertEqual(bytes(result.sink), expected)
        self.assertEqual((result.width, result.height), (source.shape[1], source.shape[0]))
        self.assertIs(type(result.sink), bytearray)
        self.assertEqual(source.tobytes(order='C'), before)
        output = np.frombuffer(result.sink, dtype='<f4').reshape(*source.shape[:2], 4)
        self.assertTrue((output[:, :, 3] == 1.0).all())
        self.assertFalse(np.shares_memory(source, output))
        return result, output

    def test_black_white_signed_zero_and_knee_are_bit_exact(self):
        import numpy as np
        knee = np.float32(0.04045)
        values = np.array([0.0, -0.0, 1.0, -1.0, knee, -knee,
                           np.nextafter(knee, np.float32(0)),
                           np.nextafter(knee, np.float32(1)),
                           -np.nextafter(knee, np.float32(1))], dtype=np.float32)
        source = np.tile(values, 5).reshape(3, 5, 3)
        _, output = self._compare(source)
        self.assertEqual(output[0, 0, 0], 0.0)
        self.assertFalse(np.signbit(output[0, 0, 0]))
        self.assertTrue(np.signbit(output[0, 0, 1]))
        self.assertEqual(output[0, 0, 2], 1.0)

    def test_signed_hdr_and_low_bits_do_not_clip_or_quantize(self):
        import numpy as np
        source = np.array([[[-2.5, -0.125, 1.5], [2.5, 0.00001, -0.00001]],
                           [[0.25, 0.5, 0.75], [1 / 65535, 257 / 65535, 65534 / 65535]]],
                          dtype=np.float32)
        _, output = self._compare(source, block=3)
        self.assertLess(output[0, 0, 0], -1.0)
        self.assertGreater(output[0, 0, 2], 1.0)
        self.assertGreater(output[1, 1, 0], 0.0)
        self.assertLess(output[1, 1, 0], output[1, 1, 1])

    def test_float64_rounding_matches_the_old_assignment_boundary(self):
        import numpy as np
        low = np.float32(0.04045)
        high = np.nextafter(low, np.float32(1.0))
        midpoint = (np.float64(low) + np.float64(high)) / 2
        source = np.array([[[np.nextafter(midpoint, -np.inf), midpoint,
                             np.nextafter(midpoint, np.inf)],
                            [-0.0, -2.0 + 1e-10, 2.0 - 1e-10]]], dtype=np.float64)
        self._compare(source, block=1)

    def test_crop_transpose_reverse_and_immutable_sources_match_old_path(self):
        import numpy as np
        owner = np.linspace(-2, 2, 6 * 9 * 3, dtype=np.float64).reshape(6, 9, 3)
        for source in (owner[1:5, 2:8], owner[::-1, ::-2], owner.transpose(1, 0, 2)):
            self._compare(source)
        immutable = np.frombuffer(np.array([0.0, -0.5, 1.5] * 12, dtype=np.float32).tobytes(),
                                  dtype='=f4').reshape(3, 4, 3)
        self._compare(immutable, block=5)

    def test_wide_and_tall_images_never_allocate_unbounded_staging(self):
        import numpy as np
        library = self.library
        for shape in ((3, 17, 3), (17, 3, 3)):
            source = np.full(shape, 0.5, dtype=np.float32)
            lengths, allocations = [], []
            real_empty = np.empty

            class ObserveNative:
                def lrt_creative_linearize_extended_rgba(self, src, dst, length):
                    lengths.append(length // 4)
                    return library.lrt_creative_linearize_extended_rgba(src, dst, length)

            def observe_empty(shape, *args, **kwargs):
                allocations.append(shape)
                return real_empty(shape, *args, **kwargs)

            with patch.object(bounded, 'BLOCK_PIXELS', 8), patch(
                    'lumaretouch_engine.creative_layer_native.native', return_value=ObserveNative()), patch(
                    'numpy.empty', side_effect=observe_empty):
                result = bounded.capture_rgb_sink(source)
            self.assertEqual(sum(lengths), shape[0] * shape[1])
            self.assertTrue(all(0 < count <= 8 for count in lengths))
            self.assertTrue(all(item[0] * item[1] <= 8 and item[2] == 4 for item in allocations))
            self.assertEqual(len(result.sink), shape[0] * shape[1] * 16)

    def test_nonfinite_and_excess_hdr_reject_even_in_the_last_block(self):
        import numpy as np
        from lumaretouch_engine.creative_layer_native import CreativeLayerNativeRejected
        for dtype in (np.float32, np.float64):
            for value in (float('nan'), float('inf'), -float('inf'), 1000.0, -1000.0):
                source = np.zeros((2, 5, 3), dtype=dtype)
                source[-1, -1, 2] = value
                before = source.tobytes()
                with patch.object(bounded, 'BLOCK_PIXELS', 3):
                    with self.assertRaises(CreativeLayerNativeRejected):
                        bounded.capture_rgb_sink(source)
                self.assertEqual(source.tobytes(), before)

    def test_cancellation_after_each_block_including_final_never_returns_sink(self):
        import numpy as np
        library = self.library
        source = np.full((2, 5, 3), 0.5, dtype=np.float32)
        before = source.tobytes()
        # block=3 produces four native calls: 3,2,3,2 pixels.
        for cancel_after in range(1, 5):
            state = {'calls': 0}

            class ObserveNative:
                def lrt_creative_linearize_extended_rgba(self, src, dst, length):
                    code = library.lrt_creative_linearize_extended_rgba(src, dst, length)
                    state['calls'] += 1
                    return code

            with patch.object(bounded, 'BLOCK_PIXELS', 3), patch(
                    'lumaretouch_engine.creative_layer_native.native', return_value=ObserveNative()):
                with self.assertRaises(InterruptedError):
                    bounded.capture_rgb_sink(source, cancelled=lambda: state['calls'] >= cancel_after)
            self.assertEqual(state['calls'], cancel_after)
            self.assertEqual(source.tobytes(), before)

    def test_result_cannot_consume_source_aliases_and_freeze_is_a_real_copy(self):
        import numpy as np
        source = np.full((2, 3, 3), 0.5, dtype=np.float32)
        alias = source
        result, output = self._compare(source)
        before = bytes(result.sink)
        alias.fill(0.0)
        self.assertIs(alias, source)
        self.assertEqual(bytes(result.sink), before)
        del output, source, alias
        # Only the owner can release all source aliases before this phase.
        content = bytes(result.sink)
        self.assertEqual(content, before)
        result.sink[0] ^= 1
        self.assertEqual(content, before)


if __name__ == '__main__':
    unittest.main()
