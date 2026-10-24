# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN measured mid-face contracts, not photographic acceptance.

All geometry, RGB, masks and observations are explicit synthetic doubles. The
independent forward/bisection oracles are TEST ONLY, never product fallbacks.
These fixtures do not prove real anatomy, segmentation, installed native ABI,
quality, or reference-product parity. No imports, collection, test execution,
inference, builds, type checks or downloads ran while authoring this file.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from test_lower_face_geometry_unrun import _fixture as _lower_fixture
from test_face_contour_geometry_unrun import _analysis
from lumaretouch_engine import face_contour_geometry as G
from lumaretouch_engine import mid_face_runtime as R, mid_face_state as S
from lumaretouch_engine import mid_face_people as PORT
from lumaretouch_engine.people_geometry import FaceGeometry


def _fixture():
    """Explicitly synthetic surface ordering, not a template for product use."""
    lm, source, skin, excluded = _lower_fixture()
    for upper, lower, neighbor, x, nx in ((117, 50, 118, .42, .405),
                                         (346, 280, 347, .58, .595)):
        lm[upper, :2] = [x, .475]
        lm[lower, :2] = [x, .510]
        lm[neighbor, :2] = [nx, .495]
    return lm, source, skin, excluded


def _recipe(amount=.5):
    return S.check({'version': 1, 'amount': amount})


def _smooth(value):
    # Independent test polynomial, not the product's stable symmetric helper.
    x = np.clip(value, 0., 1.)
    return x * x * x * (10. - 15. * x + 6. * x * x)


def _vertical(t, plateau, tail):
    out = np.zeros_like(t)
    rising = (t > 0.) & (t < 1.)
    flat = (t >= 1.) & (t <= plateau)
    falling = (t > plateau) & (t < plateau + tail)
    out[rising] = _smooth(t[rising])
    out[flat] = 1.
    out[falling] = _smooth((plateau + tail - t[falling]) / tail)
    return out


def _forward(points, parameters):
    """Independent TEST-ONLY forward oracle, including both plateau joins."""
    local = points - parameters[:2]
    height, inner, outer, plateau, tail, amount = parameters[6:]
    u, t = local @ parameters[2:4], (local @ parameters[4:6]) / height
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    shift = ((.08 * height) * amount) * lateral * _vertical(t, plateau, tail)
    return shift[:, None] * parameters[4:6]


def _native_double(points, parameters):
    """Independent physical-shift bisection oracle, NOT native execution."""
    local = points - parameters[:2]
    height, inner, outer, plateau, tail, amount = parameters[6:]
    u, t = local @ parameters[2:4], (local @ parameters[4:6]) / height
    k = ((.08 * height) * amount) * _smooth((outer - np.abs(u)) / (outer - inner))
    active = (np.abs(u) < outer) & (t > 0.) & (t < plateau + tail)
    low, high = np.minimum(k, 0.), np.maximum(k, 0.)
    for _ in range(100):
        middle = low + (high - low) * .5
        residual = middle - k * _vertical(t - middle / height, plateau, tail)
        high = np.where(residual > 0., middle, high)
        low = np.where(residual <= 0., middle, low)
    shift = np.where(active, low + (high - low) * .5, 0.)
    return np.ascontiguousarray(shift[:, None] * parameters[4:6])


def _build(monkeypatch, amount=.5, *, protected_boxes=(), mutate=None):
    lm, source, skin, excluded = _fixture()
    if mutate is not None:
        mutate(lm, source, skin, excluded)
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', _native_double)
    field = R.build(lm, _recipe(amount), source, excluded, backend='mediapipe',
                    analysis=observation, protected_boxes=protected_boxes)
    return field, lm, source, observation


def test_neutral_is_exact_identity_without_source_analysis_or_native_work(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('neutral input must not be inspected')
    monkeypatch.setattr(R, '_source', forbidden)
    monkeypatch.setattr(R, 'require_analysis', forbidden)
    monkeypatch.setattr(R, 'native_evaluate', forbidden)
    assert R.build(None, S.neutral(), None, None, backend='unavailable', analysis=None) is None
    sentinel = object()
    actual, facts = PORT.append(sentinel, None, None, None, None, S.neutral())
    assert actual is sentinel and facts is None


@pytest.mark.parametrize('amount', [1., -1., .4, -.4, 1e-10, -1e-10])
def test_signed_band_changes_both_cheeks_not_width_eye_plane_or_lower_interval(monkeypatch, amount):
    field, lm, source, _ = _build(monkeypatch, amount)
    measured = G.pixels(lm, source.shape[:2])
    p = field.parameters
    expected = _forward(measured, p)
    np.testing.assert_allclose(field.target_landmarks, measured + expected, rtol=0., atol=3e-12)
    np.testing.assert_allclose(field.evaluate(field.target_landmarks), expected, rtol=1e-8, atol=0.)
    np.testing.assert_allclose(field.target_landmarks - field.evaluate(field.target_landmarks), measured,
                               rtol=0., atol=3e-12)
    u, v = (measured - p[:2]) @ p[2:4], (measured - p[:2]) @ p[4:6]
    eyes = [index for polygon in G.EYES for index in polygon]
    assert np.all(v[eyes] < 0.)
    np.testing.assert_array_equal(field.target_landmarks[v <= 0.], measured[v <= 0.])
    np.testing.assert_allclose((field.target_landmarks - p[:2]) @ p[2:4], u, rtol=0., atol=3e-12)
    lower = (measured - measured[2]) @ p[4:6] >= 0.
    assert lower[152] and np.all(lower[[*G.LIPS, 13, 14]])
    np.testing.assert_allclose(field.target_landmarks[lower] - field.target_landmarks[2],
                               measured[lower] - measured[2], rtol=0., atol=3e-12)
    np.testing.assert_allclose(expected[lower], np.broadcast_to(((.08 * p[6]) * amount) * p[4:6],
                                                               expected[lower].shape), rtol=1e-10, atol=0.)
    for upper, lower_probe in ((117, 50), (346, 280)):
        before = (measured[lower_probe] - measured[upper]) @ p[4:6]
        after = (field.target_landmarks[lower_probe] - field.target_landmarks[upper]) @ p[4:6]
        assert (after - before) * amount > 0.
    fact = field.facts['mid_face']
    assert fact['requirement_id'] == 'LNX-REF-PC-32466-C-ea67c9d99f'
    assert fact['audited_retained_landmarks'] == 478
    assert fact['gain'] == S.LENGTH_GAIN == .08
    assert fact['tail_ratio'] == max(S.MIN_TAIL, S.TAIL_FACTOR * (p[9] - 1.))
    assert fact['minimum_forward_derivative_bound'] >= .4
    assert 'not_clinical_middle_third' in fact['limitation']
    assert 'rising_band_also_changes_nose_geometry' in fact['limitation']


@pytest.mark.parametrize('amount', [1., -1.])
def test_both_plateau_joins_use_source_membership_not_destination_membership(monkeypatch, amount):
    field, *_ = _build(monkeypatch, amount)
    p = field.parameters
    t = np.array([1. - 1e-6, 1., 1. + 1e-6, p[9] - 1e-6, p[9], p[9] + 1e-6])
    source = p[:2] + (t * p[6])[:, None] * p[4:6]
    forward = _forward(source, p)
    target = source + forward
    np.testing.assert_allclose(field.evaluate(target), forward, rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(target - field.evaluate(target), source, rtol=0., atol=3e-12)
    assert ((target[1] - p[:2]) @ p[4:6] / p[6]) == pytest.approx(1. + .08 * amount)
    if amount < 0.:
        assert (target[1] - p[:2]) @ p[4:6] < p[6]
    else:
        assert (target[4] - p[:2]) @ p[4:6] > p[6] * p[9]


def test_plateau_encloses_all_lower_points_not_only_chin_proxy(monkeypatch):
    def beyond_chin(lm, *rest):
        # Within the measured-oval tolerance; deliberately below proxy152.
        lm[100, :2] = lm[152, :2] + [0., .001]
    field, *_ = _build(monkeypatch, mutate=beyond_chin)
    p = field.parameters
    v = (field.source_landmarks - p[:2]) @ p[4:6]
    assert v[100] > v[152]
    assert p[9] * p[6] > np.max(v)
    np.testing.assert_allclose(field.target_landmarks[[2, 100, 152]] - field.source_landmarks[[2, 100, 152]],
                               np.broadcast_to(((.08 * p[6]) * p[11]) * p[4:6], (3, 2)), atol=3e-12)


@pytest.mark.parametrize('scale', [0., .5, -1.])
def test_native_zero_attenuation_or_wrong_sign_cannot_be_reported_applied(monkeypatch, scale):
    lm, source, skin, excluded = _fixture()
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda q, p: _native_double(q, p) * scale)
    with pytest.raises(ValueError, match='full requested amount'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=observation)


def test_unrepresentable_amount_is_refused_not_gain_inflated(monkeypatch):
    lm, source, skin, excluded = _fixture()
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('lost target precision reached native'))
    with pytest.raises(ValueError, match='representable'):
        R.build(lm, _recipe(1e-300), source, excluded, backend='mediapipe', analysis=observation)


def test_closed_lips_keep_measured_coincidence_without_an_invented_opening(monkeypatch):
    def closed(lm, *rest):
        lm[13, :2] = lm[14, :2] = [.5, .62]
    field, *_ = _build(monkeypatch, mutate=closed)
    np.testing.assert_array_equal(field.source_landmarks[13], field.source_landmarks[14])
    np.testing.assert_array_equal(field.target_landmarks[13], field.target_landmarks[14])
    assert np.any(field.target_landmarks[13] != field.source_landmarks[13])


@pytest.mark.parametrize('mode', ['collapsed_band', 'wrong_cheek_order', 'cheek_inside_nose',
                                  'missing_neighbor', 'outside_oval', 'lip_order_inverted'])
def test_bad_measured_geometry_is_refused_without_templates_or_repair(monkeypatch, mode):
    lm, source, skin, excluded = _fixture()
    if mode == 'collapsed_band': lm[2, 1] = .46
    elif mode == 'wrong_cheek_order': lm[50, 1] = lm[117, 1] - .01
    elif mode == 'cheek_inside_nose': lm[346, 0] = .5
    elif mode == 'missing_neighbor': lm[118, :2] = lm[117, :2]
    elif mode == 'outside_oval': lm[100, :2] = [.05, .05]
    else: lm[13, 1], lm[14, 1] = lm[14, 1], lm[13, 1]
    observation = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('bad geometry reached native'))
    with pytest.raises(ValueError):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=observation)


@pytest.mark.parametrize('mode', ['missing_skin', 'zero_skin', 'flat_rgb', 'placeholder'])
def test_478_landmarks_cannot_replace_actual_skin_and_rgb_evidence(monkeypatch, mode):
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


@pytest.mark.parametrize('sector', [0, 1, 2, 3])
@pytest.mark.parametrize('loss', ['skin', 'rgb', 'variance'])
def test_each_cheek_sector_requires_its_own_skin_rgb_and_variance(monkeypatch, sector, loss):
    field, _, source, observation = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    _, _, center, width = G.frame(lm)
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    points = np.column_stack((xx.ravel(), yy.ravel()))
    u, v = (points - p[:2]) @ p[2:4], (points - p[:2]) @ p[4:6]
    side = (u >= 0.) == bool(sector % 2)
    half = (v >= .5 * p[6]) == bool(sector // 2)
    selected = (side & half & (v > 0.) & (v < p[6])).reshape(source.shape[:2])
    skin = observation['face_skin'].copy()
    if loss == 'skin': skin[selected] = 0.
    else: source[selected] = 1. if loss == 'rgb' else .5
    with pytest.raises(ValueError, match='all four cheek-band sectors'):
        R._cheek_support(lm, center, p[:2], p[2:4], p[4:6], p[6], width,
                         source, skin, observation['excluded'])


def test_nose_only_skin_cannot_pass_cheek_evidence(monkeypatch):
    field, _, source, observation = _build(monkeypatch)
    p, lm = field.parameters, field.source_landmarks
    _, _, center, width = G.frame(lm)
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    points = np.column_stack((xx.ravel(), yy.ravel()))
    u, v = (points - p[:2]) @ p[2:4], (points - p[:2]) @ p[4:6]
    skin = observation['face_skin'].copy()
    rising = (v > 0.) & (v < p[6])
    nose_min = field.facts['mid_face']['cheek_excluded_nose_axis_min_px']
    nose_max = field.facts['mid_face']['cheek_excluded_nose_axis_max_px']
    skin.ravel()[rising & ((u < nose_min) | (u > nose_max))] = 0.
    with pytest.raises(ValueError, match='all four cheek-band sectors'):
        R._cheek_support(lm, center, p[:2], p[2:4], p[4:6], p[6], width,
                         source, skin, observation['excluded'])


def test_local_cheek_probe_requires_actual_rgb_not_just_sector_averages(monkeypatch):
    def blank(lm, source, skin, excluded):
        x, y = np.rint(lm[117, :2] * [source.shape[1] - 1, source.shape[0] - 1]).astype(int)
        source[y - 3:y + 4, x - 3:x + 4] = .5
    with pytest.raises(ValueError, match='cheek-surface probes'):
        _build(monkeypatch, mutate=blank)


@pytest.mark.parametrize('index', [117, 346, 2, 13, 152])
def test_known_occlusion_veto_covers_cheeks_nose_lips_and_lower_oval(monkeypatch, index):
    def occlude(lm, source, skin, excluded):
        point = lm[index, :2] * [source.shape[1] - 1, source.shape[0] - 1]
        if index == 152:
            point[1] -= 2.  # Interior immediately above actual chin boundary.
        x, y = np.rint(point).astype(int)
        excluded[y, x] = 1.
    with pytest.raises(ValueError, match='occlud'):
        _build(monkeypatch, mutate=occlude)


def test_lip_skin_class_is_exempt_but_rgb_and_occlusion_are_not(monkeypatch):
    def remove_skin(lm, source, skin, excluded):
        yy, xx = np.mgrid[:skin.shape[0], :skin.shape[1]]
        points = np.column_stack((xx.ravel(), yy.ravel()))
        inside = G.polygon_inside(points, G.pixels(lm, skin.shape)[list(G.LIPS)])
        skin.ravel()[inside] = 0.
    field, *_ = _build(monkeypatch, mutate=remove_skin)
    assert field.facts['mid_face']['lip_support_px'] > 0


def test_every_measured_oval_segment_crossing_the_upper_plane_requires_support(monkeypatch):
    seen = []
    original = R._segment_support
    def record(a, b, *args):
        seen.append((a.copy(), b.copy()))
        return original(a, b, *args)
    monkeypatch.setattr(R, '_segment_support', record)
    field, *_ = _build(monkeypatch)
    oval = field.source_landmarks[list(G.FACE_OVAL)]
    v = (oval - field.parameters[:2]) @ field.parameters[4:6]
    expected = [(a, b) for index, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0)))
                if max(v[index], v[(index + 1) % len(oval)]) > 0.]
    assert len(seen) == len(expected) == field.facts['mid_face']['boundary_segments']
    np.testing.assert_array_equal(np.asarray(seen), np.asarray(expected))


def test_canonical_float32_evidence_not_added_caller_precision(monkeypatch):
    field, lm, source, observation = _build(monkeypatch)
    precise = observation['landmarks'].astype(np.float64) + 1e-11
    other = R.build(precise, _recipe(), source, observation['excluded'], backend='mediapipe',
                    analysis={**observation, 'landmarks': precise})
    np.testing.assert_array_equal(field.parameters, other.parameters)
    forged = deepcopy(observation)
    forged['landmarks'][117, 0] += .001
    with pytest.raises(ValueError, match='exact retained'):
        R.build(lm, _recipe(), source, observation['excluded'], backend='mediapipe', analysis=forged)


@pytest.mark.parametrize('location', ['lateral_feather', 'below_plateau_feather', 'rectangle_corner'])
def test_complete_support_rectangle_protects_every_other_retained_face(monkeypatch, location):
    field, _, source, _ = _build(monkeypatch)
    p = field.parameters
    if location == 'lateral_feather': x, y = .5 * (p[7] + p[8]), .5 * p[6]
    elif location == 'below_plateau_feather': x, y = 0., (p[9] + .5 * p[10]) * p[6]
    else: x, y = p[8] - .1, (p[9] + p[10]) * p[6] - .1
    point = p[:2] + x * p[2:4] + y * p[4:6]
    h, w = source.shape[:2]
    box = np.r_[point - .25, point + .25] / [w - 1, h - 1, w - 1, h - 1]
    with pytest.raises(ValueError, match='another retained face'):
        _build(monkeypatch, protected_boxes=[box])


def test_support_cannot_be_clipped_or_gain_reduced_to_fit_source(monkeypatch):
    def shift(lm, *rest): lm[:, 1] += .12
    with pytest.raises(ValueError, match='complete influence bounding box'):
        _build(monkeypatch, mutate=shift)


def test_roll_mirror_and_scale_follow_actual_measured_axes(monkeypatch):
    field, lm, source, observation = _build(monkeypatch)
    angle = .16
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    for transform, scale in ((rotation, 1.), (np.diag([-1., 1.]), 1.), (np.eye(2), .9)):
        changed = lm.copy()
        changed[:, :2] = ((lm[:, :2].astype(np.float64) - .5) @ transform.T * scale + .5).astype(np.float32)
        changed_observation = _analysis(changed, source.shape[:2], observation['face_skin'], observation['excluded'])
        other = R.build(changed, _recipe(), source, observation['excluded'],
                        backend='mediapipe', analysis=changed_observation)
        np.testing.assert_allclose(other.parameters[2:4], transform @ field.parameters[2:4], atol=2e-6)
        np.testing.assert_allclose(other.parameters[4:6], transform @ field.parameters[4:6], atol=2e-6)
        assert other.parameters[6] == pytest.approx(field.parameters[6] * scale, abs=4e-5)
        transformed_target = (field.target_landmarks - 200.) @ transform.T * scale + 200.
        np.testing.assert_allclose(other.target_landmarks, transformed_target, rtol=0., atol=6e-5)


def test_exact_upper_outside_identity_and_smooth_lateral_below_chin_feathers(monkeypatch):
    field, *_ = _build(monkeypatch)
    p = field.parameters
    local = np.array([[0., -.2 * p[6]], [0., 0.], [0., .5 * p[6]],
                      [.5 * (p[7] + p[8]), .5 * p[6]], [0., (p[9] + .5 * p[10]) * p[6]],
                      [p[8] + 1., .5 * p[6]], [0., (p[9] + p[10] + .01) * p[6]]])
    points = p[:2] + local[:, :1] * p[2:4] + local[:, 1:] * p[4:6]
    delta = field.evaluate(points)
    np.testing.assert_array_equal(delta[[0, 1, 5, 6]], np.zeros((4, 2)))
    assert 0. < np.linalg.norm(delta[3]) < np.linalg.norm(delta[2])
    assert np.linalg.norm(delta[4]) > 0.
    np.testing.assert_allclose(delta @ p[2:4], 0., rtol=0., atol=1e-12)


def test_forward_zero_edge_audit_avoids_cancellation():
    p = np.array([0., 0., 1., 0., 0., 1., 100., 50., 75., 3., 1., 1.])
    delta = R._forward_delta(np.array([[75. - 1e-6, 400. - 1e-6]]), p)
    assert delta[0, 0] == 0. and delta[0, 1] > 0.


def test_parameter_landmark_and_metadata_storage_has_no_mutable_aliases(monkeypatch):
    field, *_ = _build(monkeypatch)
    for value in (field.state, field.parameters, field.source_landmarks, field.target_landmarks):
        assert not value.flags.writeable
        with pytest.raises(ValueError): value.setflags(write=True)
    with pytest.raises(FrozenInstanceError): field.state = np.zeros(12)
    facts = field.facts
    facts['mid_face']['amount'] = 0.
    assert field.facts['mid_face']['amount'] == .5
    assert field.resident_bytes() >= sum(a.nbytes for a in
        (field.parameters, field.source_landmarks, field.target_landmarks))


def test_native_calls_and_evidence_tiles_remain_bounded(monkeypatch):
    field, *_ = _build(monkeypatch)
    calls = []
    def bounded(points, parameters):
        calls.append(len(points))
        return _native_double(points, parameters)
    monkeypatch.setattr(R, 'native_evaluate', bounded)
    points = np.tile([[200.5, 220.25]], (2 * 65536 + 3, 1))
    np.testing.assert_array_equal(field.evaluate(points), _native_double(points, field.parameters))
    assert calls == [65536, 65536, 3]
    assert all((ys.stop - ys.start) * (xs.stop - xs.start) <= 65536
               for ys, xs in R._tiles((7, 9), (1032, 1047)))


def test_common_helpers_do_not_load_lower_face_or_face_size_native(monkeypatch):
    from lumaretouch_engine import lower_face_native, face_size_native
    from lumaretouch_engine import lower_face_runtime, face_size_runtime
    def forbidden(*args, **kwargs): pytest.fail('mid face invoked an unrelated operator')
    for native in (lower_face_native, face_size_native): monkeypatch.setattr(native, 'native', forbidden)
    for runtime in (lower_face_runtime, face_size_runtime): monkeypatch.setattr(runtime, 'build', forbidden)
    field, *_ = _build(monkeypatch)
    assert field.facts['mid_face']['applied']


class _SyntheticField:
    """Explicit composition/guard double, not measured anatomy or native code."""
    state = ('synthetic',)
    def __init__(self, function, resident=32): self.function, self.resident = function, resident
    def evaluate(self, points): return self.function(points)
    def resident_bytes(self): return self.resident


class _MetadataPrefix(FaceGeometry):
    def resident_bytes(self): return super().resident_bytes() + 819


def test_outermost_composition_preserves_every_prefix_mouth_slot_and_metadata_budget():
    zero = _SyntheticField(lambda q: np.zeros_like(q), resident=17)
    mouth = _SyntheticField(lambda q: q * [.01, .02], resident=41)
    for count in (4, 5, 6, 7):
        fields = (None, None, None, mouth) + (zero,) * (count - 4)
        prefix = _MetadataPrefix('synthetic', (401, 401), zero, fields)
        mid = _SyntheticField(lambda q: np.tile([0., 2.], (len(q), 1)), resident=83)
        wrapper = PORT.MidFace('synthetic', (401, 401), zero, (*fields, mid), prefix, ())
        q = np.array([[190., 240.], [210., 260.]])
        expected = mid.evaluate(q) + prefix.evaluate(q - mid.evaluate(q))
        np.testing.assert_array_equal(wrapper.evaluate(q), expected)
        assert wrapper.prefix is prefix and wrapper.fields[3] is mouth
        assert all(a is b for a, b in zip(wrapper.fields[:-1], fields))
        assert wrapper.resident_bytes() == prefix.resident_bytes() + 83 + 256


@pytest.mark.parametrize('stage', ['output', 'intermediate', 'final'])
def test_output_intermediate_and_final_foreign_footprints_are_guarded(stage):
    q = np.array([[150., 200.]])
    mid = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    position = {'output': [150., 200.], 'intermediate': [150., 190.], 'final': [150., 180.]}[stage]
    box = tuple(np.r_[np.asarray(position) - .1, np.asarray(position) + .1] / 400.)
    wrapper = PORT.MidFace('synthetic', (401, 401), prior, (*prefix.fields, mid), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)


def test_cancellation_does_not_hide_foreign_intermediate_or_invalid_source_footprint():
    q = np.array([[150., 200.]])
    mid = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., -10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    box = (149.9 / 400., 189.9 / 400., 150.1 / 400., 190.1 / 400.)
    wrapper = PORT.MidFace('synthetic', (401, 401), prior, (*prefix.fields, mid), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)
    zero = _SyntheticField(lambda p: np.zeros_like(p))
    prefix = FaceGeometry('synthetic', (401, 401), zero, (None,) * 4)
    huge = _SyntheticField(lambda p: np.tile([0., 250.], (len(p), 1)))
    wrapper = PORT.MidFace('synthetic', (401, 401), zero, (*prefix.fields, huge), prefix, ())
    with pytest.raises(ValueError, match='genuine source margin'): wrapper.evaluate(q)
