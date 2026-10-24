# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Requires installed NumPy/Torch; never run during authoring."""
import unittest
import numpy as np
from lumaretouch_engine.brow_enhance_composition import apply_np, apply_t


class BrowCompositionUnrun(unittest.TestCase):
    def test_zero_is_exact_identity(self):
        source = np.array([[[.1, .4, .8]]], np.float32)
        self.assertIs(apply_np(source, np.zeros_like(source)), source)

    def test_feasible_delta_not_channel_clipped(self):
        source = np.array([[[.9, .5, .2]]], np.float32)
        delta = np.array([[[.4, .2, -.1]]], np.float32)
        before = source.copy()
        result = apply_np(source, delta)
        ratio = (result-source)/delta
        np.testing.assert_allclose(ratio, np.full_like(ratio, ratio[0, 0, 0]), atol=8e-7)
        self.assertTrue(np.all((result >= 0) & (result <= 1)))
        np.testing.assert_array_equal(source, before)
        self.assertLess(float(result[0, 0, 1]), .56)

    def test_active_hdr_and_nonfinite_refuse(self):
        for value in (1.1, -.1, float('nan'), float('inf')):
            source = np.array([[[value, .4, .5]]], np.float32)
            with self.assertRaises(ValueError):
                apply_np(source, np.full_like(source, .01))
        with self.assertRaises(ValueError):
            apply_np(np.zeros((1, 1, 3), np.float32), np.full((1, 1, 3), np.nan, np.float32))

    def test_wrong_dtype_and_shape_refuse(self):
        with self.assertRaises(ValueError):
            apply_np(np.zeros((2, 3), np.float32), np.zeros((2, 3), np.float32))
        with self.assertRaises(ValueError):
            apply_np(np.zeros((1, 1, 3)), np.zeros((1, 1, 3), np.float32))

    def test_device_algebra_matches_cpu(self):
        import torch
        source = np.array([[[.9, .5, .2], [.02, .7, .3], [.1, .2, .3]]], np.float32)
        delta = np.array([[[.4, .2, -.1], [-.1, .1, -.2], [0, 0, 0]]], np.float32)
        cpu = apply_np(source, delta)
        current = torch.from_numpy(source.transpose(2, 0, 1)[None].copy())
        change = torch.from_numpy(delta.transpose(2, 0, 1)[None].copy())
        out = apply_t(current, change).numpy()[0].transpose(1, 2, 0)
        np.testing.assert_allclose(out, cpu, atol=2*np.finfo(np.float32).eps, rtol=0)
        self.assertIs(apply_t(current, torch.zeros_like(current)), current)
