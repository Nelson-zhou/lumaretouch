# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN fourth-operation body/own-face review consent.

Synthetic source/person/anatomy and mocked full-render pixels only exercise the
authored contract. No test collection/execution, product imports, native calls,
builds, typechecks, inference or downloads ran during authoring. This is not
native/photo quality acceptance or proof of learned-AI/brightness matching.
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
from test_body_face_match_support_unrun import fixture as source_fixture

FAMILY = 'body_face_match'
OPTIONS = {'family': FAMILY, 'operation_id': 'lnx.body_face_match.v1'}
FAMILIES = ('skin_colour', 'skin_finish', 'body_skin_evenness', FAMILY)


def retained(families=(FAMILY,)):
    data = source_fixture(attach=False)
    for family in families:
        data[0], data[1] = S.retain(data[0], data[1], data[2], data[3], data[4], data[5], family=family)
    return data


def target_for(ref):
    return {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}


def preview_payload(review, family=FAMILY):
    return {'review': review, **({'amount': .4} if family in ('body_skin_evenness', FAMILY) else {})}


class TensorBoundaryDouble:
    """Only the existing tensor-to-numpy transport boundary, no GPU execution."""
    def __init__(self, value):self.value = value
    @property
    def shape(self):return self.value.shape
    def __getitem__(self, index):return TensorBoundaryDouble(self.value[index])
    def permute(self, *axes):return TensorBoundaryDouble(self.value.transpose(axes))
    def to(self, *args):return self
    def numpy(self):return self.value


def as_pipeline(rgb):
    return TensorBoundaryDouble(rgb.transpose(2, 0, 1)[None])


def host_fixture(monkeypatch):
    from lumaretouch_engine import full_candidate_render as F, virtual_copy_people as V
    from lumaretouch_engine import body_pose_commands, creative_derived_source as SOURCE, cpu_memory_budget
    state, assets, ref, bank, analysis, review, source_rgb, manual = retained(families=FAMILIES[:3])
    state = P.set_override(state, 'face', ref['face_instance_id'], S.OPERATION, '/temperature', .2)
    state = P.set_override(state, 'face', ref['face_instance_id'], S.FINISH_OPERATION, '/whitening', .3)
    state = P.set_override(state, 'face', ref['face_instance_id'], S.EVENNESS_OPERATION, '/amount', .2)
    source = {'sha256': ref['asset_sha256'], 'width': 1024, 'height': 1024}
    target = target_for(ref); row = {'path': 'synthetic-source.png'}; snapshot = {'unchanged': True}
    version = SimpleNamespace(document_id='document', revision=7)
    context = {'people_graph': deepcopy(state), 'people_support_assets': deepcopy(assets)}
    engine = SimpleNamespace(_people_support=deepcopy(assets), _people_targets={source['sha256']: target},
        _people_analyses={source['sha256']: {ref['face_instance_id']: analysis}}, _creative_base=None,
        _people_source=lambda: source, _body_bank=lambda: bank, _people_binding=lambda: {'binding': 1},
        _capture_state=lambda: snapshot, _document_versions=lambda: SimpleNamespace(version=lambda _: version),
        _vram=SimpleNamespace(src_f32=as_pipeline(source_rgb), repair_base=None))
    monkeypatch.setattr(V, 'current_row', lambda _: row)
    monkeypatch.setattr(F, 'identity', lambda e, r, s, document, revision:
        ({'synthetic': True, 'document': document, 'revision': revision}, state, deepcopy(context)))
    monkeypatch.setattr(body_pose_commands, 'source_preview', lambda _: {
        'base64': 'synthetic-raw-source', 'decoded_width': 256, 'decoded_height': 256})
    monkeypatch.setattr(SOURCE, 'analysis_rgb', lambda _: np.rint(source_rgb*255).astype(np.uint8))
    monkeypatch.setattr(SOURCE, 'verify', lambda expected, owner: expected if expected == owner._people_source() else
                        (_ for _ in ()).throw(ValueError('wrong synthetic source binding')))
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 512*1024*1024)
    monkeypatch.setattr(S.M, 'raster', lambda *a: manual)
    calls = []
    def render(owner, current_row, captured, document, revision, **kwargs):
        assert owner._people_support == assets and current_row is row and captured is snapshot
        calls.append(deepcopy(kwargs)); staged = kwargs.get('staged_people_context')
        if staged is not None:
            assert staged['people_graph'] == kwargs['people_graph']
            assert all(staged['people_support_assets'][key] == value for key, value in assets.items())
        return np.full((256, 256, 3), .3 if staged else .2, np.float32), {'synthetic': 'render-proof'}
    monkeypatch.setattr(F, 'render', render)
    return engine, state, target, preview_payload(review), bank, analysis, version, calls


def amount(state, face_id):
    from lumaretouch_engine.people_algorithms import defaults, recipes
    from lumaretouch_engine.people_resolver import resolve
    return recipes(resolve(state, face_id, defaults()))[OPTIONS['operation_id']]['amount']


def test_fourth_family_is_explicit_and_existing_defaults_remain():
    assert S.FAMILIES == (*FAMILIES, 'collarbone')
    assert S.family_spec() == ('skin_colour_body_visibility', 'lnx.skin_colour.v1')
    assert S.family_spec(**OPTIONS) == ('body_face_match_visibility', 'lnx.body_face_match.v1')
    assert S.FACE_MATCH_KIND == 'body_face_match_visibility'
    for family, other in product(FAMILIES, repeat=2):
        if family != other:
            with pytest.raises(ValueError):S.family_spec(family, S.family_spec(other)[1])


@pytest.mark.parametrize('family,verb', product(FAMILIES, ('reference', 'preview', 'confirm', 'detach')))
def test_each_family_has_exact_actions_and_payload(family, verb):
    data = source_fixture(); ref, review = data[2], data[5]
    payload = (preview_payload(review, family) if verb == 'preview' else
               {'preview_id': 'exact-review', 'reviewed': True} if verb == 'confirm' else {})
    action = A.action_name(verb, family=family)
    A.check_action(action, payload, target_for(ref), family=family)
    for other in FAMILIES:
        if other != family:
            with pytest.raises(ValueError):A.check_action(action, payload, target_for(ref), family=other)
    assert A.action_name(verb, **OPTIONS) == 'body_face_match_'+verb


@pytest.mark.parametrize('value', [0, -.1, 1.01, True, False, None, '.3', [], {}, float('nan'), float('inf'), 10**400])
def test_private_match_candidate_requires_explicit_positive_bounded_amount(value):
    data = source_fixture()
    with pytest.raises(ValueError):
        A.check_action('body_face_match_preview', {'review': data[5], 'amount': value}, target_for(data[2]), **OPTIONS)


@pytest.mark.parametrize('extra', ['face_ref', 'reference_rgb', 'target_face', 'reference_source', 'donor'])
def test_preview_cannot_select_or_donate_an_arbitrary_reference(extra):
    data = source_fixture()
    with pytest.raises(ValueError):
        A.check_action('body_face_match_preview', {**preview_payload(data[5]), extra: None}, target_for(data[2]), **OPTIONS)


def test_four_reviews_have_distinct_hashes_and_new_reference_observation_only():
    state, assets, ref, bank, analysis, *_ = retained(families=FAMILIES)
    records = {family: S.resolve(state, assets, ref, bank, analysis, family=family) for family in FAMILIES}
    assert len(assets) == len({key for _, key in records.values()}) == 4
    for family, (record, _) in records.items():
        assert ('face_skin_observation' in record['row']) is (family == FAMILY)
        for other in FAMILIES:
            if other != family:
                with pytest.raises(ValueError):S.check_record(record, family=other)


def test_old_three_reviews_never_authorize_matching_or_its_reference():
    state, assets, ref, *_ = retained(families=FAMILIES[:3]); before = deepcopy(assets)
    assert S.resolve(state, assets, ref, None, None, **OPTIONS) is None
    assert S.FACE_MATCH_KIND not in state['faces'][ref['face_instance_id']]['local_assets']
    assert assets == before


def test_historical_match_review_requires_its_own_bank_and_face_observation():
    state, assets, ref, *_ = retained(families=FAMILIES)
    project = {'people_graph': state, 'people_support_assets': assets}
    S.validate_project(project, **OPTIONS)
    private = {'people_support_assets': assets, 'people_context': {
        'people_graph': state, 'people_support_assets': {}}}
    with pytest.raises(ValueError):S.validate_project(private, **OPTIONS)
    for other in FAMILIES[:3]:
        bad = deepcopy(project); face = bad['people_graph']['faces'][ref['face_instance_id']]
        face['local_assets'][S.FACE_MATCH_KIND]['content_sha256'] = face['local_assets'][S.family_spec(other)[0]]['content_sha256']
        with pytest.raises(ValueError):S.validate_project(bad, **OPTIONS)
    record = deepcopy(next(r for r in assets.values() if r['row']['target'] == S.FACE_MATCH_KIND))
    record['row'].pop('face_skin_observation')
    with pytest.raises(ValueError):S.check_record(record, **OPTIONS)


def test_first_use_stages_face_amount_and_support_then_confirms_atomically(monkeypatch):
    engine, state, target, payload, _, _, _, calls = host_fixture(monkeypatch)
    assert amount(state, target['target_id']) == 0
    for family in FAMILIES[:3]:setattr(engine, H._family(family, None)[4], {'other': family})
    reference = H.reference(engine, state, target, {}, **OPTIONS)
    before = deepcopy(engine._people_support); graph = deepcopy(state)
    shown = H.preview(engine, state, target, payload, **OPTIONS)
    assert state == graph and engine._people_support == before and len(calls) == 2
    assert amount(calls[0]['people_graph'], target['target_id']) == 0
    candidate = calls[1]['people_graph']
    assert amount(candidate, target['target_id']) == payload['amount']
    assert S.FACE_MATCH_KIND in candidate['faces'][target['target_id']]['local_assets']
    assert shown['reference_support'] == reference['reference_support']
    assert shown['own_face_reference'] == reference['own_face_reference']
    assert shown['reference_source_stage'] == reference['reference_source_stage'] == 'immutable-source'
    assert reference['reference_overlay']['mapping'] == shown['overlay']['mapping'] == 'normalized_full_frame'
    marks = []
    committed, reply = H.confirm(engine, state, target, {'preview_id': shown['preview_id'], 'reviewed': True},
        **OPTIONS, mark_started=lambda: marks.append(deepcopy(engine._people_support)))
    assert committed == candidate and marks == [before]
    assert reply == {'kind': 'confirmed', 'attached': True, **OPTIONS}
    assert engine._body_face_match_reference is None and engine._body_face_match_preview is None
    assert len(engine._people_support) == len(before)+1
    assert all(getattr(engine, H._family(family, None)[4]) == {'other': family} for family in FAMILIES[:3])


@pytest.mark.parametrize('other_family', FAMILIES[:3])
def test_old_reference_or_receipt_cannot_confirm_matching_even_with_rewritten_fence(monkeypatch, other_family):
    engine, state, target, payload, *_ = host_fixture(monkeypatch)
    H.reference(engine, state, target, {}, family=other_family)
    old = H.preview(engine, state, target, preview_payload(payload['review'], other_family), family=other_family)
    copied = deepcopy(getattr(engine, H._family(other_family, None)[4]))
    copied['fence'] = H._capture(engine, state, target, **OPTIONS)[0]
    engine._body_face_match_preview = copied; before = deepcopy(engine._people_support)
    with pytest.raises(ValueError):
        H.confirm(engine, state, target, {'preview_id': old['preview_id'], 'reviewed': True}, **OPTIONS)
    assert engine._people_support == before


@pytest.mark.parametrize('change', ['body', 'association', 'face-observation', 'face-skin', 'amount',
                                  'source-pixels', 'repair-stage', 'document'])
def test_confirmation_rejects_changed_source_reference_consent_and_context(monkeypatch, change):
    engine, state, target, payload, bank, analysis, version, _ = host_fixture(monkeypatch)
    H.reference(engine, state, target, {}, **OPTIONS)
    shown = H.preview(engine, state, target, payload, **OPTIONS); before = deepcopy(engine._people_support)
    if change == 'body':bank['revision'] += 1
    elif change == 'association':state['association_revision'] += 1
    elif change == 'face-observation':analysis['face_skin_observation']['producer_width'] = 32
    elif change == 'face-skin':analysis['face_skin'][20, 100] = 0
    elif change == 'amount':engine._body_face_match_preview['amount'] = .6
    elif change == 'source-pixels':engine._vram.src_f32.value[0, 0, 30, 120] += .01
    elif change == 'repair-stage':engine._vram.repair_base = TensorBoundaryDouble(engine._vram.src_f32.value.copy())
    else:version.revision += 1
    marks = []
    with pytest.raises(ValueError):
        H.confirm(engine, state, target, {'preview_id': shown['preview_id'], 'reviewed': True},
                  **OPTIONS, mark_started=lambda: marks.append(True))
    assert marks == [] and engine._people_support == before


def test_reference_uses_actual_repair_source_not_raw_or_rendered_colour(monkeypatch):
    engine, state, target, _, _, analysis, _, _ = host_fixture(monkeypatch)
    repaired = np.full((256, 256, 3), [.61, .41, .32], np.float32)
    engine._vram.repair_base = as_pipeline(repaired)
    working, coverage, facts, identity, stage = H._own_face(engine, state, target['face_ref'], analysis)
    np.testing.assert_array_equal(working, repaired)
    assert not working.flags.writeable and stage == 'verified-repair-base'
    assert facts['reference_samples'] >= 64 and np.any(coverage)
    assert identity['reference_method'] == 'effective-source-stage-own-face-robust-log-chroma'
    reference = H.reference(engine, state, target, {}, **OPTIONS)
    assert reference['reference_source_stage'] == 'verified-repair-base'


def test_derived_reference_requires_existing_repair_replay_verification(monkeypatch):
    from lumaretouch_engine import creative_derived_source as SOURCE, creative_derived_repair_runtime as REPAIR
    engine, state, target, _, _, analysis, _, _ = host_fixture(monkeypatch)
    raw = np.full((256, 256, 3), 128, np.uint8)
    engine._vram.src_f32 = as_pipeline(raw.astype(np.float32)/255.)
    engine._vram.repair_base = as_pipeline(np.full((256, 256, 3), .6, np.float32))
    monkeypatch.setattr(SOURCE, 'record', lambda _: {'fixture-derived': True})
    monkeypatch.setattr(SOURCE, 'analysis_rgb', lambda _: raw)
    with patch.object(REPAIR, 'verify_pipeline', side_effect=ValueError('stale derived repair replay')) as verify:
        with pytest.raises(ValueError, match='stale derived repair'):
            H._own_face(engine, state, target['face_ref'], analysis)
    verify.assert_called_once_with(engine._vram, engine._people_source())


@pytest.mark.parametrize('scope', ['face', 'all_people', 'person'])
def test_active_detach_refuses_and_never_silently_neutralizes_other_scope(monkeypatch, scope):
    engine, state, target, payload, bank, analysis, *_ = host_fixture(monkeypatch)
    state, assets = S.retain(state, engine._people_support, target['face_ref'], bank, analysis, payload['review'], **OPTIONS)
    key = (target['target_id'] if scope == 'face' else target['face_ref']['asset_sha256']
           if scope == 'all_people' else state['links'][0]['person_id'])
    state = P.set_override(state, scope, key, OPTIONS['operation_id'], '/amount', .4)
    engine._people_support = assets; engine._body_face_match_preview = {'pending': True}
    with pytest.raises(ValueError, match='zero'):H.detach(engine, state, target, {}, **OPTIONS)
    assert engine._people_support == assets and engine._body_face_match_preview == {'pending': True}


def test_neutral_detach_preserves_old_three_reviews_and_history_without_live_body(monkeypatch):
    engine, state, target, payload, bank, analysis, *_ = host_fixture(monkeypatch)
    state, assets = S.retain(state, engine._people_support, target['face_ref'], bank, analysis, payload['review'], **OPTIONS)
    engine._people_support = assets
    engine._body_bank = lambda: (_ for _ in ()).throw(AssertionError('neutral consulted body'))
    candidate, reply = H.detach(engine, state, target, {}, **OPTIONS)
    assert reply == {'kind': 'detached', 'attached': False, **OPTIONS}
    assert S.FACE_MATCH_KIND not in candidate['faces'][target['target_id']]['local_assets']
    assert all(S.family_spec(f)[0] in candidate['faces'][target['target_id']]['local_assets'] for f in FAMILIES[:3])
    assert engine._people_support == assets


def test_report_metadata_identity_is_null_until_attached_and_null_when_stale(monkeypatch):
    engine, state, target, payload, bank, analysis, *_ = host_fixture(monkeypatch)
    absent = H.report(engine, state, engine._people_source(), target['target_id'], **OPTIONS)
    assert absent['own_face_reference'] is None and not absent['attached']
    state, assets = S.retain(state, engine._people_support, target['face_ref'], bank, analysis, payload['review'], **OPTIONS)
    engine._people_support = assets
    current = H.report(engine, state, engine._people_source(), target['target_id'], **OPTIONS)
    assert current['own_face_reference']['face_ref'] == target['face_ref'] and not current['needs_review']
    assert 'reference_support' not in current  # Metadata is not actual sample/raster proof.
    bank['association_revision'] += 1
    stale = H.report(engine, state, engine._people_source(), target['target_id'], **OPTIONS)
    assert stale['own_face_reference'] is None and stale['needs_review']
