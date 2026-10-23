"""AUTHORED / UNRUN: spill scalar preset/batch routing and frozen ownership.

No fixtures in this file were imported, collected or executed during authoring.
Source files and display-port payloads are synthetic byte identities, not decoded
photos or PNG evidence. Explicit synthetic visual ports exercise transaction
fences only: parked targets are not claimed as rendered. Real encoding is tested
separately against a mocked full renderer in test_spill_transfer_review_unrun.py.
Numerical spill quality, native execution and visual acceptance remain UNRUN.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import base64
import json
import struct

import pytest

from test_batch_sync_controller import fixture as base_fixture
from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import id_background_state as I
from lumaretouch_engine import id_background_support as SUPPORT
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import optics_auto_scope as OA
from lumaretouch_engine import preset_controller as P
from lumaretouch_engine import scope as SC
from lumaretouch_engine import spill_removal_scope as SP
from lumaretouch_engine import spill_removal_state as S
from lumaretouch_engine import spill_transfer_review as REVIEW
from lumaretouch_engine.batch_group_history import restore_group
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.local_grade_preset_review import PresetReviews
from lumaretouch_engine.optics_candidate_identity import fingerprint
from lumaretouch_engine.ops.geometry import out_size


def synthetic_visual_record(row, before, candidate, document_id, revision):
    """Transaction-only mock. These display bytes deliberately are not photos."""
    proof = SOURCE.row_proof({**row, 'state': before})
    source = proof['creative_source']
    size = [source['width'], source['height']] if source else [row['src_w'], row['src_h']]
    before_size = list(out_size(*size, before['_crop_rect'], before['_crop_rotation']))
    after_size = list(out_size(*size, candidate['_crop_rect'], candidate['_crop_rotation']))
    people = fingerprint(row.get('_synthetic_people_context', {}))
    record = {'version': 1, 'document_id': document_id, 'revision': str(revision),
        'source_proof': proof, 'before_sha256': fingerprint(before),
        'candidate_sha256': fingerprint(candidate), 'before_people_sha256': people,
        'candidate_people_sha256': people, 'source_size': size,
        'before_output_size': before_size, 'after_output_size': after_size,
        'parameters': SP.params_of(candidate)}
    public_images = {}
    for side, state, output in (('before', before, before_size), ('after', candidate, after_size)):
        # Identical states produce identical display identities, including a
        # rollback's before/before pair. This remains a non-image port mock.
        payload = ('SYNTHETIC TRANSACTION PORT, NOT A PNG: ' + document_id + ':' + fingerprint(state)).encode()
        scale = min(1., REVIEW.PREVIEW_EDGE / max(output))
        image = {'mime': 'image/png', 'width': max(1, round(output[0] * scale)),
            'height': max(1, round(output[1] * scale)), 'sha256': sha256(payload).hexdigest()}
        record[side] = image
        public_images[side] = {**image, 'base64': base64.b64encode(payload).decode('ascii')}
    compact = REVIEW.checked(record)
    return compact, {**deepcopy(compact), **public_images}


def synthetic_verify_spill(row, before, candidate, document_id, revision, record):
    expected, _ = synthetic_visual_record(row, before, candidate, document_id, revision)
    if REVIEW.checked(record) != expected:
        raise ValueError('Synthetic transaction target source, people or full edits changed')
    return expected


def acknowledgment(transfer):
    return {'document_id': transfer['document_id'], 'revision': transfer['revision'],
        'before_sha256': transfer['before']['sha256'], 'after_sha256': transfer['after']['sha256']}


def review_acks(plan):
    return [acknowledgment(target['spill_transfer']) for target in plan['targets'] if not target['blocked']]


def preset_review(reviews, row, document_id='loaded', revision='7'):
    return reviews.prepare(stored(), row['state'], row, document_id, revision, None,
        prepare_spill=synthetic_visual_record, verify_spill=synthetic_verify_spill)


def owned_id(source):
    mask = M.empty(); mask['source'] = deepcopy(source)
    mask['recipe']['objects'] = [{'id': 'owned', 'name': 'Owned target range',
        'enabled': True, 'kind': 'brush', 'operation': 'add', 'opacity': 1.,
        'feather': 0., 'points': [[.5, .5]], 'axes': [[.1, 0.], [0., .1]]}]
    value = I.empty(); value.update(enabled=True, source=deepcopy(source))
    value['support']['subject'] = {'version': 1, 'category': 'subject',
        'reviewed': True, 'mask': mask, 'recipe_sha256': SUPPORT.digest(mask)}
    return I.check(value)


def fixture(tmp_path):
    owner, rows, current, events, replays, remember = base_fixture()
    for index, row in enumerate(rows):
        path = tmp_path / f'original-{index}.bin'
        path.write_bytes(f'synthetic-original-source-{index}'.encode())
        row.update(path=str(path), src_w=32, src_h=24)
        # Spill-only transaction fixtures do not exercise native WB/exposure.
        row['state'].update(_crop_rect=[0., 0., 1., 1.], _crop_rotation=0., _exposure=(0.,) * 7)
        source = SOURCE.binding(row['state'], row['path'], (32, 24))
        row['state']['_id_background'] = owned_id(source)
        row['state']['_id_background_bundle'] = None
    rows[0]['state']['_id_background'] = I.with_spill(rows[0]['state']['_id_background'],
        {**S.neutral(), 'enabled': True, 'strength': 81.})
    owner.editor = replace(owner.editor, prepare_spill=synthetic_visual_record, verify_spill=synthetic_verify_spill)
    owner.preflight.ports = replace(owner.preflight.ports,
        prepare_spill=synthetic_visual_record, verify_spill=synthetic_verify_spill)
    return owner, rows, current, events, replays, remember


def review(owner, events, docs=(1, 2), policy='skip_and_report'):
    owner.handle_command({'action': 'preflight', 'docs': list(docs), 'module_scope': [SP.OP],
        'conflict_policy': policy, 'request_id': 'spill-review'})
    result = events[-1]
    assert result['event'] == 'batch_result' and result['success']
    return result


def commit(owner, events, plan):
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'request_id': 'spill-commit', 'spill_review_ack': review_acks(plan)})
    return events[-1]


def stored():
    return {'id': 'spill', 'name': 'Spill scalars', 'kind': 'custom',
        'modules': {SP.OP: {'enabled': True, 'strength': 81.}}}


def test_batch_freezes_actual_source_and_every_targets_complete_id_dependencies(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    before = deepcopy([row['state'] for row in rows]); plan = review(owner, events)
    assert plan['source_snapshot']['source_proof'] == SOURCE.row_proof(rows[0])
    for target in plan['targets']:
        row = rows[target['index']]
        assert target['source_proof'] == SOURCE.row_proof(row)
        assert target['source_proof'] != plan['source_snapshot']['source_proof']
        assert target['before'] == {SP.OP: {'target_recipe_key': SP.undo_key(row['state'])}}
    assert plan['applies'] == stored()['modules']
    assert [row['state'] for row in rows] == before and not replays and not owner.ledger


def test_original_and_derived_targets_keep_separate_effective_source_proofs(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    value = rows[2]['state']
    value['_creative_base'] = make_asset('rgba', 32, 24, struct.pack('<4f', .2, .3, .4, 1.) * (32 * 24))
    value['_id_background'] = owned_id(SOURCE.binding(value))
    plan = review(owner, events)
    assert plan['ok'] == 2 and plan['targets'][0]['source_proof']['creative_source'] is None
    assert plan['targets'][1]['source_proof']['creative_source'] == SOURCE.binding(value)
    before_source = value['_creative_base']; result = commit(owner, events, plan)
    assert result['success'] and not replays
    assert rows[2]['state']['_creative_base'] is before_source
    assert rows[2]['state']['_id_background']['source'] == SOURCE.binding(value)


@pytest.mark.parametrize('mutation', ['parent', 'source-file', 'missing-target', 'inactive'])
def test_changed_or_missing_target_is_not_silently_replaced_or_enabled(tmp_path, mutation):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events)
    first = rows[1]
    if mutation == 'parent': first['state']['_id_background']['edge'] = 2.
    elif mutation == 'source-file': (tmp_path / 'original-1.bin').write_bytes(b'replaced-source')
    elif mutation == 'missing-target': rows.pop(1)
    else: first['state']['_id_background']['enabled'] = False
    before = deepcopy(first['state']); result = commit(owner, events, plan)
    assert result['success'] and len(result['targets']) == 1 and result['skipped']
    assert first['state'] == before and not replays


def test_inactive_target_is_blocked_in_initial_review_not_enabled_by_scalars(tmp_path):
    owner, rows, _, events, _, _ = fixture(tmp_path)
    rows[1]['state']['_id_background']['enabled'] = False
    plan = review(owner, events)
    assert plan['ok'] == 1 and plan['targets'][0]['blocked']
    assert not rows[1]['state']['_id_background']['enabled']


def test_frozen_source_edit_does_not_replace_reviewed_parameters(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events, (1,))
    rows[0]['state']['_id_background']['spill']['strength'] = 20.
    owner.versions.advance(rows[0]); result = commit(owner, events, plan)
    assert result['success'] and result['source_changed_since_preflight']
    assert I.spill_of(rows[1]['state']['_id_background'])['strength'] == 81. and not replays


def test_unreviewed_spill_commit_is_rejected_before_target_writes(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); before = deepcopy(rows)
    owner.handle_command({'action': 'commit', 'docs': [1], 'module_scope': [SP.OP], 'request_id': 'direct'})
    assert not events[-1]['success'] and rows == before and not replays and not owner.ledger


def test_active_commit_is_strict_and_parked_fields_wait_for_activation_or_export(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events, (0, 1, 2))
    result = commit(owner, events, plan)
    assert result['success'] and result['targets'] == [0, 1, 2]
    assert len(replays) == 1 and replays[0]['strict_local'] is True
    assert len(rows[1]['undo']) == len(rows[2]['undo']) == 1


@pytest.mark.parametrize('change', ['parent', 'people', 'unscoped'])
def test_live_dependency_mutation_rolls_back_before_any_parked_write(tmp_path, change):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events, (0, 1, 2))
    before = deepcopy([row['state'] for row in rows]); actual = owner.editor.replay; invalidated = []
    def changed(candidate, **kwargs):
        frame = actual(candidate, **kwargs)
        if kwargs['replayed_for'].startswith('batch:'):
            if change == 'parent': rows[0]['state']['_id_background']['edge'] = 3.
            elif change == 'people': rows[0]['_synthetic_people_context'] = {'person': 'changed-during-replay'}
            else: rows[0]['state']['untouched'] = 'changed full target during replay'
        return frame
    owner.editor = replace(owner.editor, replay=changed, invalidate=lambda: invalidated.append(True))
    result = commit(owner, events, plan)
    assert not result['success'] and [row['state'] for row in rows] == before
    assert not rows[1]['undo'] and not rows[2]['undo'] and not owner.ledger
    assert replays[0]['strict_local'] is True
    if change == 'people':
        assert rows[0]['_synthetic_people_context'] == {'person': 'changed-during-replay'}
        assert invalidated == [True]
        assert any(event['event'] == 'engine_warn' and 'rollback failed' in event['warn'] for event in events)
    else:
        assert not invalidated and not any(event['event'] == 'engine_warn' for event in events)


def test_group_undo_redo_is_strict_and_restores_exact_legacy_target_not_source(tmp_path):
    owner, rows, current, events, replays, _ = fixture(tmp_path)
    before = deepcopy(rows[1]['state']); result = commit(owner, events, review(owner, events, (1,)))
    assert result['success']; bid = result['batch_id']; after = deepcopy(rows[1]['state'])
    rows[1]['state']['untouched'] = 'later unrelated edit'; current[0] = 1
    restore_group(owner, {'action': 'undo', 'batch_id': bid})
    assert rows[1]['state']['_id_background'] == before['_id_background']
    assert rows[1]['state']['untouched'] == 'later unrelated edit'
    assert replays[-1]['strict_local'] is True
    restore_group(owner, {'action': 'redo', 'batch_id': bid})
    assert rows[1]['state']['_id_background'] == after['_id_background']
    assert rows[1]['state']['_id_background']['source'] != rows[0]['state']['_id_background']['source']
    assert rows[1]['state']['untouched'] == 'later unrelated edit' and replays[-1]['strict_local'] is True


@pytest.mark.parametrize('change', ['source', 'support', 'parent', 'people', 'unscoped'])
def test_preset_review_claim_rechecks_source_and_full_target_dependencies(tmp_path, change):
    _, rows, _, _, _, _ = fixture(tmp_path); row = rows[1]; state = row['state']; reviews = PresetReviews()
    plan = preset_review(reviews, row)
    assert plan['source_proof'] == SOURCE.row_proof(row)
    if change == 'source': (tmp_path / 'original-1.bin').write_bytes(b'changed-original')
    elif change == 'support':
        support = state['_id_background']['support']['subject']; support['mask']['recipe']['objects'][0]['points'] = [[.6, .5]]
        support['recipe_sha256'] = SUPPORT.digest(support['mask'])
    elif change == 'parent': state['_id_background']['edge'] = 2.
    elif change == 'people': row['_synthetic_people_context'] = {'person': 'different-owner'}
    else: state['untouched'] = 'unscoped but visible target edit'
    with pytest.raises(ValueError):
        reviews.claim(plan['preflight_token'], 'spill', state, row, 'loaded', '7',
            verify_spill=synthetic_verify_spill, spill_review_ack=[acknowledgment(plan['spill_transfer'])])
    assert plan['preflight_token'] in reviews.pending


def preset_owner(batch, row, events, replays):
    def replay(value, **kwargs):
        replays.append(kwargs); row['state'] = deepcopy(value)
        return {'event': 'frame', 'render_ms': 1}
    return P.PresetController(P.PresetPorts(lambda _: None, lambda: 'loaded',
        lambda: deepcopy(row['state']), replay, lambda: ('ok', ''), lambda: {'document_id': 'loaded'},
        lambda: None, target_row=lambda: row, revision=lambda: str(batch.versions.version(row).revision),
        advance=lambda: batch.versions.advance(row), prepare_spill=synthetic_visual_record,
        verify_spill=synthetic_verify_spill), events.append)


def test_preset_apply_requires_token_and_replays_strictly_with_original_proof(tmp_path, monkeypatch):
    batch, rows, _, events, replays, _ = fixture(tmp_path); owner = preset_owner(batch, rows[1], events, replays)
    monkeypatch.setattr(P.PS, 'find', lambda _: stored())
    with pytest.raises(ValueError): owner.apply({'id': 'spill'})
    assert not replays
    plan = preset_review(owner.reviews, rows[1], revision=owner.ports.revision())
    result = owner.apply({'id': 'spill', 'preflight_token': plan['preflight_token'],
        'spill_review_ack': [acknowledgment(plan['spill_transfer'])]})
    assert result['source_proof'] == SOURCE.row_proof(rows[1]) and replays[-1]['strict_local'] is True


def test_default_save_does_not_select_both_full_id_and_scalar_spill(tmp_path, monkeypatch):
    batch, rows, _, events, replays, _ = fixture(tmp_path); owner = preset_owner(batch, rows[0], events, replays)
    monkeypatch.setattr(SC, 'transferable_ops', lambda: [SC.ID_BACKGROUND.OP, SP.OP, SC.OP_EXPOSURE])
    saved = []
    monkeypatch.setattr(P.PS, 'save', lambda value, **kwargs: saved.append(value) or '/not-written.json')
    result = owner.save({'id': 'default', 'name': 'Default selection'})
    assert SP.OP not in result['module_scope'] and SC.ID_BACKGROUND.OP in result['module_scope']
    assert len(saved) == 1 and not replays


@pytest.mark.parametrize('missing', ['prepare_spill', 'verify_spill'])
def test_batch_without_visual_port_blocks_every_target_without_writes(tmp_path, missing):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    owner.preflight.ports = replace(owner.preflight.ports, **{missing: None})
    before = deepcopy(rows); plan = review(owner, events)
    assert plan['ok'] == 0 and plan['blocked'] == 2
    assert all(target['blocked'] and target['spill_transfer'] is None for target in plan['targets'])
    assert rows == before and not replays and not owner.ledger


@pytest.mark.parametrize('invalid', ['missing', 'boolean', 'partial', 'swapped', 'duplicate', 'hash', 'revision'])
def test_batch_requires_every_exact_target_image_ack_before_any_write(tmp_path, invalid):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events)
    before = deepcopy(rows); acks = review_acks(plan)
    if invalid == 'boolean': acks = True
    elif invalid == 'partial': acks.pop()
    elif invalid == 'swapped': acks.reverse()
    elif invalid == 'duplicate': acks[1] = deepcopy(acks[0])
    elif invalid == 'hash': acks[0]['after_sha256'] = '0' * 64
    elif invalid == 'revision': acks[0]['revision'] = str(int(acks[0]['revision']) + 1)
    command = {'action': 'commit', 'preflight_token': plan['preflight_token'], 'request_id': 'bad-spill-ack'}
    if invalid != 'missing': command['spill_review_ack'] = acks
    owner.handle_command(command)
    assert not events[-1]['success'] and rows == before and not replays and not owner.ledger


@pytest.mark.parametrize('change', ['people', 'unscoped'])
def test_batch_full_target_review_rejects_changes_outside_scalar_scope(tmp_path, change):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events)
    if change == 'people': rows[1]['_synthetic_people_context'] = {'person': 'new-ownership'}
    else: rows[1]['state']['untouched'] = 'changed full-target appearance'
    before = deepcopy(rows[1]); result = commit(owner, events, plan)
    assert result['success'] and result['targets'] == [2] and result['skipped']
    assert rows[1] == before and not replays


def test_batch_rejects_ninth_target_without_omitting_it_or_preparing_images(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path)
    for index in range(3, 9):
        row = deepcopy(rows[1]); row.pop('document_id', None)
        row['path'] = str(tmp_path / f'never-decoded-{index}.bin')
        rows.append(row)
    calls = []
    owner.preflight.ports = replace(owner.preflight.ports,
        prepare_spill=lambda *args: calls.append(args))
    before = deepcopy(rows)
    owner.handle_command({'action': 'preflight', 'docs': list(range(9)),
        'module_scope': [SP.OP], 'request_id': 'too-many-spill-targets'})
    assert not events[-1]['success'] and 'eight' in events[-1]['error']
    assert rows == before and not calls and not replays and not owner.preflight.store.pending


def test_spill_histories_and_frozen_plans_keep_compact_proofs_not_display_bytes(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events)
    frozen = owner.preflight.store.pending[plan['preflight_token']]
    for target in frozen.targets:
        compact = json.loads(target.spill_json)
        assert REVIEW.checked(compact) == compact and 'base64' not in target.spill_json
    assert all('base64' in target['spill_transfer']['before'] for target in plan['targets'])
    result = commit(owner, events, plan); assert result['success']
    for target in owner.ledger[result['batch_id']]['targets'].values():
        assert REVIEW.checked(target['spill_review']) == target['spill_review']
        assert 'base64' not in json.dumps(target['spill_review'])
    assert 'base64' not in repr([row['undo'] for row in rows]) and not replays


def test_completed_batch_token_replay_requires_its_original_ack_without_reexecution(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events)
    result = commit(owner, events, plan); assert result['success']; before = deepcopy(rows)
    repeated = commit(owner, events, plan)
    assert repeated['success'] and repeated['replayed'] and rows == before and not replays
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'request_id': 'missing-replay-ack'})
    assert not events[-1]['success'] and rows == before and len(owner.ledger) == 1


@pytest.mark.parametrize('missing', ['prepare_spill', 'verify_spill'])
def test_preset_without_visual_port_never_mints_review_token(tmp_path, missing):
    _, rows, _, _, _, _ = fixture(tmp_path); reviews = PresetReviews()
    ports = {'prepare_spill': synthetic_visual_record, 'verify_spill': synthetic_verify_spill}
    ports[missing] = None
    before = deepcopy(rows[1])
    with pytest.raises(ValueError):
        reviews.prepare(stored(), rows[1]['state'], rows[1], 'loaded', '7', None, **ports)
    assert rows[1] == before and not reviews.pending


@pytest.mark.parametrize('invalid', ['missing', 'boolean', 'wrong-target', 'swapped-pair', 'duplicate', 'overbudget'])
def test_preset_missing_or_mismatched_image_ack_never_replays(tmp_path, invalid):
    batch, rows, _, events, replays, _ = fixture(tmp_path)
    owner = preset_owner(batch, rows[1], events, replays)
    plan = preset_review(owner.reviews, rows[1], revision=owner.ports.revision())
    before = deepcopy(rows[1]); acks = [acknowledgment(plan['spill_transfer'])]
    if invalid == 'boolean': acks = True
    elif invalid == 'wrong-target': acks[0]['document_id'] = 'another-target'
    elif invalid == 'swapped-pair':
        acks[0]['before_sha256'], acks[0]['after_sha256'] = acks[0]['after_sha256'], acks[0]['before_sha256']
    elif invalid == 'duplicate': acks.append(deepcopy(acks[0]))
    elif invalid == 'overbudget': acks *= REVIEW.MAX_TARGETS + 1
    command = {'id': 'spill', 'preflight_token': plan['preflight_token']}
    if invalid != 'missing': command['spill_review_ack'] = acks
    with pytest.raises(ValueError): owner.apply(command)
    assert rows[1] == before and not replays and plan['preflight_token'] in owner.reviews.pending


def test_preset_pending_record_keeps_compact_proof_not_public_images(tmp_path):
    _, rows, _, _, _, _ = fixture(tmp_path); reviews = PresetReviews()
    plan = preset_review(reviews, rows[1]); saved = reviews.pending[plan['preflight_token']]
    assert 'base64' in plan['spill_transfer']['before']
    assert REVIEW.checked(saved['spill']) == saved['spill'] and 'base64' not in json.dumps(saved)


@pytest.mark.parametrize('change', ['people', 'unscoped'])
def test_preset_replay_rechecks_full_target_before_publishing_success(tmp_path, change):
    batch, rows, _, events, replays, _ = fixture(tmp_path); row = rows[1]
    owner = preset_owner(batch, row, events, replays)
    plan = preset_review(owner.reviews, row, revision=owner.ports.revision())
    before = deepcopy(row['state']); original = owner.ports.replay; invalidated = []

    def changed(candidate, **kwargs):
        frame = original(candidate, **kwargs)
        if kwargs['replayed_for'] == 'preset:spill':
            if change == 'people': row['_synthetic_people_context'] = {'person': 'changed-during-replay'}
            else: row['state']['untouched'] = 'changed full target during replay'
        return frame

    owner.ports = replace(owner.ports, replay=changed, invalidate=lambda: invalidated.append(True))
    with pytest.raises(P.PresetApplyError) as raised:
        owner.apply({'id': 'spill', 'preflight_token': plan['preflight_token'],
            'spill_review_ack': [acknowledgment(plan['spill_transfer'])]})
    assert row['state'] == before and replays[0]['strict_local'] is True
    assert not any(event['event'] == 'preset_applied' for event in events)
    if change == 'people':
        assert row['_synthetic_people_context'] == {'person': 'changed-during-replay'}
        assert not raised.value.rolled_back and raised.value.requires_reload and invalidated == [True]
    else:
        assert raised.value.rolled_back and not raised.value.requires_reload and not invalidated


@pytest.mark.parametrize('change', ['enable-spill', 'inactive-spill-strength', 'active-parent-edge', 'active-parent-disable'])
def test_whole_id_install_cannot_bypass_dedicated_target_spill_review(tmp_path, change):
    _, rows, _, _, _, _ = fixture(tmp_path)
    state = deepcopy(rows[0 if change.startswith('active') else 1]['state'])
    params = SC.ID_BACKGROUND.params_of(state)
    if change in ('enable-spill', 'inactive-spill-strength'):
        value = I.with_spill(state['_id_background'], {**S.neutral(), 'enabled': change == 'enable-spill', 'strength': 45.})
        params = {'recipe': I.portable(value)}
    elif change == 'active-parent-edge': params['recipe']['edge'] = 3.
    else: params['recipe']['enabled'] = False
    before = deepcopy(state)
    with pytest.raises(ValueError): SC.ID_BACKGROUND.install(state, params)
    assert state == before
