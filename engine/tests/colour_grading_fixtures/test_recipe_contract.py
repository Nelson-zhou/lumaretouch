"""UNRUN fixtures. Execute only in authorized Qoder/local validation environment."""
import unittest
from lumaretouch_engine import colour_grading_state as S
from lumaretouch_engine import colour_grading_adapters as A
from lumaretouch_engine.colour_grading_controller import ColourGradingController


class Host:
    requires_reload = False
    def __init__(self): self.revision = 0; self.recipe = S.neutral(); self.history = 0
    def context(self): return ('document-a', self.revision)
    def render_preview(self, recipe, cancelled):
        if cancelled(): raise InterruptedError()
        return {'path': 'preview.png'}
    def render_committed(self): return {'path': 'committed.png'}
    def commit(self, recipe, doc, revision):
        self.recipe = recipe; self.revision += 1; self.history += 1
        return {'recipe': recipe, 'revision': self.revision}


class ColourGradingContract(unittest.TestCase):
    def test_exact_recipe_roundtrip_and_all_wheels(self):
        r = S.neutral()
        for k in S.RANGES: r[k] = {'hue': 240, 'saturation': 40, 'luminance': -20}
        self.assertEqual(A.check_preset(A.preset_from_state({S.KEY: r})), r)
        self.assertEqual(S.from_state({}), S.neutral())
        with self.assertRaises(ValueError): S.from_state({S.KEY: None})
        with self.assertRaises(ValueError): S.check({**r, 'balance': True})
        with self.assertRaises(ValueError): S.check({**r, 'blending': float('nan')})
        with self.assertRaises(ValueError): S.check({**r, 'algorithm': 'hsl'})

    def test_batch_replaces_and_isolates_recipe(self):
        p = A.preset_from_state({}); rows = A.prepare_batch([{}, {}], p)
        rows[0][S.KEY]['global']['saturation'] = 5
        self.assertEqual(rows[1][S.KEY]['global']['saturation'], 0)

    def test_cancel_prevents_commit_and_restores_visible_frame(self):
        h = Host(); c = ColourGradingController(h)
        base = {'cmd':'colour_grading', 'document_id':'document-a', 'revision':0}
        c.handle({**base, 'action':'preview', 'request_id':'p', 'recipe':S.neutral()})
        result = c.handle({**base, 'action':'cancel', 'request_id':'x'})
        self.assertEqual(result['frame']['path'], 'committed.png')
        with self.assertRaises(ValueError): c.handle({**base, 'action':'commit', 'request_id':'c', 'preview_id':'p'})
        self.assertEqual(h.history, 0)

    def test_latest_preview_and_one_history_and_status_after_revision(self):
        h = Host(); c = ColourGradingController(h)
        base = {'cmd':'colour_grading', 'document_id':'document-a', 'revision':0}
        for rid in ('old', 'new'): c.handle({**base,'action':'preview','request_id':rid,'recipe':S.neutral()})
        with self.assertRaises(ValueError): c.handle({**base,'action':'commit','request_id':'wrong','preview_id':'old'})
        msg = {**base,'action':'commit','request_id':'apply','preview_id':'new'}
        self.assertEqual(c.handle(msg)['status'], 'applied')
        self.assertEqual(c.handle(msg)['status'], 'applied')
        self.assertEqual(h.history, 1)
        self.assertEqual(c.handle({**base,'action':'status','request_id':'apply'})['status'], 'applied')

    def test_document_switch_and_invalidation(self):
        h = Host(); c = ColourGradingController(h)
        base = {'cmd':'colour_grading','document_id':'document-a','revision':0}
        c.handle({**base,'action':'preview','request_id':'p','recipe':S.neutral()})
        c.invalidate(); h.revision += 1
        with self.assertRaises(ValueError): c.handle({**base,'action':'commit','request_id':'c','preview_id':'p'})
