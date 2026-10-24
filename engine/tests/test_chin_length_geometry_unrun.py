# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN below-lip chin-length geometry/source contracts.

All coordinates, RGB, semantic observations and field doubles are explicitly
synthetic. The independent bisection below is TEST ONLY, not a runtime inverse
or execution of the reused Rust primitive. These fixtures do not establish real
anatomy, segmentation, native loading, photographic acceptance or parity.
No imports, collection, execution, numerical probes, builds, inference, downloads,
installation or type checks ran while authoring this file.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from test_chin_shape_geometry_unrun import _fixture
from test_face_contour_geometry_unrun import _analysis
from lumaretouch_engine import face_contour_geometry as G
from lumaretouch_engine import chin_length_runtime as R, chin_length_state as S
from lumaretouch_engine import chin_length_people as PORT
from lumaretouch_engine.people_geometry import FaceGeometry


def _recipe(amount=.5):
    return S.check({'version': 1, 'amount': amount})


def _smooth(value):
    t = np.clip(value, 0., 1.)
    z = np.minimum(t, 1. - t)
    low = z * z * z * (10. + z * (6. * z - 15.))
    return np.where(t <= .5, low, 1. - low)


def _vertical(t, tail=.5):
    out = np.zeros_like(t)
    rising, falling = (t > 0.) & (t <= 1.), (t > 1.) & (t < 1. + tail)
    out[rising] = _smooth(t[rising])
    out[falling] = _smooth((1. + tail - t[falling]) / tail)
    return out


def _forward(points, parameters):
    local = points - parameters[:2]
    u, t = local @ parameters[2:4], (local @ parameters[4:6]) / parameters[6]
    height, inner, outer, tail, amount = parameters[6:]
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    distance = ((.08 * height) * amount) * lateral * _vertical(t, tail)
    return distance[:, None] * parameters[4:6]


def _native_double(points, parameters):
    """Independent TEST-ONLY displacement bisection, not a production fallback."""
    origin, right, down = parameters[:2], parameters[2:4], parameters[4:6]
    height, inner, outer, tail, amount = parameters[6:]
    local = points - origin
    u, t = local @ right, (local @ down) / height
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    amplitude = ((.08 * height) * amount) * lateral
    active = (np.abs(u) < outer) & (t > 0.) & (t < 1. + tail)
    low, high = np.minimum(amplitude, 0.), np.maximum(amplitude, 0.)
    for _ in range(96):
        middle = low + .5 * (high - low)
        residual = middle - amplitude * _vertical(t - middle / height, tail)
        high = np.where(residual > 0., middle, high)
        low = np.where(residual <= 0., middle, low)
    distance = np.where(active, low + .5 * (high - low), 0.)
    return np.ascontiguousarray(distance[:, None] * down)


def _build(monkeypatch, amount=.5, *, protected_boxes=(), mutate=None):
    lm, source, skin, excluded = _fixture()
    if mutate is not None:
        mutate(lm, source, skin, excluded)
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', _native_double)
    field = R.build(lm, _recipe(amount), source, excluded, backend='mediapipe',
                    analysis=observation, protected_boxes=protected_boxes)
    return field, lm, source, observation


def test_neutral_skips_all_source_legacy_native_work_and_preserves_old_field(monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('neutral inspected an unrelated input')
    for name in ('_source', 'require_analysis', 'native_evaluate'):
        monkeypatch.setattr(R, name, forbidden)
    monkeypatch.setattr(S, 'check_coexistence', forbidden)
    assert R.build(None, S.neutral(), None, None, backend='unavailable', analysis=None) is None
    legacy_field = object()
    for old_amount in (1., -.7, object()):
        out, facts = PORT.append(legacy_field, None, None, None, None, S.neutral(), legacy_amount=old_amount)
        assert out is legacy_field and facts is None


@pytest.mark.parametrize('amount', [-1., .5, 1.])
@pytest.mark.parametrize('legacy', [-1., -.2, .2, 1.])
def test_active_old_new_coexistence_refuses_before_any_source_or_prefix_read(monkeypatch, amount, legacy):
    def forbidden(*args, **kwargs): pytest.fail('conflict reached source identity or geometry')
    monkeypatch.setattr(PORT.P, 'check_ref', forbidden)
    monkeypatch.setattr(R, 'build', forbidden)
    recipe = _recipe(amount)
    before = deepcopy(recipe)
    legacy_field = object()
    with pytest.raises(ValueError):
        PORT.append(legacy_field, None, None, None, None, recipe, legacy_amount=legacy)
    assert recipe == before


def test_complete_true_lower_arc_not_cheek_or_upper_oval_and_all_forty_lips():
    assert R.LOWER_ARC == (150, 149, 176, 148, 152, 377, 400, 378, 379)
    edges = {frozenset((a, b)) for a, b in zip(G.FACE_OVAL, (*G.FACE_OVAL[1:], G.FACE_OVAL[0]))}
    assert all(frozenset(edge) in edges for edge in zip(R.LOWER_ARC, R.LOWER_ARC[1:]))
    assert not set(R.LOWER_ARC).intersection((10, 21, 251, 234, 454, 93, 323))
    assert len(R.LIP_VERTICES) == 40
    assert set(G.LIPS).issubset(R.LIP_VERTICES) and set(R.INNER_LIPS).issubset(R.LIP_VERTICES)
    assert not set(R.LOWER_ARC).intersection(R.LIP_VERTICES)


@pytest.mark.parametrize('amount', [1., -1., .4, -.4, 1e-10, -1e-10])
def test_signed_length_moves_actual_tip_and_full_lower_arc_not_width_lips_or_upper_plane(monkeypatch, amount):
    field, lm, source, _ = _build(monkeypatch, amount)
    measured, p = G.pixels(lm, source.shape[:2]), field.parameters
    expected = _forward(measured, p)
    np.testing.assert_allclose(field.target_landmarks, measured + expected, rtol=0., atol=3e-12)
    np.testing.assert_allclose(field.evaluate(field.target_landmarks), expected, rtol=1e-8, atol=3e-12)
    np.testing.assert_allclose(field.target_landmarks - field.evaluate(field.target_landmarks), measured,
                               rtol=0., atol=3e-12)
    before, after = measured - p[:2], field.target_landmarks - p[:2]
    np.testing.assert_allclose(after @ p[2:4], before @ p[2:4], rtol=0., atol=3e-12)
    np.testing.assert_array_equal(field.target_landmarks[list(R.LIP_VERTICES)], measured[list(R.LIP_VERTICES)])
    upper = before @ p[4:6] <= 0.
    np.testing.assert_array_equal(field.target_landmarks[upper], measured[upper])
    assert np.all(before[list(R.LIP_VERTICES)] @ p[4:6] < 0.)
    changes = (field.target_landmarks - measured) @ p[4:6]
    assert np.all(changes[list(R.LOWER_ARC)] * amount > 0.)
    assert changes[152] == pytest.approx((.08 * p[6]) * amount, rel=2e-4, abs=3e-14)
    fact = field.facts['chin_length']
    assert fact['requirement_id'] == S.CONTROL_ID == 'LNX-REF-PC-32466-C-44a42baef4'
    assert fact['audited_retained_landmarks'] == 478 and fact['protected_lip_vertices'] == 40
    assert fact['gain'] == S.LENGTH_GAIN == .08 and fact['tail_ratio'] == S.TAIL == .5
    assert fact['minimum_forward_vertical_slope_bound'] >= .7
    assert fact['maximum_forward_vertical_slope_bound'] <= 1.3
    assert fact['lower_arc_probe_count'] == 9 and fact['actual_tip_index'] == 152
    assert 'lower_face_native' in fact['method']
    assert 'prior_edited_points_can_enter_feather' in fact['limitation']


def test_plane_uses_every_actual_outer_and_inner_lip_and_actual_tip_lateral_axis(monkeypatch):
    field, *_ = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    _, _, _, width = G.frame(lm)
    expected = float(np.max(lm[list(R.LIP_VERTICES)] @ p[4:6])) + max(1., .01 * width)
    assert float(p[:2] @ p[4:6]) == pytest.approx(expected, abs=3e-12)
    assert float((lm[152] - p[:2]) @ p[2:4]) == pytest.approx(0., abs=3e-12)
    assert float((lm[152] - p[:2]) @ p[4:6]) == pytest.approx(p[6], abs=3e-12)
    assert p[8] - p[7] == pytest.approx(.25 * width)
    assert p[9] == .5


def test_closed_inner_lips_need_no_invented_opening(monkeypatch):
    def close(lm, *rest): lm[list(R.INNER_LIPS), 1] = .62
    field, *_ = _build(monkeypatch, mutate=close)
    np.testing.assert_array_equal(field.target_landmarks[list(R.INNER_LIPS)],
                                  field.source_landmarks[list(R.INNER_LIPS)])
    np.testing.assert_array_equal(field.source_landmarks[13], field.source_landmarks[14])


@pytest.mark.parametrize('mode', ['collapsed_band', 'inverted_arc', 'omitted_neighbor',
                                  'wrong_tip', 'inner_lip_outside', 'outside_oval', 'lip_order'])
def test_unmeasured_or_invalid_anatomy_refuses_without_repair(monkeypatch, mode):
    lm, source, skin, excluded = _fixture()
    if mode == 'collapsed_band': lm[list(G.LIPS), 1] += .12
    elif mode == 'inverted_arc': lm[149, :2], lm[150, :2] = lm[150, :2].copy(), lm[149, :2].copy()
    elif mode == 'omitted_neighbor': lm[176, :2] = lm[148, :2]
    elif mode == 'wrong_tip': lm[152, 0] += .12
    elif mode == 'inner_lip_outside': lm[402, :2] = [.5, .72]
    elif mode == 'outside_oval': lm[100, :2] = [.05, .05]
    else: lm[13, 1], lm[14, 1] = lm[14, 1], lm[13, 1]
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('invalid geometry reached native'))
    with pytest.raises(ValueError):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=observation)


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


@pytest.mark.parametrize('sector', range(4))
@pytest.mark.parametrize('loss', ['skin', 'rgb', 'variance'])
def test_each_below_lip_sector_requires_independent_actual_source_evidence(monkeypatch, sector, loss):
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
    with pytest.raises(ValueError, match='all lower-chin sectors'):
        R._chin_support(lm, center, p[:2], p[2:4], p[4:6], p[6], width,
                        source, skin, observation['excluded'], p[8])


@pytest.mark.parametrize('landmark', R.LOWER_ARC)
def test_each_true_lower_arc_probe_requires_local_rgb_not_sector_average(monkeypatch, landmark):
    field, _, source, observation = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    _, _, center, width = G.frame(lm)
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    points = np.column_stack((xx.ravel(), yy.ravel()))
    selected = np.linalg.norm(points - lm[landmark], axis=1) <= max(3., .025 * width)
    source.reshape(-1, 3)[selected] = .5
    with pytest.raises(ValueError, match='actual measured lower-arc vertices'):
        R._chin_support(lm, center, p[:2], p[2:4], p[4:6], p[6], width,
                        source, observation['face_skin'], observation['excluded'], p[8])


@pytest.mark.parametrize('landmark', [148, 152, 377, 14])
def test_occluder_veto_includes_moving_centerline_tip_and_fixed_lips(monkeypatch, landmark):
    def occlude(lm, source, skin, excluded):
        point = lm[landmark, :2] * [source.shape[1] - 1, source.shape[0] - 1]
        if landmark != 14: point[1] -= 2.
        x, y = np.rint(point).astype(int)
        excluded[y, x] = 1.
    with pytest.raises(ValueError, match='occluder'):
        _build(monkeypatch, mutate=occlude)


def test_lip_skin_exemption_is_not_an_rgb_or_occlusion_exemption(monkeypatch):
    def change(lm, source, skin, excluded, blank=False):
        yy, xx = np.mgrid[:skin.shape[0], :skin.shape[1]]
        points = np.column_stack((xx.ravel(), yy.ravel()))
        selected = G.polygon_inside(points, G.pixels(lm, skin.shape)[list(G.LIPS)])
        skin.ravel()[selected] = 0.
        if blank: source.reshape(-1, 3)[selected] = .5
    field, *_ = _build(monkeypatch, mutate=change)
    assert field.facts['chin_length']['lower_lip_rgb_px'] > 0
    with pytest.raises(ValueError, match='lower-lip RGB'):
        _build(monkeypatch, mutate=lambda *args: change(*args, blank=True))


def test_every_moving_oval_segment_uses_actual_endpoints_not_synthetic_jaw(monkeypatch):
    seen = []
    original = R._chin_segment_support
    def record(a, b, *args):
        seen.append((a.copy(), b.copy()))
        return original(a, b, *args)
    monkeypatch.setattr(R, '_chin_segment_support', record)
    field, *_ = _build(monkeypatch)
    p, oval = field.parameters, field.source_landmarks[list(G.FACE_OVAL)]
    v = (oval - p[:2]) @ p[4:6]
    expected = [(a, b) for i, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0)))
                if max(v[i], v[(i + 1) % len(oval)]) > 0.]
    np.testing.assert_array_equal(np.asarray(seen), np.asarray(expected))
    assert len(seen) == field.facts['chin_length']['boundary_segments']


@pytest.mark.parametrize('scale', [0., .5, -1.])
def test_native_zero_attenuation_and_wrong_sign_cannot_report_applied(monkeypatch, scale):
    lm, source, skin, excluded = _fixture()
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    before = tuple(value.copy() for value in (lm, source, skin, excluded))
    recipe = _recipe()
    monkeypatch.setattr(R, 'native_evaluate', lambda q, p: _native_double(q, p) * scale)
    with pytest.raises(ValueError, match='full requested amount'):
        R.build(lm, recipe, source, excluded, backend='mediapipe', analysis=observation)
    for current, original in zip((lm, source, skin, excluded), before):
        np.testing.assert_array_equal(current, original)
    assert recipe == _recipe()


def test_nonrepresentable_amount_refuses_without_gain_inflation_or_partial_result(monkeypatch):
    lm, source, skin, excluded = _fixture()
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('lost precision reached native'))
    with pytest.raises(ValueError, match='representable'):
        R.build(lm, _recipe(1e-300), source, excluded, backend='mediapipe', analysis=observation)


def test_full_target_audit_refuses_fabricated_or_snapped_actual_tip(monkeypatch):
    field, *_ = _build(monkeypatch)
    target = field.target_landmarks.copy()
    target[152] = field.source_landmarks[152]
    with pytest.raises(ValueError, match='full requested forward operation'):
        R.ChinLengthField(field.parameters.copy(), field.source_landmarks.copy(), target,
                          field.shape, field.facts['chin_length'])


def test_canonical_source_ownership_rejects_forgery_and_ignores_unauthenticated_precision(monkeypatch):
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


@pytest.mark.parametrize('location', ['lateral_feather', 'below_tip_feather', 'rectangle_corner', 'centerline'])
def test_complete_support_rectangle_protects_every_other_retained_face(monkeypatch, location):
    field, _, source, _ = _build(monkeypatch)
    p = field.parameters
    x, y = {'lateral_feather': (.5 * (p[7] + p[8]), .5 * p[6]),
            'below_tip_feather': (.5 * p[7], 1.25 * p[6]),
            'rectangle_corner': (p[8] - .1, 1.5 * p[6] - .1),
            'centerline': (0., p[6])}[location]
    point = p[:2] + x * p[2:4] + y * p[4:6]
    h, w = source.shape[:2]
    box = np.r_[point - .25, point + .25] / [w - 1, h - 1, w - 1, h - 1]
    with pytest.raises(ValueError, match='another retained face'):
        _build(monkeypatch, protected_boxes=[box])


@pytest.mark.parametrize('axis,offset', [(0, .28), (1, .18)])
def test_full_support_cannot_be_clipped_or_strength_silently_reduced(monkeypatch, axis, offset):
    def shift(lm, *rest): lm[:, axis] += offset
    with pytest.raises(ValueError, match='complete influence bounding box'):
        _build(monkeypatch, mutate=shift)


def test_roll_mirror_scale_and_tip_translation_follow_measured_head_axes(monkeypatch):
    field, lm, source, observation = _build(monkeypatch, .7)
    angle = .12
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    for transform, scale in ((rotation, 1.), (np.diag([-1., 1.]), 1.), (np.eye(2), .9)):
        changed = lm.copy()
        changed[:, :2] = ((lm[:, :2].astype(np.float64) - .5) @ transform.T * scale + .5).astype(np.float32)
        changed_observation = _analysis(changed, source.shape[:2], observation['face_skin'], observation['excluded'])
        other = R.build(changed, _recipe(.7), source, observation['excluded'],
                        backend='mediapipe', analysis=changed_observation)
        np.testing.assert_allclose(other.parameters[2:4], transform @ field.parameters[2:4], atol=2e-6)
        np.testing.assert_allclose(other.parameters[4:6], transform @ field.parameters[4:6], atol=2e-6)
        transformed = (field.target_landmarks - 200.) @ transform.T * scale + 200.
        np.testing.assert_allclose(other.target_landmarks, transformed, rtol=0., atol=8e-5)


def test_centerline_moves_but_upper_plane_and_complete_support_edges_are_identity(monkeypatch):
    field, *_ = _build(monkeypatch)
    p = field.parameters
    local = np.array([[0., 0.], [p[7], -.1], [p[8], p[6]], [p[7], 1.5 * p[6]],
                      [0., p[6]], [.5 * (p[7] + p[8]), p[6]], [0., 1.25 * p[6]]])
    points = p[:2] + local[:, :1] * p[2:4] + local[:, 1:] * p[4:6]
    delta = field.evaluate(points)
    np.testing.assert_array_equal(delta[:4], np.zeros((4, 2)))
    assert np.all(np.linalg.norm(delta[4:], axis=1) > 0.)
    np.testing.assert_allclose(delta @ p[2:4], 0., rtol=0., atol=1e-12)


@pytest.mark.parametrize('amount', [-1., 1.])
def test_tip_and_feather_join_inverse_uses_recovered_source_height(monkeypatch, amount):
    field, *_ = _build(monkeypatch, amount)
    p = field.parameters
    t = np.array([.5, 1. - 1e-8, 1., 1. + 1e-8, 1.25, 1.5 - 1e-6])
    measured = p[:2] + (t * p[6])[:, None] * p[4:6]
    expected = _forward(measured, p)
    target = measured + expected
    np.testing.assert_allclose(field.evaluate(target), expected, rtol=1e-8, atol=1e-12)
    np.testing.assert_allclose(target - field.evaluate(target), measured, rtol=0., atol=3e-12)


def test_forward_zero_edge_is_stable_and_never_used_as_query_pullback():
    p = np.array([0., 0., 1., 0., 0., 1., 100., 50., 100., .5, 1.])
    delta = R._forward_delta(np.array([[100. - 1e-6, 150. - 1e-6]]), p)
    assert delta[0, 0] == 0. and delta[0, 1] > 0.
    query = np.array([[0., 105.]])
    assert not np.array_equal(R._forward_delta(query, p), _native_double(query, p))


def test_parameters_landmarks_and_facts_are_immutable_owned_snapshots(monkeypatch):
    field, *_ = _build(monkeypatch)
    for value in (field.state, field.parameters, field.source_landmarks, field.target_landmarks):
        assert not value.flags.writeable
        with pytest.raises(ValueError): value.setflags(write=True)
    with pytest.raises(FrozenInstanceError): field.state = np.zeros(11)
    facts = field.facts; facts['chin_length']['amount'] = 0.
    assert field.facts['chin_length']['amount'] == .5
    assert field.resident_bytes() >= sum(value.nbytes for value in
        (field.parameters, field.source_landmarks, field.target_landmarks))


def test_query_and_evidence_batches_remain_bounded(monkeypatch):
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
def test_bad_native_outputs_refuse_without_conversion_or_publish(monkeypatch, kind):
    field, *_ = _build(monkeypatch)
    def malformed(points, parameters):
        if kind == 'float32': return np.zeros(points.shape, np.float32)
        if kind == 'shape': return np.zeros((len(points), 3), np.float64)
        if kind == 'nan': return np.full(points.shape, np.nan, np.float64)
        return [[0., 0.] for _ in points]
    monkeypatch.setattr(R, 'native_evaluate', malformed)
    with pytest.raises(ValueError, match='finite float64 output contract'):
        field.evaluate(np.array([[220., 280.]]))


def test_no_other_control_build_or_unrelated_native_is_used(monkeypatch):
    from lumaretouch_engine import chin_shape_native, face_size_native, mid_face_native
    from lumaretouch_engine import chin_shape_runtime, lower_face_runtime, face_size_runtime, mid_face_runtime
    def forbidden(*args, **kwargs): pytest.fail('chin length invoked another control instead of shared primitive')
    for native in (chin_shape_native, face_size_native, mid_face_native):
        monkeypatch.setattr(native, 'native', forbidden)
    for runtime in (chin_shape_runtime, lower_face_runtime, face_size_runtime, mid_face_runtime):
        monkeypatch.setattr(runtime, 'build', forbidden)
    field, *_ = _build(monkeypatch)
    assert field.facts['chin_length']['applied']


class _SyntheticField:
    """Composition/footprint double, not anatomy or a native implementation."""
    state = ('synthetic',)
    def __init__(self, function, resident=32): self.function, self.resident = function, resident
    def evaluate(self, points): return self.function(points)
    def resident_bytes(self): return self.resident


class _MetadataPrefix(FaceGeometry):
    def resident_bytes(self): return super().resident_bytes() + 819


def test_prefix_four_through_nine_preserves_mouth_slot_metadata_and_pullback_order():
    zero = _SyntheticField(lambda q: np.zeros_like(q), resident=17)
    mouth = _SyntheticField(lambda q: q * [.01, .02], resident=41)
    for count in (4, 5, 6, 7, 8, 9):
        fields = (None, None, None, mouth) + (zero,) * (count - 4)
        prefix = _MetadataPrefix('synthetic', (401, 401), zero, fields)
        chin = _SyntheticField(lambda q: np.tile([0., 2.], (len(q), 1)), resident=83)
        wrapper = PORT.ChinLength('synthetic', (401, 401), zero, (*fields, chin), prefix, ())
        q = np.array([[190., 240.], [210., 260.]])
        expected = chin.evaluate(q) + prefix.evaluate(q - chin.evaluate(q))
        np.testing.assert_array_equal(wrapper.evaluate(q), expected)
        assert wrapper.prefix is prefix and wrapper.fields[3] is mouth
        assert all(a is b for a, b in zip(wrapper.fields[:-1], fields))
        assert wrapper.resident_bytes() == prefix.resident_bytes() + 83 + 256


@pytest.mark.parametrize('stage', ['output', 'intermediate', 'final'])
def test_output_intermediate_final_foreign_footprints_are_guarded(stage):
    q = np.array([[150., 200.]])
    chin = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    position = {'output': [150., 200.], 'intermediate': [150., 190.], 'final': [150., 180.]}[stage]
    box = tuple(np.r_[np.asarray(position) - .1, np.asarray(position) + .1] / 400.)
    wrapper = PORT.ChinLength('synthetic', (401, 401), prior, (*prefix.fields, chin), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)


def test_cancellation_cannot_hide_foreign_intermediate_or_bad_source_margin():
    q = np.array([[150., 200.]])
    chin = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., -10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    box = (149.9 / 400., 189.9 / 400., 150.1 / 400., 190.1 / 400.)
    wrapper = PORT.ChinLength('synthetic', (401, 401), prior, (*prefix.fields, chin), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)
    zero = _SyntheticField(lambda p: np.zeros_like(p))
    prefix = FaceGeometry('synthetic', (401, 401), zero, (None,) * 4)
    huge = _SyntheticField(lambda p: np.tile([0., 250.], (len(p), 1)))
    wrapper = PORT.ChinLength('synthetic', (401, 401), zero, (*prefix.fields, huge), prefix, ())
    with pytest.raises(ValueError, match='genuine source margin'): wrapper.evaluate(q)


def test_failed_composed_request_preserves_prefix_fields_and_query_array():
    q = np.array([[150., 200.]])
    before = q.copy()
    zero = _SyntheticField(lambda p: np.zeros_like(p))
    mouth = _SyntheticField(lambda p: p * [.01, .02])
    prefix = _MetadataPrefix('synthetic', (401, 401), zero, (None, None, None, mouth))
    original = prefix.evaluate(q).copy()
    bad = _SyntheticField(lambda p: np.full_like(p, np.nan))
    wrapper = PORT.ChinLength('synthetic', (401, 401), zero, (*prefix.fields, bad), prefix, ())
    with pytest.raises(ValueError, match='invalid chin pullback'): wrapper.evaluate(q)
    np.testing.assert_array_equal(q, before)
    np.testing.assert_array_equal(prefix.evaluate(q), original)
    assert prefix.fields == (None, None, None, mouth) and wrapper.fields[3] is mouth
