"""AUTHORED / UNRUN: torso scalar frozen batch ownership and retry fences.

No imports, test collection, execution, builds, typechecks, inference or downloads
were performed while authoring. Body/face records are synthetic contract inputs,
not detector output. Visual ports below deliberately hash NON-PNG bytes: these
fixtures test transaction fencing, never actual full rendering or photo quality.
Real full-render evidence belongs to torso_length_transfer_review's own tests.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import base64
import json

import pytest

from test_batch_sync_controller import fixture as base_fixture
from test_torso_length_support_unrun import fixture as body_fixture
from lumaretouch_engine import body_pose_evidence as E, body_pose_state as B
from lumaretouch_engine import body_pose_project as D, torso_length_project as P
from lumaretouch_engine import torso_length_scope as T, torso_length_state as S
from lumaretouch_engine import torso_length_runtime as R, torso_length_transfer_review as REVIEW
from lumaretouch_engine import creative_derived_source as SOURCE, waist_shape_state as W
from lumaretouch_engine import batch_preflight as STORE, scope as SC
from lumaretouch_engine.batch_group_history import restore_group
from lumaretouch_engine.batch_sync import verify_history_source
from lumaretouch_engine.optics_candidate_identity import fingerprint
from lumaretouch_engine.ops.geometry import out_size


def target_identity(row, state):
    bank, body, item, support = T.target(state)
    face = R.validate_face_review(support['data'], body, row['_synthetic_people_context'])
    return {'body_ref': deepcopy(body['record']['body_ref']),
        'associated_face': R.face_binding(face), 'body_support_sha256': item['support_sha256'],
        'body_review_sha256': E.content_digest(item['review']), 'bank_sha256': E.content_digest(bank)}


def synthetic_history_identity(row, state, document, revision):
    T.validate_target(state, row['path'], (row['src_h'], row['src_w']))
    target_identity(row, state)
    return {'document_id': document, 'revision': str(revision),
        'source_proof': SOURCE.row_proof({**row, 'state': state}),
        'candidate_sha256': fingerprint(state),
        'people_sha256': fingerprint(row['_synthetic_people_context'])}


def synthetic_visual_record(row, before, candidate, document, revision):
    """Full-state transaction mock only; does not claim these bytes are PNGs."""
    left = synthetic_history_identity(row, before, document, revision)
    right = synthetic_history_identity(row, candidate, document, revision)
    a, b = target_identity(row, before), target_identity(row, candidate)
    assert all(a[k] == b[k] for k in a if k != 'bank_sha256')
    size = [row['src_w'], row['src_h']]
    record = {'version': 1, 'document_id': document, 'revision': str(revision),
        'source_proof': left['source_proof'], 'before_sha256': left['candidate_sha256'],
        'candidate_sha256': right['candidate_sha256'], 'before_people_sha256': left['people_sha256'],
        'candidate_people_sha256': right['people_sha256'], 'source_size': size,
        'before_output_size': list(out_size(*size, before['_crop_rect'], before['_crop_rotation'])),
        'after_output_size': list(out_size(*size, candidate['_crop_rect'], candidate['_crop_rotation'])),
        'parameters': T.params_of(candidate), **{k: v for k, v in b.items() if k != 'bank_sha256'},
        'before_bank_sha256': a['bank_sha256'], 'candidate_bank_sha256': b['bank_sha256']}
    images = {}
    for side, state in (('before', before), ('after', candidate)):
        payload = ('SYNTHETIC TRANSACTION PORT, NOT A PNG: ' + document + ':' + fingerprint(state)).encode()
        output = record[side + '_output_size']; scale = min(1., REVIEW.PREVIEW_EDGE / max(output))
        image = {'mime': 'image/png', 'width': max(1, round(output[0] * scale)),
            'height': max(1, round(output[1] * scale)), 'sha256': sha256(payload).hexdigest()}
        record[side] = image
        images[side] = {**image, 'base64': base64.b64encode(payload).decode('ascii')}
    compact = REVIEW.checked(record)
    return compact, {**deepcopy(compact), **images}


def synthetic_verify(row, before, candidate, document, revision, proof):
    expected, _ = synthetic_visual_record(row, before, candidate, document, revision)
    if REVIEW.checked(proof) != expected:
        raise ValueError('Synthetic torso target full-state, body, face, source or display fence changed')
    return expected


def fixture(tmp_path):
    owner, rows, current, events, replays, remember = base_fixture()
    for index, row in enumerate(rows):
        path = tmp_path / f'torso-original-{index}.bin'
        path.write_bytes(f'synthetic-torso-original-{index}'.encode())
        row.update(path=str(path), src_w=1024, src_h=1024)
        row['state'].update(_crop_rect=[0., 0., 1., 1.], _crop_rotation=0., _exposure=(0.,) * 7)
        source = {**SOURCE.binding(row['state'], str(path), (1024, 1024)), 'orientation': E.ORIENTATION}
        bank, people, ref, _, _ = body_fixture(source=source, amount=.65 if index == 0 else -.2)
        # An unrelated retained body operation is never sourced from another row.
        bank = B.set_recipe(bank, ref, W.neutral(), operation_id=W.OPERATION_ID)
        row['state'][D.KEY] = P.pack(bank)
        row['_synthetic_people_context'] = people
    owner.editor = replace(owner.editor, prepare_torso=synthetic_visual_record,
        verify_torso=synthetic_verify, torso_history_identity=synthetic_history_identity)
    owner.preflight.ports = replace(owner.preflight.ports,
        prepare_torso=synthetic_visual_record, verify_torso=synthetic_verify)
    return owner, rows, current, events, replays, remember


def preflight(owner, events, docs=(1, 2), policy='skip_and_report'):
    owner.handle_command({'action': 'preflight', 'docs': list(docs), 'module_scope': [T.OP],
        'conflict_policy': policy, 'request_id': 'torso-review'})
    result = events[-1]
    assert result['success'], result
    return result


def acks(plan):
    return [{'document_id': target['document_id'], 'revision': target['revision'],
        'before_sha256': target['torso_transfer']['before']['sha256'],
        'after_sha256': target['torso_transfer']['after']['sha256']}
        for target in plan['targets'] if not target['blocked']]


def commit(owner, events, plan, acknowledgment=None):
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'request_id': 'torso-commit', 'torso_review_ack': acks(plan) if acknowledgment is None else acknowledgment})
    return events[-1]


def protected_body(state):
    bank, body, _, _ = T.target(state)
    bank.pop('revision')
    body['operations'][T.OP].pop('recipe')
    return bank


def test_every_target_has_full_review_and_independent_body_face_source(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    before = deepcopy(rows); plan = preflight(owner, events)
    assert plan['applies'] == {T.OP: {'version': 1, 'amount': .65}}
    assert plan['ok'] == 2 and not plan['blocked']
    for target in plan['targets']:
        row = rows[target['index']]; proof = target['torso_transfer']
        assert target['source_proof'] == SOURCE.row_proof(row)
        assert target['source_proof'] != plan['source_snapshot']['source_proof']
        assert proof['body_ref']['asset_sha256'] == target['source_proof']['asset_sha256']
        assert target['before'] == {T.OP: {'target_recipe_key': T.undo_key(row['state'])}}
    frozen = owner.preflight.store.pending[plan['preflight_token']]
    assert all('base64' not in target.torso_json for target in frozen.targets)
    assert rows == before and not owner.ledger and not replays


@pytest.mark.parametrize('kind', ['empty', 'reordered', 'duplicate', 'hash', 'revision', 'extra-field'])
def test_invalid_ack_never_consumes_review_or_writes(tmp_path, kind):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    plan = preflight(owner, events); value = acks(plan); before = deepcopy(rows)
    if kind == 'empty': value = []
    elif kind == 'reordered': value.reverse()
    elif kind == 'duplicate': value[1] = deepcopy(value[0])
    elif kind == 'hash': value[0]['after_sha256'] = 'f' * 64
    elif kind == 'revision': value[0]['revision'] = '999'
    else: value[0]['approved'] = True
    result = commit(owner, events, plan, value)
    assert not result['success'] and plan['preflight_token'] in owner.preflight.store.pending
    assert rows == before and not replays and not owner.ledger
    assert commit(owner, events, plan)['success']


def test_missing_ack_leaves_token_usable(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path); plan = preflight(owner, events)
    before = deepcopy(rows)
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'], 'request_id': 'missing'})
    assert not events[-1]['success'] and rows == before
    assert plan['preflight_token'] in owner.preflight.store.pending


def test_commit_transfers_only_scalar_and_retains_target_bank(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    before = deepcopy(rows); plan = preflight(owner, events); result = commit(owner, events, plan)
    assert result['success'] and result['module_scope'] == [T.OP]
    assert result['torso_review_ack'] == acks(plan) and not replays
    for index in (1, 2):
        assert T.params_of(rows[index]['state']) == {'version': 1, 'amount': .65}
        assert protected_body(rows[index]['state']) == protected_body(before[index]['state'])
        receipt = owner.ledger[result['batch_id']]['targets'][str(index)]
        assert 'torso_review' in receipt and receipt['source_proof'] == SOURCE.row_proof(rows[index])
        assert receipt['torso_review']['before_bank_sha256'] == T.bank_sha256(before[index]['state'])
        assert receipt['torso_review']['candidate_bank_sha256'] == T.bank_sha256(rows[index]['state'])


@pytest.mark.parametrize('field', ['source-file', 'full-edit', 'bank-revision', 'people', 'support-review'])
def test_changed_target_cannot_reuse_review(tmp_path, field):
    owner, rows, _, events, _, _ = fixture(tmp_path); plan = preflight(owner, events)
    row = rows[1]
    if field == 'source-file': (tmp_path / 'torso-original-1.bin').write_bytes(b'changed effective source')
    elif field == 'full-edit': row['state']['unrelated_visual_edit'] = 'changed after review'
    elif field == 'people': row['_synthetic_people_context']['revision'] += 1
    else:
        bank = D.bank(row['state'])
        if field == 'bank-revision': bank['revision'] += 1
        else:
            body = next(iter(bank['bodies'].values()))
            body['operations'][T.OP]['review'] = None
        row['state'][D.KEY] = P.pack(bank)
    before = deepcopy(row['state']); result = commit(owner, events, plan)
    assert result['success'] and result['targets'] == [2]
    assert row['state'] == before


def test_frozen_source_amount_survives_later_source_edit(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path); plan = preflight(owner, events)
    T.install(rows[0]['state'], {'version': 1, 'amount': -.6}); owner.versions.advance(rows[0])
    result = commit(owner, events, plan)
    assert result['success'] and result['source_changed_since_preflight']
    assert all(T.params_of(rows[i]['state'])['amount'] == .65 for i in (1, 2))


def test_direct_transfer_and_ack_on_noncommit_are_refused(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); before = deepcopy(rows)
    owner.handle_command({'action': 'commit', 'docs': [1], 'module_scope': [T.OP], 'request_id': 'direct'})
    assert not events[-1]['success']
    for action in ('preflight', 'state', 'undo', 'redo'):
        owner.handle_command({'action': action, 'request_id': 'wrong-action', 'torso_review_ack': []})
        assert not events[-1]['success']
    assert rows == before and not replays and not owner.ledger


def test_missing_review_adapter_blocks_without_render_or_write(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); before = deepcopy(rows)
    owner.preflight.ports = replace(owner.preflight.ports, prepare_torso=None)
    plan = preflight(owner, events)
    assert plan['ok'] == 0 and plan['blocked'] == 2
    assert all(target['torso_transfer'] is None for target in plan['targets'])
    assert rows == before and not replays


def test_completed_token_requires_exact_ack_and_never_reexecutes(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = preflight(owner, events)
    result = commit(owner, events, plan); assert result['success']
    before = deepcopy(rows); replay_count = len(replays)
    repeated = commit(owner, events, plan)
    assert repeated['replayed'] and repeated['batch_id'] == result['batch_id']
    bad = acks(plan); bad[0]['after_sha256'] = 'f' * 64
    assert not commit(owner, events, plan, bad)['success']
    assert rows == before and len(replays) == replay_count and len(owner.ledger) == 1


def test_result_budget_fallback_preserves_exact_retry_fence(tmp_path, monkeypatch):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = preflight(owner, events)
    monkeypatch.setattr(STORE, 'MAX_RESULT_BYTES', 1)
    result = commit(owner, events, plan)
    assert not result['success'] and result['outcome_unknown']
    assert result['module_scope'] == [T.OP] and result['torso_review_ack'] == acks(plan)
    before = deepcopy(rows); count = len(replays)
    again = commit(owner, events, plan)
    assert again['replayed'] and again['outcome_unknown'] and again['torso_review_ack'] == acks(plan)
    assert rows == before and len(replays) == count


def test_guard_is_never_bypassed_by_preflight_or_pending_commit(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path); plan = preflight(owner, events)
    before = deepcopy(rows)
    owner.editor = replace(owner.editor, guard=lambda _: 'document is guarded')
    assert not commit(owner, events, plan)['success'] and rows == before
    assert plan['preflight_token'] in owner.preflight.store.pending
    owner.handle_command({'action': 'preflight', 'docs': [1], 'module_scope': [T.OP], 'request_id': 'guard'})
    assert not events[-1]['success'] and rows == before


def test_live_failed_replay_keeps_parked_rows_and_terminal_ack(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path); plan = preflight(owner, events, (0, 1, 2))
    before = deepcopy(rows); replay = owner.editor.replay; invalidated = []
    def drift(state, **kwargs):
        result = replay(state, **kwargs)
        rows[0]['_synthetic_people_context']['revision'] += 1
        return result
    owner.editor = replace(owner.editor, replay=drift, invalidate=lambda: invalidated.append(True))
    result = commit(owner, events, plan)
    assert not result['success'] and result['outcome_unknown']
    assert result['torso_review_ack'] == acks(plan) and result['module_scope'] == [T.OP]
    assert rows[1:] == before[1:] and invalidated and not owner.ledger
    assert plan['preflight_token'] not in owner.preflight.store.pending


def test_scoped_group_undo_redo_preserves_unrelated_image_and_body(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path); before = deepcopy(rows)
    result = commit(owner, events, preflight(owner, events)); assert result['success']
    bid = result['batch_id']
    for index in (1, 2): rows[index]['state']['unrelated_visual_edit'] = f'later-{index}'
    restore_group(owner, {'action': 'undo', 'batch_id': bid})
    assert owner.ledger[bid]['undone']
    for index in (1, 2):
        assert T.params_of(rows[index]['state']) == T.params_of(before[index]['state'])
        assert protected_body(rows[index]['state']) == protected_body(before[index]['state'])
        assert rows[index]['state']['unrelated_visual_edit'] == f'later-{index}'
    restore_group(owner, {'action': 'redo', 'batch_id': bid})
    assert not owner.ledger[bid]['undone']
    assert all(T.params_of(rows[i]['state'])['amount'] == .65 for i in (1, 2))


def test_group_history_requires_actual_face_review_for_parked_targets(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path)
    result = commit(owner, events, preflight(owner, events)); bid = result['batch_id']
    rows[1]['_synthetic_people_context']['association_revision'] += 1
    before = deepcopy(rows)
    with pytest.raises(ValueError): restore_group(owner, {'action': 'undo', 'batch_id': bid})
    assert rows == before and not owner.ledger[bid]['undone']


def test_group_history_dependency_edit_conflicts_all_targets(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path)
    result = commit(owner, events, preflight(owner, events)); bid = result['batch_id']
    bank = D.bank(rows[1]['state']); body = next(iter(bank['bodies'].values()))
    body['operations'][W.OPERATION_ID]['enabled'] = False
    rows[1]['state'][D.KEY] = P.pack(bank); before = deepcopy(rows)
    with pytest.raises(ValueError): restore_group(owner, {'action': 'undo', 'batch_id': bid})
    assert rows == before and not owner.ledger[bid]['undone']


def test_group_replay_drift_and_failed_rollback_invalidate_without_parked_write(tmp_path):
    owner, rows, current, events, _, _ = fixture(tmp_path)
    result = commit(owner, events, preflight(owner, events)); bid = result['batch_id']; current[0] = 1
    parked = deepcopy(rows[2]); replay = owner.editor.replay; invalidated = []
    def drift(state, **kwargs):
        result = replay(state, **kwargs)
        rows[1]['_synthetic_people_context']['revision'] += 1
        return result
    owner.editor = replace(owner.editor, replay=drift, invalidate=lambda: invalidated.append(True))
    with pytest.raises(ValueError): restore_group(owner, {'action': 'undo', 'batch_id': bid})
    assert invalidated and rows[2] == parked and not owner.ledger[bid]['undone']


def test_corrupt_saved_bank_identity_cannot_authorize_history(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path)
    result = commit(owner, events, preflight(owner, events)); saved = owner.ledger[result['batch_id']]['targets']['1']
    saved['torso_review']['candidate_bank_sha256'] = 'f' * 64
    with pytest.raises(ValueError): verify_history_source(rows[1], saved, [T.OP], saved['before'])


def test_group_history_rejects_new_foreign_people_context_even_with_own_face_retained(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path)
    result = commit(owner, events, preflight(owner, events)); bid = result['batch_id']
    # Own associated face and support remain identical, but the canonical people
    # context is no longer the one whose complete target render was approved.
    rows[1]['_synthetic_people_context']['persons']['new-foreign-person'] = {'anonymous': True}
    before = deepcopy(rows)
    with pytest.raises(ValueError): restore_group(owner, {'action': 'undo', 'batch_id': bid})
    assert rows == before and not owner.ledger[bid]['undone']


def test_ninth_target_is_refused_without_omission_or_preview(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    while len(rows) < 10: rows.append(deepcopy(rows[1]))
    before = deepcopy(rows)
    owner.handle_command({'action': 'preflight', 'docs': list(range(1, 10)),
        'module_scope': [T.OP], 'request_id': 'over-bound'})
    assert not events[-1]['success'] and 'eight' in events[-1]['error']
    assert rows == before and not replays and not owner.preflight.store.pending


@pytest.mark.parametrize('kind', ['missing', 'foreign-source', 'wrong-params', 'oversized'])
def test_store_refuses_unowned_or_missing_compact_torso_proof(tmp_path, kind):
    owner, _, _, events, _, _ = fixture(tmp_path); public = preflight(owner, events)
    plan = owner.preflight.store.pending[public['preflight_token']]
    targets = list(plan.targets); target = targets[0]
    value = json.loads(target.torso_json)
    if kind == 'missing': target = replace(target, torso_json=None)
    elif kind == 'foreign-source': target = replace(target, source_proof_json=plan.source_proof_json)
    elif kind == 'wrong-params':
        value['parameters']['amount'] = -.8
        target = replace(target, torso_json=STORE.canonical(value))
    else: target = replace(target, torso_json='x' * 16385)
    targets[0] = target
    with pytest.raises(ValueError):
        owner.preflight.store.create(plan.workspace, plan.source_id, plan.source_revision, plan.source_path,
            plan.modules, plan.params(), plan.policy, targets, plan.rejected(),
            source_proof=json.loads(plan.source_proof_json))


def test_non_torso_token_rejects_unrequested_torso_ack(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path)
    owner.handle_command({'action': 'preflight', 'docs': [1], 'module_scope': [SC.OP_EXPOSURE], 'request_id': 'ordinary'})
    plan = events[-1]; before = deepcopy(rows)
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'torso_review_ack': [], 'request_id': 'foreign-ack'})
    assert not events[-1]['success'] and rows == before
    assert plan['preflight_token'] in owner.preflight.store.pending


def test_recheck_conflict_keeps_entire_batch_unwritten_and_retains_ack(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    plan = preflight(owner, events, policy='recheck')
    rows[1]['state']['unrelated_visual_edit'] = 'changed'; before = deepcopy(rows)
    result = commit(owner, events, plan)
    assert not result['success'] and not result['outcome_unknown']
    assert result['module_scope'] == [T.OP] and result['torso_review_ack'] == acks(plan)
    assert rows == before and not replays and not owner.ledger


def test_claim_alone_is_an_exact_terminal_unknown_retry_fence(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); public = preflight(owner, events)
    plan = owner.preflight.store.pending[public['preflight_token']]
    proof = acks(public); owner.preflight.store.claim(plan, torso_review_ack=proof)
    before = deepcopy(rows)
    result = commit(owner, events, public)
    assert not result['success'] and result['outcome_unknown'] and result['replayed']
    assert result['module_scope'] == [T.OP] and result['torso_review_ack'] == proof
    assert rows == before and not replays and not owner.ledger


def test_group_history_missing_face_verification_port_fails_closed(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    result = commit(owner, events, preflight(owner, events)); before = deepcopy(rows)
    owner.editor = replace(owner.editor, torso_history_identity=None)
    with pytest.raises(ValueError): restore_group(owner, {'action': 'undo', 'batch_id': result['batch_id']})
    assert rows == before and not replays and not owner.ledger[result['batch_id']]['undone']


def test_live_target_switch_refuses_rollback_before_writing_new_active_document(tmp_path):
    owner, rows, current, events, replays, _ = fixture(tmp_path)
    plan = preflight(owner, events, (0, 1, 2)); before = deepcopy(rows)
    replay = owner.editor.replay; invalidated = []
    def switch_after_forward(state, **kwargs):
        replay(state, **kwargs)
        current[0] = 1
        raise ValueError('Synthetic target switch while the forward renderer failed')
    owner.editor = replace(owner.editor, replay=switch_after_forward, invalidate=lambda: invalidated.append(True))
    result = commit(owner, events, plan)
    assert not result['success'] and result['outcome_unknown'] and invalidated
    assert len(replays) == 1 and rows[1:] == before[1:] and not owner.ledger
    assert all('rollback' not in call['replayed_for'] for call in replays)


def test_group_target_switch_refuses_rollback_before_writing_new_active_document(tmp_path):
    owner, rows, current, events, replays, _ = fixture(tmp_path)
    result = commit(owner, events, preflight(owner, events)); bid = result['batch_id']; current[0] = 1
    parked = deepcopy(rows[2]); replay = owner.editor.replay; invalidated = []
    def switch_after_forward(state, **kwargs):
        replay(state, **kwargs)
        current[0] = 2
        raise ValueError('Synthetic history target switch while the renderer failed')
    owner.editor = replace(owner.editor, replay=switch_after_forward, invalidate=lambda: invalidated.append(True))
    with pytest.raises(ValueError): restore_group(owner, {'action': 'undo', 'batch_id': bid})
    assert invalidated and rows[2] == parked and not owner.ledger[bid]['undone']
    assert len(replays) == 1 and all('rollback' not in call['replayed_for'] for call in replays)


@pytest.mark.parametrize('kind', ['missing-body', 'unreviewed-body'])
def test_ineligible_target_is_explicitly_blocked_while_reviewed_target_can_commit(tmp_path, kind):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    if kind == 'missing-body': rows[1]['state'].pop(D.KEY)
    else:
        bank = D.bank(rows[1]['state']); body = next(iter(bank['bodies'].values()))
        body['operations'][T.OP]['review'] = None
        rows[1]['state'][D.KEY] = P.pack(bank)
    before = deepcopy(rows[1]); plan = preflight(owner, events)
    assert plan['ok'] == 1 and plan['blocked'] == 1
    blocked = plan['targets'][0]
    assert blocked['blocked'] and blocked['before'] == {} and blocked['torso_transfer'] is None
    assert len(acks(plan)) == 1
    result = commit(owner, events, plan)
    assert result['success'] and result['targets'] == [2] and len(result['skipped']) == 1
    assert rows[1] == before and not replays
