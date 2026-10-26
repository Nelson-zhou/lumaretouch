# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic schema fixtures are NOT photographic evidence."""
from copy import deepcopy
import pytest
from lumaretouch_engine import hand_shape_state as S
from lumaretouch_engine import hand_shape_manifest as M
from lumaretouch_engine.hand_shape_provenance import check_proposal


def source():
    return {'sha256': 'a'*64, 'width': 1000, 'height': 1000}


def region():
    return {'id': 'region:one', 'kind': 'palm', 'part': 'palm',
            'start': [.5, .35], 'end': [.5, .65],
            'negative': [.54, .5], 'positive': [.46, .5]}


def review():
    return {'version': 1, 'domain': 'source-normalized', 'hand_id': 'hand:one',
            'regions': [region()], 'protect': [], 'proposal_id': None,
            'confirmed': {key: True for key in S.FLAGS}}


def recipe():
    return {'version': 1, 'source': source(), 'repair_sha256': 'b'*64,
            'review': review(), 'amounts': {'palm': .5, 'finger': 0., 'joint': 0.},
            'proposal': None}


def proposal():
    # Explicitly synthetic producer-shaped object; schema acceptance cannot
    # authenticate it. Production routes must use their own retained receipt.
    return {'version': 1, 'source': source(), 'proposal_id': 'proposal:fixture',
            'model_id': M.MODEL_ID, 'model_sha256': M.MODEL_SHA256,
            'backend_version': M.RUNTIME_VERSION, 'backend_code_sha256': 'c'*64,
            'input_rgb_sha256': 'd'*64, 'input_dimensions': [1000, 1000],
            'points': [{'index': i, 'x': -.2 if i == 0 else .5,
                        'y': 1.2 if i == 20 else .5, 'z': -.01} for i in range(21)],
            'handedness': [{'index': 0, 'score': .6, 'category_name': 'Left',
                            'display_name': None}]}


def test_manual_standalone_no_face_or_body_prerequisite():
    value = recipe()
    assert S.check(value) == value
    assert S.active(value)
    assert S.check(None) is None
    assert not S.active(None)
    value['amounts']['palm'] = 0
    assert not S.active(value)


def test_copy_is_detached_and_input_not_rewritten():
    value = recipe()
    retained = S.check(value)
    retained['review']['regions'][0]['start'][0] = .1
    assert value['review']['regions'][0]['start'] == [.5, .35]
    p = proposal()
    retained_p = check_proposal(p)
    retained_p['points'][0]['x'] = 0
    assert p['points'][0]['x'] == -.2


@pytest.mark.parametrize('flag', S.FLAGS)
def test_every_visibility_ownership_contact_transition_protection_confirmation_required(flag):
    value = recipe()
    value['review']['confirmed'][flag] = False
    with pytest.raises(ValueError): S.check(value)
    value['review']['confirmed'][flag] = 1
    with pytest.raises(ValueError): S.check(value)


@pytest.mark.parametrize('kind', ['finger', 'joint'])
def test_active_control_requires_its_own_anatomical_support(kind):
    value = recipe()
    value['amounts'][kind] = .3
    with pytest.raises(ValueError): S.check(value)


def test_geometry_comes_from_four_actual_points_not_body_pose():
    geom = S.region_geometry(region(), source())
    assert len(geom) == 6
    assert geom[0] == pytest.approx(499.5)
    assert geom[1] == pytest.approx(499.5)
    assert geom[2:4] == pytest.approx((0., 1.))
    assert geom[4] == pytest.approx(149.85)
    assert geom[5] == pytest.approx(71.928)


def test_duplicate_region_and_wrong_anatomical_role_rejected():
    value = recipe()
    value['review']['regions'].append(deepcopy(value['review']['regions'][0]))
    with pytest.raises(ValueError): S.check(value)
    value = recipe(); value['review']['regions'][0]['part'] = 'thumb'
    with pytest.raises(ValueError): S.check(value)


def test_missing_opposite_contour_hidden_fill_tiny_axis_and_source_edge_rejected():
    for mutate in (
        lambda r: r.update(positive=deepcopy(r['negative'])),
        lambda r: r.update(end=deepcopy(r['start'])),
        lambda r: r.update(start=[.04, .35], end=[.04, .65],
                           negative=[.07, .5], positive=[.01, .5]),
    ):
        value = recipe(); mutate(value['review']['regions'][0])
        with pytest.raises(ValueError): S.check(value)
    value = recipe(); value['review']['regions'][0]['hidden_points'] = [[.5, .3]]
    with pytest.raises(ValueError): S.check(value)


def test_protection_intersection_refuses_instead_of_mask_edge_clipping():
    value = recipe(); value['review']['protect'] = [[.48, .48, .52, .52]]
    with pytest.raises(ValueError): S.check(value)
    value['review']['protect'] = [[.01, .01, .03, .03]]
    assert S.check(value) == value


def test_invalid_source_and_nonfinite_controls_are_not_clamped():
    for field, replacement in [('width', True), ('height', 0), ('sha256', 'not-a-hash')]:
        value = recipe(); value['source'][field] = replacement
        with pytest.raises(ValueError): S.check(value)
    for amount in (float('nan'), float('inf'), 1.01, -1.01, True):
        value = recipe(); value['amounts']['palm'] = amount
        with pytest.raises(ValueError): S.check(value)


def test_raw_proposal_preserves_out_of_frame_and_does_not_gain_visibility():
    p = proposal(); retained = check_proposal(p)
    assert retained == p
    assert retained['points'][0]['x'] == -.2
    assert retained['points'][20]['y'] == 1.2
    assert 'visibility' not in retained['points'][0]
    retained['points'][0]['visibility'] = 1.
    with pytest.raises(ValueError): check_proposal(retained)


def test_matching_proposal_is_not_a_substitute_for_visible_review():
    value = recipe(); value['proposal'] = proposal()
    value['review']['proposal_id'] = value['proposal']['proposal_id']
    assert S.check(value) == value
    value['review']['confirmed']['visible_only'] = False
    with pytest.raises(ValueError): S.check(value)


def test_manual_support_cannot_claim_neural_provenance_and_proposal_source_must_match():
    value = recipe(); value['proposal'] = proposal()
    with pytest.raises(ValueError): S.check(value)
    value['review']['proposal_id'] = value['proposal']['proposal_id']
    value['proposal']['source']['sha256'] = 'e'*64
    with pytest.raises(ValueError): S.check(value)
    value = recipe(); value['review']['proposal_id'] = 'missing'
    with pytest.raises(ValueError): S.check(value)


@pytest.mark.parametrize('key,replacement', [
    ('model_sha256', '0'*64), ('model_id', 'unknown'), ('backend_version', 'unknown'),
    ('backend_code_sha256', 'bogus'), ('input_rgb_sha256', 'bogus'),
    ('input_dimensions', [1000, 500]), ('input_dimensions', [True, 1000]),
    ('input_dimensions', [2000, 2000]), ('version', True),
])
def test_proposal_pin_runtime_hash_and_full_frame_contract(key, replacement):
    value = proposal(); value[key] = replacement
    with pytest.raises(ValueError): check_proposal(value)


def test_proposal_21_indexed_finite_points_and_actual_categories_only():
    value = proposal(); value['points'].pop()
    with pytest.raises(ValueError): check_proposal(value)
    value = proposal(); value['points'][2]['index'] = 3
    with pytest.raises(ValueError): check_proposal(value)
    value = proposal(); value['points'][2]['x'] = float('nan')
    with pytest.raises(ValueError): check_proposal(value)
    value = proposal(); value['handedness'][0]['score'] = True
    with pytest.raises(ValueError): check_proposal(value)
    value = proposal(); value['handedness'][0]['identity'] = 'invented-owner'
    with pytest.raises(ValueError): check_proposal(value)
