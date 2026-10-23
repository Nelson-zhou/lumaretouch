"""Optional Kandinsky 2.2 execution, not a capability or quality acceptance claim.

Original adapter using the Apache-2.0 Diffusers v0.29.0 public API. No upstream
implementation is copied. The admission gate must finish before optional imports.
Only a native-scale <=768 square-context patch is accepted; this module neither
resizes sources nor installs models, writes assets, or commits document state.
The caller MUST perform source-owned full-precision fusion outside this decoder:
its latent preservation is not pixel identity, and its mask expands in latent space.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Callable


EDGE = 768
DIFFUSERS_COMMIT = "39aa3909e8e2dfe30f4807aedaadf42c1d8b1a8f"


class GenerationCancelled(RuntimeError):
    """Cancellation produces no publishable pair."""


@dataclass(frozen=True)
class GenerationSettings:
    prompt: str
    negative_prompt: str = ""
    prior_steps: int = 25
    decoder_steps: int = 100
    prior_guidance: float = 4.0
    decoder_guidance: float = 4.0
    device: str = "cpu"


@dataclass(frozen=True)
class Candidate:
    # Read-only ndarray; caller still must copy into its immutable asset store.
    rgb: object
    seed: int
    sha256: str


@dataclass(frozen=True)
class CandidatePair:
    candidates: tuple[Candidate, Candidate]
    provenance_json: str


def _check_settings(settings, seeds):
    if not isinstance(settings, GenerationSettings):
        raise ValueError("Explicit generation settings required")
    if type(seeds) is not tuple or len(seeds) != 2 or any(
        type(seed) is not int or not 0 <= seed < 2**63 for seed in seeds
    ) or seeds[0] == seeds[1]:
        raise ValueError("Two distinct persisted uint63 seeds required")
    for prompt in (settings.prompt, settings.negative_prompt):
        if type(prompt) is not str or len(prompt) > 4096 or "\x00" in prompt:
            raise ValueError("Invalid bounded prompt")
    if not settings.prompt.strip():
        raise ValueError("A reviewed nonempty prompt is required")
    for steps in (settings.prior_steps, settings.decoder_steps):
        if type(steps) is not int or not 1 <= steps <= 150:
            raise ValueError("Steps must be integers in 1..150")
    for value in (settings.prior_guidance, settings.decoder_guidance):
        if type(value) not in (float, int) or not math.isfinite(value) or not 1 < value <= 20:
            raise ValueError("Guidance must be finite in (1,20]")
    if settings.device not in ("cpu", "cuda"):
        raise ValueError("Only explicit CPU or CUDA float32 execution is defined")


def _digest(array):
    """Endian-stable digest; dimensions and semantics are separately receipted."""
    return hashlib.sha256(array.astype("<f4", copy=False).tobytes(order="C")).hexdigest()


def _prepare(source_rgb, repaint_mask, protected_mask):
    import numpy as np
    if not isinstance(source_rgb, np.ndarray) or source_rgb.dtype != np.float32:
        raise ValueError("Source must be encoded-working-sRGB float32, not PIL/RGB8")
    if source_rgb.ndim != 3 or source_rgb.shape[2] != 3:
        raise ValueError("Opaque RGB only: alpha sources need a separate supported path")
    height, width = source_rgb.shape[:2]
    if not (1 <= height <= EDGE and 1 <= width <= EDGE):
        raise ValueError("Native context extent exceeds 768; no implicit downsampling")
    source = source_rgb.copy(order="C")
    if not np.isfinite(source).all() or (source < 0).any() or (source > 1).any():
        raise ValueError("HDR/nonfinite sources unsupported; input is never clipped")
    masks = []
    for value in (repaint_mask, protected_mask):
        if not isinstance(value, np.ndarray) or value.shape != (height, width):
            raise ValueError("Repaint and protected-subject masks must match native source")
        if not np.isfinite(value).all() or not ((value == 0) | (value == 1)).all():
            raise ValueError("Decoder masks must be binary; fusion feather is separate")
        masks.append(value.astype(np.float32, copy=True))
    repaint, protected = masks
    if not repaint.any() or (repaint * protected).any() or repaint.all():
        raise ValueError("Need nonempty repaint, preserved context and no protected overlap")
    # Replicate right/bottom context without resampling or quantizing original pixels.
    padded = np.pad(source, ((0, EDGE-height), (0, EDGE-width), (0, 0)), mode="edge")
    mask = np.pad(repaint, ((0, EDGE-height), (0, EDGE-width)), mode="constant")
    return source, repaint, protected, padded, mask


def _decode_output(raw, height, width):
    import numpy as np
    if raw.shape != (1, 3, EDGE, EDGE) or raw.dtype != np.float32:
        raise ValueError("Unexpected model output shape or dtype")
    if not np.isfinite(raw).all() or float(np.abs(raw).max()) > 16:
        raise ValueError("Nonfinite or grossly out-of-contract decoder output")
    stats = {"raw_sha256": _digest(raw), "raw_min": float(raw.min()),
             "raw_max": float(raw.max()), "below_minus_one": int((raw < -1).sum()),
             "above_plus_one": int((raw > 1).sum())}
    # Exactly the official np output SDR display transform, but retain float32.
    # This maps GENERATED values only, never source pixels or an HDR source.
    rgb = np.clip(raw[0].transpose(1, 2, 0) * np.float32(.5) + np.float32(.5), 0, 1)
    rgb = np.ascontiguousarray(rgb[:height, :width])
    rgb.setflags(write=False)
    return rgb, stats


def _diversity(candidates, repaint):
    """Two actual attempts are required, not fabricated/guaranteed visual variety."""
    return {"identical_whole_output": candidates[0].sha256 == candidates[1].sha256,
            "identical_repaint_area": _digest(candidates[0].rgb[repaint > 0]) ==
            _digest(candidates[1].rgb[repaint > 0])}


def generate_pair(source_rgb, repaint_mask, protected_mask, *, seeds: tuple[int, int],
                  settings: GenerationSettings, pack_root: str | Path | None,
                  cancelled: Callable[[], bool] | None = None) -> CandidatePair:
    """Return two genuine samples atomically, or raise without publishing anything.

    `protected_mask` is explicit target-owned evidence, even when all-zero after
    review. Caller binds patch origin/full-source identity and freezes prompt,
    masks and seeds before invoking. This module does not detect passersby.
    Cancellation is checked between stages and each denoising step, not while
    an individual model kernel or initial weight load is executing.
    """
    from .creative_generation_pack import verify_pack
    _check_settings(settings, seeds)
    def check():
        if cancelled is not None and cancelled():
            raise GenerationCancelled("Generation cancelled; no candidate pair committed")
    def callback(_pipeline, _step, _timestep, values):
        check()
        return values
    check()
    pack = verify_pack(pack_root)  # No imports/inference until all admission pins pass.
    source, repaint, protected, padded, mask = _prepare(source_rgb, repaint_mask, protected_mask)
    import torch
    from diffusers import KandinskyV22PriorPipeline, KandinskyV22InpaintPipeline
    check()
    load_options = {"local_files_only": True, "use_safetensors": True,
                    "torch_dtype": torch.float32}
    prior = KandinskyV22PriorPipeline.from_pretrained(str(pack.prior_path), **load_options)
    decoder = None
    try:
        check()
        prior.to(settings.device)
        prior.set_progress_bar_config(disable=True)
        for prompt in (settings.prompt, settings.negative_prompt):
            tokens = prior.tokenizer(prompt, truncation=False, add_special_tokens=True)["input_ids"]
            if len(tokens) > prior.tokenizer.model_max_length:
                raise ValueError("Prompt exceeds actual pinned tokenizer limit; no truncation")
        decoder = KandinskyV22InpaintPipeline.from_pretrained(str(pack.decoder_path), **load_options)
        decoder.to(settings.device)
        decoder.set_progress_bar_config(disable=True)
        if verify_pack(pack_root) != pack:
            raise ValueError("Model pack changed during loading")
        check()
        image = torch.from_numpy(padded.transpose(2, 0, 1).copy()).unsqueeze(0) * 2 - 1
        mask_tensor = torch.from_numpy(mask.copy()).unsqueeze(0).unsqueeze(0)
        candidates, stats = [], []
        with torch.inference_mode():
            for seed in seeds:
                check()
                # Independent per-stage streams. Both seed values are recorded.
                prior_rng = torch.Generator(device=settings.device).manual_seed(seed)
                decoder_rng = torch.Generator(device=settings.device).manual_seed(seed)
                embeds = prior(prompt=settings.prompt, negative_prompt=settings.negative_prompt,
                    num_inference_steps=settings.prior_steps, guidance_scale=settings.prior_guidance,
                    num_images_per_prompt=1, generator=prior_rng, output_type="pt", return_dict=True,
                    callback_on_step_end=callback, callback_on_step_end_tensor_inputs=[])
                check()
                result = decoder(image_embeds=embeds.image_embeds,
                    negative_image_embeds=embeds.negative_image_embeds,
                    image=image.clone(), mask_image=mask_tensor.clone(), height=EDGE, width=EDGE,
                    num_inference_steps=settings.decoder_steps, guidance_scale=settings.decoder_guidance,
                    num_images_per_prompt=1, generator=decoder_rng, output_type="pt", return_dict=True,
                    callback_on_step_end=callback, callback_on_step_end_tensor_inputs=[])
                raw = result.images.detach().to(device="cpu", dtype=torch.float32).numpy()
                rgb, evidence = _decode_output(raw, source.shape[0], source.shape[1])
                candidates.append(Candidate(rgb, seed, _digest(rgb)))
                stats.append(evidence)
                del result, embeds, raw
        check()
        diversity = _diversity(candidates, repaint)
        rechecked = verify_pack(pack_root)
        if rechecked != pack:
            raise ValueError("Model pack changed during generation")
        provenance = {"schema": "kandinsky22-pair-v1", "pack": pack.identity,
            "namespace": pack.namespace, "diffusers_commit": DIFFUSERS_COMMIT,
            "source_rgb_sha256": _digest(source), "repaint_sha256": _digest(repaint),
            "protected_sha256": _digest(protected), "width": source.shape[1],
            "height": source.shape[0], "model_extent": [EDGE, EDGE],
            "padding": "right-bottom-edge-no-resize", "source_space": "encoded-srgb-opaque-f32",
            "decoder_mask": "binary-white-repaint-upstream-latent-expansion",
            "output_transform": "official-generated-only-(sample+1)/2-clamp-sdr-f32",
            "gross_decoder_bound": 16, "output_stats": stats,
            "seeds": list(seeds), "stage_rng": "separate-prior-decoder-same-seed",
            "settings": vars(settings), "candidates": [c.sha256 for c in candidates],
            "diversity": diversity,
            "pixel_identity_outside_mask": False, "requires_canonical_fusion": True}
        check()
        return CandidatePair(tuple(candidates), json.dumps(provenance, sort_keys=True, allow_nan=False))
    finally:
        # Release references only. Never alter global allocator/settings or source state.
        del prior, decoder
