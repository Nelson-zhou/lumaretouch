# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored, UNRUN contracts, not photographic or executable acceptance evidence.

Synthetic coordinates below isolate mathematical/source-binding contracts only.
They do not certify a landmark backend, semantic model or visible human anatomy.
The implementation task did not import product modules or execute these tests.
"""
from copy import deepcopy

import numpy as np
import pytest

from lumaretouch_engine import face_contour_state as S
from lumaretouch_engine import face_contour_geometry as G
from lumaretouch_engine import face_contour_runtime as R
from lumaretouch_engine.face_contour_field import FaceContourField


def _fixture(shape=(401, 401)):
    """Deterministic geometric test double, explicitly not an analysis producer."""
    h, w = shape
    lm = np.full((478, 3), .5, np.float64)
    angle = np.arange(len(G.FACE_OVAL)) * (2 * np.pi / len(G.FACE_OVAL))
    lm[list(G.FACE_OVAL), :2] = np.stack((.5 + .25 * np.sin(angle), .5 - .34 * np.cos(angle)), axis=1)
    for ids, cx, rx, ry, phase in (
            (G.EYES[0], .3875, .0525, .0225, np.pi),
            (G.EYES[1], .6125, .0525, .0225, 0.),
            (G.BROW_RIGHT, .3875, .0675, .0125, 0.),
            (G.BROW_LEFT, .6125, .0675, .0125, 0.),
            (G.LIPS, .5, .0875, .0225, np.pi)):
        cy = .65 if ids == G.LIPS else .35 if ids in (G.BROW_LEFT, G.BROW_RIGHT) else .415
        a = phase + np.arange(len(ids)) * (2 * np.pi / len(ids))
        lm[list(ids), :2] = np.stack((cx + rx * np.cos(a), cy + ry * np.sin(a)), axis=1)
    for i, index in enumerate(G.NOSE):
        lm[index, :2] = [.5 + .015 * (i % 3 - 1), .45 + .01 * i]
    lm[1, :2] = [.5, .55]
    for center, ids in (([.3875, .415], range(468, 473)), ([.6125, .415], range(473, 478))):
        lm[ids.start, :2] = center
        for i, index in enumerate(tuple(ids)[1:]):
            a = i * np.pi / 2
            lm[index, :2] = np.asarray(center) + [.009 * np.cos(a), .009 * np.sin(a)]
    yy, xx = np.mgrid[:h, :w]
    luma = .35 + .12 * (xx + yy) / (h + w) + .008 * np.sin(xx * .14)
    source = np.repeat(luma[..., None], 3, axis=2).astype(np.float32)
    return lm.astype(np.float32), source, np.ones((h, w), np.float32), np.zeros((h, w), np.float32)


def _recipe(key='jaw', side='left', value=.2):
    recipe = S.neutral()
    recipe[key] = {'linked': False, 'left': 0., 'right': 0.}
    recipe[key][side] = value
    return S.check(recipe)


def _analysis(lm, shape, skin, excluded):
    h, w = shape
    return {
        'face_ref': {'asset_sha256': 'a' * 64, 'face_instance_id': 'test-face', 'analysis_revision': 1},
        'evidence': {'backend': 'mediapipe', 'detector_model_sha256': 'b' * 64,
                     'semantic_model_sha256': 'c' * 64, 'landmark_digest': R._landmark_digest(lm),
                     'status': 'verified', 'source_width': w, 'source_height': h,
                     'orientation': 'exif_normalized_once'},
        'landmarks': lm.copy(), 'excluded': excluded.copy(), 'skin': skin.copy(),
        'face_skin': skin.copy(), 'face_skin_observation': {
            'contract': 'mediapipe-face-skin-edit-weight-v1', 'source_sha256': 'a' * 64,
            'semantic_model_sha256': 'c' * 64, 'producer_width': w, 'producer_height': h},
    }


def _native_double(points, roles, sides, frame, values):
    """Unit-test oracle only; production must never fall back to this formula."""
    values = np.asarray(values).reshape(3, 2)
    side_values = np.where(sides[:, None] > 0, values[:, 0], values[:, 1])
    amount = np.sum(roles * side_values * [1., -1., 1.], axis=1) * sides * frame[6] * .035
    return np.ascontiguousarray(amount[:, None] * frame[:2], dtype=np.float64)


def _admit_for_control_tests(lm, recipe, source, skin, excluded):
    # Deliberately bypass photometric admission only for isolated control tests.
    r = S.check(recipe)
    right, up, center, width = G.frame(lm)
    facts = {f'{key}/{side}': {
        'control': key, 'side': side, 'requested': r[key][side] != 0,
        'applied': r[key][side] != 0, 'reason': None, 'support_px': 0,
    } for key in S.KEYS for side in S.SIDES}
    return facts, right, up, center, width


def _controls(monkeypatch, recipe=None, protected_boxes=()):
    lm, source, skin, excluded = _fixture()
    monkeypatch.setattr(G, 'native_controls', _native_double)
    monkeypatch.setattr(G, 'evidence', _admit_for_control_tests)
    out = G.build_controls(lm, source.shape[:2], recipe or _recipe(), source, excluded,
                           backend='mediapipe', skin=skin, protected_boxes=protected_boxes)
    return lm, source, out


def test_verified_oval_chains_not_legacy_lip_chain():
    assert len(G.FACE_OVAL) == 36
    edges = {frozenset((a, b)) for a, b in zip(G.FACE_OVAL, (*G.FACE_OVAL[1:], G.FACE_OVAL[0]))}
    for side, ids in G.CHAINS.items():
        assert len(ids) == 11 and set(ids).issubset(G.FACE_OVAL)
        assert all(frozenset(edge) in edges for edge in zip(ids, ids[1:]))
        assert not set(ids).intersection(G.LIPS)
    assert G.CHAINS['right'] == (21, 162, 127, 234, 93, 132, 58, 172, 136, 150, 149)
    assert G.CHAINS['left'] == (251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378)
    assert G.ROLE_WEIGHTS[0] == G.ROLE_WEIGHTS[-1] == (0., 0., 0.)
    assert not set(G.ANCHORS).intersection(G.FACE_OVAL)


def test_pixel_centers_use_dimension_minus_one_without_legacy_change():
    lm = np.zeros((478, 3), np.float32)
    lm[0, :2] = 1
    assert np.array_equal(G.pixels(lm, (81, 101))[0], [100., 80.])
    with pytest.raises(ValueError):
        G.pixels(lm, (1, 100))


@pytest.mark.parametrize('key,direction', [('temple', 1.), ('cheekbone', -1.), ('jaw', 1.)])
@pytest.mark.parametrize('side,sign', [('left', 1.), ('right', -1.)])
def test_control_is_true_destination_pullback_and_opposite_side_pinned(monkeypatch, key, direction, side, sign):
    lm, source, (P, D, meta) = _controls(monkeypatch, _recipe(key, side, .25))
    src = G.pixels(lm, source.shape[:2])
    # Raw pre-dedupe controls preserve the exact source-coordinate identity.
    count = len(G.FACE_OVAL)
    assert np.allclose(meta['requested_P'][:count] - meta['requested_D'][:count], src[list(G.FACE_OVAL)])
    peak = {'temple': 1, 'cheekbone': 3, 'jaw': 7}[key]
    index = G.FACE_OVAL.index(G.CHAINS[side][peak])
    right, _, _, width = G.frame(src)
    assert np.allclose(meta['requested_D'][index], right * width * .035 * .25 * direction * sign)
    other = 'right' if side == 'left' else 'left'
    rows = [G.FACE_OVAL.index(i) for i in G.CHAINS[other]]
    assert np.array_equal(meta['requested_D'][rows], np.zeros((len(rows), 2)))
    assert set(meta['controls']) == {f'{k}/{s}' for k in S.KEYS for s in S.SIDES}


def test_native_zero_does_not_silently_cancel_nonzero_request(monkeypatch):
    lm, source, skin, excluded = _fixture()
    monkeypatch.setattr(G, 'evidence', _admit_for_control_tests)
    monkeypatch.setattr(G, 'native_controls', lambda points, *args: np.zeros_like(points))
    with pytest.raises(ValueError, match='native request mismatch'):
        G.build_controls(lm, source.shape[:2], _recipe(), source, excluded, backend='mediapipe', skin=skin)


def test_mirrored_rotation_retains_person_relative_frame():
    lm, source, _, _ = _fixture()
    p = G.pixels(lm, source.shape[:2])
    right, up, center, width = G.frame(p)
    a = .37
    rotation = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    rotated = (p - 200) @ rotation.T + 200
    r2, u2, c2, w2 = G.frame(rotated)
    assert np.allclose(r2, rotation @ right)
    assert np.allclose(u2, rotation @ up)
    assert np.allclose(c2, rotation @ (center - 200) + 200)
    assert w2 == pytest.approx(width)
    mirrored = p * [-1., 1.] + [400., 0.]
    rm, um, cm, wm = G.frame(mirrored)
    assert np.allclose(rm, right * [-1., 1.])
    assert np.allclose(um, up * [-1., 1.])
    assert wm == pytest.approx(width)


@pytest.mark.parametrize('value', [None, np.zeros((401, 401), np.float32)])
def test_landmarks_alone_never_authorize_visible_contour(value):
    lm, source, _, excluded = _fixture()
    facts, *_ = G.evidence(G.pixels(lm, source.shape[:2]), _recipe(), source, value, excluded)
    assert facts['jaw/left']['requested']
    assert not facts['jaw/left']['applied']
    assert facts['jaw/left']['reason']


def test_atomic_refusal_keeps_both_sides_unapplied(monkeypatch):
    lm, source, skin, excluded = _fixture()
    recipe = _recipe()
    recipe['jaw']['right'] = .2
    def reject_one(*args):
        facts, *rest = _admit_for_control_tests(*args)
        facts['jaw/right'].update(reason='occluded', applied=False)
        return facts, *rest
    monkeypatch.setattr(G, 'evidence', reject_one)
    monkeypatch.setattr(G, 'native_controls', lambda *args: pytest.fail('native must not run after admission refusal'))
    with pytest.raises(G.FaceContourRefusal) as result:
        G.build_controls(lm, source.shape[:2], recipe, source, excluded, backend='mediapipe', skin=skin)
    assert not any(f['applied'] for f in result.value.facts.values())
    assert result.value.facts['jaw/left']['reason'] == 'atomic_request_refused'


def test_foreign_box_in_feather_halo_refuses_not_mask_copy(monkeypatch):
    _, source, (_, _, meta) = _controls(monkeypatch)
    center, flat, radius = meta['windows'][0]
    # Outside the unit-weight core but inside complete compact support.
    point = center + [(flat + radius) * .5, 0]
    h, w = source.shape[:2]
    box = np.r_[point - .5, point + .5] / [w - 1, h - 1, w - 1, h - 1]
    with pytest.raises(G.FaceContourRefusal, match='complete_influence_window'):
        _controls(monkeypatch, protected_boxes=[box])


def test_circle_box_overlap_checks_full_window_and_pixel_footprint():
    window = (np.array([100., 100.]), 5., 20.)
    assert G.window_overlaps_box(window, np.array([120.1, 99., 122., 101.]))
    assert not G.window_overlaps_box(window, np.array([122., 99., 124., 101.]))
    with pytest.raises(ValueError):
        G._boxes([[.8, .2, .1, .7]], (100, 100))


def test_runtime_neutral_does_not_require_source_masks_or_library(monkeypatch):
    monkeypatch.setattr(R, 'require_analysis', lambda *args: pytest.fail('neutral cannot inspect analysis'))
    assert R.build(None, S.neutral(), None, None, backend='missing', analysis=None) is None


def test_runtime_requires_exact_landmark_bytes_and_named_skin_observation():
    lm, source, skin, excluded = _fixture()
    analysis = _analysis(lm, source.shape[:2], skin, excluded)
    assert R.require_analysis(lm, analysis, source.shape[:2], excluded) is analysis['face_skin']
    forged = deepcopy(analysis)
    forged['landmarks'][1, 0] += .001
    with pytest.raises(ValueError, match='exact retained'):
        R.require_analysis(lm, forged, source.shape[:2], excluded)
    for key in ('face_skin', 'face_skin_observation'):
        missing = deepcopy(analysis)
        del missing[key]
        with pytest.raises(ValueError):
            R.require_analysis(lm, missing, source.shape[:2], excluded)
    wrong = deepcopy(analysis)
    wrong['face_skin_observation']['source_sha256'] = 'd' * 64
    with pytest.raises(ValueError):
        R.require_analysis(lm, wrong, source.shape[:2], excluded)
    wrong = excluded.copy(); wrong[0, 0] = 1
    with pytest.raises(ValueError, match='exclusion'):
        R.require_analysis(lm, analysis, source.shape[:2], wrong)


def _simple_field_meta(P, D):
    # Deliberately distant feature geometry, isolating the TPS math contract.
    lm = np.full((478, 2), 140., np.float64)
    return {'controls': {}, 'merged': 0, 'windows': [(np.array([40., 40.]), 25., 50.)],
            'landmarks': lm, 'width': 100., 'pinned_segments': np.empty((0, 2, 2)),
            'requested_P': P.copy(), 'requested_D': D.copy(),
            'source_contour': P - D, 'target_contour': P.copy()}


def test_tps_final_control_displacement_band_equivalence_and_compact_identity():
    P = np.array([[25., 25.], [55., 25.], [55., 55.], [25., 55.], [150., 150.], [150., 0.], [0., 150.]])
    D = np.array([[.25, 0.], [.25, 0.], [.25, 0.], [.25, 0.], [0., 0.], [0., 0.], [0., 0.]])
    field = FaceContourField(P, D, _simple_field_meta(P, D), (201, 201))
    assert np.allclose(field.evaluate(P), D, atol=1e-6)
    assert np.allclose(P - field.evaluate(P), P - D, atol=1e-6)
    outside = np.array([[100., 40.], [200., 200.], [-10., -10.]])
    assert np.array_equal(field.evaluate(outside), np.zeros_like(outside))
    q = np.array([[x, 38.75] for x in np.linspace(1, 110, 102)])
    whole = field.evaluate(q)
    field.batch = 7
    assert np.array_equal(field.evaluate(q), whole)
    assert field.resident_bytes() > field.landmarks.nbytes
    assert field.minimum_jacobian >= .20


@pytest.mark.parametrize('amount', [.25, 1e-10])
def test_post_protection_cancellation_is_a_refusal_not_success(amount):
    P = np.array([[25., 25.], [55., 25.], [55., 55.], [25., 55.], [150., 150.]])
    D = np.array([[amount, 0.], [amount, 0.], [amount, 0.], [amount, 0.], [0., 0.]])
    meta = _simple_field_meta(P, D)
    meta['pinned_segments'] = np.array([[[20., 25.], [60., 25.]]])
    with pytest.raises(ValueError, match='silent reduction'):
        FaceContourField(P, D, meta, (201, 201))


def test_fold_check_refuses_orientation_reversal():
    field = object.__new__(FaceContourField)
    field.width = 100.; field.windows = ()
    field.source_contour = field.target_contour = np.array([[1., 1.], [2., 2.]])
    field.evaluate = lambda x: np.asarray(x) * [2., 0.]
    with pytest.raises(ValueError, match='fold'):
        field._check_fold(field.source_contour)


def test_sampling_composes_pullbacks_not_forward_field_addition():
    from lumaretouch_engine.people_geometry import FaceGeometry
    class Field:
        state = True
        def __init__(self, scale): self.scale = np.asarray(scale)
        def evaluate(self, p): return p * self.scale
        def resident_bytes(self): return self.scale.nbytes
    base, contour = Field([.12, .03]), Field([.05, .08])
    geometry = FaceGeometry('test-face', (10, 10), base, (contour,))
    points = np.array([[1.25, 2.5], [5., 7.]])
    first = points - base.evaluate(points)
    expected = points - (first - contour.evaluate(first))
    assert np.allclose(geometry.evaluate(points), expected)
    assert not np.allclose(expected, base.evaluate(points) + contour.evaluate(points))
