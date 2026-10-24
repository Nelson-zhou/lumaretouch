# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: v2 preset admission, canonical replay and target transfer.

Synthetic evidence and mocked native/full-render boundaries specify contracts;
they are not inference, native numerical, photographic or runtime acceptance.
No product import, test collection, test execution, build or typecheck was run
while authoring this file. Legacy deform intent is deliberately not migrated.
Targets LNX-REF-PC-32466-C-da1d54e292 and existing preset/scope contracts;
PORTRAIT-007 photographic acceptance remains separate and pending.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import slim_face_scope as C, slim_face_state as S
from lumaretouch_engine import face_contour_scope as CONTOUR, face_contour_native as N
from lumaretouch_engine import people_state as P, people_algorithms as A, people_scope as REPLAY, scope as SC
from lumaretouch_engine import skin_colour_scope as COLOUR
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, isolate_other_captures)

LEAVES = ('/linked', '/left', '/right')


def recipe(left=0., right=0., *, linked=True):
    return {'recipe': {'version': 2, 'linked': linked, 'left': left, 'right': right}}


def engine_fixture(monkeypatch):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, analysis, current = colour_engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: True)
    engine._docs = [{'document_id': 'target-document', 'path': 'fixture.jpg', 'state': current}]
    engine._doc_index = 0
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    engine._document_versions = lambda: versions
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': ASSET,
        'creative_source': None, 'original_sha256': ASSET})
    return engine, owner, analysis, current


def replay_fixture(monkeypatch, *, fail=False):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); calls = []
    def replay(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        if fail: raise RuntimeError('authored target-render refusal')
        return {'event': 'frame', 'render_ms': 0}
    engine._replay_state = replay
    return engine, owner, analysis, current, calls


def put(owner, params, op=C.OP):
    for path, value in A.leaves(params['recipe']).items():
        owner.value = P.set_override(owner.value, 'face', FACE, op, path, value)


def values(owner):
    return A.recipes(resolve(owner.snapshot(), FACE, A.defaults()))


def test_separate_v2_operation_preserves_legacy_slots_and_generic_derived_guard():
    assert C.OP == 'lnx.slim_face.v2' and S.VERSION == 2
    assert S.CONTROL_ID == 'LNX-REF-PC-32466-C-da1d54e292'
    assert A.GEOMETRY == ('lnx.brow_shape.v1', 'lnx.nose_shape.v1', 'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')
    assert C.OP not in A.GEOMETRY and C.OP not in SC.DERIVED_PARAMETER_OPS
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True
    assert A.defaults()[C.OP] == {'/linked': True, '/left': 0., '/right': 0.}
    assert S.neutral() == recipe()['recipe'] and not S.active(S.neutral())
    assert '/slim_face' in A.defaults()[A.DEFORM] and A.defaults()[A.DEFORM]['/slim_face'] == 0.


@pytest.mark.parametrize('left,right,linked', [(-1., 1., False), (.4, -.7, True), (0., 0., False), (1., 1., True)])
def test_only_link_flag_and_two_signed_amounts_round_trip(left, right, linked):
    params = recipe(left, right, linked=linked)
    assert C.check_params(params) == SC.check_params(C.OP, params) == params
    portable = {'schema': SC.PRESET_SCHEMA, 'id': 'slim-v2', 'name': 'Slim v2',
        'kind': 'portrait', 'modules': {C.OP: params}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(portable)))
    assert loaded['modules'] == {C.OP: params}
    assert set(loaded['modules'][C.OP]['recipe']) == {'version', 'linked', 'left', 'right'}
    assert set(A.leaves(loaded['modules'][C.OP]['recipe'])) == set(LEAVES)


@pytest.mark.parametrize('side', S.SIDES)
@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'), -1.01, 1.01, 10**1000])
def test_bad_scalar_refuses_before_ephemeral_or_canonical_mutation(monkeypatch, side, value):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state); params = recipe()
    params['recipe'][side] = value
    with pytest.raises(ValueError): C.install(state, params)
    assert state == before and not owner.commits


@pytest.mark.parametrize('key', ['face_ref', 'owner', 'source', 'face_skin', 'excluded', 'landmarks',
    'analysis', 'mesh', 'control_points', 'displacement', 'mask', 'coverage', 'supported', 'body_ref', 'ai', 'model_3d'])
def test_portable_shape_rejects_source_geometry_and_claimed_readiness(key):
    params = recipe(.3, -.2, linked=False)
    with pytest.raises(ValueError): C.check_params({**params, key: {}})
    params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


@pytest.mark.parametrize('fault', ['null', 'missing-version', 'bool-version', 'old-version',
    'new-version', 'missing-side', 'non-bool-link', 'legacy-amount'])
def test_shape_is_exactly_the_new_version_not_an_alias_or_legacy_conversion(fault):
    params = recipe()
    if fault == 'null': params['recipe'] = None
    elif fault == 'missing-version': del params['recipe']['version']
    elif fault == 'bool-version': params['recipe']['version'] = True
    elif fault == 'old-version': params['recipe']['version'] = 1
    elif fault == 'new-version': params['recipe']['version'] = 3
    elif fault == 'missing-side': del params['recipe']['right']
    elif fault == 'non-bool-link': params['recipe']['linked'] = 1
    else: params['recipe'] = {'slim_face': .4}
    with pytest.raises(ValueError): C.check_params(params)


def test_workflow_capture_exports_canonical_intent_but_not_evidence(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); params = recipe(.35, -.2, linked=True)
    put(owner, params)
    captured = WorkflowPortsMixin._people_preset_capture(engine)
    portable = SC.params_of(captured, [C.OP])
    assert portable == {C.OP: params} and json.loads(json.dumps(portable)) == portable
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_slim_face_v2_supported'] is True and captured[C.REQUESTED] is False
    assert C.owner_identity(captured) == {'document_id': 'target-document', 'epoch': 'workspace',
        'people_scope': 'project', 'source_proof': {'asset_sha256': ASSET,
            'creative_source': None, 'original_sha256': ASSET}}
    assert set(captured[C.OWNER]) == {'document', 'people_scope', 'state_revision',
        'association_revision', 'graph_sha256', 'source_proof'}
    assert 'face_skin' not in captured and 'landmarks' not in captured
    assert engine._people_analyses[ASSET][FACE] is analysis and current == {}


def test_capture_does_not_translate_or_clear_legacy_slim_amount(monkeypatch):
    engine, owner, _, current = engine_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/slim_face', -.6)
    current['_deform'] = {'amounts': {'slim_face': -.6}, 'built': True}
    before = owner.snapshot(); captured = C.capture(engine)
    assert C.params_of(captured) == recipe()
    assert captured['_deform'] == current['_deform']
    assert owner.snapshot() == before and not owner.commits


@pytest.mark.parametrize('fault', ['face-skin', 'observation', 'excluded', 'ref', 'model',
    'landmark-bytes', 'landmark-count', 'synthetic', 'dimensions', 'donor-analysis'])
def test_capture_needs_own_authenticated_skin_and_actual_478_landmarks(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'face-skin': analysis['face_skin'] = None
    elif fault == 'observation': analysis.pop('face_skin_observation')
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'model': analysis['face_skin_observation']['semantic_model_sha256'] = 'f' * 64
    elif fault == 'landmark-bytes': analysis['landmarks'][0, 0] = .8
    elif fault == 'landmark-count':
        analysis['landmarks'] = analysis['landmarks'][:468]
        digest = sha256(analysis['landmarks'].tobytes()).hexdigest()
        owner.value['faces'][FACE]['evidence']['landmark_digest'] = digest
        analysis['evidence']['landmark_digest'] = digest
    elif fault == 'synthetic':
        owner.value['faces'][FACE]['evidence']['status'] = 'synthetic'
        analysis['evidence']['status'] = 'synthetic'
    elif fault == 'dimensions': engine._people_source = lambda: {'sha256': ASSET, 'width': 641, 'height': 480}
    else: engine._people_analyses[ASSET][FACE] = graph('e' * 64, 'donor-face')[1]
    captured = C.capture(engine)
    assert captured['_slim_face_v2_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3, -.2))
    assert not owner.commits


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged', 'no-document'])
def test_selection_requires_exact_enabled_face_and_owner_not_cursor_alone(monkeypatch, fault):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    if fault == 'no-cursor': engine._people_cursors.clear()
    elif fault == 'group-target': engine._people_targets[ASSET] = {'scope': 'group', 'target_id': 'preserved'}
    elif fault == 'stale-target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'disabled': owner.value['faces'][FACE]['enabled'] = False
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    else: engine._docs.clear()
    captured = C.capture(engine)
    with pytest.raises(ValueError): C.params_of(captured)
    with pytest.raises(ValueError): C.install(captured, recipe())
    assert not owner.commits


def test_install_changes_only_dedicated_transport_and_keeps_generic_derived_refusal(monkeypatch):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3, -.2, linked=False)})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET] and after[C.OWNER] == before[C.OWNER]
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe())
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    with pytest.raises(ValueError): SC.apply_modules({}, {C.OP: recipe(.3, -.2)})
    assert not owner.commits


def test_active_requires_native_but_neutral_reset_needs_only_same_owner(monkeypatch):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(.3, -.2, linked=False))
    monkeypatch.setattr(N, 'available', lambda: False)
    with pytest.raises(ValueError, match='Rust'): C.install(C.capture(engine), recipe(.4, .4))
    analysis['excluded'] = None
    state = C.capture(engine); C.install(state, recipe()); REPLAY.replay_preset(engine, state)
    assert values(owner)[C.OP] == S.neutral()
    assert calls[-1][1]['strict_local'] is True
    assert engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged', 'source',
    'document', 'owner', 'epoch', 'proof', 'source-kind', 'original-source'])
def test_replay_rechecks_live_owner_and_readiness_not_captured_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3, -.2))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'analysis': analysis['excluded'] = None
    elif fault == 'target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    elif fault == 'source': engine._people_source = lambda: {'sha256': 'e' * 64, 'width': 640, 'height': 480}
    elif fault == 'document': engine._docs[0]['document_id'] = 'another-document'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    elif fault == 'epoch': engine._document_versions().workspace = 'another-workspace'
    elif fault == 'proof': state.pop(C.OWNER)
    elif fault == 'source-kind':
        state[C.OWNER]['source_proof']['creative_source'] = {'sha256': ASSET, 'width': 640, 'height': 480}
    else: state[C.OWNER]['source_proof']['original_sha256'] = 'f' * 64
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_same_source_face_switch_refuses_stale_capture_even_when_only_one_remains_enabled(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3, -.2))
    other, analysis = graph(face_id='another-face')
    owner.value['faces']['another-face'] = other['faces']['another-face']
    owner.value['faces'][FACE]['enabled'] = False
    engine._people_analyses[ASSET]['another-face'] = analysis
    engine._people_cursors[ASSET] = 'another-face'
    engine._people_targets[ASSET] = {'scope': 'face', 'target_id': 'another-face',
        'face_ref': P.face_ref(other['faces']['another-face'])}
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_success_preserves_other_operations_and_uses_existing_canonical_owner(monkeypatch):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, COLOUR.OP, '/tint', -.25)
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/slim_face', 0.)
    before = owner.snapshot(); params = recipe(.35, -.2, linked=False)
    state = C.capture(engine); C.install(state, params); REPLAY.replay_preset(engine, state, mode='preset')
    after = owner.snapshot()
    for field in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert after[field] == before[field]
    assert all(row in after['overrides'] for row in before['overrides'])
    added = [row for row in after['overrides'] if row not in before['overrides']]
    assert {(leaf['parameter_path'], leaf['value']) for leaf in added} == {
        ('/linked', False), ('/left', .35), ('/right', -.2)}
    assert all(leaf['scope'] == 'face' and leaf['target_id'] == FACE and leaf['operation_id'] == C.OP for leaf in added)
    assert len(calls) == len(owner.commits) == 1 and calls[0][1]['strict_local'] is True
    assert engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('scope', ['all_people', 'group', 'person', 'face'])
@pytest.mark.parametrize('amount', [-.6, .4])
def test_complete_candidate_refuses_inherited_legacy_without_clearing_or_partial_commit(monkeypatch, scope, amount):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    if scope == 'person':
        owner.value['persons']['confirmed-person'] = {'anonymous': True}
        owner.value['links'] = [{'face_instance_id': FACE, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    target = {'all_people': ASSET, 'group': 'preserved', 'person': 'confirmed-person', 'face': FACE}[scope]
    owner.value = P.set_override(owner.value, scope, target, A.DEFORM, '/slim_face', amount)
    state = C.capture(engine); C.install(state, recipe(.3, -.2))
    # An unrelated module is also staged; conflict cannot partially publish it.
    # Use the existing colour transport rather than guessing a geometry leaf.
    colour = COLOUR.capture(engine, state)
    COLOUR.install(colour, {'recipe': {'version': 1, 'temperature': .2, 'tint': -.1}})
    before = owner.snapshot()
    with pytest.raises(ValueError, match='legacy lnx.deform.v1/slim_face'):
        REPLAY.replay_preset(engine, colour)
    assert owner.snapshot() == before and not owner.commits and not calls
    assert values(owner)[A.DEFORM]['slim_face'] == amount


@pytest.mark.parametrize('key', CONTOUR.S.KEYS)
@pytest.mark.parametrize('side', CONTOUR.S.SIDES)
def test_complete_candidate_refuses_standalone_contour_without_rewriting_it(monkeypatch, key, side):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'group', 'preserved', CONTOUR.OP, f'/{key}/{side}', -.2)
    state = C.capture(engine); C.install(state, recipe(.3, -.2))
    before = owner.snapshot()
    with pytest.raises(ValueError, match='active lnx.face_contour.v1'):
        REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


@pytest.mark.parametrize('order', ['slim-first', 'contour-first'])
def test_two_active_modules_in_one_preset_refuse_before_first_commit(monkeypatch, order):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    state = CONTOUR.capture(engine, C.capture(engine))
    contour = CONTOUR.S.neutral(); contour['jaw']['right'] = -.2
    modules = [(C.OP, recipe(.3, -.2)), (CONTOUR.OP, {'recipe': contour})]
    if order == 'contour-first': modules.reverse()
    after = SC.apply_modules(state, dict(modules)); before = owner.snapshot()
    with pytest.raises(ValueError, match='active lnx.face_contour.v1'):
        REPLAY.replay_preset(engine, after)
    assert owner.snapshot() == before and not owner.commits and not calls


@pytest.mark.parametrize('direction', ['to-slim', 'to-contour'])
def test_explicit_two_module_replacement_uses_complete_candidate_not_intermediate_state(monkeypatch, direction):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    contour = CONTOUR.S.neutral(); contour['jaw']['right'] = -.2
    if direction == 'to-slim': put(owner, {'recipe': contour}, CONTOUR.OP)
    else: put(owner, recipe(.3, -.2, linked=False))
    state = CONTOUR.capture(engine, C.capture(engine))
    modules = {C.OP: recipe(.3, -.2) if direction == 'to-slim' else recipe(),
        CONTOUR.OP: {'recipe': CONTOUR.S.neutral() if direction == 'to-slim' else contour}}
    after = SC.apply_modules(state, modules); REPLAY.replay_preset(engine, after)
    actual = values(owner)
    assert actual[C.OP] == modules[C.OP]['recipe']
    assert actual[CONTOUR.OP] == modules[CONTOUR.OP]['recipe']
    assert len(owner.commits) == len(calls) == 1 and calls[0][1]['strict_local'] is True


def test_contour_only_preset_cannot_hide_an_already_active_v2(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(.3, -.2))
    state = CONTOUR.capture(engine)
    contour = CONTOUR.S.neutral(); contour['temple']['left'] = .4
    CONTOUR.install(state, {'recipe': contour}); before = owner.snapshot()
    assert C.FIELD not in state
    with pytest.raises(ValueError, match='active lnx.face_contour.v1'):
        REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_neutral_v2_reset_leaves_existing_legacy_and_contour_intent_unchanged(monkeypatch):
    # Render is mocked: retained other effects may still need analysis/native code.
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(.3, -.2, linked=False))
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/slim_face', -.4)
    owner.value = P.set_override(owner.value, 'face', FACE, CONTOUR.OP, '/jaw/left', .2)
    legacy_before = [deepcopy(row) for row in owner.value['overrides'] if row['operation_id'] != C.OP]
    monkeypatch.setattr(N, 'available', lambda: False); analysis['excluded'] = None
    state = C.capture(engine); C.install(state, recipe()); REPLAY.replay_preset(engine, state)
    assert values(owner)[C.OP] == S.neutral()
    assert [row for row in owner.value['overrides'] if row['operation_id'] != C.OP] == legacy_before
    assert calls[-1][1]['strict_local'] is True


def test_unchanged_active_v2_still_uses_strict_target_renderer(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(.3, -.2))
    REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_link_only_neutral_scope_admission_preserves_zero_side_values(monkeypatch):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    analysis['excluded'] = None; monkeypatch.setattr(N, 'available', lambda: False)
    state = C.capture(engine); C.install(state, recipe(linked=False))
    REPLAY.replay_preset(engine, state)
    assert [row for row in owner.value['overrides'] if row['operation_id'] == C.OP] == [
        {'scope': 'face', 'target_id': FACE, 'operation_id': C.OP,
         'parameter_path': '/linked', 'value': False}]
    assert calls[-1][1]['strict_local'] is True


def test_failed_target_render_restores_graph_and_outer_history_rollback_can_replay(monkeypatch):
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    from lumaretouch_engine.preset_transaction import apply_with_rollback, PresetApplyError
    engine, initial, _, _, _ = replay_fixture(monkeypatch)
    owner = PeopleGraphOwner(initial.snapshot()); engine._people_owner = lambda: owner
    before_graph = owner.snapshot(); before = C.capture(engine); after = deepcopy(before)
    C.install(after, recipe(.3, -.2, linked=False)); calls = []
    def render(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        if len(calls) == 1: raise RuntimeError('authored target-render refusal')
        return {'event': 'frame'}
    engine._replay_state = render
    with pytest.raises(PresetApplyError) as error:
        apply_with_rollback(lambda state, **kwargs: REPLAY.replay_preset(engine, state, **kwargs),
            before, after, preset_id='slim-v2', emit=lambda event: None,
            invalidate=lambda: pytest.fail('Rollback must remain available'))
    assert error.value.rolled_back is True and len(calls) == 2
    assert calls[0][1]['strict_local'] is True and calls[1][1]['mode'] == 'preset_rollback'
    actual = owner.snapshot()
    # Three changed scalar leaves advance the staged graph; rollback adds one.
    assert actual['revision'] == before_graph['revision'] + 4 and owner.fence == 2
    assert {key: value for key, value in actual.items() if key != 'revision'} == {
        key: value for key, value in before_graph.items() if key != 'revision'}


def test_generic_preset_does_not_guess_between_multiple_enabled_faces(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    other, _ = graph(face_id='neighbour-face'); owner.value['faces']['neighbour-face'] = other['faces']['neighbour-face']
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.3, -.2))
    with pytest.raises(ValueError, match='one explicit unambiguous enabled face'):
        REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_unrelated_replay_is_not_blocked_by_missing_v2_target_or_document(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    engine._people_targets.clear(); engine._docs.clear()
    REPLAY.replay_preset(engine, {})
    assert not owner.commits and len(calls) == 1 and C.FIELD not in calls[0][0]


def test_explicit_people_selection_accepts_three_intent_leaves_not_version_or_geometry():
    from lumaretouch_engine import people_batch_transfer as B
    value, _ = graph(); selected = {'source_ref': P.face_ref(value['faces'][FACE]),
        'selection': {C.OP: list(LEAVES)}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/version', '/slim_face', '/face_ref', '/face_skin', '/landmarks', '/mask', '/control_points', '/supported'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [path]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


@pytest.mark.parametrize('target_policy', ['explicit_face_map', 'confirmed_person_only'])
def test_selected_leaf_transfer_preserves_other_side_target_assets_and_owner_fences(target_policy):
    from lumaretouch_engine import people_transfer_adapter as T
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for value, face_id in ((source, 'source-face'), (target, FACE)):
        value['persons']['confirmed-person'] = {'anonymous': True}
        value['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    source = P.set_override(source, 'face', 'source-face', C.OP, '/linked', True)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/left', -.4)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/right', .8)
    target = P.set_override(target, 'face', FACE, C.OP, '/linked', False)
    target = P.set_override(target, 'face', FACE, C.OP, '/right', .2)
    scope = 'project' if target_policy == 'confirmed_person_only' else None
    source_owner = endpoint(source, 'source', scope=scope); target_owner = endpoint(target, 'target', scope=scope)
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    selection = {C.OP: ['/linked', '/left']}
    if target_policy == 'confirmed_person_only':
        payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), 'e' * 64,
            selection, A.defaults(), **kwargs)
    else:
        payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
            [P.face_ref(target['faces'][FACE])], selection, A.defaults(), **kwargs)
        payload['target_policy'] = target_policy
    candidate = T.candidate(payload, source, target, **kwargs)
    assert payload['parameters'] == [
        {'operation_id': C.OP, 'parameter_path': '/left', 'value': -.4},
        {'operation_id': C.OP, 'parameter_path': '/linked', 'value': True}]
    assert {leaf['parameter_path']: leaf['value'] for leaf in candidate['overrides']
        if leaf['operation_id'] == C.OP} == {'/linked': True, '/left': -.4, '/right': .2}
    assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    changed = deepcopy(target_owner); changed['source_proof'] = {'asset_sha256': 'f' * 64,
        'creative_source': None, 'original_sha256': 'f' * 64}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **{**kwargs, 'target_owner': changed})


@pytest.mark.parametrize('target_policy', ['explicit_face_map', 'confirmed_person_only'])
@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('refused_target', [None, 'target-b'])
def test_each_original_or_derived_target_recalculates_own_full_source_not_donor_geometry(monkeypatch, target_policy, derived, refused_target):
    """Actual preflight routing, mocked pixels only; no render-quality claim."""
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL
    source, _ = graph(face_id='source-face')
    target_a, _ = graph('e' * 64, 'target-a-face'); target_b, _ = graph('f' * 64, 'target-b-face')
    states = {'source': source, 'target-a': target_a, 'target-b': target_b}
    face_ids = {'source': 'source-face', 'target-a': 'target-a-face', 'target-b': 'target-b-face'}
    if target_policy == 'confirmed_person_only':
        for identity, value in states.items():
            value['persons']['confirmed-person'] = {'anonymous': True}
            value['links'] = [{'face_instance_id': face_ids[identity], 'person_id': 'confirmed-person',
                'state': 'confirmed', 'confirmation_revision': 0}]
    params = recipe(.3, -.2, linked=False)
    for path, value in A.leaves(params['recipe']).items():
        source = P.set_override(source, 'face', 'source-face', C.OP, path, value)
    states['source'] = source
    for identity in ('target-a', 'target-b'):
        states[identity] = P.set_override(states[identity], 'face', face_ids[identity], COLOUR.OP, '/tint', -.2)
        states[identity]['faces'][face_ids[identity]]['local_assets']['target-only']['content_sha256'] = (
            '1' if identity == 'target-a' else '2') * 64
    owner = Owner(source)
    rows = [{'document_id': identity, 'path': identity + '.jpg', 'state': {}} for identity in states]
    if derived:
        for row in rows[1:]: row['state']['_creative_base'] = {'fixture': row['document_id'] + ' immutable source'}
    def proof(value, identity):
        out = endpoint(value, identity, scope='project' if target_policy == 'confirmed_person_only' else None)
        if derived and identity != 'source':
            asset = value['faces'][face_ids[identity]]['asset_sha256']
            out['source_proof']['creative_source'] = {'sha256': asset, 'width': 640, 'height': 480}
            out['source_proof']['original_sha256'] = '3' * 64
        return out
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    batch = SimpleNamespace(versions=versions,
        documents=SimpleNamespace(rows=lambda: rows, current_index=lambda: 0, remember_current=lambda: None),
        target_indices=lambda docs: ([1, 2], []))
    engine = SimpleNamespace(_people_bind=lambda: None, _people_owner=lambda: owner,
        _batch_controller=lambda: batch, _document_versions=lambda: versions,
        _body_bank=lambda: pytest.fail('Slim v2 does not acquire body coverage'))
    monkeypatch.setattr(B.V, 'row_snapshot', lambda actual_engine, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I, 'proof', lambda actual_engine, row, value: proof(value, row['document_id']))
    def verify(actual_engine, row, value, expected):
        assert expected == proof(value, row['document_id']); return expected
    monkeypatch.setattr(I, 'verify', verify)
    monkeypatch.setattr(B.SOURCE, 'row_proof', lambda row: proof(states[row['document_id']], row['document_id'])['source_proof'])
    def verify_source(row, expected):
        assert expected == B.SOURCE.row_proof(row); return expected
    monkeypatch.setattr(B.SOURCE, 'verify_row', verify_source)
    renders = []
    expected_parameters = [{'operation_id': C.OP, 'parameter_path': path, 'value': value}
        for path, value in sorted(A.leaves(params['recipe']).items())]
    def render(actual_engine, row, state, document_id, revision, *, people_graph):
        assert actual_engine is engine and row['document_id'] == document_id
        assert state is row['state'] and revision == '2' and document_id != 'source'
        target = states[document_id]; face_id = face_ids[document_id]
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert people_graph[key] == target[key]
        added = [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']]
        assert sorted(added, key=lambda leaf: leaf['parameter_path']) == [
            {'scope': 'face', 'target_id': face_id, **leaf} for leaf in expected_parameters]
        assert all(leaf in people_graph['overrides'] for leaf in target['overrides'])
        renders.append((document_id, deepcopy(people_graph)))
        if document_id == refused_target:
            raise ValueError('Target-owned slim v2 renderer refused spatial or photometric support')
        return None, {'fixture': 'routing only'}
    monkeypatch.setattr(FULL, 'render', render)
    plans = []
    def freeze(workspace, source_id, revision, path, modules, params, policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda plan: {},
        emit=lambda event: None, emit_result=lambda request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-slim-v2',
        'docs': ['target-a', 'target-b'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': P.face_ref(source['faces']['source-face']), 'selection': {C.OP: list(LEAVES)},
            'target_policy': 'explicit_face_map', 'source': proof(source, 'source'), 'targets': [
                {'target': proof(states[identity], identity),
                 'target_refs': [P.face_ref(states[identity]['faces'][face_ids[identity]])]}
                for identity in ('target-a', 'target-b')]}}
    if target_policy == 'confirmed_person_only':
        request['people_transfer'] = {key: value for key, value in request['people_transfer'].items()
            if key not in ('source', 'targets')}
        request['people_transfer']['target_policy'] = target_policy
    before = deepcopy(states); B.preflight(engine, controller, request)
    assert states == before and not owner.commits
    assert [identity for identity, _ in renders] == ['target-a', 'target-b']
    result = replies[-1]
    assert (result['ok'], result['blocked']) == ((1, 1) if refused_target else (2, 0))
    for index, identity in enumerate(('target-a', 'target-b')):
        payload = result['targets'][index]['people_transfer']
        if identity == refused_target:
            assert payload is None and plans[0][index].people_json is None
            assert 'Target-owned slim v2 renderer refused' in result['targets'][index]['blocked']
        else:
            assert payload['parameters'] == expected_parameters
            assert payload['target_refs'] == [P.face_ref(states[identity]['faces'][face_ids[identity]])]
            assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
            assert not any('coverage' in key or 'support' in key for key in payload)
            assert json.loads(plans[0][index].people_json) == payload


def test_capture_authenticates_live_baseline_not_parked_document_state(monkeypatch):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, _, current = engine_fixture(monkeypatch)
    current['audit_marker'] = 'live'
    engine._docs[0]['state'] = {'audit_marker': 'parked'}
    observed = []
    def source_proof(row):
        observed.append(deepcopy(row['state']))
        assert row['state']['audit_marker'] == 'live'
        return {'asset_sha256': ASSET, 'creative_source': None, 'original_sha256': ASSET}
    monkeypatch.setattr(I.SOURCE, 'row_proof', source_proof)
    captured = C.capture(engine)
    assert C.params_of(captured) == recipe() and observed == [current]
    assert engine._docs[0]['state'] == {'audit_marker': 'parked'}
    assert not owner.commits


@pytest.mark.parametrize('fault', ['document', 'epoch', 'owner', 'target'])
def test_neutral_reset_never_bypasses_changed_owner_or_face(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(.3, -.2))
    state = C.capture(engine); C.install(state, recipe())
    analysis['excluded'] = None; monkeypatch.setattr(N, 'available', lambda: False)
    if fault == 'document': engine._docs[0]['document_id'] = 'other-document'
    elif fault == 'epoch': engine._document_versions().workspace = 'other-workspace'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    else: engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_explicit_legacy_zero_shadow_allows_v2_without_erasing_inherited_history(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'group', 'preserved', A.DEFORM, '/slim_face', .4)
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/slim_face', 0.)
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.3, -.2))
    REPLAY.replay_preset(engine, state)
    assert values(owner)[A.DEFORM]['slim_face'] == 0.
    assert values(owner)[C.OP] == recipe(.3, -.2)['recipe']
    assert all(row in owner.value['overrides'] for row in before['overrides'])
    assert len(owner.commits) == len(calls) == 1
