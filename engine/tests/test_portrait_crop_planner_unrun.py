# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN numerical oracle and unchanged-sampler contract fixtures.

Synthetic coordinates are not detection, image review or photographic evidence.
No tests, product imports, native loads, builds or inference ran while authoring.
"""
import math
import numpy as np
import pytest
from lumaretouch_engine import portrait_crop_planner as P
from lumaretouch_engine import portrait_crop_state as S
from lumaretouch_engine.ops import geometry as G


def a(crown=(500, 100), chin=(500, 700), center=(500, 400)):
    return {'version': 1, 'crown': list(crown), 'chin': list(chin), 'face_center': list(center)}


def r(aspect=1., room=.1, head=.6, horizontal=.5):
    return {'version': 1, 'aspect_ratio': aspect, 'headroom_fraction': room,
            'head_fraction': head, 'horizontal_position': horizontal}


def test_neutral_reuses_existing_identity_sampler_without_new_pixels():
    p = P.reference_plan(1000, 1000, a(), r())
    assert p['continuous_rect_pixels'] == [0., 0., 1000., 1000.]
    assert p['rect_normalized'] == [0., 0., 1., 1.]
    assert p['output_size'] == [1000, 1000] and p['is_full_frame']
    assert p['backend'] == 'python-reference-unrun'
    image = np.zeros((1000, 1000, 3), dtype=np.uint8)
    assert G.crop_rotate_np(image, p['rect_normalized'], p['rotation_degrees']) is image
    assert p['requested']['vertical_position'] == p['achieved']['vertical_position'] == .4


@pytest.mark.parametrize('width,height,anchors,rules,bounds,size', [
    (1200, 1600, a((600, 400), (600, 1000), (600, 700)), r(.75), [225, 300, 975, 1300], [750, 1000]),
    (1600, 1400, a((800, 300), (800, 700), (800, 500)), r(1.5, .1, .5), [200, 220, 1400, 1020], [1200, 800]),
    (1, 1, a((.5, 0), (.5, 1), (.5, .5)), r(1, 0, 1), [0, 0, 1, 1], [1, 1]),
])
def test_aspect_and_source_boundaries_agree_with_sampler(width, height, anchors, rules, bounds, size):
    p = P.reference_plan(width, height, anchors, rules)
    assert p['pixel_bounds'] == bounds and p['output_size'] == size
    assert list(G.out_size(width, height, p['rect_normalized'], 0.)) == size
    assert p['achieved']['aspect_ratio'] == size[0] / size[1]


@pytest.mark.parametrize('anchors,bounds', [
    (a((40, 28.5), (40, 60.5), (42.5, 44.5)), [10, 20, 74, 84]),
    (a((40, 29.5), (40, 61.5), (43.5, 45.5)), [12, 22, 76, 86]),
])
def test_half_pixel_ties_round_even_for_both_parities(anchors, bounds):
    p = P.reference_plan(128, 128, anchors, r(1, .125, .5))
    assert p['pixel_bounds'] == bounds
    assert list(G._cut(128, p['rect_normalized'][0], p['rect_normalized'][2])) == [bounds[0], bounds[2]]
    assert list(G._cut(128, p['rect_normalized'][1], p['rect_normalized'][3])) == [bounds[1], bounds[3]]
    assert p['achieved']['headroom_fraction'] == (anchors['crown'][1] - bounds[1]) / 64
    assert p['achieved']['horizontal_position'] == (anchors['face_center'][0] - bounds[0]) / 64


def test_requested_and_achieved_metrics_are_separate_after_rounding():
    p = P.reference_plan(128, 128, a((40, 28.5), (40, 60.5), (43, 44.5)), r(65/64, .125, .5))
    assert p['continuous_rect_pixels'] == [10.5, 20.5, 75.5, 84.5]
    assert p['pixel_bounds'] == [10, 20, 76, 84]
    assert p['requested']['aspect_ratio'] == 65/64
    assert p['achieved']['aspect_ratio'] == 66/64
    assert p['achieved']['headroom_fraction'] == 8.5/64
    assert p['requested']['vertical_position'] == .375
    assert p['achieved']['vertical_position'] == 24.5/64
    image = np.arange(128*128*3, dtype=np.float32).reshape(128, 128, 3)
    sampled = G.crop_np(image, p['rect_normalized'])
    assert np.array_equal(sampled, image[20:84, 10:76])
    assert sampled.shape == (64, 66, 3)


def test_off_center_uses_face_center_instead_of_source_center():
    p = P.reference_plan(1200, 1600, a((600, 400), (600, 1000), (600, 700)), r(.75, .1, .6, .25))
    assert p['continuous_rect_pixels'][0] == 412.5
    assert p['pixel_bounds'] == [412, 300, 1162, 1300]
    assert p['requested']['horizontal_position'] == .25
    assert p['achieved']['horizontal_position'] == 188/750


@pytest.mark.parametrize('width,height,anchors,rules,code', [
    (1000, 1000, a(), r(2), 'infeasible'),
    (1000, 1000, a(), r(1, .1, .6, 0), 'infeasible'),
    (1000, 1000, a((500, 20), (500, 620), (500, 320)), r(), 'infeasible'),
    (1000, 1000, a(), r(1, .1, math.ulp(0.)), 'infeasible'),
    (100, 100, a((20.25, 20.125), (20.25, 20.375), (20.25, 20.25)), r(1, 0, 1), 'pixel_rounding'),
    (128, 128, a((64, 20.75), (64, 52.75), (64, 36.75)), r(1, 0, .5), 'pixel_rounding'),
    (1000, 1000, a((0, 100), (500, 700), (500, 400)), r(.5), 'infeasible'),
])
def test_no_clamp_padding_or_forced_single_pixel(width, height, anchors, rules, code):
    with pytest.raises(S.PortraitCropError) as error:
        P.reference_plan(width, height, anchors, rules)
    assert error.value.code == code


def test_vertical_target_cannot_overdetermine_other_rules():
    request = r(); request['vertical_position'] = .25
    with pytest.raises(S.PortraitCropError): P.reference_plan(1000, 1000, a(), request)


def test_native_absence_does_not_enable_reference_fallback(monkeypatch):
    def absent(*args): raise RuntimeError('Native deliberately absent')
    monkeypatch.setattr(P.N, 'solve', absent)
    with pytest.raises(RuntimeError, match='deliberately absent'): P.plan(1000, 1000, a(), r())


def test_native_disagreement_is_not_repaired(monkeypatch):
    def incorrect(width, height, anchors, rules):
        values = P._reference_vector(width, height, anchors, rules)
        values[8] = 1.
        return values
    monkeypatch.setattr(P.N, 'solve', incorrect)
    with pytest.raises(RuntimeError, match='disagreement'): P.plan(1000, 1000, a(), r())


def test_protocol_double_preserves_schema_but_does_not_prove_native_acceptance(monkeypatch):
    monkeypatch.setattr(P.N, 'solve', P._reference_vector)
    p = P.plan(1000, 1000, a(), r())
    assert set(p) == {'version', 'convention', 'operation_id', 'rotation_degrees', 'source_size',
        'anchors', 'rules', 'continuous_rect_pixels', 'rect_normalized', 'pixel_bounds', 'output_size',
        'requested', 'achieved', 'is_full_frame', 'backend'}
    assert set(p['requested']) == {*S.RULE_NAMES, 'vertical_position'}
    assert set(p['achieved']) == {*S.RULE_NAMES, 'vertical_position', 'head_height_pixels'}
    assert p['backend'] == S.BACKEND
