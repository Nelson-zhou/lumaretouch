# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: independent body-colour-evenness review and consent.

LNX-REF-PC-32465-C-d5ac2d4606 is body-region colour unevenness only.
This is not adjacent body-to-face matching d8b09012a9, learned correction,
native execution, an executed test, or photographic/runtime acceptance.
Synthetic source/person/model observations and mocked full-render pixels only
exercise the authored contract; manual raster doubles do not prove Rust quality.
"""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import people_state as P, body_pose_state as B
from lumaretouch_engine import skin_colour_body_support as S
from lumaretouch_engine import skin_colour_body_actions as A
from lumaretouch_engine import skin_colour_body_host as H
from test_skin_colour_body_support_unrun import fixture as source_fixture

FAMILY = 'body_skin_evenness'
EVENNESS = {'family': FAMILY, 'operation_id': 'lnx.body_skin_evenness.v1'}
FAMILIES = ('skin_colour', 'skin_finish', FAMILY)


def fixture():
    state, assets, ref, bank, analysis, review = source_fixture()
    analysis['excluded'] = np.zeros((64, 64), np.float32)
    return state, assets, ref, bank, analysis, review


def retained(*, families=(FAMILY,)):
    state, assets, ref, bank, analysis, review = fixture()
    for family in families:
        state, assets = S.retain(state, assets, ref, bank, analysis, review, family=family)
    return state, assets, ref, bank, analysis, review


def raster(state, assets, ref, bank, analysis, *, family=FAMILY):
    with patch.object(S.M, 'raster', return_value=np.full((64, 64), 255, np.uint8)):
        return S.raster(state, assets, ref, bank, analysis, (64, 64),
                        byte_budget=128*1024*1024, family=family)


def target_for(ref):
    return {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}


def preview_payload(review, family=FAMILY):
    return {'review': review, **({'amount': .4} if family == FAMILY else {})}


def test_exact_third_family_preserves_old_public_defaults():
    assert S.FAMILIES[:3] == FAMILIES
    assert S.FAMILIES == (*FAMILIES, 'body_face_match', 'collarbone')
    assert S.family_spec() == ('skin_colour_body_visibility', 'lnx.skin_colour.v1')
    assert S.family_spec('skin_finish') == ('skin_finish_body_visibility', 'lnx.skin_finish.v1')
    assert S.family_spec(**EVENNESS) == ('body_skin_evenness_visibility', 'lnx.body_skin_evenness.v1')
    assert S.EVENNESS_KIND == 'body_skin_evenness_visibility'
    assert S.EVENNESS_OPERATION == EVENNESS['operation_id']
    for family in (None, '', 'skin_evenness', 'body_evenness', S.EVENNESS_KIND,
                   S.EVENNESS_OPERATION, 'body_to_face_matching', [], True):
        with pytest.raises(ValueError):
            S.family_spec(family)
    for family, other in product(FAMILIES, repeat=2):
        if family != other:
            with pytest.raises(ValueError):
                S.family_spec(family, S.family_spec(other)[1])


@pytest.mark.parametrize('family,verb', product(FAMILIES, ('reference', 'preview', 'confirm', 'detach')))
def test_each_operation_admits_only_its_exact_action_and_payload(family, verb):
    _, _, ref, _, _, review = fixture(); target = target_for(ref)
    payload = (preview_payload(review, family) if verb == 'preview' else
               {'preview_id': 'exact-review', 'reviewed': True} if verb == 'confirm' else {})
    action = A.action_name(verb, family=family)
    assert action in A.ACTIONS
    A.check_action(action, payload, target, family=family)
    for other in FAMILIES:
        if other != family:
            with pytest.raises(ValueError):
                A.check_action(action, payload, target, family=other)
    assert A.action_name(verb, **EVENNESS) == 'body_skin_evenness_' + verb


@pytest.mark.parametrize('amount', [0, -.1, 1.01, True, False, None, '.3', [], {},
                                    float('nan'), float('inf'), -float('inf'), 10**400])
def test_evenness_preview_requires_explicit_finite_positive_bounded_amount(amount):
    _, _, ref, _, _, review = fixture()
    with pytest.raises(ValueError):
        A.check_action('body_skin_evenness_preview', {'review': review, 'amount': amount},
                       target_for(ref), **EVENNESS)


def test_evenness_candidate_amount_is_not_accepted_as_colour_or_finish_consent():
    _, _, ref, _, _, review = fixture(); target = target_for(ref)
    with pytest.raises(ValueError):
        A.check_action('body_skin_evenness_preview', {'review': review}, target, **EVENNESS)
    for family in FAMILIES[:2]:
        with pytest.raises(ValueError):
            A.check_action(A.action_name('preview', family=family), preview_payload(review),
                           target, family=family)
    with pytest.raises(ValueError):
        A.check_action('body_skin_evenness_confirm',
                       {'preview_id': 'preview', 'reviewed': True, 'amount': .5}, target, **EVENNESS)


@pytest.mark.parametrize('scope', ['all_people', 'person', 'group'])
def test_body_evenness_review_is_exact_face_owned_not_shared(scope):
    _, _, ref, _, _, _ = fixture()
    with pytest.raises(ValueError):
        A.check_action('body_skin_evenness_reference', {}, {**target_for(ref), 'scope': scope}, **EVENNESS)


@pytest.mark.parametrize('flag', S.FLAGS)
def test_existing_reviews_never_supply_new_visibility_or_ownership_acknowledgment(flag):
    state, assets, ref, bank, analysis, review = retained(families=FAMILIES[:2])
    review[flag] = False; original = deepcopy(assets)
    with pytest.raises(ValueError):
        S.retain(state, assets, ref, bank, analysis, review, **EVENNESS)
    with pytest.raises(ValueError):
        A.check_action('body_skin_evenness_preview', preview_payload(review), target_for(ref), **EVENNESS)
    assert assets == original and len(assets) == 2


def test_colour_and_finish_support_never_enable_evenness_or_copy_a_mask():
    state, assets, ref, _, _, _ = retained(families=FAMILIES[:2]); original = deepcopy(assets)
    assert S.resolve(state, assets, ref, None, None, **EVENNESS) is None
    assert S.raster(state, assets, ref, None, None, (64, 64), **EVENNESS) == (None, {'enabled': False})
    assert S.EVENNESS_KIND not in state['faces'][ref['face_instance_id']]['local_assets']
    assert assets == original


def test_three_deliberate_reviews_have_distinct_hashes_and_independent_detach():
    state, assets, ref, bank, analysis, _ = retained(families=FAMILIES)
    resolved = {family: S.resolve(state, assets, ref, bank, analysis, family=family) for family in FAMILIES}
    assert len({key for _, key in resolved.values()}) == len(assets) == 3
    original = deepcopy(assets)
    for family, (record, _) in resolved.items():
        assert record['row']['operation_id'] == S.family_spec(family)[1]
        for other in FAMILIES:
            if other != family:
                with pytest.raises(ValueError): S.check_record(record, family=other)
        detached = S.detach(state, ref, family=family)
        assert S.resolve(detached, assets, ref, None, None, family=family) is None
        for other in FAMILIES:
            if other != family:
                assert S.resolve(detached, assets, ref, bank, analysis, family=other) == resolved[other]
    assert assets == original


@pytest.mark.parametrize('mutation', ['body-unlink', 'body-disabled', 'body-points', 'body-model',
    'people-revision', 'body-revision', 'face-link', 'observation-model', 'observation-grid',
    'source', 'body-skin-missing', 'landmarks', 'wrong-face'])
def test_evenness_uses_current_exact_body_person_source_and_real_semantic_proof(mutation):
    state, assets, ref, bank, analysis, review = retained()
    if mutation == 'body-unlink': bank = B.unlink(bank, review['body_ref'])
    elif mutation == 'body-disabled': B.target(bank, review['body_ref'])['enabled'] = False
    elif mutation == 'body-points': B.target(bank, review['body_ref'])['record']['points_sha256'] = '9'*64
    elif mutation == 'body-model': B.target(bank, review['body_ref'])['record']['model_sha256'] = '9'*64
    elif mutation == 'people-revision': state['association_revision'] += 1
    elif mutation == 'body-revision': bank['association_revision'] += 1
    elif mutation == 'face-link': state['links'][0]['confirmation_revision'] = 0
    elif mutation == 'observation-model': analysis['body_skin_observation']['semantic_model_sha256'] = '9'*64
    elif mutation == 'observation-grid': analysis['body_skin_observation']['producer_width'] = 32
    elif mutation == 'body-skin-missing': analysis['skin'] = analysis.pop('body_skin')
    elif mutation == 'landmarks': analysis['landmarks'][0, 0] = .8
    elif mutation == 'wrong-face': analysis['face_ref'] = {**ref, 'analysis_revision': 1}
    else: B.target(bank, review['body_ref'])['record']['source']['width'] = 80
    with pytest.raises(ValueError): S.resolve(state, assets, ref, bank, analysis, **EVENNESS)


def test_all_three_same_owner_coverages_compose_without_borrowing_consent():
    state, assets, ref, bank, analysis, _ = retained(families=FAMILIES)
    coverages = [raster(state, assets, ref, bank, analysis, family=family) for family in FAMILIES]
    assert all(np.array_equal(coverages[0][0], coverage) for coverage, _ in coverages)
    assert all(not coverage.flags.writeable and facts['competing_review_count'] == 0
               for coverage, facts in coverages)


def test_evenness_support_intersects_real_semantics_and_known_occluders_and_protects_faces():
    state, assets, ref, bank, analysis, _ = retained(families=FAMILIES)
    analysis['body_skin'][40, 30] = .4
    analysis['excluded'][42, 30] = .1
    analysis['excluded'][43, 30] = .1001
    analysis['body_skin'][:, :4] = 0
    coverage, facts = raster(state, assets, ref, bank, analysis)
    assert coverage[40, 30] == np.float32(.4) and coverage[42, 30] > 0
    assert coverage[43, 30] == 0 and not np.any(coverage[:, :4])
    assert not np.any(coverage[5:21, 5:21]) and not coverage.flags.writeable
    assert facts['protected_face_boxes'] == 1 and facts['runtime_quality_accepted'] is False
    # The new protection must not silently change old colour/finish coverage.
    for family in FAMILIES[:2]:
        old, _ = raster(state, assets, ref, bank, analysis, family=family)
        assert old[43, 30] > 0


@pytest.mark.parametrize('fault', ['missing', 'none', 'wrong-shape', 'wrong-dtype', 'list', 'nan', 'negative', 'high'])
def test_evenness_missing_or_invalid_known_occluder_support_refuses_before_raster(fault):
    state, assets, ref, bank, analysis, _ = retained()
    if fault == 'missing': analysis.pop('excluded')
    elif fault == 'none': analysis['excluded'] = None
    elif fault == 'wrong-shape': analysis['excluded'] = np.zeros((32, 32), np.float32)
    elif fault == 'wrong-dtype': analysis['excluded'] = np.zeros((64, 64), np.float64)
    elif fault == 'list': analysis['excluded'] = analysis['excluded'].tolist()
    else: analysis['excluded'][40, 30] = {'nan': np.nan, 'negative': -.1, 'high': 1.1}[fault]
    with patch.object(S.M, 'raster') as native:
        with pytest.raises(ValueError, match='occluder'):
            S.raster(state, assets, ref, bank, analysis, (64, 64), byte_budget=128*1024*1024, **EVENNESS)
        native.assert_not_called()


def test_evenness_fully_occluded_region_is_not_reported_as_success():
    state, assets, ref, bank, analysis, _ = retained(); analysis['excluded'][:] = 1
    with pytest.raises(ValueError, match='no admitted'):
        raster(state, assets, ref, bank, analysis)


@pytest.mark.parametrize('active_family,other_family', product(FAMILIES, repeat=2))
def test_other_owner_regions_reserve_coverage_across_every_family_even_if_disabled(active_family, other_family):
    state, assets, ref, bank, analysis, _ = retained(families=FAMILIES)
    record, _ = S.resolve(state, assets, ref, bank, analysis, family=other_family)
    other = P.new_face(ref['asset_sha256'], [.7, .05, .9, .2], analysis['evidence'])
    other['enabled'] = False; other_ref = P.face_ref(other); copied = deepcopy(record)
    # Historical competitor reserves ownership without fabricating a new live
    # same-person association or pretending this disabled face was reanalysed.
    copied['face_ref'] = other_ref
    copied['row']['face_link']['face_instance_id'] = other_ref['face_instance_id']
    key = S.content_digest(S.check_record(copied, family=other_family)); assets[key] = copied
    kind, _ = S.family_spec(other_family)
    other['local_assets'][kind] = {'owner': other_ref, 'kind': kind, 'content_sha256': key}
    state['faces'][other_ref['face_instance_id']] = other
    with pytest.raises(ValueError, match='overlap'):
        raster(state, assets, ref, bank, analysis, family=active_family)


def test_historical_evenness_cannot_borrow_another_family_or_another_private_bank():
    state, assets, ref, _, _, _ = retained(families=FAMILIES)
    project = {'people_graph': state, 'people_support_assets': assets}
    for family in FAMILIES: S.validate_project(project, family=family)
    for other in FAMILIES[:2]:
        bad = deepcopy(project); face = bad['people_graph']['faces'][ref['face_instance_id']]
        face['local_assets'][S.EVENNESS_KIND]['content_sha256'] = face['local_assets'][S.family_spec(other)[0]]['content_sha256']
        with pytest.raises(ValueError): S.validate_project(bad, **EVENNESS)
    private = {'people_support_assets': assets, 'people_context': {
        'people_graph': state, 'people_support_assets': {}}}
    with pytest.raises(ValueError): S.validate_project(private, **EVENNESS)


def host_fixture(monkeypatch):
    from lumaretouch_engine import full_candidate_render as F, virtual_copy_people as V
    from lumaretouch_engine import body_pose_commands, creative_derived_source, cpu_memory_budget
    state, assets, ref, bank, analysis, review = retained(families=FAMILIES[:2])
    state = P.set_override(state, 'face', ref['face_instance_id'], S.OPERATION, '/temperature', .2)
    state = P.set_override(state, 'face', ref['face_instance_id'], S.FINISH_OPERATION, '/whitening', .3)
    source = {'sha256': ref['asset_sha256'], 'width': 64, 'height': 64}
    target = target_for(ref); row = {'path': 'synthetic-source.png'}; snapshot = {'unchanged': True}
    version = SimpleNamespace(document_id='document', revision=7)
    context = {'people_graph': deepcopy(state), 'people_support_assets': deepcopy(assets)}
    engine = SimpleNamespace(_people_support=deepcopy(assets), _people_targets={source['sha256']: target},
        _people_analyses={source['sha256']: {ref['face_instance_id']: analysis}},
        _people_source=lambda: source, _body_bank=lambda: bank, _people_binding=lambda: {'binding': 1},
        _capture_state=lambda: snapshot, _document_versions=lambda: SimpleNamespace(version=lambda _: version))
    monkeypatch.setattr(V, 'current_row', lambda _: row)
    monkeypatch.setattr(F, 'identity', lambda e, r, s, document, revision:
        ({'synthetic': True, 'document': document, 'revision': revision}, state, deepcopy(context)))
    monkeypatch.setattr(body_pose_commands, 'source_preview', lambda _: {'base64': 'synthetic-reference'})
    monkeypatch.setattr(creative_derived_source, 'analysis_rgb', lambda _: np.full((64, 64, 3), 128, np.uint8))
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 512*1024*1024)
    monkeypatch.setattr(S.M, 'raster', lambda *a: np.full((64, 64), 255, np.uint8))
    calls = []
    def render(owner, current_row, captured, document, revision, **kwargs):
        assert owner._people_support == assets and current_row is row and captured is snapshot
        assert document == version.document_id and revision == str(version.revision)
        calls.append(deepcopy(kwargs)); staged = kwargs.get('staged_people_context')
        if staged is not None:
            assert staged['people_graph'] == kwargs['people_graph']
            assert all(staged['people_support_assets'][key] == value for key, value in assets.items())
        return np.full((64, 64, 3), .3 if staged else .2, np.float32), {'synthetic': 'render-proof'}
    monkeypatch.setattr(F, 'render', render)
    return engine, state, target, preview_payload(review), bank, analysis, version, calls


def effective_amount(state, face_id):
    from lumaretouch_engine.people_algorithms import defaults, recipes
    from lumaretouch_engine.people_resolver import resolve
    return recipes(resolve(state, face_id, defaults()))[S.EVENNESS_OPERATION]['amount']


def test_three_family_capture_identities_and_private_slots_are_distinct(monkeypatch):
    engine, state, target, _, _, _, _, _ = host_fixture(monkeypatch)
    assert len({H._capture(engine, state, target, family=family)[0] for family in FAMILIES}) == 3
    assert len({H._family(family, None)[3] for family in FAMILIES}) == 3
    assert len({H._family(family, None)[4] for family in FAMILIES}) == 3
    assert H._family(FAMILY, None)[3:] == ('_body_skin_evenness_reference', '_body_skin_evenness_preview')


@pytest.mark.parametrize('other_family', FAMILIES[:2])
def test_colour_or_finish_reference_cannot_enable_evenness_preview(monkeypatch, other_family):
    engine, state, target, payload, _, _, _, calls = host_fixture(monkeypatch)
    H.reference(engine, state, target, {}, family=other_family); before = deepcopy(engine._people_support)
    with pytest.raises(ValueError, match='reference'):
        H.preview(engine, state, target, payload, **EVENNESS)
    assert engine._people_support == before and calls == []
    old_key = H._family(other_family, None)[3]
    copied = deepcopy(getattr(engine, old_key))
    copied['fence'] = H._capture(engine, state, target, **EVENNESS)[0]
    engine._body_skin_evenness_reference = copied
    with pytest.raises(ValueError, match='reference'):
        H.preview(engine, state, target, payload, **EVENNESS)
    assert engine._people_support == before and calls == []


def test_first_use_previews_neutral_before_and_explicit_face_amount_after_without_mutation(monkeypatch):
    engine, state, target, payload, _, _, _, calls = host_fixture(monkeypatch)
    assert effective_amount(state, target['target_id']) == 0.
    engine._skin_body_preview = {'old-colour': True}; engine._skin_finish_body_preview = {'old-finish': True}
    reference = H.reference(engine, state, target, {}, **EVENNESS)
    assert reference['attached'] is False and all(reference[key] == value for key, value in EVENNESS.items())
    before = deepcopy(engine._people_support); graph = deepcopy(state)
    shown = H.preview(engine, state, target, payload, **EVENNESS)
    assert all(shown[key] == value for key, value in EVENNESS.items()) and shown['amount'] == payload['amount']
    assert engine._people_support == before and state == graph and len(calls) == 2
    assert effective_amount(calls[0]['people_graph'], target['target_id']) == 0.
    candidate = calls[1]['people_graph']
    assert effective_amount(candidate, target['target_id']) == payload['amount']
    new_amounts = [entry for entry in candidate['overrides'] if entry['operation_id'] == S.EVENNESS_OPERATION]
    assert new_amounts == [{'scope': 'face', 'target_id': target['target_id'],
        'operation_id': S.EVENNESS_OPERATION, 'parameter_path': '/amount', 'value': payload['amount']}]
    assert [entry for entry in candidate['overrides'] if entry['operation_id'] != S.EVENNESS_OPERATION] == state['overrides']
    assert S.EVENNESS_KIND in candidate['faces'][target['target_id']]['local_assets']
    assert shown['before']['base64'] != shown['after']['base64']
    assert shown['overlay']['mapping'] == 'normalized_full_frame'
    assert shown['runtime_quality_accepted'] is False
    assert engine._skin_body_preview == {'old-colour': True} and engine._skin_finish_body_preview == {'old-finish': True}
    marks = []
    committed, reply = H.confirm(engine, state, target,
        {'preview_id': shown['preview_id'], 'reviewed': True}, **EVENNESS,
        mark_started=lambda: marks.append(deepcopy(engine._people_support)))
    assert committed == candidate and marks == [before]
    assert reply == {'kind': 'confirmed', 'attached': True, **EVENNESS}
    assert state == graph and effective_amount(committed, target['target_id']) == payload['amount']
    assert len(engine._people_support) == len(before) + 1
    assert all(engine._people_support[key] == value for key, value in before.items())
    assert engine._body_skin_evenness_reference is None and engine._body_skin_evenness_preview is None


@pytest.mark.parametrize('copied_from,copied_to', [(a, b) for a, b in product(FAMILIES, repeat=2) if a != b])
def test_copied_preview_receipt_even_with_rewritten_fence_never_changes_family(monkeypatch, copied_from, copied_to):
    engine, state, target, payload, _, _, _, _ = host_fixture(monkeypatch)
    H.reference(engine, state, target, {}, family=copied_from)
    shown = H.preview(engine, state, target, preview_payload(payload['review'], copied_from), family=copied_from)
    copied = deepcopy(getattr(engine, H._family(copied_from, None)[4]))
    copied['fence'] = H._capture(engine, state, target, family=copied_to)[0]
    setattr(engine, H._family(copied_to, None)[4], copied); before = deepcopy(engine._people_support)
    marks = []
    with pytest.raises(ValueError):
        H.confirm(engine, state, target, {'preview_id': shown['preview_id'], 'reviewed': True},
                  family=copied_to, mark_started=lambda: marks.append(True))
    assert marks == [] and engine._people_support == before


@pytest.mark.parametrize('change', ['body', 'semantic', 'association', 'scalar', 'document', 'amount'])
def test_confirmation_rejects_changed_evidence_or_private_amount_without_append(monkeypatch, change):
    engine, state, target, payload, bank, analysis, version, _ = host_fixture(monkeypatch)
    H.reference(engine, state, target, {}, **EVENNESS)
    shown = H.preview(engine, state, target, payload, **EVENNESS); before = deepcopy(engine._people_support)
    if change == 'body': bank['revision'] += 1
    elif change == 'semantic': analysis['body_skin_observation']['semantic_model_sha256'] = '9'*64
    elif change == 'association': state['association_revision'] += 1
    elif change == 'scalar': state.update(P.set_override(state, 'face', target['target_id'], S.OPERATION, '/temperature', .4))
    elif change == 'document': version.revision += 1
    else: engine._body_skin_evenness_preview['amount'] = .6
    marks = []
    with pytest.raises(ValueError):
        H.confirm(engine, state, target, {'preview_id': shown['preview_id'], 'reviewed': True},
                  **EVENNESS, mark_started=lambda: marks.append(True))
    assert marks == [] and engine._people_support == before


@pytest.mark.parametrize('scope', ['face', 'all_people', 'person'])
def test_active_detach_refuses_without_clearing_pending_review_or_scalar(monkeypatch, scope):
    engine, state, target, payload, bank, analysis, _, _ = host_fixture(monkeypatch)
    state, assets = S.retain(state, engine._people_support, target['face_ref'], bank, analysis, payload['review'], **EVENNESS)
    target_id = (target['target_id'] if scope == 'face' else target['face_ref']['asset_sha256']
                 if scope == 'all_people' else state['links'][0]['person_id'])
    state = P.set_override(state, scope, target_id, S.EVENNESS_OPERATION, '/amount', .4)
    engine._people_support = assets; engine._body_skin_evenness_preview = {'pending': True}
    before = deepcopy(state)
    with pytest.raises(ValueError, match='zero'):
        H.detach(engine, state, target, {}, **EVENNESS)
    assert state == before and engine._people_support == assets
    assert engine._body_skin_evenness_preview == {'pending': True}


def test_neutral_detach_removes_only_evenness_even_with_stale_body_evidence(monkeypatch):
    engine, state, target, payload, bank, analysis, _, _ = host_fixture(monkeypatch)
    state, assets = S.retain(state, engine._people_support, target['face_ref'], bank, analysis, payload['review'], **EVENNESS)
    engine._people_support = assets
    engine._skin_body_preview = {'colour': True}; engine._skin_finish_body_preview = {'finish': True}
    engine._body_skin_evenness_preview = {'evenness': True}
    def unavailable(): raise AssertionError('Neutral detach must not consult stale body evidence')
    engine._body_bank = unavailable
    candidate, reply = H.detach(engine, state, target, {}, **EVENNESS)
    assert reply == {'kind': 'detached', 'attached': False, **EVENNESS}
    assert S.EVENNESS_KIND not in candidate['faces'][target['target_id']]['local_assets']
    assert all(S.family_spec(f)[0] in candidate['faces'][target['target_id']]['local_assets'] for f in FAMILIES[:2])
    assert engine._body_skin_evenness_preview is None and engine._people_support == assets
    assert engine._skin_body_preview == {'colour': True} and engine._skin_finish_body_preview == {'finish': True}


def test_report_is_family_tagged_and_does_not_invent_missing_evenness_support(monkeypatch):
    engine, state, target, payload, bank, analysis, _, _ = host_fixture(monkeypatch)
    source = engine._people_source()
    absent = H.report(engine, state, source, target['target_id'], **EVENNESS)
    assert absent['attached'] is False and absent['needs_review'] is False
    assert all(absent[key] == value for key, value in EVENNESS.items())
    state, assets = S.retain(state, engine._people_support, target['face_ref'], bank, analysis, payload['review'], **EVENNESS)
    engine._people_support = assets
    current = H.report(engine, state, source, target['target_id'], **EVENNESS)
    assert current['attached'] is True and current['needs_review'] is False
    bank['association_revision'] += 1
    stale = H.report(engine, state, source, target['target_id'], **EVENNESS)
    assert stale['attached'] is True and stale['needs_review'] is True and stale['reason']
