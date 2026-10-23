"""Isolated generation-to-asset boundary; NOT wired to live documents or UI.

No publication, history, persistence, automatic detection, or model installation.
Callers must add job/revision ownership and review before any future transaction.
Inputs are existing canonical immutable asset records, never arbitrary file paths.
"""
from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class StagedPair:
    assets: tuple[dict, dict]
    provenance_json: str


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stage_pair(source_asset, selection_asset, protection_asset, *, roi,
               seeds, settings, pack_root=None, cancelled=lambda: False):
    """Produce two real protected patch assets or no returned result.

    Initial fusion equals the retained soft eligible selection, density 1. Future
    editable fusion must re-bind source/eligibility, never accept arbitrary mask
    expansion. Returned patches are positioned at roi x/y, NOT canvas origin.
    Caller must retain that positioning and every candidate/provenance reference.
    This function does not imply that inputs were reviewed in a product UI.
    """
    from .creative_generation_pack import verify_pack
    verify_pack(pack_root)  # Fail closed before allocating native/model buffers.
    from .creative_document_assets import validate_asset, make_asset
    from .creative_generation_backend import generate_pair
    from . import creative_generation_patch_native as native
    import numpy as np

    if cancelled():
        raise InterruptedError("Generation staging cancelled")
    records = []
    for asset, kind in ((source_asset, "rgba"), (selection_asset, "mask"),
                        (protection_asset, "mask")):
        if type(asset) is not dict:
            raise ValueError("Canonical immutable creative asset required")
        frozen = dict(asset)  # Every content payload must already be immutable bytes.
        validate_asset(frozen)
        if frozen["kind"] != kind:
            raise ValueError("Generation source or mask kind mismatch")
        records.append(frozen)
    source, selection, protection = records
    width, height = source["width"], source["height"]
    if width * height > 32_000_000:
        raise ValueError("Generation source exceeds bounded 32MP preparation contract")
    if any((m["width"], m["height"]) != (width, height) for m in (selection, protection)):
        raise ValueError("Generation masks must use the same full-source pixel domain")
    if type(roi) is not tuple or len(roi) != 4 or any(type(v) is not int for v in roi):
        raise ValueError("Explicit integer native-source ROI required")
    x, y, rw, rh = roi
    if not (x >= 0 and y >= 0 and 1 <= rw <= 768 and 1 <= rh <= 768
            and x + rw <= width and y + rh <= height):
        raise ValueError("Generation ROI exceeds native source/context extent")
    job = {"schema": "creative-generation-stage-v1", "source_asset": source["id"],
           "selection_asset": selection["id"], "protection_asset": protection["id"],
           "roi": list(roi), "seeds": list(seeds), "settings": vars(settings),
           "input_space": "linear-srgb-d65-premultiplied-f32",
           "initial_fusion": "eligible-selection-density-one"}
    job_id = hashlib.sha256(_json(job).encode()).hexdigest()
    def pixels(asset, channels=None):
        shape = (height, width, channels) if channels else (height, width)
        array = np.frombuffer(asset["content"], dtype="<f4").reshape(shape)
        return array if array.dtype.isnative else array.astype(np.float32)
    rgb, repaint, eligible = native.prepare(pixels(source, 4), pixels(selection),
        pixels(protection), roi, cancelled=cancelled)
    # The binary model exclusion is derived from ACTUAL protection, not a zero
    # placeholder. Canonical fusion is the strict pixel-preservation mechanism.
    protected = (pixels(protection)[y:y+rh, x:x+rw] > 0).astype(np.float32)
    pair = generate_pair(rgb[:rh, :rw], repaint[:rh, :rw], protected,
        seeds=seeds, settings=settings, pack_root=pack_root, cancelled=cancelled)
    assets = []
    for candidate in pair.candidates:
        if cancelled():
            raise InterruptedError("Generation staging cancelled")
        # Native fuse takes fixed context extent; outside ROI has zero eligibility.
        padded = np.zeros((768, 768, 3), dtype=np.float32)
        padded[:rh, :rw] = candidate.rgb
        rgba = native.fuse(padded, eligible, eligible, (rw, rh), 1.0, cancelled=cancelled)
        content = np.ascontiguousarray(rgba[:rh, :rw]).astype("<f4", copy=False).tobytes()
        assets.append(make_asset("rgba", rw, rh, content))
    if cancelled():
        raise InterruptedError("Generation staging cancelled")
    evidence = {"job_id": job_id, "job": job, "model": json.loads(pair.provenance_json),
                "patch_asset_ids": [asset["id"] for asset in assets],
                "eligible_sha256": hashlib.sha256(eligible.astype("<f4", copy=False).tobytes()).hexdigest(),
                "placement": {"x": x, "y": y}, "published": False,
                "reviewed": False, "acceptance": "UNRUN"}
    return StagedPair(tuple(assets), _json(evidence))
