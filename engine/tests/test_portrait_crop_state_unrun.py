# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No product imports or tests were executed while authoring."""
from copy import deepcopy
import math
import pytest
from lumaretouch_engine import portrait_crop_state as S


def anchors():
    return {'version': 1, 'crown': [500, 100], 'chin': [500, 700], 'face_center': [500, 400]}


def rules():
    return {'version': 1, 'aspect_ratio': 1, 'headroom_fraction': .1,
            'head_fraction': .6, 'horizontal_position': .5}


def test_records_are_detached_and_not_provenance_or_approval():
    original = anchors()
    clean = S.check_anchors(original, 1000, 1000)
    original['crown'][0] = 7
    assert clean['crown'] == [500.0, 100.0]
    assert clean is not original
    for extra in ('reviewed', 'source_sha256', 'detector_model_sha256', 'vertical_position'):
        value = rules(); value[extra] = True
        with pytest.raises(S.PortraitCropError, match='exact version-1'):
            S.check_rules(value)


@pytest.mark.parametrize('value', [0, -1, True, 1.0, 2**31, '1000'])
def test_dimensions_reject_coercion_and_out_of_domain(value):
    with pytest.raises(S.PortraitCropError): S.check_size(value, 1000)
    with pytest.raises(S.PortraitCropError): S.check_size(1000, value)


@pytest.mark.parametrize('value', [True, '0.5', None, math.nan, math.inf, -math.inf, 10**1000])
@pytest.mark.parametrize('field', S.RULE_NAMES)
def test_nonfinite_boolean_string_and_nonrepresentable_rules_rejected(value, field):
    request = rules(); request[field] = value
    with pytest.raises(S.PortraitCropError) as error: S.check_rules(request)
    assert error.value.code == 'invalid_geometry'


@pytest.mark.parametrize('field,value', [('aspect_ratio', 0), ('aspect_ratio', -1),
    ('headroom_fraction', -.01), ('headroom_fraction', 1.01), ('head_fraction', 0),
    ('head_fraction', 1.01), ('horizontal_position', -.01), ('horizontal_position', 1.01)])
def test_local_fraction_domain_not_silent_clamp(field, value):
    request = rules(); request[field] = value
    with pytest.raises(S.PortraitCropError) as error: S.check_rules(request)
    assert error.value.code == 'invalid_geometry'


def test_overdetermined_headroom_is_infeasible_not_changed():
    request = rules(); request['headroom_fraction'] = .5
    with pytest.raises(S.PortraitCropError) as error: S.check_rules(request)
    assert error.value.code == 'infeasible'
    assert request['headroom_fraction'] == .5


@pytest.mark.parametrize('field,point', [('crown', [-1, 100]), ('chin', [500, 1001]),
    ('crown', [500, 700]), ('chin', [500, 99]), ('face_center', [500, 99]),
    ('face_center', [500, 701]), ('crown', [False, 100]), ('chin', [500, math.inf]),
    ('crown', [500]), ('chin', [500, 700, 0])])
def test_observed_anchor_geometry_is_required(field, point):
    value = anchors(); value[field] = point
    with pytest.raises(S.PortraitCropError) as error: S.check_anchors(value, 1000, 1000)
    assert error.value.code == 'invalid_geometry'


def test_missing_fields_wrong_versions_and_preset_scope():
    for original, validator in ((anchors(), lambda v: S.check_anchors(v, 1000, 1000)), (rules(), S.check_rules)):
        for version in (True, 1.0, 0, 2):
            value = deepcopy(original); value['version'] = version
            with pytest.raises(S.PortraitCropError): validator(value)
        value = deepcopy(original); del value['version']
        with pytest.raises(S.PortraitCropError): validator(value)
    assert S.CONTROL_IDS == ('control:PC-32478:9', 'control:PC-32478:15', 'control:PC-32478:16', 'control:PC-32478:17')
    assert S.OPERATION_ID == 'lnx.crop.v1'
    assert 'control:PC-32478:18' not in S.CONTROL_IDS
