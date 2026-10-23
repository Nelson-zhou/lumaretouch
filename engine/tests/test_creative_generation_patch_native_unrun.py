"""AUTHORED / UNRUN. No native binary, model or quality acceptance evidence."""
import unittest
from unittest.mock import patch
import numpy as np
from lumaretouch_engine import creative_generation_patch_native as boundary


class GenerationPatchBridgeContracts(unittest.TestCase):
    def test_snapshot_is_owned_float32_and_immutable(self):
        source = np.full((2, 3), 0.5, dtype=np.float32)
        result = boundary._snapshot(source, source.shape, 'fixture', lambda: False)
        source[:] = 0
        self.assertTrue(np.all(result == 0.5))
        self.assertFalse(result.flags.writeable)
        self.assertTrue(result.flags.c_contiguous)

    def test_no_dtype_or_nonfinite_coercion(self):
        for value in (np.zeros((1, 1), dtype=np.float64),
                      np.full((1, 1), np.nan, dtype=np.float32),
                      np.full((1, 1), 1.01, dtype=np.float32)):
            with self.assertRaises(ValueError):
                boundary._snapshot(value, (1, 1), 'fixture', lambda: False)

    def test_alpha_and_roi_refuse_before_loading_native(self):
        rgba = np.ones((1, 1, 4), dtype=np.float32)
        mask = np.ones((1, 1), dtype=np.float32)
        with patch.object(boundary, 'native') as loader:
            rgba[0, 0, 3] = 0.5
            with self.assertRaises(ValueError):
                boundary.prepare(rgba, mask, mask, (0, 0, 1, 1))
            rgba[0, 0, 3] = 1
            with self.assertRaises(ValueError):
                boundary.prepare(rgba, mask, mask, (0, 0, 769, 1))
            with self.assertRaises(ValueError):
                boundary.prepare(rgba, mask, mask, (True, 0, 1, 1))
            loader.assert_not_called()

    def test_cancel_never_publishes_output(self):
        rgba = np.ones((1, 1, 4), dtype=np.float32)
        mask = np.ones((1, 1), dtype=np.float32)
        with patch.object(boundary, 'native') as loader:
            with self.assertRaises(InterruptedError):
                boundary.prepare(rgba, mask, mask, (0, 0, 1, 1), cancelled=lambda: True)
            loader.assert_not_called()

    def test_callback_exception_is_preserved(self):
        def broken():
            raise RuntimeError('cancellation provider failed')
        callback, errors = boundary._callback(broken)
        self.assertEqual(callback(), 1)
        with self.assertRaisesRegex(RuntimeError, 'provider failed'):
            boundary._result(3, lambda: False, errors)

    def test_density_and_dimensions_refuse_before_native(self):
        with patch.object(boundary, 'native') as loader:
            with self.assertRaises(ValueError):
                boundary.fuse(None, None, None, (1, 1), density=float('nan'))
            with self.assertRaises(ValueError):
                boundary.fuse(None, None, None, (1, 1), density=True)
            with self.assertRaises(ValueError):
                boundary.fuse(None, None, None, (0, 1))
            loader.assert_not_called()

    def test_selected_pixels_outside_roi_are_not_silently_dropped(self):
        source = np.ones((3, 3, 4), dtype=np.float32)
        selected = np.zeros((3, 3), dtype=np.float32)
        selected[0, 0] = 1
        selected[2, 2] = 1
        with patch.object(boundary, 'native') as loader:
            with self.assertRaises(ValueError):
                boundary.prepare(source, selected, np.zeros_like(selected), (0, 0, 2, 2))
            loader.assert_not_called()
