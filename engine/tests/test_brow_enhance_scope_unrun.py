# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: original-brow contrast scope and target-owned transfer.

LNX-REF-PC-32471-C-18765fa8ea retains signed existing-brow contrast intent:
negative reduces, positive strengthens. Added brow makeup remains separate.
Synthetic observations and mocked native/full-render boundaries specify the
contracts, not real inference, photographic quality or runtime acceptance.
No product imports, test collection/execution, build or typecheck were run.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import brow_enhance_scope as C, brow_enhance_state as S
from lumaretouch_engine import brow_enhance_native as N, brow_makeup_state as MAKEUP
from lumaretouch_engine import people_state as P, people_algorithms as A
from lumaretouch_engine import people_scope as REPLAY, scope as SC
from lumaretouch_engine import skin_colour_scope as COLOUR
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, isolate_other_captures)

LEAVES = ('/linked', '/left', '/right')


def recipe(left=0., right=None, *, linked=True):
    return {'recipe': {'version': 1, 'linked': linked,
        'left': left, 'right': left if right is None else right}}


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


def replay_fixture(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); calls = []
    def replay(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        return {'event': 'frame', 'render_ms': 0}
    engine._replay_state = replay
    return engine, owner, analysis, current, calls


def put(owner, params):
    for path, value in A.leaves(params['recipe']).items():
        owner.value = P.set_override(owner.value, 'face', FACE, C.OP, path, value)


def values(owner):
    return A.recipes(resolve(owner.snapshot(), FACE, A.defaults()))


def retain_makeup(owner):
    makeup = MAKEUP.neutral()
    makeup['linked'] = False
    makeup['left'].update(pattern='fine', strength=.4, colour='#463428')
    makeup['right'].update(pattern='tail', strength=.2, colour='#3A3038')
    for path, value in A.leaves(makeup).items():
        owner.value = P.set_override(owner.value, 'face', FACE, MAKEUP.OP, path, value)
    return makeup


def test_distinct_original_brow_contrast_registration_not_added_brow_makeup():
    assert C.OP == 'lnx.brow_enhance.v1' and S.VERSION == 1
    assert S.CONTROL_ID == 'LNX-REF-PC-32471-C-18765fa8ea'
    assert C.OP != MAKEUP.OP and C.OP not in A.GEOMETRY
    assert C.OP not in SC.DERIVED_PARAMETER_OPS
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True
    assert SC.MODULES[C.OP]['transferable'] is True
    assert SC.MODULES[C.OP]['label'] == '眉毛增强（原有眉毛对比度，左右独立正负强度）'
    assert A.defaults()[C.OP] == {'/linked': True, '/left': 0., '/right': 0.}
    assert S.neutral() == recipe()['recipe']
    assert not S.active(S.neutral()) and not S.active(recipe(linked=False)['recipe'])


@pytest.mark.parametrize('left,right,linked', [(-1., 1., False), (.4, -.7, False),
    (0., 0., False), (1., 1., True), (-1., -1., True), (.4, .4, True)])
def test_only_link_flag_and_signed_amounts_round_trip(left, right, linked):
    params = recipe(left, right, linked=linked)
    assert C.check_params(params) == SC.check_params(C.OP, params) == params
    portable = {'schema': SC.PRESET_SCHEMA, 'id': 'brow-enhance', 'name': 'Original brow contrast',
        'kind': 'portrait', 'modules': {C.OP: params}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(portable)))
    assert loaded['modules'] == {C.OP: params}
    assert set(loaded['modules'][C.OP]['recipe']) == {'version', 'linked', 'left', 'right'}
    assert set(A.leaves(loaded['modules'][C.OP]['recipe'])) == set(LEAVES)


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'),
    float('-inf'), -1.01, 1.01, 10**1000, -(10**1000)])
def test_invalid_signed_amount_refuses_without_mutation(monkeypatch, side, value):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state); params = recipe(linked=False)
    params['recipe'][side] = value
    with pytest.raises(ValueError): C.install(state, params)
    assert state == before and not owner.commits


@pytest.mark.parametrize('left,right', [(0., .01), (.5, -.5), (-1., 1.)])
def test_linked_requires_equal_sides_and_never_averages(monkeypatch, left, right):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state); params = recipe(left, right)
    with pytest.raises(ValueError): C.check_params(params)
    with pytest.raises(SC.ScopeError): SC.check_params(C.OP, params)
    with pytest.raises(ValueError): C.install(state, params)
    assert state == before and not owner.commits


@pytest.mark.parametrize('raw', [None, {}, {'version': 1},
    {'linked': True, 'left': 0., 'right': 0.},
    {'version': True, 'linked': True, 'left': 0., 'right': 0.},
    {'version': 2, 'linked': True, 'left': 0., 'right': 0.},
    {'version': 1, 'linked': 1, 'left': 0., 'right': 0.},
    {'version': 1, 'linked': True, 'left': 0.}, {'version': 1, 'amount': .3},
    {'version': 1, 'linked': True, 'left': MAKEUP.neutral_brow(), 'right': MAKEUP.neutral_brow()}])
def test_exact_schema_is_not_makeup_or_single_amount(raw):
    with pytest.raises(ValueError): C.check_params({'recipe': raw})


@pytest.mark.parametrize('key', ['face_ref', 'owner', 'source', 'face_skin', 'excluded',
    'landmarks', 'analysis', 'geometry', 'control_points', 'mask', 'coverage',
    'reference_samples', 'forehead_samples', 'brow_samples', 'resolved_contrast',
    'supported', 'pattern', 'colour', 'strength', 'reference'])
def test_transport_rejects_all_source_copies_and_resolved_evidence(key):
    params = recipe(.3, -.2, linked=False)
    with pytest.raises(ValueError): C.check_params({**params, key: {}})
    params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


def test_workflow_exports_only_canonical_intent_not_source_measurements(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); params = recipe(.35, -.2, linked=False)
    put(owner, params); makeup = retain_makeup(owner); before = owner.snapshot()
    captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert SC.params_of(captured, [C.OP]) == {C.OP: params}
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_brow_enhance_supported'] is True and captured[C.REQUESTED] is False
    assert C.owner_identity(captured) == {'document_id': 'target-document', 'epoch': 'workspace',
        'people_scope': 'project', 'source_proof': {'asset_sha256': ASSET,
            'creative_source': None, 'original_sha256': ASSET}}
    assert not {'face_skin', 'landmarks', 'reference_samples', 'resolved_contrast'} & set(captured)
    assert values(owner)[MAKEUP.OP] == makeup and owner.snapshot() == before
    assert engine._people_analyses[ASSET][FACE] is analysis and current == {} and not owner.commits


@pytest.mark.parametrize('fault', ['face-skin', 'observation', 'excluded', 'ref', 'model',
    'landmark-bytes', 'landmark-count', 'synthetic', 'dimensions', 'donor-analysis', 'observation-source'])
def test_capture_requires_target_owned_observation_and_actual_478(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'face-skin': analysis['face_skin'] = None
    elif fault == 'observation': analysis.pop('face_skin_observation')
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'model': analysis['face_skin_observation']['semantic_model_sha256'] = 'f' * 64
    elif fault == 'observation-source': analysis['face_skin_observation']['source_sha256'] = 'e' * 64
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
    assert captured['_brow_enhance_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3))
    assert not owner.commits


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged', 'no-document'])
def test_selection_requires_enabled_exact_face_and_document_owner(monkeypatch, fault):
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


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('observed', [False, True])
def test_observed_admission_and_native_readiness_are_independent(monkeypatch, native, observed):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: native)
    if not observed: analysis.pop('face_skin_observation')
    captured = C.capture(engine)
    assert captured['_brow_enhance_supported'] is observed
    assert captured['_brow_enhance_native_available'] is native
    C.install(captured, recipe(linked=False))
    assert C.params_of(captured) == recipe(linked=False)
    if native and observed:
        C.install(captured, recipe(-.4)); assert C.params_of(captured) == recipe(-.4)
    else:
        with pytest.raises(ValueError): C.install(captured, recipe(-.4))
    assert not owner.commits


def test_install_only_changes_transport_and_keeps_generic_derived_fence(monkeypatch):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3, -.2, linked=False)})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET] and after[C.OWNER] == before[C.OWNER]
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe())
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    with pytest.raises(ValueError): SC.apply_modules({}, {C.OP: recipe(.3)})
    assert not owner.commits


@pytest.mark.parametrize('amount', [0., .3])
def test_source_proof_mismatch_refuses_even_neutral(monkeypatch, amount):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, _, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': 'e' * 64,
        'creative_source': None, 'original_sha256': 'e' * 64})
    state = C.capture(engine); before = deepcopy(state)
    assert state['_brow_enhance_supported'] is False
    with pytest.raises(ValueError, match='有效来源'): C.install(state, recipe(amount))
    assert state == before and not owner.commits


@pytest.mark.parametrize('derived_snapshot', ['current', 'previous'])
def test_generic_derived_restore_cannot_bypass_explicit_people_transfer(monkeypatch, derived_snapshot):
    from lumaretouch_engine import creative_derived_transfer as D
    current = {}; previous = {}
    (current if derived_snapshot == 'current' else previous)['_creative_base'] = {'fixture': 'derived'}
    monkeypatch.setattr(D, 'involved', lambda state, **kwargs: True)
    with pytest.raises(SC.ScopeError, match='历史'):
        SC.restore_modules(current, previous, [C.OP])


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged', 'source',
    'document', 'owner', 'epoch', 'proof', 'source-kind', 'original-source'])
def test_replay_rechecks_live_owner_and_evidence_not_saved_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3, -.2, linked=False))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'analysis': analysis['excluded'] = None
    elif fault == 'target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    elif fault == 'source': engine._people_source = lambda: {'sha256': 'e' * 64, 'width': 640, 'height': 480}
    elif fault == 'document': engine._docs[0]['document_id'] = 'other-document'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    elif fault == 'epoch': engine._document_versions().workspace = 'other-workspace'
    elif fault == 'proof': state.pop(C.OWNER)
    elif fault == 'source-kind':
        state[C.OWNER]['source_proof']['creative_source'] = {'sha256': ASSET, 'width': 640, 'height': 480}
    else: state[C.OWNER]['source_proof']['original_sha256'] = 'f' * 64
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


@pytest.mark.parametrize('linked', [False, True])
def test_neutral_recovery_requires_no_anatomy_or_native_and_retains_makeup(monkeypatch, linked):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(.3)); makeup = retain_makeup(owner)
    engine._people_analyses.clear(); monkeypatch.setattr(N, 'available', lambda: False)
    state = C.capture(engine); C.install(state, recipe(linked=linked))
    REPLAY.replay_preset(engine, state)
    assert values(owner)[C.OP] == recipe(linked=linked)['recipe']
    assert values(owner)[MAKEUP.OP] == makeup
    assert calls[-1][1]['strict_local'] is True and not engine._people_analyses


@pytest.mark.parametrize('fault', ['document', 'epoch', 'owner', 'target'])
def test_neutral_recovery_still_fences_exact_owner_and_face(monkeypatch, fault):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(.3)); state = C.capture(engine); C.install(state, recipe(linked=False))
    engine._people_analyses.clear(); monkeypatch.setattr(N, 'available', lambda: False)
    if fault == 'document': engine._docs[0]['document_id'] = 'other-document'
    elif fault == 'epoch': engine._document_versions().workspace = 'other-workspace'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    else: engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


@pytest.mark.parametrize('start,end', [(recipe(), recipe(.4)),
    (recipe(.1, -.2, linked=False), recipe(-.3)),
    (recipe(.4), recipe(.2, -.5, linked=False))])
@pytest.mark.parametrize('refused', [False, True])
def test_complete_atomic_recipe_renders_with_other_intent_or_rolls_back(monkeypatch, start, end, refused):
    engine, owner, analysis, _, _ = replay_fixture(monkeypatch)
    put(owner, start); makeup = retain_makeup(owner)
    owner.value = P.set_override(owner.value, 'group', 'preserved', COLOUR.OP, '/tint', -.25)
    owner.value = P.set_override(owner.value, 'group', 'preserved', A.DEFORM, '/big_eye', .2)
    before = owner.snapshot(); rendered = []
    def render(state, **kwargs):
        candidate = owner.snapshot(); rendered.append(candidate)
        assert kwargs['strict_local'] is True
        assert values(owner)[C.OP] == end['recipe'] and values(owner)[MAKEUP.OP] == makeup
        assert values(owner)[COLOUR.OP]['tint'] == -.25 and values(owner)[A.DEFORM]['big_eye'] == .2
        for field in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert candidate[field] == before[field]
        assert all(leaf in candidate['overrides'] for leaf in before['overrides'] if leaf['operation_id'] != C.OP)
        if refused: raise RuntimeError('complete candidate brow or composition support refused')
        return {'event': 'frame'}
    engine._replay_state = render; state = C.capture(engine); C.install(state, end)
    if refused:
        with pytest.raises(RuntimeError, match='composition support refused'): REPLAY.replay_preset(engine, state)
        assert owner.snapshot() == before and len(owner.commits) == 2
    else:
        REPLAY.replay_preset(engine, state); assert len(owner.commits) == 1
    assert len(rendered) == 1 and engine._people_analyses[ASSET][FACE] is analysis


def test_unchanged_active_intent_still_uses_complete_strict_renderer(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(-.3)); REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_full_render_failure_restores_graph_and_existing_outer_history(monkeypatch):
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    from lumaretouch_engine.preset_transaction import apply_with_rollback, PresetApplyError
    engine, initial, _, _, _ = replay_fixture(monkeypatch)
    makeup = retain_makeup(initial)
    owner = PeopleGraphOwner(initial.snapshot()); engine._people_owner = lambda: owner
    before_graph = owner.snapshot(); before = C.capture(engine); after = deepcopy(before)
    C.install(after, recipe(.3)); calls = []
    def render(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        if len(calls) == 1: raise RuntimeError('target actual brow or forehead support refused')
        return {'event': 'frame'}
    engine._replay_state = render
    with pytest.raises(PresetApplyError) as error:
        apply_with_rollback(lambda state, **kwargs: REPLAY.replay_preset(engine, state, **kwargs),
            before, after, preset_id='brow-enhance', emit=lambda event: None,
            invalidate=lambda: pytest.fail('Rollback must remain available'))
    assert error.value.rolled_back is True and len(calls) == 2
    assert calls[0][1]['strict_local'] is True and calls[1][1]['mode'] == 'preset_rollback'
    actual = owner.snapshot()
    assert actual['revision'] == before_graph['revision'] + 2 and owner.fence == 2
    assert {key: value for key, value in actual.items() if key != 'revision'} == {
        key: value for key, value in before_graph.items() if key != 'revision'}
    assert values(owner)[MAKEUP.OP] == makeup


def test_dormant_unlinked_intent_cannot_silently_fall_back_to_legacy(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, recipe(linked=False)); state = C.capture(engine)
    engine._people_managed = lambda: False
    with pytest.raises(ValueError, match='眉毛增强'): REPLAY.replay_preset(engine, state)
    assert not calls and not owner.commits


def test_generic_preset_never_guesses_between_enabled_faces(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    other, _ = graph(face_id='neighbour'); owner.value['faces']['neighbour'] = other['faces']['neighbour']
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.3))
    with pytest.raises(ValueError, match='one explicit unambiguous enabled face'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_capture_authenticates_live_state_not_parked_row(monkeypatch):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, _, current = engine_fixture(monkeypatch)
    current['audit_marker'] = 'live'; engine._docs[0]['state'] = {'audit_marker': 'parked'}; seen = []
    def source_proof(row):
        seen.append(deepcopy(row['state'])); assert row['state']['audit_marker'] == 'live'
        return {'asset_sha256': ASSET, 'creative_source': None, 'original_sha256': ASSET}
    monkeypatch.setattr(I.SOURCE, 'row_proof', source_proof)
    assert C.params_of(C.capture(engine)) == recipe() and seen == [current]
    assert engine._docs[0]['state'] == {'audit_marker': 'parked'} and not owner.commits


@pytest.mark.parametrize('reuse_original', [False, True])
def test_derived_capture_uses_own_effective_analysis_never_original_donor(monkeypatch, reuse_original):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, original, current = engine_fixture(monkeypatch)
    derived = 'e' * 64; target, own = graph(derived); owner.value = target
    engine._people_source = lambda: {'sha256': derived, 'width': 640, 'height': 480}
    engine._people_cursors = {derived: FACE}
    engine._people_targets = {derived: {'scope': 'face', 'target_id': FACE,
        'face_ref': P.face_ref(target['faces'][FACE])}}
    engine._people_analyses = {ASSET: {FACE: original}, derived: {FACE: original if reuse_original else own}}
    current['_creative_base'] = {'fixture': 'derived baseline, not product pixels'}
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': derived,
        'creative_source': {'sha256': derived, 'width': 640, 'height': 480}, 'original_sha256': ASSET})
    put(owner, recipe(.3, -.2, linked=False)); captured = C.capture(engine)
    assert captured['_brow_enhance_supported'] is (not reuse_original)
    if reuse_original:
        with pytest.raises(ValueError): C.params_of(captured)
    else:
        assert C.params_of(captured) == recipe(.3, -.2, linked=False)
        assert C.owner_identity(captured)['source_proof']['asset_sha256'] == derived
    with pytest.raises(ValueError, match='合成来源'): C.install(captured, recipe())
    assert not owner.commits


def test_dormant_link_intent_round_trips_project_and_history_without_makeup_conversion():
    from lumaretouch_engine import people_project as PROJECT
    old, _ = graph(); edited = P.set_override(old, 'face', FACE, C.OP, '/linked', False)
    source_proof = endpoint(old, 'target-document', scope='project')['source_proof']
    payload = {'people_graph': edited, 'source_proof': source_proof,
        'undo': [{'_people_state': old, 'source_proof': deepcopy(source_proof)}],
        'redo': [{'_people_state': edited, 'source_proof': deepcopy(source_proof)}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False)); PROJECT.validate_records(restored)
    assert restored == payload
    for state, linked in ((restored['people_graph'], False),
            (restored['undo'][0]['_people_state'], True), (restored['redo'][0]['_people_state'], False)):
        materialized = A.recipes(resolve(P.check(state), FACE, A.defaults()))
        assert materialized[C.OP] == recipe(linked=linked)['recipe'] and not S.active(materialized[C.OP])
        assert materialized[MAKEUP.OP] == MAKEUP.neutral()
        assert state['faces'] == old['faces'] and state['links'] == old['links']


def test_batch_selection_accepts_only_link_and_two_signed_leaves():
    from lumaretouch_engine import people_batch_transfer as B
    state, _ = graph(); selected = {'source_ref': P.face_ref(state['faces'][FACE]),
        'selection': {C.OP: list(LEAVES)}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/version', '/amount', '/strength', '/face_ref', '/landmarks', '/excluded',
            '/mask', '/reference_samples', '/forehead_samples', '/resolved_contrast'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [path]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


@pytest.mark.parametrize('policy', ['explicit_face_map', 'confirmed_person_only'])
def test_parameter_transfer_preserves_target_assets_and_other_intent(policy):
    from lumaretouch_engine import people_transfer_adapter as T
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for state, face_id in ((source, 'source-face'), (target, FACE)):
        state['persons']['confirmed-person'] = {'anonymous': True}
        state['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    params = recipe(-.4, .2, linked=False)
    for path, value in A.leaves(params['recipe']).items():
        source = P.set_override(source, 'face', 'source-face', C.OP, path, value)
    target = P.set_override(target, 'face', FACE, COLOUR.OP, '/tint', -.3)
    target_owner = Owner(target); makeup = retain_makeup(target_owner); target = target_owner.snapshot()
    owner_scope = 'project' if policy == 'confirmed_person_only' else None
    source_owner = endpoint(source, 'source', scope=owner_scope); target_owner = endpoint(target, 'target', scope=owner_scope)
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    selection = {C.OP: list(LEAVES)}
    if policy == 'confirmed_person_only':
        payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), 'e' * 64,
            selection, A.defaults(), **kwargs)
    else:
        payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
            [P.face_ref(target['faces'][FACE])], selection, A.defaults(), **kwargs)
        payload['target_policy'] = policy
    candidate = T.candidate(payload, source, target, **kwargs)
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': path, 'value': value}
        for path, value in sorted(A.leaves(params['recipe']).items())]
    materialized = A.recipes(resolve(candidate, FACE, A.defaults()))
    assert materialized[C.OP] == params['recipe'] and materialized[MAKEUP.OP] == makeup
    assert materialized[COLOUR.OP]['tint'] == -.3
    assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    changed = deepcopy(target_owner); changed['source_proof'] = {'asset_sha256': 'f' * 64,
        'creative_source': None, 'original_sha256': 'f' * 64}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **{**kwargs, 'target_owner': changed})


@pytest.mark.parametrize('selection', [['/left'], ['/linked'], list(LEAVES)])
def test_partial_transfer_never_repairs_target_link_state_or_copies_unselected_side(selection):
    from lumaretouch_engine import people_transfer_adapter as T
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for path, value in A.leaves(recipe(.4)['recipe']).items():
        source = P.set_override(source, 'face', 'source-face', C.OP, path, value)
    for path, value in A.leaves(recipe(.1, -.2, linked=False)['recipe']).items():
        target = P.set_override(target, 'face', FACE, C.OP, path, value)
    source_owner = endpoint(source, 'source'); target_owner = endpoint(target, 'target')
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
        [P.face_ref(target['faces'][FACE])], {C.OP: selection}, A.defaults(), **kwargs)
    payload['target_policy'] = 'explicit_face_map'; before = deepcopy(target)
    candidate = T.candidate(payload, source, target, **kwargs)
    if selection == ['/linked']:
        with pytest.raises(ValueError): A.recipes(resolve(candidate, FACE, A.defaults()))
    else:
        expected = recipe(.4, -.2, linked=False) if selection == ['/left'] else recipe(.4)
        assert A.recipes(resolve(candidate, FACE, A.defaults()))[C.OP] == expected['recipe']
    assert target == before and {item['parameter_path'] for item in payload['parameters']} == set(selection)


def test_capture_admission_is_not_actual_brow_acceptance_and_full_render_can_refuse(monkeypatch):
    from lumaretouch_engine import brow_enhance_layer as L
    import numpy as np
    engine, owner, analysis, _, _ = replay_fixture(monkeypatch)
    # This basic capture fixture authenticates finite/digested 478 points, but
    # all coordinates coincide. It must not pretend visible brows were found.
    owner.value['faces'][FACE]['evidence'].update(source_width=10, source_height=8)
    analysis['evidence'] = deepcopy(owner.value['faces'][FACE]['evidence'])
    engine._people_source = lambda: {'sha256': ASSET, 'width': 10, 'height': 8}
    captured = C.capture(engine)
    assert captured['_brow_enhance_supported'] is True
    C.install(captured, recipe(.3)); before = owner.snapshot(); calls = []
    def render(state, **kwargs):
        calls.append(kwargs)
        return L.prepare(P.face_ref(owner.value['faces'][FACE]), analysis,
            np.full((8, 10, 3), .5, np.float32), values(owner)[C.OP], byte_budget=512*1024**2)
    engine._replay_state = render
    with pytest.raises(ValueError, match='brow'): REPLAY.replay_preset(engine, captured)
    assert calls[0]['strict_local'] is True and len(owner.commits) == 2
    assert owner.snapshot() == before


@pytest.mark.parametrize('policy', ['explicit_face_map', 'confirmed_person_only'])
@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('fault', [None, 'target-forehead', 'target-brow', 'copied-source-analysis'])
def test_full_target_review_remeasures_actual_brows_and_adjacent_forehead(monkeypatch, policy, derived, fault):
    """Real target evidence/contrast admission; only full render/native doubled.

    Each source has its own authentic synthetic observation binding and RGB.
    The complete-render boundary executes actual geometry/skin/exclusion and
    contrast support. This asserts neither real inference nor native quality.
    """
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL, brow_enhance_layer as L
    from lumaretouch_engine.people_render_runtime import verify_analysis
    from test_brow_enhance_support_unrun import synthetic_observation, MockNative, _geometry_mask
    import numpy as np
    settings = {'source': (ASSET, 'source-face', .9),
        'target-a': ('e' * 64, 'target-a-face', 1.), 'target-b': ('f' * 64, 'target-b-face', 1.1)}
    states = {}; analyses = {}; sources = {}; face_ids = {}
    for identity, (asset, face_id, illumination) in settings.items():
        state, _ = graph(asset, face_id)
        _, analysis, rgb = synthetic_observation()
        analysis = deepcopy(analysis); rgb = np.asarray(rgb * np.float32(illumination), dtype=np.float32)
        # This full-target routing fixture treats its independently generated
        # RGB as the immutable source, not as the helper's 1024-source proxy.
        # Bind both durable face evidence and its analysis to those true extents.
        analysis['evidence'].update(source_width=rgb.shape[1], source_height=rgb.shape[0])
        state['faces'][face_id]['evidence'] = deepcopy(analysis['evidence'])
        state['faces'][face_id]['box'] = [.05, .03, .95, .97]
        analysis['face_ref'] = P.face_ref(state['faces'][face_id])
        analysis['face_skin_observation']['source_sha256'] = asset
        if policy == 'confirmed_person_only':
            state['persons']['confirmed-person'] = {'anonymous': True}
            state['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
                'state': 'confirmed', 'confirmation_revision': 0}]
        states[identity] = state; analyses[identity] = analysis
        sources[identity] = rgb; face_ids[identity] = face_id
    params = recipe(.45, -.3, linked=False)
    for path, value in A.leaves(params['recipe']).items():
        states['source'] = P.set_override(states['source'], 'face', 'source-face', C.OP, path, value)
    for identity in ('target-a', 'target-b'):
        states[identity] = P.set_override(states[identity], 'face', face_ids[identity], COLOUR.OP, '/tint', -.2)
        states[identity]['faces'][face_ids[identity]]['local_assets']['target-only']['content_sha256'] = (
            '1' if identity == 'target-a' else '2') * 64
    if fault == 'target-forehead':
        own = analyses['target-b']; mask = _geometry_mask(own, sources['target-b'].shape[:2], 'left', 'reference')
        own['excluded'][mask] = 1.
    elif fault == 'target-brow':
        own = analyses['target-b']; mask = _geometry_mask(own, sources['target-b'].shape[:2], 'right', 'polygon')
        sources['target-b'][mask] = sources['target-b'][0, 0]
    elif fault == 'copied-source-analysis':
        analyses['target-b'] = analyses['source']
    native = MockNative(); monkeypatch.setattr(N, 'available', lambda: True)
    monkeypatch.setattr(N, 'apply', native)
    source_layer = L.prepare(P.face_ref(states['source']['faces']['source-face']),
        analyses['source'], sources['source'], params['recipe'], byte_budget=512*1024**2)[0]
    source_reference = source_layer.facts['sides']['left']['thirds'][0]['reference_median_luma']
    owner = Owner(states['source'])
    rows = [{'document_id': identity, 'path': identity + '.jpg', 'state': {}} for identity in states]
    if derived:
        for row in rows[1:]: row['state']['_creative_base'] = {'fixture': row['document_id'] + ' immutable source'}
    def proof(state, identity):
        out = endpoint(state, identity, scope='project' if policy == 'confirmed_person_only' else None)
        if derived and identity != 'source':
            asset = state['faces'][face_ids[identity]]['asset_sha256']
            evidence = state['faces'][face_ids[identity]]['evidence']
            out['source_proof']['creative_source'] = {'sha256': asset,
                'width': evidence['source_width'], 'height': evidence['source_height']}
            out['source_proof']['original_sha256'] = '3' * 64
        return out
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    batch = SimpleNamespace(versions=versions,
        documents=SimpleNamespace(rows=lambda: rows, current_index=lambda: 0, remember_current=lambda: None),
        target_indices=lambda docs: ([1, 2], []))
    engine = SimpleNamespace(_people_bind=lambda: None, _people_owner=lambda: owner,
        _batch_controller=lambda: batch, _document_versions=lambda: versions,
        _body_bank=lambda: pytest.fail('Original-brow contrast does not acquire body coverage'))
    monkeypatch.setattr(B.V, 'row_snapshot', lambda actual, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I, 'proof', lambda actual, row, state: proof(state, row['document_id']))
    def verify(actual, row, state, expected):
        assert expected == proof(state, row['document_id']); return expected
    monkeypatch.setattr(I, 'verify', verify)
    monkeypatch.setattr(B.SOURCE, 'row_proof', lambda row: proof(states[row['document_id']], row['document_id'])['source_proof'])
    def verify_source(row, expected):
        assert expected == B.SOURCE.row_proof(row); return expected
    monkeypatch.setattr(B.SOURCE, 'verify_row', verify_source)
    expected_parameters = [{'operation_id': C.OP, 'parameter_path': path, 'value': value}
        for path, value in sorted(A.leaves(params['recipe']).items())]
    renders = []; measured = {}
    def render(actual, row, state, document_id, revision, *, people_graph):
        assert actual is engine and row['document_id'] == document_id
        assert state is row['state'] and revision == '2' and document_id != 'source'
        target = states[document_id]; face_id = face_ids[document_id]
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert people_graph[key] == target[key]
        assert all(leaf in people_graph['overrides'] for leaf in target['overrides'])
        assert [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']] == [
            {'scope': 'face', 'target_id': face_id, **parameter} for parameter in expected_parameters]
        renders.append(document_id)
        analysis, rgb = analyses[document_id], sources[document_id]
        verify_analysis(people_graph['faces'][face_id], analysis, rgb.shape[:2])
        candidate_recipe = A.recipes(resolve(people_graph, face_id, A.defaults()))[C.OP]
        own = L.prepare(P.face_ref(people_graph['faces'][face_id]), analysis, rgb,
            candidate_recipe, byte_budget=512*1024**2)[0]
        assert own.face_ref == P.face_ref(target['faces'][face_id])
        assert own.facts['forehead_observation']['source_sha256'] == target['faces'][face_id]['asset_sha256']
        own_reference = own.facts['sides']['left']['thirds'][0]['reference_median_luma']
        assert own_reference != pytest.approx(source_reference)
        measured[document_id] = own_reference
        return None, {'fixture': 'real target evidence and contrast support; mocked full-render boundary'}
    monkeypatch.setattr(FULL, 'render', render); plans = []
    def freeze(workspace, source_id, revision, path, modules, params, target_policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda plan: {},
        emit=lambda event: None, emit_result=lambda request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-brow-enhance',
        'docs': ['target-a', 'target-b'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': P.face_ref(states['source']['faces']['source-face']), 'selection': {C.OP: list(LEAVES)},
            'target_policy': 'explicit_face_map', 'source': proof(states['source'], 'source'), 'targets': [
                {'target': proof(states[identity], identity),
                 'target_refs': [P.face_ref(states[identity]['faces'][face_ids[identity]])]}
                for identity in ('target-a', 'target-b')]}}
    if policy == 'confirmed_person_only':
        request['people_transfer'] = {key: value for key, value in request['people_transfer'].items()
            if key not in ('source', 'targets')}
        request['people_transfer']['target_policy'] = policy
    before = deepcopy(states); B.preflight(engine, controller, request)
    assert states == before and not owner.commits and renders == ['target-a', 'target-b']
    result = replies[-1]
    assert (result['ok'], result['blocked']) == ((1, 1) if fault else (2, 0))
    assert set(measured) == ({'target-a'} if fault else {'target-a', 'target-b'})
    if not fault: assert measured['target-a'] != pytest.approx(measured['target-b'])
    for index, identity in enumerate(('target-a', 'target-b')):
        payload = result['targets'][index]['people_transfer']
        if fault and identity == 'target-b':
            assert payload is None and plans[0][index].people_json is None and result['targets'][index]['blocked']
        else:
            assert payload['parameters'] == expected_parameters
            assert payload['target_refs'] == [P.face_ref(states[identity]['faces'][face_ids[identity]])]
            assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
            assert not any(key in payload for key in ('reference_samples', 'forehead_samples',
                'resolved_contrast', 'landmarks', 'face_skin', 'mask'))
            assert json.loads(plans[0][index].people_json) == payload
