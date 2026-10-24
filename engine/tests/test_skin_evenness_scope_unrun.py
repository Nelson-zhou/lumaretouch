# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: partial facial colour-evenness preset/transfer contracts.

LNX-REF-PC-32465-C-60b7c0e3d1 is PARTIAL, not learned AI, body/multi-person
tone matching, defect recognition, blur, global tint or official parity.
Synthetic ownership observations and explicitly labelled routing/native doubles
are not real inference, compiled-native, full-file export or photo acceptance.
No product imports, execution, collection, tests, builds or typechecks were run.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import skin_evenness_scope as C, skin_evenness_state as S
from lumaretouch_engine import skin_evenness_native as N
from lumaretouch_engine import people_state as P, people_algorithms as A
from lumaretouch_engine import people_scope as REPLAY, scope as SC
from lumaretouch_engine import skin_colour_scope as COLOUR
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, isolate_other_captures)

LEAVES = ('/amount',)
LEGACY = {'_strength': .65, '_params': {'radius': 8, 'eps': .02,
    'texture_radius': 3, 'broad_gain': .35, 'mid_gain': .7, 'detail_gain': 1.1}}


def recipe(amount=0.):
    return {'recipe': {'version': 1, 'amount': amount}}


def engine_fixture(monkeypatch):
    """Schema fixture; coincident landmarks deliberately do not prove anatomy."""
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, analysis, current = colour_engine_fixture(monkeypatch)
    current.update(deepcopy(LEGACY))
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
    """Routing-only outer renderer stub, not target-support or pixel proof."""
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


def test_distinct_partial_scalar_registration_not_legacy_or_tint_alias():
    assert C.OP == 'lnx.skin_evenness.v1' and S.VERSION == 1
    assert S.CONTROL_ID == 'LNX-REF-PC-32465-C-60b7c0e3d1'
    assert C.OP not in (SC.OP_SKIN, COLOUR.OP, A.ENHANCE, A.WRINKLES)
    assert C.OP not in A.GEOMETRY and C.OP not in SC.DERIVED_PARAMETER_OPS
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True
    assert SC.MODULES[C.OP]['transferable'] is True
    assert SC.MODULES[C.OP]['label'] == '面部肤色均匀（独立强度，部分非 AI 调整）'
    assert A.defaults()[C.OP] == {'/amount': 0.}
    assert S.neutral() == recipe()['recipe'] and not S.active(S.neutral())


@pytest.mark.parametrize('amount', [0., .01, .4, 1.])
def test_only_version_and_amount_round_trip(amount):
    params = recipe(amount)
    assert C.check_params(params) == SC.check_params(C.OP, params) == params
    portable = {'schema': SC.PRESET_SCHEMA, 'id': 'skin-evenness', 'name': 'Facial colour evenness',
        'kind': 'portrait', 'modules': {C.OP: params}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(portable)))
    assert loaded['modules'] == {C.OP: params}
    assert set(loaded['modules'][C.OP]['recipe']) == {'version', 'amount'}
    assert set(A.leaves(params['recipe'])) == set(LEAVES)


@pytest.mark.parametrize('amount', [True, False, None, '0.5', float('nan'), float('inf'),
    float('-inf'), -.01, 1.01, 10**1000, -(10**1000)])
def test_invalid_amount_refuses_without_mutation(monkeypatch, amount):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state)
    with pytest.raises(ValueError): C.install(state, recipe(amount))
    with pytest.raises(SC.ScopeError): SC.check_params(C.OP, recipe(amount))
    assert state == before and not owner.commits


@pytest.mark.parametrize('raw', [None, {}, {'version': 1}, {'amount': .3},
    {'version': True, 'amount': .3}, {'version': 2, 'amount': .3},
    {'version': 1, 'strength': .3}, {'version': 1, 'broad_gain': .3}])
def test_exact_schema_does_not_alias_old_broad_gain(raw):
    with pytest.raises(ValueError): C.check_params({'recipe': raw})


@pytest.mark.parametrize('key', ['face_ref', 'owner', 'source', 'face_skin',
    'face_skin_observation', 'excluded', 'landmarks', 'mask', 'coverage',
    'reference_chroma', 'chroma_shift', 'rgb_delta', 'supported', 'native_result',
    'body', 'match_person', 'defects', 'ai', 'temperature', 'tint', 'broad_gain'])
def test_portable_transport_rejects_donor_support_and_other_controls(key):
    params = recipe(.3)
    with pytest.raises(ValueError): C.check_params({**params, key: {}})
    params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


def test_workflow_exports_canonical_scalar_without_migrating_legacy(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); before = owner.snapshot()
    # Existing broad smoothing does not imply any new evenness intent.
    captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert SC.params_of(captured, [C.OP]) == {C.OP: recipe()}
    put(owner, .35); captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert SC.params_of(captured, [C.OP]) == {C.OP: recipe(.35)}
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_skin_evenness_supported'] is True and not captured[C.REQUESTED]
    assert C.owner_identity(captured) == {'document_id': 'target-document', 'epoch': 'workspace',
        'people_scope': 'project', 'source_proof': {'asset_sha256': ASSET,
            'creative_source': None, 'original_sha256': ASSET}}
    assert not {'face_skin', 'landmarks', 'reference_chroma', 'chroma_shift'} & set(captured)
    assert {key: captured[key] for key in LEGACY} == current == LEGACY
    assert before['faces'] == owner.snapshot()['faces']
    assert engine._people_analyses[ASSET][FACE] is analysis and not owner.commits


@pytest.mark.parametrize('fault', ['merged-skin-only', 'observation', 'excluded', 'ref',
    'semantic-missing', 'model', 'observation-source', 'landmark-bytes',
    'landmark-count', 'synthetic', 'dimensions', 'donor-analysis'])
def test_capture_authenticates_actual_target_observation_and478(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'merged-skin-only': analysis['face_skin'] = analysis['face_skin_observation'] = None
    elif fault == 'observation': analysis.pop('face_skin_observation')
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'semantic-missing':
        analysis['evidence']['semantic_model_sha256'] = None
        owner.value['faces'][FACE]['evidence']['semantic_model_sha256'] = None
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
    assert captured['_skin_evenness_supported'] is False
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
def test_neutral_recovery_independent_of_native_and_observation(monkeypatch, native, observed):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: native)
    if not observed: analysis['face_skin_observation'] = None
    captured = C.capture(engine)
    assert captured['_skin_evenness_supported'] is observed
    assert captured['_skin_evenness_native_available'] is native
    C.install(captured, recipe()); assert C.params_of(captured) == recipe()
    if native and observed:
        C.install(captured, recipe(.4)); assert C.params_of(captured) == recipe(.4)
    else:
        with pytest.raises(ValueError): C.install(captured, recipe(.4))
    assert not owner.commits


def test_install_only_changes_scalar_transport_and_keeps_derived_guard(monkeypatch):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3)})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET] and after[C.OWNER] == before[C.OWNER]
    assert {key: after[key] for key in LEGACY} == LEGACY
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe())
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    with pytest.raises(ValueError): SC.apply_modules({}, {C.OP: recipe(.3)})
    assert not owner.commits


@pytest.mark.parametrize('derived_snapshot', ['current', 'previous'])
def test_generic_derived_restore_cannot_bypass_people_review(monkeypatch, derived_snapshot):
    from lumaretouch_engine import creative_derived_transfer as D
    current = {}; previous = {}
    (current if derived_snapshot == 'current' else previous)['_creative_base'] = {'fixture': 'derived'}
    monkeypatch.setattr(D, 'involved', lambda state, **kwargs: True)
    with pytest.raises(SC.ScopeError, match='历史'): SC.restore_modules(current, previous, [C.OP])


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged', 'source',
    'document', 'owner', 'epoch', 'proof', 'source-kind', 'original-source'])
def test_replay_rechecks_live_fences_not_captured_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'analysis': analysis['face_skin_observation'] = None
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


def test_neutral_recovery_keeps_legacy_broad_and_other_colour_intent(monkeypatch):
    engine, owner, _, current, calls = replay_fixture(monkeypatch)
    put(owner, .3)
    owner.value = P.set_override(owner.value, 'group', 'preserved', COLOUR.OP, '/tint', -.25)
    engine._people_analyses.clear(); monkeypatch.setattr(N, 'available', lambda: False)
    state = C.capture(engine); C.install(state, recipe()); REPLAY.replay_preset(engine, state)
    assert values(owner)[C.OP] == S.neutral() and values(owner)[COLOUR.OP]['tint'] == -.25
    assert {key: calls[-1][0][key] for key in LEGACY} == current == LEGACY
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


@pytest.mark.parametrize('amount', [0., .3])
def test_source_proof_mismatch_refuses_even_neutral(monkeypatch, amount):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, _, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': 'e' * 64,
        'creative_source': None, 'original_sha256': 'e' * 64})
    state = C.capture(engine); before = deepcopy(state)
    assert state['_skin_evenness_supported'] is False
    with pytest.raises(ValueError, match='有效来源'): C.install(state, recipe(amount))
    assert state == before and not owner.commits


def test_requested_neutral_cannot_fall_back_to_unmanaged_legacy(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe()); engine._people_managed = lambda: False
    with pytest.raises(ValueError, match='面部肤色均匀'): REPLAY.replay_preset(engine, state)
    assert not calls and not owner.commits


@pytest.mark.parametrize('start,end', [(0., .4), (.4, .2), (.3, 0.)])
@pytest.mark.parametrize('refused', [False, True])
def test_complete_renderer_routing_preserves_retained_intent_and_rolls_back(monkeypatch, start, end, refused):
    """Outer-renderer stub asserts atomic graph/recipe routing, not pixels."""
    engine, owner, analysis, _, _ = replay_fixture(monkeypatch)
    put(owner, start)
    owner.value = P.set_override(owner.value, 'group', 'preserved', COLOUR.OP, '/tint', -.25)
    before = owner.snapshot(); rendered = []
    def render(state, **kwargs):
        candidate = owner.snapshot(); rendered.append(candidate)
        assert kwargs['strict_local'] is True
        assert values(owner)[C.OP] == recipe(end)['recipe']
        assert values(owner)[COLOUR.OP]['tint'] == -.25
        assert {key: state[key] for key in LEGACY} == LEGACY
        for field in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert candidate[field] == before[field]
        assert all(leaf in candidate['overrides'] for leaf in before['overrides'] if leaf['operation_id'] != C.OP)
        if refused: raise RuntimeError('target chroma support or complete composition refused')
        return {'event': 'frame'}
    engine._replay_state = render; state = C.capture(engine); C.install(state, recipe(end))
    if refused:
        with pytest.raises(RuntimeError, match='composition refused'): REPLAY.replay_preset(engine, state)
        assert owner.snapshot() == before and len(owner.commits) == 2
    else:
        REPLAY.replay_preset(engine, state); assert len(owner.commits) == 1
    assert len(rendered) == 1 and engine._people_analyses[ASSET][FACE] is analysis


def test_unchanged_active_intent_still_routes_to_strict_renderer(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, .3); REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_outer_preset_transaction_restores_graph_and_legacy_recipe(monkeypatch):
    """Render-failure/history route only; no actual output pixels are claimed."""
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    from lumaretouch_engine.preset_transaction import apply_with_rollback, PresetApplyError
    engine, initial, _, _, _ = replay_fixture(monkeypatch)
    owner = PeopleGraphOwner(initial.snapshot()); engine._people_owner = lambda: owner
    before_graph = owner.snapshot(); before = C.capture(engine); after = deepcopy(before)
    C.install(after, recipe(.3)); calls = []
    def render(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        assert {key: state[key] for key in LEGACY} == LEGACY
        if len(calls) == 1: raise RuntimeError('target chroma support refused')
        return {'event': 'frame'}
    engine._replay_state = render
    with pytest.raises(PresetApplyError) as error:
        apply_with_rollback(lambda state, **kwargs: REPLAY.replay_preset(engine, state, **kwargs),
            before, after, preset_id='skin-evenness', emit=lambda event: None,
            invalidate=lambda: pytest.fail('Rollback must remain available'))
    assert error.value.rolled_back is True and len(calls) == 2
    assert calls[0][1]['strict_local'] is True and calls[1][1]['mode'] == 'preset_rollback'
    actual = owner.snapshot()
    assert actual['revision'] == before_graph['revision'] + 2 and owner.fence == 2
    assert {key: value for key, value in actual.items() if key != 'revision'} == {
        key: value for key, value in before_graph.items() if key != 'revision'}


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
def test_derived_capture_uses_own_source_and_keeps_generic_install_guard(monkeypatch, reuse_original):
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
    put(owner, .3); captured = C.capture(engine)
    assert captured['_skin_evenness_supported'] is (not reuse_original)
    if reuse_original:
        with pytest.raises(ValueError): C.params_of(captured)
    else:
        assert C.params_of(captured) == recipe(.3)
        assert C.owner_identity(captured)['source_proof']['asset_sha256'] == derived
    with pytest.raises(ValueError, match='合成来源'): C.install(captured, recipe())
    assert not owner.commits


def test_batch_selection_allows_only_amount():
    from lumaretouch_engine import people_batch_transfer as B
    state, _ = graph(); selected = {'source_ref': P.face_ref(state['faces'][FACE]),
        'selection': {C.OP: list(LEAVES)}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/version', '/broad_gain', '/tint', '/face_ref', '/face_skin',
            '/reference_chroma', '/chroma_shift', '/coverage', '/body'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [path]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


@pytest.mark.parametrize('policy,derived', [('explicit_face_map', False),
    ('confirmed_person_only', False), ('explicit_face_map', True)])
def test_transfer_payload_preserves_target_intent_and_exact_confirmed_receipt(policy, derived):
    from lumaretouch_engine import people_transfer_adapter as T
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for state, face_id in ((source, 'source-face'), (target, FACE)):
        if not derived:
            state['persons']['confirmed-person'] = {'anonymous': True}
            state['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
                'state': 'confirmed', 'confirmation_revision': 0}]
    source = P.set_override(source, 'face', 'source-face', C.OP, '/amount', .4)
    target = P.set_override(target, 'face', FACE, COLOUR.OP, '/tint', -.3)
    owner_scope = 'project' if policy == 'confirmed_person_only' else None
    source_owner = endpoint(source, 'source', scope=owner_scope)
    target_owner = endpoint(target, 'target', scope=owner_scope)
    if derived:
        target_owner['source_proof']['creative_source'] = {'sha256': 'e' * 64, 'width': 640, 'height': 480}
        target_owner['source_proof']['original_sha256'] = '3' * 64
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    selection = {C.OP: list(LEAVES)}
    if policy == 'confirmed_person_only':
        payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), 'e' * 64,
            selection, A.defaults(), **kwargs)
        assert payload['target_policy'] == policy
        assert payload['confirmed_person_id'] == 'confirmed-person'
        assert payload['confirmation_revisions'] == [(FACE, 0)]
    else:
        payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
            [P.face_ref(target['faces'][FACE])], selection, A.defaults(), **kwargs)
        payload['target_policy'] = policy
        assert 'confirmed_person_id' not in payload and 'confirmation_revisions' not in payload
    candidate = T.candidate(payload, source, target, **kwargs)
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': .4}]
    materialized = A.recipes(resolve(candidate, FACE, A.defaults()))
    assert materialized[C.OP] == recipe(.4)['recipe'] and materialized[COLOUR.OP]['tint'] == -.3
    assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    changed = deepcopy(target_owner); changed['source_proof'] = {'asset_sha256': 'f' * 64,
        'creative_source': None, 'original_sha256': 'f' * 64}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **{**kwargs, 'target_owner': changed})


def test_confirmed_ids_do_not_authorize_independent_owners():
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for state, face_id in ((source, 'source-face'), (target, FACE)):
        state['persons']['same-id'] = {'anonymous': True}
        state['links'] = [{'face_instance_id': face_id, 'person_id': 'same-id',
            'state': 'confirmed', 'confirmation_revision': 0}]
    source_owner, target_owner = endpoint(source, 'source'), endpoint(target, 'target')
    with pytest.raises(ValueError, match='Independent portrait owners'):
        prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), 'e' * 64,
            {C.OP: list(LEAVES)}, A.defaults(), source_document=source_owner['document'],
            target_document=target_owner['document'], source_owner=source_owner, target_owner=target_owner)


def source_fixture(asset, face_id, size, illumination, *, confirmed=False):
    """Independently generated source grids with real helper admission intact.

    Synthetic producer evidence is explicitly bound to each full current grid;
    it is not a real inference result or a donor mask promoted to a new source.
    """
    import numpy as np
    from test_skin_evenness_support_unrun import synthetic_observation
    _, analysis, rgb = synthetic_observation(size=size, source_size=size)
    rgb = np.ascontiguousarray(rgb*np.float32(illumination), dtype=np.float32)
    state = P.empty()
    face = P.new_face(asset, [.05, .03, .95, .97], deepcopy(analysis['evidence']))
    face['face_instance_id'] = face_id; state['faces'][face_id] = face
    analysis['face_ref'] = P.face_ref(face)
    analysis['face_skin_observation']['source_sha256'] = asset
    # A disabled/unresolved foreign face still contributes its protective box.
    foreign = deepcopy(face); foreign['face_instance_id'] = face_id+'-neighbour'
    foreign['enabled'] = False; foreign['evidence']['status'] = 'unresolved'
    foreign['box'] = [.01, .01, .06, .06]
    state['faces'][foreign['face_instance_id']] = foreign
    if confirmed:
        state['persons']['confirmed-person'] = {'anonymous': True}
        state['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    return state, analysis, rgb


def source_endpoint(state, identity, *, derived=False, confirmed=False):
    out = endpoint(state, identity, scope='project' if confirmed else None)
    if derived:
        face = next(iter(state['faces'].values())); evidence = face['evidence']
        out['source_proof']['creative_source'] = {'sha256': face['asset_sha256'],
            'width': evidence['source_width'], 'height': evidence['source_height']}
        out['source_proof']['original_sha256'] = '3' * 64
    return out


@pytest.mark.parametrize('policy,derived', [('explicit_face_map', False),
    ('confirmed_person_only', False), ('explicit_face_map', True)])
@pytest.mark.parametrize('fault', [None, 'target-occluded', 'target-clipped',
    'foreign-face', 'copied-source-analysis'])
def test_real_target_runtime_rebuilds_reference_with_only_native_doubled(monkeypatch, policy, derived, fault):
    """Real adapter, resolver, runtime, anatomy/semantic gates and compositor.

    Only native availability/prepare/apply are numerical boundary doubles. No
    support preparer or complete renderer is replaced here. This asserts own
    source routing and typed-field composition, not the native reference solve.
    """
    import numpy as np
    from lumaretouch_engine import people_transfer_adapter as T, people_render_runtime as RUNTIME
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    from test_skin_evenness_support_unrun import native_prepare_double, native_apply_double
    confirmed = policy == 'confirmed_person_only'
    source, source_analysis, source_rgb = source_fixture(ASSET, 'source-face', 256, .9, confirmed=confirmed)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/amount', .45)
    source_owner = source_endpoint(source, 'source', confirmed=confirmed)
    preparations = []; applications = []; measured = {}
    monkeypatch.setattr(N, 'available', lambda: True)
    monkeypatch.setattr(N, 'prepare', native_prepare_double(preparations))
    monkeypatch.setattr(N, 'apply', native_apply_double(applications))
    for asset, face_id, identity, size, illumination in (
            ('e'*64, 'target-a-face', 'target-a', 320, 1.),
            ('f'*64, 'target-b-face', 'target-b', 384, 1.1)):
        target, analysis, rgb = source_fixture(asset, face_id, size, illumination, confirmed=confirmed)
        target_owner = source_endpoint(target, identity, derived=derived, confirmed=confirmed)
        kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
            'source_owner': source_owner, 'target_owner': target_owner}
        if confirmed:
            payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), asset,
                {C.OP: list(LEAVES)}, A.defaults(), **kwargs)
            assert payload['target_policy'] == policy
            assert payload['confirmed_person_id'] == 'confirmed-person'
            assert payload['confirmation_revisions'] == [(face_id, 0)]
        else:
            payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
                [P.face_ref(target['faces'][face_id])], {C.OP: list(LEAVES)}, A.defaults(), **kwargs)
            payload['target_policy'] = policy
        candidate = T.candidate(payload, source, target, **kwargs)
        assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': .45}]
        assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
        bad = identity == 'target-b' and fault is not None
        if bad:
            if fault == 'target-occluded': analysis['excluded'][:] = 1.
            elif fault == 'target-clipped': rgb[:] = 1.
            elif fault == 'foreign-face': candidate['faces'][face_id+'-neighbour']['box'] = [.01, .01, .99, .99]
            else: analysis = source_analysis
        before = deepcopy(target); before_pixels = rgb.copy(); count = len(preparations)
        binding = target_owner['source_proof']['creative_source'] if derived else None
        def prepare():
            return RUNTIME.prepare(candidate, asset, rgb, {face_id: analysis},
                byte_budget=512*1024**2, document_id=identity, creative_source=binding)
        if bad:
            with pytest.raises(RUNTIME.PeoplePreparationRefused): prepare()
            assert len(preparations) == count
        else:
            prepared = prepare(); assert len(preparations) == count+1
            records = [record for record in prepared.effects if record.stage == 'skin_evenness']
            assert len(records) == 1
            record = records[0]; facts = record.facts; y, x, h, w = record.window
            assert record.face_ref == P.face_ref(target['faces'][face_id])
            assert record.delta is None and record.chroma_shift.shape == (h, w, 2)
            assert record.chroma_shift.flags.writeable is False
            np.testing.assert_array_equal(preparations[-1]['source'], rgb[y:y+h, x:x+w])
            assert preparations[-1]['source'].shape != source_rgb.shape
            assert facts['source_dimensions'] == facts['render_dimensions'] == [size, size]
            assert facts['face_skin_observation']['source_sha256'] == asset
            assert facts['reference_samples'] >= 64 and facts['protected_face_boxes'] == 1
            assert preparations[-1]['amount'] == .45 and facts['changed_pixels'] > 0
            # Apply the source-measured field to genuinely different CURRENT
            # RGB and preserve that input's linear luminance, not source luma.
            current = np.ascontiguousarray(rgb*.85+.025, dtype=np.float32)
            output, composition = prepared.apply_source_stage('skin_evenness', current)
            assert composition['changed_pixels'] > 0 and np.any(output != current)
            assert output.shape == current.shape and np.isfinite(output).all()
            linear = lambda rgb: np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)
            np.testing.assert_allclose(linear(output) @ [.2126, .7152, .0722],
                linear(current) @ [.2126, .7152, .0722], atol=2e-6, rtol=0)
            assert applications
            measured[identity] = (facts['radius'], float(preparations[-1]['source'].mean()))
        assert target == before
        np.testing.assert_array_equal(rgb, before_pixels)
    if fault is None:
        assert measured['target-a'][0] != measured['target-b'][0]
        assert measured['target-a'][1] != pytest.approx(measured['target-b'][1])
    else:
        assert set(measured) == {'target-a'}


@pytest.mark.parametrize('policy,derived', [('explicit_face_map', False),
    ('confirmed_person_only', False), ('explicit_face_map', True)])
@pytest.mark.parametrize('fault', [None, 'target-occluded', 'copied-source-analysis'])
def test_frozen_batch_preflight_uses_real_target_support_and_preserves_receipts(monkeypatch, policy, derived, fault):
    """Outer full-file I/O/freeze stubs, actual canonical target support inside.

    Decoder/export and plan persistence are not exercised. Their labelled
    boundary calls the real people runtime, support helper and compositor with
    only native numerical doubles; failed targets get no success payload.
    """
    import numpy as np
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL, people_render_runtime as RUNTIME
    from test_skin_evenness_support_unrun import native_prepare_double, native_apply_double
    confirmed = policy == 'confirmed_person_only'
    settings = {'source': (ASSET, 'source-face', 256, .9),
        'target-a': ('e'*64, 'target-a-face', 320, 1.),
        'target-b': ('f'*64, 'target-b-face', 384, 1.1)}
    states = {}; analyses = {}; sources = {}; face_ids = {}
    for identity, (asset, face_id, size, illumination) in settings.items():
        state, analysis, rgb = source_fixture(asset, face_id, size, illumination, confirmed=confirmed)
        states[identity] = state; analyses[identity] = analysis; sources[identity] = rgb; face_ids[identity] = face_id
    states['source'] = P.set_override(states['source'], 'face', 'source-face', C.OP, '/amount', .45)
    if fault == 'target-occluded': analyses['target-b']['excluded'][:] = 1.
    elif fault == 'copied-source-analysis': analyses['target-b'] = analyses['source']
    preparations = []; monkeypatch.setattr(N, 'available', lambda: True)
    monkeypatch.setattr(N, 'prepare', native_prepare_double(preparations))
    monkeypatch.setattr(N, 'apply', native_apply_double())
    owner = Owner(states['source'])
    rows = [{'document_id': identity, 'path': identity+'.jpg', 'state': deepcopy(LEGACY)} for identity in states]
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
        _body_bank=lambda: pytest.fail('Facial evenness must not acquire body coverage'))
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
        assert {key: state[key] for key in LEGACY} == LEGACY
        target = states[document_id]; face_id = face_ids[document_id]
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert people_graph[key] == target[key]
        assert [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']] == [
            {'scope': 'face', 'target_id': face_id, **expected_parameters[0]}]
        renders.append(document_id); rgb = sources[document_id]
        target_proof = proof(target, document_id)['source_proof']
        prepared = RUNTIME.prepare(people_graph, target_proof['asset_sha256'], rgb,
            {face_id: analyses[document_id]}, byte_budget=512*1024**2,
            document_id=document_id, creative_source=target_proof['creative_source'])
        record = next(record for record in prepared.effects if record.stage == 'skin_evenness')
        assert record.face_ref == P.face_ref(target['faces'][face_id])
        y, x, h, w = record.window
        np.testing.assert_array_equal(preparations[-1]['source'], rgb[y:y+h, x:x+w])
        assert record.chroma_shift.shape == (h, w, 2) and record.delta is None
        assert record.facts['protected_face_boxes'] == 1
        output, composition = prepared.apply_source_stage('skin_evenness', rgb)
        assert composition['changed_pixels'] > 0
        measured[document_id] = (record.facts['radius'], float(preparations[-1]['source'].mean()))
        return output, {'fixture': 'actual target support/compositor; not full-file I/O or native acceptance'}
    monkeypatch.setattr(FULL, 'render', render); plans = []
    def freeze(workspace, source_id, revision, path, modules, params, target_policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda plan: {},
        emit=lambda event: None, emit_result=lambda request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-skin-evenness',
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
    before = deepcopy(states); before_rows = deepcopy(rows); B.preflight(engine, controller, request)
    assert states == before and rows == before_rows and not owner.commits
    assert renders == ['target-a', 'target-b']
    result = replies[-1]
    assert (result['ok'], result['blocked']) == ((1, 1) if fault else (2, 0))
    assert len(preparations) == (1 if fault else 2)
    assert set(measured) == ({'target-a'} if fault else {'target-a', 'target-b'})
    for index, identity in enumerate(('target-a', 'target-b')):
        payload = result['targets'][index]['people_transfer']
        if fault and identity == 'target-b':
            assert payload is None and plans[0][index].people_json is None
            assert result['targets'][index]['blocked']
        else:
            assert payload['parameters'] == expected_parameters
            assert payload['target_policy'] == policy
            assert payload['target_refs'] == [P.face_ref(states[identity]['faces'][face_ids[identity]])]
            assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
            assert not {'reference_chroma', 'chroma_shift', 'pixels', 'landmarks', 'mask', 'face_skin'} & set(payload)
            frozen = json.loads(plans[0][index].people_json)
            # Canonical JSON turns confirmed revision tuples into lists; compare
            # normalized complete receipts, not Python tuple/list incidental form.
            assert frozen == json.loads(json.dumps(payload))
            if confirmed:
                assert frozen['confirmed_person_id'] == 'confirmed-person'
                assert frozen['confirmation_revisions'] == [[face_ids[identity], 0]]
            else:
                assert 'confirmed_person_id' not in frozen and 'confirmation_revisions' not in frozen
