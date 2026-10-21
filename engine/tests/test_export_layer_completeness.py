"""Unbuilt active portrait recipes must never disappear from export accounting."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_export_per_image_recipe import _mk_session, _batch_snap


@pytest.mark.parametrize("layer,key", [("deform", "slim_face"), ("enhance", "sclera")])
def test_nonzero_unbuilt_layer_is_reported_not_silently_omitted(layer, key):
    snap = _batch_snap()
    snap[layer] = {"amounts": {key: .3}, "built": False}
    snap[layer + "_defer"] = False
    before = deepcopy(snap[layer])
    spec, skipped = _mk_session([])._export_snapshot(snap, 64, 96, for_document=True)
    assert any(item.startswith(layer + "（") for item in skipped)
    assert snap[layer] == before


@pytest.mark.parametrize("layer,key", [("deform", "slim_face"), ("enhance", "sclera")])
def test_deferred_layer_remains_rebuildable_from_selected_landmarks(layer, key):
    snap = _batch_snap()
    snap[layer] = {"amounts": {key: .3}, "built": False}
    snap[layer + "_defer"] = True
    landmarks = np.zeros((478, 3), np.float32)
    snap["precompute"] = SimpleNamespace(landmarks=landmarks)
    spec, skipped = _mk_session([])._export_snapshot(snap, 64, 96, for_document=True)
    assert not any(item.startswith(layer + "（") for item in skipped)
    applied = spec.deform_amounts if layer == "deform" else spec.enhance
    assert applied == {key: .3}
    np.testing.assert_array_equal(spec.landmarks, landmarks)


def test_neutral_unbuilt_layers_are_not_false_missing_features():
    snap = _batch_snap()
    snap["deform"] = {"amounts": {"slim_face": 0.}, "built": False}
    snap["enhance"] = {"amounts": {"sclera": 0.}, "built": False}
    _, skipped = _mk_session([])._export_snapshot(snap, 64, 96, for_document=True)
    assert not any(item.startswith(("deform（", "enhance（")) for item in skipped)
