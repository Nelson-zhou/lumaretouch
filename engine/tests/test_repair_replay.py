"""Preview/export share ordered float replay; legacy heal pixels stay unchanged."""
import copy

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from lumaretouch_engine import repair_replay as R
from lumaretouch_engine.export import apply_repair_full
from lumaretouch_engine.repair_record import RepairOp, DEFAULT_REPAIR
from lumaretouch_engine.vram import PreviewPipeline


def patch_params():
    return {"version": "source-patch-v1", "polygon": [[.65, .35], [.85, .35], [.85, .65], [.65, .65]],
            "offset": [-.45, 0.]}


def rgb():
    rng = np.random.default_rng(12)
    image = np.full((100, 160, 3), .45, np.float32)
    image += rng.uniform(-.025, .025, image.shape).astype(np.float32)
    image[45:55, 42:52] = .08
    image[43:57, 112:128] = .1
    return image


def ops():
    heal_weight = np.zeros((100, 160), np.uint8)
    heal_weight[44:56, 41:53] = 255
    patch_weight = np.zeros((100, 160), np.uint8)
    patch_weight[35:66, 104:137] = 255
    return [RepairOp(1, heal_weight), RepairOp(2, patch_weight, patch_params(), "source_patch")]


def tensor(image):
    return torch.from_numpy(np.ascontiguousarray(image.transpose(2, 0, 1))[None])


def test_legacy_heal_matches_original_formula_exactly():
    from lumaretouch_engine.ops.inpaint import crop_apply_t, hole_extent, inpaint_t, levels_for, mask_bbox
    op = ops()[0]
    source = tensor(rgb())
    weights = op.weight.astype(np.float32) / 255.0
    p = DEFAULT_REPAIR
    box = mask_bbox(weights, pad=p["pad"], grow=p["grow"])
    y0, y1, x0, x1 = box
    levels = levels_for(hole_extent(weights), y1-y0, x1-x0)
    wsub = torch.from_numpy(np.ascontiguousarray(weights[None, None, y0:y1, x0:x1]))
    fill = inpaint_t(source[..., y0:y1, x0:x1], wsub, levels=levels,
                     smooth_iters=p["smooth_iters"], refine_iters=p["refine_iters"], kappa=p["kappa"])
    expected = crop_apply_t(source, box, fill)
    actual, boxes, painted = R.replay_repair_t(source, [op])
    assert torch.equal(actual, expected)
    assert boxes == [list(box)] and painted == op.area_px


def test_source_patch_reads_previous_operation_and_not_display_rgb8():
    pytest.importorskip("cv2")
    source = tensor(rgb())
    before = source.clone()
    mixed = ops()
    first, _, _ = R.replay_repair_t(source, mixed[:1])
    expected, _, _ = R.replay_repair_t(first, mixed[1:])
    actual, boxes, _ = R.replay_repair_t(source, mixed)
    reversed_result, _, _ = R.replay_repair_t(source, list(reversed(mixed)))
    assert torch.equal(actual, expected) and len(boxes) == 2
    assert not torch.equal(actual, reversed_result)
    assert torch.equal(source, before)
    # Coverage is retained as proxy input/history, not the patch's render mask.
    patch = copy.deepcopy(mixed[1])
    patch.weight[:] = 0
    rendered, _, _ = R.replay_repair_t(first, [patch])
    assert torch.equal(rendered, expected)


def test_preview_and_uint16_full_replay_match_before_output_quantization():
    pytest.importorskip("cv2")
    original = np.rint(rgb() * 65535).astype(np.uint16)
    # Keep the exact same uint16 conversion as the full export entry point.
    image = tensor(original).to(torch.float32).div_(65535.)[0].permute(1, 2, 0).numpy()
    pipe = PreviewPipeline("cpu", 160, 100)
    pipe.load_rgb_f32(image)
    assert pipe.src_u8 is None
    pipe.set_repair_ops(ops())
    full, stats = apply_repair_full(original, ops(), "cpu")
    np.testing.assert_array_equal(full, pipe.base()[0].permute(1, 2, 0).numpy())
    assert stats["applied"] == 2
    # A float32 intermediate, not the display's 8-bit approximation.
    assert np.any(np.abs(full * 255 - np.rint(full * 255)) > .01)


def test_mixed_undo_redo_and_rebuild_reproduce_exact_pixels():
    pytest.importorskip("cv2")
    pipe = PreviewPipeline("cpu", 160, 100)
    pipe.load_rgb_f32(rgb())
    records = ops()
    pipe.add_repair(records[0])
    first = pipe.base().clone()
    pipe.add_repair(records[1])
    both = pipe.base().clone()
    version = pipe.repair_version
    pipe.undo_repair()
    assert torch.equal(pipe.base(), first) and pipe.redo_ops[0].kind == "source_patch"
    pipe.redo_repair()
    assert torch.equal(pipe.base(), both) and pipe.repair_version == version + 2
    rebuilt = PreviewPipeline("cpu", 160, 100)
    rebuilt.load_rgb_f32(rgb())
    rebuilt.set_repair_ops(pipe.repair_ops, pipe.redo_ops)
    assert torch.equal(rebuilt.base(), both)


def test_source_patch_failure_does_not_change_ops_versions_or_filter_cache(monkeypatch):
    from lumaretouch_engine.ops import source_patch
    pipe = PreviewPipeline("cpu", 160, 100)
    pipe.load_rgb_f32(rgb())
    pipe.add_repair(ops()[0])
    pipe.prepare(radius=4, texture_radius=2)
    before = (pipe.repair_ops, pipe.redo_ops, pipe.repair_base, pipe.repair_version,
              pipe.retouched, pipe.filter_key, pipe.bands, pipe.bands_key)
    source = pipe.src_f32.clone()
    def fail(*args):
        raise RuntimeError("injected source-patch failure")
    monkeypatch.setattr(source_patch, "apply_t", fail)
    with pytest.raises(RuntimeError, match="injected"):
        pipe.add_repair(ops()[1])
    after = (pipe.repair_ops, pipe.redo_ops, pipe.repair_base, pipe.repair_version,
             pipe.retouched, pipe.filter_key, pipe.bands, pipe.bands_key)
    assert all(a is b for a, b in zip(before, after))
    assert torch.equal(pipe.src_f32, source)


def test_unknown_kind_and_bad_redo_are_rejected_before_replay(monkeypatch):
    pipe = PreviewPipeline("cpu", 160, 100)
    pipe.load_rgb_f32(rgb())
    version = pipe.repair_version
    invalid = ops()[0]
    invalid.kind = "not-heal"
    monkeypatch.setattr(R, "inpaint_t", lambda *a, **k: pytest.fail("bad stack rendered before preflight"))
    with pytest.raises(ValueError, match="kind"):
        pipe.set_repair_ops([ops()[0], invalid])
    with pytest.raises(ValueError, match="kind"):
        pipe.set_repair_ops([], [invalid])
    assert pipe.repair_version == version and not pipe.repair_ops and not pipe.redo_ops
