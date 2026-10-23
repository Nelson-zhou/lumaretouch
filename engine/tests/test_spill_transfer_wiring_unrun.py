"""AUTHORED / UNRUN: spill scalar preset/batch routing and frozen ownership.

No fixtures in this file were imported, collected or executed during authoring.
Source files are synthetic byte identities, not decoded photos. Replay stubs
exercise transaction fences only: parked targets are not claimed as rendered.
Numerical spill quality, native execution and visual acceptance remain UNRUN.
"""
from copy import deepcopy
from dataclasses import replace
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
from lumaretouch_engine.batch_group_history import restore_group
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.local_grade_preset_review import PresetReviews


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
        source = SOURCE.binding(row['state'], row['path'], (32, 24))
        row['state']['_id_background'] = owned_id(source)
        row['state']['_id_background_bundle'] = None
    rows[0]['state']['_id_background'] = I.with_spill(rows[0]['state']['_id_background'],
        {**S.neutral(), 'enabled': True, 'strength': 81.})
    return owner, rows, current, events, replays, remember


def review(owner, events, docs=(1, 2), policy='skip_and_report'):
    owner.handle_command({'action': 'preflight', 'docs': list(docs), 'module_scope': [SP.OP],
        'conflict_policy': policy, 'request_id': 'spill-review'})
    result = events[-1]
    assert result['event'] == 'batch_result' and result['success']
    return result


def commit(owner, events, plan):
    owner.handle_command({'action': 'commit', 'preflight_token': plan['preflight_token'],
        'request_id': 'spill-commit'})
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


def test_live_dependency_mutation_rolls_back_before_any_parked_write(tmp_path):
    owner, rows, _, events, replays, _ = fixture(tmp_path); plan = review(owner, events, (0, 1, 2))
    before = deepcopy([row['state'] for row in rows]); actual = owner.editor.replay
    def changed(candidate, **kwargs):
        frame = actual(candidate, **kwargs)
        if kwargs['replayed_for'].startswith('batch:'):
            rows[0]['state']['_id_background']['edge'] = 3.
        return frame
    owner.editor = replace(owner.editor, replay=changed)
    result = commit(owner, events, plan)
    assert not result['success'] and [row['state'] for row in rows] == before
    assert not rows[1]['undo'] and not rows[2]['undo'] and not owner.ledger
    assert replays[0]['strict_local'] is True


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


@pytest.mark.parametrize('change', ['source', 'support', 'parent'])
def test_preset_review_claim_rechecks_source_and_full_target_dependencies(tmp_path, change):
    _, rows, _, _, _, _ = fixture(tmp_path); row = rows[1]; state = row['state']; reviews = PresetReviews()
    plan = reviews.prepare(stored(), state, row, 'loaded', '7', None)
    assert plan['source_proof'] == SOURCE.row_proof(row)
    if change == 'source': (tmp_path / 'original-1.bin').write_bytes(b'changed-original')
    elif change == 'support':
        support = state['_id_background']['support']['subject']; support['mask']['recipe']['objects'][0]['points'] = [[.6, .5]]
        support['recipe_sha256'] = SUPPORT.digest(support['mask'])
    else: state['_id_background']['edge'] = 2.
    with pytest.raises(ValueError): reviews.claim(plan['preflight_token'], 'spill', state, row, 'loaded', '7')
    assert plan['preflight_token'] in reviews.pending


def preset_owner(batch, row, events, replays):
    def replay(value, **kwargs):
        replays.append(kwargs); row['state'] = deepcopy(value)
        return {'event': 'frame', 'render_ms': 1}
    return P.PresetController(P.PresetPorts(lambda _: None, lambda: 'loaded',
        lambda: deepcopy(row['state']), replay, lambda: ('ok', ''), lambda: {'document_id': 'loaded'},
        lambda: None, target_row=lambda: row, revision=lambda: str(batch.versions.version(row).revision),
        advance=lambda: batch.versions.advance(row)), events.append)


def test_preset_apply_requires_token_and_replays_strictly_with_original_proof(tmp_path, monkeypatch):
    batch, rows, _, events, replays, _ = fixture(tmp_path); owner = preset_owner(batch, rows[1], events, replays)
    monkeypatch.setattr(P.PS, 'find', lambda _: stored())
    with pytest.raises(ValueError): owner.apply({'id': 'spill'})
    assert not replays
    plan = owner.reviews.prepare(stored(), rows[1]['state'], rows[1], 'loaded', owner.ports.revision(), None)
    result = owner.apply({'id': 'spill', 'preflight_token': plan['preflight_token']})
    assert result['source_proof'] == SOURCE.row_proof(rows[1]) and replays[-1]['strict_local'] is True


def test_default_save_does_not_select_both_full_id_and_scalar_spill(tmp_path, monkeypatch):
    batch, rows, _, events, replays, _ = fixture(tmp_path); owner = preset_owner(batch, rows[0], events, replays)
    monkeypatch.setattr(SC, 'transferable_ops', lambda: [SC.ID_BACKGROUND.OP, SP.OP, SC.OP_EXPOSURE])
    saved = []
    monkeypatch.setattr(P.PS, 'save', lambda value, **kwargs: saved.append(value) or '/not-written.json')
    result = owner.save({'id': 'default', 'name': 'Default selection'})
    assert SP.OP not in result['module_scope'] and SC.ID_BACKGROUND.OP in result['module_scope']
    assert len(saved) == 1 and not replays
