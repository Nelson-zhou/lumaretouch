"""Local Qoder execution required. Synthetic contracts are not portrait acceptance.

Requires the packaged Rust kernel + OpenCV + torch. No model loading/inference.
"""
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import facial_wrinkle_layer as L
from lumaretouch_engine import facial_wrinkle_state as S
from lumaretouch_engine.facial_wrinkle_native import merge


def source():
    image = np.full((64, 96, 3), .5, np.float32)
    image[12:52, 30:33] = .32
    image[12:52, 65:68] = .37
    return image


def prepared(monkeypatch):
    image = source()
    masks = {}
    for i, key in enumerate(S.KEYS):
        mask = np.zeros(image.shape[:2], np.float32)
        mask[8:56, 20:76] = 1
        masks[key] = mask
    facts = {key: {'geom_px': 2688, 'gated_px': 2688, 'reason': None, 'sides': {}} for key in S.KEYS}
    monkeypatch.setattr(L, 'geometry', lambda *a: (masks, facts, 40.))
    layer = L.FacialWrinkleLayer((0, 0, 64, 96), image, np.zeros((478, 2), np.float32),
                                np.ones((64, 96), np.float32), backend='mediapipe')
    return layer


def test_neutral_needs_no_native_kernel_or_face_backend():
    image = source()
    layer = L.FacialWrinkleLayer((0, 0, 64, 96), image, np.zeros((478, 2), np.float32), None, backend='synthetic')
    assert layer.solve({}) is None
    assert layer.solve({S.LINK_KEY: 1}) is None
    assert np.array_equal(image, layer.source)
    assert layer.masks is None


def test_max_merge_overlap_and_atomic_rejection():
    proposal = np.full((4, 4), 6, np.float32); mask = np.ones((4, 4), np.float32); out = np.zeros((4, 4), np.float32)
    mask[0] = 0
    merge(proposal, mask, .5, out); once = out.copy()
    merge(proposal, mask, .5, out)
    assert np.array_equal(out, once) and np.max(out) == 3 and not np.any(out[0])
    bad = proposal.copy(); bad[-1, -1] = np.nan
    with pytest.raises(ValueError): merge(bad, mask, 1, out)
    assert np.array_equal(out, once)


def test_frozen_source_overlap_no_double_lift_and_zero_return(monkeypatch):
    layer = prepared(monkeypatch)
    original = layer.source.copy()
    one = layer.solve({'wrinkle_forehead': 1}).copy()
    two = layer.solve({'wrinkle_forehead': 1, 'wrinkle_glabellar': 1}).copy()
    assert np.array_equal(one, two)
    assert not np.any(two[:8]) and not np.any(two[56:])
    assert not np.any(two[:, :20]) and not np.any(two[:, 76:])
    assert np.array_equal(original, layer.source)
    assert layer.solve({}) is None
    assert np.array_equal(layer.solve({'wrinkle_forehead': 1}), one)


def test_unlock_only_never_recalculates_or_changes_pixels(monkeypatch):
    layer = prepared(monkeypatch)
    delta = layer.solve({'wrinkle_forehead': .7})
    assert layer.solve({'wrinkle_forehead': .7, S.LINK_KEY: 1}) is delta


def test_prepared_full_face_tile_crops_are_exact(monkeypatch):
    import torch
    layer = prepared(monkeypatch)
    delta = layer.solve({'wrinkle_forehead': 1})
    whole = SimpleNamespace(h=64, w=96, device='cpu')
    L.attach_delta(whole, layer.window, delta)
    pixels = torch.from_numpy(source()).permute(2, 0, 1)[None]
    full = L.apply_delta(whole, pixels)
    stitched = torch.empty_like(full)
    for x0, x1 in ((0, 31), (31, 63), (63, 96)):
        tile = SimpleNamespace(h=64, w=x1-x0, device='cpu')
        L.attach_delta(tile, layer.window, delta, origin=(0, x0))
        stitched[:, :, :, x0:x1] = L.apply_delta(tile, pixels[:, :, :, x0:x1])
    assert torch.equal(stitched, full)


def test_lift_preserves_preceding_unrelated_changes(monkeypatch):
    import torch
    layer = prepared(monkeypatch); delta = layer.solve({'wrinkle_forehead': .5})
    pipe = SimpleNamespace(h=64, w=96, device='cpu')
    L.attach_delta(pipe, layer.window, delta)
    incoming = torch.from_numpy(source() * .8).permute(2, 0, 1)[None]
    result = L.apply_delta(pipe, incoming)
    expected = (incoming + torch.from_numpy(delta).permute(2, 0, 1)[None]).clamp(0, 1)
    assert torch.equal(result, expected)
    assert torch.equal(result[:, :, :8], incoming[:, :, :8])
