# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN recipe contracts, not photographic/native acceptance.

No product import, test collection/execution, build, typecheck or inference was
performed during authoring. Tests below require a separately authorized run.
"""
from copy import deepcopy
import pytest
from lumaretouch_engine import face_style_recipes as S, people_algorithms as A

STYLES = ('classic', 'youthful', 'bold', 'youth', 'round', 'long', 'square')
SUFFIXES = ('7ce4146bc1', 'e4a7970fd2', '7e035684d8', '0e3343d22a',
            '7b800a0655', 'ae54a179f8', '9fc7c5a61e')


def defaults():
    return {op: deepcopy(recipe) for op, (recipe, _) in A.specifications().items()}


def apply(values, patches):
    """Fixture-only path merge, not a replacement production owner."""
    out = deepcopy(values)
    for patch in patches:
        assert patch['unset'] is False
        node = out[patch['operation_id']]
        components = patch['parameter_path'].split('/')[1:]
        for key in components[:-1]:
            node = node[key]
        node[components[-1]] = patch['value']
    return out


def test_exact_catalogue_and_detached_metadata():
    c = S.catalogue()
    assert c['version'] == c['binding_version'] == 1
    assert c['family_control_id'] == 'PC-32466-C-3b31aac970'
    assert c['amount_control_id'] == 'PC-32466-C-6c86bf2c55'
    assert [r['id'] for r in c['styles']] == list(STYLES)
    assert [r['control_id'] for r in c['styles']] == ['PC-32466-C-' + x for x in SUFFIXES]
    assert sum(map(len, c['owned_parameters'].values())) == 30
    assert len(c['owned_operation_ids']) == 10
    c['styles'][0]['id'] = 'changed'
    c['owned_parameters'].clear()
    assert S.catalogue()['styles'][0]['id'] == 'classic'
    assert S.catalogue()['owned_parameters']


@pytest.mark.parametrize('style', STYLES)
@pytest.mark.parametrize('amount', (0, .125, .5, 1))
def test_all_recipes_validate_and_share_exact_owned_union(style, amount):
    patches = S.patches(style, amount)
    assert patches == S.patches(style, amount)
    identities = [(p['operation_id'], p['parameter_path']) for p in patches]
    assert len(identities) == len(set(identities)) == 30
    assert identities == [(p['operation_id'], p['parameter_path']) for p in S.patches('classic', 0)]
    assert all(set(p) == {'operation_id', 'parameter_path', 'unset', 'value'} for p in patches)
    assert all(p['operation_id'] not in ('lnx.deform.v1', 'lnx.slim_face.v2') for p in patches)
    assert all(type(p['value']) is bool or abs(p['value']) <= .30 for p in patches)
    candidate = apply(defaults(), patches)
    assert S.validate_compatibility(candidate) == candidate


@pytest.mark.parametrize('previous', STYLES)
@pytest.mark.parametrize('following', STYLES)
def test_switch_replaces_prior_owned_intent_only(previous, following):
    original = defaults()
    original['lnx.brow_shape.v1']['arch'] = {'linked': False, 'left': .31, 'right': -.22}
    original['lnx.eye_shape.v1']['iris_size']['left'] = .13
    original['lnx.nose_shape.v1']['wing'] = -.14
    original['lnx.mouth_shape.v1']['upper'] = .2
    before = deepcopy(original)
    switched = apply(apply(original, S.patches(previous, .8)), S.patches(following, .4))
    assert switched == apply(original, S.patches(following, .4))
    assert original == before
    neutral = apply(switched, S.patches(following, 0))
    assert neutral == original


def test_owned_manual_values_are_explicitly_overwritten_not_restored():
    original = defaults()
    original[S.CONTOUR.OP]['jaw'] = {'linked': False, 'left': .5, 'right': -.4}
    original['lnx.eye_shape.v1']['size']['left'] = -.2
    changed = apply(original, S.patches('classic', 0))
    assert changed[S.CONTOUR.OP]['jaw'] == {'linked': True, 'left': 0., 'right': 0.}
    assert changed['lnx.eye_shape.v1']['size'] == {'linked': True, 'left': 0., 'right': 0.}
    assert original[S.CONTOUR.OP]['jaw']['left'] == .5


def test_exact_signed_local_coefficients():
    classic = apply(defaults(), S.patches('classic', 1))
    assert [classic[S.CONTOUR.OP][k]['left'] for k in ('temple', 'cheekbone', 'jaw')] == [-.12, .18, -.20]
    assert classic['lnx.eye_shape.v1']['size']['left'] == .18
    young = apply(defaults(), S.patches('youthful', 1))
    assert young[S.MID.OP]['amount'] == -.08
    assert young[S.LOWER.OP]['amount'] == -.04
    assert young['lnx.brow_shape.v1']['position']['left'] == -.04
    assert young['lnx.eye_shape.v1']['spacing']['left'] == .04
    assert young['lnx.eye_shape.v1']['position']['left'] == -.04
    assert young['lnx.nose_shape.v1']['height'] == -.03
    assert young['lnx.mouth_shape.v1']['vertical'] == -.03
    assert apply(defaults(), S.patches('bold', 1))[S.SIZE.OP]['amount'] == .25
    youth = apply(defaults(), S.patches('youth', 1))
    assert [youth[S.CONTOUR.OP][k]['left'] for k in ('temple', 'cheekbone', 'jaw')] == [-.10, .14, -.16]
    assert youth[S.CHIN.OP]['left'] == .06
    round_face = apply(defaults(), S.patches('round', 1))
    assert round_face[S.CONTOUR.OP]['cheekbone']['left'] == .25
    assert round_face[S.CONTOUR.OP]['jaw']['left'] == -.12
    assert round_face[S.CHIN.OP]['left'] == .18
    assert round_face[S.LENGTH.OP]['amount'] == .06
    long_face = apply(defaults(), S.patches('long', 1))
    assert [long_face[op]['amount'] for op in (S.MID.OP, S.LOWER.OP, S.LENGTH.OP)] == [-.25, -.18, -.08]
    square = apply(defaults(), S.patches('square', 1))
    assert square[S.CONTOUR.OP]['jaw']['left'] == -.30
    assert square[S.CHIN.OP]['left'] == .08


@pytest.mark.parametrize('amount', (-.01, 1.01, float('nan'), float('inf'), -float('inf'), True, False, None, '1', [], 10**1000))
def test_invalid_amounts_refuse(amount):
    with pytest.raises(ValueError): S.patches('classic', amount)


@pytest.mark.parametrize('style', ('unknown', '', None, True, [], {}))
def test_invalid_styles_refuse(style):
    with pytest.raises(ValueError): S.patches(style, .5)


@pytest.mark.parametrize('version', (0, 2, True, 1.0, '1', None))
def test_unknown_binding_refuses(version):
    with pytest.raises(ValueError): S.patches('classic', .5, binding_version=version)


def test_future_geometry_schema_refuses(monkeypatch):
    monkeypatch.setattr(S.EYE, 'VERSION', 2)
    with pytest.raises(ValueError): S.patches('classic', .5)
    with pytest.raises(ValueError): S.catalogue()


@pytest.mark.parametrize('style,legacy,value', (
    ('classic', 'big_eye', .2), ('round', 'small_chin', .2), ('long', 'small_chin', .2),
))
def test_existing_legacy_conflicts_are_not_cleared(style, legacy, value):
    candidate = apply(defaults(), S.patches(style, 1))
    candidate[A.DEFORM][legacy] = value
    before = deepcopy(candidate)
    with pytest.raises(ValueError): S.validate_compatibility(candidate)
    assert candidate == before


def test_active_slim_v2_conflicts_with_owned_contour_but_not_neutral():
    original = defaults()
    original[A.SLIM_FACE.OP] = {'version': 2, 'linked': True, 'left': .2, 'right': .2}
    # Use its actual schema rather than assume the operation suffix equals version.
    original[A.SLIM_FACE.OP]['version'] = A.SLIM_FACE.VERSION
    with pytest.raises(ValueError):
        S.validate_compatibility(apply(original, S.patches('square', 1)))
    assert S.validate_compatibility(apply(original, S.patches('square', 0))) == original


def test_compatibility_requires_complete_recipe_map_and_does_not_alias():
    with pytest.raises(ValueError): S.validate_compatibility({})
    values = defaults()
    values['unexpected'] = {}
    with pytest.raises(ValueError): S.validate_compatibility(values)
    original = apply(defaults(), S.patches('classic', .5))
    checked = S.validate_compatibility(original)
    checked[S.SIZE.OP]['amount'] = .8
    assert original[S.SIZE.OP]['amount'] == 0.
