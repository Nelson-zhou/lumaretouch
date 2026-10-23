"""UNRUN: source-authored contracts, not inference/precision/quality acceptance.

Run only in the separately authorized local validation workflow. These numerical
fixtures do not load weights; a real installed-pack integration run is still owed.
"""
import unittest
from unittest.mock import patch
import numpy as np

from lumaretouch_engine.creative_generation_backend import (
    EDGE, Candidate, GenerationSettings, _check_settings, _decode_output, _digest, _diversity, _prepare,
    generate_pair,
)


class BackendContractUnrun(unittest.TestCase):
    def inputs(self):
        source = np.full((3, 5, 3), np.float32(32769 / 65535), dtype=np.float32)
        mask = np.zeros((3, 5), dtype=np.float32)
        mask[1, 2] = 1
        protected = np.zeros_like(mask)
        protected[0, 0] = 1
        return source, mask, protected

    def test_padding_preserves_low_bits_and_original_ownership(self):
        source, mask, protected = self.inputs()
        saved = source.copy()
        result, repaint, protection, padded, decoder_mask = _prepare(source, mask, protected)
        self.assertTrue(np.array_equal(padded[:3, :5], saved))
        self.assertEqual(padded.shape, (EDGE, EDGE, 3))
        self.assertEqual(float(decoder_mask[3:, :].sum()), 0)
        self.assertFalse(np.shares_memory(result, source))
        self.assertFalse(np.shares_memory(repaint, mask))
        self.assertFalse(np.shares_memory(protection, protected))
        self.assertTrue(np.array_equal(source, saved))

    def test_reject_alpha_hdr_nonfinite_and_oversized(self):
        source, mask, protected = self.inputs()
        bad_sources = [np.ones((3, 5, 4), dtype=np.float32),
                       source.astype(np.float64), source + 1,
                       source * np.float32(np.nan),
                       np.zeros((769, 5, 3), dtype=np.float32)]
        for bad in bad_sources:
            with self.subTest(shape=bad.shape), self.assertRaises(ValueError):
                _prepare(bad, mask, protected)

    def test_protection_and_binary_mask_are_not_silently_adjusted(self):
        source, mask, protected = self.inputs()
        for bad_mask in (mask * .5, np.ones_like(mask), np.zeros_like(mask), protected):
            with self.assertRaises(ValueError):
                _prepare(source, bad_mask, protected)

    def test_distinct_seed_and_bounded_settings_contract(self):
        settings = GenerationSettings("empty pavement matching surrounding scene")
        _check_settings(settings, (0, 2**63 - 1))
        for seeds in ((1, 1), (-1, 2), (True, 2), (1, 2**63), [1, 2]):
            with self.assertRaises(ValueError):
                _check_settings(settings, seeds)
        with self.assertRaises(ValueError):
            _check_settings(GenerationSettings("test", decoder_guidance=float("nan")), (1, 2))

    def test_generated_only_sdr_transform_receipts_preclamp_values(self):
        raw = np.zeros((1, 3, EDGE, EDGE), dtype=np.float32)
        raw[0, 0, 0, 0] = -1.1
        raw[0, 1, 0, 0] = 1.1
        rgb, evidence = _decode_output(raw, 3, 5)
        self.assertEqual(rgb.shape, (3, 5, 3))
        self.assertEqual(rgb.dtype, np.float32)
        self.assertFalse(rgb.flags.writeable)
        self.assertEqual(evidence["raw_sha256"], _digest(raw))
        self.assertEqual(evidence["below_minus_one"], 1)
        self.assertEqual(evidence["above_plus_one"], 1)
        self.assertEqual(float(rgb[0, 0, 0]), 0)
        self.assertEqual(float(rgb[0, 0, 1]), 1)
        self.assertEqual(float(rgb[0, 0, 2]), .5)
        raw[0, 0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            _decode_output(raw, 3, 5)

    def test_unavailable_pack_raises_before_optional_model_loading(self):
        from lumaretouch_engine.creative_generation_pack import PackUnavailable
        source, mask, protected = self.inputs()
        with patch("lumaretouch_engine.creative_generation_pack.verify_pack",
                   side_effect=PackUnavailable("fixture_unavailable", "No verified model")):
            with self.assertRaises(PackUnavailable):
                generate_pair(source, mask, protected, seeds=(1, 2),
                              settings=GenerationSettings("empty floor"), pack_root=None)

    def test_two_genuine_equal_samples_are_receipted_not_rejected(self):
        source, repaint, _protected = self.inputs()
        candidates = (Candidate(source.copy(), 1, _digest(source)),
                      Candidate(source.copy(), 2, _digest(source)))
        self.assertEqual(_diversity(candidates, repaint),
                         {"identical_whole_output": True, "identical_repaint_area": True})
        different = source.copy()
        different[0, 0, 0] = 0
        outside_only = (candidates[0], Candidate(different, 2, _digest(different)))
        self.assertEqual(_diversity(outside_only, repaint),
                         {"identical_whole_output": False, "identical_repaint_area": True})


if __name__ == "__main__":
    unittest.main()
