"""AUTHORED / UNRUN. Synthetic contract fixtures, not photo acceptance."""
from pathlib import Path
import numpy as np
import pytest
from lumaretouch_engine import red_eye_apply as R, under_eye_layer as U
from lumaretouch_engine import enhance_scope as S, people_algorithms as A
from lumaretouch_engine.ops import enhance as H


def landmarks(radius=6):
    h, w = 64, 96
    lm = np.full((478, 3), .5, np.float32)
    for cx, ring, iris, rim in ((28, H.EYE_RING_LEFT, H.IRIS_LEFT, H.IRIS_RIM_LEFT),
                                (68, H.EYE_RING_RIGHT, H.IRIS_RIGHT, H.IRIS_RIM_RIGHT)):
        lm[iris, :2] = [cx/w, 30/h]
        for i, index in enumerate(ring):
            angle = .017 + i*2*np.pi/len(ring)
            lm[index, :2] = [(cx+12*np.cos(angle))/w, (30+7*np.sin(angle))/h]
        for i, index in enumerate(rim):
            angle = i*2*np.pi/len(rim)
            lm[index, :2] = [(cx+radius*np.cos(angle))/w, (30+radius*np.sin(angle))/h]
    return lm


def test_support_is_central_not_full_iris_or_whole_eye():
    weight, facts = R.support(landmarks(), 64, 96)
    yy, xx = np.mgrid[:64, :96]
    outside = ((np.hypot(xx+.5-28, yy+.5-30) >= .65*6+1e-5) &
               (np.hypot(xx+.5-68, yy+.5-30) >= .65*6+1e-5))
    assert not np.any(weight[outside])
    assert np.any(weight) and all(f['reason'] is None for f in facts)
    assert H.SUBS == ('sclera', 'iris', 'teeth')
    assert 'red_eye' not in H.PIXEL_KEYS and U.KEYS[-1] == 'red_eye'


def test_tiny_geometry_refuses_instead_of_inventing_a_pupil():
    with pytest.raises(ValueError, match='中央虹膜'): R.support(landmarks(.4), 64, 96)


def test_red_only_does_not_require_or_call_legacy_opencv_filters(monkeypatch):
    from lumaretouch_engine import red_eye_native as N
    monkeypatch.setattr(U.EYES, 'cv2', None)
    monkeypatch.setattr(U.EYES, 'apply', lambda *_: pytest.fail('Called under-eye solver'))
    monkeypatch.setattr(U.DETAIL, 'apply', lambda *_: pytest.fail('Called sclera/vein solver'))
    monkeypatch.setattr(N, 'apply', lambda rgb, mask, amount, **kw: rgb.copy())
    source = np.full((64,96,3), .5, np.float32)
    layer = U.UnderEyeLayer((0,0,64,96), source, landmarks()[:,:2]*[96,64])
    delta = layer.solve({'red_eye': .5})
    assert not np.any(delta)
    assert layer.facts['red_eye']['reason'] == 'no_red_dominant_central_iris_pixels'
    assert layer.facts['red_eye']['geom_px'] > 0


def test_neutral_avoids_native_and_legacy_algorithms(monkeypatch):
    monkeypatch.setattr(R, 'correct', lambda *_args, **_kwargs: pytest.fail('Neutral native call'))
    source = np.full((64,96,3), .5, np.float32)
    assert U.correct(source, landmarks(), [0]*len(U.KEYS)) is source


@pytest.mark.parametrize('value', [True, '0.5', None, -.1, 1.1, float('nan')])
def test_red_eye_rejects_invalid_scalar(value):
    with pytest.raises(ValueError): H.check_amounts({'red_eye': value})


def test_sparse_old_recipe_stays_neutral_and_new_leaf_is_scalar_only():
    assert H.check_amounts({'iris': .2})['red_eye'] == 0
    assert '/red_eye' in A.defaults()[A.ENHANCE]
    assert S.check_params({'recipe': {'version': 1, 'amounts': {'red_eye': .6}}})['recipe']['amounts']['red_eye'] == .6
    with pytest.raises(ValueError): S.check_params({'recipe': {'version': 1, 'amounts': {'red_eye': .6, 'mask': []}}})


def test_export_and_replay_do_not_silently_skip_red_eye():
    root = Path(__file__).resolve().parents[1]/'src'/'lumaretouch_engine'
    assert 'ENH.RED_EYE.active(enh_amounts)' in (root/'export_recipe.py').read_text()
    assert 'ENH.RED_EYE.active(self._enhance.get("amounts",{}))' in (root/'server.py').read_text()
    assert 'under_layer.solve(spec.enhance, cancelled=tone_cancelled)' in (root/'export.py').read_text()
