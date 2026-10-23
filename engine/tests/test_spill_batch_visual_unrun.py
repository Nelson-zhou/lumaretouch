"""AUTHORED / UNRUN: per-target batch spill image review and write fences.

Nothing in this file was imported, collected or executed during authoring.
Synthetic source bytes and a substituted complete renderer exercise orchestration
only. These fixtures are not photographic, native, GPU, export, performance or
visual-quality acceptance evidence. Actual full-source rendering remains UNRUN.
"""
from copy import deepcopy
from dataclasses import replace
import json
import struct

import numpy as np
import pytest

from test_batch_sync_controller import fixture as base_fixture
from test_spill_transfer_wiring_unrun import owned_id
from lumaretouch_engine import batch_preflight as STORE
from lumaretouch_engine import batch_preflight_controller as PLANNER
from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import id_background_state as ID
from lumaretouch_engine import optics_auto_scope as OA
from lumaretouch_engine import reference_color_scope as RC
from lumaretouch_engine import scope as SC
from lumaretouch_engine import spill_removal_scope as SP
from lumaretouch_engine import spill_removal_state as SPILL
from lumaretouch_engine import spill_transfer_review as REVIEW
from lumaretouch_engine import white_balance_recipe as WB
from lumaretouch_engine.batch_sync import verify_history_source
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.optics_candidate_identity import fingerprint
from lumaretouch_engine.ops.geometry import out_size


@pytest.fixture
def setup(tmp_path, monkeypatch):
    def create(count=3, derived=False):
        owner, rows, current, events, replays, remember = base_fixture()
        while len(rows) < count:
            rows.append({'path': 'not-yet-bound', 'state': deepcopy(rows[2]['state']),
                         'undo': [], 'redo': []})
        renders, checks, people = [], [], {}
        for index, row in enumerate(rows):
            path = tmp_path / f'target-{index}.bin'
            path.write_bytes(f'owned-original-target-{index}'.encode())
            row.update(path=str(path), src_w=32, src_h=24)
            row['state'].update(_crop_rect=[0., 0., 1., 1.], _crop_rotation=0.,
                                _target_mask=np.full((2, 3), index, np.float32))
            if derived and index == 2:
                row['state']['_creative_base'] = make_asset(
                    'rgba', 32, 24, struct.pack('<4f', .2, .3, .4, 1.) * (32 * 24))
            source = SOURCE.binding(row['state'], row['path'], (32, 24))
            row['state']['_id_background'] = owned_id(source)
            row['state']['_id_background_bundle'] = None
            version = owner.versions.version(row)
            people[version.document_id] = {'owner': f'person-{index}'}
        rows[0]['state']['_id_background'] = ID.with_spill(rows[0]['state']['_id_background'],
            {**SPILL.neutral(), 'enabled': True, 'strength': 65.})

        def identity(engine, row, state, document, revision):
            version = owner.versions.version(row)
            if (document, str(revision)) != (version.document_id, str(version.revision)):
                raise ValueError('Synthetic target identity/revision changed')
            proof = SOURCE.row_proof(row)
            SOURCE.verify_row({**row, 'state': state}, proof)
            return {'document_id': document, 'revision': str(revision), 'source_proof': proof,
                    'candidate_sha256': fingerprint(state),
                    'people_sha256': fingerprint(people[document])}, {}, {}

        def render(engine, row, state, document, revision):
            proof, _, _ = identity(engine, row, state, document, revision)
            size = [32, 24]
            output = list(out_size(*size, state['_crop_rect'], state['_crop_rotation']))
            renders.append((document, deepcopy(state)))
            spill = ID.spill_of(state['_id_background'])
            pixels = np.full((output[1], output[0], 3),
                             .2 + .1 * spill['enabled'] * spill['strength'] / 100., np.float32)
            return pixels, {**proof, 'source_size': size, 'output_size': output}

        def prepare(row, before, candidate, document, revision):
            return REVIEW.prepare(owner, row, before, candidate, document, revision)

        def verify(row, before, candidate, document, revision, record):
            checks.append((document, revision))
            return REVIEW.verify(owner, row, before, candidate, document, revision, record)

        monkeypatch.setattr(FULL, 'identity', identity)
        monkeypatch.setattr(FULL, 'render', render)
        # This fixture exercises review transactions, not a native WB build.
        monkeypatch.setattr(WB, 'prepare_state', lambda state: None)
        owner.editor = replace(owner.editor, prepare_spill=prepare, verify_spill=verify)
        owner.preflight.ports = replace(owner.preflight.ports, prepare_spill=prepare, verify_spill=verify)
        return owner, rows, current, events, replays, renders, checks, people
    return create


def review(data, docs=(1, 2), modules=None, policy='skip_and_report'):
    owner, _, _, events, *_ = data
    owner.handle_command({'action': 'preflight', 'docs': list(docs),
        'module_scope': modules or [SP.OP], 'conflict_policy': policy, 'request_id': 'visual-review'})
    result = events[-1]
    assert result['event'] == 'batch_result' and result['success'], result
    return result


def acknowledgment(plan):
    return [{'document_id': target['document_id'], 'revision': target['revision'],
             'before_sha256': target['spill_transfer']['before']['sha256'],
             'after_sha256': target['spill_transfer']['after']['sha256']}
            for target in plan['targets'] if not target['blocked']]


def commit(data, plan, **extra):
    owner, _, _, events, *_ = data
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'request_id': 'visual-commit', 'spill_review_ack': acknowledgment(plan), **extra})
    return events[-1]


def states(rows):
    return [fingerprint(row['state']) for row in rows]


def test_all_eight_targets_receive_two_actual_complete_display_views(setup):
    data = setup(count=8)
    owner, rows, _, _, replays, renders, _, _ = data
    before = states(rows)
    plan = review(data, range(8))
    assert plan['ok'] == 8 and len(plan['targets']) == 8 and len(renders) == 16
    assert states(rows) == before and not replays and not owner.ledger
    frozen = owner.preflight.store.get(plan['preflight_token'], owner.versions.workspace)
    for target, saved in zip(plan['targets'], frozen.targets):
        public = target['spill_transfer']; compact = json.loads(saved.spill_json)
        assert public['source_proof'] == SOURCE.row_proof(rows[target['index']])
        assert public['parameters'] == {'enabled': True, 'strength': 65.}
        assert REVIEW.checked(compact) == compact
        for side in ('before', 'after'):
            assert public[side]['mime'] == 'image/png' and len(public[side]['base64']) <= 200000
            assert max(public[side]['width'], public[side]['height']) <= 256
            assert 'base64' not in compact[side]
    assert all(not row['undo'] and not row['redo'] for row in rows)


def test_ninth_target_is_rejected_without_rendering_or_truncating(setup):
    data = setup(count=9)
    owner, rows, _, events, replays, renders, _, _ = data
    before = states(rows)
    owner.handle_command({'action': 'preflight', 'docs': list(range(9)),
        'module_scope': [SP.OP], 'request_id': 'too-many'})
    assert not events[-1]['success'] and 'eight' in events[-1]['error']
    assert states(rows) == before and not renders and not replays and not owner.preflight.store.pending


@pytest.mark.parametrize('invalid', ['missing', 'empty', 'boolean', 'hash', 'revision', 'duplicate', 'extra', 'reordered'])
def test_exact_acknowledgment_is_required_before_claim_or_any_write(setup, invalid):
    data = setup(); owner, rows, _, events, replays, _, _, _ = data
    plan = review(data); ack = acknowledgment(plan); before = states(rows)
    if invalid == 'empty': ack = []
    elif invalid == 'boolean': ack = True
    elif invalid == 'hash': ack[0]['before_sha256'] = '0' * 64
    elif invalid == 'revision': ack[0]['revision'] = '99'
    elif invalid == 'duplicate': ack[1] = deepcopy(ack[0])
    elif invalid == 'extra': ack.append(deepcopy(ack[-1]))
    elif invalid == 'reordered': ack.reverse()
    request = {'action': 'commit', 'preflight_token': plan['preflight_token'], 'request_id': 'bad-ack'}
    if invalid != 'missing': request['spill_review_ack'] = ack
    owner.handle_command(request)
    assert not events[-1]['success'] and not events[-1]['outcome_unknown']
    assert plan['preflight_token'] in owner.preflight.store.pending
    assert plan['preflight_token'] not in owner.preflight.store.terminal
    assert states(rows) == before and not replays and not owner.ledger


def test_nonspill_token_rejects_spill_ack_without_consuming_review(setup):
    data = setup(); owner, rows, _, events, replays, renders, _, _ = data
    plan = review(data, (1,), modules=[SC.OP_EXPOSURE]); before = states(rows)
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'spill_review_ack': [], 'request_id': 'wrong-module'})
    assert not events[-1]['success'] and plan['preflight_token'] in owner.preflight.store.pending
    assert states(rows) == before and not replays and not renders


def test_missing_renderer_blocks_each_target_instead_of_supplying_fake_images(setup):
    data = setup(); owner, rows, _, _, _, renders, _, _ = data
    owner.preflight.ports = replace(owner.preflight.ports, prepare_spill=None, verify_spill=None)
    before = states(rows); plan = review(data)
    assert plan['ok'] == 0 and plan['blocked'] == 2 and not renders
    assert all(target['spill_transfer'] is None for target in plan['targets'])
    assert states(rows) == before and not owner.ledger


def test_blocked_target_is_reported_and_cannot_be_acknowledged_as_eligible(setup):
    data = setup(); _, rows, _, _, _, renders, _, _ = data
    rows[1]['state']['_id_background']['enabled'] = False
    plan = review(data)
    assert plan['blocked'] == 1 and plan['ok'] == 1 and len(renders) == 2
    assert plan['targets'][0]['spill_transfer'] is None and len(acknowledgment(plan)) == 1
    result = commit(data, plan)
    assert result['success'] and result['targets'] == [2]
    assert not rows[1]['state']['_id_background']['enabled']


def test_original_and_derived_commit_keep_only_compact_evidence_and_target_masks(setup):
    data = setup(derived=True)
    owner, rows, _, _, replays, renders, checks, _ = data
    masks = [row['state']['_target_mask'] for row in rows]
    source_asset = rows[2]['state']['_creative_base']
    plan = review(data); result = commit(data, plan)
    assert result['success'] and not replays and len(renders) == 4
    assert len(checks) >= 8  # Preflight, token resolution, planning, pre-write.
    ledger = owner.ledger[result['batch_id']]['targets']
    for index in (1, 2):
        row = rows[index]; saved = ledger[str(index)]
        assert row['state']['_target_mask'] is masks[index] and masks[index] is not masks[0]
        assert saved['after'] is not row['state'] and saved['spill_review']['source_proof'] == SOURCE.row_proof(row)
        assert 'base64' not in json.dumps(saved['spill_review'])
        assert SP.params_of(row['state']) == {'enabled': True, 'strength': 65.}
    assert rows[2]['state']['_creative_base'] is source_asset
    assert ledger['1']['source_proof']['creative_source'] is None
    assert ledger['2']['source_proof']['creative_source'] is not None


@pytest.mark.parametrize('changed', ['upstream', 'people', 'revision', 'source', 'extent'])
def test_stale_target_is_skipped_without_replacing_its_reviewed_full_state(setup, changed):
    data = setup(); owner, rows, _, _, _, _, _, people = data
    plan = review(data); row = rows[1]
    if changed == 'upstream': row['state']['untouched'] = 'new unrelated edit after visual review'
    elif changed == 'people': people[owner.versions.version(row).document_id]['owner'] = 'new-owner'
    elif changed == 'revision': owner.versions.advance(row)
    elif changed == 'source':
        from pathlib import Path
        Path(row['path']).write_bytes(b'externally-replaced-original')
    else: row['src_w'] = 33
    before = fingerprint(row['state']); result = commit(data, plan)
    assert result['success'] and result['targets'] == [2] and len(result['skipped']) == 1
    assert fingerprint(row['state']) == before and not row['undo']


def test_exact_ack_replay_returns_terminal_result_without_second_write(setup):
    data = setup(); owner, rows, _, events, _, renders, checks, _ = data
    plan = review(data); result = commit(data, plan)
    assert result['success']; before = states(rows); count = len(checks)
    replayed = commit(data, plan)
    assert replayed['success'] and replayed['replayed'] and replayed['batch_id'] == result['batch_id']
    assert states(rows) == before and len(renders) == 4 and len(checks) == count
    altered = acknowledgment(plan); altered[0]['after_sha256'] = 'f' * 64
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'spill_review_ack': altered, 'request_id': 'bad-replay'})
    assert not events[-1]['success'] and states(rows) == before and len(owner.ledger) == 1


def test_terminal_budget_failure_retains_ack_and_never_reexecutes(setup, monkeypatch):
    data = setup(); owner, rows, _, _, _, renders, checks, _ = data
    plan = review(data)
    monkeypatch.setattr(STORE, 'MAX_RESULT_BYTES', 1)
    result = commit(data, plan)
    assert not result['success'] and result['outcome_unknown']
    assert result['spill_review_ack'] == acknowledgment(plan)
    before = states(rows); count = len(checks)
    replayed = commit(data, plan)
    assert replayed['replayed'] and replayed['outcome_unknown']
    assert states(rows) == before and len(checks) == count and len(renders) == 4
    assert len(owner.ledger) == 1 and all(len(rows[index]['undo']) == 1 for index in (1, 2))


def test_actual_write_port_rechecks_after_frozen_controller_resolution(setup):
    data = setup(); owner, rows, _, _, replays, _, _, _ = data
    plan = review(data); before = states(rows)
    def changed(*args):
        raise ValueError('Synthetic ownership changed at actual write boundary')
    owner.editor = replace(owner.editor, verify_spill=changed)
    result = commit(data, plan)
    assert not result['success'] and states(rows) == before and not replays and not owner.ledger


@pytest.mark.parametrize('changed', ['state', 'people'])
def test_live_replay_rechecks_complete_candidate_before_any_parked_write(setup, changed):
    data = setup(); owner, rows, _, events, replays, _, _, people = data
    plan = review(data, (0, 1, 2)); before = states(rows); replay = owner.editor.replay
    def mutate(candidate, **kwargs):
        frame = replay(candidate, **kwargs)
        if kwargs['replayed_for'].startswith('batch:'):
            if changed == 'state': rows[0]['state']['untouched'] = 'changed during full replay'
            else: people[owner.versions.version(rows[0]).document_id]['owner'] = 'changed-during-replay'
        return frame
    invalidated = []
    owner.editor = replace(owner.editor, replay=mutate, invalidate=lambda: invalidated.append(True))
    result = commit(data, plan)
    assert not result['success'] and states(rows) == before and not owner.ledger
    assert not rows[1]['undo'] and not rows[2]['undo'] and len(replays) == 2
    assert bool(invalidated) is (changed == 'people')
    assert any(event.get('event') == 'engine_warn' and 'reload' in event.get('warn', '')
               for event in events) is (changed == 'people')


def test_undo_redo_preserve_later_unrelated_edits_without_fresh_visual_render(setup):
    data = setup(derived=True); owner, rows, _, events, replays, renders, _, _ = data
    before = [deepcopy(row['state']['_id_background']) for row in rows]
    result = commit(data, review(data)); bid = result['batch_id']; render_count = len(renders)
    rows[1]['state']['untouched'] = 'later edit'; rows[2]['state']['unrelated'] = 'preserved'
    owner.handle_command({'action': 'undo', 'batch_id': bid, 'request_id': 'undo'})
    assert events[-1]['success'] and events[-1]['restored'] == [1, 2]
    assert rows[1]['state']['_id_background'] == before[1] and rows[2]['state']['_id_background'] == before[2]
    owner.handle_command({'action': 'redo', 'batch_id': bid, 'request_id': 'redo'})
    assert events[-1]['success'] and events[-1]['restored'] == [1, 2]
    assert rows[1]['state']['untouched'] == 'later edit' and rows[2]['state']['unrelated'] == 'preserved'
    assert len(renders) == render_count and not replays


@pytest.mark.parametrize('index', [1, 2])
@pytest.mark.parametrize('corrupt', ['missing', 'document', 'revision', 'proof', 'before', 'after'])
def test_history_cannot_restore_tampered_original_or_derived_saved_evidence(setup, index, corrupt):
    data = setup(derived=True); owner, rows, *_ = data
    result = commit(data, review(data))
    saved = deepcopy(owner.ledger[result['batch_id']]['targets'][str(index)])
    if corrupt == 'missing': saved.pop('spill_review')
    elif corrupt == 'document': saved['spill_review']['document_id'] = 'another-target'
    elif corrupt == 'revision': saved['spill_review']['revision'] = '99'
    elif corrupt == 'proof': saved['source_proof']['original_sha256'] = 'f' * 64
    elif corrupt == 'before': saved['before']['untouched'] = 'altered saved state'
    else: saved['after']['untouched'] = 'altered saved state'
    with pytest.raises(ValueError):
        verify_history_source(rows[index], saved, [SP.OP], saved['before'])


def test_direct_spill_commit_stays_fenced_even_with_display_ack_field(setup):
    data = setup(); owner, rows, _, events, replays, renders, _, _ = data
    before = states(rows)
    owner.handle_command({'action': 'commit', 'docs': [1], 'module_scope': [SP.OP],
        'spill_review_ack': [], 'request_id': 'direct'})
    assert not events[-1]['success'] and states(rows) == before and not owner.ledger
    assert not renders and not replays


def test_combined_optics_and_reference_are_installed_before_spill_review(setup, monkeypatch):
    """Synthetic dependency installers establish ordering, not optics quality."""
    data = setup(); owner, _, _, _, _, renders, _, _ = data
    original_params = SC.params_of
    original_candidate = OA.candidate
    monkeypatch.setattr(SC, 'params_of', lambda state, ops: {
        op: ({'synthetic_request': True} if op in (OA.OP, RC.OP) else original_params(state, [op])[op])
        for op in ops})
    monkeypatch.setattr(OA, 'candidate', lambda state, modules, **kw: original_candidate(
        state, {op: value for op, value in modules.items() if op not in (OA.OP, RC.OP)}, **kw))
    optics = {'recipe': {'synthetic_installed': 'optics'}}
    reference = {'synthetic_installed': 'reference'}
    monkeypatch.setattr(PLANNER.OR, 'prepare', lambda *args, **kwargs: (deepcopy(optics), {}))
    monkeypatch.setattr(RC, 'verify_target', lambda *args, **kwargs: deepcopy(reference))
    monkeypatch.setattr(RC, 'apply_verified', lambda candidate, value: candidate.update(_reference_color=value))
    owner.preflight.ports = replace(owner.preflight.ports,
        prepare_optics=lambda *args: {}, prepare_reference=lambda *args: deepcopy(reference))
    plan = review(data, (1,), modules=[SP.OP, OA.OP, RC.OP])
    assert plan['ok'] == 1 and len(renders) == 2
    before, after = renders[0][1], renders[1][1]
    assert before.get('_optics') != optics['recipe'] and before.get('_reference_color') != reference
    assert after['_optics'] == optics['recipe'] and after['_reference_color'] == reference
