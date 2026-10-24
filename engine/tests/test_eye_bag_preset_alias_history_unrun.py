# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN mixed-preset alias transaction and durable codec fixtures.

Synthetic graphs and mocked source/render boundaries only. No collection,
product imports, tests, build, inference or photo-quality evaluation ran during
source authoring. These are executable acceptance specifications, not results.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from test_eye_bag_preserve_host_unrun import graph, ASSET
from lumaretouch_engine import eye_bag_preset_alias_history as H
from lumaretouch_engine import eye_bag_preset_alias_transaction as T, people_batch_ledger as L
from lumaretouch_engine import people_history_persistence as PERSIST, people_state as P
from lumaretouch_engine import virtual_copy_people as V, creative_derived_source as SOURCE
from lumaretouch_engine import full_candidate_render as FULL, face_style_alias_review as CLOSURE
from lumaretouch_engine import eye_bag_preserve_state as EYE
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
from lumaretouch_engine.people_graph_patch import between


@pytest.fixture
def mixed(monkeypatch):
    before_graph, target = graph(); owner = PeopleGraphOwner(before_graph)
    def state(exposure, crop):
        return {'_fixture_source': ASSET, '_exposure': [exposure], '_crop_rect': crop,
            '_repair_ops': [], '_redo_ops': [], '_light_ops': [], '_light_redo': [],
            '_lut_preset': 'film-neutral', '_grade_mask': np.zeros((2, 2), dtype=np.uint8),
            '_face_manual': {'disabled': [], 'added': []}, '_deform_default': {'slim_face': 0.},
            '_deform_overrides': [], '_deform': {'amounts': {'slim_face': .2}, 'built': True},
            '_deform_defer': False, '_op_seq': 12, '_proxy': [2, 2], '_precompute': object(), '_precompute_backend': 'fixture'}
    first = {'document_id': 'doc-current', 'document_revision': 4, 'path': '/fixture/current.png',
        'state': state(.1, [0., 0., 1., 1.]), 'undo': [], 'redo': [], 'copy_number': 0}
    sibling = {'document_id': 'doc-sibling', 'document_revision': 8, 'path': '/fixture/sibling.png',
        'state': state(.7, [.1, .1, .8, .8]), 'undo': [], 'redo': [], 'copy_number': 0}
    engine = SimpleNamespace(_docs=[sibling, first], _doc_index=1, _load_id='load-current',
        _people_project_context={'owner': owner}, _people_active_context={'owner': owner},
        _people_graph_owner=owner, _people_scope_row=first, current=deepcopy(first['state']), _project=None,
        HISTORY_SKIP=('_precompute', '_precompute_backend'), DOC_FIELDS=tuple(first['state']),
        _people_analysis_key=None, _people_shared_mutation=False)
    versions = SimpleNamespace(workspace='workspace-mixed')
    versions.version = lambda row: SimpleNamespace(document_id=row['document_id'], revision=row['document_revision'])
    versions.check_advance = versions.version
    versions.advance = lambda row: row.update(document_revision=row['document_revision'] + 1)
    versions.find = lambda rows, doc: next(((i, row) for i, row in enumerate(rows) if row['document_id'] == doc), None)
    engine._document_versions = lambda: versions
    engine._capture_state = lambda: deepcopy(engine.current)
    engine._people_preset_capture = engine._capture_state
    engine.doc_state = lambda: {}
    engine._people_sync = Mock(); engine._write_current_frame = Mock(return_value={'event': 'frame'})
    def replay(value, **kwargs):
        assert kwargs['strict_local'] is True
        engine.current = deepcopy(value)
        # The graph's mirror is reconstructed, without changing durable defaults.
        engine.current['_deform'] = {'amounts': {'slim_face': .2}, 'built': True}
        return {'event': 'frame'}
    engine._replay_state = replay
    def remember(): V.current_row(engine)['state'] = deepcopy(engine.current)
    batch = SimpleNamespace(versions=versions, ledger={}, sequence=0, clock=lambda: 1., monotonic=lambda: 1,
        documents=SimpleNamespace(rows=lambda: engine._docs, remember_current=remember),
        editor=SimpleNamespace(mark_dirty=Mock(), invalidate=Mock()), emit=Mock())
    engine._batch_controller = lambda: batch
    monkeypatch.setattr(V, 'row_owner', lambda _, row: owner)
    monkeypatch.setattr(V, 'row_snapshot', lambda _, row: owner.snapshot())
    monkeypatch.setattr(V, 'scope_rows', lambda actual, row=None: [item for item in actual._docs if V.scope(item) == 'project'])
    monkeypatch.setattr(V, 'remember', Mock())
    monkeypatch.setattr(CLOSURE, 'verify_dormant', Mock())
    def proof(row):
        asset = row['state']['_fixture_source']
        return {'asset_sha256': asset, 'original_sha256': asset, 'creative_source': None}
    monkeypatch.setattr(SOURCE, 'row_proof', proof)
    def verify(row, expected):
        if proof(row) != expected: raise ValueError('Fixture source changed')
        return expected
    monkeypatch.setattr(SOURCE, 'verify_row', verify)
    monkeypatch.setattr(FULL, 'people_context', lambda *_: {'version': 1, 'people_graph': owner.snapshot(), **{key: {} for key in V.FIELDS}})
    render = Mock(return_value=(None, {})); monkeypatch.setattr(FULL, 'render', render)
    candidate_graph = P.set_override(before_graph, 'face', target['target_id'], EYE.OP, '/amount', .4)
    current_before = deepcopy(engine.current); current_after = deepcopy(current_before); current_after['_exposure'] = [.3]
    plans = {'project': {'row': first, 'before': before_graph, 'candidate': candidate_graph, 'reviewed_face_refs': [target['face_ref']]}}
    targets = {str(index): {'path': row['path'], 'document_id': row['document_id'], 'revision': row['document_revision'],
        'asset_sha256': ASSET, 'people_scope': 'project', 'source_proof': proof(row), 'reviewed_face_refs': [target['face_ref']]}
        for index, row in enumerate(engine._docs)}
    members = [{'path': row['path'], 'visual': {'document_id': row['document_id'], 'revision': str(row['document_revision']),
        'source_proof': proof(row)}} for row in (first, sibling)]
    review = {'review_sha256': '1' * 64, 'preset_sha256': '2' * 64, 'applies_sha256': '3' * 64,
        'face_ref': target['face_ref'], 'replace_legacy': False, 'visual': members[0]['visual'], 'members': members}
    modules = {EYE.OP: {'recipe': {'version': 2, 'amount': .4, 'preserve': 1.}}, 'lnx.exposure.v1': {}}
    def marker():
        return H.prepare(engine, review, plans, targets, current_before=current_before, current_after=current_after, modules=modules)
    def entry():
        return {'ops': [L.OP], 'people_changes': [], 'people_scoped_changes': [{'scope': 'project',
            'document_id': first['document_id'], 'changes': between(plans['project']['before'], plans['project']['candidate'])}],
            'targets': deepcopy(targets), 'policy': 'protected_scoped_graph', H.KEY: marker(), 'at_ns': 1, 'undone': False}
    return SimpleNamespace(engine=engine, owner=owner, row=first, sibling=sibling, batch=batch, review=review,
        modules=modules, before=current_before, after=current_after, plans=plans, targets=targets, marker=marker, entry=entry, render=render)


def apply(h):
    return T.commit(h.engine, review=h.review, plans=h.plans, targets=h.targets,
        current_before=h.before, current_after=h.after, modules=h.modules, request_id='mixed-preset')


def test_marker_is_distinct_and_asymmetric_current_state_is_complete(mixed):
    h = mixed; marker = h.marker(); entry = h.entry()
    assert H.check(entry) is not None
    assert '_lut_preset' in marker['state_fields'] and '_proxy' in marker['state_fields']
    assert {'_face_manual', '_deform_default', '_deform_overrides'} <= set(marker['state_fields'])
    assert not set(marker['state_fields']) & H.LIVE_FIELDS
    assert marker['selected_modules'] == list(h.modules)
    records = {item['document_id']: item for item in marker['dependencies']}
    assert records['doc-current']['before']['state_sha256'] != records['doc-current']['after']['state_sha256']
    assert records['doc-sibling']['before']['state_sha256'] == records['doc-sibling']['after']['state_sha256']
    from lumaretouch_engine import eye_bag_alias_history as OLD
    assert OLD.check(entry) is None


def test_one_ledger_atomic_graph_and_current_only_recipe(mixed):
    h = mixed; sibling = H.stable(H.project_state(h.sibling['state'], H.state_fields(h.engine)))
    bid, frame = apply(h)
    assert len(h.batch.ledger) == 1 and H.KEY in h.batch.ledger[bid]
    assert h.engine.current['_exposure'] == [.3] and h.row['state']['_exposure'] == [.3]
    assert H.graph_digest(h.owner.snapshot()) == H.graph_digest(h.plans['project']['candidate'])
    assert H.stable(H.project_state(h.sibling['state'], H.state_fields(h.engine))) == sibling
    assert h.row['document_revision'] == 5 and h.sibling['document_revision'] == 9
    assert h.row['undo'] == h.row['redo'] == h.sibling['undo'] == h.sibling['redo'] == []
    assert h.engine._people_shared_mutation and frame['doc_state'] == {}
    assert h.render.call_args_list[0].args[2]['_exposure'] == [.7]
    assert h.render.call_args_list[1].args[2]['_exposure'] == [.3]


def test_graph_noop_can_change_current_recipe_but_complete_noop_cannot(mixed):
    h = mixed; h.plans['project']['candidate'] = deepcopy(h.plans['project']['before']); fence = h.owner.fence
    bid, _ = apply(h)
    assert h.batch.ledger[bid]['people_scoped_changes'][0]['changes'] == [] and h.owner.fence == fence
    assert h.engine.current['_exposure'] == [.3]


def test_complete_noop_has_no_history_or_revision_advance(mixed):
    h = mixed; h.plans['project']['candidate'] = deepcopy(h.plans['project']['before']); h.after.update(h.before)
    with pytest.raises(ValueError, match='no-op') as failed: apply(h)
    assert failed.value.side_effects_started is False
    assert not h.batch.ledger and h.row['document_revision'] == 4 and h.sibling['document_revision'] == 8


@pytest.mark.parametrize('fault', ('member', 'source', 'sibling-state', 'graph-face', 'graph-support', 'unselected', 'second-marker', 'missing-field', 'runtime-field'))
def test_marker_refuses_widening_or_incomplete_dependencies(mixed, fault):
    h = mixed; entry = h.entry(); marker = entry[H.KEY]
    if fault == 'member': marker['document_ids'].pop()
    elif fault == 'source': marker['dependencies'][0]['source_proof']['asset_sha256'] = 'b' * 64
    elif fault == 'sibling-state': marker['dependencies'][1]['after']['state_sha256'] = '0' * 64
    elif fault in ('graph-face', 'graph-support'):
        entry['people_scoped_changes'][0]['changes'][0]['collection'] = 'faces'
    elif fault == 'unselected': marker['selected_modules'] = [EYE.OP]; entry['people_scoped_changes'][0]['changes'][0]['key'][2] = 'lnx.nose_shape.v1'
    elif fault == 'second-marker': entry['eye_bag_alias_review'] = {}
    elif fault == 'missing-field': del marker['current_states']['before']['_crop_rect']
    else: marker['state_fields'].append('_precompute'); marker['state_fields'].sort()
    with pytest.raises((ValueError, KeyError)): H.check(entry)


def test_codec_deduplicates_array_assets_and_reopens_without_runtime_buffers(mixed):
    h = mixed; entry = h.entry(); assets = {}
    encoded = H.encode_states(entry, assets)
    assert encoded[H.KEY]['current_states']['codec'] == 'project.v1' and len(assets) == 1
    restored = H.decode_states(encoded, assets)
    assert H.status_summary(restored) == H.status_summary(entry)
    assert H.stable(restored[H.KEY]['current_states']) == H.stable(entry[H.KEY]['current_states'])
    _, records = PERSIST.prepare({'assets': assets, 'people_batch_history': {'batch': encoded}}, [], 64)
    assert H.check(records['batch']) is not None
    with pytest.raises(ValueError): H.decode_states(encoded, {})


def test_save_rebuild_reencodes_current_history_assets_after_restore(mixed):
    h = mixed; bid, _ = apply(h); h.engine._batch_sync = h.batch
    project = {'assets': {}}; PERSIST.save(h.engine, project)
    assert project['assets'] and project['people_batch_history'][bid][H.KEY]['current_states']['codec'] == 'project.v1'
    _, records = PERSIST.prepare(project, [], 64); h.batch.ledger = records; h.engine._project = project
    rebuilt = {'assets': {}}; PERSIST.save(h.engine, rebuilt)
    assert rebuilt['assets'] == project['assets']


def test_undo_redo_restores_graph_and_selected_recipe_from_one_marker(mixed):
    h = mixed; bid, _ = apply(h); entry = h.batch.ledger[bid]
    L.restore_scoped(h.engine, entry, False)
    assert h.engine.current['_exposure'] == [.1] and h.sibling['state']['_exposure'] == [.7]
    assert H.graph_digest(h.owner.snapshot()) == H.graph_digest(h.plans['project']['before'])
    L.restore_scoped(h.engine, entry, True)
    assert h.engine.current['_exposure'] == [.3] and h.row['document_revision'] == 7 and h.sibling['document_revision'] == 11


@pytest.mark.parametrize('target,field', (('current','_exposure'), ('sibling','_crop_rect'), ('sibling','_grade_mask'), ('current','_proxy')))
def test_later_repair_crop_recipe_and_coordinate_changes_refuse_undo(mixed, target, field):
    h = mixed; bid, _ = apply(h); state = h.engine.current if target == 'current' else h.sibling['state']
    if field == '_grade_mask': state[field][0, 0] = 255
    else: state[field] = [9.]
    graph_before = h.owner.snapshot()
    with pytest.raises(ValueError): L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert h.owner.snapshot() == graph_before and len(h.batch.ledger) == 1


def test_preparation_failure_never_claims_mutation(mixed):
    h = mixed; h.render.side_effect = ValueError('full-source render refused')
    with pytest.raises(ValueError) as failed: apply(h)
    assert failed.value.side_effects_started is False and not h.engine._people_shared_mutation
    assert h.row['document_revision'] == 4 and h.sibling['document_revision'] == 8 and not h.batch.ledger


def test_failed_current_replay_compensates_graph_and_recipe_without_rewinding_fences(mixed):
    h = mixed; replay = h.engine._replay_state; calls = []
    def fail_once(value, **kwargs):
        calls.append(kwargs['mode']); result = replay(value, **kwargs)
        if len(calls) == 1: raise ValueError('failed after installing current recipe')
        return result
    h.engine._replay_state = fail_once
    with pytest.raises(ValueError) as failed: apply(h)
    assert failed.value.side_effects_started and failed.value.rolled_back
    assert h.engine.current['_exposure'] == [.1] and h.sibling['state']['_exposure'] == [.7]
    assert H.graph_digest(h.owner.snapshot()) == H.graph_digest(h.plans['project']['before'])
    assert h.owner.fence == 2 and h.row['document_revision'] == 5 and h.sibling['document_revision'] == 9
    assert h.engine._people_shared_mutation and not h.batch.ledger and calls == ['preset', 'preset_rollback']


def test_rollback_refuses_newer_owner_instead_of_overwriting_it(mixed):
    h = mixed
    def fail_after_unrelated_graph(value, **kwargs):
        later = P.set_override(h.owner.snapshot(), 'face', h.review['face_ref']['face_instance_id'], EYE.OP, '/preserve', .5)
        h.owner.commit(later, expected_fence=h.owner.fence)
        raise ValueError('intervening graph mutation')
    h.engine._replay_state = fail_after_unrelated_graph
    with pytest.raises(ValueError) as failed: apply(h)
    assert failed.value.side_effects_started and not failed.value.rolled_back and failed.value.requires_reload
    h.batch.editor.invalidate.assert_called_once()
    assert h.owner.fence == 2 and not h.batch.ledger


def test_postpublication_error_retains_only_verified_known_ledger_receipt(mixed):
    h = mixed; h.batch.editor.mark_dirty.side_effect = RuntimeError('late status hook failed')
    with pytest.raises(RuntimeError) as failed: apply(h)
    error = failed.value
    assert error.side_effects_started and error.batch_id in h.batch.ledger
    assert error.eye_bag_preset_alias_review == H.status_summary(h.batch.ledger[error.batch_id])
    assert error.alias_members == [
        {'document_id': 'doc-current', 'expected_revision': '4', 'result_revision': '5'},
        {'document_id': 'doc-sibling', 'expected_revision': '8', 'result_revision': '9'}]


@pytest.mark.parametrize('active', ('sibling', 'unrelated-private'))
def test_undo_can_restore_parked_original_current_without_switching_selection(mixed, active):
    h = mixed; bid, _ = apply(h)
    if active == 'sibling': h.engine._doc_index = 0
    else:
        other = {**deepcopy(h.sibling), 'document_id': 'private-other', 'copy_number': 1,
            'path': '/fixture/private.png', 'document_revision': 1}
        other['state']['_fixture_source'] = 'c' * 64
        h.engine._docs.append(other); h.engine._doc_index = len(h.engine._docs) - 1
    selected = V.current_row(h.engine); h.engine.current = deepcopy(selected['state'])
    own = H.stable(H.project_state(h.engine.current, H.state_fields(h.engine)))
    L.restore_scoped(h.engine, h.batch.ledger[bid], False)
    assert V.current_row(h.engine) is selected and h.row['state']['_exposure'] == [.1]
    assert H.stable(H.project_state(h.engine.current, H.state_fields(h.engine))) == own
    assert h.sibling['state']['_exposure'] == [.7]


def test_repair_and_light_dataclasses_roundtrip_without_rendered_pixel_snapshots(mixed):
    from lumaretouch_engine.repair_record import RepairOp
    from lumaretouch_engine.vram import LightOp
    h = mixed; coverage = np.full((2, 2), 127, dtype=np.uint8)
    for state in (h.before, h.after, h.engine.current, h.row['state']):
        state['_repair_ops'] = [RepairOp(2, coverage.copy())]
        state['_light_ops'] = [LightOp(3, coverage.copy(), -1)]
    assets = {}; encoded = H.encode_states(h.entry(), assets); decoded = H.decode_states(encoded, assets)
    for state in decoded[H.KEY]['current_states'].values():
        assert type(state['_repair_ops'][0]) is RepairOp and type(state['_light_ops'][0]) is LightOp
        assert np.array_equal(state['_repair_ops'][0].weight, coverage)
        assert state['_light_ops'][0].sign == -1
    assert len(assets) == 2  # shared grade-mask and shared repair/light coverage


def test_crafted_saved_field_subset_never_becomes_replay_authority(mixed):
    h = mixed; entry = h.entry(); marker = entry[H.KEY]
    marker['state_fields'].remove('_crop_rect')
    for state in marker['current_states'].values(): del state['_crop_rect']
    for item in marker['dependencies']:
        for side in ('before', 'after'):
            if item['document_id'] == 'doc-current': item[side]['state_sha256'] = H.stable(marker['current_states'][side])
    assert H.check(entry) is not None  # syntactic saved schema alone grants no authority
    with pytest.raises(ValueError, match='durable state contract'):
        H.verify_restore(h.engine, entry, h.plans, h.targets, redo=True)
    assert h.owner.fence == 0 and not h.batch.ledger


def test_final_status_callback_cannot_add_dormant_alias_after_last_check(mixed, monkeypatch):
    h = mixed; invalid = False
    def dormant(*args):
        if invalid: raise ValueError('unavailable affected saved alias appeared')
    monkeypatch.setattr(CLOSURE, 'verify_dormant', dormant)
    def status():
        nonlocal invalid
        invalid = True
        return {}
    h.engine.doc_state = status
    with pytest.raises(ValueError) as failed: apply(h)
    assert failed.value.side_effects_started and not failed.value.rolled_back
    assert not h.batch.ledger and h.engine._people_shared_mutation
    h.batch.editor.invalidate.assert_called_once()


@pytest.mark.parametrize('location', ('/restored/references/sky.png', '/restored/missing/references/sky.png'))
def test_package_sky_locator_relocation_preserves_content_identity_not_filename(mixed, location):
    from lumaretouch_engine import sky_replacement_state as SKY
    from lumaretouch_engine.project_package_dependencies import inventory
    h = mixed; sky = SKY.empty()
    sky['asset'] = {'path': '/old/sky.png', 'sha256': 'd' * 64, 'width': 10, 'height': 20,
        'bits': 16, 'working_color': 'encoded-srgb', 'icc_sha256': 'e' * 64}
    h.engine.DOC_FIELDS += ('_sky_replacement',)
    for state in (h.before, h.after, h.engine.current, h.row['state'], h.sibling['state']): state['_sky_replacement'] = deepcopy(sky)
    assets = {}; entry = h.entry(); encoded = H.encode_states(entry, assets)
    package = {'schema_version': 'lrt.project.v23', 'docs': [], 'source_assets': {}, 'assets': assets,
        'people_batch_history': {'mixed': encoded}}
    references = inventory(package, include_references=True)
    assert len(references) == 1 and len(references[0]['bindings']) == 2
    states = encoded[H.KEY]['current_states']['value']
    for state in states.values(): state['_sky_replacement']['asset']['path'] = location
    restored = H.decode_states(encoded, assets)
    assert H.status_summary(restored) == H.status_summary(entry)
    assert all(state['_sky_replacement']['asset']['path'] == location for state in restored[H.KEY]['current_states'].values())
    assert H.stable(restored[H.KEY]['current_states']) == H.stable(entry[H.KEY]['current_states'])
    bad = deepcopy(encoded); bad[H.KEY]['current_states']['value']['after']['_sky_replacement']['asset']['sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='durable recipe'): H.decode_states(bad, assets)
    bad = deepcopy(encoded); bad[H.KEY]['current_states']['value']['after']['_sky_replacement']['asset']['icc_sha256'] = None
    with pytest.raises(ValueError, match='durable recipe'): H.decode_states(bad, assets)
    assert H.stable({'provenance_path': '/old/sky.png'}) != H.stable({'provenance_path': location})


def test_relocated_sky_never_bypasses_runtime_content_verification(mixed, monkeypatch):
    from lumaretouch_engine import sky_replacement_state as SKY, sky_replacement_assets as ASSETS
    h = mixed; sky = SKY.empty(); sky['enabled'] = True
    # Isolate the asset-byte barrier, not sky region/numeric validation.
    monkeypatch.setattr(SKY, 'check_saved_record', lambda value: value)
    sky['asset'] = {'path': '/restored/sky.png', 'sha256': 'd' * 64}
    h.engine.current['_sky_replacement'] = sky
    verifier = Mock(side_effect=ValueError('same locator, changed bytes'))
    monkeypatch.setattr(ASSETS, 'verify', verifier)
    with pytest.raises(ValueError, match='changed bytes'):
        H.dependencies(h.engine, h.row, h.engine.current, h.owner.snapshot(), H.state_fields(h.engine))
    verifier.assert_called_once_with(sky['asset'])


def test_history_conflict_echoes_validated_marker_without_claiming_write(mixed):
    h = mixed; bid, _ = apply(h); h.engine.current['_exposure'] = [9.]
    h.batch.editor.people_restore = lambda entry, redo: L.restore_scoped(h.engine, entry, redo)
    request = {'cmd': 'batch', 'action': 'undo', 'batch_id': bid, 'request_id': 'undo-conflict'}
    with pytest.raises(ValueError) as failed: L.restore(h.batch, request)
    assert failed.value.eye_bag_preset_alias_history_no_write is True
    assert T.failure_context(h.batch, request) == {'batch_id': bid, 'module_scope': [L.OP],
        H.KEY: H.status_summary(h.batch.ledger[bid])}
    assert T.failure_context(h.batch, {**request, 'batch_id': 'unknown'}) == {}
    assert T.failure_context(h.batch, {**request, 'action': 'commit'}) == {}


def test_late_history_status_failure_is_unknown_not_false_no_write(mixed):
    h = mixed; bid, _ = apply(h)
    h.batch.editor.people_restore = lambda entry, redo: L.restore_scoped(h.engine, entry, redo)
    h.batch.editor.mark_dirty.side_effect = RuntimeError('late history dirty failure')
    request = {'cmd': 'batch', 'action': 'undo', 'batch_id': bid, 'request_id': 'undo-unknown'}
    with pytest.raises(RuntimeError) as failed: L.restore(h.batch, request)
    assert failed.value.eye_bag_preset_alias_history_no_write is False
    assert h.batch.ledger[bid]['undone'] is True and h.engine.current['_exposure'] == [.1]
    assert T.failure_context(h.batch, request)[H.KEY] == H.status_summary(h.batch.ledger[bid])


@pytest.mark.parametrize('fault', ('missing-request', 'null-request', 'blank-request', 'spaces-request',
    'control-request', 'long-request', 'utf8-request', 'nontext-request', 'missing-command', 'wrong-command', 'wrong-action', 'extra-field'))
def test_composite_history_refuses_uncorrelated_or_extended_envelopes_before_any_restore(mixed, fault):
    h = mixed; entry = h.entry(); h.batch.ledger['batch-existing'] = entry
    h.batch.editor.people_restore = Mock(side_effect=AssertionError('No uncorrelated restore allowed'))
    request = {'cmd': 'batch', 'action': 'undo', 'request_id': 'request-history', 'batch_id': 'batch-existing'}
    if fault == 'missing-request': request.pop('request_id')
    elif fault == 'null-request': request['request_id'] = None
    elif fault == 'blank-request': request['request_id'] = ''
    elif fault == 'spaces-request': request['request_id'] = '   '
    elif fault == 'control-request': request['request_id'] = 'bad\u0085id'
    elif fault == 'long-request': request['request_id'] = 'a' * 129
    elif fault == 'utf8-request': request['request_id'] = '修' * 43
    elif fault == 'nontext-request': request['request_id'] = 12
    elif fault == 'missing-command': request.pop('cmd')
    elif fault == 'wrong-command': request['cmd'] = 'people'
    elif fault == 'wrong-action': request['action'] = 'apply'
    else: request['module_scope'] = [L.OP]
    with pytest.raises(ValueError) as failed: L.restore(h.batch, request)
    assert failed.value.eye_bag_preset_alias_history_no_write is True
    h.batch.editor.people_restore.assert_not_called()
    assert h.row['document_revision'] == 4 and h.sibling['document_revision'] == 8 and h.owner.fence == 0
    assert entry['undone'] is False


def test_exact_correlated_envelope_admits_existing_composite_batch_only(mixed):
    h = mixed; entry = h.entry(); h.batch.ledger['batch-existing'] = entry
    request = {'cmd': 'batch', 'action': 'undo', 'request_id': 'r' * 128, 'batch_id': 'batch-existing'}
    T.require_history_request(h.batch, request, entry)
    with pytest.raises(ValueError): T.require_history_request(h.batch, request, deepcopy(entry))
    with pytest.raises(ValueError): T.require_history_request(h.batch, {**request, 'batch_id': 'another'}, entry)


def test_unmarked_old_history_keeps_existing_uncorrelated_route(mixed):
    h = mixed; entry = h.entry(); entry.pop(H.KEY); h.batch.ledger['legacy-existing'] = entry
    h.batch.editor.people_restore = Mock(return_value=None); h.batch.editor.status = lambda: {}
    body = L.restore(h.batch, {'action': 'undo', 'batch_id': 'legacy-existing'})
    h.batch.editor.people_restore.assert_called_once_with(entry, False)
    assert body['event'] == 'batch_undone' and H.KEY not in body
