# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No product import, test runner or runtime was executed."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from lumaretouch_engine import portrait_group_reference as R


class ReferenceGroupContract(unittest.TestCase):
    def test_reference_only_intent_not_retained_or_copied_gain(self):
        with patch.object(R.RC, 'check_params', return_value={'strength': 1.0}):
            self.assertTrue(R.support({'modules': {R.RC.OP: {}}})['supported'])
            self.assertFalse(R.support({'modules': {R.RC.OP: {}, 'lnx.skin_finish.v1': {}}})['supported'])
        with patch.object(R.RC, 'check_params', side_effect=ValueError('gain not portable')):
            self.assertFalse(R.support({'modules': {R.RC.OP: {'log2_gains': [1, 1, 1]}}})['supported'])

    def test_frozen_fit_is_reused_without_fitting_or_face_analysis(self):
        row = {'path': 'target.png', 'state': {'unchanged': 1}, 'undo': [], 'redo': []}
        group = SimpleNamespace(engine=SimpleNamespace(), _row=lambda doc: (2, row),
            batch=SimpleNamespace(versions=SimpleNamespace(version=lambda row:
                SimpleNamespace(revision=7))))
        record = {'reference': {'document_id': 'reference', 'source': {'sha256': 'a'*64}},
            'target': {'document_id': 'target', 'revision': '7'}, 'recipe': {'own': 'target'}}
        proof = {'render': {'source_proof': {'asset_sha256': 'b'*64}}, 'repair_sha256': 'c'*64}
        preset = {'modules': {R.RC.OP: {'version': 1, 'strength': 1, 'reference': {}}}}
        def install(candidate, recipe):
            candidate['_reference_color'] = deepcopy(recipe)
        with patch.object(R.SOURCE, 'record', return_value=None), \
             patch.object(R.SOURCE, 'row_proof', return_value={'asset_sha256': 'b'*64}), \
             patch.object(R.full, 'people_context', return_value={}), \
             patch.object(R.review, '_proof', return_value=(proof, {})), \
             patch.object(R.RC, 'verify_target', return_value=record['recipe']) as verify, \
             patch.object(R.RC, 'apply_verified', side_effect=install), \
             patch('lumaretouch_engine.white_balance_recipe.prepare_state'), \
             patch.object(R.RE, 'prepare_target', return_value=record) as fit:
            first = R.inputs(group, 'target', preset)
            second = R.inputs(group, 'target', preset, first[0]['reference_fit'])
            self.assertEqual(fit.call_count, 1)
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(first[0], second[0])
            self.assertEqual(row['state'], {'unchanged': 1})
            self.assertEqual(row['undo'], [])
            self.assertIsNot(first[0]['reference_fit'], record)
            with self.assertRaisesRegex(ValueError, 'remain unchanged'):
                R.inputs(group, 'reference', preset, record)
