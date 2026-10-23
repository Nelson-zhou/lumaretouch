"""AUTHORED / UNRUN: spill review ownership, receipts and transaction fences.

Nothing in this file was imported or executed while authoring. The complete
renderer, live sync and history seams below are synthetic orchestration doubles.
These fixtures do not establish native correctness, real engine history replay,
source-resolution performance, visual acceptance or GPU/export parity.
"""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import id_background_runtime as RUNTIME
from lumaretouch_engine import id_background_state as ID
from lumaretouch_engine import id_background_support as SUPPORT
from lumaretouch_engine import local_mask_state as MASK
from lumaretouch_engine import project_recovery_runtime as RECOVERY
from lumaretouch_engine import spill_removal_controller as CONTROL
from lumaretouch_engine import spill_removal_review as REVIEW


def digest(value):
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def id_recipe(source):
    mask = MASK.empty()
    mask['source'] = deepcopy(source)
    mask['recipe']['objects'] = [{
        'id': 'subject', 'name': 'Reviewed subject', 'enabled': True,
        'operation': 'add', 'kind': 'radial', 'opacity': 1., 'feather': 0.,
        'center': [.5, .5], 'axes': [[.4, 0.], [0., .4]],
    }]
    value = ID.empty()
    value.update(enabled=True, source=deepcopy(source))
    value['support']['subject'] = SUPPORT.check_binding({
        'version': 1, 'category': 'subject', 'reviewed': True,
        'mask': mask, 'recipe_sha256': SUPPORT.digest(mask),
    }, 'subject')
    return value


class EngineDouble:
    def __init__(self):
        self._load_id = 'loaded-photo'
        self._doc_index = 0
        self._docs = [{'path': 'synthetic-no-file', 'document_id': 'recipe-photo'}]
        self.revision = 4
        self.source = {'sha256': 'a' * 64, 'width': 12, 'height': 8}
        self.people = {'owner': 'person-a'}
        self._id_background = id_recipe(self.source)
        self.upstream = 0
        self._project_dirty = False
        self._vram = object()
        self.ledger = SimpleNamespace(undo=[], redo=[{'retained': 'redo'}],
                                      group='earlier-gesture', group_ns=17)
        self.fences = self.frames = self.cancellations = 0
        self.frame_fault = None

    def _document_versions(self):
        return SimpleNamespace(version=lambda row: SimpleNamespace(
            document_id=row['document_id'], revision=self.revision))

    def _capture_state(self):
        return {'_id_background': deepcopy(self._id_background), '_upstream': self.upstream}

    def _history_capture(self):
        return {**self._capture_state(), '_people_snapshot': deepcopy(self.people)}

    def _history_apply(self, before):
        self._id_background = deepcopy(before['_id_background'])
        self.upstream = before['_upstream']
        self.people = deepcopy(before['_people_snapshot'])

    def _history_controller(self):
        return self.ledger

    def _history_record(self, group, before, *, coalesce):
        assert coalesce is False
        self.ledger.undo.append(deepcopy(before))
        self.ledger.redo.clear()
        self.ledger.group, self.ledger.group_ns = group, 19
        self._project_dirty = True
        self._docs[0]['_library_edit_time_ns'] = 23

    def _history_report(self):
        return {'undo_steps': len(self.ledger.undo), 'redo_steps': len(self.ledger.redo)}

    def _guard_editable(self, reason):
        return None

    def _fence_current_document(self):
        self.fences += 1
        self.revision += 1

    def _cancel_snapshot(self, reason):
        self.cancellations += 1

    def _write_current_frame(self, mode):
        self.frames += 1
        fault, self.frame_fault = self.frame_fault, None
        if fault == 'raise':
            raise ValueError('Synthetic frame failure')
        if fault == 'upstream':
            self.upstream += 1
        if fault == 'people':
            self.people['owner'] = 'person-b'
        return {'event': 'frame', 'mode': mode}

    def doc_state(self):
        return {'revision': self.revision, 'dirty': self._project_dirty}


@pytest.fixture
def target(monkeypatch):
    engine = EngineDouble()
    events, renders = [], []

    def identity(owner, row, state, document, revision):
        if document != row['document_id'] or str(revision) != str(owner.revision):
            raise ValueError('Synthetic document identity changed')
        return {'document_id': document, 'revision': str(revision),
                'source_proof': deepcopy(owner.source),
                'candidate_sha256': digest(state),
                'people_sha256': digest(owner.people)}, {}, {}

    def render(owner, row, state, document, revision):
        renders.append(deepcopy(state))
        proof, _, _ = identity(owner, row, state, document, revision)
        spill = ID.spill_of(state['_id_background'])
        pixels = np.full((8, 12, 3), .2 + spill['enabled'] * .1, np.float32)
        return pixels, {**proof, 'source_size': [12, 8], 'output_size': [12, 8]}

    def verify(source, owner):
        if source != owner.source:
            raise ValueError('Synthetic source changed')
        return deepcopy(source)

    monkeypatch.setattr(FULL, 'identity', identity)
    monkeypatch.setattr(FULL, 'render', render)
    monkeypatch.setattr(SOURCE, 'binding', lambda owner: deepcopy(owner.source))
    monkeypatch.setattr(SOURCE, 'verify', verify)
    monkeypatch.setattr(RUNTIME, 'sync', lambda owner, **kwargs: None)
    monkeypatch.setattr(RUNTIME, 'report', lambda owner: {
        'recipe': deepcopy(owner._id_background), 'recipe_revision': str(owner.revision)})
    control = CONTROL.controller(engine, events.append)
    return engine, control, events, renders


def preview_request(engine, request_id='preview-1'):
    return {'cmd': 'background', 'action': 'id_spill_preview',
            'request_id': request_id, 'document_id': engine._load_id,
            'recipe_document_id': engine._docs[0]['document_id'],
            'recipe_revision': str(engine.revision),
            'parameters': {'enabled': True, 'strength': 40.},
            'coverage_ids': None, 'coverage_reviewed': False}


def prepare(target, request_id='preview-1'):
    engine, control, events, _ = target
    request = preview_request(engine, request_id)
    control.handle(request)
    assert events[-1]['success'] is True
    return request, events[-1]['review']


def apply_request(preview, review, request_id='apply-1'):
    return {**{key: preview[key] for key in CONTROL.BASE},
            'action': 'id_spill_apply', 'request_id': request_id,
            'token': review['token'], 'reviewed': True,
            'before_sha256': review['before']['sha256'],
            'after_sha256': review['after']['sha256']}


def test_preview_is_nonmutating_and_private_review_retains_no_display_pixels(target):
    engine, _, _, renders = target
    before = deepcopy((engine._history_capture(), vars(engine.ledger), engine.doc_state()))
    _, review = prepare(target)
    assert len(renders) == 2
    assert (engine._history_capture(), vars(engine.ledger), engine.doc_state()) == before
    assert engine.fences == engine.frames == engine.cancellations == 0
    assert review['before']['sha256'] != review['after']['sha256']
    private = REVIEW.owner(engine).review
    assert 'base64' not in private['before'] and 'base64' not in private['after']
    assert 'base64' in review['before'] and 'base64' in review['after']


def test_superseded_preview_receipts_are_compact_and_cannot_rearm_old_token(target):
    engine, control, events, renders = target
    first, old_review = prepare(target)
    _, current = prepare(target, 'preview-2')
    cached_reviews = [result.get('review') for _, result in control.cache.values()
                      if result.get('review') is not None]
    assert len(cached_reviews) == 1
    control.handle(first)
    assert events[-1]['success'] is False and events[-1]['replayed'] is True
    assert REVIEW.owner(engine).review['token'] == current['token']
    control.handle(apply_request(first, old_review))
    assert events[-1]['success'] is False
    assert engine.fences == 0 and len(renders) == 4


@pytest.mark.parametrize('changed', ['source', 'people', 'upstream', 'document', 'revision'])
def test_apply_rejects_stale_complete_ownership_before_first_mutation(target, changed):
    engine, control, events, _ = target
    request, review = prepare(target)
    if changed == 'source':
        engine.source['sha256'] = 'b' * 64
    elif changed == 'people':
        engine.people['owner'] = 'another-person'
    elif changed == 'upstream':
        engine.upstream += 1
    elif changed == 'document':
        engine._load_id = 'another-loaded-photo'
    else:
        engine.revision += 1
    control.handle(apply_request(request, review))
    assert events[-1]['success'] is False
    assert engine.fences == engine.frames == 0
    assert engine.ledger.undo == [] and engine._project_dirty is False


def test_exact_apply_receipt_replays_without_second_write_or_undo_step(target):
    engine, control, events, _ = target
    request, review = prepare(target)
    apply = apply_request(request, review)
    control.handle(apply)
    assert events[-1]['success'] is True
    assert engine.fences == engine.frames == len(engine.ledger.undo) == 1
    control.handle(apply)
    assert events[-1]['success'] is True and events[-1]['replayed'] is True
    assert engine.fences == engine.frames == len(engine.ledger.undo) == 1
    control.handle({**apply, 'request_id': 'apply-another'})
    assert events[-1]['success'] is False
    assert engine.fences == engine.frames == len(engine.ledger.undo) == 1


def test_frame_failure_restores_recipe_history_dirty_and_edit_time(target):
    engine, control, events, _ = target
    request, review = prepare(target)
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    engine.frame_fault = 'raise'
    control.handle(apply_request(request, review))
    assert events[-1]['success'] is False
    assert events[-1]['outcome_unknown'] is False
    assert (engine._history_capture(), vars(engine.ledger)) == before
    assert engine._project_dirty is False
    assert '_library_edit_time_ns' not in engine._docs[0]
    assert engine.fences == 1  # Mutation fences intentionally never rewind.
    assert REVIEW.owner(engine).review is None  # Failed commit cannot reuse token.


def test_failed_rollback_is_retained_unknown_and_never_reexecuted(target, monkeypatch):
    engine, control, events, _ = target
    request, review = prepare(target)
    apply = apply_request(request, review)
    engine.frame_fault = 'raise'

    def failed_restore(before):
        raise ValueError('Synthetic rollback failure')

    monkeypatch.setattr(engine, '_history_apply', failed_restore)
    control.handle(apply)
    assert events[-1]['success'] is False
    assert events[-1]['outcome_unknown'] is True and events[-1]['requires_reload'] is True
    assert engine._vram is None
    writes = engine.fences, engine.frames
    control.handle(apply)
    assert events[-1]['outcome_unknown'] is True and events[-1]['replayed'] is True
    assert (engine.fences, engine.frames) == writes


@pytest.mark.parametrize('action', ['preview', 'apply'])
def test_receipt_byte_admission_rejects_before_any_write(target, monkeypatch, action):
    engine, control, events, renders = target
    if action == 'apply':
        request, review = prepare(target)
        request = apply_request(request, review)
    else:
        request = preview_request(engine)
    count = len(renders)
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    monkeypatch.setattr(CONTROL, 'MAX_RECEIPT_BYTES', 0)
    control.handle(request)
    assert events[-1]['success'] is False and events[-1]['outcome_unknown'] is False
    assert engine.fences == engine.frames == engine.cancellations == 0
    assert len(renders) == count
    assert (engine._history_capture(), vars(engine.ledger)) == before


def test_receipt_count_admission_cannot_evict_a_terminal_apply_identity(target):
    engine, control, events, renders = target
    control.cache.update({f'old-{i}': ('a' * 64, {'success': True}) for i in range(512)})
    before = deepcopy(control.cache)
    control.handle(preview_request(engine))
    assert events[-1]['success'] is False
    assert control.cache == before
    assert engine.fences == engine.frames == 0 and renders == []


@pytest.mark.parametrize('changed', ['upstream', 'people'])
def test_frame_sync_cannot_commit_an_unreviewed_complete_target(target, changed):
    """The real frame writer runs live people/sync owners after initial proof."""
    engine, control, events, _ = target
    request, review = prepare(target)
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    engine.frame_fault = changed
    control.handle(apply_request(request, review))
    assert events[-1]['success'] is False
    assert events[-1]['outcome_unknown'] is False
    assert (engine._history_capture(), vars(engine.ledger)) == before


def test_dismissed_read_only_review_does_not_block_project_recovery(target):
    engine, _, _, _ = target
    prepare(target)
    recovery = object.__new__(RECOVERY.Runtime)  # No store/filesystem setup.
    recovery.engine, recovery.tainted, recovery.reason = engine, False, None
    recovery.guard()
    assert REVIEW.owner(engine).review is not None


@pytest.mark.parametrize('failed', [False, True])
def test_preview_success_or_failure_cannot_taint_or_advance_recovery(target, failed):
    engine, _, _, _ = target
    runtime = SimpleNamespace(revision=9, tainted=False, reason=None)
    engine._project_recovery_runtime = runtime
    boundary = {'message': preview_request(engine), 'started': True,
                'returned': not failed, 'failed': failed}
    RECOVERY.finish(engine, boundary, 'Synthetic preview failure' if failed else None)
    assert vars(runtime) == {'revision': 9, 'tainted': False, 'reason': None}


def test_single_receipt_budget_refuses_before_mutation(target, monkeypatch):
    engine, control, events, _ = target
    request, review = prepare(target)
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    monkeypatch.setattr(CONTROL, 'MAX_RESULT_BYTES', 1)
    control.handle(apply_request(request, review))
    assert events[-1]['success'] is False and not events[-1]['outcome_unknown']
    assert engine.fences == engine.frames == engine.cancellations == 0
    assert (engine._history_capture(), vars(engine.ledger)) == before
