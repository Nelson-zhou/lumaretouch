# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: scalar-only lip-furrow presets and target-owned transfer.

LNX-REF-PC-32464-C-b6315c40ca is PARTIAL: eligible narrow original dark furrows,
not added material, broad blur, AI blemish removal, dry-flake/crack repair or
official parity. Synthetic observations specify ownership/routing contracts;
they do not prove actual inference, native correctness or photographic quality.
No product imports, collection, tests, builds or typechecks ran during authoring.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import lip_texture_scope as C, lip_texture_state as S
from lumaretouch_engine import lip_texture_native as N, lipstick_state as MAKEUP
from lumaretouch_engine import people_state as P, people_algorithms as A
from lumaretouch_engine import people_scope as REPLAY, scope as SC
from lumaretouch_engine import skin_colour_scope as COLOUR
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, isolate_other_captures)

LEAVES = ('/amount',)


def recipe(amount=0.):
    return {'recipe': {'version': 1, 'amount': amount}}


def engine_fixture(monkeypatch):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, analysis, current = colour_engine_fixture(monkeypatch)
    # Vermilion need not belong to the semantic face-skin class. Admission uses
    # exact retained 478 points, genuine excluded/model evidence and effective source.
    analysis.pop('face_skin'); analysis.pop('face_skin_observation')
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
        calls.append((deepcopy(state), kwargs)); return {'event': 'frame'}
    engine._replay_state = replay
    return engine, owner, analysis, current, calls


def put(owner, amount):
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/amount', amount)


def values(owner):
    return A.recipes(resolve(owner.snapshot(), FACE, A.defaults()))


def retain_makeup(owner):
    makeup = {**MAKEUP.neutral(), 'pattern': 'inner_bloom', 'strength': .3,
              'texture': 'cream', 'colour': '#A94359'}
    for path, value in A.leaves(makeup).items():
        owner.value = P.set_override(owner.value, 'face', FACE, MAKEUP.OP, path, value)
    owner.value = P.set_override(owner.value, 'face', FACE, A.LIP, '/brightness', -.2)
    return makeup


def test_distinct_scalar_registration_does_not_claim_full_lip_repair():
    assert C.OP == 'lnx.lip_texture.v1' and S.VERSION == 1
    assert S.CONTROL_ID == 'LNX-REF-PC-32464-C-b6315c40ca'
    assert C.OP not in (MAKEUP.OP, A.LIP, A.WRINKLES, A.ENHANCE)
    assert C.OP not in A.GEOMETRY and C.OP not in SC.DERIVED_PARAMETER_OPS
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True and SC.MODULES[C.OP]['transferable'] is True
    assert SC.MODULES[C.OP]['label'] == '唇部暗细纹减淡（独立强度，部分唇纹修整）'
    assert A.defaults()[C.OP] == {'/amount': 0.}
    assert S.neutral() == recipe()['recipe'] and not S.active(S.neutral())


@pytest.mark.parametrize('amount', [0., .01, .4, 1.])
def test_version_and_amount_alone_round_trip(amount):
    params = recipe(amount)
    assert C.check_params(params) == SC.check_params(C.OP, params) == params
    portable = {'schema': SC.PRESET_SCHEMA, 'id': 'lip-texture', 'name': 'Lip dark furrows',
        'kind': 'portrait', 'modules': {C.OP: params}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(portable)))
    assert loaded['modules'] == {C.OP: params}
    assert set(loaded['modules'][C.OP]['recipe']) == {'version', 'amount'}
    assert set(A.leaves(params['recipe'])) == set(LEAVES)


@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'),
    float('-inf'), -.01, 1.01, 10**1000, -(10**1000)])
def test_invalid_amount_refuses_without_mutation(monkeypatch, value):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state)
    with pytest.raises(ValueError): C.install(state, recipe(value))
    with pytest.raises(SC.ScopeError): SC.check_params(C.OP, recipe(value))
    assert state == before and not owner.commits


@pytest.mark.parametrize('raw', [None, {}, {'version': 1}, {'amount': .3},
    {'version': True, 'amount': .3}, {'version': 2, 'amount': .3},
    {'version': 1, 'strength': .3}, MAKEUP.neutral()])
def test_exact_schema_is_not_lipstick_or_optional_amount(raw):
    with pytest.raises(ValueError): C.check_params({'recipe': raw})


@pytest.mark.parametrize('key', ['face_ref', 'owner', 'source', 'face_skin', 'excluded',
    'landmarks', 'analysis', 'geometry', 'control_points', 'mask', 'coverage',
    'furrow_samples', 'flank_samples', 'native_result', 'supported', 'pattern',
    'colour', 'strength', 'texture', 'lipstick_review', 'lipstick_visibility',
    'linked', 'left', 'right', 'dry_flakes', 'cracks', 'ai_blemish'])
def test_transport_rejects_donor_evidence_material_and_claimed_readiness(key):
    params = recipe(.3)
    with pytest.raises(ValueError): C.check_params({**params, key: {}})
    params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


def test_workflow_exports_only_canonical_intent_without_skin_or_lipstick_review(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); put(owner, .35); makeup = retain_makeup(owner)
    before = owner.snapshot(); captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert SC.params_of(captured, [C.OP]) == {C.OP: recipe(.35)}
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_lip_texture_supported'] is True and captured[C.REQUESTED] is False
    assert C.owner_identity(captured) == {'document_id': 'target-document', 'epoch': 'workspace',
        'people_scope': 'project', 'source_proof': {'asset_sha256': ASSET,
            'creative_source': None, 'original_sha256': ASSET}}
    assert not {'face_skin', 'landmarks', 'furrow_samples', 'lipstick_review'} & set(captured)
    assert 'face_skin' not in analysis and values(owner)[MAKEUP.OP] == makeup
    assert values(owner)[A.LIP]['brightness'] == -.2 and owner.snapshot() == before
    assert engine._people_analyses[ASSET][FACE] is analysis and current == {} and not owner.commits


@pytest.mark.parametrize('fault', ['excluded', 'ref', 'semantic-missing', 'model',
    'landmark-bytes', 'landmark-count', 'synthetic', 'dimensions', 'donor-analysis'])
def test_capture_requires_target_owned_semantic_observation_and_actual478(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'excluded': analysis['excluded'] = None
    elif fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'semantic-missing':
        analysis['evidence']['semantic_model_sha256'] = None
        owner.value['faces'][FACE]['evidence']['semantic_model_sha256'] = None
    elif fault == 'model': analysis['evidence']['semantic_model_sha256'] = 'f' * 64
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
    assert captured['_lip_texture_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3))
    assert not owner.commits


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged', 'no-document'])
def test_even_neutral_requires_exact_enabled_face_and_live_owner(monkeypatch, fault):
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
def test_native_and_observation_are_independent_of_neutral_recovery(monkeypatch, native, observed):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: native)
    if not observed: analysis['excluded'] = None
    captured = C.capture(engine)
    assert captured['_lip_texture_supported'] is observed
    assert captured['_lip_texture_native_available'] is native
    C.install(captured, recipe()); assert C.params_of(captured) == recipe()
    if native and observed:
        C.install(captured, recipe(.4)); assert C.params_of(captured) == recipe(.4)
    else:
        with pytest.raises(ValueError): C.install(captured, recipe(.4))
    assert not owner.commits


def test_lipstick_support_claim_cannot_replace_lip_texture_observation(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    analysis['excluded'] = None
    current.update(_lipstick_supported=True,
        _lipstick_preset_target=P.face_ref(owner.value['faces'][FACE]))
    captured = C.capture(engine)
    assert captured['_lipstick_supported'] is True
    assert captured['_lip_texture_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3))
    assert not owner.commits


def test_install_changes_only_transport_and_keeps_generic_derived_fence(monkeypatch):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3)})
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
    assert state['_lip_texture_supported'] is False
    with pytest.raises(ValueError, match='有效来源'): C.install(state, recipe(amount))
    assert state == before and not owner.commits


@pytest.mark.parametrize('derived_snapshot', ['current', 'previous'])
def test_generic_derived_restore_cannot_bypass_confirmed_people_transfer(monkeypatch, derived_snapshot):
    from lumaretouch_engine import creative_derived_transfer as D
    current = {}; previous = {}
    (current if derived_snapshot == 'current' else previous)['_creative_base'] = {'fixture': 'derived'}
    monkeypatch.setattr(D, 'involved', lambda state, **kwargs: True)
    with pytest.raises(SC.ScopeError, match='历史'): SC.restore_modules(current, previous, [C.OP])


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged', 'source',
    'document', 'owner', 'epoch', 'proof', 'source-kind', 'original-source'])
def test_replay_rechecks_live_owner_and_evidence_not_saved_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
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


def test_neutral_recovery_needs_no_anatomy_or_native_and_preserves_makeup(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, .3); makeup = retain_makeup(owner)
    engine._people_analyses.clear(); monkeypatch.setattr(N, 'available', lambda: False)
    state = C.capture(engine); C.install(state, recipe()); REPLAY.replay_preset(engine, state)
    assert values(owner)[C.OP] == S.neutral() and values(owner)[MAKEUP.OP] == makeup
    assert values(owner)[A.LIP]['brightness'] == -.2
    assert calls[-1][1]['strict_local'] is True and not engine._people_analyses


@pytest.mark.parametrize('fault', ['document', 'epoch', 'owner', 'target'])
def test_neutral_recovery_still_fences_exact_owner_and_face(monkeypatch, fault):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, .3); state = C.capture(engine); C.install(state, recipe())
    engine._people_analyses.clear(); monkeypatch.setattr(N, 'available', lambda: False)
    if fault == 'document': engine._docs[0]['document_id'] = 'other-document'
    elif fault == 'epoch': engine._document_versions().workspace = 'other-workspace'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    else: engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


@pytest.mark.parametrize('start,end', [(0., .4), (.4, .2), (.3, 0.)])
@pytest.mark.parametrize('refused', [False, True])
def test_complete_renderer_composes_retained_intent_or_rolls_back(monkeypatch, start, end, refused):
    engine, owner, analysis, _, _ = replay_fixture(monkeypatch)
    put(owner, start); makeup = retain_makeup(owner)
    owner.value = P.set_override(owner.value, 'group', 'preserved', COLOUR.OP, '/tint', -.25)
    before = owner.snapshot(); rendered = []
    def render(state, **kwargs):
        candidate = owner.snapshot(); rendered.append(candidate)
        assert kwargs['strict_local'] is True
        assert values(owner)[C.OP] == recipe(end)['recipe'] and values(owner)[MAKEUP.OP] == makeup
        assert values(owner)[A.LIP]['brightness'] == -.2 and values(owner)[COLOUR.OP]['tint'] == -.25
        for field in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert candidate[field] == before[field]
        assert all(leaf in candidate['overrides'] for leaf in before['overrides'] if leaf['operation_id'] != C.OP)
        if refused: raise RuntimeError('complete candidate lip or composition support refused')
        return {'event': 'frame'}
    engine._replay_state = render; state = C.capture(engine); C.install(state, recipe(end))
    if refused:
        with pytest.raises(RuntimeError, match='composition support refused'): REPLAY.replay_preset(engine, state)
        assert owner.snapshot() == before and len(owner.commits) == 2
    else:
        REPLAY.replay_preset(engine, state); assert len(owner.commits) == 1
    assert len(rendered) == 1 and engine._people_analyses[ASSET][FACE] is analysis


def test_unchanged_active_intent_still_uses_complete_strict_renderer(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, .3); REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_full_render_failure_restores_graph_and_existing_outer_history(monkeypatch):
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    from lumaretouch_engine.preset_transaction import apply_with_rollback, PresetApplyError
    engine, initial, _, _, _ = replay_fixture(monkeypatch); makeup = retain_makeup(initial)
    owner = PeopleGraphOwner(initial.snapshot()); engine._people_owner = lambda: owner
    before_graph = owner.snapshot(); before = C.capture(engine); after = deepcopy(before)
    C.install(after, recipe(.3)); calls = []
    def render(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        if len(calls) == 1: raise RuntimeError('target own lip ring or furrow support refused')
        return {'event': 'frame'}
    engine._replay_state = render
    with pytest.raises(PresetApplyError) as error:
        apply_with_rollback(lambda state, **kwargs: REPLAY.replay_preset(engine, state, **kwargs),
            before, after, preset_id='lip-texture', emit=lambda event: None,
            invalidate=lambda: pytest.fail('Rollback must remain available'))
    assert error.value.rolled_back is True and len(calls) == 2
    assert calls[0][1]['strict_local'] is True and calls[1][1]['mode'] == 'preset_rollback'
    actual = owner.snapshot()
    assert actual['revision'] == before_graph['revision'] + 2 and owner.fence == 2
    assert {key: value for key, value in actual.items() if key != 'revision'} == {
        key: value for key, value in before_graph.items() if key != 'revision'}
    assert values(owner)[MAKEUP.OP] == makeup and values(owner)[A.LIP]['brightness'] == -.2


def test_requested_neutral_cannot_silently_fall_back_to_unmanaged_legacy(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe()); engine._people_managed = lambda: False
    with pytest.raises(ValueError, match='唇部暗细纹'): REPLAY.replay_preset(engine, state)
    assert not calls and not owner.commits


def test_generic_preset_never_guesses_between_enabled_faces(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    other, _ = graph(face_id='neighbour'); owner.value['faces']['neighbour'] = other['faces']['neighbour']
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.3))
    with pytest.raises(ValueError, match='one explicit unambiguous enabled face'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_capture_authenticates_live_source_state_not_parked_row(monkeypatch):
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
def test_derived_capture_uses_effective_analysis_never_original_donor(monkeypatch, reuse_original):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, original, current = engine_fixture(monkeypatch)
    derived = 'e' * 64; target, own = graph(derived); owner.value = target
    own.pop('face_skin'); own.pop('face_skin_observation')
    engine._people_source = lambda: {'sha256': derived, 'width': 640, 'height': 480}
    engine._people_cursors = {derived: FACE}
    engine._people_targets = {derived: {'scope': 'face', 'target_id': FACE,
        'face_ref': P.face_ref(target['faces'][FACE])}}
    engine._people_analyses = {ASSET: {FACE: original}, derived: {FACE: original if reuse_original else own}}
    current['_creative_base'] = {'fixture': 'derived baseline, not product pixels'}
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': derived,
        'creative_source': {'sha256': derived, 'width': 640, 'height': 480}, 'original_sha256': ASSET})
    put(owner, .3); captured = C.capture(engine)
    assert captured['_lip_texture_supported'] is (not reuse_original)
    if reuse_original:
        with pytest.raises(ValueError): C.params_of(captured)
    else:
        assert C.params_of(captured) == recipe(.3)
        assert C.owner_identity(captured)['source_proof']['asset_sha256'] == derived
    with pytest.raises(ValueError, match='合成来源'): C.install(captured, recipe())
    assert not owner.commits


def test_disabled_face_amount_round_trips_project_and_history_without_conversion():
    from lumaretouch_engine import people_project as PROJECT
    old, _ = graph(); edited = P.set_override(old, 'face', FACE, C.OP, '/amount', .4)
    edited['faces'][FACE]['enabled'] = False
    source_proof = endpoint(old, 'target-document', scope='project')['source_proof']
    payload = {'people_graph': edited, 'source_proof': source_proof,
        'undo': [{'_people_state': old, 'source_proof': deepcopy(source_proof)}],
        'redo': [{'_people_state': edited, 'source_proof': deepcopy(source_proof)}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False)); PROJECT.validate_records(restored)
    assert restored == payload
    assert restored['people_graph']['faces'][FACE]['enabled'] is False
    for state, amount in ((restored['people_graph'], .4),
            (restored['undo'][0]['_people_state'], 0.), (restored['redo'][0]['_people_state'], .4)):
        materialized = A.recipes(resolve(P.check(state), FACE, A.defaults()))
        assert materialized[C.OP] == recipe(amount)['recipe']
        assert materialized[MAKEUP.OP] == MAKEUP.neutral()
        assert state['links'] == old['links']


def test_batch_selection_accepts_only_amount_not_geometry_or_lipstick_review():
    from lumaretouch_engine import people_batch_transfer as B
    state, _ = graph(); selected = {'source_ref': P.face_ref(state['faces'][FACE]),
        'selection': {C.OP: list(LEAVES)}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/version', '/strength', '/linked', '/face_ref', '/landmarks', '/excluded',
            '/mask', '/furrow_samples', '/flank_samples', '/lipstick_review', '/texture'):
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
    source = P.set_override(source, 'face', 'source-face', C.OP, '/amount', .4)
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
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': .4}]
    materialized = A.recipes(resolve(candidate, FACE, A.defaults()))
    assert materialized[C.OP] == recipe(.4)['recipe'] and materialized[MAKEUP.OP] == makeup
    assert materialized[A.LIP]['brightness'] == -.2 and materialized[COLOUR.OP]['tint'] == -.3
    assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    changed = deepcopy(target_owner); changed['source_proof'] = {'asset_sha256': 'f' * 64,
        'creative_source': None, 'original_sha256': 'f' * 64}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **{**kwargs, 'target_owner': changed})


def test_capture_admission_does_not_assert_anatomy_and_full_render_can_refuse(monkeypatch):
    from lumaretouch_engine import lip_texture_layer as L
    import numpy as np
    engine, owner, analysis, _, _ = replay_fixture(monkeypatch)
    # Exact digested 478 points may be anatomically unusable. Capability/ownership
    # admission cannot treat coincident points as a visible measured lip ring.
    owner.value['faces'][FACE]['evidence'].update(source_width=10, source_height=8)
    analysis['evidence'] = deepcopy(owner.value['faces'][FACE]['evidence'])
    engine._people_source = lambda: {'sha256': ASSET, 'width': 10, 'height': 8}
    captured = C.capture(engine); assert captured['_lip_texture_supported'] is True
    C.install(captured, recipe(.3)); before = owner.snapshot(); calls = []
    def render(state, **kwargs):
        calls.append(kwargs)
        return L.prepare(P.face_ref(owner.value['faces'][FACE]), analysis,
            np.full((8, 10, 3), .5, np.float32), values(owner)[C.OP], byte_budget=512*1024**2)
    engine._replay_state = render
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, captured)
    assert calls[0]['strict_local'] is True and len(owner.commits) == 2
    assert owner.snapshot() == before


def source_fixture(asset, face_id, size, illumination, *, confirmed=False):
    """Independent synthetic actual grids, not copied masks or real inference.

    Durable dimensions are explicitly bound to each generated full grid, rather
    than quietly declaring the support helper's 1024-source proxy a full source.
    Dormant lip-makeup recovery belongs to this target and remains independent.
    """
    import numpy as np
    from test_lip_texture_support_unrun import synthetic_observation
    _, analysis, rgb = synthetic_observation(size=size)
    rgb = np.ascontiguousarray(rgb*np.float32(illumination), dtype=np.float32)
    analysis['evidence'].update(source_width=size, source_height=size)
    state = P.empty(); face = P.new_face(asset, [.05, .03, .95, .97], deepcopy(analysis['evidence']))
    face['face_instance_id'] = face_id; state['faces'][face_id] = face
    ref = P.face_ref(face); analysis['face_ref'] = deepcopy(ref)
    recovery_digest = sha256(('target-owned-recovery:'+face_id).encode()).hexdigest()
    face['local_assets']['lip_makeup'] = {'owner': deepcopy(ref),
        'content_sha256': recovery_digest, 'kind': 'lip_makeup'}
    weight = np.zeros((size, size), np.uint8)
    recovery = {(face_id, 'lip_makeup'): {'face_ref': deepcopy(ref), 'stage': 'lip_makeup',
        'weight': weight, 'content_sha256': sha256(weight.tobytes()).hexdigest(),
        'recipe_sha256': recovery_digest}}
    # Preserve dormant material intent without borrowing its visibility review.
    state = P.set_override(state, 'face', face_id, MAKEUP.OP, '/texture', 'cream')
    foreign = deepcopy(face); foreign['face_instance_id'] = face_id+'-neighbour'
    foreign['local_assets'] = {}; foreign['enabled'] = False
    foreign['evidence']['status'] = 'unresolved'; foreign['box'] = [.01, .01, .10, .10]
    state['faces'][foreign['face_instance_id']] = foreign
    if confirmed:
        state['persons']['confirmed-person'] = {'anonymous': True}
        state['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    return state, analysis, rgb, recovery


def source_endpoint(state, identity, *, derived=False, confirmed=False):
    out = endpoint(state, identity, scope='project' if confirmed else None)
    if derived:
        face = next(iter(state['faces'].values())); evidence = face['evidence']
        out['source_proof']['creative_source'] = {'sha256': face['asset_sha256'],
            'width': evidence['source_width'], 'height': evidence['source_height']}
        out['source_proof']['original_sha256'] = '3'*64
    return out


@pytest.mark.parametrize('policy,derived', [('explicit_face_map', False),
    ('confirmed_person_only', False), ('explicit_face_map', True)])
@pytest.mark.parametrize('fault', [None, 'target-occluded', 'target-source-clipped',
    'target-foreign-face', 'copied-source-analysis'])
def test_real_transfer_runtime_rebuilds_each_target_with_only_native_doubled(monkeypatch, policy, derived, fault):
    """Actual adapter, owner verification, runtime, lip support and composition.

    Only dedicated native availability/apply are doubled. No support preparer,
    anatomical geometry, semantic gate, resolver or complete people runtime is
    replaced. This remains synthetic authored routing, not full-file export or
    a claim that the native furrow solver has been executed or validated.
    """
    import numpy as np
    from lumaretouch_engine import people_transfer_adapter as T, people_render_runtime as RUNTIME
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    from test_lip_texture_support_unrun import native_double
    confirmed = policy == 'confirmed_person_only'
    source, source_analysis, source_rgb, _ = source_fixture(ASSET, 'source-face', 256, .9, confirmed=confirmed)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/amount', .45)
    source_owner = source_endpoint(source, 'source', confirmed=confirmed)
    native_calls = []; monkeypatch.setattr(N, 'available', lambda: True)
    monkeypatch.setattr(N, 'apply', native_double(native_calls))
    measured = {}
    for identity, asset, size, illumination in (
            ('target-a', 'e'*64, 320, 1.), ('target-b', 'f'*64, 384, 1.1)):
        face_id = identity+'-face'
        target, analysis, rgb, recovery = source_fixture(asset, face_id, size, illumination, confirmed=confirmed)
        target_owner = source_endpoint(target, identity, derived=derived, confirmed=confirmed)
        kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
            'source_owner': source_owner, 'target_owner': target_owner}
        if confirmed:
            payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), asset,
                {C.OP: list(LEAVES)}, A.defaults(), **kwargs)
        else:
            payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
                [P.face_ref(target['faces'][face_id])], {C.OP: list(LEAVES)}, A.defaults(), **kwargs)
            payload['target_policy'] = policy
        candidate = T.candidate(payload, source, target, **kwargs)
        assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': .45}]
        assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
        assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
        assert all(leaf in candidate['overrides'] for leaf in target['overrides'])
        assert 'face_skin' not in analysis and 'lipstick_review' not in analysis
        bad = identity == 'target-b' and fault is not None
        if bad:
            if fault == 'target-occluded': analysis['excluded'][:] = 1.
            elif fault == 'target-source-clipped': rgb[:] = 1.
            elif fault == 'target-foreign-face':
                candidate['faces'][face_id+'-neighbour']['box'] = [.2, .5, .8, .8]
            else: analysis = source_analysis
        before_target = deepcopy(target); before_pixels = rgb.copy(); calls_before = len(native_calls)
        binding = target_owner['source_proof']['creative_source'] if derived else None
        def prepare():
            return RUNTIME.prepare(candidate, asset, rgb, {face_id: analysis},
                byte_budget=512*1024**2, document_id=identity,
                recovery_assets=recovery, creative_source=binding)
        if bad:
            with pytest.raises(RUNTIME.PeoplePreparationRefused): prepare()
            assert len(native_calls) == calls_before
        else:
            prepared = prepare(); assert len(native_calls) == calls_before+1
            records = [record for record in prepared.effects if record.stage == 'lip_texture']
            assert len(records) == 1 and records[0].face_ref == P.face_ref(target['faces'][face_id])
            record = records[0]; facts = prepared.facts[face_id]['lip_texture']; y, x, h, w = record.window
            np.testing.assert_array_equal(native_calls[-1]['source'], rgb[y:y+h, x:x+w])
            assert native_calls[-1]['source'].shape != source_rgb.shape
            assert facts['source_dimensions'] == facts['render_dimensions'] == [size, size]
            assert facts['semantic_model_sha256'] == analysis['evidence']['semantic_model_sha256']
            assert facts['protected_face_boxes'] == 1
            assert all(facts['sides'][side]['eligible_centers'] >= 4 for side in ('upper', 'lower'))
            assert native_calls[-1]['amount'] == .45 and facts['changed_pixels'] > 0
            materialized = A.recipes(resolve(candidate, face_id, A.defaults()))
            assert materialized[MAKEUP.OP]['texture'] == 'cream' and materialized[MAKEUP.OP]['strength'] == 0.
            assert (face_id, 'lip_makeup') in prepared.recovery
            output, composition = prepared.apply_source_stage('lip_texture', rgb)
            assert composition['changed_pixels'] > 0 and output.shape == rgb.shape
            assert np.any(output != rgb) and np.isfinite(output).all()
            measured[identity] = (facts['measured_mouth_width'], float(native_calls[-1]['source'].mean()))
        assert target == before_target
        np.testing.assert_array_equal(rgb, before_pixels)
    if fault is None:
        assert measured['target-a'][0] != pytest.approx(measured['target-b'][0])
        assert measured['target-a'][1] != pytest.approx(measured['target-b'][1])
    else:
        assert set(measured) == {'target-a'}


def test_derived_runtime_does_not_relax_existing_shared_identity_fence(monkeypatch):
    from lumaretouch_engine import people_render_runtime as RUNTIME
    target, analysis, rgb, recovery = source_fixture('e'*64, FACE, 320, 1., confirmed=True)
    target = P.set_override(target, 'face', FACE, C.OP, '/amount', .3)
    before = deepcopy(target)
    monkeypatch.setattr(N, 'apply', lambda *args, **kwargs: pytest.fail('Invalid derived shared owner reached native'))
    with pytest.raises(ValueError, match='shared person/group'):
        RUNTIME.prepare(target, 'e'*64, rgb, {FACE: analysis}, byte_budget=512*1024**2,
            document_id='target', recovery_assets=recovery,
            creative_source={'sha256': 'e'*64, 'width': 320, 'height': 320})
    assert target == before


@pytest.mark.parametrize('policy,derived', [('explicit_face_map', False),
    ('confirmed_person_only', False), ('explicit_face_map', True)])
@pytest.mark.parametrize('fault', [None, 'target-occluded', 'copied-source-analysis'])
def test_frozen_batch_review_uses_real_target_runtime_and_reports_refusal(monkeypatch, policy, derived, fault):
    """Batch document-I/O boundary supplies independent complete synthetic RGB.

    The full-file decoder/export boundary is intentionally replaced, not claimed
    tested. Its body calls the actual canonical people runtime, real lip support
    and compositor; only the native numerical implementation is doubled there.
    A target refusal must not produce a transferable prepared-success payload.
    """
    import numpy as np
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL, people_render_runtime as RUNTIME
    from test_lip_texture_support_unrun import native_double
    confirmed = policy == 'confirmed_person_only'
    settings = {'source': (ASSET, 'source-face', 256, .9),
        'target-a': ('e'*64, 'target-a-face', 320, 1.),
        'target-b': ('f'*64, 'target-b-face', 384, 1.1)}
    states = {}; analyses = {}; sources = {}; recoveries = {}; face_ids = {}
    for identity, (asset, face_id, size, illumination) in settings.items():
        state, analysis, rgb, recovery = source_fixture(asset, face_id, size, illumination, confirmed=confirmed)
        states[identity] = state; analyses[identity] = analysis; sources[identity] = rgb
        recoveries[identity] = recovery; face_ids[identity] = face_id
    states['source'] = P.set_override(states['source'], 'face', 'source-face', C.OP, '/amount', .45)
    if fault == 'target-occluded': analyses['target-b']['excluded'][:] = 1.
    elif fault == 'copied-source-analysis': analyses['target-b'] = analyses['source']
    native_calls = []; monkeypatch.setattr(N, 'available', lambda: True)
    monkeypatch.setattr(N, 'apply', native_double(native_calls))
    owner = Owner(states['source'])
    rows = [{'document_id': identity, 'path': identity+'.jpg', 'state': {}} for identity in states]
    if derived:
        for row in rows[1:]: row['state']['_creative_base'] = {'fixture': row['document_id']+' immutable source'}
    def proof(state, identity):
        return source_endpoint(state, identity, derived=derived and identity != 'source', confirmed=confirmed)
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    batch = SimpleNamespace(versions=versions,
        documents=SimpleNamespace(rows=lambda: rows, current_index=lambda: 0, remember_current=lambda: None),
        target_indices=lambda docs: ([1, 2], []))
    engine = SimpleNamespace(_people_bind=lambda: None, _people_owner=lambda: owner,
        _batch_controller=lambda: batch, _document_versions=lambda: versions,
        _body_bank=lambda: pytest.fail('Lip texture must not acquire body coverage'))
    monkeypatch.setattr(B.V, 'row_snapshot', lambda actual, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I, 'proof', lambda actual, row, state: proof(state, row['document_id']))
    def verify(actual, row, state, expected):
        assert expected == proof(state, row['document_id']); return expected
    monkeypatch.setattr(I, 'verify', verify)
    monkeypatch.setattr(B.SOURCE, 'row_proof', lambda row: proof(states[row['document_id']], row['document_id'])['source_proof'])
    def verify_source(row, expected):
        assert expected == B.SOURCE.row_proof(row); return expected
    monkeypatch.setattr(B.SOURCE, 'verify_row', verify_source)
    renders = []; measured = {}
    expected_parameters = [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': .45}]
    def render(actual, row, state, document_id, revision, *, people_graph):
        assert actual is engine and row['document_id'] == document_id and document_id != 'source'
        assert state is row['state'] and revision == '2'
        target = states[document_id]; face_id = face_ids[document_id]
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert people_graph[key] == target[key]
        assert all(leaf in people_graph['overrides'] for leaf in target['overrides'])
        assert [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']] == [
            {'scope': 'face', 'target_id': face_id, **expected_parameters[0]}]
        renders.append(document_id); rgb = sources[document_id]
        target_proof = proof(target, document_id)['source_proof']
        prepared = RUNTIME.prepare(people_graph, target_proof['asset_sha256'], rgb,
            {face_id: analyses[document_id]}, byte_budget=512*1024**2,
            document_id=document_id, recovery_assets=recoveries[document_id],
            creative_source=target_proof['creative_source'])
        record = next(record for record in prepared.effects if record.stage == 'lip_texture')
        assert record.face_ref == P.face_ref(target['faces'][face_id])
        y, x, h, w = record.window
        np.testing.assert_array_equal(native_calls[-1]['source'], rgb[y:y+h, x:x+w])
        assert record.facts['source_dimensions'] == [rgb.shape[1], rgb.shape[0]]
        assert record.facts['protected_face_boxes'] == 1
        output, composition = prepared.apply_source_stage('lip_texture', rgb)
        assert composition['changed_pixels'] > 0
        measured[document_id] = (record.facts['measured_mouth_width'], float(native_calls[-1]['source'].mean()))
        return output, {'fixture': 'real target people/support/composition, not full-file decoding or native acceptance'}
    monkeypatch.setattr(FULL, 'render', render); plans = []
    def freeze(workspace, source_id, revision, path, modules, params, target_policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda plan: {},
        emit=lambda event: None, emit_result=lambda request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-lip-texture',
        'docs': ['target-a', 'target-b'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': P.face_ref(states['source']['faces']['source-face']),
            'selection': {C.OP: list(LEAVES)}, 'target_policy': 'explicit_face_map',
            'source': proof(states['source'], 'source'), 'targets': [
                {'target': proof(states[identity], identity),
                 'target_refs': [P.face_ref(states[identity]['faces'][face_ids[identity]])]}
                for identity in ('target-a', 'target-b')]}}
    if confirmed:
        request['people_transfer'] = {key: value for key, value in request['people_transfer'].items()
            if key not in ('source', 'targets')}
        request['people_transfer']['target_policy'] = policy
    before = deepcopy(states); B.preflight(engine, controller, request)
    assert states == before and not owner.commits and renders == ['target-a', 'target-b']
    result = replies[-1]
    assert (result['ok'], result['blocked']) == ((1, 1) if fault else (2, 0))
    assert len(native_calls) == (1 if fault else 2)
    assert set(measured) == ({'target-a'} if fault else {'target-a', 'target-b'})
    if not fault:
        assert measured['target-a'][0] != pytest.approx(measured['target-b'][0])
        assert measured['target-a'][1] != pytest.approx(measured['target-b'][1])
    for index, identity in enumerate(('target-a', 'target-b')):
        payload = result['targets'][index]['people_transfer']
        if fault and identity == 'target-b':
            assert payload is None and plans[0][index].people_json is None and result['targets'][index]['blocked']
        else:
            assert payload['parameters'] == expected_parameters
            assert payload['target_refs'] == [P.face_ref(states[identity]['faces'][face_ids[identity]])]
            assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
            assert not any(key in payload for key in ('furrow_samples', 'flank_samples', 'pixels',
                'landmarks', 'excluded_mask', 'mask', 'lipstick_review', 'face_skin'))
            assert json.loads(plans[0][index].people_json) == payload
