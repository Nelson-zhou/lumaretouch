# Optional lens depth adapter v1

Status: source authored; runtime, inference, visual quality and native integration
acceptance are **UNRUN**. This is an isolated module boundary, not a completed
lens-blur feature, installed model, or a hot-pluggable runtime.

## Public boundary and scope

`lens_depth_adapter.py` exposes `capability_v1()`, `proxy_extent_v1(source)`, and
`estimate_depth_v1(request, model_root=..., cancelled=...)`. Its frozen v1
records are `DepthSourceV1`, `DepthOwnerV1`, `DepthRequestV1`,
`DepthNormalizationV1`, `DepthResultV1` and `DepthCapabilityV1`.

The capability is deliberately unavailable. Both missing upstream byte pins and
an independent unconditional runtime-admission refusal block the proposed model
route before model imports. Filling a manifest constant, providing a wheel,
editing an installation receipt, or merely installing Transformers cannot unlock
it. An actual activation needs a reviewed implementation and acceptance work.

The sole candidate is the official `depth-anything/Depth-Anything-V2-Small-hf`
checkpoint. There is no interchangeable V1, Base, Large, Giant, metric-depth,
ONNX, `.pth`, pickle or guessed architecture route. No source/model is downloaded,
installed or discovered in caches. Imports do not inspect files or load models.
The caller supplies an explicit local directory; no environment or path search
is used to locate weights. No source path, arbitrary model ID, import callback,
user-authored manifest or remote code is accepted.

This module does not register commands, install packages, change the server,
commit history, mutate recipes, blur pixels, detect subjects, or persist assets.
Missing/invalid models and cancellation produce an exception and no result. The
host must preserve saved recipe intent and its independent neutral/manual-depth
path instead of discarding edits or inventing a depth plane.

## Immutable source and precision contract

- Owner identity matches the UI: document ID, epoch token, decimal uint64 revision,
  and oriented source SHA256/width/height/`exif_normalized_once`. Source identity
  is not a filesystem path. The host must authenticate it against its immutable
  snapshot; matching caller-provided strings alone is not proof.
- At most 100,000,000 source pixels and 1,000,000 pixels per edge; each edge is at
  least two. This adapter additionally limits aspect ratio to 4:1. Those are
  admission bounds, not promises of available RAM, speed or photographic quality.
- A request contains immutable packed RGB8 analysis bytes, not the source render
  image. Its whole-frame extent is exactly `proxy_extent_v1`: longest edge at
  most 1024, no upscale, integer half-up shorter edge. No crop, rotation, padding
  or undocumented transform is accepted. Mapping is
  `normalized_full_frame_pixel_centres` throughout.
- The host prepares encoded-sRGB opaque analysis pixels and a SHA256 identity of
  the actual colour/alpha transform. Tone mapping HDR or flattening alpha must be
  an explicit host analysis decision with retained provenance. The adapter cannot
  validate the original image from the proxy alone. These lossy analysis bytes
  must NEVER replace the linear, premultiplied, full-precision native source.
- The candidate uses the upstream DPT processor, including its Pillow RGB8
  resize semantics. It does not advertise a lossless float32 image-input path.
  Model input is float32, finite, one RGB batch, each edge a multiple of 14,
  at most 1536 per edge and 786,432 total pixels. A valid source can still exceed
  this preprocessor budget and is then rejected, not distorted to fit.
- CPU float32 only is specified. CUDA/ROCm/MPS, mixed precision, cross-device
  reproducibility, memory guarantees and concurrency scheduling are not accepted.
  There are no persistent model resources or global allocator/environment edits.

The proposed result holds immutable little-endian float32 bytes on the complete
original oriented source grid, plus its exact digest, owner, request identity,
model/runtime provenance and normalization description. The native aperture
core consumes this same-grid near-zero/far-one field alongside the untouched
original source. Source ownership must be rechecked after computation and again
at publication/commit. A stale document epoch or revision invalidates the result.

## Relative depth, not distance or confidence

The [primary paper, section 5.2](https://arxiv.org/html/2406.09414v2#S5.SS2)
describes affine-invariant inverse depth. Larger raw values are interpreted as
nearer, so the candidate maps each full-source value `p` to
`(maximum - p) / (maximum - minimum)`, after bicubic full-grid interpolation with
`align_corners=False`. Normalization arithmetic uses float64 chunks and only the
stored field is rounded to float32. It is per-image global min/max, without
percentile clipping, and therefore sensitive to outliers and framing. Bicubic
interpolation can overshoot; the recorded extrema are the post-interpolation
extrema. The field is not comparable across images, metres, camera distance,
f-number, a measured optical circle of confusion, or a calibrated uncertainty.

Constant and near-constant fields are rejected rather than turned into fake
focus planes. Nonfinite values and wrong shapes/dtypes are rejected. Uncertainty
is explicitly `not-estimated`; subject-focus data is always absent. Any subject
focus would require a separately authenticated subject mask, not an assumption
that the nearest region is the subject. No physical-camera or competitor-parity
claim is made.

The UI needs its own bounded full-frame u16 visualization. The shared host may
derive that from the normalized float field, record resampling, quantize using
`round(value * 65535)`, and hash the exact little-endian bytes. Its quantization
error is at most `0.5/65535` before other resampling error. UI u16 bytes never
replace the native float32 processing asset. Model provenance and owner bindings
must survive this derivation; `subject_focus` remains null without separate proof.

## Evidence and exact pins

Evidence inspected 2026-10-24 using primary public pages only; no checkpoint,
package archive or executable code was downloaded or executed.

1. The [official Small-hf model card](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf)
   identifies the compatible Transformers checkpoint and DPT/DINOv2 architecture.
   The [revision page](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/commit/5426e4f0f36572d16453bbda7a8389317b1bef99)
   identifies revision `5426e4f0f36572d16453bbda7a8389317b1bef99`.
2. The [revision-scoped weight metadata](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/blob/5426e4f0f36572d16453bbda7a8389317b1bef99/model.safetensors)
   publishes SHA256 `3152477ce0d8d6978d76b995120de97cb5b928701fd0f817769f59e249a16b70`.
   The [raw public pointer](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/raw/main/model.safetensors)
   gives size 99,173,660 bytes and the same digest. This is metadata evidence, not
   a locally verified checkpoint or an inference run. The Xet hash is NOT used
   as the file SHA256.
3. The [configuration](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/blob/main/config.json)
   identifies Small DINOv2 width 384, six heads, stages 3/6/9/12, patch 14 and neck
   widths 48/96/192/384; the published file size is 950 bytes. The
   [preprocessor](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/blob/main/preprocessor_config.json)
   is a 775-byte DPT configuration with 518-size aspect-preserving bicubic resize,
   multiples of 14, RGB rescale 1/255 and ImageNet mean/std. Exact upstream byte
   hashes and revision-scoped membership for these two small files remain
   unverified. Rendered text is NOT hashed and mislabeled as upstream bytes.
   Attempts to read the revision-scoped raw/API/config pages were inaccessible
   through the available reader; no access restriction was bypassed.
4. [Historical Transformers 4.45.2 source](https://raw.githubusercontent.com/huggingface/transformers/v4.45.2/src/transformers/models/depth_anything/modeling_depth_anything.py)
   and its [DPT processor](https://raw.githubusercontent.com/huggingface/transformers/v4.45.2/src/transformers/models/dpt/image_processing_dpt.py)
   were inspected to understand the public API, not vendored. Their source
   headers identify Apache-2.0. No upstream implementation is copied here.
5. The [official PyPI 4.45.2 JSON manifest](https://pypi.org/pypi/transformers/4.45.2/json)
   publishes `transformers-4.45.2-py3-none-any.whl`, 9,881,312 bytes, SHA256
   `c551b33660cfc815bae1f9f097ecfd1e65be623f13c6ee0dda372bd881460210`.
   It also lists security advisories. This digest is retained as historical
   research evidence only, NOT a cleared version, approved installation,
   authenticated installed-code inventory or compatibility recommendation.

The model card labels Small-hf Apache-2.0, and the
[upstream license scope](https://github.com/DepthAnything/Depth-Anything-V2#license)
distinguishes Small from Base/Large/Giant, which use CC-BY-NC-4.0. Small's license
does not authorize those larger weights. Any future redistribution must carry
the applicable license/notice material for actual distributed components.
This change redistributes no model weights or upstream source package.

## Local file verification and remaining acceptance

The authored reader uses an exact three-file allowlist, bounded reads, no-follow
directory/file traversal, regular-file/one-link/size checks, before/after file
identity checks and exact SHA256 comparison. The candidate consumes the verified
bytes directly through `safetensors.torch.load`, not a subsequently reopened
weight path, cache lookup or `from_pretrained` download. `strict=True` loading
rejects incompatible checkpoints. Configuration semantic checks are additional
guards, not alternatives to the absent exact hashes.

Activation still requires all of the following:

- Authentic revision-scoped config/preprocessor byte hashes and sizes.
- A platform-specific, security-reviewed runtime graph and exact distribution
  artifact hashes; verification of the entire actual imported code inventory,
  including dependencies, shadowing and previously imported foreign modules.
  Neither installed metadata nor a mutable local receipt provides that proof.
- Correct upstream class/config/checkpoint compatibility; processor and raw depth
  parity against the pinned implementation on real licensed fixtures.
- Boundaries: orientation, alpha/HDR analysis proxies, model extent, invalid or
  constant output, source changes, cancellation, memory pressure and concurrency.
- Actual native full-frame/tile depth alignment, focus ordering, occlusion/edge
  artifacts, UI visualization/click focus, history, save/reopen and export checks.

The fixture file in this directory is explicitly authored and UNRUN. Static AST
parse and authored-file hashes, if reported separately, are only syntax/inventory
checks. No tests, imports of authored application code, builds, type checks,
inference, installation, downloads, Git operations or external tasks were run
for this adapter change.
