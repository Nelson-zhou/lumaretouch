# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN body-to-own-face support contracts.

No product imports, test execution/collection, native calls, builds, inference or
downloads ran during authoring. Synthetic anatomy/source/model/pose records are
schema and routing fixtures, NOT real measurements or image acceptance. Real
ownership, semantic, anatomical, exclusions and budget validators are used;
manual raster/native numerical doubles do not prove Rust or photographic quality.
"""
from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import people_state as P, people_binding as F
from lumaretouch_engine import body_pose_state as B
from lumaretouch_engine import skin_colour_body_support as SUPPORT
from lumaretouch_engine import skin_colour_support as FACE_SUPPORT
from lumaretouch_engine import body_face_match_layer as L, body_face_match_native as N
from lumaretouch_engine import body_face_match_state as S
from test_body_skin_evenness_support_unrun import fixture as body_fixture
from test_skin_evenness_support_unrun import synthetic_observation

ACTIVE = {'version': 1, 'amount': .6}
BUDGET = 512*1024**2
OPTIONS = {'family': 'body_face_match', 'operation_id': 'lnx.body_face_match.v1'}


def fixture(size=256, *, attach=True, family='body_face_match'):
    data = list(body_fixture(size=size, attach=False))
    state, assets, ref, bank, analysis, review, source, manual = data
    _, face_analysis, _ = synthetic_observation(size)
    landmarks = face_analysis['landmarks'].copy()
    landmarks[:, 0] = .5+(landmarks[:, 0]-.5)*.5
    landmarks[:, 1] = .2+(landmarks[:, 1]-.48)*.33
    evidence = {**analysis['evidence'], 'landmark_digest': F.landmark_digest(landmarks)}
    face = state['faces'][ref['face_instance_id']]
    face.update(evidence=deepcopy(evidence), box=[.33, .05, .67, .35])
    analysis.update(evidence=deepcopy(evidence), landmarks=landmarks,
        face_skin=np.ones((size, size), np.float32),
        face_skin_observation={'contract': FACE_SUPPORT.CONTRACT,
            'source_sha256': ref['asset_sha256'], 'semantic_model_sha256': 'c'*64,
            'producer_width': 64, 'producer_height': 64})
    if attach:
        data[0], data[1] = SUPPORT.retain(state, assets, ref, bank, analysis, review, family=family)
    return data


def native_prepare_double(calls):
    """A source-dependent routing mark, NOT the robust/guided matching solver."""
    def prepare(body_rgb, body_coverage, face_rgb, face_coverage, amount, *, radius, cancelled):
        for value in (body_rgb, body_coverage, face_rgb, face_coverage):
            assert value.dtype == np.float32 and value.flags.c_contiguous and not value.flags.writeable
        assert body_rgb.shape == (*body_coverage.shape, 3)
        assert face_rgb.shape == (*face_coverage.shape, 3)
        assert 4 <= radius <= 256
        if cancelled():raise InterruptedError('Synthetic cancelled matching')
        calls.append({'body_rgb': body_rgb.copy(), 'body_coverage': body_coverage.copy(),
            'face_rgb': face_rgb.copy(), 'face_coverage': face_coverage.copy(),
            'amount': amount, 'radius': radius})
        _, observable = L.BODY._reference_admission(body_rgb, body_coverage)
        target = float(np.mean(face_rgb[face_coverage >= .75, 0]))
        result = np.zeros((*body_coverage.shape, 2), np.float32)
        result[..., 0] = body_coverage*observable*np.float32(target*.025*amount)
        result[..., 1] = -body_coverage*observable*np.float32(.012*amount)
        result.setflags(write=False)
        return result
    return prepare


def prepare(data, *, recipe=ACTIVE, byte_budget=BUDGET, cancelled=None, native=None):
    state, assets, ref, bank, analysis, _, source, manual = data; calls = []
    with patch.object(SUPPORT.M, 'raster', return_value=manual), \
            patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=native or native_prepare_double(calls)):
        result = L.prepare(ref, analysis, source, recipe, people_state=state,
            body_assets=assets, body_bank=bank, byte_budget=byte_budget, cancelled=cancelled)
    return result, calls


def expanded(window, value, shape):
    result = np.zeros((*shape, *value.shape[2:]), value.dtype)
    y, x, h, w = window; result[y:y+h, x:x+w] = value
    return result


def test_exact_independent_operation_and_neutral_does_not_resolve_any_source():
    assert S.OP == 'lnx.body_face_match.v1' and S.CONTROL_ID == 'LNX-REF-PC-32465-C-d8b09012a9'
    assert S.check(None) == {'version': 1, 'amount': 0.}
    with patch.object(SUPPORT, 'resolve', side_effect=AssertionError('neutral review')), \
            patch.object(N, 'available', side_effect=AssertionError('neutral native')):
        assert L.prepare(None, None, None, None, people_state=None, body_assets=None,
                         body_bank=None, byte_budget=0) == []


@pytest.mark.parametrize('family', [None, 'skin_colour', 'skin_finish', 'body_skin_evenness'])
def test_active_cannot_borrow_any_existing_familys_body_review(family):
    data = fixture(attach=family is not None, family=family or 'body_face_match')
    with pytest.raises(ValueError, match='own reviewed'):
        prepare(data)


def test_same_effective_source_provides_both_immutable_rois_in_one_solve():
    data = fixture(); before = data[-2].copy(); records, calls = prepare(data)
    assert len(records) == len(calls) == 1
    record, call = records[0], calls[0]
    assert record.stage == 'body_face_match' and record.delta is None
    assert record.weights is None and record.amounts is None
    assert record.chroma_shift.shape == (*record.window[2:], 2) and not record.chroma_shift.flags.writeable
    y, x, h, w = record.window
    fy, fx, fh, fw = record.facts['reference_support']['source_window']
    np.testing.assert_array_equal(call['body_rgb'], before[y:y+h, x:x+w])
    np.testing.assert_array_equal(call['face_rgb'], before[fy:fy+fh, fx:fx+fw])
    np.testing.assert_array_equal(data[-2], before)
    assert record.facts['body_reference_samples'] >= 64 and record.facts['face_reference_samples'] >= 64
    assert record.facts['reference_method'] == 'effective-source-stage-own-face-robust-log-chroma'
    assert record.facts['reference_is_later_corrected_face'] is False
    assert record.facts['application'] == 'pointwise-current-stage-linear-luminance-preserving'
    assert record.facts['runtime_quality_accepted'] is False


def test_body_disconnected_islands_share_one_true_torso_halo_and_one_face_target():
    data = fixture(); data[-1][:] = 0
    data[-1][100:125, 80:110] = 255; data[-1][185:215, 180:210] = 255
    records, calls = prepare(data); record = records[0]
    halo = 2*calls[0]['radius']+1
    assert len(calls) == 1 and record.window == (100-halo, 80-halo, 115+2*halo, 130+2*halo)
    assert np.count_nonzero(calls[0]['body_coverage']) == 25*30+30*30
    assert record.facts['source_halo'] == halo


def test_body_masks_never_supply_or_expand_face_reference_and_vice_versa():
    data = fixture(); records, calls = prepare(data)
    body = expanded(records[0].window, calls[0]['body_coverage'], data[-2].shape[:2])
    face = expanded(records[0].facts['reference_support']['source_window'], calls[0]['face_coverage'], body.shape)
    assert not np.any((body > 0) & (face > 0))
    assert not np.any(body[11:91, 83:173])
    assert not np.any(face[100:])
    changed = data[-2].copy(); changed[face > .75, 0] = .65
    data[-2] = changed
    after, _ = prepare(data)
    assert not np.array_equal(records[0].chroma_shift, after[0].chroma_shift)


def test_foreign_disabled_or_unresolved_faces_and_known_occluders_cannot_donate():
    data = fixture(); state, _, ref, _, analysis, _, _, _ = data
    other = P.new_face(ref['asset_sha256'], [.32, .05, .48, .35], {
        **analysis['evidence'], 'status': 'unresolved', 'landmark_digest': None})
    other['enabled'] = False; state['faces'][other['face_instance_id']] = other
    analysis['excluded'][25:40, 135:145] = 1
    records, calls = prepare(data)
    coverage = expanded(records[0].facts['reference_support']['source_window'],
                        calls[0]['face_coverage'], (256, 256))
    assert not np.any(coverage[12:90, 81:124])
    assert not np.any(coverage[25:40, 135:145])
    assert records[0].facts['reference_support']['protected_face_boxes'] == 1


@pytest.mark.parametrize('fault', ['missing-face', 'merged-only', 'wrong-model', 'wrong-source',
    'wrong-producer', 'changed-digest', 'template', 'wrong-shape', 'face-not-enabled'])
def test_actual_current_own_face_observation_and_verified478_are_required(fault):
    data = fixture(); state, _, ref, _, analysis, _, _, _ = data
    if fault == 'missing-face':analysis.pop('face_skin')
    elif fault == 'merged-only':
        analysis['skin'] = analysis.pop('face_skin'); analysis.pop('face_skin_observation')
    elif fault == 'wrong-model':analysis['face_skin_observation']['semantic_model_sha256'] = '9'*64
    elif fault == 'wrong-source':analysis['face_skin_observation']['source_sha256'] = '9'*64
    elif fault == 'wrong-producer':analysis['face_skin_observation']['producer_width'] = 32
    elif fault == 'changed-digest':analysis['landmarks'][0, 0] += .01
    elif fault == 'template':analysis['evidence']['status'] = 'unresolved'
    elif fault == 'wrong-shape':analysis['landmarks'] = analysis['landmarks'][:477]
    else:state['faces'][ref['face_instance_id']]['enabled'] = False
    with pytest.raises(ValueError):prepare(data)


@pytest.mark.parametrize('fault', ['body-unlink', 'body-disabled', 'body-revision', 'person-revision'])
def test_reference_face_requires_the_reviewed_body_same_confirmed_person(fault):
    data = fixture(); state, _, _, bank, _, review, _, _ = data
    if fault == 'body-unlink':data[3] = B.unlink(bank, review['body_ref'])
    elif fault == 'body-disabled':B.target(bank, review['body_ref'])['enabled'] = False
    elif fault == 'body-revision':bank['association_revision'] += 1
    else:state['association_revision'] += 1
    with pytest.raises(ValueError):prepare(data)


@pytest.mark.parametrize('region', ['body', 'face'])
@pytest.mark.parametrize('value', [0., 1., .005])
def test_each_region_requires_64_reliable_actual_samples(region, value):
    data = fixture()
    if region == 'body':data[-2][100:, :] = value
    else:data[-2][:95, :] = value
    with pytest.raises(ValueError, match='64 reliable'):
        prepare(data, native=lambda *a, **k: pytest.fail('unreliable input reached native'))


def test_too_few_body_samples_cannot_borrow_the_face_count():
    data = fixture(); data[-1][:] = 0; data[-1][100:107, 100:109] = 255
    with pytest.raises(ValueError, match='64 reliable own-body'):prepare(data)


def test_too_few_face_samples_cannot_borrow_the_body_count():
    data = fixture(); data[4]['face_skin'][:] = 0; data[4]['face_skin'][47:54, 126:135] = 1
    with pytest.raises(ValueError, match='64 reliable'):prepare(data)


def test_reference_has_no_face_guided_radius_requirement():
    data = fixture(size=128)
    # Retained face oval's min span*0.08 <4 while true reliable samples can
    # still exceed64. Only the body guided solve has a measured radius gate.
    state, _, ref, _, analysis, _, source, _ = data
    coverage, facts = L.reference_support(ref, analysis, source, people_state=state, byte_budget=BUDGET)
    assert facts['reference_samples'] >= 64 and np.any(coverage > 0)


def test_aggregate_body_and_face_native_estimate_is_admitted_before_native():
    data = fixture()
    with patch.object(N, 'memory_estimate', return_value=BUDGET) as estimate, \
            patch.object(N, 'available', side_effect=AssertionError('native probed after refused budget')):
        with pytest.raises(ValueError, match='combined source-window'):
            prepare(data, native=lambda *a, **k: pytest.fail('oversized combined solve'))
    assert len(estimate.call_args.args) == 2


def test_tiny_budget_refuses_before_body_or_face_raster():
    data = fixture()
    with patch.object(SUPPORT, 'raster', side_effect=AssertionError('body raster')), \
            patch.object(L.FACE, 'selected_face_skin', side_effect=AssertionError('face raster')):
        with pytest.raises(ValueError, match='memory budget before allocation'):
            prepare(data, byte_budget=0)


@pytest.mark.parametrize('fault', ['dtype', 'nan', 'hdr', 'negative'])
def test_source_is_exact_finite_sdr_float32_not_a_clipped_reference(fault):
    data = fixture()
    if fault == 'dtype':data[-2] = data[-2].astype(np.float64)
    elif fault == 'nan':data[-2][40, 120, 0] = np.nan
    elif fault == 'hdr':data[-2][40, 120, 0] = 1.001
    else:data[-2][40, 120, 0] = -.001
    with pytest.raises(ValueError):prepare(data)


def test_missing_native_matching_extension_never_uses_body_evenness_as_fallback():
    data = fixture(); state, assets, ref, bank, analysis, _, source, manual = data
    with patch.object(SUPPORT.M, 'raster', return_value=manual), \
            patch.object(N, 'available', return_value=False), \
            patch.object(L.BODY.N, 'prepare', side_effect=AssertionError('body-evenness fallback')):
        with pytest.raises(RuntimeError, match='no Python effect fallback'):
            L.prepare(ref, analysis, source, ACTIVE, people_state=state, body_assets=assets,
                      body_bank=bank, byte_budget=BUDGET)


@pytest.mark.parametrize('fault', ['rgb-delta', 'nan', 'unbounded', 'protected'])
def test_invalid_native_field_never_publishes_pixels(fault):
    def invalid(body_rgb, coverage, *args, **kwargs):
        if fault == 'rgb-delta':return np.zeros((*coverage.shape, 3), np.float32)
        result = np.zeros((*coverage.shape, 2), np.float32)
        if fault == 'nan':result[0, 0] = np.nan
        elif fault == 'unbounded':result[coverage > 0] = [.08, .08]
        else:result[coverage == 0] = [.01, 0.]
        return result
    with pytest.raises(ValueError):prepare(fixture(), native=invalid)


def test_native_refusal_and_cancellation_are_not_neutral_success():
    with pytest.raises(InterruptedError):prepare(fixture(), cancelled=lambda: True)
    def refused(*a, **k):raise ValueError('insufficient supported source guided context')
    with pytest.raises(ValueError, match='guided context'):prepare(fixture(), native=refused)


def test_competing_owner_of_every_family_reserves_body_coverage():
    for family in SUPPORT.FAMILIES:
        data = fixture(); state, assets, ref, _, analysis, _, _, _ = data
        other = P.new_face(ref['asset_sha256'], [.8, .05, .95, .2], analysis['evidence'])
        other['enabled'] = False; other_ref = P.face_ref(other)
        record = deepcopy(next(iter(assets.values())))
        kind, operation = SUPPORT.family_spec(family)
        record['face_ref'] = other_ref
        record['row'].update(target=kind, operation_id=operation)
        record['row']['face_link']['face_instance_id'] = other_ref['face_instance_id']
        if family != 'body_face_match':record['row'].pop('face_skin_observation')
        if family == 'collarbone':
            record['row']['review']['clavicle'] = {'version':1,'domain':'source-normalized',
                'category':'female','eligibility_confirmed':True,'visible_anatomy_confirmed':True,
                'curves':[{'id':'left','width':.03125,'points':[[.4,.55],[.5,.54],[.6,.56]]}]}
        key = SUPPORT.content_digest(SUPPORT.check_record(record, family=family)); assets[key] = record
        other['local_assets'][kind] = {'owner': other_ref, 'kind': kind, 'content_sha256': key}
        state['faces'][other_ref['face_instance_id']] = other
        with pytest.raises(ValueError, match='overlap'):prepare(data)
