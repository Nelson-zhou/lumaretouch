# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: independent skin-finish body authorization contracts.

Synthetic observations, mocked full-render pixels and stubbed manual rasters
are not detector/native execution, photographic acceptance, or a passed test.
The pre-existing colour fixture provides source/person geometry only; each
finish support record below is deliberately reviewed under its own operation.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import people_state as P, body_pose_state as B
from lumaretouch_engine import skin_colour_body_support as S
from lumaretouch_engine import skin_colour_body_host as H
from lumaretouch_engine import skin_colour_body_actions as A
from test_skin_colour_body_support_unrun import fixture

FINISH = {'family': 'skin_finish', 'operation_id': S.FINISH_OPERATION}


def retained(*, both=False):
    state, assets, ref, bank, analysis, review = fixture()
    if both:
        state, assets = S.retain(state, assets, ref, bank, analysis, review)
    state, assets = S.retain(state, assets, ref, bank, analysis, review, **FINISH)
    return state, assets, ref, bank, analysis, review


def raster(state, assets, ref, bank, analysis, *, family='skin_finish'):
    with patch.object(S.M, 'raster', return_value=np.full((64, 64), 255, np.uint8)):
        return S.raster(state, assets, ref, bank, analysis, (64, 64),
                        byte_budget=128*1024*1024, family=family)


def test_family_and_operation_are_exact_not_aliases():
    assert S.family_spec() == (S.KIND, S.OPERATION)
    assert S.family_spec(**FINISH) == (S.FINISH_KIND, S.FINISH_OPERATION)
    for family, operation in [('skin_finish', S.OPERATION), ('skin_colour', S.FINISH_OPERATION),
                              ('skin', None), (S.FINISH_OPERATION, None), (None, None)]:
        with pytest.raises(ValueError):
            S.family_spec(family, operation)


@pytest.mark.parametrize('verb', ['reference', 'preview', 'confirm', 'detach'])
def test_finish_actions_cannot_use_colour_admission(verb):
    _, _, ref, _, _, review = fixture()
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    payload = ({'review': review} if verb == 'preview' else
               {'preview_id': 'reviewed-finish', 'reviewed': True} if verb == 'confirm' else {})
    finish = A.action_name(verb, **FINISH); colour = A.action_name(verb)
    assert finish in A.FINISH_ACTIONS and colour in A.COLOUR_ACTIONS
    A.check_action(finish, payload, target, **FINISH)
    A.check_action(colour, payload, target)
    with pytest.raises(ValueError): A.check_action(finish, payload, target)
    with pytest.raises(ValueError): A.check_action(colour, payload, target, **FINISH)


@pytest.mark.parametrize('scope', ['all_people', 'group', 'person'])
def test_finish_body_review_cannot_be_shared_as_a_scalar_scope(scope):
    _, _, ref, _, _, _ = fixture()
    target = {'scope': scope, 'target_id': ref['face_instance_id'], 'face_ref': ref}
    with pytest.raises(ValueError):
        A.check_action('skin_finish_body_reference', {}, target, **FINISH)


def test_colour_review_never_enables_finish_or_copies_its_mask():
    state, assets, ref, bank, analysis, review = fixture()
    colour, assets = S.retain(state, assets, ref, bank, analysis, review)
    before = deepcopy(assets)
    assert S.resolve(colour, assets, ref, None, None, **FINISH) is None
    assert S.raster(colour, assets, ref, None, None, (64, 64), **FINISH) == (None, {'enabled': False})
    assert S.FINISH_KIND not in colour['faces'][ref['face_instance_id']]['local_assets']
    assert assets == before


def test_deliberate_reviews_have_distinct_immutable_records_and_detach_independently():
    state, assets, ref, bank, analysis, _ = retained(both=True)
    colour, colour_key = S.resolve(state, assets, ref, bank, analysis)
    finish, finish_key = S.resolve(state, assets, ref, bank, analysis, **FINISH)
    assert colour_key != finish_key and len(assets) == 2
    assert colour['row']['operation_id'] == S.OPERATION
    assert finish['row']['operation_id'] == S.FINISH_OPERATION
    with pytest.raises(ValueError): S.check_record(colour, **FINISH)
    with pytest.raises(ValueError): S.check_record(finish)
    before = deepcopy(assets)
    detached = S.detach(state, ref, **FINISH)
    assert S.resolve(detached, assets, ref, bank, analysis, **FINISH) is None
    assert S.resolve(detached, assets, ref, bank, analysis)[1] == colour_key
    inverse = S.detach(state, ref)
    assert S.resolve(inverse, assets, ref, bank, analysis, **FINISH)[1] == finish_key
    assert S.resolve(inverse, assets, ref, bank, analysis) is None and assets == before


@pytest.mark.parametrize('flag', S.FLAGS)
def test_finish_needs_each_new_explicit_visibility_confirmation(flag):
    state, assets, ref, bank, analysis, review = fixture()
    state, assets = S.retain(state, assets, ref, bank, analysis, review)
    review[flag] = False
    with pytest.raises(ValueError):
        S.retain(state, assets, ref, bank, analysis, review, **FINISH)
    assert len(assets) == 1


@pytest.mark.parametrize('mutation', ['body-unlink', 'body-disabled', 'body-points', 'body-model',
                                     'people-revision', 'face-link', 'observation-model', 'source'])
def test_finish_requires_current_exact_face_body_source_model_and_association(mutation):
    state, assets, ref, bank, analysis, review = retained()
    if mutation == 'body-unlink': bank = B.unlink(bank, review['body_ref'])
    elif mutation == 'body-disabled': B.target(bank, review['body_ref'])['enabled'] = False
    elif mutation == 'body-points': B.target(bank, review['body_ref'])['record']['points_sha256'] = '9'*64
    elif mutation == 'body-model': B.target(bank, review['body_ref'])['record']['model_sha256'] = '9'*64
    elif mutation == 'people-revision': state['association_revision'] += 1
    elif mutation == 'face-link': state['links'][0]['confirmation_revision'] = 0
    elif mutation == 'observation-model': analysis['body_skin_observation']['semantic_model_sha256'] = '9'*64
    else: B.target(bank, review['body_ref'])['record']['source']['width'] = 80
    with pytest.raises(ValueError): S.resolve(state, assets, ref, bank, analysis, **FINISH)


def test_same_owner_can_have_two_separately_reviewed_overlapping_coverages():
    state, assets, ref, bank, analysis, _ = retained(both=True)
    finish, facts = raster(state, assets, ref, bank, analysis)
    colour, colour_facts = raster(state, assets, ref, bank, analysis, family='skin_colour')
    assert np.array_equal(finish, colour) and not finish.flags.writeable
    assert facts['competing_review_count'] == colour_facts['competing_review_count'] == 0


@pytest.mark.parametrize('active_family,other_family',
                         [('skin_finish', 'skin_colour'), ('skin_colour', 'skin_finish')])
def test_other_face_body_coverage_is_reserved_across_families_even_if_disabled(active_family, other_family):
    state, assets, ref, bank, analysis, _ = retained(both=True)
    record, _ = S.resolve(state, assets, ref, bank, analysis, family=other_family)
    other = P.new_face(ref['asset_sha256'], [.7, .05, .9, .2], analysis['evidence'])
    other['enabled'] = False; other_ref = P.face_ref(other); copied = deepcopy(record)
    # A structurally valid historical competitor still reserves ownership. It
    # is not claimed to have a currently valid live body/person association.
    copied['face_ref'] = other_ref
    copied['row']['face_link']['face_instance_id'] = other_ref['face_instance_id']
    key = S.content_digest(S.check_record(copied, family=other_family)); assets[key] = copied
    kind, _ = S.family_spec(other_family)
    other['local_assets'][kind] = {'owner': other_ref, 'kind': kind, 'content_sha256': key}
    state['faces'][other_ref['face_instance_id']] = other
    with pytest.raises(ValueError, match='overlap'):
        raster(state, assets, ref, bank, analysis, family=active_family)


def test_finish_history_uses_its_private_bank_without_rebinding_colour_bytes():
    state, assets, ref, _, _, _ = retained(both=True)
    project = {'people_graph': state, 'people_support_assets': assets}
    S.validate_project(project); S.validate_project(project, **FINISH)
    bad = deepcopy(project)
    descriptor = bad['people_graph']['faces'][ref['face_instance_id']]['local_assets'][S.FINISH_KIND]
    colour_key = state['faces'][ref['face_instance_id']]['local_assets'][S.KIND]['content_sha256']
    descriptor['content_sha256'] = colour_key
    with pytest.raises(ValueError): S.validate_project(bad, **FINISH)
    private = {'people_support_assets': assets, 'people_context': {
        'people_graph': state, 'people_support_assets': {}}}
    with pytest.raises(ValueError): S.validate_project(private, **FINISH)


def host_fixture(monkeypatch):
    from lumaretouch_engine import full_candidate_render as F, virtual_copy_people as V
    from lumaretouch_engine import body_pose_commands, creative_derived_source, cpu_memory_budget
    state, assets, ref, bank, analysis, review = fixture()
    state = P.set_override(state, 'face', ref['face_instance_id'], S.OPERATION, '/temperature', .2)
    state = P.set_override(state, 'face', ref['face_instance_id'], S.FINISH_OPERATION, '/whitening', .3)
    state, assets = S.retain(state, assets, ref, bank, analysis, review)
    source = {'sha256': ref['asset_sha256'], 'width': 64, 'height': 64}
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    row = {'path': 'synthetic-source.png'}; snapshot = {'unchanged': True}
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
    return engine, state, target, {'review': review}, bank, analysis, version, calls


def test_capture_separates_family_even_for_identical_source_and_scalars(monkeypatch):
    engine, state, target, _, _, _, _, _ = host_fixture(monkeypatch)
    assert H._capture(engine, state, target)[0] != H._capture(engine, state, target, **FINISH)[0]


def test_colour_reference_never_authorizes_finish_preview(monkeypatch):
    engine, state, target, payload, _, _, _, calls = host_fixture(monkeypatch)
    H.reference(engine, state, target, {})
    before = deepcopy(engine._people_support)
    with pytest.raises(ValueError, match='reference'):
        H.preview(engine, state, target, payload, **FINISH)
    assert engine._people_support == before and calls == []


def test_nonzero_colour_alone_does_not_admit_neutral_finish_preview(monkeypatch):
    engine, state, target, payload, _, _, _, calls = host_fixture(monkeypatch)
    state.update(P.set_override(state, 'face', target['target_id'], S.FINISH_OPERATION, '/whitening', 0.))
    H.reference(engine, state, target, {}, **FINISH); before = deepcopy(engine._people_support)
    with pytest.raises(ValueError, match='skin-finish'):
        H.preview(engine, state, target, payload, **FINISH)
    assert engine._people_support == before and calls == []
    assert engine._skin_finish_body_preview is None


def test_finish_full_comparison_and_confirmation_are_private_and_family_tagged(monkeypatch):
    engine, state, target, payload, _, _, _, calls = host_fixture(monkeypatch)
    H.reference(engine, state, target, {})
    colour = H.preview(engine, state, target, payload)
    old_pending = deepcopy(engine._skin_body_preview)
    reference = H.reference(engine, state, target, {}, **FINISH)
    assert reference['attached'] is False and reference['family'] == 'skin_finish'
    assert reference['operation_id'] == S.FINISH_OPERATION
    before = deepcopy(engine._people_support); graph = deepcopy(state)
    finish = H.preview(engine, state, target, payload, **FINISH)
    assert finish['family'] == 'skin_finish' and finish['operation_id'] == S.FINISH_OPERATION
    assert finish['preview_id'] != colour['preview_id'] and engine._skin_body_preview == old_pending
    assert engine._people_support == before and state == graph
    assert len(calls) == 4 and calls[-1]['staged_people_context']['people_graph'] != state
    assert finish['before']['base64'] != finish['after']['base64']
    assert finish['overlay']['mapping'] == 'normalized_full_frame'
    with pytest.raises(ValueError):
        H.confirm(engine, state, target, {'preview_id': colour['preview_id'], 'reviewed': True}, **FINISH)
    marks = []
    candidate, reply = H.confirm(engine, state, target,
        {'preview_id': finish['preview_id'], 'reviewed': True}, **FINISH,
        mark_started=lambda: marks.append(deepcopy(engine._people_support)))
    assert marks == [before] and reply == {'kind': 'confirmed', 'attached': True, **FINISH}
    assert candidate['overrides'] == state['overrides'] and state == graph
    assert len(engine._people_support) == len(before) + 1
    assert all(engine._people_support[key] == value for key, value in before.items())
    assert engine._skin_finish_body_preview is None and engine._skin_finish_body_reference is None
    assert engine._skin_body_preview == old_pending


@pytest.mark.parametrize('copied_from,copied_to', [('skin_colour', 'skin_finish'), ('skin_finish', 'skin_colour')])
def test_even_copied_private_receipt_with_rewritten_fence_cannot_cross_family(monkeypatch, copied_from, copied_to):
    engine, state, target, payload, _, _, _, _ = host_fixture(monkeypatch)
    H.reference(engine, state, target, {}, family=copied_from)
    shown = H.preview(engine, state, target, payload, family=copied_from)
    source_key = '_skin_body_preview' if copied_from == 'skin_colour' else '_skin_finish_body_preview'
    target_key = '_skin_body_preview' if copied_to == 'skin_colour' else '_skin_finish_body_preview'
    copied = deepcopy(getattr(engine, source_key)); copied['fence'] = H._capture(engine, state, target, family=copied_to)[0]
    setattr(engine, target_key, copied); before = deepcopy(engine._people_support)
    with pytest.raises(ValueError):
        H.confirm(engine, state, target, {'preview_id': shown['preview_id'], 'reviewed': True}, family=copied_to)
    assert engine._people_support == before


@pytest.mark.parametrize('change', ['body', 'model', 'association', 'scalar', 'document'])
def test_finish_confirmation_refuses_changed_capture_without_append(monkeypatch, change):
    engine, state, target, payload, bank, analysis, version, _ = host_fixture(monkeypatch)
    H.reference(engine, state, target, {}, **FINISH)
    shown = H.preview(engine, state, target, payload, **FINISH); before = deepcopy(engine._people_support)
    if change == 'body': bank['revision'] += 1
    elif change == 'model': analysis['body_skin_observation']['semantic_model_sha256'] = '9'*64
    elif change == 'association': state['association_revision'] += 1
    elif change == 'scalar':
        state.update(P.set_override(state, 'face', target['target_id'], S.FINISH_OPERATION, '/whitening', .4))
    else: version.revision += 1
    marks = []
    with pytest.raises(ValueError):
        H.confirm(engine, state, target, {'preview_id': shown['preview_id'], 'reviewed': True},
                  **FINISH, mark_started=lambda: marks.append(True))
    assert marks == [] and engine._people_support == before


def test_finish_detach_and_report_do_not_consume_colour_ownership(monkeypatch):
    engine, state, target, payload, bank, analysis, _, _ = host_fixture(monkeypatch)
    source = engine._people_source(); ref = target['face_ref']
    assert H.report(engine, state, source, target['target_id'])['attached'] is True
    report = H.report(engine, state, source, target['target_id'], **FINISH)
    assert report['attached'] is False and report['family'] == 'skin_finish'
    state, assets = S.retain(state, engine._people_support, ref, bank, analysis, payload['review'], **FINISH)
    engine._people_support = assets; engine._skin_body_preview = {'old-colour': True}
    engine._skin_finish_body_preview = {'old-finish': True}
    candidate, reply = H.detach(engine, state, target, {}, **FINISH)
    assert reply == {'kind': 'detached', 'attached': False, **FINISH}
    assert S.KIND in candidate['faces'][ref['face_instance_id']]['local_assets']
    assert S.FINISH_KIND not in candidate['faces'][ref['face_instance_id']]['local_assets']
    assert engine._skin_body_preview == {'old-colour': True} and engine._skin_finish_body_preview is None
    assert engine._people_support == assets
