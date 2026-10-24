# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN scalar body-to-own-face preset and frozen batch contracts.

LNX-REF-PC-32465-C-d8b09012a9 is PARTIAL, not learned AI, body evenness,
brightness matching, donor colour transfer or equivalence to later face edits.
Synthetic actual-class observations use real review/ownership validation; native
availability, outer-render and export-snapshot boundaries are labelled doubles.
No product import, fixture execution, collection, native run, inference, build,
typecheck, full-file export or photographic acceptance happened while authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
import json
import numpy as np
import pytest

from lumaretouch_engine import body_face_match_scope as C, body_face_match_state as S
from lumaretouch_engine import body_face_match_native as N, skin_colour_support as FACE
from lumaretouch_engine import body_skin_evenness_scope as BODY_EVENNESS, skin_evenness_scope as FACE_EVENNESS
from lumaretouch_engine import skin_colour_body_support as BODY, skin_colour_transfer_review as REVIEW
from lumaretouch_engine import people_state as P, people_algorithms as A, body_pose_state as B
from lumaretouch_engine import people_scope as REPLAY, scope as SC
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_body_support_unrun import fixture as body_fixture
from test_skin_colour_scope_unrun import Owner, endpoint, isolate_other_captures
from test_body_skin_evenness_scope_unrun import independent_fixture as unreviewed_independent_fixture

LEAVES = ('/amount',)
LEGACY = {'_strength': .65, '_params': {'radius': 8, 'eps': .02,
    'texture_radius': 3, 'broad_gain': .35, 'mid_gain': .7, 'detail_gain': 1.1}}


def recipe(amount=0.):
    return {'recipe': {'version': 1, 'amount': amount}}


def add_face_observation(analysis, ref):
    """Synthetic own-face class observation, never copied from another target."""
    analysis.update(skin=np.ones((64, 64), np.float32), excluded=np.zeros((64, 64), np.float32),
        face_skin=np.ones((64, 64), np.float32), face_skin_observation={
            'contract': FACE.CONTRACT, 'source_sha256': ref['asset_sha256'],
            'semantic_model_sha256': analysis['evidence']['semantic_model_sha256'],
            'producer_width': 64, 'producer_height': 64})


def retained_fixture(*, family=C.FAMILY):
    graph, assets, ref, bank, analysis, review = body_fixture()
    add_face_observation(analysis, ref)
    if family is not None:
        graph, assets = BODY.retain(graph, assets, ref, bank, analysis, review, family=family)
    return graph, assets, ref, bank, analysis, review


def engine_fixture(monkeypatch, *, family=C.FAMILY):
    from lumaretouch_engine import people_transfer_inventory as I
    graph, assets, ref, bank, analysis, review = retained_fixture(family=family)
    owner = Owner(graph); current = deepcopy(LEGACY); asset = ref['asset_sha256']; face_id = ref['face_instance_id']
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    engine = SimpleNamespace(_people_managed=lambda: True, _people_owner=lambda: owner,
        _people_source=lambda: {'sha256': asset, 'width': 64, 'height': 64},
        _people_cursors={asset: face_id},
        _people_targets={asset: {'scope': 'face', 'target_id': face_id, 'face_ref': ref}},
        _people_analyses={asset: {face_id: analysis}}, _people_support=assets,
        _body_bank=lambda: bank, _people_analysis_key='old',
        _capture_state=lambda: deepcopy(current), _document_versions=lambda: versions,
        _docs=[{'document_id': 'target-document', 'path': 'fixture.jpg', 'state': current}], _doc_index=0)
    monkeypatch.setattr(N, 'available', lambda: True)
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': asset,
        'creative_source': None, 'original_sha256': asset})
    return engine, owner, ref, bank, analysis, review, current


def replay_fixture(monkeypatch):
    fixture = engine_fixture(monkeypatch); engine = fixture[0]
    isolate_other_captures(monkeypatch); calls = []
    def replay(state, **kwargs):
        calls.append((deepcopy(state), kwargs)); return {'event': 'frame'}
    engine._replay_state = replay
    return (*fixture, calls)


def put(owner, ref, amount):
    owner.value = P.set_override(owner.value, 'face', ref['face_instance_id'], C.OP, '/amount', amount)


def values(owner, ref):
    return A.recipes(resolve(owner.snapshot(), ref['face_instance_id'], A.defaults()))


def test_exact_distinct_operation_requirement_and_scalar_registration():
    assert C.OP == 'lnx.body_face_match.v1' and S.VERSION == 1
    assert S.CONTROL_ID == 'LNX-REF-PC-32465-C-d8b09012a9'
    assert C.FAMILY == 'body_face_match'
    assert BODY.family_spec(C.FAMILY, C.OP) == ('body_face_match_visibility', C.OP)
    assert C.OP not in (BODY_EVENNESS.OP, FACE_EVENNESS.OP, SC.OP_SKIN)
    assert C.OP not in SC.DERIVED_PARAMETER_OPS and C.OP not in A.GEOMETRY
    assert SC.MODULES[C.OP]['read'] is C.params_of and SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True and SC.MODULES[C.OP]['transferable'] is True
    assert SC.MODULES[C.OP]['label'] == '身体与本人面部肤色匹配（独立审核范围，部分非 AI 调整）'
    assert A.defaults()[C.OP] == {'/amount': 0.} and S.neutral() == recipe()['recipe']


@pytest.mark.parametrize('amount', [0., .01, .4, 1.])
def test_scalar_portable_roundtrip_contains_only_version_and_amount(amount):
    params = recipe(amount)
    assert C.check_params(params) == SC.check_params(C.OP, params) == params
    portable = {'schema': SC.PRESET_SCHEMA, 'id': 'body-face-match', 'name': 'Body to own face',
        'kind': 'portrait', 'modules': {C.OP: params}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(portable)))
    assert loaded['modules'] == {C.OP: params}
    assert set(loaded['modules'][C.OP]['recipe']) == {'version', 'amount'}
    assert set(A.leaves(params['recipe'])) == set(LEAVES)


@pytest.mark.parametrize('amount', [True, False, None, '0.5', float('nan'), float('inf'),
    float('-inf'), -.01, 1.01, 10**1000, -(10**1000)])
def test_invalid_amount_never_mutates_scalar_or_graph(monkeypatch, amount):
    engine, owner, *_ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state)
    with pytest.raises(ValueError): C.install(state, recipe(amount))
    with pytest.raises(SC.ScopeError): SC.check_params(C.OP, recipe(amount))
    assert state == before and not owner.commits


@pytest.mark.parametrize('raw', [None, {}, {'version': 1}, {'amount': .3},
    {'version': True, 'amount': .3}, {'version': 2, 'amount': .3},
    {'version': 1, 'strength': .3}, {'version': 1, 'broad_gain': .3}])
def test_recipe_does_not_migrate_adjacent_evenness_or_legacy_intent(raw):
    with pytest.raises(ValueError): C.check_params({'recipe': raw})


@pytest.mark.parametrize('key', ['face_ref', 'body_ref', 'person_id', 'source', 'owner', 'body_skin',
    'face_skin', 'body_skin_observation', 'face_skin_observation', 'review', 'recipe', 'manual',
    'support_sha256', 'points_sha256', 'mask', 'coverage', 'reference_chroma', 'own_face_reference',
    'chroma_shift', 'target_face_colour', 'brightness', 'temperature', 'tint', 'broad_gain', 'ai'])
def test_transport_rejects_reference_pixels_masks_consent_and_other_controls(key):
    with pytest.raises(ValueError): C.check_params({**recipe(.3), key: {}})
    params = recipe(.3); params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


def test_workflow_capture_keeps_body_and_face_references_nonportable(monkeypatch):
    engine, owner, ref, bank, analysis, _, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch)
    put(owner, ref, .35); before = owner.snapshot()
    captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert SC.params_of(captured, [C.OP]) == {C.OP: recipe(.35)}
    assert captured[C.TARGET] == ref and captured[C.REQUESTED] is False
    expected = REVIEW.describe(owner.snapshot(), engine._people_support, ref, bank, analysis,
        recipe(.35)['recipe'], family=C.FAMILY)
    assert captured[C.COVERAGE] == expected and expected['scope'] == 'reviewed-body-own-face'
    assert set(expected) == {'face_ref', 'scope', 'body_review_sha256', 'own_face_reference'}
    identity = expected['own_face_reference']
    assert identity == {'face_ref': ref, 'face_skin_observation': analysis['face_skin_observation'],
        'landmark_digest': analysis['evidence']['landmark_digest'],
        'reference_method': 'effective-source-stage-own-face-robust-log-chroma'}
    assert C.owner_identity(captured)['document_id'] == 'target-document'
    assert owner.snapshot() == before and {key: captured[key] for key in LEGACY} == current == LEGACY
    assert not {'review', 'manual', 'body_ref', 'reference_chroma', 'face_skin', 'body_skin'} & set(captured)
    assert not owner.commits


@pytest.mark.parametrize('family', [None, 'skin_colour', 'skin_finish', 'body_skin_evenness'])
def test_other_body_consent_cannot_authorize_matching(monkeypatch, family):
    engine, owner, *_ = engine_fixture(monkeypatch, family=family)
    captured = C.capture(engine); assert captured['_body_face_match_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3))
    C.install(captured, recipe()); assert C.params_of(captured) == recipe()
    assert captured[C.COVERAGE]['scope'] == 'neutral-no-effect' and not owner.commits


@pytest.mark.parametrize('fault', ['body-unlink', 'body-disabled', 'body-revision', 'people-revision',
    'review-asset', 'body-observation', 'body-model', 'body-detector', 'body-source', 'merged-body',
    'face-observation', 'face-model', 'face-source', 'face-grid', 'merged-face', 'face-missing',
    'excluded', 'landmarks', 'wrong-ref', 'dimensions', 'body-grid'])
def test_capture_requires_both_actual_target_observations_and_exact_review(monkeypatch, fault):
    engine, owner, ref, bank, analysis, review, _ = engine_fixture(monkeypatch)
    if fault == 'body-unlink': engine._body_bank = lambda: B.unlink(bank, review['body_ref'])
    elif fault == 'body-disabled': B.target(bank, review['body_ref'])['enabled'] = False
    elif fault == 'body-revision': bank['association_revision'] += 1
    elif fault == 'people-revision': owner.value['association_revision'] += 1
    elif fault == 'review-asset': engine._people_support = {}
    elif fault == 'body-observation': analysis['body_skin_observation'] = None
    elif fault == 'body-model': analysis['body_skin_observation']['semantic_model_sha256'] = '9'*64
    elif fault == 'body-detector': analysis['body_skin_observation']['detector_model_sha256'] = '9'*64
    elif fault == 'body-source': analysis['body_skin_observation']['source_sha256'] = '9'*64
    elif fault == 'merged-body': analysis['body_skin'] = analysis['body_skin_observation'] = None
    elif fault == 'face-observation': analysis['face_skin_observation'] = None
    elif fault == 'face-model': analysis['face_skin_observation']['semantic_model_sha256'] = '9'*64
    elif fault == 'face-source': analysis['face_skin_observation']['source_sha256'] = '9'*64
    elif fault == 'face-grid': analysis['face_skin'] = np.ones((32, 32), np.float32)
    elif fault == 'merged-face': analysis['face_skin'] = analysis['face_skin_observation'] = None
    elif fault == 'face-missing': analysis.pop('face_skin')
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'landmarks': analysis['landmarks'][0, 0] = .8
    elif fault == 'wrong-ref': analysis['face_ref'] = {**ref, 'analysis_revision': 1}
    elif fault == 'dimensions': engine._people_source = lambda: {'sha256': ref['asset_sha256'], 'width': 80, 'height': 64}
    else: analysis['body_skin'] = np.ones((32, 32), np.float32)
    captured = C.capture(engine); before = owner.snapshot()
    assert captured['_body_face_match_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3))
    C.install(captured, recipe()); assert owner.snapshot() == before and not owner.commits


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged', 'no-document'])
def test_neutral_still_requires_enabled_exact_face_and_document_owner(monkeypatch, fault):
    engine, owner, ref, *_ = engine_fixture(monkeypatch); asset = ref['asset_sha256']
    if fault == 'no-cursor': engine._people_cursors.clear()
    elif fault == 'group-target': engine._people_targets[asset] = {'scope': 'all_people', 'target_id': asset}
    elif fault == 'stale-target': engine._people_targets[asset]['face_ref'] = {**ref, 'analysis_revision': 1}
    elif fault == 'disabled': owner.value['faces'][ref['face_instance_id']]['enabled'] = False
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    else: engine._docs.clear()
    captured = C.capture(engine)
    with pytest.raises(ValueError): C.params_of(captured)
    with pytest.raises(ValueError): C.install(captured, recipe())
    assert not owner.commits


def test_neutral_recovery_without_body_face_analysis_or_native_preserves_other_intent(monkeypatch):
    engine, owner, ref, _, _, _, current, calls = replay_fixture(monkeypatch)
    put(owner, ref, .4)
    owner.value = P.set_override(owner.value, 'face', ref['face_instance_id'], FACE_EVENNESS.OP, '/amount', .2)
    before_faces = deepcopy(owner.value['faces']); before_support = deepcopy(engine._people_support)
    engine._people_analyses.clear(); engine._body_bank = lambda: pytest.fail('Neutral recovery needs no live body')
    monkeypatch.setattr(N, 'available', lambda: False)
    captured = C.capture(engine); C.install(captured, recipe()); REPLAY.replay_preset(engine, captured)
    assert values(owner, ref)[C.OP] == S.neutral() and values(owner, ref)[FACE_EVENNESS.OP]['amount'] == .2
    assert owner.value['faces'] == before_faces and engine._people_support == before_support
    assert calls[-1][1]['strict_local'] is True and {key: calls[-1][0][key] for key in LEGACY} == current == LEGACY


@pytest.mark.parametrize('fault', ['native', 'consent', 'body', 'body-analysis', 'face-analysis',
    'target', 'document', 'epoch', 'owner', 'proof', 'source-kind', 'source-original', 'unmanaged'])
def test_replay_refreshes_live_fences_not_captured_support_booleans(monkeypatch, fault):
    engine, owner, ref, bank, analysis, review, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'consent': owner.value = BODY.detach(owner.value, ref, family=C.FAMILY)
    elif fault == 'body': engine._body_bank = lambda: B.unlink(bank, review['body_ref'])
    elif fault == 'body-analysis': analysis['body_skin_observation'] = None
    elif fault == 'face-analysis': analysis['face_skin_observation'] = None
    elif fault == 'target': engine._people_targets[ref['asset_sha256']]['face_ref'] = {**ref, 'analysis_revision': 1}
    elif fault == 'document': engine._docs[0]['document_id'] = 'other-document'
    elif fault == 'epoch': engine._document_versions().workspace = 'other-workspace'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    elif fault == 'proof': state.pop(C.OWNER)
    elif fault == 'source-kind': state[C.OWNER]['source_proof']['creative_source'] = {'sha256': ref['asset_sha256'], 'width': 64, 'height': 64}
    elif fault == 'source-original': state[C.OWNER]['source_proof']['original_sha256'] = '9'*64
    else: engine._people_managed = lambda: False
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


@pytest.mark.parametrize('amount', [0., .3])
def test_effective_source_mismatch_refuses_even_neutral(monkeypatch, amount):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, *_ = engine_fixture(monkeypatch)
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': '9'*64,
        'creative_source': None, 'original_sha256': '9'*64})
    with pytest.raises(ValueError, match='有效来源'): C.install(C.capture(engine), recipe(amount))
    assert not owner.commits


def test_install_changes_scalar_only_and_generic_derived_guard_stays_closed(monkeypatch):
    engine, owner, *_ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3)})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET] and after[C.OWNER] == before[C.OWNER]
    assert {key: after[key] for key in LEGACY} == LEGACY
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe())
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    assert not owner.commits


@pytest.mark.parametrize('derived_snapshot', ['current', 'previous'])
def test_generic_derived_restore_cannot_bypass_body_and_own_face_review(monkeypatch, derived_snapshot):
    from lumaretouch_engine import creative_derived_transfer as D
    current = {}; previous = {}; (current if derived_snapshot == 'current' else previous)['_creative_base'] = {}
    monkeypatch.setattr(D, 'involved', lambda state, **kwargs: True)
    with pytest.raises(SC.ScopeError, match='历史'): SC.restore_modules(current, previous, [C.OP])


@pytest.mark.parametrize('start,end', [(0., .4), (.4, .2), (.3, 0.)])
@pytest.mark.parametrize('refused', [False, True])
def test_strict_complete_renderer_and_atomic_graph_rollback(monkeypatch, start, end, refused):
    """Outer-render double verifies ownership/routing, not numerical pixels."""
    engine, owner, ref, _, _, _, _, _ = replay_fixture(monkeypatch)
    put(owner, ref, start)
    owner.value = P.set_override(owner.value, 'face', ref['face_instance_id'], BODY_EVENNESS.OP, '/amount', .2)
    before = owner.snapshot(); before_support = deepcopy(engine._people_support); rendered = []
    def render(state, **kwargs):
        rendered.append(owner.snapshot())
        assert kwargs['strict_local'] is True and values(owner, ref)[C.OP] == recipe(end)['recipe']
        assert values(owner, ref)[BODY_EVENNESS.OP]['amount'] == .2
        assert {key: state[key] for key in LEGACY} == LEGACY
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert owner.value[key] == before[key]
        assert engine._people_support == before_support
        if refused: raise RuntimeError('own-face measurement or composition refused')
        return {'event': 'frame'}
    engine._replay_state = render; state = C.capture(engine); C.install(state, recipe(end))
    if refused:
        with pytest.raises(RuntimeError, match='composition refused'): REPLAY.replay_preset(engine, state)
        assert owner.snapshot() == before and len(owner.commits) == 2
    else:
        REPLAY.replay_preset(engine, state); assert len(owner.commits) == 1
    assert len(rendered) == 1


def test_unchanged_active_intent_still_requires_strict_complete_render(monkeypatch):
    engine, owner, ref, _, _, _, _, calls = replay_fixture(monkeypatch)
    put(owner, ref, .3); REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def independent_fixture(asset, face_id, *, family=C.FAMILY):
    """Fresh synthetic source observations created before any family review."""
    graph, assets, ref, bank, analysis, review = unreviewed_independent_fixture(asset, face_id, family=None)
    add_face_observation(analysis, ref)
    if family is not None:
        graph, assets = BODY.retain(graph, assets, ref, bank, analysis, review, family=family)
    return graph, assets, ref, bank, analysis, review


def prepared_transfer(*, policy='explicit_face_map', derived=False, family=C.FAMILY, amount=.4):
    from lumaretouch_engine import people_transfer_adapter as T
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, source_assets, source_ref, _, _, _ = independent_fixture('a'*64, 'source-face')
    target, target_assets, target_ref, target_bank, target_analysis, _ = independent_fixture('9'*64, 'target-face', family=family)
    source = P.set_override(source, 'face', source_ref['face_instance_id'], C.OP, '/amount', amount)
    target = P.set_override(target, 'face', target_ref['face_instance_id'], FACE_EVENNESS.OP, '/amount', .2)
    confirmed = policy == 'confirmed_person_only'
    source_owner = endpoint(source, 'source', scope='project' if confirmed else None)
    target_owner = endpoint(target, 'target', scope='project' if confirmed else None)
    if derived:
        target_owner['source_proof']['creative_source'] = {'sha256': target_ref['asset_sha256'], 'width': 64, 'height': 64}
        target_owner['source_proof']['original_sha256'] = '8'*64
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    if confirmed:
        payload = prepare_confirmed(source, target, source_ref, target_ref['asset_sha256'],
            {C.OP: list(LEAVES)}, A.defaults(), **kwargs)
    else:
        payload = T.prepare(source, target, source_ref, [target_ref], {C.OP: list(LEAVES)}, A.defaults(), **kwargs)
        payload['target_policy'] = policy
    candidate = T.candidate(payload, source, target, **kwargs)
    return payload, candidate, source, target, source_assets, target_assets, target_ref, target_bank, target_analysis, kwargs


@pytest.mark.parametrize('policy,derived', [('explicit_face_map', False),
    ('confirmed_person_only', False), ('explicit_face_map', True)])
def test_reviewed_mapping_moves_only_amount_then_describes_target_own_reference(policy, derived):
    payload, candidate, _, target, source_assets, target_assets, ref, bank, analysis, _ = prepared_transfer(policy=policy, derived=derived)
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': .4}]
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert candidate[key] == target[key]
    result = A.recipes(resolve(candidate, ref['face_instance_id'], A.defaults()))
    assert result[C.OP] == recipe(.4)['recipe'] and result[FACE_EVENNESS.OP]['amount'] == .2
    own, own_key = BODY.resolve(candidate, target_assets, ref, bank, analysis, family=C.FAMILY)
    assert own['face_ref'] == ref and own_key in target_assets and own_key not in source_assets
    disclosure = REVIEW.describe(candidate, target_assets, ref, bank, analysis, result[C.OP], family=C.FAMILY)
    assert disclosure['body_review_sha256'] == own_key and disclosure['scope'] == 'reviewed-body-own-face'
    assert disclosure['own_face_reference']['face_ref'] == ref
    assert disclosure['own_face_reference']['face_skin_observation']['source_sha256'] == ref['asset_sha256']
    assert not {'recipe', 'manual', 'body_ref', 'body_skin', 'face_skin', 'reference_chroma', 'chroma_shift'} & set(payload)
    if policy == 'confirmed_person_only': assert payload['confirmed_person_id'] == 'confirmed-person'


@pytest.mark.parametrize('family', [None, 'skin_colour', 'skin_finish', 'body_skin_evenness'])
def test_mapping_cannot_import_donor_consent_or_reference_to_target(family):
    _, candidate, _, target, donor_assets, assets, ref, bank, analysis, _ = prepared_transfer(family=family)
    assert candidate['faces'] == target['faces']
    with pytest.raises(ValueError, match='own target-local'):
        REVIEW.describe(candidate, assets, ref, bank, analysis, recipe(.4)['recipe'], family=C.FAMILY)
    with pytest.raises(ValueError):
        REVIEW.describe(candidate, donor_assets, ref, bank, analysis, recipe(.4)['recipe'], family=C.FAMILY)


@pytest.mark.parametrize('fault', [None, 'missing', 'body-unlink', 'donor-assets', 'donor-analysis',
    'face-missing', 'face-source', 'snapshot-owner', 'snapshot-source'])
@pytest.mark.parametrize('derived', [False, True])
def test_frozen_disclosure_resolves_exact_target_snapshot_and_own_face(monkeypatch, fault, derived):
    """Snapshot/context doubles only; real body ownership and review validators."""
    from lumaretouch_engine import full_candidate_render as FULL, body_pose_project as BP, shoulder_shape_project as PACK
    payload, candidate, _, _, source_assets, assets, ref, bank, analysis, _ = prepared_transfer(derived=derived)
    row = {'document_id': 'target', 'path': 'target.jpg', 'state': {BP.KEY: PACK.pack(bank)}}
    if derived: row['state']['_creative_base'] = {'fixture': 'own immutable source, not a real file'}
    if fault == 'missing': candidate = BODY.detach(candidate, ref, family=C.FAMILY)
    elif fault == 'body-unlink': row['state'][BP.KEY] = PACK.pack(B.unlink(bank, next(iter(bank['bodies'].values()))['record']['body_ref']))
    elif fault == 'donor-assets': assets = source_assets
    elif fault == 'donor-analysis': analysis = independent_fixture('a'*64, 'source-face')[4]
    elif fault == 'face-missing': analysis['face_skin'] = analysis['face_skin_observation'] = None
    elif fault == 'face-source': analysis['face_skin_observation']['source_sha256'] = 'a'*64
    snapshot_calls = []
    def snapshot(state, path, actual, *, context, document_id):
        assert state is row['state'] and path == row['path'] and actual == candidate
        assert context == {'fixture': 'target context'} and document_id == 'target'
        snapshot_calls.append(document_id)
        return {'state': actual, 'document_id': 'other' if fault == 'snapshot-owner' else document_id,
            'asset_sha256': 'a'*64 if fault == 'snapshot-source' else ref['asset_sha256'],
            'support_assets': assets, 'analyses': {ref['face_instance_id']: analysis}}
    engine = SimpleNamespace(_people_export_snapshot=snapshot)
    monkeypatch.setattr(FULL, 'people_context', lambda actual, actual_row: {'fixture': 'target context'})
    before = deepcopy(candidate); before_payload = deepcopy(payload); before_assets = deepcopy(assets)
    if fault is not None:
        with pytest.raises(ValueError): REVIEW.for_target(engine, row, candidate, payload, family=C.FAMILY)
    else:
        coverage = REVIEW.for_target(engine, row, candidate, payload, family=C.FAMILY)
        expected = REVIEW.describe(candidate, assets, ref, bank, analysis, recipe(.4)['recipe'], family=C.FAMILY)
        assert coverage == {'version': 1, 'support_transfer': 'none', 'targets': [expected]}
        frozen = json.loads(json.dumps({**payload, 'body_face_match_coverage': coverage}))
        assert frozen['body_face_match_coverage']['targets'][0]['body_review_sha256'] in assets
        assert frozen['parameters'] == payload['parameters']
    assert candidate == before and payload == before_payload and assets == before_assets
    assert len(snapshot_calls) == (0 if fault == 'missing' else 1)


@pytest.mark.parametrize('family', [None, C.FAMILY, 'skin_colour', 'skin_finish', 'body_skin_evenness'])
def test_neutral_receipt_needs_no_live_body_or_face_reference(family):
    payload, candidate, _, _, _, _, ref, _, _, _ = prepared_transfer(family=family, amount=0.)
    engine = SimpleNamespace(_people_export_snapshot=lambda *args, **kwargs:
        pytest.fail('Neutral disclosure must not acquire target body or face evidence'))
    assert REVIEW.for_target(engine, {'state': {}}, candidate, payload, family=C.FAMILY) == {
        'version': 1, 'support_transfer': 'none', 'targets': [
            {'face_ref': ref, 'scope': 'neutral-no-effect', 'body_review_sha256': None, 'own_face_reference': None}]}


def test_unrelated_transfer_does_not_claim_body_face_coverage():
    payload = {'parameters': [{'operation_id': BODY_EVENNESS.OP, 'parameter_path': '/amount', 'value': .4}]}
    assert REVIEW.for_target(None, None, None, payload, family=C.FAMILY) is None


def commit_fixture(monkeypatch, *, derived=False, amount=.4):
    """Actual adapter/commit/review helpers; render/storage boundaries doubled.

    This never represents full-file native rendering or ledger publication as
    exercised. Render calls and graph routing are visible assertions only.
    """
    from lumaretouch_engine import people_batch_transfer as BT, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL, body_pose_project as BP, shoulder_shape_project as PACK
    from lumaretouch_engine import people_batch_ledger as LEDGER
    payload, staged, source, target, _, assets, ref, bank, analysis, kwargs = prepared_transfer(derived=derived, amount=amount)
    payload['body_face_match_coverage'] = {'version': 1, 'support_transfer': 'none', 'targets': [
        REVIEW.describe(staged, assets, ref, bank, analysis, recipe(amount)['recipe'], family=C.FAMILY)]}
    states = {'source': source, 'target': target}
    rows = [{'document_id': identity, 'path': identity+'.jpg', 'copy_number': 1,
        'state': {BP.KEY: PACK.pack(bank)} if identity == 'target' else {}} for identity in states]
    versions = SimpleNamespace(workspace='workspace',
        version=lambda row: SimpleNamespace(document_id=row['document_id'], revision=2),
        find=lambda actual_rows, identity: next(((i, row) for i, row in enumerate(actual_rows)
            if row['document_id'] == identity), None))
    batch = SimpleNamespace(versions=versions, documents=SimpleNamespace(rows=lambda: rows, remember_current=lambda: None))
    observed = {'snapshots': [], 'renders': [], 'prepare': [], 'verify': [], 'publish': [], 'claim': [], 'events': []}
    owner = Owner(source)
    def snapshot(state, path, graph, *, context, document_id):
        assert state is rows[1]['state'] and path == 'target.jpg' and document_id == 'target'
        observed['snapshots'].append(document_id)
        return {'state': graph, 'document_id': document_id, 'asset_sha256': ref['asset_sha256'],
                'support_assets': assets, 'analyses': {ref['face_instance_id']: analysis}}
    engine = SimpleNamespace(_docs=rows, _batch_controller=lambda: batch, _people_owner=lambda: owner,
        _document_versions=lambda: versions, _people_export_snapshot=snapshot)
    monkeypatch.setattr(BT.V, 'row_snapshot', lambda actual, row: deepcopy(states[row['document_id']]))
    def proof(actual, row, graph, *, source_row=None):
        result = endpoint(graph, row['document_id'])
        if row['document_id'] == 'target': result['source_proof'] = deepcopy(kwargs['target_owner']['source_proof'])
        return result
    monkeypatch.setattr(I, 'proof', proof)
    monkeypatch.setattr(BT.SOURCE, 'row_proof', lambda row: proof(engine, row, states[row['document_id']])['source_proof'])
    def verify_source(row, expected):
        assert expected == BT.SOURCE.row_proof(row); return expected
    monkeypatch.setattr(BT.SOURCE, 'verify_row', verify_source)
    monkeypatch.setattr(FULL, 'people_context', lambda actual, row: {'fixture': 'target context'})
    def render(actual, row, state, document_id, revision, *, people_graph):
        assert actual is engine and row is rows[1] and state is rows[1]['state']
        assert (document_id, revision) == ('target', '2') and people_graph == staged
        observed['renders'].append(document_id); return None, {'fixture': 'full-file renderer boundary only'}
    monkeypatch.setattr(FULL, 'render', render)
    # The actual commit must validate once before adding the scoped plan, then
    # re-read the exact receipt after aggregate full-candidate preparation.
    monkeypatch.setattr(LEDGER, '_targets', lambda batch, actual, plans: {})
    def prepare(actual, plans, targets):
        observed['prepare'].append(True)
        from lumaretouch_engine.people_candidate_render import validate
        for item in plans.values(): validate(actual, item['row'], item['candidate'])
    monkeypatch.setattr(LEDGER, 'prepare_scoped', prepare)
    monkeypatch.setattr(LEDGER, '_verify', lambda *args: observed['verify'].append(True))
    def publish(*args, **options):
        observed['publish'].append(options); return 'fixture-batch', None
    monkeypatch.setattr(LEDGER, 'commit_scoped', publish)
    frozen = SimpleNamespace(document_id='target', path='target.jpg', revision=2, blocked=None,
        before_json=json.dumps({'source_proof': kwargs['target_owner']['source_proof']}), people_json=json.dumps(payload))
    parameters = {BT.MARKER: {'source_asset': kwargs['source_owner']['source_proof']['asset_sha256'],
        'source_proof': kwargs['source_owner']['source_proof'], 'state_revision': source['revision'],
        'association_revision': source['association_revision'], 'source_owner': kwargs['source_owner']}}
    plan = SimpleNamespace(source_id='source', source_path='source.jpg', source_revision=2,
        targets=[frozen], policy='skip_and_report', params=lambda: parameters,
        modules=[C.OP], token='fixture-token', workspace='workspace')
    controller = SimpleNamespace(store=SimpleNamespace(claim=lambda plan: observed['claim'].append(True),
        finish=lambda plan, body: body), _source=lambda plan: {'fixture': 'source summary'},
        emit=lambda body: observed['events'].append(body), emit_result=lambda request, body: None)
    return engine, controller, plan, payload, states, rows, owner, analysis, observed


@pytest.mark.parametrize('refused', [False, True])
@pytest.mark.parametrize('derived', [False, True])
def test_preflight_renders_target_before_freezing_own_face_receipt(monkeypatch, refused, derived):
    """Full-render boundary double; real preflight, mapping and receipt helpers."""
    from lumaretouch_engine import people_batch_transfer as BT, full_candidate_render as FULL
    engine, controller, _, previous, states, _, owner, _, seen = commit_fixture(monkeypatch, derived=derived)
    batch = engine._batch_controller(); batch.documents.current_index = lambda: 0
    batch.target_indices = lambda docs: ([1], [])
    engine._people_bind = lambda: None
    original_render = FULL.render
    def render(*args, **kwargs):
        result = original_render(*args, **kwargs)
        if refused: raise ValueError('Target own body/face full-source renderer refused')
        return result
    monkeypatch.setattr(FULL, 'render', render)
    frozen = []
    def freeze(workspace, source_id, revision, path, modules, params, policy, targets, rejected):
        frozen.extend(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    controller.store.create = freeze
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-body-face-preflight',
        'docs': ['target'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': previous['source_ref'], 'selection': {C.OP: ['/amount']},
            'target_policy': 'explicit_face_map', 'source': previous['source_owner'],
            'targets': [{'target': previous['target_owner'], 'target_refs': previous['target_refs']}]}}
    before = deepcopy(states); BT.preflight(engine, controller, request)
    result = seen['events'][-1]
    assert (result['ok'], result['blocked']) == ((0, 1) if refused else (1, 0))
    assert seen['renders'] == ['target'] and states == before and not owner.commits
    if refused:
        assert result['targets'][0]['people_transfer'] is None and frozen[0].people_json is None
        assert seen['snapshots'] == []
    else:
        payload = result['targets'][0]['people_transfer']
        assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': .4}]
        assert payload['body_face_match_coverage'] == previous['body_face_match_coverage']
        assert json.loads(frozen[0].people_json)['body_face_match_coverage'] == payload['body_face_match_coverage']
        assert seen['snapshots'] == ['target']


def test_commit_renderer_refusal_precedes_receipt_acquisition_and_publication(monkeypatch):
    from lumaretouch_engine import people_batch_transfer as BT, full_candidate_render as FULL
    engine, controller, plan, _, states, rows, owner, _, seen = commit_fixture(monkeypatch)
    def refused(*args, **kwargs):
        seen['renders'].append('target'); raise ValueError('Actual target source/body/face support refused')
    monkeypatch.setattr(FULL, 'render', refused)
    before = deepcopy(states); before_rows = deepcopy(rows)
    with pytest.raises(ValueError, match='No confirmed target remains eligible'):
        BT.commit(engine, controller, {'cmd': 'batch', 'action': 'commit',
            'request_id': 'fixture-body-face', 'preflight_token': 'fixture-token'}, plan)
    assert seen['renders'] == ['target'] and not seen['snapshots'] and not seen['prepare']
    assert not seen['claim'] and not seen['publish'] and not owner.commits
    assert states == before and rows == before_rows


@pytest.mark.parametrize('fault', ['missing-receipt', 'forged-digest', 'face-only', 'neutral-fallback',
    'donor-ref', 'donor-source', 'reference-method', 'reference-extra', 'face-observation', 'body-unlinked'])
def test_commit_refuses_changed_body_or_own_face_receipt_before_any_plan(monkeypatch, fault):
    from lumaretouch_engine import people_batch_transfer as BT, body_pose_project as BP, shoulder_shape_project as PACK
    engine, controller, plan, payload, states, rows, owner, analysis, seen = commit_fixture(monkeypatch)
    receipt = payload['body_face_match_coverage']['targets'][0]
    if fault == 'missing-receipt': payload.pop('body_face_match_coverage')
    elif fault == 'forged-digest': receipt['body_review_sha256'] = '0'*64
    elif fault == 'face-only': receipt['scope'] = 'face-only'
    elif fault == 'neutral-fallback': receipt.update(scope='neutral-no-effect', body_review_sha256=None, own_face_reference=None)
    elif fault == 'donor-ref': receipt['own_face_reference']['face_ref'] = payload['source_ref']
    elif fault == 'donor-source': receipt['own_face_reference']['face_skin_observation']['source_sha256'] = 'a'*64
    elif fault == 'reference-method': receipt['own_face_reference']['reference_method'] = 'later-corrected-face'
    elif fault == 'reference-extra': receipt['own_face_reference']['reference_chroma'] = [.1, .2]
    elif fault == 'face-observation': analysis['face_skin_observation'] = None
    else:
        bank = BP.bank(rows[1]['state']); ref = next(iter(bank['bodies'].values()))['record']['body_ref']
        rows[1]['state'][BP.KEY] = PACK.pack(B.unlink(bank, ref))
    plan.targets[0].people_json = json.dumps(payload)
    before = deepcopy(states); before_rows = deepcopy(rows)
    with pytest.raises(ValueError, match='No confirmed target remains eligible'):
        BT.commit(engine, controller, {'cmd': 'batch', 'action': 'commit',
            'request_id': 'fixture-body-face', 'preflight_token': 'fixture-token'}, plan)
    assert seen['renders'] == ['target'] and seen['snapshots'] == ['target']
    assert not seen['prepare'] and not seen['claim'] and not seen['publish']
    assert states == before and rows == before_rows and not owner.commits


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('amount', [0., .4])
def test_commit_revalidates_exact_target_then_frozen_receipt_before_publish(monkeypatch, derived, amount):
    from lumaretouch_engine import people_batch_transfer as BT
    engine, controller, plan, _, states, rows, owner, _, seen = commit_fixture(monkeypatch, derived=derived, amount=amount)
    before = deepcopy(states); before_rows = deepcopy(rows)
    BT.commit(engine, controller, {'cmd': 'batch', 'action': 'commit',
        'request_id': 'fixture-body-face', 'preflight_token': 'fixture-token'}, plan)
    assert seen['renders'] == ['target', 'target'] and seen['prepare'] == [True]
    assert seen['snapshots'] == ([] if amount == 0. else ['target', 'target'])
    assert seen['claim'] == [True] and len(seen['publish']) == 1
    assert seen['events'][-1]['success'] is True and seen['events'][-1]['applied'] == [1]
    assert states == before and rows == before_rows and not owner.commits  # Publication boundary is doubled.


def test_final_preparation_cannot_silently_replace_own_face_observation(monkeypatch):
    from lumaretouch_engine import people_batch_transfer as BT, people_batch_ledger as LEDGER
    engine, controller, plan, _, states, rows, owner, analysis, seen = commit_fixture(monkeypatch)
    original_prepare = LEDGER.prepare_scoped
    def changed(actual, plans, targets):
        original_prepare(actual, plans, targets)
        analysis['face_skin_observation']['producer_width'] = 32
    monkeypatch.setattr(LEDGER, 'prepare_scoped', changed)
    before = deepcopy(states); before_rows = deepcopy(rows)
    with pytest.raises(ValueError):
        BT.commit(engine, controller, {'cmd': 'batch', 'action': 'commit',
            'request_id': 'fixture-body-face', 'preflight_token': 'fixture-token'}, plan)
    assert seen['renders'] == ['target', 'target'] and seen['snapshots'] == ['target', 'target']
    assert not seen['claim'] and not seen['publish'] and not owner.commits
    assert states == before and rows == before_rows


@pytest.mark.parametrize('fault', ['document', 'epoch', 'owner', 'target'])
def test_neutral_replay_keeps_exact_owner_and_face_fences(monkeypatch, fault):
    engine, owner, ref, _, _, _, _, calls = replay_fixture(monkeypatch)
    put(owner, ref, .3); state = C.capture(engine); C.install(state, recipe())
    engine._people_analyses.clear(); monkeypatch.setattr(N, 'available', lambda: False)
    if fault == 'document': engine._docs[0]['document_id'] = 'other-document'
    elif fault == 'epoch': engine._document_versions().workspace = 'other-workspace'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    else: engine._people_targets[ref['asset_sha256']]['face_ref'] = {**ref, 'analysis_revision': 1}
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls
