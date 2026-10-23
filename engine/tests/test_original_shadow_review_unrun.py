"""AUTHORED / UNRUN: isolated original-shadow review and source-owned masks.

No imports or tests were executed while authoring. Full rendering and history
are orchestration doubles, not native, photo-quality or performance acceptance.
The real geometric-state validation is exercised only when these tests are run.
"""
from copy import deepcopy

import numpy as np
import pytest

from test_spill_review_unrun import EngineDouble, digest
from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import id_background_runtime as RUNTIME
from lumaretouch_engine import id_background_state as ID
from lumaretouch_engine import local_mask_state as MASK
from lumaretouch_engine import original_shadow_controller as CONTROL
from lumaretouch_engine import original_shadow_review as REVIEW


def radial(ident, x):
    return {'id': ident, 'name': ident, 'enabled': True, 'operation': 'add',
            'kind': 'radial', 'opacity': 1., 'feather': 0., 'center': [x, .75],
            'axes': [[.1, 0.], [0., .1]]}


class ShadowEngineDouble(EngineDouble):
    def __init__(self):
        super().__init__()
        self._local_masks = MASK.empty()
        self._local_masks['source'] = deepcopy(self.source)
        self._local_masks['recipe']['objects'] = [radial('lit', .15), radial('retained', .75)]
        self.derived = False
        self.original_sha256 = self.source['sha256']

    def _capture_state(self):
        return {**super()._capture_state(), '_local_masks': deepcopy(self._local_masks)}

    def _history_apply(self, before):
        super()._history_apply(before)
        self._local_masks = deepcopy(before['_local_masks'])


@pytest.fixture
def target(monkeypatch):
    engine = ShadowEngineDouble()
    events, renders = [], []

    def identity(owner, row, state, document, revision):
        if document != row['document_id'] or str(revision) != str(owner.revision):
            raise ValueError('Synthetic document identity changed')
        source = {'asset_sha256': owner.source['sha256'],
                  'creative_source': deepcopy(owner.source) if owner.derived else None,
                  'original_sha256': owner.original_sha256}
        return {'document_id': document, 'revision': str(revision),
                'source_proof': source, 'candidate_sha256': digest(state),
                'people_sha256': digest(owner.people)}, {}, {}

    def render(owner, row, state, document, revision):
        renders.append(deepcopy(state))
        proof, _, _ = identity(owner, row, state, document, revision)
        intent = ID.original_shadow_of(state['_id_background'])
        pixels = np.full((8, 12, 3), .4 - intent['enabled'] * .1, np.float32)
        return pixels, {**proof, 'source_size': [12, 8], 'output_size': [12, 8]}

    def verify(source, owner):
        if source != owner.source:
            raise ValueError('Synthetic effective source changed')
        return deepcopy(source)

    monkeypatch.setattr(FULL, 'identity', identity)
    monkeypatch.setattr(FULL, 'render', render)
    monkeypatch.setattr(SOURCE, 'binding', lambda owner: deepcopy(owner.source))
    monkeypatch.setattr(SOURCE, 'verify', verify)
    monkeypatch.setattr(RUNTIME, 'sync', lambda owner, **kwargs: None)
    monkeypatch.setattr(RUNTIME, 'report', lambda owner: {
        'recipe': deepcopy(owner._id_background), 'recipe_revision': str(owner.revision)})
    return engine, CONTROL.controller(engine, events.append), events, renders


def preview_request(engine, request_id='shadow-preview-1'):
    return {'cmd': 'background', 'action': 'id_original_shadow_preview',
            'request_id': request_id, 'document_id': engine._load_id,
            'recipe_document_id': engine._docs[0]['document_id'],
            'recipe_revision': str(engine.revision),
            'parameters': {'enabled': True, 'strength': 75., 'blend': 'normal'},
            'lit_ids': ['lit'], 'retention_ids': ['retained'],
            'samples_reviewed': True, 'uniform_floor_confirmed': True}


def prepare(target, request_id='shadow-preview-1'):
    engine, control, events, _ = target
    request = preview_request(engine, request_id)
    control.handle(request)
    assert events[-1]['success'] is True
    return request, events[-1]['shadow_review']


def apply_request(preview, review, request_id='shadow-apply-1'):
    return {**{key: preview[key] for key in CONTROL.BASE},
            'action': 'id_original_shadow_apply', 'request_id': request_id,
            'token': review['token'], 'reviewed': True,
            'before_sha256': review['before']['sha256'],
            'after_sha256': review['after']['sha256']}


def test_preview_renders_both_complete_candidates_without_live_mutation(target):
    engine, _, _, renders = target
    before = deepcopy((engine._history_capture(), vars(engine.ledger), engine.doc_state()))
    _, review = prepare(target)
    assert len(renders) == 2
    assert (engine._history_capture(), vars(engine.ledger), engine.doc_state()) == before
    assert engine.fences == engine.frames == engine.cancellations == 0
    assert review['before']['sha256'] != review['after']['sha256']
    private = REVIEW.owner(engine).review
    assert 'base64' not in private['before'] and 'base64' not in private['after']
    shadow = ID.original_shadow_of(private['recipe'])
    assert shadow['lit_floor']['mask']['recipe']['objects'][0]['id'] == 'lit'
    assert shadow['retention']['mask']['recipe']['objects'][0]['id'] == 'retained'
    assert all(field['mask']['source'] == engine.source for field in (
        shadow['lit_floor'], shadow['retention']))


@pytest.mark.parametrize('change', [
    {'uniform_floor_confirmed': False}, {'uniform_floor_confirmed': 1},
    {'samples_reviewed': False}, {'samples_reviewed': 1},
    {'lit_ids': []}, {'retention_ids': []}, {'lit_ids': ['missing']},
    {'lit_ids': ['lit', 'lit']}, {'retention_ids': ['lit']},
    {'lit_ids': None, 'retention_ids': None, 'samples_reviewed': False},
])
def test_incomplete_unconfirmed_or_reused_manual_samples_reject_before_render(target, change):
    engine, control, events, renders = target
    control.handle({**preview_request(engine), **change})
    assert events[-1]['success'] is False
    assert renders == [] and engine.fences == engine.frames == 0


@pytest.mark.parametrize('changed', ['source', 'semantic', 'full'])
def test_samples_cannot_borrow_another_source_or_analysis_masks(target, changed):
    engine, control, events, renders = target
    if changed == 'source':
        engine._local_masks['source']['sha256'] = 'b' * 64
    else:
        obj = engine._local_masks['recipe']['objects'][0]
        obj.pop('center'); obj.pop('axes'); obj['kind'] = changed
        if changed == 'semantic': obj['channel'] = 'foreground'
    control.handle(preview_request(engine))
    assert events[-1]['success'] is False and renders == []


@pytest.mark.parametrize('blend', ['normal', 'multiply', 'softlight'])
def test_retained_snapshots_can_be_reviewed_without_fake_reselection(target, blend):
    engine, control, events, _ = target
    request, review = prepare(target)
    control.handle(apply_request(request, review))
    assert events[-1]['success'] is True
    retained = deepcopy(ID.original_shadow_of(engine._id_background))
    request = preview_request(engine, 'parameter-review')
    request.update(lit_ids=None, retention_ids=None, samples_reviewed=False)
    request['parameters']['blend'] = blend
    control.handle(request)
    assert events[-1]['success'] is True
    candidate = ID.original_shadow_of(REVIEW.owner(engine).review['recipe'])
    assert candidate['lit_floor'] == retained['lit_floor']
    assert candidate['retention'] == retained['retention']


def test_returned_source_keeps_effective_asset_and_original_provenance_separate(target):
    engine, _, _, _ = target
    engine.derived = True
    engine.original_sha256 = 'b' * 64
    _, review = prepare(target)
    assert review['source'] == engine.source
    proof = REVIEW.owner(engine).review['proposed']['source_proof']
    assert proof['asset_sha256'] == engine.source['sha256']
    assert proof['original_sha256'] == 'b' * 64
    assert proof['creative_source'] == engine.source


def test_output_crop_need_not_match_source_aspect(target, monkeypatch):
    engine, control, events, _ = target
    old = FULL.render
    def cropped(*args):
        pixels, proof = old(*args)
        return pixels[:6, :6].copy(), {**proof, 'output_size': [6, 6]}
    monkeypatch.setattr(FULL, 'render', cropped)
    control.handle(preview_request(engine))
    review = events[-1]['shadow_review']
    assert review['source']['width'] == 12
    assert review['before']['width'] == review['after']['height'] == 6


@pytest.mark.parametrize('kind', ['rgb8', 'nonfinite', 'wrong_extent', 'wrong_proof'])
def test_preview_rejects_noncanonical_full_render(target, monkeypatch, kind):
    engine, control, events, _ = target
    old = FULL.render
    def malformed(*args):
        pixels, proof = old(*args)
        if kind == 'rgb8': pixels = (pixels * 255).astype(np.uint8)
        elif kind == 'nonfinite': pixels[0, 0, 0] = np.nan
        elif kind == 'wrong_extent': proof['output_size'] = [6, 6]
        else: proof['candidate_sha256'] = '0' * 64
        return pixels, proof
    monkeypatch.setattr(FULL, 'render', malformed)
    control.handle(preview_request(engine))
    assert events[-1]['success'] is False and REVIEW.owner(engine).review is None
    assert engine.fences == engine.frames == 0


def test_both_masks_and_applicability_are_not_client_supplied_payloads(target):
    engine, control, events, _ = target
    control.handle({**preview_request(engine), 'lit_floor': {'reviewed': True}})
    assert events[-1]['success'] is False
    control.handle({**preview_request(engine, 'paint'), 'paint': {'strokes': []}})
    assert events[-1]['success'] is False and engine.fences == engine.frames == 0
