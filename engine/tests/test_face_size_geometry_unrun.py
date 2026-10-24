# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN geometry contracts, never photographic acceptance evidence.

Synthetic landmarks, source texture and the explicit native-double below only
isolate ownership/admission/math. They do not certify MediaPipe, segmentation,
real visible anatomy, the compiled Rust ABI or output quality. No imports,
inference, product execution or tests ran while authoring these fixtures.
"""
from dataclasses import FrozenInstanceError
from copy import deepcopy

import numpy as np
import pytest

from test_face_contour_geometry_unrun import _fixture as _contour_fixture, _analysis
from lumaretouch_engine import face_contour_geometry as G
from lumaretouch_engine import face_size_runtime as R, face_size_state as S


def _fixture():
    lm, source, skin, excluded = _contour_fixture()
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    value = .4 + .06 * np.sin((xx + 2 * yy) * .7) + .04 * np.cos((2 * xx - yy) * .4)
    source = np.repeat(value[..., None], 3, axis=2).astype(np.float32)
    return lm, source, skin, excluded


def _recipe(amount=.5):
    return S.check({'version': 1, 'amount': amount})


def _native_double(points, parameters):
    """Test oracle only. Production has no Python deformation fallback."""
    center, right, up = parameters[:2], parameters[2:4], parameters[4:6]
    hx, hy, inner, outer, scale = parameters[6:]
    local = points - center
    radius = np.hypot(local @ right / hx, local @ up / hy)
    t = np.clip((radius - inner) / (outer - inner), 0., 1.)
    weight = 1. - t**3 * (10. + t * (-15. + 6. * t))
    weight[radius >= outer] = 0.
    return np.ascontiguousarray(local * (((scale - 1.) / scale) * weight)[:, None])


def _build(monkeypatch, amount=.5, *, protected_boxes=()):
    lm, source, skin, excluded = _fixture()
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', _native_double)
    field = R.build(lm, _recipe(amount), source, excluded, backend='mediapipe',
                    analysis=analysis, protected_boxes=protected_boxes)
    return field, lm, source, analysis


def test_neutral_has_no_source_analysis_native_or_geometry_work(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('neutral cannot inspect or load this input')
    monkeypatch.setattr(R, 'require_analysis', forbidden)
    monkeypatch.setattr(R, 'native_evaluate', forbidden)
    assert R.build(None, S.neutral(), None, None, backend='unavailable', analysis=None) is None


@pytest.mark.parametrize('amount', [1., -1., .4, -.4, 1e-10, -1e-10])
def test_all_478_landmarks_share_exact_whole_face_scale_without_feature_pins(monkeypatch, amount):
    field, lm, source, _ = _build(monkeypatch, amount)
    measured = G.pixels(lm, source.shape[:2])
    center = field.parameters[:2]
    scale = 1. - .06 * amount
    target = center + scale * (measured - center)
    np.testing.assert_allclose(field.target_landmarks, target, rtol=0., atol=0.)
    np.testing.assert_allclose(target - field.evaluate(target), measured, rtol=0., atol=2e-12)
    expected = (target - center) * ((scale - 1.) / scale)
    np.testing.assert_allclose(field.evaluate(target), expected, rtol=1e-8, atol=0.)
    feature_ids = np.asarray(G.ANCHORS)
    moving = np.linalg.norm(measured[feature_ids] - center, axis=1) > 0
    assert np.all(np.any(field.evaluate(target[feature_ids])[moving] != 0, axis=1))
    assert (np.linalg.norm(target[10] - target[152]) < np.linalg.norm(measured[10] - measured[152])) == (amount > 0)
    fact = field.facts['face_size']
    assert fact['uniform_core_landmarks'] == 478 and fact['applied']
    assert fact['requirement_id'] == 'LNX-REF-PC-32466-C-728fc62cdd'
    assert fact['minimum_inverse_radial_derivative_bound'] >= .20


def test_native_zero_cannot_turn_nonzero_request_into_success(monkeypatch):
    lm, source, skin, excluded = _fixture()
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda q, p: np.zeros_like(q))
    for amount in (.5, 1e-10):
        with pytest.raises(ValueError, match='full requested scale'):
            R.build(lm, _recipe(amount), source, excluded, backend='mediapipe', analysis=analysis)


def test_nonrepresentable_nonzero_amount_is_refused_not_reported_applied(monkeypatch):
    lm, source, skin, excluded = _fixture()
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('unrepresentable amount reached native'))
    with pytest.raises(ValueError, match='representable'):
        R.build(lm, _recipe(1e-300), source, excluded, backend='mediapipe', analysis=analysis)


def test_parameters_landmarks_and_field_are_read_only_without_mutable_aliases(monkeypatch):
    field, *_ = _build(monkeypatch)
    for value in (field.state, field.parameters, field.source_landmarks, field.target_landmarks):
        assert not value.flags.writeable
        with pytest.raises(ValueError):
            value.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        field.state = np.zeros(11)
    before = field.parameters.copy()
    facts = field.facts
    facts['face_size']['scale'] = 0.
    assert field.facts['face_size']['scale'] != 0.
    np.testing.assert_array_equal(before, field.parameters)
    assert field.resident_bytes() >= sum(a.nbytes for a in
        (field.parameters, field.source_landmarks, field.target_landmarks))


def test_native_calls_and_all_new_pixel_tiles_are_bounded(monkeypatch):
    field, *_ = _build(monkeypatch)
    counts = []
    def bounded(q, p):
        counts.append(len(q))
        return _native_double(q, p)
    monkeypatch.setattr(R, 'native_evaluate', bounded)
    q = np.tile([[200.5, 185.25]], (65536 * 2 + 3, 1))
    result = field.evaluate(q)
    assert counts == [65536, 65536, 3]
    np.testing.assert_array_equal(result, _native_double(q, field.parameters))
    assert all((ys.stop - ys.start) * (xs.stop - xs.start) <= 65536
               for ys, xs in R._tiles((7, 9), (1032, 1047)))


def test_uniform_core_feather_and_exact_outside_identity(monkeypatch):
    field, *_ = _build(monkeypatch)
    p = field.parameters
    center, right, hx, inner, outer = p[:2], p[2:4], p[6], p[8], p[9]
    core = center + right * hx * inner * .9
    feather = center + right * hx * ((inner + outer) * .5)
    outside = center + right * hx * (outer + .1)
    q = np.stack((core, feather, outside))
    values = field.evaluate(q)
    np.testing.assert_array_equal(values[2], [0., 0.])
    assert np.linalg.norm(values[1]) > 0
    assert np.linalg.norm(values[1]) < np.linalg.norm((feather - center) * ((p[10] - 1.) / p[10]))
    assert 'background' in field.facts['face_size']['limitation']


def test_every_oval_segment_is_checked_not_only_lateral_contour(monkeypatch):
    seen = []
    original = R._segment_support
    def record(a, b, *args):
        seen.append((a.copy(), b.copy()))
        return original(a, b, *args)
    monkeypatch.setattr(R, '_segment_support', record)
    field, *_ = _build(monkeypatch)
    oval = field.source_landmarks[list(G.FACE_OVAL)]
    assert len(seen) == len(G.FACE_OVAL) == 36
    np.testing.assert_array_equal(np.asarray(seen)[:, 0], oval)
    np.testing.assert_array_equal(np.asarray(seen)[:, 1], np.roll(oval, -1, axis=0))


@pytest.mark.parametrize('mode', ['missing_skin', 'zero_skin', 'known_occluder', 'flat_rgb', 'placeholder'])
def test_landmarks_alone_never_authorize_whole_face_size(monkeypatch, mode):
    lm, source, skin, excluded = _fixture()
    if mode == 'zero_skin': skin.fill(0.)
    if mode == 'known_occluder': excluded[195:205, 195:205] = 1.
    if mode == 'flat_rgb': source.fill(.5)
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    if mode == 'missing_skin':
        del analysis['face_skin']; del analysis['face_skin_observation']
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('unsupported evidence reached native'))
    with pytest.raises(ValueError):
        R.build(lm, _recipe(), source, excluded,
                backend='template' if mode == 'placeholder' else 'mediapipe', analysis=analysis)


def test_same_canonical_float32_observation_not_extra_precision(monkeypatch):
    field, lm, source, analysis = _build(monkeypatch)
    precise = analysis['landmarks'].astype(np.float64) + 1e-11
    altered = {**analysis, 'landmarks': precise}
    duplicate = R.build(precise, _recipe(), source, analysis['excluded'], backend='mediapipe', analysis=altered)
    np.testing.assert_array_equal(field.parameters, duplicate.parameters)
    forged = deepcopy(analysis)
    forged['landmarks'][1, 0] += .001
    with pytest.raises(ValueError, match='exact retained'):
        R.build(lm, _recipe(), source, analysis['excluded'], backend='mediapipe', analysis=forged)


def test_full_ellipse_bbox_including_background_halo_protects_foreign_faces(monkeypatch):
    field, _, source, _ = _build(monkeypatch)
    p = field.parameters
    point = p[:2] + p[2:4] * p[6] * ((p[8] + p[9]) * .5)
    h, w = source.shape[:2]
    box = np.r_[point - .25, point + .25] / [w - 1, h - 1, w - 1, h - 1]
    with pytest.raises(ValueError, match='another retained face'):
        _build(monkeypatch, protected_boxes=[box])


def test_whole_influence_must_fit_source_without_border_fill(monkeypatch):
    lm, source, skin, excluded = _fixture()
    # Same measured geometry translated upward, still normalized but with an
    # outer ellipse that would cross the image. Do not crop its feather.
    lm[:, 1] -= .12
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('clipped field reached native'))
    with pytest.raises(ValueError, match='complete influence bounding box'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=analysis)


def test_rotation_and_mirroring_follow_measured_head_frame(monkeypatch):
    field, lm, source, analysis = _build(monkeypatch)
    angle = .19
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    for transform in (rotation, np.diag([-1., 1.])):
        changed = lm.copy()
        changed[:, :2] = ((lm[:, :2].astype(np.float64) - .5) @ transform.T + .5).astype(np.float32)
        observation = _analysis(changed, source.shape[:2], analysis['face_skin'], analysis['excluded'])
        other = R.build(changed, _recipe(), source, analysis['excluded'],
                        backend='mediapipe', analysis=observation)
        np.testing.assert_allclose(other.parameters[2:4], transform @ field.parameters[2:4], atol=2e-6)
        np.testing.assert_allclose(other.parameters[4:6], transform @ field.parameters[4:6], atol=2e-6)
        assert other.parameters[10] == field.parameters[10]


def test_bad_pose_and_outlying_measured_point_do_not_expand_a_template(monkeypatch):
    lm, source, skin, excluded = _fixture()
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('bad measured geometry reached native'))
    for mode in ('foreshortened', 'outside_oval'):
        changed = lm.copy()
        if mode == 'foreshortened': changed[133, :2] = changed[33, :2] + [.002, 0.]
        else: changed[100, :2] = [.05, .05]
        analysis = _analysis(changed, source.shape[:2], skin, excluded)
        with pytest.raises(ValueError):
            R.build(changed, _recipe(), source, excluded, backend='mediapipe', analysis=analysis)


def test_strips_do_not_substitute_for_missing_interior_face_skin(monkeypatch):
    lm, source, skin, excluded = _fixture()
    skin[155:245, 140:260] = 0.
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    monkeypatch.setattr(R, 'native_evaluate', lambda *args: pytest.fail('missing interior reached native'))
    with pytest.raises(ValueError, match='whole interior'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=analysis)


def test_large_strip_uses_same_full_resolution_evidence_without_large_grid(monkeypatch):
    # Exercise only tiled evidence, not any anatomical admission or native code.
    h, w = 700, 1000
    yy, xx = np.mgrid[:h, :w]
    value = .4 + .05 * np.sin(xx * .7) + .04 * np.cos(yy * .5)
    source = np.repeat(value[..., None], 3, axis=2).astype(np.float32)
    skin = np.ones((h, w), np.float32); excluded = np.zeros_like(skin)
    oval = np.array([[40., 40.], [960., 40.], [960., 660.], [40., 660.]])
    a, b, center, width = np.array([80., 80.]), np.array([920., 80.]), np.array([500., 350.]), 1600.
    expected = G._support_segment(a, b, center, width, oval, source, skin, excluded)
    monkeypatch.setattr(G, '_support_segment', lambda *args: pytest.fail('oversized strip allocated legacy grid'))
    assert R._segment_support(a, b, center, width, oval, source, skin, excluded) == expected
