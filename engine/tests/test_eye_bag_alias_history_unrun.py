# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN narrow ridge history, exact replay and persistence.

Only synthetic graph/cache boundaries are described. Nothing here was imported,
collected or executed while authoring. Actual image quality and runtime UNRUN.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_eye_bag_alias_review_unrun import host as alias_host, reviewed, entry, REAL_DEPENDENCIES
from lumaretouch_engine import eye_bag_alias_history as H, people_batch_ledger as L
from lumaretouch_engine import people_history_persistence as P, people_state as S
from lumaretouch_engine import eye_bag_preserve_state as E, eye_bag_preserve_host as R
from lumaretouch_engine import virtual_copy_people as V
from lumaretouch_engine.people_graph_patch import between


@pytest.fixture
def history(alias_host):
    h = alias_host; review = reviewed(h); pending = entry(h, review)
    h.batch.documents.remember_current()
    plans = {'project': {'row': h.row, 'before': h.state, 'candidate': pending['candidate'],
                         'reviewed_face_refs': [h.target['face_ref']]}}
    targets = deepcopy(pending['targets'])
    marker = H.prepare(h.engine, review, plans, targets)
    record = {'ops': [L.OP], 'people_changes': [], 'people_scoped_changes': [
        {'scope': 'project', 'document_id': h.row['document_id'], 'changes': between(h.state, pending['candidate'])}],
        'targets': targets, 'policy': 'protected_scoped_graph', H.KEY: marker,
        'at_ns': 1, 'undone': False, 'request_id': 'alias-history'}
    h.review = review; h.plans = plans; h.record = record; h.candidate = pending['candidate']
    return h


def undo_plans(h):
    return {'project': {'row': h.row, 'before': h.candidate, 'candidate': h.state,
                         'reviewed_face_refs': [h.target['face_ref']]}}


def test_marker_pins_both_support_contexts_and_every_own_input(history):
    h = history; marker = H.check(h.record)
    assert marker['document_ids'] == ['doc-alias', 'doc-eye']
    assert marker['before_face']['local_assets'].get(E.KIND) is None
    assert marker['after_face']['local_assets'][E.KIND]['content_sha256'] == h.review['support_sha256']
    assert marker['before_graph_sha256'] != marker['after_graph_sha256']
    for dependency in marker['dependencies']:
        assert dependency['before']['context_sha256'] != dependency['after']['context_sha256']
        assert dependency['before']['state_sha256'] == dependency['after']['state_sha256']
    assert marker['dependencies'][0]['before']['state_sha256'] != marker['dependencies'][1]['before']['state_sha256']


@pytest.mark.parametrize('fault', ('version', 'extra-marker', 'private-owner', 'members', 'duplicate', 'face-owner',
    'observations', 'other-support', 'descriptor', 'extra-collection', 'foreign-face', 'foreign-leaf',
    'legacy-without-approval', 'legacy-nonzero', 'unset', 'no-face-patch', 'empty', 'cohort-marker',
    'same-graph', 'input-changed', 'missing-dependency', 'source-provenance'))
def test_narrow_history_cannot_widen_ridge_authority(history, fault):
    h = history; record = deepcopy(h.record); marker = record[H.KEY]
    changes = record['people_scoped_changes'][0]['changes']; face = marker['after_face']
    scalar = next(change for change in changes if change['collection'] == 'overrides')
    face_change = next(change for change in changes if change['collection'] == 'faces')
    if fault == 'version': marker['version'] = True
    elif fault == 'extra-marker': marker['implicit'] = True
    elif fault == 'private-owner': marker['people_scope'] = 'doc-eye'
    elif fault == 'members': marker['document_ids'].pop()
    elif fault == 'duplicate': marker['document_ids'][1] = marker['document_ids'][0]
    elif fault == 'face-owner': marker['face_ref']['face_instance_id'] = 'another-face'
    elif fault == 'observations': face['labels']['changed'] = True; face_change['after'] = deepcopy(face)
    elif fault == 'other-support': face['local_assets']['unreviewed'] = deepcopy(face['local_assets'][E.KIND]); face_change['after'] = deepcopy(face)
    elif fault == 'descriptor': face['local_assets'][E.KIND]['content_sha256'] = '0' * 64; face_change['after'] = deepcopy(face)
    elif fault == 'extra-collection': scalar['collection'] = 'persons'
    elif fault == 'foreign-face': scalar['key'][1] = 'another-face'
    elif fault == 'foreign-leaf': scalar['key'][2] = 'lnx.nose_shape.v1'; scalar['after']['operation_id'] = 'lnx.nose_shape.v1'
    elif fault in ('legacy-without-approval', 'legacy-nonzero'):
        scalar['key'][2:] = ['lnx.enhance.v1', '/eye_bags']; scalar['after'].update(operation_id='lnx.enhance.v1', parameter_path='/eye_bags', value=.5 if fault == 'legacy-nonzero' else 0.)
        marker['replace_legacy'] = fault == 'legacy-nonzero'
    elif fault == 'unset': scalar['after'] = None
    elif fault == 'no-face-patch': changes.remove(face_change)
    elif fault == 'empty': changes.clear()
    elif fault == 'cohort-marker': record['eye_bag_cohort_review'] = {}
    elif fault == 'same-graph': marker['after_graph_sha256'] = marker['before_graph_sha256']
    elif fault == 'input-changed': marker['dependencies'][0]['after']['state_sha256'] = '0' * 64
    elif fault == 'missing-dependency': marker['dependencies'].pop()
    else: marker['dependencies'][0]['source_proof'] = {'asset_sha256': 'a' * 64,
        'original_sha256': 'b' * 64, 'creative_source': {'sha256': 'a' * 64, 'width': 128, 'height': 192}}
    with pytest.raises((ValueError, KeyError)): H.check(record)


def test_graph_undo_redo_keeps_append_only_assets_and_two_sided_dependencies(history):
    h = history; bank = deepcopy(h.engine._people_support)
    h.owner.state = deepcopy(h.candidate)
    H.verify_restore(h.engine, h.record, undo_plans(h), h.record['targets'], redo=False)
    h.owner.state = deepcopy(h.state)
    H.verify_restore(h.engine, h.record, h.plans, h.record['targets'], redo=True)
    assert h.engine._people_support == bank


@pytest.mark.parametrize('fault', ('repair', 'crop', 'unrelated-scalar', 'new-member', 'trashed', 'support-context'))
def test_restore_refuses_changed_full_input_or_complete_graph(history, monkeypatch, fault):
    h = history; h.owner.state = deepcopy(h.candidate); plans = undo_plans(h)
    if fault == 'repair': h.alias['state']['repair'] = 'new repair'
    elif fault == 'crop': h.alias['state']['crop'] = [60, 70]
    elif fault == 'unrelated-scalar':
        h.owner.state = S.set_override(h.owner.state, 'face', h.target['target_id'], 'lnx.nose_shape.v1', '/wing', .2)
        plans['project']['before'] = h.owner.snapshot()
    elif fault == 'new-member': h.engine._docs.append({**deepcopy(h.alias), 'document_id': 'unreviewed'})
    elif fault == 'trashed': h.alias['trashed'] = True
    else: monkeypatch.setattr(H, '_dependencies', lambda *args: {'context_sha256': '0' * 64, 'state_sha256': '0' * 64})
    with pytest.raises(ValueError): H.verify_restore(h.engine, h.record, plans, h.record['targets'], redo=False)


def test_restore_uses_retained_shared_owner_when_an_unrelated_private_copy_is_current(history):
    h = history; h.owner.state = deepcopy(h.candidate)
    other = {'document_id': 'private-other', 'document_revision': 1, 'copy_number': 1,
        'path': '/fixture/private.png', 'state': {'source': 'c' * 64, 'repair': 'independent'}}
    h.engine._docs.append(other); h.engine._doc_index = len(h.engine._docs) - 1
    h.engine.current = deepcopy(other['state'])
    h.engine._people_graph_owner = SimpleNamespace(snapshot=lambda: S.empty())
    h.engine._people_active_context = {'owner': h.engine._people_graph_owner}
    h.engine._people_scope_row = other
    H.verify_restore(h.engine, h.record, undo_plans(h), h.record['targets'], redo=False)
    assert h.engine._people_scope_row is other and h.engine._people_project_context['owner'] is h.owner


def test_restore_captures_current_unsaved_repair_before_protected_dependencies(history, monkeypatch):
    h = history; h.owner.state = deepcopy(h.candidate)
    monkeypatch.setattr(V, 'row_snapshot', lambda *args: h.owner.snapshot())
    h.engine.current['repair'] = 'unsaved current repair'
    publication = Mock(); monkeypatch.setattr(L, '_publish', publication)
    with pytest.raises(ValueError, match='repair, crop'):
        L.restore_scoped(h.engine, h.record, False)
    assert h.row['state']['repair'] == 'unsaved current repair'
    publication.assert_not_called()


def test_restore_rechecks_member_dependencies_after_preparation(history, monkeypatch):
    h = history; h.owner.state = deepcopy(h.candidate)
    monkeypatch.setattr(V, 'row_snapshot', lambda *args: h.owner.snapshot())
    def prepare(*args): h.alias['state']['repair'] = 'changed during prepare'
    monkeypatch.setattr(L, 'prepare_scoped', prepare)
    publication = Mock(); monkeypatch.setattr(L, '_publish', publication)
    with pytest.raises(ValueError, match='repair, crop'):
        L.restore_scoped(h.engine, h.record, False)
    publication.assert_not_called()


def test_save_reopen_retains_exact_marker_and_rejects_malformed_member(history):
    h = history; saved = {'assets': {}, 'people_batch_history': {'batch-one': deepcopy(h.record)}}
    stacks, entries = P.prepare(saved, [], 64)
    assert stacks == {} and entries['batch-one'][H.KEY] == h.record[H.KEY]
    saved['people_batch_history']['batch-one'][H.KEY]['dependencies'].pop()
    with pytest.raises(ValueError): P.prepare(saved, [], 64)


def test_commit_validates_narrow_marker_before_any_graph_publication(history, monkeypatch):
    h = history; publication = Mock()
    monkeypatch.setattr(L, '_verify', lambda *args: None); monkeypatch.setattr(L, '_publish', publication)
    marker = deepcopy(h.record[H.KEY]); marker['after_face']['box'][0] += .01
    with pytest.raises(ValueError): L.commit_scoped(h.batch, h.engine, h.plans, request_id='invalid',
        prepare=False, prepared_targets=h.record['targets'], eye_bag_alias_history=marker)
    publication.assert_not_called(); assert not h.batch.ledger


def test_actual_dependency_codec_selects_explicit_before_after_ridge_without_live_swap(history, monkeypatch):
    from lumaretouch_engine import full_candidate_render as FULL, eye_bag_batch_history as INPUT
    h = history
    context = {'people_graph': h.state, 'people_landmarks': {}, 'people_support_assets': h.engine._people_support}
    monkeypatch.setattr(FULL, 'people_context', lambda *args: deepcopy(context))
    monkeypatch.setattr(INPUT, '_dependencies', lambda *args: {'state_sha256': 'd' * 64, 'context_sha256': 'e' * 64})
    before = REAL_DEPENDENCIES(h.engine, h.row, h.state)
    after = REAL_DEPENDENCIES(h.engine, h.row, h.candidate)
    assert before['context_sha256'] != after['context_sha256']
    assert before['state_sha256'] == after['state_sha256'] == 'd' * 64
    assert context['people_graph'] == h.state and h.owner.snapshot() == h.state


def test_legacy_unmarked_entries_do_not_acquire_alias_authority(history):
    record = deepcopy(history.record); record.pop(H.KEY)
    assert H.check(record) is None and H.status_summary(record) is None
    H.verify_restore(None, record, {}, {}, redo=False)
