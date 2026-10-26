# SPDX-License-Identifier: GPL-3.0-or-later
"""Original offline, fail-closed optional depth boundary. AUTHORED / UNRUN.

This module owns no document, recipe, installation, cache, or native render state.
It supplies a result only after exact optional-artifact integrity and a genuine
installed CPU readiness check; development/runtime/quality acceptance is UNRUN. A missing model never becomes a fake
plane, subject mask, luminance depth, or a silently changed recipe.

The proposed inference route is the upstream Transformers implementation with
the official compatible safetensors checkpoint, not the original .pth loader.
Model code imports occur only inside a bounded worker after conditional admission.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Callable

from . import lens_depth_manifest as manifest


MAX_SOURCE_PIXELS = 100_000_000
MAX_SOURCE_EDGE = 1_000_000
MAX_PROXY_EDGE = 1024
MAX_MODEL_EDGE = 1536
MAX_MODEL_PIXELS = 786_432
MAX_SOURCE_ASPECT = 4
ORIENTATION = "exif_normalized_once"
MAPPING = "normalized_full_frame_pixel_centres"
PROXY_FORMAT = "opaque-encoded-srgb-rgb8-analysis-only"
NORMALIZATION = "per-image-global-minmax-inverted-after-bicubic-v1"
Cancel = Callable[[], bool]


class DepthUnavailable(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


class DepthCancelled(DepthUnavailable):
    def __init__(self):
        super().__init__("cancelled", "Depth cancelled; no result or recipe change")


def _token(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is not None


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _revision(value: object) -> bool:
    return (type(value) is str and re.fullmatch(r"0|[1-9][0-9]{0,19}", value) is not None
            and int(value) <= 18_446_744_073_709_551_615)


def _integer(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class DepthSourceV1:
    """Same oriented source-grid identity as the native/UI boundary, not a path."""
    sha256: str
    width: int
    height: int
    orientation: str = ORIENTATION

    def __post_init__(self):
        if (not _sha(self.sha256) or self.orientation != ORIENTATION
                or not _integer(self.width, 2, MAX_SOURCE_EDGE)
                or not _integer(self.height, 2, MAX_SOURCE_EDGE)
                or self.width * self.height > MAX_SOURCE_PIXELS):
            raise ValueError("Invalid or oversized immutable source-grid identity")
        if max(self.width, self.height) > MAX_SOURCE_ASPECT * min(self.width, self.height):
            raise ValueError("Depth v1 supports full-frame aspect ratios only through 4:1")


@dataclass(frozen=True)
class DepthOwnerV1:
    document_id: str
    document_epoch: str
    document_revision: str
    source: DepthSourceV1

    def __post_init__(self):
        if (not _token(self.document_id) or not _token(self.document_epoch)
                or not _revision(self.document_revision) or type(self.source) is not DepthSourceV1):
            raise ValueError("Explicit source-owned document epoch and revision required")


def proxy_extent_v1(source: DepthSourceV1) -> tuple[int, int]:
    """Canonical whole-frame extent, no upscaling, integer half-up short edge."""
    if type(source) is not DepthSourceV1:
        raise ValueError("DepthSourceV1 required")
    longest = max(source.width, source.height)
    if longest <= MAX_PROXY_EDGE:
        return source.width, source.height
    width = max(2, (source.width * MAX_PROXY_EDGE * 2 + longest) // (2 * longest))
    height = max(2, (source.height * MAX_PROXY_EDGE * 2 + longest) // (2 * longest))
    return width, height


@dataclass(frozen=True)
class DepthRequestV1:
    """Host-prepared analysis proxy, NEVER the colour pixels used for rendering.

    The source owner must authenticate its source snapshot and analysis transform.
    A digest supplied here binds identity but cannot prove correct proxy creation.
    HDR tone mapping or alpha flattening is the host's explicit, receipted analysis
    decision; it must not replace the native full-precision original source.
    """
    owner: DepthOwnerV1
    proxy_width: int
    proxy_height: int
    proxy_rgb8: bytes
    analysis_transform_sha256: str
    proxy_format: str = PROXY_FORMAT
    mapping: str = MAPPING

    def __post_init__(self):
        if type(self.owner) is not DepthOwnerV1 or not _sha(self.analysis_transform_sha256):
            raise ValueError("Source owner and analysis colour/alpha transform identity required")
        if (not _integer(self.proxy_width, 2, MAX_PROXY_EDGE)
                or not _integer(self.proxy_height, 2, MAX_PROXY_EDGE)
                or (self.proxy_width, self.proxy_height) != proxy_extent_v1(self.owner.source)
                or self.proxy_format != PROXY_FORMAT or self.mapping != MAPPING):
            raise ValueError("Proxy must be the canonical oriented whole-source frame")
        if type(self.proxy_rgb8) is not bytes or len(self.proxy_rgb8) != self.proxy_width * self.proxy_height * 3:
            raise ValueError("Proxy must be immutable packed RGB8 bytes with exact bounds")

    @property
    def proxy_sha256(self) -> str:
        return hashlib.sha256(self.proxy_rgb8).hexdigest()

    @property
    def identity(self) -> str:
        return hashlib.sha256(b"lrt-lens-depth-request-v1\0" + _canonical({
            "owner": asdict(self.owner), "proxy_width": self.proxy_width,
            "proxy_height": self.proxy_height, "proxy_sha256": self.proxy_sha256,
            "analysis_transform_sha256": self.analysis_transform_sha256,
            "proxy_format": self.proxy_format, "mapping": self.mapping,
        })).hexdigest()


@dataclass(frozen=True)
class DepthNormalizationV1:
    raw_min: float
    raw_max: float
    method: str = NORMALIZATION
    raw_convention: str = manifest.RAW_CONVENTION
    uncertainty: str = "not-estimated"
    metric_units: None = None


@dataclass(frozen=True)
class DepthResultV1:
    """Immutable source-grid little-endian float32 bytes; never an RGB preview.

    Hosts must verify owner equality AGAIN before publishing or using this result.
    Hash equality and this Python type are not a substitute for model provenance.
    The host persists assets and keeps any UI u16 quantization separate.
    """
    owner: DepthOwnerV1
    request_identity: str
    depth_le_f32: bytes
    depth_sha256: str
    inference_id: str
    provenance_json: str
    normalization: DepthNormalizationV1
    version: int = manifest.CONTRACT_VERSION
    convention: str = manifest.OUTPUT_CONVENTION
    mapping: str = MAPPING
    subject_focus: None = None


@dataclass(frozen=True)
class DepthCapabilityV1:
    version: int
    adapter_id: str
    model_id: str
    available: bool
    code: str
    reason: str
    admission_gaps: tuple[str, ...]
    inference_acceptance: str = "UNRUN"
    downloads_attempted: bool = False
    installs_attempted: bool = False


def capability_v1() -> DepthCapabilityV1:
    """Offline actual integrity/readiness check; never model import or network."""
    from .lens_depth_setup import model_status
    status = model_status()
    return DepthCapabilityV1(manifest.CONTRACT_VERSION, manifest.ADAPTER_ID,
        manifest.MODEL_ID, status['ready'], status['code'], status['reason'],
        () if status['ready'] else (status['code'],))


def _cancel(cancelled: Cancel | None) -> None:
    if cancelled is not None and cancelled():
        raise DepthCancelled()


def _open_directory(root: Path) -> int:
    if not root.is_absolute() or ".." in root.parts:
        raise DepthUnavailable("invalid-model-root", "Model root must be an explicit absolute local directory")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise DepthUnavailable("unsupported-platform", "No-follow local directory traversal is required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for component in root.parts[1:]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_exact(fd: int, pin: manifest.FilePin, cancelled: Cancel | None) -> bytes:
    if pin.sha256 is None or pin.size_bytes is None or not _sha(pin.sha256):
        raise DepthUnavailable("manifest-incomplete", "A bundled exact byte pin is missing")
    handle = os.open(pin.filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(handle)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size != pin.size_bytes):
            raise DepthUnavailable("model-file-invalid", "Model file type, link count, or size mismatch: " + pin.filename)
        parts, digest, count = [], hashlib.sha256(), 0
        while True:
            _cancel(cancelled)
            chunk = os.read(handle, min(1024 * 1024, pin.size_bytes + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > pin.size_bytes:
                raise DepthUnavailable("model-file-changed", "Model file grew during verification")
            digest.update(chunk)
            parts.append(chunk)
        after = os.fstat(handle)
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if count != pin.size_bytes or any(getattr(before, key) != getattr(after, key) for key in fields):
            raise DepthUnavailable("model-file-changed", "Model file changed during verification")
        if digest.hexdigest() != pin.sha256:
            raise DepthUnavailable("model-file-hash", "Model SHA256 mismatch: " + pin.filename)
        return b"".join(parts)  # The loader must consume these exact verified bytes.
    finally:
        os.close(handle)


def _read_model_bytes(root: Path, cancelled: Cancel | None) -> dict[str, bytes]:
    pins = manifest.MODEL_FILES
    if (len(pins) != 3 or {pin.filename for pin in pins} !=
            {"model.safetensors", "config.json", "preprocessor_config.json"}
            or any(pin.sha256 is None or pin.size_bytes is None or
                   not pin.revision_membership_verified for pin in pins)):
        raise DepthUnavailable("manifest-incomplete", "Exact upstream config/preprocessor pins or revision membership are missing; no model is loaded")
    try:
        fd = _open_directory(root)
        try:
            if set(os.listdir(fd)) != {pin.filename for pin in pins}:
                raise DepthUnavailable("model-file-set", "Model directory must contain exactly the three reviewed model files")
            return {pin.filename: _read_exact(fd, pin, cancelled) for pin in pins}
        finally:
            os.close(fd)
    except OSError as exc:
        raise DepthUnavailable("model-not-installed", "Local model pack is absent, unreadable, or unsafe; no download fallback") from exc


def _admit_runtime_v1(model_root: Path) -> str:
    # The app-selected base runtime is a disclosed trusted prerequisite. Added
    # optional code must match retained, bundled-SHA256-authenticated wheel bytes.
    # This is integrity checking, not protection against a hostile OS/user who
    # can replace the app or the selected interpreter itself.
    from .lens_depth_setup import activate_runtime
    identity = activate_runtime(model_root.parent)
    return hashlib.sha256(_canonical(identity)).hexdigest()


def _check_upstream_configs(config: dict, processor: dict) -> None:
    """Semantic guard in addition to byte pins, never a hash substitute."""
    backbone = config.get("backbone_config", {})
    if (config.get("architectures") != [manifest.ARCHITECTURE]
            or config.get("model_type") != "depth_anything"
            or config.get("backbone") is not None
            or config.get("use_pretrained_backbone") is not False
            or config.get("patch_size") != manifest.PATCH_SIZE
            or config.get("neck_hidden_sizes") != list(manifest.NECK_WIDTHS)
            or config.get("fusion_hidden_size") != manifest.FUSION_WIDTH
            or config.get("reassemble_hidden_size") != manifest.BACKBONE_WIDTH
            or config.get("torch_dtype") != "float32"
            or not isinstance(backbone, dict)
            or backbone.get("model_type") != manifest.BACKBONE
            or backbone.get("hidden_size") != manifest.BACKBONE_WIDTH
            or backbone.get("num_attention_heads") != manifest.BACKBONE_ATTENTION_HEADS
            or backbone.get("out_indices") != list(manifest.BACKBONE_STAGES)
            or backbone.get("patch_size") != manifest.PATCH_SIZE
            or backbone.get("reshape_hidden_states") is not False):
        raise DepthUnavailable("unsupported-model-config", "Only the reviewed official Small-hf architecture is supported")
    expected = {"image_processor_type": manifest.PREPROCESSOR, "do_resize": True,
        "size": {"height": 518, "width": 518}, "keep_aspect_ratio": True,
        "ensure_multiple_of": 14, "resample": 3, "do_rescale": True,
        "rescale_factor": 1 / 255, "do_normalize": True,
        "image_mean": list(manifest.IMAGE_MEAN), "image_std": list(manifest.IMAGE_STD),
        "do_pad": False, "size_divisor": None}
    if any(type(processor.get(key)) is not type(value) or processor.get(key) != value
           for key, value in expected.items()):
        raise DepthUnavailable("unsupported-preprocessor", "Only the reviewed full-frame DPT RGB8 preprocessing is supported")


def _normalize_full_grid(raw, source: DepthSourceV1,
                         cancelled: Cancel | None) -> tuple[bytes, DepthNormalizationV1]:
    """Numerical stage only. It does not authenticate input or claim inference."""
    import numpy as np
    if raw.dtype != np.float32 or raw.shape != (source.height, source.width) or not np.isfinite(raw).all():
        raise DepthUnavailable("invalid-depth-output", "Expected finite source-grid float32 depth")
    low, high = float(raw.min()), float(raw.max())
    span = high - low
    if not math.isfinite(span) or span <= max(1e-6, 1e-6 * max(abs(low), abs(high))):
        raise DepthUnavailable("uninformative-depth", "Constant or near-constant model output cannot establish a focus ordering")
    # Chunked float64 arithmetic avoids float32 span overflow/cancellation. The
    # result alone is rounded to float32, never to an 8-bit visualized depth map.
    flat = raw.reshape(-1)
    output = bytearray(source.width * source.height * 4)
    for offset in range(0, flat.size, 262_144):
        _cancel(cancelled)
        values = (high - flat[offset:offset + 262_144].astype(np.float64)) / span
        if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
            raise DepthUnavailable("invalid-normalization", "Depth normalization is out of bounds")
        chunk = values.astype("<f4").tobytes(order="C")
        output[offset * 4:offset * 4 + len(chunk)] = chunk
    immutable = bytes(output)
    return immutable, DepthNormalizationV1(low, high)


def _normalized_result(raw, request: DepthRequestV1, runtime_identity: str,
                       model_extent: tuple[int, int], cancelled: Cancel | None) -> DepthResultV1:
    source = request.owner.source
    immutable, normalization = _normalize_full_grid(raw, source, cancelled)
    digest = hashlib.sha256(immutable).hexdigest()
    provenance = {"version": 1, "adapter_id": manifest.ADAPTER_ID,
        "model_id": manifest.MODEL_ID, "model_repository": manifest.MODEL_REPOSITORY,
        "model_revision": manifest.MODEL_REVISION,
        "model_files": {p.filename: p.sha256 for p in manifest.MODEL_FILES},
        "runtime_identity": runtime_identity, "owner": asdict(request.owner),
        "request_identity": request.identity, "proxy_sha256": request.proxy_sha256,
        "proxy_extent": [request.proxy_width, request.proxy_height],
        "proxy_format": request.proxy_format,
        "analysis_transform_sha256": request.analysis_transform_sha256,
        "model_extent": list(model_extent), "output_extent": [source.width, source.height],
        "mapping": MAPPING, "output_dtype": "little-endian-float32",
        "depth_sha256": digest, "convention": manifest.OUTPUT_CONVENTION,
        "normalization": asdict(normalization), "device": "cpu", "precision": "float32",
        "upsampling": "bicubic-align_corners_false-to-full-source-grid",
        "source_colour_pixels_modified": False, "subject_focus": None,
        "inference_acceptance": manifest.INFERENCE_ACCEPTANCE}
    receipt = _canonical(provenance)
    inference_id = hashlib.sha256(b"lrt-lens-depth-result-v1\0" + receipt).hexdigest()
    _cancel(cancelled)
    return DepthResultV1(request.owner, request.identity, immutable, digest, inference_id,
                         receipt.decode("utf-8"), normalization)


def _estimate_depth_in_process(request: DepthRequestV1, *, model_root: str | Path,
                      cancelled: Cancel | None = None) -> DepthResultV1:
    """Private worker-only CPU float32 route after installed artifact admission.

    The caller owns cancellation/stale-revision rejection and native asset commit.
    Cancellation is cooperative between reads/stages, not inside a Torch kernel.
    No install, network, cache discovery, remote code, .pth/pickle fallback, source
    edit, recipe change, or fallback depth occurs on failure. Resources are local
    to this call. Concurrent calls must be bounded by the host's resource budget.
    """
    if type(request) is not DepthRequestV1:
        raise ValueError("An immutable DepthRequestV1 is required")
    _cancel(cancelled)
    files = _read_model_bytes(Path(model_root), cancelled)
    runtime_identity = _admit_runtime_v1(Path(model_root))
    config_data = json.loads(files["config.json"])
    processor_data = json.loads(files["preprocessor_config.json"])
    if type(config_data) is not dict or type(processor_data) is not dict:
        raise DepthUnavailable("invalid-model-json", "Reviewed configurations must be objects")
    _check_upstream_configs(config_data, processor_data)
    import numpy as np
    import torch
    from safetensors.torch import load as load_safetensors
    from transformers import DepthAnythingConfig, DepthAnythingForDepthEstimation
    from transformers.models.dpt.image_processing_pil_dpt import DPTImageProcessorPil
    _cancel(cancelled)
    processor = DPTImageProcessorPil.from_dict(processor_data)
    proxy = np.frombuffer(request.proxy_rgb8, dtype=np.uint8).reshape(
        request.proxy_height, request.proxy_width, 3)
    inputs = processor(images=proxy, return_tensors="pt", input_data_format="channels_last")
    pixels = inputs["pixel_values"]
    if (pixels.ndim != 4 or tuple(pixels.shape[:2]) != (1, 3)
            or pixels.dtype != torch.float32 or not bool(torch.isfinite(pixels).all())):
        raise DepthUnavailable("invalid-model-input", "Preprocessor did not produce finite float32 RGB")
    height, width = int(pixels.shape[2]), int(pixels.shape[3])
    if (min(width, height) < 14 or max(width, height) > MAX_MODEL_EDGE
            or width * height > MAX_MODEL_PIXELS or width % 14 or height % 14):
        raise DepthUnavailable("model-resource-bound", "Official preprocessor extent exceeds the v1 model budget; no forced distortion or crop")
    config = DepthAnythingConfig.from_dict(config_data)
    if config.depth_estimation_type != "relative":
        raise DepthUnavailable("unsupported-depth-convention", "Metric checkpoints are not interchangeable")
    model = None
    try:
        _cancel(cancelled)
        with torch.device("cpu"):
            model = DepthAnythingForDepthEstimation(config).to(device="cpu", dtype=torch.float32).eval()
        weights = load_safetensors(files["model.safetensors"])
        model.load_state_dict(weights, strict=True)
        del weights, files
        _cancel(cancelled)
        with torch.inference_mode(), torch.autocast(device_type="cpu", enabled=False):
            predicted = model(pixel_values=pixels.to(device="cpu", dtype=torch.float32)).predicted_depth
            if (predicted.dtype != torch.float32 or tuple(predicted.shape) != (1, height, width)
                    or not bool(torch.isfinite(predicted).all()) or bool((predicted < 0).any())):
                raise DepthUnavailable("invalid-model-output", "Relative head returned unexpected/nonfinite/negative values")
            _cancel(cancelled)
            full = torch.nn.functional.interpolate(predicted.unsqueeze(1),
                size=(request.owner.source.height, request.owner.source.width),
                mode="bicubic", align_corners=False)[0, 0]
            raw = full.detach().cpu().numpy()
        _cancel(cancelled)
        return _normalized_result(raw, request, runtime_identity, (width, height), cancelled)
    finally:
        del model  # Never change global allocator, precision, threads, or environment.


def estimate_depth_v1(request: DepthRequestV1, *, model_root: str | Path,
                      cancelled: Cancel | None = None) -> DepthResultV1:
    """Bounded offline child inference; no Torch import or global state in host.

    Genuine installed readiness is required. Cancellation terminates the child,
    including a long Torch kernel; no output is published before complete receipt
    and source-grid byte verification. Caller still owns its document fence.
    """
    import sys
    import tempfile
    from .lens_depth_setup import model_status, _read, runtime_identity
    from .prompted_model_install import _run
    if type(request) is not DepthRequestV1:
        raise ValueError('An immutable DepthRequestV1 is required')
    _cancel(cancelled)
    root = Path(model_root)
    if not root.is_absolute() or root.name != 'model':
        raise DepthUnavailable('invalid-model-root', 'Canonical explicit depth model directory required')
    status = model_status(root.parent)
    if not status['ready']:
        raise DepthUnavailable(status['code'], status['reason'])
    identity = runtime_identity(root.parent)
    _cancel(cancelled)
    with tempfile.TemporaryDirectory(prefix='lrt-depth-analysis-') as directory:
        directory = Path(directory)
        metadata = {'owner': asdict(request.owner), 'proxy_width':request.proxy_width,
            'proxy_height':request.proxy_height,'analysis_transform_sha256':request.analysis_transform_sha256,
            'proxy_sha256':request.proxy_sha256,'request_identity':request.identity}
        (directory/'request.json').write_bytes(_canonical(metadata))
        (directory/'proxy.rgb8').write_bytes(request.proxy_rgb8)
        _run([sys.executable,'-B','-m','lumaretouch_engine.lens_depth_worker',
              '--root',str(root.parent),'--output',str(directory/'result.json'),
              '--request',str(directory),'--parent-pid',str(os.getpid())],
             cancelled,directory/'worker.log',timeout=110)
        _cancel(cancelled)
        receipt = json.loads(_read(directory/'result.json',65536))
        raw = _read(directory/'depth.f32',request.owner.source.width*request.owner.source.height*4)
        if (receipt.get('owner') != asdict(request.owner) or receipt.get('request_identity')!=request.identity
                or len(raw)!=request.owner.source.width*request.owner.source.height*4
                or hashlib.sha256(raw).hexdigest()!=receipt.get('depth_sha256')
                or runtime_identity(root.parent)!=identity):
            raise DepthUnavailable('invalid-worker-result','Depth child output or runtime identity changed')
        normalization = DepthNormalizationV1(**receipt['normalization'])
        provenance = receipt['provenance_json']
        if (type(provenance) is not str or hashlib.sha256(b'lrt-lens-depth-result-v1\0'+provenance.encode()).hexdigest()!=receipt['inference_id']):
            raise DepthUnavailable('invalid-worker-provenance','Depth result provenance identity mismatch')
        return DepthResultV1(request.owner, request.identity, raw, receipt['depth_sha256'],
                             receipt['inference_id'],provenance,normalization)
