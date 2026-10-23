"""AUTHORED / UNRUN: scalar shadow target review, retry and owned-history routes.

Synthetic transaction ports are not actual PNGs, photo evidence or a renderer.
No product imports, test collection or execution occurred during authoring.
"""
from copy import deepcopy
from dataclasses import replace
import pytest
from test_spill_transfer_wiring_unrun import fixture as spill_fixture, synthetic_visual_record as spill_record
from lumaretouch_engine import id_background_state as I, original_shadow_state as O
from lumaretouch_engine import original_shadow_scope as SH, original_shadow_transfer_review as REVIEW
from lumaretouch_engine.local_grade_preset_review import PresetReviews
from lumaretouch_engine.optics_candidate_identity import fingerprint
from lumaretouch_engine.batch_group_history import restore_group


def record(row, before, candidate, document_id, revision):
    compact, public = spill_record(row, before, candidate, document_id, revision)
    compact['parameters'] = SH.params_of(candidate)
    public['parameters'] = deepcopy(compact['parameters'])
    return REVIEW.checked(compact), public


def verify(row, before, candidate, document_id, revision, proof):
    expected, _ = record(row, before, candidate, document_id, revision)
    if REVIEW.checked(proof) != expected:raise ValueError('target full state, people or source changed')


def history_identity(row, state, document_id, revision):
    return {'document_id': document_id, 'revision': str(revision),
            'candidate_sha256': fingerprint(state),
            'people_sha256': fingerprint(row.get('_synthetic_people_context', {}))}


def fixture(tmp_path):
    owner, rows, current, events, replays, remember = spill_fixture(tmp_path)
    for index, row in enumerate(rows):
        value = row['state']['_id_background']
        bindings = {}
        for role in ('lit_floor', 'retention'):
            mask = deepcopy(value['support']['subject']['mask'])
            mask['recipe']['objects'][0]['id'] = f'{role}-{index}'
            bindings[role] = {'version': 1, 'reviewed': True, 'mask': mask, 'recipe_sha256': O.digest(mask)}
        row['state']['_id_background'] = I.with_original_shadow(value,
            {**O.neutral(), **bindings, 'uniform_floor_confirmed': True,
             'enabled': index == 0, 'strength': 75., 'blend': 'softlight'})
    owner.editor = replace(owner.editor, prepare_shadow=record, verify_shadow=verify, history_identity=history_identity)
    owner.preflight.ports = replace(owner.preflight.ports, prepare_shadow=record, verify_shadow=verify)
    return owner, rows, current, events, replays, remember


def preflight(owner, events, docs=(1, 2)):
    owner.handle_command({'action': 'preflight', 'docs': list(docs), 'module_scope': [SH.OP],
        'conflict_policy': 'skip_and_report', 'request_id': 'shadow-review'})
    result = events[-1]
    assert result['success'], result
    return result


def acks(plan):
    return [{'document_id': t['document_id'], 'revision': t['revision'],
        'before_sha256': t['shadow_transfer']['before']['sha256'],
        'after_sha256': t['shadow_transfer']['after']['sha256']}
        for t in plan['targets'] if not t['blocked']]


def commit(owner, events, plan, acknowledgment):
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'request_id': 'shadow-commit', 'shadow_review_ack': acknowledgment})
    return events[-1]


def test_each_target_retains_samples_and_spill_and_requires_review(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path)
    before = [deepcopy(r['state']) for r in rows]
    plan = preflight(owner, events)
    assert all(t['shadow_transfer'] is not None for t in plan['targets'] if not t['blocked'])
    bad = commit(owner, events, plan, [])
    assert not bad['success'] and [r['state'] for r in rows] == before
    good = commit(owner, events, plan, acks(plan));assert good['success'], good
    for index in (1, 2):
        value = I.original_shadow_of(rows[index]['state']['_id_background'])
        old = I.original_shadow_of(before[index]['_id_background'])
        assert value['lit_floor'] == old['lit_floor'] and value['retention'] == old['retention']
        assert I.spill_of(rows[index]['state']['_id_background']) == I.spill_of(before[index]['_id_background'])
        assert SH.params_of(rows[index]['state']) == SH.params_of(before[0])


def test_changed_review_hash_does_not_reexecute_completed_token(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    plan = preflight(owner, events);proof = acks(plan)
    assert commit(owner, events, plan, proof)['success']
    before = deepcopy([r['state'] for r in rows]);count = len(replays)
    altered = deepcopy(proof);altered[0]['after_sha256'] = 'f' * 64
    assert not commit(owner, events, plan, altered)['success']
    assert [r['state'] for r in rows] == before and len(replays) == count


def test_target_sample_change_after_preflight_cannot_gain_source_samples(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path)
    plan = preflight(owner, events, (1,))
    value = I.original_shadow_of(rows[1]['state']['_id_background'])
    value['uniform_floor_confirmed'] = False
    rows[1]['state']['_id_background'] = I.with_original_shadow(rows[1]['state']['_id_background'], value)
    before = deepcopy(rows[1]['state'])
    result = commit(owner, events, plan, acks(plan))
    assert not result['success'] and rows[1]['state'] == before


def test_preset_claim_requires_target_hashes_without_consuming_bad_ack(tmp_path):
    _, rows, _, _, _, _ = fixture(tmp_path)
    row = rows[1];reviews = PresetReviews()
    preset = {'id': 'shadow', 'name': 'Shadow scalars', 'kind': 'custom',
              'modules': {SH.OP: {'enabled': True, 'strength': 75., 'blend': 'softlight'}}}
    view = reviews.prepare(preset, row['state'], row, 'target', '4', None,
                           prepare_shadow=record, verify_shadow=verify)
    token = view['preflight_token']
    with pytest.raises(ValueError):
        reviews.claim(token, 'shadow', row['state'], row, 'target', '4', verify_shadow=verify, shadow_review_ack=[])
    assert token in reviews.pending
    image = view['shadow_transfer']
    ack = [{'document_id': 'target', 'revision': '4', 'before_sha256': image['before']['sha256'], 'after_sha256': image['after']['sha256']}]
    result = reviews.claim(token, 'shadow', row['state'], row, 'target', '4', verify_shadow=verify, shadow_review_ack=ack)
    assert result['shadow']['parameters'] == preset['modules'][SH.OP]
    assert token not in reviews.pending


@pytest.mark.parametrize('field', ['spill_review_ack', 'shadow_review_ack'])
@pytest.mark.parametrize('action', ['state', 'undo', 'redo'])
def test_ack_on_noncommit_returns_after_rejection(tmp_path, field, action):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    before = deepcopy([row['state'] for row in rows])
    owner.handle_command({'action': action, 'request_id': 'bad-ack', field: []})
    assert events[-1]['event'] == 'batch_result' and not events[-1]['success']
    assert not any(event.get('event') == 'batch_state' for event in events)
    assert [row['state'] for row in rows] == before and not replays


def test_group_undo_detects_people_change_during_replay_and_failed_rollback(tmp_path):
    owner, rows, current, events, _, _ = fixture(tmp_path)
    plan = preflight(owner, events, (1,))
    assert commit(owner, events, plan, acks(plan))['success']
    bid = owner.summary()['last'];current[0] = 1
    original = owner.editor.replay;invalidated = []
    def changed(state, **kwargs):
        result = original(state, **kwargs)
        rows[1]['_synthetic_people_context'] = {'changed': True}
        return result
    owner.editor = replace(owner.editor, replay=changed, invalidate=lambda: invalidated.append(True))
    with pytest.raises(ValueError):restore_group(owner, {'action': 'undo', 'batch_id': bid})
    assert invalidated and owner.ledger[bid]['undone'] is False
