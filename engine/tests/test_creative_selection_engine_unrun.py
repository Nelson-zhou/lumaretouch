# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: original selection engine contract fixtures.

Lifecycle mocks below are not image/numerical acceptance. The separate native
class requires packaged real native libraries; missing libraries are a skip,
not a successful acceptance result. No fixture in this file has been executed.
"""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from lumaretouch_engine import creative_document_state as S
from lumaretouch_engine.creative_document_assets import AssetStore, make_asset
from lumaretouch_engine.creative_document_host import CreativeHost, fields, rotate, token
from lumaretouch_engine.creative_document_project import capture_into, restore_from, encode_record, validate_records
from lumaretouch_engine import creative_selection_recipe as R
from lumaretouch_engine import creative_selection_stage as ST
from lumaretouch_engine import creative_selection_native as N
from lumaretouch_engine import creative_selection_host as H
from lumaretouch_engine.creative_selection_jobs import Jobs


def recipe(width=8, height=6, operations=None, feather=0):
    return {'version': 1, 'coordinate_space': R.SPACE, 'canvas': {'width': width, 'height': height},
            'feather_radius': feather, 'operations': operations or [
                {'kind': 'rectangle', 'combine': 'new', 'x0': 1, 'y0': 1, 'x1': width-1, 'y1': height-1}]}


def scene(width=8, height=6, mask=None):
    assets = AssetStore()
    rgba = np.ones((height, width, 4), dtype='<f4')
    rgba[:, :, 0] = np.linspace(.1, .9, width)
    source = make_asset('rgba', width, height, rgba.tobytes(), original=b'original-file-provenance-fixture')
    identity = assets.intern(source)
    document = S.create('photo-owner', identity, assets)
    layer = document['layers'][0]
    if mask is not None:
        layer['mask_id'] = assets.intern(make_asset('mask', width, height, np.full((height, width), mask, dtype='<f4').tobytes()))
    return assets, document, layer, source


def engine_scene(mask=None):
    assets, document, layer, source = scene(mask=mask)
    e = SimpleNamespace(_creative_document=document, _creative_asset_records=assets.records(S.references(document)),
                        _creative_base=None, _load_id='load', _creative_owner_nonce='owner',
                        _docs=[{'document_id': 'photo-owner'}], _doc_index=0,
                        _undo=[], _redo=[], _project_dirty=False)
    versions = SimpleNamespace(workspace='workspace')
    e._document_versions = lambda: versions
    e._guard_editable = lambda _: None
    e._history_capture = lambda: fields(e)
    e._history_record = lambda label, before, coalesce: e._undo.append({'label': label, 'before': before})
    e._remember_current = lambda: None
    e._fence_current_document = lambda: rotate(e)
    e._history_report = lambda: {'can_undo': bool(e._undo), 'can_redo': bool(e._redo)}
    e.doc_state = lambda: {'fixture': 'host lifecycle only'}
    emitted = []
    e._creative_host = CreativeHost(e, emitted.append)
    e._creative_host.sync()
    owner = H.Service(e, emitted.append)
    e._creative_selection_service = owner
    owner._budget = lambda: 512_000_000
    return e, owner, emitted, layer, source


def context_request(e, layer, rid='context'):
    d = e._creative_document
    return {'cmd': H.COMMAND, 'action': 'context', 'request_id': rid, 'source_uid': d['source_uid'],
            'document_id': d['document_id'], 'ownership_token': token(e),
            'expected_revision': d['revision'], 'layer_id': layer['id']}


def install_review(owner, e, layer, *, policy='create'):
    """Lifecycle-only fixture injects a real immutable mask, not a claimed render."""
    host = e._creative_host
    before = deepcopy(e._creative_document)
    proof = owner._proof(host, before, layer)
    owner.context = {'proof': proof, 'document': before, 'request_id': 'context'}
    record = make_asset('mask', 8, 6, np.full((6, 8), .25, dtype='<f4').tobytes())
    after = deepcopy(before)
    after['layers'][0]['mask_id'] = record['id']; after['revision'] += 1
    review = {'proof': proof, 'preview_token': 'preview-token', 'ack': 'unit-fixture-only-not-a-visual-proof',
              'mask_policy': policy, 'output_mask_sha256': ST.content_hash(record['content'])}
    owner.candidate = {'request_id': 'preview', 'before': before, 'after': after, 'record': record, 'review': review}
    return {'cmd': H.COMMAND, 'action': 'apply', 'request_id': 'apply', 'source_uid': 'photo-owner',
            'proof': deepcopy(proof), 'preview_token': review['preview_token'], 'ack': review['ack'], 'reviewed': True}


class RecipeContracts(unittest.TestCase):
    def test_empty_boolean_nonfinite_foreign_and_implicit_policy_rejected(self):
        value = recipe()
        for mutate in (lambda v: v.update(operations=[]), lambda v: v.update(feather_radius=True),
                       lambda v: v['canvas'].update(width=4),
                       lambda v: v['operations'][0].update(x0=float('nan')),
                       lambda v: v.update(unrecognized=True)):
            bad = deepcopy(value); mutate(bad)
            with self.assertRaises(ValueError): R.validate(bad, value['canvas'])
        for policy, old in ((None, 'old-mask'), ('create', 'old-mask'), ('replace', None)):
            with self.assertRaises(ValueError): R.mask_policy(policy, old)

    def test_stable_owned_vector_recipe_and_all_explicit_mask_policies(self):
        value = recipe()
        accepted = R.validate(value, value['canvas'])
        accepted['operations'][0]['x0'] = 2
        self.assertEqual(value['operations'][0]['x0'], 1)
        self.assertEqual(R.sha(value), R.sha(dict(reversed(list(value.items())))))
        for policy in ('replace', 'union', 'intersect', 'subtract'):
            self.assertEqual(R.mask_policy(policy, 'old-mask'), policy)

    def test_abi_unused_path_offsets_zero_after_brush(self):
        value = recipe(operations=[{'kind': 'brush', 'combine': 'add', 'points': [[2, 2]],
                                   'diameter': 1, 'hardness': 1, 'opacity': .5},
                                  {'kind': 'rectangle', 'combine': 'intersect', 'x0': 1, 'y0': 1, 'x1': 6, 'y1': 4},
                                  {'kind': 'invert'}])
        bridge = N.Evaluator(value)
        self.assertEqual(bridge.operations[1].point_offset, 0)
        self.assertEqual(bridge.operations[2].point_offset, 0)
        self.assertEqual(bridge.operations[2].combine, 0)


class ProjectionContracts(unittest.TestCase):
    def test_identity_and_center_retaining_horizontal_flip(self):
        canvas = np.arange(48, dtype=np.float32).reshape(6, 8) / 48
        np.testing.assert_array_equal(ST.project_canvas_mask(canvas, S.TRANSFORM, 8, 6), canvas)
        flipped = {**S.TRANSFORM, 'flip_x': True}
        np.testing.assert_array_equal(ST.project_canvas_mask(canvas, flipped, 8, 6), canvas[:, ::-1])

    def test_translation_rotation_scale_and_exterior_are_forward_source_samples(self):
        canvas = np.tile(np.arange(8, dtype=np.float32)[None, :] / 8, (8, 1))
        transform = {**S.TRANSFORM, 'x': 1., 'y': 1., 'rotation': 90., 'scale_x': 2., 'scale_y': 2.}
        projected = ST.project_canvas_mask(canvas, transform, 2, 2)
        affine = S.affine(transform, 2, 2)
        for y in range(2):
            for x in range(2):
                cx = affine[0]*(x+.5) + affine[1]*(y+.5) + affine[2]
                self.assertAlmostEqual(float(projected[y, x]), (cx-.5)/8)
        outside = ST.project_canvas_mask(np.ones((6, 8), dtype=np.float32), {**S.TRANSFORM, 'x': 100.}, 8, 6)
        self.assertFalse(outside.any())

    def test_cancellation_and_extreme_panorama_display_edge(self):
        with self.assertRaises(InterruptedError):
            ST.project_canvas_mask(np.ones((6, 8), dtype=np.float32), S.TRANSFORM, 8, 6, cancelled=lambda: True)
        self.assertEqual(ST.display_size(131072, 1), (4096, 1))


class CancellationContracts(unittest.TestCase):
    def test_early_cancel_and_transport_key_do_not_lose_original_identity(self):
        jobs = Jobs()
        request = {'cmd': H.COMMAND, 'action': 'context', 'request_id': 'read', 'source_uid': 'photo'}
        self.assertTrue(jobs.request_cancel('photo', 'read'))
        self.assertFalse(jobs.ingress(json.dumps({**request, '_host_request_id': 'native-wrapper'})))
        with self.assertRaises(InterruptedError): jobs.run(request, lambda _: 'never')
        self.assertNotIn(('photo', 'read'), jobs.events)
        self.assertIn(('photo', 'read'), jobs.finished)

    def test_source_bound_cancel_does_not_stop_another_photo_or_apply(self):
        jobs = Jobs()
        request = {'cmd': H.COMMAND, 'action': 'preview', 'request_id': 'read', 'source_uid': 'photo'}
        event = jobs.register(request)
        jobs.request_cancel('other', 'read')
        self.assertFalse(event.is_set())
        jobs.ingress(json.dumps({'cmd': H.COMMAND, 'action': 'apply', 'request_id': 'write', 'source_uid': 'photo'}))
        self.assertNotIn(('photo', 'write'), jobs.events)


class HostLifecycleContracts(unittest.TestCase):
    def setUp(self):
        self.cap = patch.object(H, 'capability', return_value={'available': True, 'abi': 1, 'reason': None, 'manual_only': True})
        self.cap.start()
        self.addCleanup(self.cap.stop)

    def test_missing_native_fails_without_graph_asset_or_history_change(self):
        e, owner, events, layer, _ = engine_scene()
        before = fields(e)
        with patch.object(H, 'capability', return_value={'available': False, 'reason': 'missing-native'}):
            owner.handle(context_request(e, layer))
        self.assertEqual(events[-1]['status'], 'rejected')
        self.assertEqual(fields(e), before); self.assertEqual(e._undo, [])

    def test_ancestor_lock_and_selected_group_are_not_bypassed(self):
        assets, doc, layer, _ = scene()
        group = S._layer('group', 'locked ancestor')
        group['locked'] = True; layer['parent_id'] = group['id']; doc['layers'].insert(0, group)
        S.validate(doc, assets)
        with self.assertRaisesRegex(ValueError, 'ancestor'): H._layer(doc, layer['id'])
        doc['selected_id'] = group['id']
        with self.assertRaisesRegex(ValueError, 'leaf'): H._layer(doc, group['id'])

    def test_exact_apply_one_history_original_bytes_and_persistence_codec(self):
        e, owner, events, layer, source = engine_scene()
        request = install_review(owner, e, layer)
        with patch.object(e._creative_host, 'render_preview', side_effect=ValueError('display unavailable after commit')):
            owner.handle(request)
            owner.handle(deepcopy(request))
        self.assertEqual(len(e._undo), 1)
        self.assertEqual(events[-1]['status'], 'applied')
        self.assertTrue(events[-1]['success']); self.assertFalse(events[-1]['outcome_unknown'])
        self.assertIn('preview_error', events[-1])
        self.assertEqual(e._undo[0]['label'], 'creative:selection_mask')
        self.assertEqual(e._creative_asset_records[source['id']], source)
        snapshot = capture_into({}, e._creative_document, e._creative_host.assets)
        restored, restored_assets = restore_from(snapshot)
        self.assertEqual(restored, e._creative_document)
        self.assertEqual(restored_assets.get(events[-1]['mask_id'], 'mask')['id'], events[-1]['mask_id'])
        blobs = {}
        encoded = deepcopy(snapshot)
        encoded['_creative_asset_records'] = {key: encode_record(row, blobs) for key, row in snapshot['_creative_asset_records'].items()}
        checked = validate_records(encoded, assets=blobs)
        self.assertEqual(checked.get(events[-1]['mask_id'], 'mask')['content'], restored_assets.get(events[-1]['mask_id'])['content'])

    def test_stale_transform_ack_and_mask_policy_reject_before_history(self):
        for mutation in ('transform', 'ack', 'mask_policy'):
            e, owner, events, layer, _ = engine_scene(mask=.5 if mutation == 'mask_policy' else None)
            request = install_review(owner, e, layer)
            if mutation == 'transform': e._creative_document['layers'][0]['transform']['x'] = 1
            elif mutation == 'ack': request['ack'] = 'foreign'
            owner.handle(request)
            self.assertEqual(events[-1]['status'], 'rejected'); self.assertEqual(e._undo, [])

    def test_uncertain_commit_is_retained_and_never_retried_or_cancelled(self):
        e, owner, events, layer, _ = engine_scene()
        request = install_review(owner, e, layer)
        def failure(*_): raise RuntimeError('uncertain host adapter')
        e._creative_host.controller.ports = replace(e._creative_host.controller.ports, commit_document=failure)
        owner.handle(request)
        self.assertEqual(events[-1]['status'], 'unknown')
        owner.handle({'cmd': H.COMMAND, 'action': 'cancel', 'request_id': 'cancel', 'source_uid': 'photo-owner', 'target_request_id': 'apply'})
        self.assertEqual(events[-1]['original_result']['status'], 'unknown')
        with self.assertRaises(ValueError): H.guard_other(e, 'history', {'action': 'undo'})
        H.guard_other(e, 'project', {'action': 'open'})
        e._document_versions().workspace = 'reopened-authoritative-workspace'
        H.guard_other(e, 'history', {'action': 'undo'})
        self.assertIsNone(owner.uncertain)

    def test_conflicting_request_id_does_not_replace_original_receipt(self):
        e, owner, events, _, _ = engine_scene()
        original = {'cmd': H.COMMAND, 'action': 'status', 'request_id': 'query', 'source_uid': 'photo-owner', 'target_request_id': 'a'}
        owner.handle(original)
        owner.handle({**original, 'target_request_id': 'b'})
        self.assertEqual(events[-1]['status'], 'rejected')
        self.assertEqual(owner.receipts[('photo-owner', 'query')]['request'], original)

    def test_pending_cancel_settles_only_after_original_actual_unwind(self):
        e, owner, events, layer, _ = engine_scene()
        original = context_request(e, layer, 'queued-read')
        cancellation = {'cmd': H.COMMAND, 'action': 'cancel', 'request_id': 'cancel-read',
                        'source_uid': 'photo-owner', 'target_request_id': 'queued-read'}
        owner.handle(cancellation)
        self.assertEqual(events[-1]['status'], 'pending')
        owner.handle(original)
        self.assertEqual(events[-1]['request_id'], 'cancel-read')
        self.assertEqual(events[-1]['status'], 'cancelled')
        self.assertEqual(owner.receipts[('photo-owner', 'queued-read')]['event']['status'], 'cancelled')
        self.assertEqual(e._undo, [])

    def test_context_without_mask_has_null_descriptor_and_no_canonical_write(self):
        e, owner, events, layer, _ = engine_scene()
        before = fields(e)
        with patch.object(ST, 'composite_image', return_value={'fixture': 'not image acceptance'}):
            owner.handle(context_request(e, layer))
        self.assertEqual(events[-1]['status'], 'ready')
        self.assertIsNone(events[-1]['context']['existing_mask_image'])
        self.assertEqual(fields(e), before)
        self.assertEqual(e._undo, [])


class RealNativeAcceptanceUnrun(unittest.TestCase):
    def setUp(self):
        cap = N.capability()
        if not cap['available']: self.skipTest('Native acceptance UNRUN: ' + cap['reason'])

    def test_tiled_full_canvas_matches_independent_whole_output_and_edges(self):
        value = recipe(513, 259, operations=[{'kind': 'rectangle', 'combine': 'new', 'x0': 0, 'y0': 0, 'x1': 513, 'y1': 259}], feather=5)
        evaluator = N.Evaluator(value)
        a = np.empty((259, 513), dtype=np.float32)
        for y in range(0, 259, 256):
            for x in range(0, 513, 256):
                tile = evaluator.tile(x, y, min(256, 513-x), min(256, 259-y))
                a[y:y+tile.shape[0], x:x+tile.shape[1]] = tile
        b = np.empty_like(a)
        for y in range(0, 259, 127):
            for x in range(0, 513, 127):
                tile = evaluator.tile(x, y, min(127, 513-x), min(127, 259-y))
                b[y:y+tile.shape[0], x:x+tile.shape[1]] = tile
        np.testing.assert_array_equal(a, b)
        self.assertGreater(float(a[0, 0]), 0)
        self.assertLess(float(a[0, 0]), 1)
        self.assertEqual(float(a[10, 10]), 1)

    def test_existing_mask_policies_and_fullsource_dimensions(self):
        assets, document, layer, source = scene(mask=.5)
        original = deepcopy(document)
        value = recipe(operations=[{'kind': 'invert'}])
        for policy, expected in (('replace', 1), ('union', 1), ('intersect', .5), ('subtract', 0)):
            record, after, _ = ST.candidate(document, layer, assets, value, policy, max_bytes=512_000_000)
            np.testing.assert_array_equal(np.frombuffer(record['content'], dtype='<f4'), expected)
            self.assertEqual((record['width'], record['height']), (8, 6))
            self.assertEqual(after['source_asset'], source['id'])
        self.assertEqual(document, original)

    def test_real_before_after_composite_and_coverage_review_no_intern(self):
        assets, document, layer, source = scene()
        prior = assets.records(S.references(document))
        record, after, images = ST.prepare(document, layer, assets, recipe(), 'create', max_bytes=512_000_000)
        self.assertNotEqual(images['before_composite']['sha256'], images['after_composite']['sha256'])
        self.assertNotEqual(images['before_mask']['sha256'], images['after_mask']['sha256'])
        with self.assertRaises(ValueError): assets.get(record['id'])
        self.assertEqual(assets.records(S.references(document)), prior)
        self.assertEqual(after['source_asset'], source['id'])

    def test_budget_cancel_and_no_preview_to_final_upsampling(self):
        assets, document, layer, _ = scene()
        with self.assertRaisesRegex(ValueError, 'memory budget'):
            ST.candidate(document, layer, assets, recipe(), 'create', max_bytes=1)
        with self.assertRaises(InterruptedError):
            ST.candidate(document, layer, assets, recipe(), 'create', max_bytes=512_000_000, cancelled=lambda: True)
