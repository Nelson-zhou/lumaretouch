import numpy as np
import pytest
from lumaretouch_engine.semantic_masks import skin_from_multiclass


def test_each_class_maps_to_correct_skin_semantics():
    probabilities = np.eye(6, dtype=np.float32).reshape(6, 1, 6)
    np.testing.assert_array_equal(skin_from_multiclass(probabilities), [[0, 0, 1, 1, 0, 0]])


def test_soft_boundary_is_preserved_and_output_does_not_alias_runtime():
    p = np.array([.1, .1, .2, .3, .2, .1], dtype=np.float32)[:, None, None]
    out = skin_from_multiclass(p)
    np.testing.assert_allclose(out, [[.5]])
    p[:] = 0
    np.testing.assert_allclose(out, [[.5]])


@pytest.mark.parametrize("count", [0, 1, 2, 5, 7])
def test_old_person_mask_or_unknown_model_rejected(count):
    with pytest.raises(ValueError, match="six"):
        skin_from_multiclass([np.zeros((2, 3))] * count)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.1])
def test_bad_probabilities_rejected(bad):
    p = np.zeros((6, 2, 3), dtype=np.float32); p[0] = 1; p[1, 0, 0] = bad
    with pytest.raises(ValueError, match="finite probabilities"):
        skin_from_multiclass(p)


def test_logits_and_bad_sum_not_renormalized():
    with pytest.raises(ValueError, match="sum to one"):
        skin_from_multiclass(np.full((6, 2, 3), .5))


def test_mismatched_shapes_rejected():
    p = [np.zeros((2, 3)) for _ in range(6)]; p[0] = np.zeros((3, 2))
    with pytest.raises(ValueError, match="matching shapes"):
        skin_from_multiclass(p)


def test_singleton_channels_supported():
    p = np.zeros((6, 2, 3, 1)); p[3] = 1
    np.testing.assert_array_equal(skin_from_multiclass(p), np.ones((2, 3)))


def test_edit_weight_protects_uncertain_and_non_skin_without_hard_edge():
    from lumaretouch_engine.semantic_masks import skin_edit_weight
    p = np.array([[0, .03, .49, .5, .5001, .75, 1]], dtype=np.float32)
    out = skin_edit_weight(p)
    np.testing.assert_allclose(out, [[0, 0, 0, 0, .0002, .5, 1]], atol=1e-7)
    assert out.dtype == np.float32


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -.01, 1.01])
def test_edit_weight_rejects_invalid_probability(bad):
    from lumaretouch_engine.semantic_masks import skin_edit_weight
    with pytest.raises(ValueError): skin_edit_weight([[bad]])


def test_face_backend_uses_semantic_skin_not_person_channel(monkeypatch):
    import sys
    from types import SimpleNamespace
    from lumaretouch_engine.face import MediaPipeFace, NUM_LANDMARKS
    # The six columns represent each class at confidence one. Whole-person
    # segmentation would wrongly include columns 1 (hair) and 4 (clothes).
    masks = np.repeat(np.eye(6, dtype=np.float32)[:, None, :], 3, axis=1)
    channels = [SimpleNamespace(numpy_view=lambda a=a: a) for a in masks]
    landmarks = [SimpleNamespace(x=.5, y=.5, z=0) for _ in range(NUM_LANDMARKS)]
    detect = SimpleNamespace(detect=lambda _: SimpleNamespace(face_landmarks=[landmarks]))
    segment = SimpleNamespace(segment=lambda _: SimpleNamespace(confidence_masks=channels))
    monkeypatch.setitem(sys.modules, 'mediapipe', SimpleNamespace(
        Image=lambda **kw: kw, ImageFormat=SimpleNamespace(SRGB=1)))
    backend = MediaPipeFace.__new__(MediaPipeFace)
    backend._ensure = lambda: (detect, segment)
    backend.model_paths = {'multiclass': '/test/model'}
    result = backend(np.zeros((3, 6, 3), dtype=np.uint8))
    np.testing.assert_array_equal(result.masks['skin'], np.tile([0, 0, 1, 1, 0, 0], (3, 1)))
    assert result.landmarks.shape == (478, 3)


def test_face_metadata_exposes_empty_skin_without_invalidating_landmarks():
    from lumaretouch_engine.face import SyntheticFace
    pc = SyntheticFace()(np.zeros((12, 16, 3), dtype=np.uint8))
    pc.masks["skin"][:] = 0
    meta = pc.meta(12, 16)
    assert meta["mask_nonzero_pixels"]["skin"] == 0
    assert meta["num_landmarks"] == 478
