"""AUTHORED / UNRUN: original-shadow review receipts, proof and rollback.

Synthetic orchestration tests only. No runtime, GPU/export, real-history,
photo-quality or performance acceptance is established by this source file.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_original_shadow_review_unrun import target, prepare, preview_request, apply_request
from lumaretouch_engine import original_shadow_controller as CONTROL
from lumaretouch_engine import original_shadow_review as REVIEW
from lumaretouch_engine import id_background_runtime as RUNTIME
from lumaretouch_engine import project_recovery_runtime as RECOVERY


@pytest.mark.parametrize('changed', ['source', 'provenance', 'people', 'upstream', 'masks', 'document', 'revision'])
def test_apply_rejects_stale_complete_target_before_mutation(target, changed):
    engine, control, events, _ = target
    request, review = prepare(target)
    if changed == 'source': engine.source['sha256'] = 'b' * 64
    elif changed == 'provenance': engine.original_sha256 = 'c' * 64
    elif changed == 'people': engine.people['owner'] = 'other-person'
    elif changed == 'upstream': engine.upstream += 1
    elif changed == 'masks': engine._local_masks['recipe']['objects'][0]['opacity'] = .5
    elif changed == 'document': engine._load_id = 'other-document'
    else: engine.revision += 1
    control.handle(apply_request(request, review))
    assert events[-1]['success'] is False
    assert engine.fences == engine.frames == engine.cancellations == 0
    assert engine.ledger.undo == [] and not engine._project_dirty


@pytest.mark.parametrize('field', ['reviewed', 'before_sha256', 'after_sha256', 'token'])
def test_apply_needs_this_exact_pair_acknowledged(target, field):
    engine, control, events, _ = target
    request, review = prepare(target)
    apply = apply_request(request, review)
    apply[field] = False if field == 'reviewed' else '0' * 64
    control.handle(apply)
    assert events[-1]['success'] is False and engine.fences == engine.frames == 0


def test_superseded_review_cannot_be_rearmed_by_old_cached_preview(target):
    engine, control, events, renders = target
    first, old = prepare(target)
    _, current = prepare(target, 'shadow-preview-2')
    assert len([r for _, r in control.cache.values() if 'shadow_review' in r]) == 1
    control.handle(first)
    assert not events[-1]['success'] and events[-1]['replayed']
    assert REVIEW.owner(engine).review['token'] == current['token']
    control.handle(apply_request(first, old))
    assert not events[-1]['success'] and engine.fences == 0 and len(renders) == 4


def test_expired_review_requires_a_new_pair(target, monkeypatch):
    engine, control, events, _ = target
    request, review = prepare(target)
    expires = REVIEW.owner(engine).review['expires']
    monkeypatch.setattr(REVIEW.time, 'monotonic', lambda: expires + 1)
    control.handle(apply_request(request, review))
    assert not events[-1]['success'] and engine.fences == 0


def test_exact_success_receipt_replays_without_second_history_step(target):
    engine, control, events, _ = target
    request, review = prepare(target)
    apply = apply_request(request, review)
    control.handle(apply)
    assert events[-1]['success'] and engine.fences == engine.frames == len(engine.ledger.undo) == 1
    control.handle(apply)
    assert events[-1]['success'] and events[-1]['replayed']
    assert engine.fences == engine.frames == len(engine.ledger.undo) == 1
    control.handle({**apply, 'request_id': 'different-apply'})
    assert not events[-1]['success'] and engine.fences == 1
    control.handle({**apply, 'before_sha256': '0' * 64})
    assert not events[-1]['success'] and engine.fences == 1


@pytest.mark.parametrize('fault', ['raise', 'upstream', 'people'])
def test_failed_apply_restores_frozen_recipe_people_and_history(target, fault):
    engine, control, events, _ = target
    request, review = prepare(target)
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    engine.frame_fault = fault
    control.handle(apply_request(request, review))
    assert not events[-1]['success'] and not events[-1]['outcome_unknown']
    assert (engine._history_capture(), vars(engine.ledger)) == before
    assert not engine._project_dirty and '_library_edit_time_ns' not in engine._docs[0]
    assert engine.fences == 1 and REVIEW.owner(engine).review is None


def test_sync_cannot_install_an_unreviewed_complete_candidate(target, monkeypatch):
    engine, control, events, _ = target
    request, review = prepare(target)
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    changed = []
    def sync(owner, **kwargs):
        if not changed:
            changed.append(True)
            owner.people['owner'] = 'unreviewed-person'
    monkeypatch.setattr(RUNTIME, 'sync', sync)
    control.handle(apply_request(request, review))
    assert not events[-1]['success'] and not events[-1]['outcome_unknown']
    assert (engine._history_capture(), vars(engine.ledger)) == before


def test_history_failure_after_append_restores_undo_redo_dirty_and_edit_time(target, monkeypatch):
    engine, control, events, _ = target
    request, review = prepare(target)
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    record = engine._history_record
    def failing_record(*args, **kwargs):
        record(*args, **kwargs)
        raise ValueError('Synthetic history failure after append')
    monkeypatch.setattr(engine, '_history_record', failing_record)
    control.handle(apply_request(request, review))
    assert not events[-1]['success'] and not events[-1]['outcome_unknown']
    assert (engine._history_capture(), vars(engine.ledger)) == before
    assert not engine._project_dirty and '_library_edit_time_ns' not in engine._docs[0]


@pytest.mark.parametrize('fault', ['restore_raises', 'wrong_people', 'wrong_source', 'rollback_frame'])
def test_unproven_rollback_reports_unknown_and_never_blindly_retries(target, monkeypatch, fault):
    engine, control, events, _ = target
    request, review = prepare(target)
    apply = apply_request(request, review)
    engine.frame_fault = 'raise'
    restore = engine._history_apply
    def incomplete(before):
        if fault == 'restore_raises': raise ValueError('Synthetic restoration failure')
        restore(before)
        if fault == 'wrong_people': engine.people['owner'] = 'unrestored-person'
        elif fault == 'wrong_source': engine.source['sha256'] = 'b' * 64
        elif fault == 'rollback_frame': engine.frame_fault = 'upstream'
    monkeypatch.setattr(engine, '_history_apply', incomplete)
    control.handle(apply)
    assert not events[-1]['success']
    assert events[-1]['outcome_unknown'] and events[-1]['requires_reload']
    assert engine._vram is None
    writes = engine.fences, engine.frames
    control.handle(apply)
    assert events[-1]['outcome_unknown'] and events[-1]['replayed']
    assert (engine.fences, engine.frames) == writes


@pytest.mark.parametrize('action', ['preview', 'apply'])
def test_receipt_byte_budget_refuses_before_render_or_write(target, monkeypatch, action):
    engine, control, events, renders = target
    if action == 'apply':
        request, review = prepare(target)
        request = apply_request(request, review)
    else: request = preview_request(engine)
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    count = len(renders)
    monkeypatch.setattr(CONTROL, 'MAX_RECEIPT_BYTES', 0)
    control.handle(request)
    assert not events[-1]['success'] and not events[-1]['outcome_unknown']
    assert (engine._history_capture(), vars(engine.ledger)) == before
    assert engine.fences == engine.frames == 0 and len(renders) == count


def test_receipt_count_budget_does_not_evict_terminal_identities(target):
    engine, control, events, renders = target
    control.cache.update({f'old-{i}': ('a' * 64, {'success': True}) for i in range(512)})
    before = deepcopy(control.cache)
    control.handle(preview_request(engine))
    assert not events[-1]['success'] and control.cache == before
    assert engine.fences == engine.frames == 0 and renders == []


@pytest.mark.parametrize('failed', [False, True])
def test_read_only_preview_does_not_taint_or_advance_autosave(target, failed):
    engine, _, _, _ = target
    runtime = SimpleNamespace(revision=9, tainted=False, reason=None)
    engine._project_recovery_runtime = runtime
    boundary = {'message': preview_request(engine), 'started': True,
                'returned': not failed, 'failed': failed}
    RECOVERY.finish(engine, boundary, 'Synthetic failure' if failed else None)
    assert vars(runtime) == {'revision': 9, 'tainted': False, 'reason': None}


def test_dismissed_review_is_not_an_open_history_transaction(target):
    engine, _, _, _ = target
    prepare(target)
    runtime = object.__new__(RECOVERY.Runtime)
    runtime.engine, runtime.tainted, runtime.reason = engine, False, None
    runtime.guard()
    assert REVIEW.owner(engine).review is not None
