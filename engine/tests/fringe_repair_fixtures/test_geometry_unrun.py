"""AUTHORED / UNRUN: UI-circle inversion and full-resolution eligibility.

No test execution or native raster invocation was performed while authoring.
Raster mocks below isolate composition; they are not raster-quality evidence.
"""
from copy import deepcopy

import numpy as np
import pytest

from lumaretouch_engine import fringe_repair_geometry as F
from lumaretouch_engine import fringe_repair_state as S


def circle():
    return {'id': 'a' * 32, 'mode': 'subtract', 'points': [[.2, .3]],
            'radius': .1, 'opacity': .8, 'feather': .2}


def test_ui_radius_is_short_edge_fraction_not_independent_xy_radius():
    raw = circle(); original = deepcopy(raw)
    stroke, = F.inverse_strokes((800, 600), None, [raw])
    np.testing.assert_allclose(stroke['points'], raw['points'], atol=1e-15, rtol=0.)
    np.testing.assert_allclose(stroke['axes'], [[.075, 0.], [0., .1]], atol=1e-15, rtol=0.)
    assert 'radius' not in stroke and raw == original
    assert S.check_stroke(stroke) == stroke


def test_crop_quarter_turn_transforms_center_and_both_circle_axes_once():
    geometry = ((.25, .25, .75, .75), 90.)
    stroke, = F.inverse_strokes((800, 600), geometry, [circle()])
    np.testing.assert_allclose(stroke['points'], [[.4, .65]], atol=1e-15, rtol=0.)
    np.testing.assert_allclose(stroke['axes'], [[0., -.05], [.0375, 0.]], atol=1e-15, rtol=0.)
    with pytest.raises(ValueError, match='circular brush intent'):
        F.inverse_strokes((800, 600), geometry, [stroke])


def test_arbitrary_rotation_anchor_matches_full_pixel_inverse_not_proxy_rounding():
    from lumaretouch_engine.ops.geometry import out_size
    from lumaretouch_engine.photo_grain_geometry import mapping
    source = (601, 401); geometry = ((.123, .177, .833, .912), 33.)
    ow, oh = out_size(*source, *geometry)
    x, y = ow // 2, oh // 2
    raw = circle(); raw['points'] = [[(x + .5) / ow, (y + .5) / oh]]
    stroke, = F.inverse_strokes(source, geometry, [raw])
    pixel = mapping(source, geometry, (ow, oh))(x, y, 1)[0]
    assert pixel[2] == 1.
    np.testing.assert_allclose(stroke['points'][0], (pixel[:2] + .5) / source, atol=2e-7, rtol=0.)
    axes = np.asarray(stroke['axes']) * source
    np.testing.assert_allclose(np.linalg.norm(axes, axis=1), .1 * min(ow, oh), atol=1e-12, rtol=0.)
    assert abs(float(axes[0] @ axes[1])) < 1e-9


def test_rotation_padding_is_not_a_valid_brush_anchor():
    raw = circle(); raw['points'] = [[0., 0.]]
    with pytest.raises(ValueError, match='crop/rotation padding'):
        F.inverse_strokes((800, 600), ((0., 0., 1., 1.), 45.), [raw])


@pytest.mark.parametrize('radius', [0., -.1, .50001, True, float('nan'), float('inf'), '0.1'])
def test_ui_radius_invalid_values_fail_closed(radius):
    raw = circle(); raw['radius'] = radius
    with pytest.raises(ValueError): F.inverse_strokes((800, 600), None, [raw])


def test_ui_radius_upper_transport_boundary_is_accepted():
    raw = circle(); raw['radius'] = .5
    stroke, = F.inverse_strokes((800, 600), None, [raw])
    np.testing.assert_allclose(stroke['axes'], [[.375, 0.], [0., .5]], atol=1e-15, rtol=0.)


def test_duplicate_and_aggregate_ui_points_are_bounded():
    with pytest.raises(ValueError, match='identities must be unique'):
        F.inverse_strokes((800, 600), None, [circle(), circle()])
    rows = []
    for index in range(9):
        raw = circle(); raw['id'] = str(index); raw['points'] *= S.MAX_STROKE_POINTS
        rows.append(raw)
    with pytest.raises(ValueError, match='total point budget'):
        F.inverse_strokes((800, 600), None, rows)


def test_subtract_then_add_restores_eligibility_without_forcing_detection(monkeypatch):
    from lumaretouch_engine import local_mask_recipe as R
    raw = circle(); raw['opacity'] = 1.; raw['feather'] = 0.
    rows = [raw, {**deepcopy(raw), 'id': 'b' * 32, 'mode': 'add'}]
    value = S.neutral(); value['source'] = {'sha256': 'a' * 64, 'width': 6, 'height': 4}
    value['coverage']['strokes'] = F.inverse_strokes((6, 4), None, rows)
    calls = []
    monkeypatch.setattr(R, 'validate_budget', lambda stack, shape: {'work': 1})
    def raster(stack, shape):
        assert shape == (4, 6)
        calls.append(stack['objects'][0])
        return np.full(shape, 128, np.uint8)
    monkeypatch.setattr(R, 'raster', raster)
    actual = F.coverage(value, (6, 4), None, (6, 4))
    alpha = np.float32(128 / 255.)
    expected = (1. - alpha) + alpha * alpha
    np.testing.assert_allclose(actual, expected, atol=1e-7, rtol=0.)
    assert actual.dtype == np.float32 and len(calls) == 2
    assert all(item['operation'] == 'add' for item in calls)


def test_automatic_capture_masks_rotation_padding_and_rejects_proxy_canvas():
    from lumaretouch_engine.ops.geometry import out_size
    from lumaretouch_engine.photo_grain_geometry import mapping
    source = (8, 6); geometry = ((0., 0., 1., 1.), 45.)
    canvas = out_size(*source, *geometry)
    actual = F.coverage(S.neutral(), source, geometry, canvas)
    row = mapping(source, geometry, canvas)
    expected = np.stack([row(0, y, canvas[0])[:, 2] for y in range(canvas[1])])
    np.testing.assert_array_equal(actual, expected)
    assert actual[0, 0] == 0. and actual.max() == 1.
    with pytest.raises(ValueError, match='full-resolution geometry canvas'):
        F.coverage(S.neutral(), source, geometry, (4, 3))
