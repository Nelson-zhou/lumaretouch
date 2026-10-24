# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN eye-symmetry geometry and source-boundary fixtures.

Every landmark, mask, evidence hash and source below is an explicit synthetic
test double, never a production face fallback or measured photographic evidence.
Only the shared native loader/primitive is replaced in complete build fixtures;
actual measurement, existing RGB visibility, adapter validation, protected TPS
and canonical composition remain real product paths. No product imports, test
collection/execution, builds, numerical probes or inference ran while authoring.
These fixtures establish no executable, native, visual or photographic result.
"""
from copy import deepcopy
import hashlib

import numpy as np
import pytest

from lumaretouch_engine import eye_shape_native as N
from lumaretouch_engine import eye_symmetry_runtime as R, eye_symmetry_state as S
from lumaretouch_engine import eye_symmetry_people as PORT
from lumaretouch_engine.people_geometry import FaceGeometry


def _fixture(shape=(512, 512), *, left_scale=1.04, right_scale=1., height_difference=2., roll=0.):
    """Explicit 478-point synthetic observations; not an analysis producer.

The 16-point integer lid ring makes exact equal-area/no-roll cases genuinely
equal after canonical float32 retention, rather than using an asymmetry epsilon.
Scale factors are fixture anatomy, not edits or engine recipe controls.
"""
    h, w = shape
    lm = np.tile([256., 300., 0.], (478, 1))
    for i, index in enumerate(R.NOSE_PROTECTION):
        angle = 2. * np.pi * i / len(R.NOSE_PROTECTION)
        lm[index, :2] = [256. - 18. * np.sin(angle), 240. - 60. * np.cos(angle)]
    for i, index in enumerate(R.BRIDGE):
        lm[index, :2] = [256., 180. + i * 15.]
    for side, (upper, lower) in R.CHAINS.items():
        xs = np.linspace(283., 355., 5) if side == 'left' else np.linspace(229., 157., 5)
        lm[list(upper), :2] = np.column_stack((xs, np.full(5, 164.)))
        lm[list(lower), :2] = np.column_stack((xs, np.full(5, 174.)))
    for i, index in enumerate(R.LIPS):
        angle = 2. * np.pi * i / len(R.LIPS)
        lm[index, :2] = [256. + 45. * np.cos(angle), 345. + 12. * np.sin(angle)]
    lm[10, :2], lm[152, :2] = [256., 80.], [256., 430.]
    lm[109, :2], lm[338, :2] = [220., 85.], [292., 85.]
    ring = np.array([[24., 0.], [22., 2.], [18., 4.], [10., 6.], [0., 7.],
                     [-10., 6.], [-18., 4.], [-22., 2.], [-24., 0.],
                     [-22., -2.], [-18., -4.], [-10., -6.], [0., -7.],
                     [10., -6.], [18., -4.], [22., -2.]])
    iris = np.array([[0., 0.], [4., 0.], [0., 4.], [-4., 0.], [0., -4.]])
    for side, cx, factor, dy in (('left', 320., left_scale, -.5 * height_difference),
                                  ('right', 192., right_scale, .5 * height_difference)):
        direction = np.array([1., 1.]) if side == 'left' else np.array([-1., 1.])
        center = np.array([cx, 220. + dy])
        lm[list(R.EYES[side]), :2] = center + ring * direction * factor
        lm[list(R.IRIS[side]), :2] = center + iris * factor
    if roll:
        rotation = np.array([[np.cos(roll), -np.sin(roll)], [np.sin(roll), np.cos(roll)]])
        lm[:, :2] = (lm[:, :2] - [256., 256.]) @ rotation.T + [256., 256.]
    # Scale the complete synthetic pixel geometry to the requested source frame.
    lm[:, :2] /= 512.
    yy, xx = np.mgrid[:h, :w]
    luma = .48 + .12 * np.sin(xx * .7) + .09 * np.cos(yy * .8)
    source = np.repeat(luma[..., None], 3, axis=2).astype(np.float32)
    return lm.astype(np.float32), source, np.zeros((h, w), np.float32)


def _analysis(lm, shape, excluded, *, asset='a' * 64, instance='test-face'):
    h, w = shape
    return {
        'face_ref': {'asset_sha256': asset, 'face_instance_id': instance, 'analysis_revision': 1},
        'evidence': {'backend': 'mediapipe', 'detector_model_sha256': 'b' * 64,
                     'semantic_model_sha256': 'c' * 64,
                     'landmark_digest': hashlib.sha256(np.ascontiguousarray(lm, dtype='<f4').tobytes()).hexdigest(),
                     'status': 'verified', 'source_width': w, 'source_height': h,
                     'orientation': 'exif_normalized_once'},
        'landmarks': lm.copy(), 'excluded': excluded.copy(), 'skin': None,
    }


def _recipe(horizontal=.5, size=.5, reference='auto'):
    return S.check({'version': 1, 'horizontal': horizontal, 'size': size, 'reference': reference})


def _native_double(points, roles, frame, values):
    """Independent TEST-ONLY shared Rust size/position oracle, not a fallback."""
    assert np.array_equal(roles, np.zeros_like(roles))
    assert np.array_equal(values[1:9], np.zeros(8))
    local = points - frame[4:6]
    x, y = local @ frame[:2], local @ frame[2:4]
    dx = .12 * values[0] * x
    dy = .12 * values[0] * y + .08 * frame[8] * values[9]
    return np.ascontiguousarray(dx[:, None] * frame[:2] + dy[:, None] * frame[2:4], dtype=np.float64)


def _install_native(monkeypatch):
    # Both are native-layer seams. No geometry/visibility/TPS builder is mocked.
    monkeypatch.setattr(N, 'native', lambda: object())
    monkeypatch.setattr(N, 'controls', _native_double)


def _build(monkeypatch, recipe=None, *, fixture=None, protected_boxes=()):
    _install_native(monkeypatch)
    lm, source, excluded = _fixture(**(fixture or {}))
    analysis = _analysis(lm, source.shape[:2], excluded)
    field = R.build(lm, recipe or _recipe(), source, excluded, backend='mediapipe',
                    analysis=analysis, protected_boxes=protected_boxes)
    return field, lm, source, analysis


def test_neutral_does_not_read_anatomy_source_visibility_native_or_prefix(monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('neutral touched an unrelated input')
    for name in ('_source', '_retained', '_measure', 'evidence', 'native_available', 'native_controls'):
        monkeypatch.setattr(R, name, forbidden)
    assert R.build(None, _recipe(0., 0., 'right'), None, None, backend=None, analysis=None) is None
    prefix = object()
    assert PORT.append(prefix, None, None, None, None, _recipe(0., 0., 'left')) == (prefix, None)


def test_full21_actual_points_and_independent_axis_do_not_use_iris_baseline():
    lm, source, _ = _fixture(height_difference=4.)
    measured = R._measure(R.pixels(lm, source.shape[:2]))
    assert measured['height_difference'] == 4.
    np.testing.assert_array_equal(measured['up'], [0., -1.])
    assert all(eye['points'].shape == (21, 2) for eye in measured['eyes'].values())
    changed = R.pixels(lm, source.shape[:2])
    changed[list(R.IRIS['left']), 1] += 1.
    changed[list(R.IRIS['right']), 1] -= 1.
    other = R._measure(changed)
    np.testing.assert_array_equal(other['up'], measured['up'])
    assert other['height_difference'] == measured['height_difference']


@pytest.mark.parametrize('roll', [-.25, .2])
def test_roll_is_head_relative_not_pixel_horizontal_or_eye_baseline(roll):
    lm, source, _ = _fixture(height_difference=4., roll=roll)
    measured = R._measure(R.pixels(lm, source.shape[:2]))
    assert measured['height_difference'] == pytest.approx(4., abs=3e-5)
    assert abs(measured['eyes']['left']['center'][1] - measured['eyes']['right']['center'][1]) > 10.


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
def test_horizontal_moves_both_corner_centers_to_head_relative_mean_independent_of_reference(monkeypatch, reference):
    field, lm, source, _ = _build(monkeypatch, _recipe(1., 0., reference))
    measured = R._measure(R.pixels(lm, source.shape[:2]))
    before = field.source_eyes[:, [0, 8]].mean(1)
    after = field.target_eyes[:, [0, 8]].mean(1)
    np.testing.assert_allclose(after @ measured['up'], np.full(2, float(np.mean(before @ measured['up']))), atol=1e-12)
    np.testing.assert_allclose((after - before).sum(0), [0., 0.], atol=1e-12)
    for original, target in zip(field.source_eyes, field.target_eyes):
        np.testing.assert_allclose(target - original, np.tile((target - original)[0], (21, 1)), atol=1e-12)


@pytest.mark.parametrize('left_scale,right_scale,expected', [(1.04, 1., 'left'), (1., 1.04, 'right')])
def test_auto_remeasures_each_source_and_matches_smaller_lid_area_without_copying(monkeypatch, left_scale, right_scale, expected):
    field, *_ = _build(monkeypatch, _recipe(0., 1.), fixture={'left_scale': left_scale, 'right_scale': right_scale})
    assert field.facts['size']['resolved_reference'] == expected
    ref = 0 if expected == 'left' else 1
    other = 1 - ref
    np.testing.assert_array_equal(field.target_eyes[ref], field.source_eyes[ref])
    assert R._area(field.target_eyes[other, :16]) == pytest.approx(R._area(field.source_eyes[ref, :16]), rel=1e-12)
    # The target stays on its own side; no reference-eye texture/points copied.
    assert np.linalg.norm(field.target_eyes[other, 16] - field.source_eyes[ref, 16]) > 100.


def test_manual_smaller_reference_shrinks_other_eye_and_reference_can_move_for_horizontal(monkeypatch):
    field, *_ = _build(monkeypatch, _recipe(.5, 1., 'right'))
    assert field.facts['size']['left_scale'] < 1. and field.facts['size']['right_scale'] == 1.
    shift = field.target_eyes[1] - field.source_eyes[1]
    np.testing.assert_allclose(shift, np.tile(shift[0], (21, 1)), atol=1e-12)
    assert np.linalg.norm(shift[0]) > 0.


def test_partial_size_is_linear_scale_interpolation_not_area_blending(monkeypatch):
    field, *_ = _build(monkeypatch, _recipe(0., .25))
    fact = field.facts['size']
    expected = 1. + .25 * (np.sqrt(fact['left_opening_area_px2'] / fact['right_opening_area_px2']) - 1.)
    assert fact['right_scale'] == expected
    original = field.source_eyes[1]
    center = (original[0] + original[8]) * .5
    np.testing.assert_allclose(field.target_eyes[1] - center, expected * (original - center), atol=1e-12)


def test_exact_already_symmetric_request_is_admitted_identity_with_actual_native_calls(monkeypatch):
    calls = []
    _install_native(monkeypatch)
    def record(points, roles, frame, values):
        calls.append(values.copy())
        return _native_double(points, roles, frame, values)
    monkeypatch.setattr(N, 'controls', record)
    lm, source, excluded = _fixture(left_scale=1., right_scale=1., height_difference=0.)
    field = R.build(lm, _recipe(1., 1.), source, excluded, backend='mediapipe',
                    analysis=_analysis(lm, source.shape[:2], excluded))
    assert field.state is None and len(calls) == 2
    assert all(np.array_equal(values, np.zeros(10)) for values in calls)
    assert all(fact['requested'] and fact['applied'] and fact['already_symmetric'] for fact in field.facts.values())
    np.testing.assert_array_equal(field.source_eyes, field.target_eyes)
    np.testing.assert_array_equal(field.evaluate(np.array([[200., 200.]])), [[0., 0.]])


def test_active_identity_still_refuses_missing_native(monkeypatch):
    lm, source, excluded = _fixture(left_scale=1., height_difference=0.)
    def missing(): raise RuntimeError('synthetic absent shared library')
    monkeypatch.setattr(N, 'native', missing)
    with pytest.raises(RuntimeError, match='installed shared'):
        R.build(lm, _recipe(1., 1.), source, excluded, backend='mediapipe',
                analysis=_analysis(lm, source.shape[:2], excluded))


@pytest.mark.parametrize('fixture,recipe', [({'height_difference': 20.}, _recipe(1., 0.)),
                                         ({'left_scale': 1.2}, _recipe(0., 1.)),
                                         ({'left_scale': 1.2}, _recipe(0., 1., 'right'))])
def test_requested_native_overrange_refuses_without_capping(monkeypatch, fixture, recipe):
    with pytest.raises(ValueError): _build(monkeypatch, recipe, fixture=fixture)


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('loss', ['flat_rgb', 'known_occluder'])
def test_both_eyes_need_actual_source_evidence_even_with_explicit_reference(monkeypatch, side, loss):
    _install_native(monkeypatch)
    lm, source, excluded = _fixture()
    points = R.pixels(lm, source.shape[:2])[list(R.EYES[side])]
    low, high = np.floor(points.min(0) - 10).astype(int), np.ceil(points.max(0) + 11).astype(int)
    if loss == 'flat_rgb': source[low[1]:high[1], low[0]:high[0]] = .5
    else: excluded[low[1]:high[1], low[0]:high[0]] = 1.
    with pytest.raises(ValueError, match='both visible eyes'):
        R.build(lm, _recipe(0., .5, 'left'), source, excluded, backend='mediapipe',
                analysis=_analysis(lm, source.shape[:2], excluded))


@pytest.mark.parametrize('mode', ['forehead_equals_chin', 'bridge_sideways', 'reversed_bridge', 'closed_eye', 'crossing_lid'])
def test_unresolved_anatomy_is_refused_without_repair(mode):
    lm, source, _ = _fixture()
    points = R.pixels(lm, source.shape[:2])
    if mode == 'forehead_equals_chin': points[10] = points[152]
    elif mode == 'bridge_sideways': points[197, 0] += 80.
    elif mode == 'reversed_bridge': points[197, 1] = points[1, 1] + 20.
    elif mode == 'closed_eye': points[list(R.EYES['left']), 1] = points[R.EYES['left'][0], 1]
    else:
        a, b = R.EYES['left'][3], R.EYES['left'][12]
        points[[a, b]] = points[[b, a]]
    before = points.copy()
    with pytest.raises(ValueError): R._measure(points)
    np.testing.assert_array_equal(points, before)


@pytest.mark.parametrize('factor', [0., .5, -1.])
def test_wrong_sign_zero_and_hidden_native_strength_reduction_refuse(monkeypatch, factor):
    _install_native(monkeypatch)
    monkeypatch.setattr(N, 'controls', lambda *args: _native_double(*args) * factor)
    lm, source, excluded = _fixture()
    with pytest.raises(ValueError, match='full requested correction'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=_analysis(lm, source.shape[:2], excluded))


@pytest.mark.parametrize('recipe', [_recipe(1e-300, 0.), _recipe(0., 1e-300)])
def test_nonrepresentable_strength_is_not_inflated_or_silently_zeroed(monkeypatch, recipe):
    with pytest.raises(ValueError, match='representable'): _build(monkeypatch, recipe)


def test_canonical_digest_source_evidence_and_float32_precision_are_enforced(monkeypatch):
    field, lm, source, analysis = _build(monkeypatch)
    precise = lm.astype(np.float64) + 1e-12
    same = R.build(precise, _recipe(), source, analysis['excluded'], backend='mediapipe',
                   analysis={**analysis, 'landmarks': precise})
    np.testing.assert_array_equal(same.source_eyes, field.source_eyes)
    changed = deepcopy(analysis); changed['landmarks'][263, 0] += .001
    with pytest.raises(ValueError, match='exact retained'):
        R.build(lm, _recipe(), source, analysis['excluded'], backend='mediapipe', analysis=changed)
    excluded = analysis['excluded'].copy(); excluded[0, 0] = 1.
    with pytest.raises(ValueError, match='retained same-source'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=analysis)


def test_same_owner_snapshot_rebuilds_geometry_on_each_grid_without_rewriting_evidence(monkeypatch):
    import cv2
    from lumaretouch_engine import people_state as P, people_snapshot as SNAP
    from lumaretouch_engine.people_geometry import AutomaticField
    from lumaretouch_engine.ops.deform import KINDS
    full, lm, source, analysis = _build(monkeypatch)
    state = P.empty()
    face = P.new_face('a' * 64, [.2, .1, .8, .9], analysis['evidence'])
    face['face_instance_id'], face['analysis_revision'] = 'test-face', 1
    state['faces']['test-face'] = face
    snapshot = SNAP.capture(state, 'a' * 64, {'test-face': analysis})
    proxy_shape = (384, 384)
    retained, asset, observations = SNAP.at_dimensions(snapshot, proxy_shape)
    proxy = cv2.resize(source, (proxy_shape[1], proxy_shape[0]), interpolation=cv2.INTER_LINEAR)
    observed = observations['test-face']
    assert observed['evidence'] == analysis['evidence']
    assert (observed['evidence']['source_height'], observed['evidence']['source_width']) == (512, 512)
    np.testing.assert_array_equal(observed['landmarks'], lm)
    assert observed['excluded'].shape == proxy_shape and asset == 'a' * 64
    automatic = AutomaticField(lm, {key: 0. for key in KINDS}, proxy_shape)
    prefix = FaceGeometry('test-face', proxy_shape, automatic, (None,) * 4)
    composed, facts = PORT.append(prefix, retained, P.face_ref(face), observed, proxy, _recipe())
    rebuilt = composed.fields[-1]
    np.testing.assert_allclose(rebuilt.source_eyes, full.source_eyes * .75, atol=1e-12)
    np.testing.assert_allclose(rebuilt.target_eyes, full.target_eyes * .75, atol=1e-10)
    assert facts['size']['resolved_reference'] == full.facts['size']['resolved_reference']
    stale = deepcopy(observed)
    stale['face_ref']['analysis_revision'] += 1
    with pytest.raises(ValueError, match='owner/evidence'):
        PORT.append(prefix, retained, P.face_ref(face), stale, proxy, _recipe())


def test_source_and_targets_all21_and_identity_polygons_are_preserved(monkeypatch):
    field, *_ = _build(monkeypatch, _recipe(0., .5))
    actual = field.evaluate(field.target_eyes.reshape(-1, 2))
    expected = (field.target_eyes - field.source_eyes).reshape(-1, 2)
    error = np.linalg.norm(actual - expected, axis=1)
    motion = np.linalg.norm(expected, axis=1)
    assert np.all(error <= np.where(motion > 0., motion * 1e-4, 1e-7))
    for polygon in field.protected:
        np.testing.assert_array_equal(field.evaluate(polygon), np.zeros_like(polygon))
    for value in (field.source_eyes, field.target_eyes, field.requested_P, field.requested_D):
        assert not value.flags.writeable
        with pytest.raises(ValueError): value.setflags(write=True)


def test_complete_support_and_feather_protect_foreign_faces(monkeypatch):
    field, _, source, _ = _build(monkeypatch)
    center, _, radius = field.windows[0]
    point = center + [radius - .1, 0.]
    box = tuple(np.r_[point - .1, point + .1] /
                [source.shape[1] - 1, source.shape[0] - 1, source.shape[1] - 1, source.shape[0] - 1])
    with pytest.raises(ValueError, match='another retained face'):
        _build(monkeypatch, protected_boxes=(box,))


def test_whole_support_source_margin_is_refused_not_clipped(monkeypatch):
    _install_native(monkeypatch)
    lm, source, excluded = _fixture()
    # Move the complete coherent face toward the left boundary. Lids remain
    # inside while their requested complete feather leaves the source margin.
    lm[:, 0] -= 155. / 512.
    with pytest.raises(ValueError, match='source margin'):
        R.build(lm, _recipe(), source, excluded, backend='mediapipe', analysis=_analysis(lm, source.shape[:2], excluded))


class _SyntheticField:
    """Explicit composition double, not anatomy or native implementation."""
    state = ('synthetic',)
    def __init__(self, function, resident=32): self.function, self.resident = function, resident
    def evaluate(self, points): return self.function(points)
    def resident_bytes(self): return self.resident


class _MetadataPrefix(FaceGeometry):
    def resident_bytes(self): return super().resident_bytes() + 819


def test_outermost_prefix4_through11_preserves_mouthslot3_and_metadata():
    zero = _SyntheticField(lambda q: np.zeros_like(q), resident=17)
    mouth = _SyntheticField(lambda q: q * [.01, .02], resident=41)
    for count in range(4, 12):
        fields = (None, None, None, mouth) + (zero,) * (count - 4)
        prefix = _MetadataPrefix('synthetic', (512, 512), zero, fields)
        correction = _SyntheticField(lambda q: np.tile([0., 2.], (len(q), 1)), resident=83)
        wrapper = PORT.EyeSymmetry('synthetic', (512, 512), zero, (*fields, correction), prefix, ())
        q = np.array([[190., 240.], [210., 260.]])
        expected = correction.evaluate(q) + prefix.evaluate(q - correction.evaluate(q))
        np.testing.assert_array_equal(wrapper.evaluate(q), expected)
        assert wrapper.prefix is prefix and wrapper.fields[3] is mouth
        assert all(a is b for a, b in zip(wrapper.fields[:-1], fields))
        assert wrapper.resident_bytes() == prefix.resident_bytes() + 83 + 256


@pytest.mark.parametrize('stage', ['output', 'intermediate', 'final'])
def test_composition_guards_every_foreign_face_footprint(stage):
    q = np.array([[150., 200.]])
    correction = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (512, 512), prior, (None,) * 4)
    point = {'output': [150., 200.], 'intermediate': [150., 190.], 'final': [150., 180.]}[stage]
    box = tuple(np.r_[np.asarray(point) - .1, np.asarray(point) + .1] / 511.)
    wrapper = PORT.EyeSymmetry('synthetic', (512, 512), prior, (*prefix.fields, correction), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)


def test_cancellation_cannot_hide_intermediate_foreign_or_invalid_source_coordinates():
    q = np.array([[150., 200.]])
    correction = _SyntheticField(lambda p: np.tile([0., 10.], (len(p), 1)))
    prior = _SyntheticField(lambda p: np.tile([0., -10.], (len(p), 1)))
    prefix = FaceGeometry('synthetic', (512, 512), prior, (None,) * 4)
    box = (149.9 / 511., 189.9 / 511., 150.1 / 511., 190.1 / 511.)
    wrapper = PORT.EyeSymmetry('synthetic', (512, 512), prior, (*prefix.fields, correction), prefix, (box,))
    with pytest.raises(ValueError, match='another retained face'): wrapper.evaluate(q)
    huge = _SyntheticField(lambda p: np.tile([0., 250.], (len(p), 1)))
    wrapper = PORT.EyeSymmetry('synthetic', (512, 512), prior, (*prefix.fields, huge), prefix, ())
    with pytest.raises(ValueError, match='source margin'): wrapper.evaluate(q)


def test_invalid_composition_preserves_prefix_fields_and_input():
    q = np.array([[150., 200.]])
    before = q.copy()
    zero = _SyntheticField(lambda p: np.zeros_like(p))
    prefix = _MetadataPrefix('synthetic', (512, 512), zero, (None,) * 4)
    bad = _SyntheticField(lambda p: np.full_like(p, np.nan))
    wrapper = PORT.EyeSymmetry('synthetic', (512, 512), zero, (*prefix.fields, bad), prefix, ())
    with pytest.raises(ValueError, match='invalid symmetry pullback'): wrapper.evaluate(q)
    np.testing.assert_array_equal(q, before)
    assert prefix.fields == (None,) * 4
