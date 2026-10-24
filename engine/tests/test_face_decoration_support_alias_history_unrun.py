# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN support-only alias ledger/codec/atomicity specifications.

Synthetic sources and mocked complete rendering only. These fixtures have not
been imported, collected or run. No numerical or photographic acceptance claim.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from test_eye_bag_preset_alias_history_unrun import mixed
from test_eye_bag_preserve_host_unrun import eye, ASSET
from lumaretouch_engine import face_decoration_support_alias_history as H
from lumaretouch_engine import face_decoration_support_alias_transaction as T
from lumaretouch_engine import people_batch_ledger as L, people_history_persistence as PERSIST
from lumaretouch_engine import people_support_assets as BANK, people_state as P
from lumaretouch_engine import face_decoration_support as SUPPORT
from lumaretouch_engine import full_candidate_render as FULL, virtual_copy_people as V
from lumaretouch_engine import face_style_alias_review as CLOSURE
from lumaretouch_engine.people_graph_patch import between


@pytest.fixture
def support(mixed, monkeypatch):
    h = mixed; ref = h.review['face_ref']; before = deepcopy(h.plans['project']['before'])
    candidate, assets = SUPPORT.retain(before, {}, ref, eye())
    h.before_assets = {}; h.after_assets = assets; h.record = next(iter(assets))
    h.engine._people_support = h.before_assets
    project = {'owner': h.owner, 'people_support_assets': h.before_assets}
    h.engine._people_project_context = project; h.engine._people_active_context = project
    def context(*args):
        return {'version': 1, 'people_graph': h.owner.snapshot(),
            **{key: {} for key in V.FIELDS}, 'people_support_assets': deepcopy(T.bank(h.engine))}
    monkeypatch.setattr(FULL, 'people_context', context)
    h.plans['project']['candidate'] = candidate
    h.review = {'version': 1, 'target': H.TARGET, 'face_ref': ref, 'review_sha256': 'a' * 64,
        'before_support_sha256': None, 'support_sha256': h.record,
        'members': deepcopy(h.review['members']), 'before_bank_sha256': H.review_digest(h.before_assets),
        'candidate_bank_sha256': H.review_digest(h.after_assets)}
    for member in h.review['members']:
        member['visual'].update(before={'sha256': 'b' * 64}, after={'sha256': 'c' * 64})
    h.ack = lambda: {'review_sha256': h.review['review_sha256'], 'members': [
        {'document_id': member['visual']['document_id'], 'revision': member['visual']['revision'],
         'before_sha256': member['visual']['before']['sha256'], 'after_sha256': member['visual']['after']['sha256']}
        for member in h.review['members']]}
    h.engine._replay_state = Mock(side_effect=AssertionError('Support cannot replay document recipes'))
    def marker():
        return H.prepare(h.engine, h.review, h.plans, h.targets, before_assets=h.before_assets, after_assets=h.after_assets, ack=h.ack())
    def entry():
        return {'ops': [L.OP], 'people_changes': [], 'people_scoped_changes': [{'scope': 'project',
            'document_id': h.row['document_id'], 'changes': between(h.plans['project']['before'], h.plans['project']['candidate'])}],
            'targets': deepcopy(h.targets), 'policy': 'protected_scoped_graph', H.KEY: marker(), 'at_ns': 1, 'undone': False}
    h.marker = marker; h.entry = entry
    return h


def commit(h):
    return T.commit(h.engine, review=h.review, plans=h.plans, targets=h.targets,
        before_assets=h.before_assets, after_assets=h.after_assets, request_id='support-alias', ack=h.ack())


def test_support_marker_pins_records_without_preset_state_authority(support):
    h = support; marker = H.check(h.entry())
    assert marker['support_assets']['before'] is None
    assert BANK.content_digest(marker['support_assets']['after']) == h.record
    assert marker['document_ids'] == ['doc-current', 'doc-sibling']
    assert 'current_states' not in marker and 'selected_modules' not in marker
    assert marker['before_face']['local_assets'].get(H.TARGET) is None
    for dependency in marker['dependencies']:
        assert dependency['before']['state_sha256'] == dependency['after']['state_sha256']
        assert dependency['before']['context_sha256'] != dependency['after']['context_sha256']


@pytest.mark.parametrize('fault', ('second-marker', 'scalar', 'ridge', 'another-face', 'association', 'observation',
    'foreign-record', 'record-content', 'missing-record', 'wrong-kind', 'member', 'state-change', 'same-record'))
def test_support_marker_cannot_widen_its_one_reference_authority(support, fault):
    h = support; entry = h.entry(); marker = entry[H.KEY]; change = entry['people_scoped_changes'][0]['changes'][0]
    if fault == 'second-marker': entry['eye_bag_preset_alias_review'] = {}
    elif fault == 'scalar': change['collection'] = 'overrides'
    elif fault == 'ridge':
        face = marker['after_face']; face['local_assets']['eye_bag_ridge_visibility'] = face['local_assets'].pop(H.TARGET)
        change['after'] = deepcopy(face)
    elif fault == 'another-face': change['key'] = 'another-face'
    elif fault == 'association': change['collection'] = 'links'
    elif fault == 'observation': marker['after_face']['box'][0] += .01; change['after'] = deepcopy(marker['after_face'])
    elif fault == 'foreign-record': marker['support_assets']['after']['face_ref']['face_instance_id'] = 'another-face'
    elif fault == 'record-content': marker['support_assets']['after']['row']['region']['recipe']['objects'][0]['opacity'] = .5
    elif fault == 'missing-record': marker['support_assets']['after'] = None
    elif fault == 'wrong-kind': marker['after_face']['local_assets'][H.TARGET]['kind'] = 'facial_wrinkles'
    elif fault == 'member': marker['document_ids'].pop()
    elif fault == 'state-change': marker['dependencies'][0]['after']['state_sha256'] = '0' * 64
    else: marker['after_face'] = deepcopy(marker['before_face']); marker['support_assets']['after'] = None; change['after'] = deepcopy(marker['after_face'])
    with pytest.raises((ValueError, KeyError)): H.check(entry)


def test_atomic_publication_preserves_every_own_recipe_and_all_member_fences(support):
    h = support; own = {row['document_id']: H.stable(H.project_state(H.current_state(h.engine, row), H.state_fields(h.engine))) for row in h.engine._docs}
    bid, frame = commit(h)
    assert h.engine._people_shared_mutation and h.row['document_revision'] == 5 and h.sibling['document_revision'] == 9
    assert len(h.batch.ledger) == 1 and H.status_summary(h.batch.ledger[bid])['member_count'] == 2
    assert H.graph_digest(h.owner.snapshot()) == H.graph_digest(h.plans['project']['candidate'])
    assert T.bank(h.engine)[h.record] == h.after_assets[h.record]
    assert {row['document_id']: H.stable(H.project_state(H.current_state(h.engine, row), H.state_fields(h.engine))) for row in h.engine._docs} == own
    h.engine._replay_state.assert_not_called()
    assert h.row['undo'] == h.row['redo'] == h.sibling['undo'] == h.sibling['redo'] == []


def test_render_preparation_never_installs_candidate_assets(support):
    h = support
    def render(*args, **kwargs):
        assert T.bank(h.engine) == {} and h.owner.fence == 0
        assert kwargs['staged_people_context']['people_support_assets'][h.record] == h.after_assets[h.record]
        return None, {}
    h.render.side_effect = render
    commit(h)
    assert h.render.call_count == 2


def test_noop_has_no_history_bank_or_revision_mutation(support):
    h = support; h.plans['project']['candidate'] = deepcopy(h.plans['project']['before'])
    with pytest.raises(ValueError, match='Identical') as failed: commit(h)
    assert not failed.value.side_effects_started and not failed.value.requires_reload
    assert not h.batch.ledger and T.bank(h.engine) == {} and h.owner.fence == 0
    assert h.row['document_revision'] == 4 and h.sibling['document_revision'] == 8


def test_preparation_failure_is_definite_no_write(support):
    h = support; h.render.side_effect = ValueError('full-source unavailable')
    with pytest.raises(ValueError) as failed: commit(h)
    assert not failed.value.side_effects_started and not failed.value.requires_reload
    assert not h.engine._people_shared_mutation and not h.batch.ledger and T.bank(h.engine) == {}


def test_render_failure_compensates_graph_and_bank_not_monotonic_fences(support):
    h = support; h.engine._write_current_frame.side_effect = ValueError('failed frame')
    with pytest.raises(ValueError) as failed: commit(h)
    assert failed.value.side_effects_started and failed.value.rolled_back and not failed.value.requires_reload
    assert H.graph_digest(h.owner.snapshot()) == H.graph_digest(h.plans['project']['before'])
    assert T.bank(h.engine) == {} and h.owner.fence == 2 and not h.batch.ledger
    assert h.row['document_revision'] == 5 and h.sibling['document_revision'] == 9 and h.engine._people_shared_mutation


def test_intervening_owner_is_not_overwritten_and_candidate_bytes_survive(support):
    h = support
    def frame(*args):
        later = P.set_override(h.owner.snapshot(), 'face', h.review['face_ref']['face_instance_id'], 'lnx.eye_bags.v2', '/amount', .8)
        h.owner.commit(later, expected_fence=h.owner.fence)
        raise ValueError('later owner mutation')
    h.engine._write_current_frame.side_effect = frame
    with pytest.raises(ValueError) as failed: commit(h)
    assert failed.value.side_effects_started and not failed.value.rolled_back and failed.value.requires_reload
    assert h.record in T.bank(h.engine) and h.owner.fence == 2 and not h.batch.ledger
    h.batch.editor.invalidate.assert_called_once()


def test_late_dirty_failure_retains_known_batch_id_but_no_false_success(support):
    h = support; h.batch.editor.mark_dirty.side_effect = RuntimeError('late dirty failure')
    with pytest.raises(RuntimeError) as failed: commit(h)
    assert failed.value.side_effects_started and failed.value.requires_reload and not failed.value.rolled_back
    assert failed.value.batch_id in h.batch.ledger and h.record in T.bank(h.engine)
    assert failed.value.face_decoration_support_alias_review == H.status_summary(h.batch.ledger[failed.value.batch_id])
    assert failed.value.alias_members == [
        {'document_id': 'doc-current', 'expected_revision': '4', 'result_revision': '5'},
        {'document_id': 'doc-sibling', 'expected_revision': '8', 'result_revision': '9'}]


def test_history_undo_redo_and_reopen_keep_both_sides_without_document_replay(support):
    h = support; bid, _ = commit(h); entry = h.batch.ledger[bid]
    L.restore_scoped(h.engine, entry, False)
    assert H.TARGET not in h.owner.snapshot()['faces'][h.review['face_ref']['face_instance_id']]['local_assets']
    assert h.record in T.bank(h.engine)
    h.engine._batch_sync = h.batch
    project = {'assets': {}, 'people_support_assets': deepcopy(T.bank(h.engine))}
    PERSIST.save(h.engine, project)
    _, restored = PERSIST.prepare(project, [], 64)
    L.restore_scoped(h.engine, restored[bid], True)
    assert h.owner.snapshot()['faces'][h.review['face_ref']['face_instance_id']]['local_assets'][H.TARGET]['content_sha256'] == h.record
    h.engine._replay_state.assert_not_called()


def test_revised_paint_keeps_both_exact_records_through_undo_and_reopen(support):
    h = support; commit(h); previous = h.record
    h.before_assets = deepcopy(T.bank(h.engine)); h.plans['project']['before'] = h.owner.snapshot()
    region = eye(); region['recipe']['objects'][0]['points'][0] = [.31, .41]
    h.plans['project']['candidate'], h.after_assets = SUPPORT.retain(h.owner.snapshot(), h.before_assets, h.review['face_ref'], region)
    h.record = h.plans['project']['candidate']['faces'][h.review['face_ref']['face_instance_id']]['local_assets'][H.TARGET]['content_sha256']
    h.targets = H.targets(h.engine, h.batch.ledger[next(iter(h.batch.ledger))][H.KEY], h.owner.snapshot())
    h.review.update(before_support_sha256=previous, support_sha256=h.record,
        before_bank_sha256=H.review_digest(h.before_assets), candidate_bank_sha256=H.review_digest(h.after_assets))
    for member in h.review['members']:
        member['visual']['revision'] = str(h.batch.versions.version(h.batch.versions.find(h.engine._docs, member['visual']['document_id'])[1]).revision)
    bid, _ = commit(h); marker = h.batch.ledger[bid][H.KEY]
    assert BANK.content_digest(marker['support_assets']['before']) == previous
    assert BANK.content_digest(marker['support_assets']['after']) == h.record
    L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert h.owner.snapshot()['faces'][h.review['face_ref']['face_instance_id']]['local_assets'][H.TARGET]['content_sha256'] == previous
    assert previous in T.bank(h.engine) and h.record in T.bank(h.engine)
    H.validate_project_assets(h.batch.ledger[bid], {'people_support_assets': T.bank(h.engine)})


@pytest.mark.parametrize('fault', ('repair', 'crop', 'source', 'new-member', 'unavailable', 'missing-record'))
def test_fullset_history_refuses_changed_inputs_or_members(support, fault):
    h = support; bid, _ = commit(h); previous = h.owner.snapshot()
    if fault == 'repair': h.engine.current['_repair_ops'] = ['new repair']
    elif fault == 'crop': h.sibling['state']['_crop_rect'] = [.2, .2, .6, .6]
    elif fault == 'source': h.sibling['state']['_fixture_source'] = 'c' * 64
    elif fault == 'new-member': h.engine._docs.append({**deepcopy(h.sibling), 'document_id': 'unreviewed'})
    elif fault == 'unavailable': h.sibling['trashed'] = True
    else: T.bank(h.engine).pop(h.record)
    with pytest.raises(ValueError): L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert h.owner.snapshot() == previous


def test_parked_source_undo_does_not_switch_or_modify_private_selection(support):
    h = support; bid, _ = commit(h)
    other = {**deepcopy(h.sibling), 'document_id': 'private-other', 'copy_number': 1, 'document_revision': 1}
    other['state']['_fixture_source'] = 'c' * 64
    h.engine._docs.append(other); h.engine._doc_index = 2; h.engine.current = deepcopy(other['state'])
    private = {'owner': SimpleNamespace(snapshot=lambda: P.empty()), 'people_support_assets': {}}
    h.engine._people_active_context = private; h.engine._people_graph_owner = private['owner']; h.engine._people_scope_row = other
    h.engine._people_support = private['people_support_assets']
    own = H.stable(H.project_state(h.engine.current, H.state_fields(h.engine)))
    L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert V.current_row(h.engine) is other and h.engine._people_active_context is private and h.engine._people_support == {}
    assert H.stable(H.project_state(h.engine.current, H.state_fields(h.engine))) == own
    assert h.record in h.engine._people_project_context['people_support_assets']


def test_history_requires_correlated_exact_request_and_old_entries_remain_unmarked(support):
    h = support; bid, _ = commit(h); entry = h.batch.ledger[bid]
    command = {'cmd': 'batch', 'action': 'undo', 'request_id': 'history-original', 'batch_id': bid}
    T.require_history_request(h.batch, command, entry)
    for key in ('request_id', 'batch_id', 'cmd'):
        malformed = deepcopy(command); malformed.pop(key)
        with pytest.raises(ValueError): T.require_history_request(h.batch, malformed, entry)
    malformed = {**command, 'docs': [0]}
    with pytest.raises(ValueError): T.require_history_request(h.batch, malformed, entry)
    old = deepcopy(entry); old.pop(H.KEY)
    assert H.check(old) is None and H.status_summary(old) is None
    assert T.failure_context(h.batch, command)[H.KEY] == H.status_summary(entry)


def test_reopened_history_requires_exact_old_and_new_records(support):
    h = support; entry = h.entry()
    project = {'assets': {}, 'people_support_assets': deepcopy(h.after_assets), 'people_batch_history': {'saved': entry}}
    _, records = PERSIST.prepare(project, [], 64)
    assert records['saved'][H.KEY] == entry[H.KEY]
    project['people_support_assets'].clear()
    with pytest.raises(ValueError): PERSIST.prepare(project, [], 64)


def test_maximum_result_revision_is_verified_read_only(support):
    h = support
    for row in h.engine._docs: row['document_revision'] = CLOSURE.MAX_REVISION - 1
    for item in h.targets.values(): item['revision'] = CLOSURE.MAX_REVISION - 1
    for member in h.review['members']: member['visual']['revision'] = str(CLOSURE.MAX_REVISION - 1)
    commit(h)
    assert all(row['document_revision'] == CLOSURE.MAX_REVISION for row in h.engine._docs)
    assert len(h.batch.ledger) == 1


def test_unrelated_new_support_cannot_piggyback_on_support_publication(support):
    h = support; extra = deepcopy(h.after_assets[h.record]); extra['row']['region']['recipe']['objects'][0]['opacity'] = .5
    h.after_assets[BANK.content_digest(extra)] = extra
    h.review['candidate_bank_sha256'] = H.review_digest(h.after_assets)
    with pytest.raises(ValueError, match='unrelated or donor'): commit(h)
    assert h.owner.fence == 0 and T.bank(h.engine) == {} and not h.batch.ledger


def test_trimmed_saved_durable_field_set_is_never_replay_authority(support):
    h = support; entry = h.entry(); entry[H.KEY]['state_fields'].remove('_crop_rect')
    assert H.check(entry) is not None
    with pytest.raises(ValueError, match='durable field schema'):
        H.verify_restore(h.engine, entry, h.plans, h.targets, redo=True, assets=h.after_assets)
    assert h.owner.fence == 0 and not h.batch.ledger


def test_member_input_changed_during_preparation_is_refused_before_mutation(support):
    h = support
    def render(*args, **kwargs): h.sibling['state']['_crop_rect'] = [.2, .2, .5, .5]; return None, {}
    h.render.side_effect = render
    with pytest.raises(ValueError) as failed: commit(h)
    assert not failed.value.side_effects_started and h.owner.fence == 0 and not h.batch.ledger


def test_late_known_id_never_fabricates_membership_after_changed_owner(support):
    h = support
    def dirty():
        h.sibling['state']['_crop_rect'] = [.3, .3, .5, .5]
        raise RuntimeError('changed owner after publication')
    h.batch.editor.mark_dirty.side_effect = dirty
    with pytest.raises(RuntimeError) as failed: commit(h)
    assert failed.value.batch_id in h.batch.ledger and failed.value.requires_reload
    assert not hasattr(failed.value, 'face_decoration_support_alias_review') and not hasattr(failed.value, 'alias_members')


@pytest.mark.parametrize('no_write,rolled_back', ((True, False), (False, False), (False, True)))
def test_history_failure_has_exact_saved_classification_and_no_partial_restore(support, no_write, rolled_back):
    from lumaretouch_engine.batch_sync import BatchSyncController
    h = support; bid, _ = commit(h); h.batch.preflight = SimpleNamespace(emit_result=Mock())
    command = {'cmd': 'batch', 'action': 'undo', 'request_id': 'history-failure', 'batch_id': bid}
    BatchSyncController._reject(h.batch, command, 'history failure', no_write=no_write, rolled_back=rolled_back)
    result = h.batch.preflight.emit_result.call_args.args[1]
    assert result[H.KEY] == H.status_summary(h.batch.ledger[bid]) and result['batch_id'] == bid
    assert result['module_scope'] == [L.OP] and result['no_write'] is no_write
    assert result['outcome_unknown'] is (not no_write and not rolled_back)
    assert result.get('rolled_back', False) is rolled_back
    assert result.get('restored') == ([] if no_write or rolled_back else None)


def test_compensated_history_retains_advanced_fences_without_claiming_no_write(support):
    from lumaretouch_engine.batch_sync import BatchSyncController
    h = support; bid, _ = commit(h); h.batch.preflight = SimpleNamespace(emit_result=Mock())
    h.batch.editor.people_restore = lambda entry, redo: L.restore_scoped(h.engine, entry, redo)
    h.engine._write_current_frame.side_effect = ValueError('history frame failed after publication')
    command = {'cmd': 'batch', 'action': 'undo', 'request_id': 'history-compensation', 'batch_id': bid}
    before = H.graph_digest(h.owner.snapshot()); revisions = [row['document_revision'] for row in h.engine._docs]
    with pytest.raises(ValueError) as failed: L.restore(h.batch, command)
    error = failed.value
    assert error.side_effects_started and error.rolled_back and not error.requires_reload
    assert error.face_decoration_support_alias_history_no_write is False
    assert error.face_decoration_support_alias_history_rolled_back is True
    assert H.graph_digest(h.owner.snapshot()) == before and h.batch.ledger[bid]['undone'] is False
    assert [row['document_revision'] for row in h.engine._docs] == [revision + 1 for revision in revisions]
    BatchSyncController._reject(h.batch, command, str(error),
        no_write=error.face_decoration_support_alias_history_no_write,
        rolled_back=error.face_decoration_support_alias_history_rolled_back)
    result = h.batch.preflight.emit_result.call_args.args[1]
    assert result['success'] is False and result['outcome_unknown'] is False
    assert result['no_write'] is False and result['rolled_back'] is True and result['restored'] == []
    assert result[H.KEY] == H.status_summary(h.batch.ledger[bid])


@pytest.mark.parametrize('fault', ('digest', 'member-image', 'order', 'omitted', 'revision'))
def test_history_requires_actual_exact_image_ack_not_review_metadata(support, fault):
    h = support; ack = h.ack()
    if fault == 'digest': ack['review_sha256'] = 'd' * 64
    elif fault == 'member-image': ack['members'][0]['after_sha256'] = 'd' * 64
    elif fault == 'order': ack['members'].reverse()
    elif fault == 'omitted': ack['members'].pop()
    else: ack['members'][0]['revision'] = '5'
    with pytest.raises(ValueError):
        T.commit(h.engine, review=h.review, plans=h.plans, targets=h.targets,
            before_assets=h.before_assets, after_assets=h.after_assets, request_id='bad-ack', ack=ack)
    assert h.owner.fence == 0 and not h.batch.ledger


def test_history_digest_binds_ack_and_preserves_original_review_identity(support):
    h = support; marker = h.marker()
    assert marker['review_sha256'] == H.review_digest(h.ack())
    assert marker['review_sha256'] != h.review['review_sha256']
    assert marker['source_review_sha256'] == h.review['review_sha256']
    assert marker['before_bank_sha256'] == H.review_digest(h.before_assets)
    assert marker['candidate_bank_sha256'] == H.review_digest(h.after_assets)


def test_mark_started_is_called_once_after_all_detached_renders(support):
    h = support; started = Mock()
    def claim():
        assert h.render.call_count == 2 and h.owner.fence == 0 and T.bank(h.engine) == {}
        started()
    T.commit(h.engine, review=h.review, plans=h.plans, targets=h.targets,
        before_assets=h.before_assets, after_assets=h.after_assets, request_id='claim-after-render',
        ack=h.ack(), mark_started=claim)
    started.assert_called_once()


def test_original_scalar_authority_still_rejects_support_pointer_change(support):
    from lumaretouch_engine.face_decoration_alias_history import scalar_changes
    h = support
    with pytest.raises(ValueError):
        scalar_changes(h.plans['project']['before'], h.plans['project']['candidate'], [h.review['face_ref']])


def test_old_marked_entries_cannot_launder_new_support_marker(support):
    from lumaretouch_engine import face_style_alias_history as STYLE, eye_bag_batch_history as EYE
    from lumaretouch_engine import eye_bag_cohort_history as COHORT, eye_bag_alias_history as ALIAS
    from lumaretouch_engine import eye_bag_preset_alias_history as PRESET, eye_bag_recovery_alias_history as RECOVERY
    for module in (STYLE, EYE, COHORT, ALIAS, PRESET, RECOVERY):
        assert module.check({}) is None
        with pytest.raises(ValueError, match='another history authority'):
            module.check({module.KEY: {}, H.KEY: support.marker()})


def test_common_ledger_rejects_mixed_markers_before_any_preparation(support):
    h = support
    with pytest.raises(ValueError, match='cannot be combined'):
        L.commit_scoped(h.batch, h.engine, h.plans, request_id='mixed-markers',
            face_decoration_support_alias_history=h.marker(), face_decoration_alias_history={})
    assert h.owner.fence == 0 and not h.batch.ledger and not h.render.called


def test_prehandler_rejection_retains_exact_support_history_identity(support):
    from lumaretouch_engine.batch_dispatch_receipt import rejected
    h = support; bid, _ = commit(h); h.engine._batch_sync = h.batch; emit = Mock()
    request = {'cmd': 'batch', 'action': 'undo', 'request_id': 'prehandler-stop', 'batch_id': bid}
    rejected(request, ValueError('dispatcher stopped'), {'engine': h.engine, 'message': request, 'started': False}, emit)
    result = emit.call_args.args[0]
    assert result[H.KEY] == H.status_summary(h.batch.ledger[bid])
    assert result['no_write'] is True and result['outcome_unknown'] is False and result['restored'] == []


def test_frozen_whole_bank_is_proposal_evidence_not_undo_deletion_authority(support):
    h = support; h.review['before_bank_sha256'] = 'd' * 64
    with pytest.raises(ValueError, match='banks differ'): commit(h)
    assert T.bank(h.engine) == {} and h.owner.fence == 0


def test_colour_dependency_cannot_be_hidden_by_unchanged_graph(support):
    h = support; bid, _ = commit(h); h.sibling['state']['_exposure'] = [.9]
    with pytest.raises(ValueError, match='own recipe'):
        L.restore_scoped(h.engine, h.batch.ledger[bid], False)


def test_support_authority_requires_selected_and_all_active_faces(support):
    from lumaretouch_engine.face_decoration_support_alias_authority import support_changes
    from lumaretouch_engine import face_decoration_state as D
    h = support; ref = h.review['face_ref']; before = deepcopy(h.plans['project']['before'])
    other = P.new_face(ASSET, [.2, .2, .7, .8], deepcopy(before['faces'][ref['face_instance_id']]['evidence']))
    before['faces'][other['face_instance_id']] = other; other_ref = P.face_ref(other)
    before, old_bank = SUPPORT.retain(before, {}, other_ref, eye())
    before = P.set_override(before, 'face', other['face_instance_id'], D.OP, '/strength', .3)
    candidate, new_bank = SUPPORT.retain(before, old_bank, ref, eye())
    with pytest.raises(ValueError, match='all before/candidate active'):
        support_changes(before, candidate, [ref], old_bank, new_bank)
    assert support_changes(before, candidate, [ref, other_ref], old_bank, new_bank)


def test_initial_support_cannot_invent_an_active_before_image(support):
    from lumaretouch_engine.face_decoration_support_alias_authority import support_changes
    from lumaretouch_engine import face_decoration_state as D
    h = support; ref = h.review['face_ref']
    before = P.set_override(h.plans['project']['before'], 'face', ref['face_instance_id'], D.OP, '/strength', .3)
    candidate, new_bank = SUPPORT.retain(before, {}, ref, eye())
    with pytest.raises(ValueError): support_changes(before, candidate, [ref], {}, new_bank)


def test_new_support_authority_does_not_grant_detach_but_history_undo_can(support):
    from lumaretouch_engine.face_decoration_support_alias_authority import support_changes
    h = support; before = h.plans['project']['candidate']; candidate = h.plans['project']['before']
    with pytest.raises(ValueError, match='initial or revised'):
        support_changes(before, candidate, [h.review['face_ref']], h.after_assets, h.after_assets)
    assert support_changes(before, candidate, [h.review['face_ref']], h.after_assets, h.after_assets, allow_detach=True)



def test_in_place_bank_mutation_after_claim_is_not_overwritten(support):
    h = support
    def claim():
        record = deepcopy(h.after_assets[h.record]); record['row']['region']['recipe']['objects'][0]['opacity'] = .5
        T.bank(h.engine)[BANK.content_digest(record)] = record
    with pytest.raises(ValueError) as failed:
        T.commit(h.engine, review=h.review, plans=h.plans, targets=h.targets,
            before_assets=h.before_assets, after_assets=h.after_assets, request_id='changed-bank-during-claim',
            ack=h.ack(), mark_started=claim)
    assert h.owner.fence == 0 and not h.batch.ledger
    assert failed.value.requires_reload and not failed.value.rolled_back and T.bank(h.engine)



def test_numeric_serialization_only_cannot_manufacture_revised_paint(support):
    from lumaretouch_engine.face_decoration_support_alias_authority import support_changes
    h = support; before = h.plans['project']['candidate']; old_bank = h.after_assets
    region = eye(); region['recipe']['objects'][0]['opacity'] = 1
    candidate, new_bank = SUPPORT.retain(before, old_bank, h.review['face_ref'], region)
    with pytest.raises(ValueError, match='Identical visible painting'):
        support_changes(before, candidate, [h.review['face_ref']], old_bank, new_bank)
