# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN mixed decoration history and atomicity acceptance fixtures.

Synthetic immutable sources and mocked complete render/replay boundaries only.
Not imported, collected, run, or evidence of photo quality or numerical parity.
"""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from test_eye_bag_preset_alias_history_unrun import mixed
from test_eye_bag_preserve_host_unrun import eye
from lumaretouch_engine import face_decoration_preset_alias_history as H
from lumaretouch_engine import face_decoration_preset_alias_transaction as T
from lumaretouch_engine import face_decoration_preset_alias_review as REVIEW
from lumaretouch_engine import face_decoration_preset_alias_authority as AUTH
from lumaretouch_engine import face_decoration_support as SUPPORT, face_decoration_state as D
from lumaretouch_engine import people_batch_ledger as L, people_history_persistence as PERSIST
from lumaretouch_engine import people_state as P, people_support_assets as BANK
from lumaretouch_engine import full_candidate_render as FULL, virtual_copy_people as V
from lumaretouch_engine import people_transfer_inventory as INVENTORY
from lumaretouch_engine.people_graph_patch import between
from lumaretouch_engine.face_decoration_scope import resolved_recipe


@pytest.fixture
def decoration(mixed, monkeypatch):
    h = mixed; ref = h.review['face_ref']
    graph, assets = SUPPORT.retain(h.owner.snapshot(), {}, ref, eye())
    graph = P.set_override(graph, 'face', ref['face_instance_id'], D.OP, '/strength', .2)
    h.owner.commit(graph, expected_fence=h.owner.fence)
    project = {'owner': h.owner, 'people_support_assets': assets}
    h.engine._people_project_context = project; h.engine._people_active_context = project
    h.engine._people_support = assets; h.assets = deepcopy(assets); h.ref = ref
    h.record = graph['faces'][ref['face_instance_id']]['local_assets'][SUPPORT.KIND]['content_sha256']
    h.plans['project']['before'] = h.owner.snapshot()
    h.plans['project']['candidate'] = P.set_override(h.owner.snapshot(), 'face', ref['face_instance_id'], D.OP, '/strength', .4)
    h.modules = {D.OP: {'recipe': {**D.neutral(), 'strength': .4}}, 'lnx.exposure.v1': {}}
    h.preset = {'id': 'fixture-decoration-mixed'}
    def context(*args):
        return {'version': 1, 'people_graph': h.owner.snapshot(),
            **{key: {} for key in V.FIELDS}, 'people_support_assets': deepcopy(T.bank(h.engine))}
    monkeypatch.setattr(FULL, 'people_context', context)
    def refresh():
        coverage = {'version': 1, 'support_transfer': 'none', 'targets': [{'face_ref': ref,
            'scope': 'target-reviewed-visible-skin', 'visibility_sha256': h.record,
            'recipe_sha256': H.coverage_digest(resolved_recipe(h.plans['project']['candidate'], ref['face_instance_id']))}]}
        members = []
        for index, row in enumerate((h.row, h.sibling)):
            source = next(target['source_proof'] for target in h.targets.values() if target['document_id'] == row['document_id'])
            visual = {'version': 1, 'document_id': row['document_id'], 'revision': str(row['document_revision']),
                'source_proof': source, 'before_state_sha256': '1' * 64,
                'candidate_state_sha256': ('2' if index == 0 else '1') * 64,
                'before_people_sha256': '3' * 64, 'candidate_people_sha256': '4' * 64,
                'source_size': [16, 16], 'before_output_size': [2, 2], 'after_output_size': [2, 2],
                'coverage_sha256': H.coverage_digest(coverage),
                'before': {'mime': 'image/png', 'width': 2, 'height': 2, 'sha256': '5' * 64},
                'after': {'mime': 'image/png', 'width': 2, 'height': 2, 'sha256': '6' * 64}}
            members.append({'path': row['path'], 'role': 'active' if index == 0 else 'sibling', 'visual': visual})
        value = {'version': 2, 'preset_sha256': H.coverage_digest(h.preset), 'applies_sha256': H.coverage_digest(h.modules),
            'load_id': h.engine._load_id, 'owner': INVENTORY.proof(h.engine, h.row, h.plans['project']['before']),
            'face_ref': ref, 'coverage': coverage, 'visual': deepcopy(members[0]['visual']), 'members': members,
            'before_bank_sha256': H.coverage_digest(T.bank(h.engine))}
        value['review_sha256'] = H.coverage_digest(value); h.review = REVIEW.checked(value)
        h.ack = {key: value[key] for key in ('review_sha256', 'preset_sha256', 'applies_sha256')}
        h.ack['members'] = [{'document_id': member['visual']['document_id'], 'revision': member['visual']['revision'],
            'before_sha256': member['visual']['before']['sha256'], 'after_sha256': member['visual']['after']['sha256'],
            'coverage_sha256': member['visual']['coverage_sha256']} for member in members]
    h.refresh = refresh; refresh()
    h.marker = lambda: H.prepare(h.engine, h.review, h.plans, h.targets,
        current_before=h.before, current_after=h.after, modules=h.modules, ack=h.ack)
    def entry():
        return {'ops': [L.OP], 'people_changes': [], 'policy': 'protected_scoped_graph',
            'people_scoped_changes': [{'scope': 'project', 'document_id': h.row['document_id'],
                'changes': between(h.plans['project']['before'], h.plans['project']['candidate'])}],
            'targets': deepcopy(h.targets), H.KEY: h.marker(), 'at_ns': 1, 'undone': False}
    h.entry = entry; h.initial_fence = h.owner.fence
    return h


def commit(h, **kwargs):
    return T.commit(h.engine, review=h.review, plans=h.plans, targets=h.targets,
        current_before=h.before, current_after=h.after, modules=h.modules, ack=h.ack,
        request_id='decoration-mixed', verify_before=lambda: None, **kwargs)


def test_complete_selected_recipe_and_sibling_own_inputs_share_one_ledger(decoration):
    h = decoration; own = H.stable(H.project_state(h.sibling['state'], H.state_fields(h.engine)))
    bid, frame = commit(h); marker = h.batch.ledger[bid][H.KEY]
    assert h.engine.current['_exposure'] == [.3] and h.row['state']['_exposure'] == [.3]
    assert H.stable(H.project_state(h.sibling['state'], H.state_fields(h.engine))) == own
    assert marker['ack'] == h.ack and marker['ack_sha256'] == H.coverage_digest(h.ack)
    assert marker['support_assets'] == h.assets and T.bank(h.engine) == h.assets
    assert h.row['document_revision'] == 5 and h.sibling['document_revision'] == 9
    assert h.row['undo'] == h.row['redo'] == h.sibling['undo'] == h.sibling['redo'] == []
    assert frame['doc_state'] == {} and h.engine._people_shared_mutation
    assert h.render.call_args_list[0].args[2]['_exposure'] == [.7]
    assert h.render.call_args_list[1].args[2]['_exposure'] == [.3]


def test_retained_decoration_allows_genuine_recipe_only_delta_without_graph_commit(decoration):
    h = decoration; h.modules = {'lnx.exposure.v1': {}}
    h.plans['project']['candidate'] = deepcopy(h.plans['project']['before']); h.refresh()
    bid, _ = commit(h)
    assert h.owner.fence == h.initial_fence
    assert h.batch.ledger[bid]['people_scoped_changes'][0]['changes'] == []
    assert H.status_summary(h.batch.ledger[bid])['selected_modules'] == ['lnx.exposure.v1']
    L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert h.engine.current['_exposure'] == [.1] and h.owner.fence == h.initial_fence


def test_complete_noop_does_not_create_history_or_advance_member_fences(decoration):
    h = decoration; h.plans['project']['candidate'] = deepcopy(h.plans['project']['before'])
    h.after.update(h.before); h.refresh()
    with pytest.raises(ValueError, match='no-op') as failed: commit(h)
    assert not failed.value.side_effects_started and not failed.value.requires_reload
    assert h.owner.fence == h.initial_fence and not h.batch.ledger
    assert h.row['document_revision'] == 4 and h.sibling['document_revision'] == 8


@pytest.mark.parametrize('fault', ('sibling-recipe', 'extra-marker', 'missing-support', 'mutated-support',
    'coverage', 'ack-order', 'ack-revision', 'graph-face', 'unselected', 'current-state'))
def test_marker_never_widens_scalar_or_source_owned_image_authority(decoration, fault):
    h = decoration; entry = h.entry(); marker = entry[H.KEY]
    if fault == 'sibling-recipe': marker['dependencies'][1]['after']['state_sha256'] = '0' * 64
    elif fault == 'extra-marker': entry['face_decoration_support_alias_review'] = {}
    elif fault == 'missing-support': marker['support_assets'].clear()
    elif fault == 'mutated-support': marker['support_assets'][h.record]['face_ref']['face_instance_id'] = 'donor'
    elif fault == 'coverage': marker['reviewed_face_refs'] = []
    elif fault == 'ack-order': marker['ack']['members'].reverse(); marker['ack_sha256'] = H.coverage_digest(marker['ack'])
    elif fault == 'ack-revision': marker['ack']['members'][1]['revision'] = '9'; marker['ack_sha256'] = H.coverage_digest(marker['ack'])
    elif fault == 'graph-face': entry['people_scoped_changes'][0]['changes'][0]['collection'] = 'faces'
    elif fault == 'unselected': marker['selected_modules'] = ['lnx.exposure.v1']
    else: marker['current_states']['after']['_exposure'] = [.9]
    with pytest.raises((ValueError, KeyError)): H.check(entry)


def test_distinct_typed_authority_cannot_paint_or_change_another_selected_scope(decoration):
    h = decoration
    authority = AUTH.mint(h.engine, h.row, h.plans['project']['before'], h.plans['project']['candidate'], h.targets,
        [h.ref], selected_ref=h.ref, modules=h.modules, before_assets=h.assets)
    assert type(authority) is AUTH.PresetAliasAuthority
    bad = deepcopy(h.plans['project']['candidate'])
    bad['faces'][h.ref['face_instance_id']]['local_assets'].clear()
    with pytest.raises(ValueError): authority.verify(h.engine, h.row, h.plans['project']['before'], bad)
    with pytest.raises(ValueError): AUTH.mixed_changes(h.plans['project']['before'], h.plans['project']['candidate'],
        [h.ref], selected_ref=h.ref, modules=['lnx.exposure.v1'], assets=h.assets)


def test_render_failure_before_publication_is_known_no_write(decoration):
    h = decoration; h.render.side_effect = ValueError('full source unavailable')
    with pytest.raises(ValueError) as failed: commit(h)
    assert not failed.value.side_effects_started and not failed.value.requires_reload
    assert h.owner.fence == h.initial_fence and not h.batch.ledger


def test_partial_current_replay_compensates_both_sides_without_rewinding_fences(decoration):
    h = decoration; replay = h.engine._replay_state; calls = []
    def fail_once(value, **kwargs):
        calls.append(kwargs['mode']); result = replay(value, **kwargs)
        if len(calls) == 1: raise ValueError('failed after current recipe installed')
        return result
    h.engine._replay_state = fail_once
    with pytest.raises(ValueError) as failed: commit(h)
    assert failed.value.side_effects_started and failed.value.rolled_back and not failed.value.requires_reload
    assert h.engine.current['_exposure'] == [.1] and h.sibling['state']['_exposure'] == [.7]
    assert h.owner.fence == h.initial_fence + 2 and not h.batch.ledger
    assert h.row['document_revision'] == 5 and h.sibling['document_revision'] == 9
    assert T.bank(h.engine) == h.assets and calls == ['preset', 'preset_rollback']


def test_intervening_bank_mutation_is_unknown_and_never_overwritten(decoration):
    h = decoration
    def fail(value, **kwargs):
        T.bank(h.engine).pop(h.record)
        raise ValueError('intervening immutable bank deletion')
    h.engine._replay_state = fail
    with pytest.raises(ValueError) as failed: commit(h)
    assert failed.value.side_effects_started and not failed.value.rolled_back and failed.value.requires_reload
    assert h.record not in T.bank(h.engine) and not h.batch.ledger
    h.batch.editor.invalidate.assert_called_once()


def test_late_dirty_failure_retains_only_verified_original_receipt(decoration):
    h = decoration; h.batch.editor.mark_dirty.side_effect = RuntimeError('late dirty failure')
    with pytest.raises(RuntimeError) as failed: commit(h)
    error = failed.value
    assert error.side_effects_started and error.requires_reload and not error.rolled_back
    assert error.face_decoration_preset_alias_review == H.status_summary(h.batch.ledger[error.batch_id])
    assert error.alias_members == [{'document_id': 'doc-current', 'expected_revision': '4', 'result_revision': '5'},
        {'document_id': 'doc-sibling', 'expected_revision': '8', 'result_revision': '9'}]


def test_save_reopen_roundtrips_real_current_assets_and_exact_support(decoration):
    h = decoration; bid, _ = commit(h); entry = h.batch.ledger[bid]
    L.restore_scoped(h.engine, entry, False)
    h.engine._batch_sync = h.batch
    project = {'assets': {}, 'people_support_assets': deepcopy(T.bank(h.engine))}
    PERSIST.save(h.engine, project)
    assert project['people_batch_history'][bid][H.KEY]['current_states']['codec'] == 'project.v1'
    _, restored = PERSIST.prepare(project, [], 64)
    L.restore_scoped(h.engine, restored[bid], True)
    assert h.engine.current['_exposure'] == [.3] and h.sibling['state']['_exposure'] == [.7]
    assert T.bank(h.engine) == h.assets
    project['people_support_assets'].clear()
    with pytest.raises(ValueError): PERSIST.prepare(project, [], 64)


@pytest.mark.parametrize('fault', ('crop', 'repair', 'source', 'new-member', 'unavailable', 'support'))
def test_protected_restore_refuses_changed_member_inputs_without_write(decoration, fault):
    h = decoration; bid, _ = commit(h); before = h.owner.snapshot()
    if fault == 'crop': h.sibling['state']['_crop_rect'] = [.2, .2, .6, .6]
    elif fault == 'repair': h.engine.current['_repair_ops'] = ['new repair']
    elif fault == 'source': h.sibling['state']['_fixture_source'] = 'c' * 64
    elif fault == 'new-member': h.engine._docs.append({**deepcopy(h.sibling), 'document_id': 'unreviewed'})
    elif fault == 'unavailable': h.sibling['trashed'] = True
    else: T.bank(h.engine).pop(h.record)
    with pytest.raises(ValueError): L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert h.owner.snapshot() == before


def test_exact_history_request_and_marker_summary_are_distinct(decoration):
    h = decoration; bid, _ = commit(h); entry = h.batch.ledger[bid]
    command = {'cmd': 'batch', 'action': 'undo', 'request_id': 'history', 'batch_id': bid}
    T.require_history_request(h.batch, command, entry)
    assert set(H.status_summary(entry)) == {'version', 'review_sha256', 'preset_sha256', 'applies_sha256',
        'current_document_id', 'member_count', 'selected_modules'}
    with pytest.raises(ValueError): T.require_history_request(h.batch, {**command, 'docs': [0]}, entry)
    from lumaretouch_engine import eye_bag_preset_alias_history as OLD
    assert OLD.check(entry) is None
    bad = deepcopy(entry); bad[OLD.KEY] = {}
    with pytest.raises(ValueError): OLD.check(bad)


def test_append_only_unreferenced_support_survives_undo(decoration):
    h = decoration; bid, _ = commit(h); region = eye()
    region['recipe']['objects'][0]['points'][0] = [.31, .41]
    _, grown = SUPPORT.retain(h.owner.snapshot(), T.bank(h.engine), h.ref, region)
    assert set(grown) > set(h.assets)
    h.engine._people_support = grown; h.engine._people_project_context['people_support_assets'] = grown
    L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert T.bank(h.engine) == grown and h.engine.current['_exposure'] == [.1]


def test_parked_original_current_undo_never_switches_private_selection(decoration):
    from types import SimpleNamespace
    h = decoration; bid, _ = commit(h)
    other = {**deepcopy(h.sibling), 'document_id': 'private-other', 'copy_number': 1, 'document_revision': 1}
    other['state']['_fixture_source'] = 'c' * 64
    h.engine._docs.append(other); h.engine._doc_index = 2; h.engine.current = deepcopy(other['state'])
    private = {'owner': SimpleNamespace(snapshot=lambda: P.empty()), 'people_support_assets': {}}
    h.engine._people_active_context = private; h.engine._people_graph_owner = private['owner']
    h.engine._people_scope_row = other; h.engine._people_support = {}
    own = H.stable(H.project_state(h.engine.current, H.state_fields(h.engine)))
    L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert V.current_row(h.engine) is other and h.engine._people_active_context is private
    assert H.stable(H.project_state(h.engine.current, H.state_fields(h.engine))) == own
    assert h.row['state']['_exposure'] == [.1] and h.sibling['state']['_exposure'] == [.7]
    assert T.bank(h.engine) == h.assets


def test_retained_image_verifier_is_not_optional_write_authority(decoration):
    h = decoration
    with pytest.raises(ValueError, match='verifier') as failed:
        T.commit(h.engine, review=h.review, plans=h.plans, targets=h.targets,
            current_before=h.before, current_after=h.after, modules=h.modules, ack=h.ack, request_id='no-proof')
    assert not failed.value.side_effects_started and not h.batch.ledger


def test_batch_status_summary_uses_the_actual_ledger_entry_source_regression():
    import ast
    from pathlib import Path
    source = (Path(__file__).parents[1] / 'src/lumaretouch_engine/batch_sync.py').read_text()
    calls = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'dp_status_summary']
    assert len(calls) == 1 and len(calls[0].args) == 1
    assert isinstance(calls[0].args[0], ast.Name) and calls[0].args[0].id == 'entry'
    assert "face_decoration_preset_alias_history_no_write" in source
    assert "face_decoration_preset_alias_history_rolled_back" in source


def test_distinct_codec_and_read_only_dispatch_hooks_are_wired_source_regression():
    from pathlib import Path
    root = Path(__file__).parents[1] / 'src/lumaretouch_engine'
    persistence = (root / 'people_history_persistence.py').read_text()
    assert 'encode_dp_states(encode_states(entry' in persistence
    assert 'decode_dp_states(decode_states(deepcopy(value)' in persistence
    assert persistence.count('validate_dp_history(entry,project)') == 2
    receipt = (root / 'batch_dispatch_receipt.py').read_text()
    assert 'mixed = dp_failure_context(owner, request)' in receipt
    assert 'if mixed: context.update(mixed, no_write=True, restored=[])' in receipt
