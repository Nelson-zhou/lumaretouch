# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored acceptance fixtures. UNRUN: no product imports or tests executed."""
from copy import deepcopy
from pathlib import Path
import unittest


class DecorationCoverageContracts(unittest.TestCase):
    def test_neutral_and_active_coverage_have_distinct_support_authority(self):
        from lumaretouch_engine.face_decoration_batch_review import coverage_checked
        ref={'asset_sha256':'a'*64,'face_instance_id':'face-one','analysis_revision':1}
        neutral={'version':1,'support_transfer':'none','targets':[{'face_ref':ref,
            'scope':'neutral-no-effect','visibility_sha256':None,'recipe_sha256':'b'*64}]}
        self.assertEqual(coverage_checked(neutral),neutral)
        bad=deepcopy(neutral);bad['targets'][0]['visibility_sha256']='c'*64
        with self.assertRaises(ValueError):coverage_checked(bad)
        active=deepcopy(bad);active['targets'][0]['scope']='target-reviewed-visible-skin'
        self.assertEqual(coverage_checked(active),active)

    def test_duplicate_or_borrowed_coverage_not_silently_merged(self):
        from lumaretouch_engine.face_decoration_batch_review import coverage_checked
        ref={'asset_sha256':'a'*64,'face_instance_id':'face-one','analysis_revision':1}
        row={'face_ref':ref,'scope':'target-reviewed-visible-skin','visibility_sha256':'c'*64,'recipe_sha256':'b'*64}
        with self.assertRaises(ValueError):coverage_checked({'version':1,'support_transfer':'none','targets':[row,row]})
        with self.assertRaises(ValueError):coverage_checked({'version':1,'support_transfer':'donor','targets':[row]})

    def test_paged_read_requires_every_exact_coordinate(self):
        from lumaretouch_engine.face_decoration_batch_store import image_read_only
        request={'cmd':'batch','action':'face_decoration_visual','request_id':'read-one',
            'preflight_token':'a'*32,'document_id':'document-one','revision':'1','side':'before','sha256':'b'*64}
        self.assertTrue(image_read_only(request))
        for key in request:
            bad=dict(request);bad.pop(key)
            self.assertFalse(image_read_only(bad))
        self.assertFalse(image_read_only({**request,'face_decoration_review_ack':[]}))

    def test_commits_and_unknown_replies_keep_family_correlation(self):
        from lumaretouch_engine.face_decoration_batch_store import failure_context
        ack=[{'document_id':'d','revision':'1','before_sha256':'a'*64,'after_sha256':'b'*64,'coverage_sha256':'c'*64}]
        result=failure_context({'cmd':'batch','action':'commit','preflight_token':'d'*32,'face_decoration_review_ack':ack})
        self.assertEqual(result['face_decoration_review_ack'],ack)
        self.assertIs(result['face_decoration_visual_required'],True)


class DecorationBatchWiring(unittest.TestCase):
    def test_complete_render_snapshot_and_publication_order_are_authored(self):
        root=Path(__file__).parents[1]/'src'/'lumaretouch_engine'
        plan=(root/'face_decoration_batch_plan.py').read_text()
        self.assertIn("for graph in (before,candidate)",plan)
        self.assertIn('VISUAL.prepare(engine,row,plan[',plan)
        self.assertIn('snapshot_key(engine,row,row[',plan)
        self.assertIn("'before':display['before'],'after':display['after']",plan)
        transfer=(root/'people_batch_transfer.py').read_text()
        self.assertLess(transfer.index('verify_decoration(engine'),transfer.index('controller.store.claim(plan'))
        self.assertLess(transfer.index('controller.store.claim(plan'),transfer.index('result=publish('))
        self.assertIn('face_decoration_history=decoration_history',transfer)
        self.assertIn("item['outcome']='noop'",transfer)

    def test_history_is_persisted_and_gated_not_a_second_owner(self):
        root=Path(__file__).parents[1]/'src'/'lumaretouch_engine'
        history=(root/'face_decoration_batch_history.py').read_text()
        self.assertIn("KEY='face_decoration_batch_review'",history)
        self.assertIn('COMMON.verify_restore',history)
        self.assertNotIn('class ',history)
        persistence=(root/'people_history_persistence.py').read_text()
        self.assertEqual(persistence.count('check_decoration_history(entry)'),2)
        ledger=(root/'people_batch_ledger.py').read_text()
        self.assertEqual(ledger.count('verify_decoration_restore(engine,batch,plans,'),2)


if __name__=='__main__':unittest.main()
