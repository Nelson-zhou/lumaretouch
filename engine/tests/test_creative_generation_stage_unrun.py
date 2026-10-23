"""AUTHORED / UNRUN: isolation and genuine-source staging contracts.

Mocks below exercise transaction boundaries only; they are not a product model,
not generated candidates, and not inference or pixel-quality acceptance evidence.
"""
import json
import unittest
from unittest.mock import patch
import numpy as np
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.creative_generation_backend import Candidate, CandidatePair, GenerationSettings
from lumaretouch_engine.creative_generation_pack import PackUnavailable
from lumaretouch_engine.creative_generation_stage import stage_pair


class StageContractUnrun(unittest.TestCase):
    def test_pack_unavailable_before_input_or_native_model_loading(self):
        with patch('lumaretouch_engine.creative_generation_pack.verify_pack',
                   side_effect=PackUnavailable('upstream_manifest_incomplete', 'Unverified')):
            with self.assertRaises(PackUnavailable):
                stage_pair(None, None, None, roi=(0, 0, 1, 1), seeds=(1, 2),
                           settings=GenerationSettings('empty pavement'))

    def test_real_asset_id_and_roi_bound_without_publication(self):
        source = make_asset('rgba', 4, 3, np.ones((3, 4, 4), '<f4').tobytes())
        mask = np.zeros((3, 4), '<f4'); mask[1, 1] = .5
        selection = make_asset('mask', 4, 3, mask.tobytes())
        protected = make_asset('mask', 4, 3, np.zeros((3, 4), '<f4').tobytes())
        rgb = np.full((768, 768, 3), .5, np.float32)
        binary = np.zeros((768, 768), np.float32); binary[0, 0] = 1
        eligible = binary * .5
        candidate = Candidate(np.full((2, 2, 3), .25, np.float32), 1, 'fixture')
        pair = CandidatePair((candidate, candidate), '{}')
        rgba = np.zeros((768, 768, 4), np.float32); rgba[0, 0] = (.1, .1, .1, .5)
        with patch('lumaretouch_engine.creative_generation_pack.verify_pack'), \
             patch('lumaretouch_engine.creative_generation_patch_native.prepare', return_value=(rgb,binary,eligible)) as prepare, \
             patch('lumaretouch_engine.creative_generation_patch_native.fuse', return_value=rgba), \
             patch('lumaretouch_engine.creative_generation_backend.generate_pair', return_value=pair):
            result = stage_pair(source, selection, protected, roi=(1, 1, 2, 2),
                seeds=(1, 2), settings=GenerationSettings('empty pavement'))
        evidence = json.loads(result.provenance_json)
        self.assertEqual(evidence['job']['source_asset'], source['id'])
        self.assertEqual(evidence['job']['selection_asset'], selection['id'])
        self.assertEqual(evidence['placement'], {'x': 1, 'y': 1})
        self.assertFalse(evidence['published']); self.assertFalse(evidence['reviewed'])
        self.assertEqual(len(result.assets), 2)
        self.assertEqual((result.assets[0]['width'], result.assets[0]['height']), (2, 2))
        self.assertFalse(prepare.call_args.args[0].flags.writeable)
        self.assertEqual(source['content'], np.ones((3, 4, 4), '<f4').tobytes())
