# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN nose-safe philtrum geometry/source contracts.

Every coordinate, RGB field, observation and mask is an explicit synthetic
double, not measured anatomy or a product fallback. Independent bisection below
is TEST ONLY, not execution of the reused Rust primitive. These fixtures do not
establish real anatomy, segmentation, installed ABI, photographic quality,
admission prevalence or commercial parity. No product imports, collection,
execution, numerical probes, builds, inference, downloads or type checks ran.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from test_chin_shape_geometry_unrun import _fixture as _chin_fixture
from test_face_contour_geometry_unrun import _analysis
from lumaretouch_engine import face_contour_geometry as G
from lumaretouch_engine import philtrum_runtime as R, philtrum_state as S
from lumaretouch_engine import philtrum_people as PORT
from lumaretouch_engine.people_geometry import FaceGeometry


OMITTED_BY_LEGACY_NOSE = (294, 278, 344, 440, 275, 45, 220, 115, 48, 64)


def _fixture():
    """Explicit synthetic full-nose/gap ordering; never an analysis producer."""
    lm, source, skin, excluded = _chin_fixture()
    for index, landmark in enumerate(OMITTED_BY_LEGACY_NOSE):
        lm[landmark, :2] = [.466 + .068 * (index % 2), .54 + .002 * index]
    # The lowest full-set vertex is deliberately absent from legacy G.NOSE.
    lm[275, :2] = [.515, .565]
    lm[164, :2] = [.5, .584]
    return lm, source, skin, excluded


def _recipe(amount=.5):
    return S.check({'version': 1, 'amount': amount})


def _smooth(value):
    t = np.clip(value, 0., 1.)
    z = np.minimum(t, 1. - t)
    low = z * z * z * (10. + z * (6. * z - 15.))
    return np.where(t <= .5, low, 1. - low)


def _vertical(t, plateau, tail):
    out = np.zeros_like(t)
    rising, flat = (t > 0.) & (t < 1.), (t >= 1.) & (t <= plateau)
    falling = (t > plateau) & (t < plateau + tail)
    out[rising] = _smooth(t[rising])
    out[flat] = 1.
    out[falling] = _smooth((plateau + tail - t[falling]) / tail)
    return out


def _forward(points, parameters):
    """Independent TEST-ONLY expression for complete rise/plateau/fall."""
    local = points - parameters[:2]
    height, inner, outer, plateau, tail, amount = parameters[6:]
    u, t = local @ parameters[2:4], (local @ parameters[4:6]) / height
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    distance = ((.08 * height) * amount) * lateral * _vertical(t, plateau, tail)
    return distance[:, None] * parameters[4:6]


def _native_double(points, parameters):
    """Independent TEST-ONLY shift bisection, never a runtime fallback."""
    local = points - parameters[:2]
    height, inner, outer, plateau, tail, amount = parameters[6:]
    u, t = local @ parameters[2:4], (local @ parameters[4:6]) / height
    amplitude = ((.08 * height) * amount) * _smooth((outer - np.abs(u)) / (outer - inner))
    active = (np.abs(u) < outer) & (t > 0.) & (t < plateau + tail)
    low, high = np.minimum(amplitude, 0.), np.maximum(amplitude, 0.)
    for _ in range(100):
        middle = low + .5 * (high - low)
        residual = middle - amplitude * _vertical(t - middle / height, plateau, tail)
        high = np.where(residual > 0., middle, high)
        low = np.where(residual <= 0., middle, low)
    distance = np.where(active, low + .5 * (high - low), 0.)
    return np.ascontiguousarray(distance[:, None] * parameters[4:6])


def _build(monkeypatch, amount=.5, *, protected_boxes=(), mutate=None):
    lm, source, skin, excluded = _fixture()
    if mutate is not None:
        mutate(lm, source, skin, excluded)
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', _native_double)
    field = R.build(lm, _recipe(amount), source, excluded, backend='mediapipe',
                    analysis=observation, protected_boxes=protected_boxes)
    return field, lm, source, observation


def test_neutral_skips_all_source_native_and_wrapper_work(monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('neutral inspected an unrelated input')
    for name in ('_source', 'require_analysis', 'native_evaluate'):
        monkeypatch.setattr(R, name, forbidden)
    assert R.build(None, S.neutral(), None, None, backend='unavailable', analysis=None) is None
    sentinel = object()
    out, facts = PORT.append(sentinel, None, None, None, None, S.neutral())
    assert out is sentinel and facts is None


def test_complete_pinned_official_nose_and_lip_sets_do_not_inherit_incomplete_legacy_nose():
    assert R.NOSE_VERTICES == (168, 6, 197, 195, 5, 4, 1, 19, 94, 2, 98, 97, 326, 327,
                              294, 278, 344, 440, 275, 45, 220, 115, 48, 64)
    assert len(R.NOSE_VERTICES) == len(set(R.NOSE_VERTICES)) == 24
    assert set(R.NOSE_VERTICES) - set(G.NOSE) == set(OMITTED_BY_LEGACY_NOSE)
    assert len(R.LIP_VERTICES) == 40
    assert set(G.LIPS).issubset(R.LIP_VERTICES) and set(R.INNER_LIPS).issubset(R.LIP_VERTICES)
    assert not set(R.NOSE_VERTICES).intersection(R.LIP_VERTICES)


@pytest.mark.parametrize('amount', [1., -1., .4, -.4, 1e-10, -1e-10])
def test_signed_gap_keeps_full_nose_fixed_and_translates_lips_chin_and_every_lower_source(monkeypatch, amount):
    field, lm, source, _ = _build(monkeypatch, amount)
    measured, p = G.pixels(lm, source.shape[:2]), field.parameters
    expected = _forward(measured, p)
    np.testing.assert_allclose(field.target_landmarks, measured + expected, rtol=0., atol=3e-12)
    np.testing.assert_allclose(field.evaluate(field.target_landmarks), expected, rtol=1e-8, atol=3e-12)
    np.testing.assert_allclose(field.target_landmarks - field.evaluate(field.target_landmarks), measured,
                               rtol=0., atol=3e-12)
    u, v = (measured - p[:2]) @ p[2:4], (measured - p[:2]) @ p[4:6]
    lower = v >= p[6]
    assert lower[152] and np.all(lower[list(R.LIP_VERTICES)])
    np.testing.assert_array_equal(field.target_landmarks[list(R.NOSE_VERTICES)], measured[list(R.NOSE_VERTICES)])
    np.testing.assert_array_equal(field.target_landmarks[v <= 0.], measured[v <= 0.])
    np.testing.assert_allclose((field.target_landmarks - p[:2]) @ p[2:4], u, rtol=0., atol=3e-12)
    delta = ((.08 * p[6]) * amount) * p[4:6]
    np.testing.assert_allclose(expected[lower], np.broadcast_to(delta, expected[lower].shape), rtol=1e-10, atol=0.)
    np.testing.assert_allclose(field.target_landmarks[lower] - field.target_landmarks[0],
                               measured[lower] - measured[0], rtol=0., atol=3e-12)
    before = (measured[0] - measured[2]) @ p[4:6]
    after = (field.target_landmarks[0] - field.target_landmarks[2]) @ p[4:6]
    assert after - before == pytest.approx((.08 * p[6]) * amount, rel=2e-4, abs=3e-12)
    assert (after > before) if amount > 0. else (after < before)
    fact = field.facts['philtrum']
    assert fact['requirement_id'] == S.CONTROL_ID == 'LNX-REF-PC-32466-C-2605502c27'
    assert fact['audited_retained_landmarks'] == 478 and fact['protected_nose_vertices'] == 24
    assert fact['rigid_lip_vertices'] == 40 and fact['gain'] == S.LENGTH_GAIN == .08
    assert fact['audited_lower_plateau_landmarks'] == int(np.count_nonzero(lower))
    assert fact['tail_ratio'] == max(.25, .5 * (p[9] - 1.))
    assert fact['minimum_forward_vertical_slope_bound'] >= .4
    assert fact['maximum_forward_vertical_slope_bound'] <= 1.6
    assert 'full_width_rising_band_also_changes_surrounding_cheeks' in fact['limitation']
    assert 'short_gap_native_plateau_limit_refusal_prevalence_unmeasured' in fact['limitation']


@pytest.mark.parametrize('landmark', OMITTED_BY_LEGACY_NOSE)
def test_each_previously_omitted_official_nose_vertex_can_define_fixed_plane(monkeypatch, landmark):
    def lowest(lm, *rest):
        lm[275, 1] = .55
        lm[landmark, 1] = .566
    field, *_ = _build(monkeypatch, mutate=lowest)
    p, lm = field.parameters, field.source_landmarks
    _, _, _, width = G.frame(lm)
    assert float((p[:2] - lm[landmark]) @ p[4:6]) == pytest.approx(max(1., .01 * width), abs=3e-12)
    np.testing.assert_array_equal(field.target_landmarks[landmark], lm[landmark])


def test_planes_use_all_actual_vertices_and_actual_nose_lateral_axis(monkeypatch):
    field, *_ = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    _, _, _, width = G.frame(lm)
    margin = max(1., .01 * width)
    upper = float(np.max(lm[list(R.NOSE_VERTICES)] @ p[4:6])) + margin
    lower = float(np.min(lm[list(R.LIP_VERTICES)] @ p[4:6])) - margin
    assert p[:2] @ p[4:6] == pytest.approx(upper, abs=3e-12)
    assert p[6] == pytest.approx(lower - upper, abs=3e-12)
    assert (lm[2] - p[:2]) @ p[2:4] == pytest.approx(0., abs=3e-12)
    assert p[8] - p[7] == pytest.approx(.25 * width)
    assert p[9] <= 8. and p[10] == max(.25, .5 * (p[9] - 1.))
    # Actual nose2-to-lip0 is NOT the margin-trimmed H; its change is additive.
    assert (lm[0] - lm[2]) @ p[4:6] > p[6]


@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('amount', [-.7, .7])
def test_rotated_and_reflected_head_axis_keeps_nose_fixed_and_lower_face_rigid(monkeypatch, mirror, amount):
    angle = .2
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    transform = rotation @ np.diag([-1. if mirror else 1., 1.])
    def reposition(lm, *rest): lm[:, :2] = .5 + (lm[:, :2] - .5) @ transform.T
    field, *_ = _build(monkeypatch, amount, mutate=reposition)
    p, lm = field.parameters, field.source_landmarks
    np.testing.assert_allclose(p[2:4], transform @ [1., 0.], rtol=0., atol=1e-6)
    np.testing.assert_allclose(p[4:6], transform @ [0., 1.], rtol=0., atol=1e-6)
    lower = (lm - p[:2]) @ p[4:6] >= p[6]
    np.testing.assert_array_equal(field.target_landmarks[list(R.NOSE_VERTICES)], lm[list(R.NOSE_VERTICES)])
    np.testing.assert_allclose(field.target_landmarks[lower] - field.target_landmarks[0],
                               lm[lower] - lm[0], rtol=0., atol=3e-12)
    np.testing.assert_allclose(field.target_landmarks - field.evaluate(field.target_landmarks),
                               lm, rtol=0., atol=3e-12)


@pytest.mark.parametrize('amount', [-1., 1.])
def test_inverse_plateau_membership_is_source_based_at_both_joins(monkeypatch, amount):
    field, *_ = _build(monkeypatch, amount)
    p = field.parameters
    t = np.array([1. - 1e-6, 1., 1. + 1e-6, p[9] - 1e-6, p[9], p[9] + 1e-6])
    source = p[:2] + (t * p[6])[:, None] * p[4:6]
    motion = _forward(source, p)
    target = source + motion
    np.testing.assert_allclose(field.evaluate(target), motion, rtol=1e-10, atol=3e-12)
    np.testing.assert_allclose(target - field.evaluate(target), source, rtol=0., atol=3e-12)
    if amount < 0.:
        assert (target[1] - p[:2]) @ p[4:6] < p[6]
    else:
        assert (target[4] - p[:2]) @ p[4:6] > p[9] * p[6]


def test_plateau_contains_every_retained_lower_point_not_just_actual_chin(monkeypatch):
    def beyond_tip(lm, *rest): lm[100, :2] = lm[152, :2] + [0., .001]
    field, *_ = _build(monkeypatch, mutate=beyond_tip)
    p, lm = field.parameters, field.source_landmarks
    v = (lm - p[:2]) @ p[4:6]
    assert v[100] > v[152] and p[9] * p[6] > v[100]
    np.testing.assert_allclose(field.target_landmarks[[0, 100, 152]] - lm[[0, 100, 152]],
                               np.broadcast_to(((.08 * p[6]) * p[11]) * p[4:6], (3, 2)), atol=3e-12)


def test_closed_inner_lips_need_no_invented_opening(monkeypatch):
    def close(lm, *rest): lm[list(R.INNER_LIPS), 1] = .62
    field, *_ = _build(monkeypatch, mutate=close)
    np.testing.assert_array_equal(field.source_landmarks[13], field.source_landmarks[14])
    np.testing.assert_array_equal(field.target_landmarks[13], field.target_landmarks[14])


@pytest.mark.parametrize('mode', ['overlap', 'too_short', 'native_plateau_limit',
                                  'inner_lip_outside', 'outside_oval', 'nose_lip_order'])
def test_unresolved_gap_or_native_limits_refuse_without_geometry_repair(monkeypatch, mode):
    lm, source, skin, excluded = _fixture()
    if mode == 'overlap': lm[275, 1] = .61
    elif mode == 'too_short': lm[275, 1] = .59
    elif mode == 'native_plateau_limit': lm[275, 1] = .574
    elif mode == 'inner_lip_outside': lm[402, :2] = [.5, .70]
    elif mode == 'outside_oval': lm[100, :2] = [.05, .05]
    else: lm[13, 1], lm[14, 1] = lm[14, 1], lm[13, 1]
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    before = lm.copy()
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('invalid gap reached native'))
    with pytest.raises(ValueError, match='native P' if mode == 'native_plateau_limit' else None):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=observation)
    np.testing.assert_array_equal(lm, before)


@pytest.mark.parametrize('mode', ['missing_skin', 'zero_skin', 'flat_rgb', 'placeholder'])
def test_landmarks_do_not_replace_authenticated_source_skin_rgb(monkeypatch, mode):
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


def _support_args(field, source, observation):
    p, lm = field.parameters, field.source_landmarks
    _, _, center, width = G.frame(lm)
    facts = field.facts['philtrum']
    return (lm, center, p[:2], p[2:4], p[4:6], p[6], width, source,
            observation['face_skin'], observation['excluded'], p[8], p[9], p[10],
            facts['central_gap_axis_min_px'], facts['central_gap_axis_max_px'])


@pytest.mark.parametrize('region', ['central gap', 'surrounding moving band', 'lower face'])
@pytest.mark.parametrize('sector', range(4))
@pytest.mark.parametrize('loss', ['skin', 'rgb', 'variance'])
def test_each_region_has_independent_four_sector_source_evidence(monkeypatch, region, sector, loss):
    field, _, source, observation = _build(monkeypatch)
    p, lm, fact = field.parameters, field.source_landmarks, field.facts['philtrum']
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    points = np.column_stack((xx.ravel(), yy.ravel()))
    u, v = (points - p[:2]) @ p[2:4], (points - p[:2]) @ p[4:6]
    left, right = fact['central_gap_axis_min_px'], fact['central_gap_axis_max_px']
    if region == 'central gap':
        selected = (v > 0.) & (v < p[6]) & (u > left) & (u < right)
        middle = .5 * p[6]
    elif region == 'surrounding moving band':
        selected = (v > 0.) & (v < p[6]) & ((u <= left) | (u >= right))
        middle = .5 * p[6]
    else:
        end = (lm[152] - p[:2]) @ p[4:6]
        selected, middle = (v >= p[6]) & (v <= end), .5 * (p[6] + end)
    selected &= ((u >= 0.) == bool(sector % 2)) & ((v >= middle) == bool(sector // 2))
    if loss == 'skin': observation['face_skin'].ravel()[selected] = 0.
    else: source.reshape(-1, 3)[selected] = 1. if loss == 'rgb' else .5
    with pytest.raises(ValueError, match='all four ' + region + ' sectors'):
        R._source_support(*_support_args(field, source, observation))


@pytest.mark.parametrize('where', ['gap', 'surrounding', 'lips', 'chin'])
def test_known_occluders_cannot_hide_in_any_moving_region(monkeypatch, where):
    field, _, source, observation = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    point = {'gap': p[:2] + .5 * p[6] * p[4:6],
             'surrounding': p[:2] + .3 * p[7] * p[2:4] + .5 * p[6] * p[4:6],
             'lips': lm[14], 'chin': lm[152] - 2. * p[4:6]}[where]
    x, y = np.rint(point).astype(int)
    observation['excluded'][y, x] = 1.
    with pytest.raises(ValueError, match='occluder'):
        R._source_support(*_support_args(field, source, observation))


def test_gap_counts_are_local_area_scaled_not_cheek_width_squared(monkeypatch):
    field, *_ = _build(monkeypatch)
    p, fact = field.parameters, field.facts['philtrum']
    _, _, _, width = G.frame(field.source_landmarks)
    area = (fact['central_gap_axis_max_px'] - fact['central_gap_axis_min_px']) * p[6]
    for axis in ('upper_negative_axis', 'upper_positive_axis', 'lower_negative_axis', 'lower_positive_axis'):
        count = fact['central_gap_' + axis + '_skin_rgb_px']
        assert count >= max(4., .04 * area)
    assert p[6] < .08 * width  # A copied middle-third min-height would refuse this fixture.


def test_lip_skin_exemption_never_skips_actual_lip_rgb_or_occlusion(monkeypatch):
    def change(lm, source, skin, excluded, blank=False):
        yy, xx = np.mgrid[:skin.shape[0], :skin.shape[1]]
        points = np.column_stack((xx.ravel(), yy.ravel()))
        selected = G.polygon_inside(points, G.pixels(lm, skin.shape)[list(G.LIPS)])
        skin.ravel()[selected] = 0.
        if blank: source.reshape(-1, 3)[selected] = .5
    field, *_ = _build(monkeypatch, mutate=change)
    assert field.facts['philtrum']['lip_support_px'] > 0
    with pytest.raises(ValueError, match='source lips skin/RGB'):
        _build(monkeypatch, mutate=lambda *args: change(*args, blank=True))


def test_every_moving_oval_segment_uses_actual_source_endpoints(monkeypatch):
    seen = []
    original = R._moving_segment_support
    def record(a, b, *args):
        seen.append((a.copy(), b.copy()))
        return original(a, b, *args)
    monkeypatch.setattr(R, '_moving_segment_support', record)
    field, *_ = _build(monkeypatch)
    p, oval = field.parameters, field.source_landmarks[list(G.FACE_OVAL)]
    v = (oval - p[:2]) @ p[4:6]
    expected = [(a, b) for i, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0)))
                if max(v[i], v[(i + 1) % len(oval)]) > 0.]
    np.testing.assert_array_equal(np.asarray(seen), np.asarray(expected))
    assert len(seen) == field.facts['philtrum']['boundary_segments']


def test_moving_strip_ignores_untouched_upper_evidence_but_requires_moving_pixels():
    _, source, skin, excluded = _fixture()
    oval = np.array([[100., 150.], [300., 150.], [300., 320.], [100., 320.]])
    a, b, center = np.array([100., 200.]), np.array([100., 260.]), np.array([200., 230.])
    origin, right, down = np.array([200., 230.]), np.array([1., 0.]), np.array([0., 1.])
    # This explicit synthetic segment crosses the fixed plane. No evidence
    # above it should substitute for, or unnecessarily veto, the moving strip.
    skin[:231] = 0.
    excluded[:231] = 1.
    source[:231] = .5
    args = (a, b, center, 160., oval, source, skin, excluded,
            origin, right, down, 10., 120., 6., 2.5)
    assert R._moving_segment_support(*args) >= 12
    skin[231:260, 101:112] = 0.
    with pytest.raises(ValueError, match='moving-oval strip'):
        R._moving_segment_support(*args)


@pytest.mark.parametrize('scale', [0., .5, -1.])
@pytest.mark.parametrize('amount', [.5, -.5, 1e-10, -1e-10])
def test_zero_hidden_gain_cut_and_wrong_sign_never_report_applied(monkeypatch, scale, amount):
    lm, source, skin, excluded = _fixture()
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    before = tuple(value.copy() for value in (lm, source, skin, excluded))
    monkeypatch.setattr(R, 'native_evaluate', lambda q, p: _native_double(q, p) * scale)
    with pytest.raises(ValueError, match='full requested amount'):
        R.build(lm, _recipe(amount), source, excluded, backend='mediapipe', analysis=observation)
    for current, original in zip((lm, source, skin, excluded), before):
        np.testing.assert_array_equal(current, original)


def test_nonrepresentable_amount_refuses_without_gain_inflation(monkeypatch):
    lm, source, skin, excluded = _fixture()
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('lost precision reached native'))
    with pytest.raises(ValueError, match='representable'):
        R.build(lm, _recipe(1e-300), source, excluded, backend='mediapipe', analysis=observation)


@pytest.mark.parametrize('landmark', [275, 0, 13, 14, 152, 164])
def test_full_target_audit_refuses_fabricated_or_independently_pinned_targets(monkeypatch, landmark):
    field, *_ = _build(monkeypatch)
    target = field.target_landmarks.copy()
    target[landmark] += [0., .001]
    with pytest.raises(ValueError, match='full requested forward operation'):
        R.PhiltrumField(field.parameters.copy(), field.source_landmarks.copy(), target,
                        field.shape, field.facts['philtrum'])


def test_direct_constructor_cannot_shift_planes_or_shrink_source_plateau(monkeypatch):
    field, *_ = _build(monkeypatch)
    for index in (0, 1, 6, 7, 8, 9):
        params = field.parameters.copy()
        params[index] += .01
        if index == 9: params[10] = max(.25, .5 * (params[9] - 1.))
        target = field.source_landmarks + _forward(field.source_landmarks, params)
        with pytest.raises(ValueError, match='retained-source measured gap policy'):
            R.PhiltrumField(params, field.source_landmarks.copy(), target,
                            field.shape, field.facts['philtrum'])


def test_canonical_source_ownership_rejects_forgery_and_ignores_unauthenticated_precision(monkeypatch):
    field, lm, source, observation = _build(monkeypatch)
    precise = observation['landmarks'].astype(np.float64) + 1e-11
    other = R.build(precise, _recipe(), source, observation['excluded'], backend='mediapipe',
                    analysis={**observation, 'landmarks': precise})
    np.testing.assert_array_equal(other.parameters, field.parameters)
    np.testing.assert_array_equal(other.source_landmarks, field.source_landmarks)
    forged = deepcopy(observation)
    forged['landmarks'][275, 0] += .001
    with pytest.raises(ValueError, match='exact retained'):
        R.build(lm, _recipe(), source, observation['excluded'], backend='mediapipe', analysis=forged)
    wrong = observation['excluded'].copy(); wrong[0, 0] = 1.
    with pytest.raises(ValueError, match='retained same-source'):
        R.build(lm, _recipe(), source, wrong, backend='mediapipe', analysis=observation)


@pytest.mark.parametrize('location', ['lateral_feather', 'below_chin_tail', 'rectangle_corner', 'centerline'])
def test_complete_influence_rectangle_protects_every_retained_foreign_face(monkeypatch, location):
    field, _, source, _ = _build(monkeypatch)
    p = field.parameters
    x, y = {'lateral_feather': (.5 * (p[7] + p[8]), .5 * p[6]),
            'below_chin_tail': (0., (p[9] + .5 * p[10]) * p[6]),
            'rectangle_corner': (p[8] - .1, (p[9] + p[10]) * p[6] - .1),
            'centerline': (0., .5 * p[6])}[location]
    point = p[:2] + x * p[2:4] + y * p[4:6]
    # Explicit component scaling, not assumed square frames.
    box = tuple(np.r_[point - .1, point + .1] /
                [source.shape[1] - 1, source.shape[0] - 1, source.shape[1] - 1, source.shape[0] - 1])
    with pytest.raises(ValueError, match='another retained face'):
        _build(monkeypatch, protected_boxes=(box,))


def test_complete_source_frame_margin_refuses_without_clipping_tail(monkeypatch):
    def shift_down(lm, *rest): lm[:, 1] += .15
    with pytest.raises(ValueError, match='complete influence bounding box'):
        _build(monkeypatch, mutate=shift_down)


def test_stable_forward_feather_keeps_strict_interior_and_is_not_used_as_inverse():
    p = np.array([0., 0., 1., 0., 0., 1., 20., 50., 100., 6., 2.5, 1.])
    near = np.array([[100. - 1e-6, (6. + 2.5) * 20. - 1e-6]])
    assert R._forward_delta(near, p)[0, 1] > 0.
    query = np.array([[0., 10.]])
    assert not np.array_equal(R._forward_delta(query, p), _native_double(query, p))


def test_parameters_targets_and_facts_are_immutable_owned_snapshots(monkeypatch):
    field, *_ = _build(monkeypatch)
    for value in (field.state, field.parameters, field.source_landmarks, field.target_landmarks):
        assert not value.flags.writeable
        with pytest.raises(ValueError): value.setflags(write=True)
    with pytest.raises(FrozenInstanceError): field.state = np.zeros(12)
    facts = field.facts; facts['philtrum']['amount'] = 0.
    assert field.facts['philtrum']['amount'] == .5
    assert field.resident_bytes() >= sum(value.nbytes for value in
        (field.parameters, field.source_landmarks, field.target_landmarks))


def test_query_and_source_evidence_batches_are_bounded(monkeypatch):
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
def test_bad_queries_never_reach_native(monkeypatch, bad):
    field, *_ = _build(monkeypatch)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('bad query reached native'))
    with pytest.raises(ValueError): field.evaluate(bad)


@pytest.mark.parametrize('kind', ['float32', 'shape', 'nan', 'list'])
def test_bad_native_output_refuses_without_conversion_or_partial_publish(monkeypatch, kind):
    field, *_ = _build(monkeypatch)
    def malformed(points, parameters):
        if kind == 'float32': return np.zeros(points.shape, np.float32)
        if kind == 'shape': return np.zeros((len(points), 3), np.float64)
        if kind == 'nan': return np.full(points.shape, np.nan, np.float64)
        return [[0., 0.] for _ in points]
    monkeypatch.setattr(R, 'native_evaluate', malformed)
    with pytest.raises(ValueError, match='finite float64 output contract'):
        field.evaluate(np.array([[220., 280.]]))


def test_no_other_operation_build_or_python_inverse_fallback(monkeypatch):
    from lumaretouch_engine import chin_length_runtime, chin_shape_runtime, lower_face_runtime
    from lumaretouch_engine import face_size_runtime, mid_face_runtime
    def forbidden(*args, **kwargs): pytest.fail('philtrum invoked another operation builder')
    for runtime in (chin_length_runtime, chin_shape_runtime, lower_face_runtime, face_size_runtime, mid_face_runtime):
        monkeypatch.setattr(runtime, 'build', forbidden)
    field, *_ = _build(monkeypatch)
    assert field.facts['philtrum']['applied']
    def unavailable(*args): raise RuntimeError('synthetic unavailable Rust primitive')
    monkeypatch.setattr(R, 'native_evaluate', unavailable)
    with pytest.raises(RuntimeError, match='unavailable Rust'):
        field.evaluate(np.array([[220., 280.]]))


class _SyntheticField:
    """Composition/footprint double, not anatomy or a native implementation."""
    state = ('synthetic',)
    def __init__(self, function, resident=32): self.function, self.resident = function, resident
    def evaluate(self, points): return self.function(points)
    def resident_bytes(self): return self.resident


class _MetadataPrefix(FaceGeometry):
    def resident_bytes(self): return super().resident_bytes() + 819


def test_prefix_four_through_ten_keeps_mouth_slot_three_metadata_and_pullback_order():
    zero = _SyntheticField(lambda q: np.zeros_like(q), resident=17)
    mouth = _SyntheticField(lambda q: q * [.01, .02], resident=41)
    for count in (4, 5, 6, 7, 8, 9, 10):
        fields = (None, None, None, mouth) + (zero,) * (count - 4)
        prefix = _MetadataPrefix('synthetic', (401, 401), zero, fields)
        gap = _SyntheticField(lambda q: np.tile([0., 2.], (len(q), 1)), resident=83)
        wrapper = PORT.Philtrum('synthetic', (401, 401), zero, (*fields, gap), prefix, ())
        q = np.array([[190., 240.], [210., 260.]])
        expected = gap.evaluate(q) + prefix.evaluate(q - gap.evaluate(q))
        np.testing.assert_array_equal(wrapper.evaluate(q), expected)
        assert wrapper.prefix is prefix and wrapper.fields[3] is mouth
        assert all(a is b for a, b in zip(wrapper.fields[:-1], fields))
        assert wrapper.resident_bytes() == prefix.resident_bytes() + 83 + 256


@pytest.mark.parametrize('stage', ['output', 'intermediate', 'final'])
def test_output_intermediate_final_foreign_footprints_are_guarded(stage):
    q = np.array([[150., 200.]])
    gap = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    position = {'output': [150., 200.], 'intermediate': [150., 190.], 'final': [150., 180.]}[stage]
    box = tuple(np.r_[np.asarray(position) - .1, np.asarray(position) + .1] / 400.)
    wrapper = PORT.Philtrum('synthetic', (401, 401), prior, (*prefix.fields, gap), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)


def test_cancellation_cannot_hide_foreign_intermediate_or_invalid_source_margin():
    q = np.array([[150., 200.]])
    gap = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., -10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    box = (149.9 / 400., 189.9 / 400., 150.1 / 400., 190.1 / 400.)
    wrapper = PORT.Philtrum('synthetic', (401, 401), prior, (*prefix.fields, gap), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)
    zero = _SyntheticField(lambda p: np.zeros_like(p))
    prefix = FaceGeometry('synthetic', (401, 401), zero, (None,) * 4)
    huge = _SyntheticField(lambda p: np.tile([0., 250.], (len(p), 1)))
    wrapper = PORT.Philtrum('synthetic', (401, 401), zero, (*prefix.fields, huge), prefix, ())
    with pytest.raises(ValueError, match='genuine source margin'): wrapper.evaluate(q)


def test_failed_composition_preserves_prefix_fields_and_queries():
    q = np.array([[150., 200.]])
    before = q.copy()
    zero = _SyntheticField(lambda p: np.zeros_like(p))
    mouth = _SyntheticField(lambda p: p * [.01, .02])
    prefix = _MetadataPrefix('synthetic', (401, 401), zero, (None, None, None, mouth))
    original = prefix.evaluate(q).copy()
    bad = _SyntheticField(lambda p: np.full_like(p, np.nan))
    wrapper = PORT.Philtrum('synthetic', (401, 401), zero, (*prefix.fields, bad), prefix, ())
    with pytest.raises(ValueError, match='invalid philtrum pullback'): wrapper.evaluate(q)
    np.testing.assert_array_equal(q, before)
    np.testing.assert_array_equal(prefix.evaluate(q), original)
    assert prefix.fields == (None, None, None, mouth) and wrapper.fields[3] is mouth
