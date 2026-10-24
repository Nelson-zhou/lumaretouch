# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored UNRUN contracts; not imported/executed and not portrait acceptance.

Native-dependent fixtures intentionally fail if the explicitly packaged .so is
absent. They must not silently skip or use a substitute renderer.
"""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from lumaretouch_engine import face_decoration_state as S
from lumaretouch_engine.face_decoration_catalogue import catalogue, CATALOGUE_SHA256
from lumaretouch_engine.face_decoration_native import delta
from lumaretouch_engine.face_decoration_layer import prepare_record


class FaceDecorationIntent(unittest.TestCase):
    def test_exact_count_original_distinct_layouts(self):
        rows = catalogue()['patterns']
        self.assertEqual(tuple(row['id'] for row in rows), S.PATTERNS)
        self.assertEqual([row['kind'] for row in rows], ['freckle'] * 5 + ['mole'] * 3)
        self.assertEqual(len({json.dumps(row['marks']) for row in rows}), 8)
        self.assertIn('图像左', rows[5]['label'])
        self.assertIn('图像右', rows[6]['label'])
        self.assertTrue(all(1 <= len(row['marks']) <= 64 for row in rows))

    def test_catalogue_bytes_are_pinned(self):
        import lumaretouch_engine.face_decoration_catalogue as C
        path = Path(C.__file__).with_name('face_decoration_patterns.json')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), CATALOGUE_SHA256)

    def test_recipe_is_only_portable_intent(self):
        self.assertEqual(set(S.preset(S.neutral())), {'version', 'pattern', 'strength'})
        self.assertEqual(len(S.patches(S.neutral())), 2)
        self.assertFalse(S.active(None))
        for value in (True, -1, 2, float('inf'), float('nan'), 10 ** 1000, '0.5'):
            with self.assertRaises(ValueError):
                S.check({**S.neutral(), 'strength': value})
        for value in ({**S.neutral(), 'version': True}, {**S.neutral(), 'pattern': 'apple'},
                      {**S.neutral(), 'face_ref': {}}, {**S.neutral(), 'mask': []}):
            with self.assertRaises(ValueError):
                S.check(value)

    def test_neutral_needs_no_source_review_or_native(self):
        with patch('lumaretouch_engine.face_decoration_native.native', side_effect=AssertionError('native loaded')):
            self.assertIsNone(prepare_record(None, None, S.neutral(), None,
                                            excluded=None, skin=None, backend=None, semantic_sha=None))

    def test_capability_probes_native_and_is_not_an_acceptance_claim(self):
        with patch('lumaretouch_engine.face_decoration_native.available', return_value=False):
            value = S.capability()
        self.assertEqual(value['face_decoration_protocol'], 1)
        self.assertFalse(value['face_decoration_available'])
        self.assertTrue(value['face_decoration_reason'])
        self.assertEqual(value['face_decoration_contract']['source_only_validation'], 'UNRUN')


class FaceDecorationSupport(unittest.TestCase):
    def test_review_feather_is_not_mistaken_for_semantic_confidence(self):
        from lumaretouch_engine.face_decoration_geometry import _visible_support
        skin = np.full((1, 4), .8, np.float32)
        reviewed = np.array([[0, .25, .5, 1]], np.float32)
        support = _visible_support(np.ones_like(skin), skin, np.zeros_like(skin), reviewed)
        self.assertTrue(np.array_equal(support, reviewed * skin))
        self.assertGreater(float(support[0, 1]), 0)

    def test_semantics_exclusion_and_review_only_intersect(self):
        from lumaretouch_engine.face_decoration_geometry import _visible_support
        skin = np.array([[.69, .8, 1, 1]], np.float32)
        excluded = np.array([[0, .11, 0, 0]], np.float32)
        reviewed = np.array([[1, 1, 0, 1]], np.float32)
        geometry = np.array([[1, 1, 1, 0]], np.float32)
        self.assertTrue(np.array_equal(_visible_support(geometry, skin, excluded, reviewed), np.zeros_like(skin)))

    def test_missing_evidence_and_synthetic_backend_refuse(self):
        from lumaretouch_engine.face_decoration_geometry import mask, fields
        weight = np.ones((8, 8), np.float32)
        with self.assertRaises(ValueError):
            mask(None, (8, 8), '审核')
        with self.assertRaises(ValueError):
            mask(weight.astype(np.float64), (8, 8), '审核')
        with self.assertRaises(ValueError):
            fields(np.zeros((478, 2), np.float32), (8, 8), weight, weight,
                   backend='synthetic', reviewed=weight)


class FaceDecorationNative(unittest.TestCase):
    def fixture(self, size=192, scale=80):
        return (np.full((size, size, 3), 32769 / 65535, np.float32),
                np.array([[size/2, size/2], [scale, 0], [0, scale]], np.float32),
                np.ones((size, size), np.float32))

    def test_exact_neutral_without_loading_native(self):
        source, frame, support = self.fixture()
        with patch('lumaretouch_engine.face_decoration_native.native', side_effect=AssertionError('native loaded')):
            out = delta(source, frame, support, S.neutral())
        self.assertTrue(np.array_equal(out.view(np.uint32), np.zeros_like(out).view(np.uint32)))

    def test_distinct_patterns_strength_and_unmodified_source(self):
        source, frame, support = self.fixture()
        before = source.copy()
        spatial = set()
        for pattern in S.PATTERNS:
            full = delta(source, frame, support, {'version': 1, 'pattern': pattern, 'strength': 1})
            half = delta(source, frame, support, {'version': 1, 'pattern': pattern, 'strength': .5})
            self.assertTrue(np.allclose(full * .5, half, rtol=2e-6, atol=1e-8))
            self.assertTrue(np.any(full < 0))
            self.assertTrue(np.all(full <= 0))
            self.assertTrue(np.all((source + full >= 0) & (source + full <= 1)))
            self.assertTrue(np.isfinite(full).all())
            spatial.add(full.tobytes())
        self.assertEqual(len(spatial), 8)
        self.assertTrue(np.array_equal(source, before))

    def test_zero_support_exact_no_leakage(self):
        source, frame, support = self.fixture()
        support[:, :96] = 0
        out = delta(source, frame, support, {**S.neutral(), 'strength': 1})
        self.assertTrue(np.array_equal(out[:, :96], np.zeros_like(out[:, :96])))
        support[:] = 0
        out = delta(source, frame, support, {**S.neutral(), 'strength': 1})
        self.assertTrue(np.array_equal(out, np.zeros_like(out)))

    def test_repeated_call_has_no_random_flicker(self):
        source, frame, support = self.fixture()
        recipe = {**S.neutral(), 'strength': .71, 'pattern': 'freckle_scatter'}
        self.assertTrue(np.array_equal(delta(source, frame, support, recipe), delta(source, frame, support, recipe)))

    def test_subpixel_layout_mass_does_not_vanish_or_jump(self):
        source, frame, support = self.fixture(64, 12)
        recipe = {**S.neutral(), 'strength': 1, 'pattern': 'freckle_dust'}
        totals = []
        for phase in (0, .125, .375, .625, .875):
            moved = frame.copy(); moved[0] += phase
            out = delta(source, moved, support, recipe)
            totals.append(float(np.sum(out, dtype=np.float64)))
        self.assertLess(max(totals), -.001)
        self.assertLess(max(totals) - min(totals), 2e-6)

    def test_scale_integral_and_frozen_tile_crops(self):
        source, frame, support = self.fixture(96, 32)
        recipe = {**S.neutral(), 'strength': .6, 'pattern': 'freckle_bridge'}
        low = delta(source, frame, support, recipe)
        high = delta(np.repeat(np.repeat(source, 2, 0), 2, 1), frame * 2,
                     np.ones((192, 192), np.float32), recipe)
        averaged = high.reshape(96, 2, 96, 2, 3).mean(axis=(1, 3))
        self.assertTrue(np.allclose(low, averaged, atol=2e-7, rtol=2e-5))
        stitched = np.concatenate((high[:73], high[73:]), axis=0)
        self.assertTrue(np.array_equal(stitched, high))

    def test_invalid_sdr_and_noncontiguous_fields_refuse(self):
        source, frame, support = self.fixture()
        recipe = {**S.neutral(), 'strength': 1}
        for value in (float('nan'), float('inf'), -.01, 1.01):
            bad = source.copy(); bad[0, 0, 0] = value
            with self.assertRaises(ValueError):
                delta(bad, frame, support, recipe)
        with self.assertRaises(ValueError):
            delta(source[:, ::-1], frame, support, recipe)
        bad = support.copy(); bad[0, 0] = 1.1
        with self.assertRaises(ValueError):
            delta(source, frame, bad, recipe)


if __name__ == '__main__':
    unittest.main()
