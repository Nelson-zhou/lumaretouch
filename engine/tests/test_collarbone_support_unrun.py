# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic schema/ownership fixtures, not photo acceptance.

No product imports, native raster/solver execution or test runs occurred while
authoring. Manual-raster doubles below do not validate segmentation or anatomy.
"""
from copy import deepcopy
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import collarbone_support as C, collarbone_state as STATE
from lumaretouch_engine import skin_colour_body_support as S
from lumaretouch_engine import skin_colour_body_actions as ACTION
from lumaretouch_engine import body_pose_state as BODY
from test_skin_colour_body_support_unrun import fixture as body_fixture

FAMILY = {'family': 'collarbone', 'operation_id': STATE.OP}


def clavicle():
    return {'version': 1, 'domain': 'source-normalized', 'category': 'female',
            'eligibility_confirmed': True, 'visible_anatomy_confirmed': True,
            'curves': [{'id': 'left', 'width': .0625,
                        'points': [[.4, .55], [.5, .54], [.6, .56]]}]}


def fixture():
    state, assets, ref, bank, analysis, review = body_fixture()
    analysis['excluded'] = np.zeros((64, 64), np.float32)
    return state, assets, ref, bank, analysis, {**review, 'clavicle': clavicle()}


def retained():
    state, assets, ref, bank, analysis, review = fixture()
    state, assets = S.retain(state, assets, ref, bank, analysis, review, **FAMILY)
    return state, assets, ref, bank, analysis, review


def test_review_is_exact_local_schema_and_does_not_mutate_or_invent_second_side():
    value = clavicle(); before = deepcopy(value)
    checked = C.check(value, source={'width': 64, 'height': 64})
    assert checked == before and checked is not value and len(checked['curves']) == 1
    assert value == before


@pytest.mark.parametrize('fault', ['missing-category', 'wrong-category', 'false-eligibility',
    'false-visible', 'extra-field', 'boolean-version', 'wrong-domain', 'empty-curves',
    'three-curves', 'duplicate-side', 'curve-extra', 'wrong-side', 'two-points', 'nine-points',
    'edge-point', 'boolean-point', 'nan-point', 'huge-point', 'duplicate-point',
    'zero-width', 'huge-width', 'nan-width', 'boolean-width', 'backtrack', 'self-cross', 'cross-curves'])
def test_ambiguous_or_unbounded_anatomy_refuses(fault):
    value = clavicle(); curve = value['curves'][0]
    if fault == 'missing-category': del value['category']
    elif fault == 'wrong-category': value['category'] = 'inferred-female'
    elif fault == 'false-eligibility': value['eligibility_confirmed'] = False
    elif fault == 'false-visible': value['visible_anatomy_confirmed'] = False
    elif fault == 'extra-field': value['shoulder_points'] = [11, 12]
    elif fault == 'boolean-version': value['version'] = True
    elif fault == 'wrong-domain': value['domain'] = 'viewport'
    elif fault == 'empty-curves': value['curves'] = []
    elif fault == 'three-curves': value['curves'] *= 3
    elif fault == 'duplicate-side': value['curves'].append(deepcopy(curve))
    elif fault == 'curve-extra': curve['inferred'] = True
    elif fault == 'wrong-side': curve['id'] = 'anatomical-left-from-pose'
    elif fault == 'two-points': curve['points'] = curve['points'][:2]
    elif fault == 'nine-points': curve['points'] = [[.3+i*.03, .6] for i in range(9)]
    elif fault == 'edge-point': curve['points'][0][0] = 0
    elif fault == 'boolean-point': curve['points'][0][0] = True
    elif fault == 'nan-point': curve['points'][0][0] = float('nan')
    elif fault == 'huge-point': curve['points'][0][0] = 10**400
    elif fault == 'duplicate-point': curve['points'][2] = curve['points'][0]
    elif fault == 'zero-width': curve['width'] = 0
    elif fault == 'huge-width': curve['width'] = 10**400
    elif fault == 'nan-width': curve['width'] = float('nan')
    elif fault == 'boolean-width': curve['width'] = True
    elif fault == 'backtrack': curve['points'] = [[.3, .5], [.6, .5], [.4, .5]]
    elif fault == 'self-cross': curve['points'] = [[.3, .4], [.7, .7], [.7, .4], [.3, .7]]
    else: value['curves'].append({'id': 'right', 'width': .0625,
                                  'points': [[.5, .4], [.5, .6], [.5, .7]]})
    with pytest.raises(ValueError): C.check(value, source={'width': 64, 'height': 64})


@pytest.mark.parametrize('width,pixels', [(4/64, 4), (256/1024, 256)])
def test_half_width_is_admitted_at_actual_source_extent(width, pixels):
    value = clavicle(); value['curves'][0]['width'] = width
    size = 64 if pixels == 4 else 1024
    if pixels == 256:
        value['curves'][0]['points'] = [[.1, .5], [.5, .51], [.9, .5]]
    assert C.check(value, source={'width': size, 'height': size}) == value


@pytest.mark.parametrize('width', [3.99/64, 256.01/1024])
def test_width_is_not_clamped_to_native_limits(width):
    value = clavicle(); value['curves'][0]['width'] = width
    size = 64 if width < .1 else 1024
    with pytest.raises(ValueError): C.check(value, source={'width': size, 'height': size})


def test_subpixel_segment_refuses_even_when_normalized_points_are_distinct():
    value = clavicle(); value['curves'][0]['points'][1] = [.4001, .5501]
    with pytest.raises(ValueError): C.check(value, source={'width': 64, 'height': 64})


@pytest.mark.parametrize('points,width', [
    ([[.4, .5], [.42, .51], [.6, .5]], .0625),
    ([[.4, .5], [.5, .5], [.6, .5]], .2),
    ([[.4, .5], [.5, .5], [.5, .7]], .0625),
    ([[.4, .5], [.6, .5], [.5, .7]], .0625)])
def test_source_segment_length_total_extent_and_tangent_admission_match_native(points, width):
    value = clavicle(); value['curves'][0].update(points=points, width=width)
    with pytest.raises(ValueError): C.check(value, source={'width': 64, 'height': 64})


def test_second_visible_curve_and_explicit_elder_category_are_supported():
    value = clavicle(); value['category'] = 'elder_female'
    value['curves'].append({'id': 'right', 'width': .0625,
                           'points': [[.65, .56], [.75, .54], [.85, .55]]})
    assert C.check(value, source={'width': 64, 'height': 64}) == value


def test_new_family_preserves_old_review_records_and_never_borrows_them():
    state, assets, ref, bank, analysis, review = fixture()
    old = {k: v for k, v in review.items() if k != 'clavicle'}
    for family in S.FAMILIES[:3]:
        state2, assets2 = S.retain(state, assets, ref, bank, analysis, old, family=family)
        assert S.resolve(state2, assets2, ref, None, None, **FAMILY) is None
    for family in S.FAMILIES[:-1]:
        with pytest.raises(ValueError): S.retain(state, assets, ref, bank, analysis, review, family=family)
    with pytest.raises(ValueError): S.retain(state, assets, ref, bank, analysis, old, **FAMILY)
    assert S.FAMILIES == ('skin_colour', 'skin_finish', 'body_skin_evenness', 'body_face_match', 'collarbone')


def test_clavicle_review_hash_pins_every_manual_and_eligibility_decision():
    state, assets, ref, bank, analysis, review = retained()
    record, key = S.resolve(state, assets, ref, bank, analysis, **FAMILY)
    for mutation in ('width', 'point', 'category'):
        changed = deepcopy(review)
        if mutation == 'width': changed['clavicle']['curves'][0]['width'] = .08
        elif mutation == 'point': changed['clavicle']['curves'][0]['points'][1][1] += .01
        else: changed['clavicle']['category'] = 'elder_female'
        candidate, candidate_assets = S.retain(state, assets, ref, bank, analysis, changed, **FAMILY)
        _, candidate_key = S.resolve(candidate, candidate_assets, ref, bank, analysis, **FAMILY)
        assert candidate_key != key and candidate_assets[key] == record and assets[key] == record


@pytest.mark.parametrize('fault', ['unlink', 'disabled', 'body-revision', 'people-revision', 'missing-semantic'])
def test_live_anatomy_cannot_rebind_after_body_person_source_change(fault):
    state, assets, ref, bank, analysis, review = retained()
    if fault == 'unlink': bank = BODY.unlink(bank, review['body_ref'])
    elif fault == 'disabled': BODY.target(bank, review['body_ref'])['enabled'] = False
    elif fault == 'body-revision': bank['association_revision'] += 1
    elif fault == 'people-revision': state['association_revision'] += 1
    else: analysis.pop('body_skin')
    with pytest.raises(ValueError): S.resolve(state, assets, ref, bank, analysis, **FAMILY)


def test_historical_validation_retains_original_ownership_without_live_resolution():
    state, assets, ref, _, _, _ = retained()
    S.validate_project({'people_graph': state, 'people_support_assets': assets}, **FAMILY)
    original = deepcopy(assets)
    detached = S.detach(state, ref, **FAMILY)
    S.validate_project({'people_graph': detached, 'people_support_assets': assets,
                        'undo': [{'people_graph': state}]}, **FAMILY)
    assert assets == original


def test_known_occluders_and_all_face_boxes_are_excluded_from_anatomy_coverage():
    state, assets, ref, bank, analysis, _ = retained()
    analysis['excluded'][40, 30] = .11; analysis['body_skin'][41, 30] = 0
    with patch.object(S.M, 'raster', return_value=np.full((64, 64), 255, np.uint8)):
        coverage, facts = S.raster(state, assets, ref, bank, analysis, (64, 64),
                                  byte_budget=256*1024**2, **FAMILY)
    assert coverage[40, 30] == coverage[41, 30] == 0 and not np.any(coverage[5:21, 5:21])
    assert not coverage.flags.writeable and facts['runtime_quality_accepted'] is False


@pytest.mark.parametrize('amount', [0, -.1, 1.1, True, None, float('nan'), float('inf'), 10**400])
def test_private_preview_needs_explicit_positive_finite_amount(amount):
    _, _, ref, _, _, review = fixture()
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    with pytest.raises(ValueError):
        ACTION.check_action('collarbone_preview', {'review': review, 'amount': amount}, target, **FAMILY)


def test_confirm_cannot_replace_preview_anatomy_or_amount():
    _, _, ref, _, _, review = fixture()
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    ACTION.check_action('collarbone_preview', {'review': review, 'amount': .5}, target, **FAMILY)
    for extra in ({'amount': .8}, {'review': review}, {'source': 'other'}):
        with pytest.raises(ValueError): ACTION.check_action('collarbone_confirm',
            {'preview_id': 'exact-candidate', 'reviewed': True, **extra}, target, **FAMILY)


@pytest.mark.parametrize('value', [True, -1, 2, float('nan'), 10**400])
def test_scalar_state_is_bounded_and_never_accepts_anatomy(value):
    with pytest.raises(ValueError): STATE.check({'version': 1, 'amount': value})
    with pytest.raises(ValueError): STATE.check({'version': 1, 'amount': 0, 'clavicle': clavicle()})


@pytest.mark.parametrize('labels', [{'age_band': '儿童'}, {'gender_label': '男'},
                                    {'age_band': '儿童', 'gender_label': '女'}])
def test_conflicting_current_labels_refuse_new_review_and_invalidate_live_attachment(labels):
    state, assets, ref, bank, analysis, review = fixture()
    state['faces'][ref['face_instance_id']]['labels'] = labels
    with pytest.raises(ValueError, match='applicability'):
        S.retain(state, assets, ref, bank, analysis, review, **FAMILY)
    state, assets, ref, bank, analysis, review = retained()
    state['faces'][ref['face_instance_id']]['labels'] = labels
    with pytest.raises(ValueError, match='applicability'):
        S.resolve(state, assets, ref, bank, analysis, **FAMILY)
    # Structure/history is not live eligibility. Detach and neutral remain safe.
    S.validate_project({'people_graph': state, 'people_support_assets': assets}, **FAMILY)
    assert STATE.check({'version': 1, 'amount': 0}) == STATE.neutral()
    detached = S.detach(state, ref, **FAMILY)
    assert S.resolve(detached, assets, ref, None, None, **FAMILY) is None


@pytest.mark.parametrize('labels', [{}, {'age_band': '未标注', 'gender_label': '未标注'},
                                    {'age_band': '成人', 'gender_label': '女'}])
def test_unknown_labels_use_only_explicit_dedicated_applicability_attestation(labels):
    C.require_eligibility({'labels': labels}, clavicle())
    value = clavicle(); value['eligibility_confirmed'] = False
    with pytest.raises(ValueError): C.require_eligibility({'labels': labels}, value)
