"""AUTHORED / UNRUN fixtures, not model or native acceptance evidence.

Intentionally kept outside the engine's ordinary test discovery until a host
review integrates this optional module. Synthetic arrays exercise arithmetic
only and must never be represented as generated model-depth assets.
"""
from dataclasses import FrozenInstanceError
import hashlib
import sys

import pytest

from lumaretouch_engine import lens_depth_adapter as depth
from lumaretouch_engine import lens_depth_manifest as manifest


def request(width=2, height=2):
    source = depth.DepthSourceV1("1" * 64, width, height)
    owner = depth.DepthOwnerV1("document", "epoch", "0", source)
    w, h = depth.proxy_extent_v1(source)
    return depth.DepthRequestV1(owner, w, h, bytes(w * h * 3), "2" * 64)


def test_immutable_request_and_source_binding():
    original = request()
    with pytest.raises(FrozenInstanceError):
        original.owner.source.width = 3
    with pytest.raises(ValueError):
        depth.DepthRequestV1(original.owner, 2, 2, bytearray(12), "2" * 64)
    revised_owner = depth.DepthOwnerV1("document", "epoch", "1", original.owner.source)
    revised = depth.DepthRequestV1(revised_owner, 2, 2, original.proxy_rgb8, "2" * 64)
    assert original.identity != revised.identity
    assert original.proxy_sha256 == hashlib.sha256(original.proxy_rgb8).hexdigest()


@pytest.mark.parametrize("revision", ["-1", "01", "+1", "18446744073709551616", 1, True])
def test_noncanonical_document_revision_rejected(revision):
    with pytest.raises(ValueError):
        depth.DepthOwnerV1("document", "epoch", revision, request().owner.source)


def test_whole_frame_proxy_extent():
    source = depth.DepthSourceV1("1" * 64, 4000, 3000)
    assert depth.proxy_extent_v1(source) == (1024, 768)
    owner = depth.DepthOwnerV1("document", "epoch", "0", source)
    with pytest.raises(ValueError):
        depth.DepthRequestV1(owner, 100, 100, bytes(100 * 100 * 3), "2" * 64)


@pytest.mark.parametrize("width,height", [(True, 2), (1, 2), (10001, 10000), (100, 2)])
def test_source_bounds(width, height):
    with pytest.raises(ValueError):
        depth.DepthSourceV1("1" * 64, width, height)


def test_capability_is_unavailable_without_filesystem_or_optional_imports(monkeypatch):
    before = set(sys.modules)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unavailable capability must not inspect local model files")
    monkeypatch.setattr(depth, "_open_directory", forbidden)
    capability = depth.capability_v1()
    assert not capability.available
    assert capability.inference_acceptance == "UNRUN"
    assert not capability.downloads_attempted and not capability.installs_attempted
    assert "upstream-file-pin:config.json" in capability.admission_gaps
    assert "runtime-artifact-and-installed-code-provenance" in capability.admission_gaps
    assert not (set(sys.modules) - before) & {"torch", "transformers", "safetensors"}


def test_public_inference_refuses_incomplete_manifest_before_open(monkeypatch, tmp_path):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Incomplete pins must refuse before model access")
    monkeypatch.setattr(depth, "_open_directory", forbidden)
    with pytest.raises(depth.DepthUnavailable) as error:
        depth.estimate_depth_v1(request(), model_root=tmp_path)
    assert error.value.code == "manifest-incomplete"


def test_runtime_is_not_unlocked_by_metadata_or_manifest_flag(monkeypatch):
    monkeypatch.setattr(manifest, "RUNTIME_ADMISSION", "verified")
    with pytest.raises(depth.DepthUnavailable) as error:
        depth._admit_runtime_v1()
    assert error.value.code == "runtime-provenance-unverified"


def test_cancellation_publishes_no_result(tmp_path):
    with pytest.raises(depth.DepthCancelled):
        depth.estimate_depth_v1(request(), model_root=tmp_path, cancelled=lambda: True)


def test_numerical_stage_inverts_relative_order_without_creating_provenance():
    import numpy as np
    raw = np.array([[0, 1], [2, 3]], dtype=np.float32)
    original = raw.copy()
    encoded, normalization = depth._normalize_full_grid(raw, request().owner.source, None)
    result = np.frombuffer(encoded, dtype="<f4").reshape(2, 2)
    np.testing.assert_allclose(result, [[1, 2 / 3], [1 / 3, 0]], rtol=1e-6)
    np.testing.assert_array_equal(raw, original)
    assert type(encoded) is bytes and not result.flags.writeable
    assert normalization.metric_units is None and normalization.uncertainty == "not-estimated"


@pytest.mark.parametrize("values", [
    [[1, 1], [1, 1]], [[1, 1], [1, 1.0000001]],
    [[0, float("nan")], [1, 2]], [[0, float("inf")], [1, 2]],
])
def test_no_fake_plane_or_nonfinite_normalization(values):
    import numpy as np
    with pytest.raises(depth.DepthUnavailable):
        depth._normalize_full_grid(np.array(values, dtype=np.float32), request().owner.source, None)


def test_numerical_stage_rejects_shape_and_precision_mismatch():
    import numpy as np
    for raw in (np.zeros((1, 4), dtype=np.float32), np.zeros((2, 2), dtype=np.float64)):
        with pytest.raises(depth.DepthUnavailable):
            depth._normalize_full_grid(raw, request().owner.source, None)
