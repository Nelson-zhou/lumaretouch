# SPDX-License-Identifier: GPL-3.0-or-later
"""Cohort contract fixtures authored only. No imports/tests executed here."""
from copy import deepcopy
from pathlib import Path
import unittest


class DecorationCohortContracts(unittest.TestCase):
    def test_retained_unmapped_active_face_forces_review(self):
        from lumaretouch_engine.face_decoration_cohort_review import content_required
        state={'before':[{'recipe':{'version':1,'pattern':'freckle_dust','strength':0.2}}],
               'after':[{'recipe':{'version':1,'pattern':'freckle_dust','strength':0.0}}]}
        self.assertTrue(content_required({'selection':{}},{'intent':[]},[state]))
        neutral=deepcopy(state);neutral['before'][0]['recipe']['strength']=0.0
        self.assertFalse(content_required({'selection':{}},{'intent':[]},[neutral]))
        self.assertTrue(content_required({'selection':{'lnx.face_decoration.v1':['/strength']}},{'intent':[]},[neutral]))
        self.assertTrue(content_required({'selection':{}},{'intent':[{'op':'lnx.face_decoration.v1'}]},[neutral]))

    def test_member_state_requires_current_source_and_sorted_unique_faces(self):
        from lumaretouch_engine.face_decoration_cohort_review import checked_state
        row={'face_ref':{'face_instance_id':'face-one','asset_sha256':'a'*64,'analysis_revision':1},
             'recipe':{'version':1,'pattern':'freckle_dust','strength':0.0}}
        state={'before':[row],'after':[row]}
        self.assertEqual(checked_state(state,'a'*64),state)
        with self.assertRaises(ValueError):checked_state(state,'b'*64)
        with self.assertRaises(ValueError):checked_state({'before':[row,row],'after':[row]},'a'*64)

    def test_cohort_read_does_not_accept_ordinary_or_alias_authority(self):
        from lumaretouch_engine.face_decoration_cohort_store import image_read_only
        request={'cmd':'batch','action':'face_decoration_cohort_visual','request_id':'read',
            'preflight_token':'a'*32,'document_id':'b'*32,'revision':'4','side':'after','sha256':'c'*64}
        self.assertTrue(image_read_only(request))
        self.assertFalse(image_read_only({**request,'action':'face_decoration_visual'}))
        self.assertFalse(image_read_only({**request,'face_decoration_cohort_ack':[]}))
        for key in request:
            changed=dict(request);changed.pop(key);self.assertFalse(image_read_only(changed))

    def test_failure_context_keeps_source_first_ack_and_scope_even_unlink(self):
        from lumaretouch_engine.face_decoration_cohort_store import failure_context
        request={'action':'commit','preflight_token':'a'*32,'module_scope':[],
            'face_decoration_cohort_ack':[{'document_id':'source'},{'document_id':'target'}]}
        result=failure_context(request)
        self.assertEqual(result['face_decoration_cohort_ack'],request['face_decoration_cohort_ack'])
        self.assertEqual(result['module_scope'],[])
        self.assertIs(result['face_decoration_cohort'],True)


class DecorationCohortWiring(unittest.TestCase):
    def test_complete_source_and_every_member_checked_before_claim(self):
        root=Path(__file__).parents[1]/'src'/'lumaretouch_engine'
        flow=(root/'people_cross_owner_workflow.py').read_text()
        self.assertIn("item['face_decoration_cohort_state'] = DECORATION.state(item)",flow)
        self.assertIn('DECORATION.required(endpoints,selected,review)',flow)
        self.assertLess(flow.index('decoration_history=prepare_decoration_history'),flow.index('controller.store.claim(plan'))
        self.assertIn('face_decoration_cohort_history=decoration_history',flow)
        self.assertIn('association_source',flow)
        review=(root/'face_decoration_cohort_review.py').read_text()
        self.assertIn("VISUAL.FIELDS-{'coverage_sha256'}",review)
        self.assertIn("required_ids={ref['face_instance_id']}",review)
        self.assertIn('snapshot_key(engine',review)
        self.assertNotIn('support_transfer\': \'copy',review)

    def test_history_reuses_validator_without_storing_wrong_family(self):
        root=Path(__file__).parents[1]/'src'/'lumaretouch_engine'
        source=(root/'face_decoration_cohort_history.py').read_text()
        self.assertIn("KEY='face_decoration_cohort_review'",source)
        self.assertIn('COMMON.verify_restore',source)
        self.assertNotIn('class ',source)
        records=(root/'face_decoration_batch_review.py').read_text()
        self.assertIn("params.get('mode')=='persistent_association'",records)
        self.assertIn('Ordinary decoration proof cannot authorize a cohort',records)


if __name__=='__main__':unittest.main()
