# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN lower-third geometry contracts, not photographic evidence.

All landmarks, observation metadata and textures are explicit synthetic test
doubles. The bisection oracle is test-only, never a production inverse fallback.
These fixtures do not validate real anatomy, segmentation, native ABI loading,
image quality or commercial parity. No product imports, collection, execution,
inference, builds or type checks ran while authoring this file.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from test_face_contour_geometry_unrun import _fixture as _contour_fixture, _analysis
from lumaretouch_engine import face_contour_geometry as G
from lumaretouch_engine import lower_face_runtime as R, lower_face_state as S
from lumaretouch_engine import lower_face_people as PORT
from lumaretouch_engine.people_geometry import FaceGeometry


def _fixture():
    """Measured-looking synthetic geometry ONLY, with explicit proxy ordering."""
    lm, source, skin, excluded = _contour_fixture()
    lm[94, :2] = [.5, .51]
    lm[2, :2] = [.5, .54]
    lm[97, :2] = [.47, .54]
    lm[326, :2] = [.53, .54]
    lm[13, :2] = [.5, .643]
    lm[14, :2] = [.5, .657]
    # Ample genuine-source margin for the complete below-chin/lateral halo.
    lm[:, :2] = .5 + .8 * (lm[:, :2] - .5)
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    value = .4 + .06 * np.sin((xx + 2 * yy) * .7) + .04 * np.cos((2 * xx - yy) * .4)
    source = np.repeat(value[..., None], 3, axis=2).astype(np.float32)
    return lm, source, skin, excluded


def _recipe(amount=.5):
    return S.check({'version': 1, 'amount': amount})


def _smooth(t):
    t = np.clip(t, 0., 1.)
    z = np.minimum(t, 1. - t)
    low = z * z * z * (10. + z * (6. * z - 15.))
    return np.where(t <= .5, low, 1. - low)


def _vertical(t, tail):
    out = np.zeros_like(t)
    rising, falling = (t > 0) & (t <= 1), (t > 1) & (t < 1 + tail)
    out[rising] = _smooth(t[rising])
    out[falling] = _smooth((1 + tail - t[falling]) / tail)
    return out


def _native_double(points, parameters):
    """Independent bounded bisection oracle; synthetic, not Rust execution."""
    origin, right, down = parameters[:2], parameters[2:4], parameters[4:6]
    height, inner, outer, tail, amount = parameters[6:]
    local = points - origin
    u, t = local @ right, (local @ down) / height
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    k = ((.08 * height) * amount) * lateral
    active = (np.abs(u) < outer) & (t > 0.) & (t < 1. + tail)
    low, high = np.minimum(k, 0.), np.maximum(k, 0.)
    for _ in range(96):
        middle = low + .5 * (high - low)
        residual = middle - k * _vertical(t - middle / height, tail)
        high = np.where(residual > 0, middle, high)
        low = np.where(residual <= 0, middle, low)
    shift = np.where(active, low + .5 * (high - low), 0.)
    return np.ascontiguousarray(shift[:, None] * down)


def _build(monkeypatch, amount=.5, *, protected_boxes=(), mutate=None):
    lm, source, skin, excluded = _fixture()
    if mutate is not None:
        mutate(lm, source, skin, excluded)
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', _native_double)
    field = R.build(lm, _recipe(amount), source, excluded, backend='mediapipe',
                    analysis=analysis, protected_boxes=protected_boxes)
    return field, lm, source, analysis


def test_neutral_has_no_source_anatomy_native_or_wrapper_work(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('neutral cannot inspect or load this input')
    monkeypatch.setattr(R, 'require_analysis', forbidden)
    monkeypatch.setattr(R, 'native_evaluate', forbidden)
    monkeypatch.setattr(R, '_source', forbidden)
    assert R.build(None, S.neutral(), None, None, backend='unavailable', analysis=None) is None
    sentinel = object()
    result, facts = PORT.append(sentinel, None, None, None, None, S.neutral())
    assert result is sentinel and facts is None


@pytest.mark.parametrize('amount', [1., -1., .4, -.4, 1e-10, -1e-10])
def test_signed_lower_third_moves_lips_not_width_or_upper_face(monkeypatch, amount):
    field, lm, source, _ = _build(monkeypatch, amount)
    measured = G.pixels(lm, source.shape[:2])
    p = field.parameters
    u, v = (measured - p[:2]) @ p[2:4], (measured - p[:2]) @ p[4:6]
    expected_shift = ((.08 * p[6]) * amount) * _vertical(v / p[6], .5)
    expected = expected_shift[:, None] * p[4:6]
    np.testing.assert_allclose(field.target_landmarks, measured + expected, rtol=0., atol=3e-12)
    np.testing.assert_allclose(field.evaluate(field.target_landmarks), expected, rtol=1e-8, atol=0.)
    np.testing.assert_allclose(field.target_landmarks - field.evaluate(field.target_landmarks), measured,
                               rtol=0., atol=3e-12)
    np.testing.assert_array_equal(field.target_landmarks[v <= 0], measured[v <= 0])
    np.testing.assert_allclose((field.target_landmarks - p[:2]) @ p[2:4], u, rtol=0., atol=3e-12)
    lip_ids = [*G.LIPS, 13, 14]
    assert np.all(np.linalg.norm(expected[lip_ids], axis=1) > 0)
    assert np.all(np.sign(expected_shift[lip_ids]) == np.sign(amount))
    chin_interval = float((field.target_landmarks[152] - field.target_landmarks[2]) @ p[4:6])
    assert chin_interval == pytest.approx(p[6] * (1 + .08 * amount), abs=3e-12)
    fact = field.facts['lower_face']
    assert fact['requirement_id'] == 'LNX-REF-PC-32466-C-1ae8316994'
    assert fact['nose_proxy_index'] == 2 and fact['chin_proxy_index'] == 152
    assert fact['audited_retained_landmarks'] == 478
    assert fact['minimum_forward_derivative_bound'] >= .7
    assert fact['gain'] == S.LENGTH_GAIN and fact['tail_ratio'] == S.TAIL
    assert 'not_clinical_anatomy' in fact['limitation']


@pytest.mark.parametrize('amount', [.5, -.5, 1e-10, -1e-10])
def test_native_zero_or_wrong_amount_is_never_reported_applied(monkeypatch, amount):
    lm, source, skin, excluded = _fixture()
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    for scale in (0., .5, -1.):
        monkeypatch.setattr(R, 'native_evaluate', lambda q, p: _native_double(q, p) * scale)
        with pytest.raises(ValueError, match='full requested amount'):
            R.build(lm, _recipe(amount), source, excluded, backend='mediapipe', analysis=analysis)


def test_nonrepresentable_request_is_refused_before_native(monkeypatch):
    lm, source, skin, excluded = _fixture()
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('lost target precision reached native'))
    with pytest.raises(ValueError, match='representable'):
        R.build(lm, _recipe(1e-300), source, excluded, backend='mediapipe', analysis=analysis)


def test_closed_inner_lips_are_measured_not_invented_open(monkeypatch):
    def close(lm, *rest):
        lm[13, :2] = lm[14, :2] = [.5, .62]
    field, *_ = _build(monkeypatch, mutate=close)
    np.testing.assert_array_equal(field.source_landmarks[13], field.source_landmarks[14])
    np.testing.assert_array_equal(field.target_landmarks[13], field.target_landmarks[14])
    assert np.any(field.target_landmarks[13] != field.source_landmarks[13])


def test_inner_lip_boundary_contact_is_admitted_without_geometry_extrapolation(monkeypatch):
    def touch(lm, *rest):
        lm[13, :2] = lm[14, :2] = lm[0, :2]
    field, *_ = _build(monkeypatch, mutate=touch)
    np.testing.assert_array_equal(field.target_landmarks[13], field.target_landmarks[0])


@pytest.mark.parametrize('mode', ['lip_above_nose', 'chin_above_lips', 'nose_chain_inverted',
                                  'foreshortened', 'outside_oval', 'lip_order_inverted'])
def test_unmeasured_or_badly_ordered_geometry_is_not_repaired(monkeypatch, mode):
    lm, source, skin, excluded = _fixture()
    if mode == 'lip_above_nose': lm[list(G.LIPS), 1] -= .2
    elif mode == 'chin_above_lips': lm[152, 1] = .5
    elif mode == 'nose_chain_inverted': lm[94, 1] = lm[2, 1] + .03
    elif mode == 'foreshortened': lm[133, :2] = lm[33, :2] + [.002, 0.]
    elif mode == 'outside_oval': lm[100, :2] = [.05, .05]
    else: lm[13, 1], lm[14, 1] = lm[14, 1], lm[13, 1]
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('bad geometry reached native'))
    with pytest.raises(ValueError):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=analysis)


@pytest.mark.parametrize('mode', ['missing_skin', 'zero_skin', 'flat_rgb', 'placeholder',
                                  'nose_occluded', 'lips_occluded', 'lower_interior_occluded'])
def test_478_landmarks_are_not_visibility_or_rgb_evidence(monkeypatch, mode):
    lm, source, skin, excluded = _fixture()
    if mode == 'zero_skin': skin.fill(0.)
    if mode == 'flat_rgb': source.fill(.5)
    if mode == 'nose_occluded': excluded[210:216, 198:203] = 1.
    if mode == 'lips_occluded': excluded[246:250, 198:203] = 1.
    if mode == 'lower_interior_occluded': excluded[275:285, 165:175] = 1.
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    if mode == 'missing_skin':
        del analysis['face_skin']; del analysis['face_skin_observation']
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('missing evidence reached native'))
    with pytest.raises(ValueError):
        R.build(lm, _recipe(), source, excluded,
                backend='template' if mode == 'placeholder' else 'mediapipe', analysis=analysis)


def test_lip_pixels_need_rgb_not_a_false_skin_class(monkeypatch):
    def remove_lip_skin(lm, source, skin, excluded):
        yy, xx = np.mgrid[:skin.shape[0], :skin.shape[1]]
        points = np.column_stack((xx.ravel(), yy.ravel()))
        inside = G.polygon_inside(points, G.pixels(lm, skin.shape)[list(G.LIPS)])
        skin.ravel()[inside] = 0.
    field, *_ = _build(monkeypatch, mutate=remove_lip_skin)
    assert field.facts['lower_face']['lip_support_px'] > 0


def test_measured_lower_oval_segments_all_require_support(monkeypatch):
    seen = []
    original = R._segment_support
    def record(a, b, *args):
        seen.append((a.copy(), b.copy()))
        return original(a, b, *args)
    monkeypatch.setattr(R, '_segment_support', record)
    field, *_ = _build(monkeypatch)
    oval = field.source_landmarks[list(G.FACE_OVAL)]
    v = (oval - field.parameters[:2]) @ field.parameters[4:6]
    expected = [(a, b) for i, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0)))
                if max(v[i], v[(i + 1) % len(oval)]) > 0]
    assert len(seen) == len(expected) == field.facts['lower_face']['boundary_segments']
    np.testing.assert_array_equal(np.asarray(seen), np.asarray(expected))


def test_boundary_strips_do_not_replace_missing_lower_interior(monkeypatch):
    lm, source, skin, excluded = _fixture()
    skin[258:285, 180:220] = 0.
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('missing interior reached native'))
    with pytest.raises(ValueError, match='lower interior'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=analysis)


def test_canonical_float32_evidence_is_bound_without_added_precision(monkeypatch):
    field, lm, source, analysis = _build(monkeypatch)
    precise = analysis['landmarks'].astype(np.float64) + 1e-11
    other = R.build(precise, _recipe(), source, analysis['excluded'], backend='mediapipe',
                    analysis={**analysis, 'landmarks': precise})
    np.testing.assert_array_equal(field.parameters, other.parameters)
    forged = deepcopy(analysis)
    forged['landmarks'][2, 0] += .001
    with pytest.raises(ValueError, match='exact retained'):
        R.build(lm, _recipe(), source, analysis['excluded'], backend='mediapipe', analysis=forged)


@pytest.mark.parametrize('location', ['lateral_feather', 'below_chin_feather', 'rectangle_corner'])
def test_entire_support_rectangle_protects_every_foreign_face(monkeypatch, location):
    field, _, source, _ = _build(monkeypatch)
    p = field.parameters
    if location == 'lateral_feather':
        point = p[:2] + .5 * (p[7] + p[8]) * p[2:4] + .5 * p[6] * p[4:6]
    elif location == 'below_chin_feather':
        point = p[:2] + 1.25 * p[6] * p[4:6]
    else:
        point = p[:2] + (p[8] - .1) * p[2:4] + (1.5 * p[6] - .1) * p[4:6]
    h, w = source.shape[:2]
    box = np.r_[point - .25, point + .25] / [w - 1, h - 1, w - 1, h - 1]
    with pytest.raises(ValueError, match='another retained face'):
        _build(monkeypatch, protected_boxes=[box])


def test_complete_below_chin_halo_cannot_be_clipped_or_gain_reduced(monkeypatch):
    lm, source, skin, excluded = _fixture()
    lm[:, 1] += .12  # All measured points fit; the full tail does not.
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('clipped support reached native'))
    with pytest.raises(ValueError, match='complete influence bounding box'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=analysis)


def test_roll_mirror_and_scale_use_measured_head_axes(monkeypatch):
    field, lm, source, analysis = _build(monkeypatch)
    angle = .16
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    for transform, scale in ((rotation, 1.), (np.diag([-1., 1.]), 1.), (np.eye(2), .9)):
        changed = lm.copy()
        changed[:, :2] = ((lm[:, :2].astype(np.float64) - .5) @ transform.T * scale + .5).astype(np.float32)
        observation = _analysis(changed, source.shape[:2], analysis['face_skin'], analysis['excluded'])
        other = R.build(changed, _recipe(), source, analysis['excluded'], backend='mediapipe', analysis=observation)
        np.testing.assert_allclose(other.parameters[2:4], transform @ field.parameters[2:4], atol=2e-6)
        np.testing.assert_allclose(other.parameters[4:6], transform @ field.parameters[4:6], atol=2e-6)
        assert other.parameters[6] == pytest.approx(field.parameters[6] * scale, abs=3e-5)
        transformed_target = (field.target_landmarks - 200.) @ transform.T * scale + 200.
        np.testing.assert_allclose(other.target_landmarks, transformed_target, rtol=0., atol=5e-5)


def test_flat_core_lateral_and_tail_feathers_and_upper_identity(monkeypatch):
    field, *_ = _build(monkeypatch)
    p = field.parameters
    local = np.array([[0., -.2 * p[6]], [0., 0.], [0., .5 * p[6]],
                      [.5 * (p[7] + p[8]), .5 * p[6]], [0., 1.25 * p[6]],
                      [p[8] + 1., .5 * p[6]], [0., 1.51 * p[6]]])
    points = p[:2] + local[:, :1] * p[2:4] + local[:, 1:] * p[4:6]
    delta = field.evaluate(points)
    np.testing.assert_array_equal(delta[[0, 1, 5, 6]], np.zeros((4, 2)))
    assert 0 < np.linalg.norm(delta[3]) < np.linalg.norm(delta[2])
    assert np.linalg.norm(delta[4]) > 0
    np.testing.assert_allclose(delta @ p[2:4], 0., rtol=0., atol=1e-12)


def test_zero_edge_forward_audit_does_not_cancel_small_positive_weight():
    p = np.array([0., 0., 1., 0., 0., 1., 100., 50., 75., .5, 1.])
    point = np.array([[75. - 1e-6, 150. - 1e-6]])
    delta = R._forward_delta(point, p)
    assert delta[0, 0] == 0. and delta[0, 1] > 0.


def test_parameters_arrays_and_facts_have_no_mutable_aliases(monkeypatch):
    field, *_ = _build(monkeypatch)
    for value in (field.state, field.parameters, field.source_landmarks, field.target_landmarks):
        assert not value.flags.writeable
        with pytest.raises(ValueError):
            value.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        field.state = np.zeros(11)
    facts = field.facts
    facts['lower_face']['amount'] = 0.
    assert field.facts['lower_face']['amount'] == .5
    assert field.resident_bytes() >= sum(a.nbytes for a in
        (field.parameters, field.source_landmarks, field.target_landmarks))


def test_native_calls_and_all_pixel_tiles_are_bounded(monkeypatch):
    field, *_ = _build(monkeypatch)
    calls = []
    def bounded(points, parameters):
        calls.append(len(points))
        return _native_double(points, parameters)
    monkeypatch.setattr(R, 'native_evaluate', bounded)
    points = np.tile([[200.5, 250.25]], (2 * 65536 + 3, 1))
    actual = field.evaluate(points)
    assert calls == [65536, 65536, 3]
    np.testing.assert_array_equal(actual, _native_double(points, field.parameters))
    assert all((ys.stop - ys.start) * (xs.stop - xs.start) <= 65536
               for ys, xs in R._tiles((7, 9), (1032, 1047)))


def test_common_evidence_helpers_never_require_face_size_native(monkeypatch):
    from lumaretouch_engine import face_size_native as SIZE_NATIVE
    monkeypatch.setattr(SIZE_NATIVE, 'native', lambda: pytest.fail('lower face loaded unrelated native core'))
    field, *_ = _build(monkeypatch)
    assert field.facts['lower_face']['applied']


class _SyntheticField:
    """Explicit guard/composition double, not measured anatomy or native code."""
    state = ('synthetic',)
    def __init__(self, function, resident=32):
        self.function, self.resident = function, resident
    def evaluate(self, points):
        return self.function(points)
    def resident_bytes(self):
        return self.resident


def test_outermost_composition_preserves_prefix_and_mouth_slot_without_double_count():
    zero = _SyntheticField(lambda q: np.zeros_like(q), resident=17)
    mouth = _SyntheticField(lambda q: q * [.01, .02], resident=41)
    # Five/six-slot neutral extra fields isolate order without claiming contour
    # or whole-face-size quality. Each existing slot is retained by identity.
    for count in (4, 5, 6):
        fields = (None, None, None, mouth) + (zero,) * (count - 4)
        prefix = FaceGeometry('synthetic', (401, 401), zero, fields)
        lower = _SyntheticField(lambda q: np.tile([0., 2.], (len(q), 1)), resident=83)
        wrapper = PORT.LowerFace('synthetic', (401, 401), zero, (*fields, lower), prefix, ())
        q = np.array([[190., 240.], [210., 260.]])
        expected = lower.evaluate(q) + prefix.evaluate(q - lower.evaluate(q))
        np.testing.assert_array_equal(wrapper.evaluate(q), expected)
        assert wrapper.prefix is prefix and wrapper.fields[3] is mouth
        assert all(a is b for a, b in zip(wrapper.fields[:-1], fields))
        assert wrapper.resident_bytes() == prefix.resident_bytes() + 83 + 256


@pytest.mark.parametrize('stage', ['output', 'intermediate', 'final'])
def test_actual_composed_output_intermediate_and_final_foreign_footprints_are_guarded(stage):
    q = np.array([[150., 200.]])
    lower = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    position = {'output': [150., 200.], 'intermediate': [150., 190.], 'final': [150., 180.]}[stage]
    box = tuple(np.r_[np.asarray(position) - .1, np.asarray(position) + .1] / 400.)
    wrapper = PORT.LowerFace('synthetic', (401, 401), prior, (*prefix.fields, lower), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'):
        wrapper.evaluate(q)


def test_composition_cannot_fill_outside_source_and_guards_cancellation():
    q = np.array([[150., 200.]])
    lower = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., -10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (401, 401), prior, (None,) * 4)
    box = (149.9 / 400., 189.9 / 400., 150.1 / 400., 190.1 / 400.)
    wrapper = PORT.LowerFace('synthetic', (401, 401), prior, (*prefix.fields, lower), prefix, (box,))
    # Total cancellation does not make the intermediate foreign footprint safe.
    with pytest.raises(ValueError, match='another retained face'):
        wrapper.evaluate(q)
    zero = _SyntheticField(lambda p: np.zeros_like(p))
    prefix = FaceGeometry('synthetic', (401, 401), zero, (None,) * 4)
    huge = _SyntheticField(lambda p: np.tile([0., 250.], (len(p), 1)))
    wrapper = PORT.LowerFace('synthetic', (401, 401), zero, (*prefix.fields, huge), prefix, ())
    with pytest.raises(ValueError, match='genuine source margin'):
        wrapper.evaluate(q)
