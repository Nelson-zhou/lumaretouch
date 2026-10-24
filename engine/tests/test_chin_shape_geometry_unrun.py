# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN source-owned horizontal chin contracts.

All geometry, RGB, masks and observations below are explicit synthetic doubles.
Forward and bisection formulas are TEST ONLY, never runtime inverse fallbacks.
These cases do not establish actual anatomy, segmentation, native ABI loading,
photographic quality, clinical roundness or commercial parity. No imports,
collection, execution, builds, inference, downloads or type checks were run.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from test_lower_face_geometry_unrun import _fixture as _lower_fixture
from test_face_contour_geometry_unrun import _analysis
from lumaretouch_engine import face_contour_geometry as G
from lumaretouch_engine import chin_shape_runtime as R, chin_shape_state as S
from lumaretouch_engine import chin_shape_people as PORT
from lumaretouch_engine.people_geometry import FaceGeometry


def _fixture():
    """Explicit synthetic lip/oval geometry, never a product anatomy template."""
    lm, source, skin, excluded = _lower_fixture()
    angle = np.pi + np.arange(len(R.INNER_LIPS)) * (2. * np.pi / len(R.INNER_LIPS))
    lm[list(R.INNER_LIPS), :2] = np.column_stack((.5 + .045 * np.cos(angle),
                                                .62 + .006 * np.sin(angle)))
    return lm, source, skin, excluded


def _recipe(left=.5, right=None):
    if right is None:
        right = left
    return S.check({'version': 1, 'linked': left == right, 'left': left, 'right': right})


def _smooth(value):
    t = np.clip(value, 0., 1.)
    return t * t * t * (10. - 15. * t + 6. * t * t)


def _vertical(t):
    value = np.zeros_like(t)
    rising, falling = (t > 0.) & (t < 1.), (t >= 1.) & (t < 1.5)
    value[rising] = _smooth(t[rising])
    value[falling] = _smooth(2. * (1.5 - t[falling]))
    return value


def _forward(points, parameters):
    """Independent TEST-ONLY forward expression, not an inverse implementation."""
    local = points - parameters[:2]
    u, t = local @ parameters[2:4], (local @ parameters[4:6]) / parameters[6]
    inner, outer, left, right = parameters[7:]
    amount = np.where(u > 0., left, np.where(u < 0., right, 0.))
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    shift = -((.08 * u) * amount) * _vertical(t) * lateral
    return shift[:, None] * parameters[2:4]


def _native_double(points, parameters):
    """Independent bounded source-radius bisection; not execution of native code."""
    local = points - parameters[:2]
    u = local[:, 0] * parameters[2] + local[:, 1] * parameters[3]
    t = (local[:, 0] * parameters[4] + local[:, 1] * parameters[5]) / parameters[6]
    inner, outer, left, right = parameters[7:]
    radius = np.abs(u)
    amount = np.where(u > 0., left, right)
    active = (u != 0.) & (radius < outer) & (t > 0.) & (t < 1.5) & (amount != 0.)
    vertical = _vertical(t)
    low, high = np.zeros_like(radius), np.full_like(radius, outer)
    for _ in range(100):
        middle = low + .5 * (high - low)
        lateral = _smooth((outer - middle) / (outer - inner))
        destination = middle - ((.08 * middle) * amount) * vertical * lateral
        high = np.where(destination > radius, middle, high)
        low = np.where(destination <= radius, middle, low)
    recovered = low + .5 * (high - low)
    lateral = _smooth((outer - recovered) / (outer - inner))
    distance = -np.sign(u) * ((.08 * recovered) * amount) * vertical * lateral
    distance = np.where(active, distance, 0.)
    return np.ascontiguousarray(distance[:, None] * parameters[2:4])


def _build(monkeypatch, left=.5, right=None, *, protected_boxes=(), mutate=None):
    lm, source, skin, excluded = _fixture()
    if mutate is not None:
        mutate(lm, source, skin, excluded)
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', _native_double)
    field = R.build(lm, _recipe(left, right), source, excluded, backend='mediapipe',
                    analysis=observation, protected_boxes=protected_boxes)
    return field, lm, source, observation


def test_neutral_has_no_source_analysis_native_or_wrapper_work(monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('neutral input must not be inspected')
    for name in ('_source', 'require_analysis', 'native_evaluate'):
        monkeypatch.setattr(R, name, forbidden)
    assert R.build(None, S.neutral(), None, None, backend='unavailable', analysis=None) is None
    sentinel = object()
    result, facts = PORT.append(sentinel, None, None, None, None, S.neutral())
    assert result is sentinel and facts is None


def test_complete_pinned_lower_arc_and_all_forty_official_lip_vertices():
    assert R.LOWER_ARC == (150, 149, 176, 148, 152, 377, 400, 378, 379)
    edges = {frozenset((a, b)) for a, b in zip(G.FACE_OVAL, (*G.FACE_OVAL[1:], G.FACE_OVAL[0]))}
    assert all(frozenset(edge) in edges for edge in zip(R.LOWER_ARC, R.LOWER_ARC[1:]))
    assert len(R.LIP_VERTICES) == 40
    assert set(G.LIPS).issubset(R.LIP_VERTICES) and set(R.INNER_LIPS).issubset(R.LIP_VERTICES)
    assert not set(R.LOWER_ARC).intersection(R.LIP_VERTICES)


@pytest.mark.parametrize('amount', [1., -1., .4, -.4, 1e-10, -1e-10])
def test_signed_horizontal_width_preserves_actual_tip_all_verticals_and_lips(monkeypatch, amount):
    field, lm, source, _ = _build(monkeypatch, amount)
    measured, p = G.pixels(lm, source.shape[:2]), field.parameters
    expected = _forward(measured, p)
    np.testing.assert_allclose(field.target_landmarks, measured + expected, rtol=0., atol=3e-12)
    np.testing.assert_allclose(field.evaluate(field.target_landmarks), expected, rtol=1e-8, atol=3e-12)
    np.testing.assert_allclose(field.target_landmarks - field.evaluate(field.target_landmarks), measured,
                               rtol=0., atol=3e-12)
    before = measured - p[:2]
    after = field.target_landmarks - p[:2]
    np.testing.assert_allclose(after @ p[4:6], before @ p[4:6], rtol=0., atol=3e-12)
    np.testing.assert_allclose(field.target_landmarks[152], measured[152], rtol=0., atol=3e-12)
    np.testing.assert_array_equal(field.target_landmarks[list(R.LIP_VERTICES)], measured[list(R.LIP_VERTICES)])
    assert np.all(before[list(R.LIP_VERTICES)] @ p[4:6] < 0.)
    assert p[8] == 2. * p[7]
    for ids, sign in ((R.LEFT_ARC, 1.), (R.RIGHT_ARC, -1.)):
        change = sign * (after[list(ids)] @ p[2:4] - before[list(ids)] @ p[2:4])
        assert np.all(change * amount < 0.)
    fact = field.facts['chin_shape']
    assert fact['requirement_id'] == S.CONTROL_ID == 'LNX-REF-PC-32466-C-ed7837df9a'
    assert fact['audited_retained_landmarks'] == 478 and fact['protected_lip_vertices'] == 40
    assert fact['gain'] == S.WIDTH_GAIN == .08 and fact['tail_ratio'] == S.TAIL_FACTOR == .5
    assert fact['minimum_forward_horizontal_slope_bound'] >= .7
    assert fact['maximum_forward_horizontal_slope_bound'] <= 1.3
    assert fact['lower_arc_probe_count'] == 9
    assert 'not_globally_c1' in fact['limitation'] and 'not_guaranteed_roundness' in fact['limitation']


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('amount', [1., -1., .3, -.3])
def test_independent_subject_side_is_not_screen_side_and_does_not_move_neutral_side(monkeypatch, side, amount):
    field, *_ = _build(monkeypatch, amount if side == 'left' else 0., amount if side == 'right' else 0.)
    p, source = field.parameters, field.source_landmarks
    u = (source - p[:2]) @ p[2:4]
    sign = 1. if side == 'left' else -1.
    opposite = sign * u < -1e-10
    np.testing.assert_array_equal(field.target_landmarks[opposite], source[opposite])
    np.testing.assert_array_equal(field.evaluate(field.target_landmarks)[opposite], np.zeros((int(opposite.sum()), 2)))
    fact = field.facts['chin_shape']
    inactive = 'right' if side == 'left' else 'left'
    assert fact['upper_subject_' + inactive + '_skin_rgb_px'] == 0
    assert fact['lower_subject_' + inactive + '_skin_rgb_px'] == 0
    assert fact['lower_arc_probe_count'] == 5


def test_opposing_sides_keep_independent_signed_width_without_averaging(monkeypatch):
    field, *_ = _build(monkeypatch, 1., -1.)
    p = field.parameters
    u = (field.source_landmarks - p[:2]) @ p[2:4]
    target_u = (field.target_landmarks - p[:2]) @ p[2:4]
    assert np.all(target_u[list(R.LEFT_ARC)] < u[list(R.LEFT_ARC)])
    assert np.all(target_u[list(R.RIGHT_ARC)] < u[list(R.RIGHT_ARC)])
    assert field.facts['chin_shape']['linked'] is False


def test_unequal_center_slopes_are_continuous_not_falsely_smoothed_or_c1():
    p = np.array([0., 0., 1., 0., 0., 1., 100., 50., 100., 1., -1.])
    q = np.array([[-1e-6, 100.], [0., 100.], [1e-6, 100.]])
    target = q + R._forward_delta(q, p)
    assert target[1, 0] == 0.
    assert target[0, 0] / q[0, 0] == pytest.approx(1.08)
    assert target[2, 0] / q[2, 0] == pytest.approx(.92)


def test_plane_uses_lowest_actual_outer_or_inner_lip_not_a_single_marker(monkeypatch):
    field, *_ = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    _, _, _, width = G.frame(lm)
    expected = float(np.max(lm[list(R.LIP_VERTICES)] @ p[4:6])) + max(1., .01 * width)
    assert float(p[:2] @ p[4:6]) == pytest.approx(expected, abs=3e-12)
    assert float((lm[152] - p[:2]) @ p[2:4]) == pytest.approx(0., abs=3e-12)
    assert float((lm[152] - p[:2]) @ p[4:6]) == pytest.approx(p[6], abs=3e-12)


def test_closed_inner_lips_do_not_require_or_invent_an_opening(monkeypatch):
    def close(lm, *rest): lm[list(R.INNER_LIPS), 1] = .62
    field, *_ = _build(monkeypatch, mutate=close)
    np.testing.assert_array_equal(field.target_landmarks[list(R.INNER_LIPS)],
                                  field.source_landmarks[list(R.INNER_LIPS)])
    np.testing.assert_array_equal(field.source_landmarks[13], field.source_landmarks[14])


@pytest.mark.parametrize('mode', ['collapsed_band', 'inverted_arc', 'omitted_neighbor',
                                  'wrong_tip', 'inner_lip_outside', 'outside_oval', 'lip_order'])
def test_bad_measured_geometry_is_refused_without_repair_or_synthetic_markers(monkeypatch, mode):
    lm, source, skin, excluded = _fixture()
    if mode == 'collapsed_band': lm[list(G.LIPS), 1] += .12
    elif mode == 'inverted_arc': lm[149, :2], lm[150, :2] = lm[150, :2].copy(), lm[149, :2].copy()
    elif mode == 'omitted_neighbor': lm[176, :2] = lm[148, :2]
    elif mode == 'wrong_tip': lm[152, 0] += .12
    elif mode == 'inner_lip_outside': lm[402, :2] = [.5, .72]
    elif mode == 'outside_oval': lm[100, :2] = [.05, .05]
    else: lm[13, 1], lm[14, 1] = lm[14, 1], lm[13, 1]
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('bad geometry reached native'))
    with pytest.raises(ValueError):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=observation)


@pytest.mark.parametrize('mode', ['missing_skin', 'zero_skin', 'flat_rgb', 'placeholder'])
def test_landmarks_never_replace_authenticated_actual_skin_and_rgb(monkeypatch, mode):
    lm, source, skin, excluded = _fixture()
    if mode == 'zero_skin': skin.fill(0.)
    if mode == 'flat_rgb': source.fill(.5)
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    if mode == 'missing_skin':
        del observation['face_skin']; del observation['face_skin_observation']
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('missing evidence reached native'))
    with pytest.raises(ValueError):
        R.build(lm, _recipe(), source, excluded,
                backend='template' if mode == 'placeholder' else 'mediapipe', analysis=observation)


@pytest.mark.parametrize('sector', range(4))
@pytest.mark.parametrize('loss', ['skin', 'rgb', 'variance'])
def test_each_requested_chin_sector_needs_its_own_evidence(monkeypatch, sector, loss):
    field, _, source, observation = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    _, _, center, width = G.frame(lm)
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    points = np.column_stack((xx.ravel(), yy.ravel()))
    u, v = (points - p[:2]) @ p[2:4], (points - p[:2]) @ p[4:6]
    selected = (((u >= 0.) == bool(sector % 2)) & ((v >= .5 * p[6]) == bool(sector // 2))
                & (v > 0.) & (v < p[6])).reshape(source.shape[:2])
    skin = observation['face_skin'].copy()
    if loss == 'skin': skin[selected] = 0.
    else: source[selected] = 1. if loss == 'rgb' else .5
    with pytest.raises(ValueError, match='requested lower-chin sectors'):
        R._chin_support(lm, center, p[:2], p[2:4], p[4:6], p[6], width,
                        source, skin, observation['excluded'], _recipe(), p[8])


@pytest.mark.parametrize('side', ['left', 'right'])
def test_untouched_side_does_not_require_active_skin_rgb_or_occluder_clearance(monkeypatch, side):
    def remove(lm, source, skin, excluded):
        pixels = G.pixels(lm, source.shape[:2])
        right, up, _, width = G.frame(pixels)
        origin, *_ = R._measured_chin(pixels, right, -up, width)
        yy, xx = np.mgrid[:skin.shape[0], :skin.shape[1]]
        points = np.column_stack((xx.ravel(), yy.ravel()))
        u, v = (points - origin) @ right, (points - origin) @ -up
        selected = ((u < 0.) if side == 'left' else (u > 0.)) & (v > 0.)
        skin.ravel()[selected] = 0.
        excluded.ravel()[selected] = 1.
        source.reshape(-1, 3)[selected] = .5
    field, *_ = _build(monkeypatch, 1. if side == 'left' else 0.,
                       1. if side == 'right' else 0., mutate=remove)
    assert field.facts['chin_shape']['applied']


@pytest.mark.parametrize('landmark', [150, 149, 176, 148, 152, 377, 400, 378, 379])
def test_each_actual_lower_arc_probe_requires_local_rgb_not_sector_average(monkeypatch, landmark):
    field, _, source, observation = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    _, _, center, width = G.frame(lm)
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    points = np.column_stack((xx.ravel(), yy.ravel()))
    local = np.linalg.norm(points - lm[landmark], axis=1) <= max(3., .025 * width)
    source.reshape(-1, 3)[local] = .5
    with pytest.raises(ValueError, match='requested measured lower-arc vertices'):
        R._chin_support(lm, center, p[:2], p[2:4], p[4:6], p[6], width,
                        source, observation['face_skin'], observation['excluded'], _recipe(), p[8])


@pytest.mark.parametrize('landmark', [148, 152, 377, 14])
def test_known_occlusion_veto_covers_actual_moving_oval_and_measured_lips(monkeypatch, landmark):
    def occlude(lm, source, skin, excluded):
        point = lm[landmark, :2] * [source.shape[1] - 1, source.shape[0] - 1]
        if landmark != 14: point[1] -= 2.
        if landmark == 152: point[0] += 1.  # Actual moving skin, not the fixed u=0 line.
        x, y = np.rint(point).astype(int)
        excluded[y, x] = 1.
    with pytest.raises(ValueError, match='occluder'):
        _build(monkeypatch, mutate=occlude)


def test_lower_lip_skin_exemption_does_not_exempt_real_rgb_or_veto(monkeypatch):
    def remove_skin(lm, source, skin, excluded):
        yy, xx = np.mgrid[:skin.shape[0], :skin.shape[1]]
        points = np.column_stack((xx.ravel(), yy.ravel()))
        selected = G.polygon_inside(points, G.pixels(lm, skin.shape)[list(G.LIPS)])
        skin.ravel()[selected] = 0.
    field, *_ = _build(monkeypatch, mutate=remove_skin)
    assert field.facts['chin_shape']['lower_lip_rgb_px'] > 0
    def blank(lm, source, skin, excluded):
        yy, xx = np.mgrid[:skin.shape[0], :skin.shape[1]]
        points = np.column_stack((xx.ravel(), yy.ravel()))
        selected = G.polygon_inside(points, G.pixels(lm, skin.shape)[list(G.LIPS)])
        source.reshape(-1, 3)[selected] = .5
    with pytest.raises(ValueError, match='lower-lip RGB'):
        _build(monkeypatch, mutate=blank)


@pytest.mark.parametrize('scale', [0., .5, -1.])
def test_native_zero_attenuation_or_wrong_sign_cannot_be_reported_applied(monkeypatch, scale):
    lm, source, skin, excluded = _fixture()
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda q, p: _native_double(q, p) * scale)
    with pytest.raises(ValueError, match='full requested amount'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=observation)


@pytest.mark.parametrize('side', ['left', 'right', 'both'])
def test_every_requested_moving_oval_segment_uses_actual_endpoints(monkeypatch, side):
    seen = []
    original = R._chin_segment_support
    def record(a, b, *args):
        seen.append((a.copy(), b.copy()))
        return original(a, b, *args)
    monkeypatch.setattr(R, '_chin_segment_support', record)
    field, *_ = _build(monkeypatch, .5 if side != 'right' else 0., .5 if side != 'left' else 0.)
    p, oval = field.parameters, field.source_landmarks[list(G.FACE_OVAL)]
    u, v = (oval - p[:2]) @ p[2:4], (oval - p[:2]) @ p[4:6]
    epsilon = np.finfo(np.float64).eps * max(field.shape) * 32
    expected = []
    for i, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0))):
        j = (i + 1) % len(oval)
        active = ((p[9] != 0. and max(u[i], u[j]) > epsilon)
                  or (p[10] != 0. and min(u[i], u[j]) < -epsilon))
        if max(v[i], v[j]) > 0. and active: expected.append((a, b))
    np.testing.assert_array_equal(np.asarray(seen), np.asarray(expected))
    assert len(seen) == field.facts['chin_shape']['boundary_segments']


def test_nonrepresentable_one_side_refuses_whole_request_without_gain_inflation(monkeypatch):
    lm, source, skin, excluded = _fixture()
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('lost target precision reached native'))
    with pytest.raises(ValueError, match='representable'):
        R.build(lm, _recipe(.5, 1e-300), source, excluded, backend='mediapipe', analysis=observation)


def test_target_audit_cannot_accept_fabricated_or_snapped_measured_targets(monkeypatch):
    field, *_ = _build(monkeypatch)
    target = field.target_landmarks.copy()
    target[152, 0] += .1
    with pytest.raises(ValueError, match='full requested forward operation'):
        R.ChinShapeField(field.parameters.copy(), field.source_landmarks.copy(), target,
                         field.shape, field.facts['chin_shape'])


def test_canonical_float32_source_ownership_rejects_forgery_and_added_precision(monkeypatch):
    field, lm, source, observation = _build(monkeypatch)
    precise = observation['landmarks'].astype(np.float64) + 1e-11
    other = R.build(precise, _recipe(), source, observation['excluded'], backend='mediapipe',
                    analysis={**observation, 'landmarks': precise})
    np.testing.assert_array_equal(other.parameters, field.parameters)
    np.testing.assert_array_equal(other.source_landmarks, field.source_landmarks)
    forged = deepcopy(observation)
    forged['landmarks'][176, 0] += .001
    with pytest.raises(ValueError, match='exact retained'):
        R.build(lm, _recipe(), source, observation['excluded'], backend='mediapipe', analysis=forged)
    wrong_mask = observation['excluded'].copy(); wrong_mask[0, 0] = 1.
    with pytest.raises(ValueError, match='retained same-source'):
        R.build(lm, _recipe(), source, wrong_mask, backend='mediapipe', analysis=observation)


@pytest.mark.parametrize('location', ['lateral_feather', 'below_tip_feather', 'rectangle_corner', 'neutral_side'])
def test_complete_support_rectangle_conservatively_protects_all_other_retained_faces(monkeypatch, location):
    field, _, source, _ = _build(monkeypatch, .5, 0.)
    p = field.parameters
    x, y = {'lateral_feather': (1.5 * p[7], .5 * p[6]),
            'below_tip_feather': (.5 * p[7], 1.25 * p[6]),
            'rectangle_corner': (p[8] - .1, 1.5 * p[6] - .1),
            'neutral_side': (-.5 * p[7], .5 * p[6])}[location]
    point = p[:2] + x * p[2:4] + y * p[4:6]
    h, w = source.shape[:2]
    box = np.r_[point - .25, point + .25] / [w - 1, h - 1, w - 1, h - 1]
    with pytest.raises(ValueError, match='another retained face'):
        _build(monkeypatch, .5, 0., protected_boxes=[box])


@pytest.mark.parametrize('axis,offset', [(0, .20), (1, .18)])
def test_full_lateral_or_below_chin_support_cannot_be_clipped_or_gain_reduced(monkeypatch, axis, offset):
    def shift(lm, *rest): lm[:, axis] += offset
    with pytest.raises(ValueError, match='complete influence bounding box'):
        _build(monkeypatch, mutate=shift)


def test_roll_mirror_and_scale_use_actual_person_relative_axes(monkeypatch):
    field, lm, source, observation = _build(monkeypatch, .7, -.4)
    angle = .12
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    for transform, scale in ((rotation, 1.), (np.diag([-1., 1.]), 1.), (np.eye(2), .9)):
        changed = lm.copy()
        changed[:, :2] = ((lm[:, :2].astype(np.float64) - .5) @ transform.T * scale + .5).astype(np.float32)
        changed_observation = _analysis(changed, source.shape[:2], observation['face_skin'], observation['excluded'])
        other = R.build(changed, _recipe(.7, -.4), source, observation['excluded'],
                        backend='mediapipe', analysis=changed_observation)
        np.testing.assert_allclose(other.parameters[2:4], transform @ field.parameters[2:4], atol=2e-6)
        np.testing.assert_allclose(other.parameters[4:6], transform @ field.parameters[4:6], atol=2e-6)
        transformed = (field.target_landmarks - 200.) @ transform.T * scale + 200.
        np.testing.assert_allclose(other.target_landmarks, transformed, rtol=0., atol=8e-5)


def test_exact_center_upper_support_edges_and_neutral_side_identity(monkeypatch):
    field, *_ = _build(monkeypatch, .5, 0.)
    p = field.parameters
    local = np.array([[0., p[6]], [p[7], 0.], [p[7], -.1], [p[8], p[6]],
                      [p[7], 1.5 * p[6]], [-.5 * p[7], .5 * p[6]],
                      [.5 * p[7], p[6]], [1.5 * p[7], p[6]], [.5 * p[7], 1.25 * p[6]]])
    points = p[:2] + local[:, :1] * p[2:4] + local[:, 1:] * p[4:6]
    delta = field.evaluate(points)
    np.testing.assert_array_equal(delta[:6], np.zeros((6, 2)))
    assert np.all(np.linalg.norm(delta[6:], axis=1) > 0.)
    np.testing.assert_allclose(delta @ p[4:6], 0., rtol=0., atol=1e-12)


def test_support_join_inverse_uses_recovered_source_radius(monkeypatch):
    field, *_ = _build(monkeypatch, 1., -1.)
    p = field.parameters
    u = np.array([-p[7] - 1e-6, -p[7], -p[7] + 1e-6,
                  p[7] - 1e-6, p[7], p[7] + 1e-6])
    source = p[:2] + u[:, None] * p[2:4] + p[6] * p[4:6]
    expected = _forward(source, p)
    target = source + expected
    np.testing.assert_allclose(field.evaluate(target), expected, rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(target - field.evaluate(target), source, rtol=0., atol=3e-12)


def test_forward_stable_zero_edge_and_tiny_amount_multiplication_order():
    p = np.array([0., 0., 1., 0., 0., 1., 100., 50., 100., 1., 1.])
    delta = R._forward_delta(np.array([[100. - 1e-6, 150. - 1e-6]]), p)
    assert delta[0, 0] < 0. and delta[0, 1] == 0.
    # Forward-only arithmetic contract: a tiny amount can still produce a
    # representable delta at huge coordinates. Product admission may refuse it.
    p[7:9] = [1e100, 2e100]; p[9:] = np.nextafter(0., 1.)
    tiny = R._forward_delta(np.array([[1e100, 100.]]), p)
    assert tiny[0, 0] < 0.


def test_parameters_geometry_and_facts_have_no_mutable_aliases(monkeypatch):
    field, *_ = _build(monkeypatch)
    for value in (field.state, field.parameters, field.source_landmarks, field.target_landmarks):
        assert not value.flags.writeable
        with pytest.raises(ValueError): value.setflags(write=True)
    with pytest.raises(FrozenInstanceError): field.state = np.zeros(11)
    facts = field.facts; facts['chin_shape']['left'] = 0.
    assert field.facts['chin_shape']['left'] == .5
    assert field.resident_bytes() >= sum(value.nbytes for value in
        (field.parameters, field.source_landmarks, field.target_landmarks))


def test_native_and_evidence_batches_remain_bounded(monkeypatch):
    field, *_ = _build(monkeypatch)
    calls = []
    def bounded(points, parameters):
        calls.append(len(points)); return _native_double(points, parameters)
    monkeypatch.setattr(R, 'native_evaluate', bounded)
    points = np.tile([[220.5, 280.25]], (2 * 65536 + 3, 1))
    np.testing.assert_array_equal(field.evaluate(points), _native_double(points, field.parameters))
    assert calls == [65536, 65536, 3]
    assert all((ys.stop - ys.start) * (xs.stop - xs.start) <= 65536
               for ys, xs in R._tiles((7, 9), (1032, 1047)))
    assert field.evaluate(np.empty((0, 2), np.float64)).shape == (0, 2)


@pytest.mark.parametrize('bad', [np.array([[np.nan, 1.]]), np.array([[1., np.inf]]), np.zeros(3), np.zeros((2, 3))])
def test_nonfinite_or_wrong_shape_queries_never_reach_native(monkeypatch, bad):
    field, *_ = _build(monkeypatch)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('invalid query reached native'))
    with pytest.raises(ValueError): field.evaluate(bad)


@pytest.mark.parametrize('kind', ['float32', 'shape', 'nan', 'list'])
def test_invalid_native_output_is_refused_not_converted_or_published(monkeypatch, kind):
    field, *_ = _build(monkeypatch)
    def malformed(points, parameters):
        if kind == 'float32': return np.zeros(points.shape, np.float32)
        if kind == 'shape': return np.zeros((len(points), 3), np.float64)
        if kind == 'nan': return np.full(points.shape, np.nan, np.float64)
        return [[0., 0.] for _ in points]
    monkeypatch.setattr(R, 'native_evaluate', malformed)
    with pytest.raises(ValueError, match='finite float64 output contract'):
        field.evaluate(np.array([[220., 280.]]))


def test_common_helpers_do_not_build_or_load_any_other_operator(monkeypatch):
    from lumaretouch_engine import lower_face_native, face_size_native, mid_face_native
    from lumaretouch_engine import lower_face_runtime, face_size_runtime, mid_face_runtime
    def forbidden(*args, **kwargs): pytest.fail('chin shape invoked an unrelated operator')
    for native in (lower_face_native, face_size_native, mid_face_native): monkeypatch.setattr(native, 'native', forbidden)
    for runtime in (lower_face_runtime, face_size_runtime, mid_face_runtime): monkeypatch.setattr(runtime, 'build', forbidden)
    field, *_ = _build(monkeypatch)
    assert field.facts['chin_shape']['applied']


class _SyntheticField:
    """Composition/guard double only, not native or source anatomy."""
    state = ('synthetic',)
    def __init__(self, function, resident=32): self.function, self.resident = function, resident
    def evaluate(self, points): return self.function(points)
    def resident_bytes(self): return self.resident


class _MetadataPrefix(FaceGeometry):
    def resident_bytes(self): return super().resident_bytes() + 819


def test_outermost_prefix_four_through_eight_preserves_mouth_slot_and_all_metadata():
    zero = _SyntheticField(lambda q: np.zeros_like(q), resident=17)
    mouth = _SyntheticField(lambda q: q * [.01, .02], resident=41)
    for count in (4, 5, 6, 7, 8):
        fields = (None, None, None, mouth) + (zero,) * (count - 4)
        prefix = _MetadataPrefix('synthetic', (401, 401), zero, fields)
        chin = _SyntheticField(lambda q: np.tile([2., 0.], (len(q), 1)), resident=83)
        wrapper = PORT.ChinShape('synthetic', (401, 401), zero, (*fields, chin), prefix, ())
        q = np.array([[190., 240.], [210., 260.]])
        expected = chin.evaluate(q) + prefix.evaluate(q - chin.evaluate(q))
        np.testing.assert_array_equal(wrapper.evaluate(q), expected)
        assert wrapper.prefix is prefix and wrapper.fields[3] is mouth
        assert all(a is b for a, b in zip(wrapper.fields[:-1], fields))
        assert wrapper.resident_bytes() == prefix.resident_bytes() + 83 + 256


@pytest.mark.parametrize('stage', ['output', 'intermediate', 'final'])
def test_output_intermediate_and_final_foreign_footprints_are_guarded(stage):
    q = np.array([[150., 200.]])
    chin = _SyntheticField(lambda p: np.tile([10., 0.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([10., 0.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    position = {'output': [150., 200.], 'intermediate': [140., 200.], 'final': [130., 200.]}[stage]
    box = tuple(np.r_[np.asarray(position) - .1, np.asarray(position) + .1] / 400.)
    wrapper = PORT.ChinShape('synthetic', (401, 401), prior, (*prefix.fields, chin), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)


def test_cancellation_does_not_hide_foreign_intermediate_or_invalid_source_margin():
    q = np.array([[150., 200.]])
    chin = _SyntheticField(lambda p: np.tile([10., 0.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([-10., 0.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    box = (139.9 / 400., 199.9 / 400., 140.1 / 400., 200.1 / 400.)
    wrapper = PORT.ChinShape('synthetic', (401, 401), prior, (*prefix.fields, chin), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)
    zero = _SyntheticField(lambda p: np.zeros_like(p))
    prefix = FaceGeometry('synthetic', (401, 401), zero, (None,) * 4)
    huge = _SyntheticField(lambda p: np.tile([250., 0.], (len(p), 1)))
    wrapper = PORT.ChinShape('synthetic', (401, 401), zero, (*prefix.fields, huge), prefix, ())
    with pytest.raises(ValueError, match='genuine source margin'): wrapper.evaluate(q)
