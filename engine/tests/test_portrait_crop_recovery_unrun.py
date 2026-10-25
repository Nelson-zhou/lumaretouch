# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: recovery terminal boundary, not photographic acceptance."""
from types import SimpleNamespace
import unittest
from lumaretouch_engine import portrait_crop_recovery as C


class CropRecovery(unittest.TestCase):
    def setUp(self):
        self.runtime = SimpleNamespace(revision=7, tainted=False, reason=None)
        self.engine = SimpleNamespace(_project_recovery_runtime=self.runtime,
            _document_versions=lambda: SimpleNamespace(workspace='workspace-1'),
            _portrait_crop_commit_receipts={})
        self.request = {'cmd': 'portrait_crop', 'action': 'apply', 'request_id': 'crop-1'}
        self.boundary = {'message': self.request, 'started': True, 'returned': True}

    def event(self, phase, **facts):
        if phase == 'committed':
            self.engine._portrait_crop_commit_receipts['crop-1'] = {
                'workspace': 'workspace-1', 'result': facts['result']}
        return {'event': 'portrait_crop_result', 'request_id': 'crop-1',
                'original_request': dict(self.request), 'phase': phase, **facts}

    def test_provisional_unknown_then_committed_does_not_taint(self):
        C.observe(self.boundary, self.event('unknown', outcome_unknown=True))
        C.observe(self.boundary, self.event('committed', result={'status': 'applied'}))
        self.assertTrue(C.finish(self.engine, self.boundary, None))
        self.assertFalse(self.runtime.tainted)
        self.assertEqual(self.runtime.revision, 8)
        C.finish(self.engine, self.boundary, None)
        self.assertEqual(self.runtime.revision, 8)

    def test_no_change_and_proven_no_write_do_not_advance(self):
        for event in (self.event('committed', result={'status': 'no_change'}),
                      self.event('rejected', no_write=True)):
            C.observe(self.boundary, event)
            C.finish(self.engine, self.boundary, None)
        self.assertEqual(self.runtime.revision, 7)
        self.assertFalse(self.runtime.tainted)

    def test_only_exact_query_can_reconcile_own_taint(self):
        C.observe(self.boundary, self.event('unknown', outcome_unknown=True))
        C.finish(self.engine, self.boundary, None)
        self.assertTrue(self.runtime.tainted)
        query = {'cmd': 'portrait_crop', 'action': 'status', 'request_id': 'query-1', 'target_request_id': 'crop-1'}
        boundary = {'message': query, 'started': True, 'returned': True}
        committed = self.event('committed', result={'status': 'applied'})
        C.observe(boundary, {'event': 'portrait_crop_result', 'request_id': 'query-1',
                            'original_request': query, 'phase': 'status', 'receipt': committed})
        C.finish(self.engine, boundary, None)
        self.assertFalse(self.runtime.tainted)
        self.assertEqual(self.runtime.revision, 8)

    def test_unrelated_taint_is_not_cleared(self):
        self.runtime.tainted = True
        self.runtime.reason = 'another incomplete operation'
        C.observe(self.boundary, self.event('committed', result={'status': 'applied'}))
        C.finish(self.engine, self.boundary, None)
        self.assertTrue(self.runtime.tainted)
        self.assertEqual(self.runtime.reason, 'another incomplete operation')

    def test_read_failure_does_not_taint(self):
        self.boundary['message'] = {'cmd': 'portrait_crop', 'action': 'preview', 'request_id': 'preview-1'}
        C.finish(self.engine, self.boundary, 'read failed')
        self.assertFalse(self.runtime.tainted)
        self.assertEqual(self.runtime.revision, 7)

    def test_unknown_preserves_other_taint_and_reason(self):
        self.runtime.tainted = True
        self.runtime.reason = 'unrelated incomplete write'
        self.runtime._portrait_crop_taint = 'crop-1'
        C.observe(self.boundary, self.event('unknown', outcome_unknown=True))
        C.finish(self.engine, self.boundary, None)
        self.assertEqual(self.runtime.reason, 'unrelated incomplete write')

    def test_old_workspace_receipt_does_not_advance(self):
        C.observe(self.boundary, self.event('committed', result={'status': 'applied'}))
        self.engine._portrait_crop_commit_receipts['crop-1']['workspace'] = 'old-workspace'
        C.finish(self.engine, self.boundary, None)
        self.assertEqual(self.runtime.revision, 7)
