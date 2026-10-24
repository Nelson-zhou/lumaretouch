# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN body-only colour-evenness scope and transfer contracts.

LNX-REF-PC-32465-C-d5ac2d4606 is PARTIAL, not adjacent body-to-face
matching, AI correction, face-evenness migration or an old skin.broad alias.
Synthetic body/face/model observations below exercise real immutable review and
ownership helpers. Labelled native, outer-render and export-snapshot doubles are
NOT inference, compiled Rust, full-file export or photographic acceptance.
No product imports, execution, test collection, builds or typechecks were run.
"""
from copy import deepcopy
from types import SimpleNamespace
import json
import numpy as np
import pytest

from lumaretouch_engine import body_skin_evenness_scope as C, body_skin_evenness_state as S
from lumaretouch_engine import skin_evenness_scope as FACE_EVENNESS, skin_evenness_native as N
from lumaretouch_engine import skin_colour_body_support as BODY, skin_colour_transfer_review as REVIEW
from lumaretouch_engine import people_state as P, people_algorithms as A, body_pose_state as B
from lumaretouch_engine import people_scope as REPLAY, scope as SC
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_body_support_unrun import fixture as body_fixture
from test_skin_colour_scope_unrun import Owner, endpoint, isolate_other_captures

LEAVES = ('/amount',)
LEGACY = {'_strength': .65, '_params': {'radius': 8, 'eps': .02,
    'texture_radius': 3, 'broad_gain': .35, 'mid_gain': .7, 'detail_gain': 1.1}}


def recipe(amount=0.):
    return {'recipe': {'version': 1, 'amount': amount}}


def retained_fixture(*, family=C.FAMILY):
    """Real review-schema retention, synthetic observations, no raster double."""
    graph, assets, ref, bank, analysis, review = body_fixture()
    analysis.update(skin=np.ones((64, 64), np.float32), excluded=np.zeros((64, 64), np.float32))
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


def test_distinct_body_only_exact_control_and_scalar_registration():
    assert C.OP == 'lnx.body_skin_evenness.v1' and S.VERSION == 1
    assert S.CONTROL_ID == 'LNX-REF-PC-32465-C-d5ac2d4606'
    assert C.FAMILY == 'body_skin_evenness'
    assert BODY.family_spec(C.FAMILY, C.OP) == ('body_skin_evenness_visibility', C.OP)
    assert C.OP not in (FACE_EVENNESS.OP, SC.OP_SKIN)
    assert C.OP not in SC.DERIVED_PARAMETER_OPS and C.OP not in A.GEOMETRY
    assert SC.MODULES[C.OP]['read'] is C.params_of and SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True and SC.MODULES[C.OP]['transferable'] is True
    assert SC.MODULES[C.OP]['label'] == '身体肤色均匀（独立审核范围，部分非 AI 调整）'
    assert A.defaults()[C.OP] == {'/amount': 0.} and S.neutral() == recipe()['recipe']


@pytest.mark.parametrize('amount', [0., .01, .4, 1.])
def test_only_version_and_amount_round_trip(amount):
    params = recipe(amount)
    assert C.check_params(params) == SC.check_params(C.OP, params) == params
    portable = {'schema': SC.PRESET_SCHEMA, 'id': 'body-skin-evenness', 'name': 'Body region evenness',
        'kind': 'portrait', 'modules': {C.OP: params}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(portable)))
    assert loaded['modules'] == {C.OP: params}
    assert set(loaded['modules'][C.OP]['recipe']) == {'version', 'amount'}
    assert set(A.leaves(params['recipe'])) == set(LEAVES)


@pytest.mark.parametrize('amount', [True, False, None, '0.5', float('nan'), float('inf'),
    float('-inf'), -.01, 1.01, 10**1000, -(10**1000)])
def test_invalid_amount_refuses_without_mutation(monkeypatch, amount):
    engine, owner, *_ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state)
    with pytest.raises(ValueError): C.install(state, recipe(amount))
    with pytest.raises(SC.ScopeError): SC.check_params(C.OP, recipe(amount))
    assert state == before and not owner.commits


@pytest.mark.parametrize('raw', [None, {}, {'version': 1}, {'amount': .3},
    {'version': True, 'amount': .3}, {'version': 2, 'amount': .3},
    {'version': 1, 'strength': .3}, {'version': 1, 'broad_gain': .3}])
def test_recipe_never_migrates_face_evenness_or_old_broad(raw):
    with pytest.raises(ValueError): C.check_params({'recipe': raw})


@pytest.mark.parametrize('key', ['face_ref', 'body_ref', 'person_id', 'source', 'owner', 'body_skin',
    'body_skin_observation', 'review', 'recipe', 'manual', 'support_sha256', 'points_sha256',
    'mask', 'coverage', 'reference_chroma', 'chroma_shift', 'target_face_colour', 'temperature',
    'tint', 'broad_gain', 'face_evenness', 'body_to_face_matching', 'ai'])
def test_transport_rejects_donor_support_manual_recipes_and_other_controls(key):
    with pytest.raises(ValueError): C.check_params({**recipe(.3), key: {}})
    params = recipe(.3); params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


def test_actual_workflow_exports_no_support_and_never_migrates_other_amounts(monkeypatch):
    engine, owner, ref, bank, analysis, review, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', ref['face_instance_id'], FACE_EVENNESS.OP, '/amount', .6)
    before = owner.snapshot(); captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert C.params_of(captured) == recipe() and captured['_body_skin_evenness_supported'] is True
    put(owner, ref, .35); captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert SC.params_of(captured, [C.OP]) == {C.OP: recipe(.35)}
    assert captured[C.TARGET] == ref and captured[C.REQUESTED] is False
    assert captured[C.COVERAGE]['scope'] == 'reviewed-body-only'
    assert set(captured[C.COVERAGE]) == {'face_ref', 'scope', 'body_review_sha256'}
    assert C.owner_identity(captured)['document_id'] == 'target-document'
    assert values(owner, ref)[FACE_EVENNESS.OP]['amount'] == .6
    assert owner.value['faces'] == before['faces'] and owner.value['links'] == before['links']
    assert {key: captured[key] for key in LEGACY} == current == LEGACY
    assert engine._people_analyses[ref['asset_sha256']][ref['face_instance_id']] is analysis
    assert not {'review', 'manual', 'body_ref', 'reference_chroma', 'chroma_shift', 'body_skin'} & set(captured)
    assert not owner.commits


@pytest.mark.parametrize('family', [None, 'skin_colour', 'skin_finish'])
def test_other_family_or_absent_review_never_authorizes_active_body_evenness(monkeypatch, family):
    engine, owner, *_ = engine_fixture(monkeypatch, family=family)
    captured = C.capture(engine); assert captured['_body_skin_evenness_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3))
    C.install(captured, recipe()); assert C.params_of(captured) == recipe()
    assert not owner.commits


@pytest.mark.parametrize('fault', ['body-unlink', 'body-disabled', 'body-revision', 'people-revision',
    'review-asset', 'body-observation', 'body-model', 'body-detector', 'body-source', 'merged-only',
    'excluded', 'landmarks', 'wrong-ref', 'dimensions', 'mask-grid'])
def test_capture_rechecks_actual_target_body_person_masks_and_source(monkeypatch, fault):
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
    elif fault == 'merged-only': analysis['body_skin'] = analysis['body_skin_observation'] = None
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'landmarks': analysis['landmarks'][0, 0] = .8
    elif fault == 'wrong-ref': analysis['face_ref'] = {**ref, 'analysis_revision': 1}
    elif fault == 'dimensions': engine._people_source = lambda: {'sha256': ref['asset_sha256'], 'width': 80, 'height': 64}
    else: analysis['body_skin'] = np.ones((32, 32), np.float32)
    captured = C.capture(engine); before = owner.snapshot()
    assert captured['_body_skin_evenness_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3))
    C.install(captured, recipe()); assert owner.snapshot() == before and not owner.commits


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged', 'no-document'])
def test_even_neutral_demands_exact_enabled_face_and_owner(monkeypatch, fault):
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


def test_neutral_recovery_requires_no_live_body_bank_analysis_or_native(monkeypatch):
    engine, owner, ref, _, _, _, current, calls = replay_fixture(monkeypatch)
    put(owner, ref, .4)
    owner.value = P.set_override(owner.value, 'face', ref['face_instance_id'], FACE_EVENNESS.OP, '/amount', .2)
    before_faces = deepcopy(owner.value['faces']); before_support = deepcopy(engine._people_support)
    engine._people_analyses.clear(); engine._body_bank = lambda: pytest.fail('Neutral recovery must not demand live body bank')
    monkeypatch.setattr(N, 'available', lambda: False)
    captured = C.capture(engine); C.install(captured, recipe()); REPLAY.replay_preset(engine, captured)
    assert values(owner, ref)[C.OP] == S.neutral() and values(owner, ref)[FACE_EVENNESS.OP]['amount'] == .2
    assert owner.value['faces'] == before_faces and engine._people_support == before_support
    assert calls[-1][1]['strict_local'] is True and {key: calls[-1][0][key] for key in LEGACY} == current == LEGACY


@pytest.mark.parametrize('fault', ['native', 'consent', 'body', 'analysis', 'target', 'document',
    'epoch', 'owner', 'proof', 'source-kind', 'source-original', 'unmanaged'])
def test_replay_refreshes_live_target_fences_not_captured_support_booleans(monkeypatch, fault):
    engine, owner, ref, bank, analysis, review, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'consent': owner.value = BODY.detach(owner.value, ref, family=C.FAMILY)
    elif fault == 'body': engine._body_bank = lambda: B.unlink(bank, review['body_ref'])
    elif fault == 'analysis': analysis['body_skin_observation'] = None
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
def test_source_proof_mismatch_refuses_even_neutral(monkeypatch, amount):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, *_ = engine_fixture(monkeypatch)
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': '9'*64,
        'creative_source': None, 'original_sha256': '9'*64})
    captured = C.capture(engine)
    with pytest.raises(ValueError, match='有效来源'): C.install(captured, recipe(amount))
    assert not owner.commits


def test_install_changes_only_scalar_and_generic_derived_guard_stays_closed(monkeypatch):
    engine, owner, *_ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3)})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET] and after[C.OWNER] == before[C.OWNER]
    assert {key: after[key] for key in LEGACY} == LEGACY
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe())
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    assert not owner.commits


@pytest.mark.parametrize('derived_snapshot', ['current', 'previous'])
def test_generic_derived_restore_cannot_bypass_body_review(monkeypatch, derived_snapshot):
    from lumaretouch_engine import creative_derived_transfer as D
    current = {}; previous = {}; (current if derived_snapshot == 'current' else previous)['_creative_base'] = {}
    monkeypatch.setattr(D, 'involved', lambda state, **kwargs: True)
    with pytest.raises(SC.ScopeError, match='历史'): SC.restore_modules(current, previous, [C.OP])


@pytest.mark.parametrize('start,end', [(0., .4), (.4, .2), (.3, 0.)])
@pytest.mark.parametrize('refused', [False, True])
def test_strict_complete_renderer_routing_and_atomic_rollback(monkeypatch, start, end, refused):
    """Outer-render double asserts canonical graph routing, not numerical output."""
    engine, owner, ref, _, _, _, _, _ = replay_fixture(monkeypatch)
    put(owner, ref, start)
    owner.value = P.set_override(owner.value, 'face', ref['face_instance_id'], FACE_EVENNESS.OP, '/amount', .2)
    before = owner.snapshot(); before_support = deepcopy(engine._people_support); rendered = []
    def render(state, **kwargs):
        rendered.append(owner.snapshot())
        assert kwargs['strict_local'] is True and values(owner, ref)[C.OP] == recipe(end)['recipe']
        assert values(owner, ref)[FACE_EVENNESS.OP]['amount'] == .2
        assert {key: state[key] for key in LEGACY} == LEGACY
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert owner.value[key] == before[key]
        assert engine._people_support == before_support
        if refused: raise RuntimeError('target body support or composition refused')
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
    """Create separate synthetic source evidence BEFORE retaining any review.

    This is fixture construction, not relabelling a donor attachment: each call
    creates its own body observation/association, arrays and immutable support.
    """
    from lumaretouch_engine import body_pose_evidence as E
    graph, assets, original_ref, old_bank, analysis, review = body_fixture()
    face = graph['faces'].pop(original_ref['face_instance_id'])
    face.update(asset_sha256=asset, face_instance_id=face_id); graph['faces'][face_id] = face
    person = next(iter(graph['persons'])); graph['persons']['confirmed-person'] = graph['persons'].pop(person)
    for link in graph['links']:
        link.update(face_instance_id=face_id, person_id='confirmed-person')
    ref = P.face_ref(face); source = {'sha256': asset, 'width': 64, 'height': 64, 'orientation': E.ORIENTATION}
    old_record = B.target(old_bank, review['body_ref'])['record']
    record = E.create(source_frame=source, values=old_record['points'], backend_version='fixture-only',
        backend_code_sha256='d'*64, model_id='synthetic-unit-fixture', model_sha256='e'*64,
        input_rgb_sha256='f'*64, input_dimensions=(64, 64))
    bank = B.add_run(B.empty(), {'source': source, 'records': [record],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    bank = B.associate(bank, record['body_ref'], 'confirmed-person', graph, user_confirmed=True)
    analysis['face_ref'] = ref; analysis['body_skin_observation']['source_sha256'] = asset
    analysis.update(skin=np.ones((64, 64), np.float32), excluded=np.zeros((64, 64), np.float32))
    review.update(body_ref=record['body_ref'], points_sha256=record['points_sha256'])
    if family is not None:
        graph, assets = BODY.retain(graph, assets, ref, bank, analysis, review, family=family)
    return graph, assets, ref, bank, analysis, review


def prepared_transfer(*, policy='explicit_face_map', derived=False, family=C.FAMILY, amount=.4):
    from lumaretouch_engine import people_transfer_adapter as T
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, source_assets, source_ref, source_bank, source_analysis, _ = independent_fixture('a'*64, 'source-face')
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
    return (payload, candidate, source, target, source_assets, target_assets, target_ref,
            target_bank, target_analysis, kwargs)


@pytest.mark.parametrize('policy,derived', [('explicit_face_map', False),
    ('confirmed_person_only', False), ('explicit_face_map', True)])
def test_reviewed_transfer_moves_only_scalar_not_manual_consent_or_reference(policy, derived):
    payload, candidate, source, target, source_assets, target_assets, ref, bank, analysis, _ = prepared_transfer(policy=policy, derived=derived)
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': .4}]
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert candidate[key] == target[key]
    result = A.recipes(resolve(candidate, ref['face_instance_id'], A.defaults()))
    assert result[C.OP] == recipe(.4)['recipe'] and result[FACE_EVENNESS.OP]['amount'] == .2
    own, own_key = BODY.resolve(candidate, target_assets, ref, bank, analysis, family=C.FAMILY)
    assert own['face_ref'] == ref and own_key in target_assets and own_key not in source_assets
    disclosure = REVIEW.describe(candidate, target_assets, ref, bank, analysis, result[C.OP], family=C.FAMILY)
    assert disclosure == {'face_ref': ref, 'scope': 'reviewed-body-only', 'body_review_sha256': own_key}
    assert not {'recipe', 'manual', 'body_ref', 'body_skin', 'reference_chroma', 'chroma_shift'} & set(payload)
    if policy == 'confirmed_person_only':
        assert payload['confirmed_person_id'] == 'confirmed-person'
        assert payload['confirmation_revisions'] == [(ref['face_instance_id'], target['links'][0]['confirmation_revision'])]


@pytest.mark.parametrize('family', [None, 'skin_colour', 'skin_finish'])
def test_scalar_mapping_cannot_import_source_consent_to_unreviewed_target(family):
    payload, candidate, source, target, source_assets, target_assets, ref, bank, analysis, _ = prepared_transfer(family=family)
    assert candidate['faces'] == target['faces']
    # The adapter stages amount only; actual target admission must reject it.
    with pytest.raises(ValueError, match='own target-local'):
        REVIEW.describe(candidate, target_assets, ref, bank, analysis, recipe(.4)['recipe'], family=C.FAMILY)
    with pytest.raises(ValueError):
        REVIEW.describe(candidate, source_assets, ref, bank, analysis, recipe(.4)['recipe'], family=C.FAMILY)
    assert target_assets != source_assets and payload['parameters'][0]['value'] == .4


@pytest.mark.parametrize('fault', [None, 'missing', 'body-unlink', 'donor-assets', 'donor-analysis', 'snapshot-owner', 'snapshot-source'])
@pytest.mark.parametrize('derived', [False, True])
def test_frozen_target_disclosure_uses_exact_target_snapshot_and_real_review_helpers(monkeypatch, fault, derived):
    """Snapshot/context boundary doubles, real body bank and review resolution.

    This helper is only called after full target validation. No rasterization,
    reference solve, complete rendering or photographic acceptance is claimed.
    """
    from lumaretouch_engine import full_candidate_render as FULL, body_pose_project as BP, shoulder_shape_project as PACK
    payload, candidate, source, target, source_assets, assets, ref, bank, analysis, _ = prepared_transfer(derived=derived)
    row = {'document_id': 'target', 'path': 'target.jpg', 'state': {BP.KEY: PACK.pack(bank)}}
    if derived: row['state']['_creative_base'] = {'fixture': 'own immutable source, not a real file'}
    if fault == 'missing': candidate = BODY.detach(candidate, ref, family=C.FAMILY)
    elif fault == 'body-unlink': row['state'][BP.KEY] = PACK.pack(B.unlink(bank, next(iter(bank['bodies'].values()))['record']['body_ref']))
    elif fault == 'donor-assets': assets = source_assets
    elif fault == 'donor-analysis': analysis = independent_fixture('a'*64, 'source-face')[4]
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
        frozen = json.loads(json.dumps({**payload, 'body_skin_evenness_coverage': coverage}))
        assert frozen['body_skin_evenness_coverage']['targets'][0]['body_review_sha256'] in assets
        assert frozen['parameters'] == payload['parameters']
    assert candidate == before and payload == before_payload and assets == before_assets
    assert len(snapshot_calls) == (0 if fault == 'missing' else 1)


@pytest.mark.parametrize('family', [None, C.FAMILY, 'skin_colour', 'skin_finish'])
def test_zero_transfer_disclosure_needs_no_target_body_bank_or_analysis(family):
    payload, candidate, _, _, _, _, ref, _, _, _ = prepared_transfer(family=family, amount=0.)
    engine = SimpleNamespace(_people_export_snapshot=lambda *args, **kwargs:
        pytest.fail('Neutral disclosure must not acquire target body/evidence'))
    assert REVIEW.for_target(engine, {'state': {}}, candidate, payload, family=C.FAMILY) == {
        'version': 1, 'support_transfer': 'none', 'targets': [
            {'face_ref': ref, 'scope': 'neutral-no-effect', 'body_review_sha256': None}]}


def test_unrelated_transfer_has_no_body_evenness_disclosure():
    payload = {'parameters': [{'operation_id': FACE_EVENNESS.OP, 'parameter_path': '/amount', 'value': .4}]}
    assert REVIEW.for_target(None, None, None, payload, family=C.FAMILY) is None


@pytest.mark.parametrize('fault', ['missing-receipt', 'forged-digest', 'face-only', 'neutral-fallback', 'live-body-unlinked'])
def test_batch_commit_rechecks_frozen_body_coverage_before_staging_any_plan(monkeypatch, fault):
    """Actual commit/adapter/receipt resolution with labelled external boundaries.

    Full-file pixels, persisted plan loading and document storage are doubles.
    BODY.resolve, body bank unpacking, reviewed identities and consent validation
    remain real. No native rendering or ledger publication is claimed.
    """
    from lumaretouch_engine import people_batch_transfer as BT, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL, body_pose_project as BP, shoulder_shape_project as PACK
    payload, staged, source, target, _, assets, ref, bank, analysis, kwargs = prepared_transfer()
    coverage = {'version': 1, 'support_transfer': 'none', 'targets': [
        REVIEW.describe(staged, assets, ref, bank, analysis, recipe(.4)['recipe'], family=C.FAMILY)]}
    payload['body_skin_evenness_coverage'] = deepcopy(coverage)
    if fault == 'missing-receipt': payload.pop('body_skin_evenness_coverage')
    elif fault == 'forged-digest': payload['body_skin_evenness_coverage']['targets'][0]['body_review_sha256'] = '0'*64
    elif fault == 'face-only': payload['body_skin_evenness_coverage']['targets'][0]['scope'] = 'face-only'
    elif fault == 'neutral-fallback':
        payload['body_skin_evenness_coverage']['targets'][0].update(scope='neutral-no-effect', body_review_sha256=None)
    else: bank = B.unlink(bank, next(iter(bank['bodies'].values()))['record']['body_ref'])
    states = {'source': source, 'target': target}
    rows = [{'document_id': identity, 'path': identity+'.jpg', 'copy_number': 1,
        'state': {BP.KEY: PACK.pack(bank)} if identity == 'target' else {}} for identity in states]
    versions = SimpleNamespace(workspace='workspace',
        version=lambda row: SimpleNamespace(document_id=row['document_id'], revision=2),
        find=lambda actual_rows, identity: next(((i, row) for i, row in enumerate(actual_rows)
            if row['document_id'] == identity), None))
    batch = SimpleNamespace(versions=versions,
        documents=SimpleNamespace(rows=lambda: rows, remember_current=lambda: None))
    snapshots = []; renders = []; owner = Owner(source)
    def snapshot(state, path, graph, *, context, document_id):
        assert state is rows[1]['state'] and path == 'target.jpg' and document_id == 'target'
        snapshots.append(document_id)
        return {'state': graph, 'document_id': document_id, 'asset_sha256': ref['asset_sha256'],
                'support_assets': assets, 'analyses': {ref['face_instance_id']: analysis}}
    engine = SimpleNamespace(_docs=rows, _batch_controller=lambda: batch, _people_owner=lambda: owner,
        _document_versions=lambda: versions, _people_export_snapshot=snapshot)
    monkeypatch.setattr(BT.V, 'row_snapshot', lambda actual, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I, 'proof', lambda actual, row, graph: endpoint(graph, row['document_id']))
    monkeypatch.setattr(BT.SOURCE, 'row_proof', lambda row: endpoint(states[row['document_id']], row['document_id'])['source_proof'])
    def verify_source(row, expected):
        assert expected == BT.SOURCE.row_proof(row); return expected
    monkeypatch.setattr(BT.SOURCE, 'verify_row', verify_source)
    monkeypatch.setattr(FULL, 'people_context', lambda actual, row: {'fixture': 'target context'})
    def render(actual, row, state, document_id, revision, *, people_graph):
        assert actual is engine and row is rows[1] and state is rows[1]['state']
        assert (document_id, revision) == ('target', '2') and people_graph == staged
        renders.append(document_id); return None, {'fixture': 'full-file renderer boundary only'}
    monkeypatch.setattr(FULL, 'render', render)
    frozen = SimpleNamespace(document_id='target', path='target.jpg', revision=2, blocked=None,
        before_json=json.dumps({'source_proof': kwargs['target_owner']['source_proof']}), people_json=json.dumps(payload))
    parameters = {BT.MARKER: {'source_asset': kwargs['source_owner']['source_proof']['asset_sha256'],
        'source_proof': kwargs['source_owner']['source_proof'], 'state_revision': source['revision'],
        'association_revision': source['association_revision'], 'source_owner': kwargs['source_owner']}}
    plan = SimpleNamespace(source_id='source', source_path='source.jpg', source_revision=2,
        targets=[frozen], policy='skip_and_report', params=lambda: parameters)
    before = deepcopy(states); before_rows = deepcopy(rows)
    with pytest.raises(ValueError, match='No confirmed target remains eligible'):
        BT.commit(engine, SimpleNamespace(), {'cmd': 'batch', 'action': 'commit',
            'request_id': 'fixture-body-evenness', 'preflight_token': 'fixture-token'}, plan)
    assert renders == ['target'] and snapshots == ['target']
    assert states == before and rows == before_rows and not owner.commits


@pytest.mark.parametrize('fault', ['document', 'epoch', 'owner', 'target'])
def test_neutral_replay_still_fences_exact_owner_and_face(monkeypatch, fault):
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
