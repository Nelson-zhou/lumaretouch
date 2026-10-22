"""Nested source-patch recipe fields must not alias live state or cross images."""
import numpy as np
import pytest

from lumaretouch_engine.repair_record import RepairOp
from lumaretouch_engine.render_snapshot import own_render_inputs
from lumaretouch_engine.inspection_bundle import BundleWriter, read_bundle


def patch():
    return RepairOp(3, np.ones((10, 12), np.uint8),
                    {"version": "source-patch-v1", "polygon": [[.6, .3], [.8, .3], [.8, .6]],
                     "offset": [-.4, 0.]}, "source_patch")


def test_snapshot_and_bundle_preserve_kind_and_own_nested_recipe(tmp_path):
    record = patch()
    owned = own_render_inputs({"repair_ops": [record]}, max_asset_bytes=120)
    writer = BundleWriter(tmp_path, owned)
    while not writer.done:
        writer.advance(4096)
    restored = read_bundle(tmp_path, max_asset_bytes=120)["repair_ops"][0]
    record.params["polygon"][0][0] = .9
    record.params["offset"][0] = 0
    record.weight[:] = 0
    for op in (owned.value["repair_ops"][0], restored):
        assert op.kind == "source_patch"
        assert op.params["polygon"][0][0] == .6 and op.params["offset"][0] == -.4
        assert op.weight.all() and not op.weight.flags.writeable
    restored.params["polygon"][0][0] = .7
    assert owned.value["repair_ops"][0].params["polygon"][0][0] == .6


def test_export_recipe_resizes_only_coverage_and_copies_source_coordinates():
    pytest.importorskip("torch")
    from test_export_per_image_recipe import _batch_snap
    from lumaretouch_engine.export_recipe import build_export_spec
    snap = _batch_snap()
    record = patch()
    snap["repair_ops"] = [record]
    spec, skipped = build_export_spec(snap, 20, 24, for_document=True)
    assert not skipped
    saved = spec.repair[0]
    assert saved.kind == "source_patch" and saved.weight.shape == (20, 24)
    assert saved.params == record.params
    saved.params["polygon"][0][0] = .9
    saved.params["offset"][0] = 0
    assert record.params["polygon"][0][0] == .6 and record.params["offset"][0] == -.4
    other, skipped = build_export_spec(snap, 20, 24, for_document=False)
    assert not other.repair and "repair" in skipped
