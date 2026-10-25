# 镜头虚化: primary evidence and acceptance boundary

Reference: **LNX-REF-WF-165438-165adae6a7**. Research date: 2026-10-24.
Status: **AUTHORED / UNRUN / NOT FEATURE ACCEPTED**.

## Requirement, not an implementation license

[PixCake official guide 165438](https://www.pixcakeai.com/guide/165438), updated
2026-09-17, specifies automatic depth analysis, blur strength, five bokeh style
names, subject or clicked-point focus with adjustable range, depth visualization,
clear/blur brush refinement, Apply/Cancel, and batch processing. Its public
description does not reveal the kernel, numerical coefficients, model, weights
or proprietary “圆形II” optics. No public screenshots, assets, code or model
weights were copied into this implementation.

## Mature open-source reference and original-code decision

[GEGL lens-blur documentation](https://gegl.org/operations/gegl-lens-blur.html)
describes a lens-blur operation with radius, highlight controls, input clipping
and auxiliary-mask semantics.

[The original GNOME commit](https://mail.gnome.org/archives/commits-list/2020-June/msg00957.html),
59fd2d12be0535683830b0f2cb60f22e5a6b2af8, dated 2020-06-02, documents genuine
round-aperture blur with fixed or mask-varying radius. The source is marked
LGPL-3.0-or-later. This supplies a mature reference that aperture blur is not a
Gaussian alias, but does not establish depth estimation or occlusion quality.

The local Rust core uses independently authored aperture geometry, fixed
pixel-box quadrature, explicit source radius and conservative depth visibility.
No GEGL implementation was translated, copied, linked or vendored; no LGPL
source is relabeled. Local code is GPL-3.0-or-later, matching the repository's
original cores. Mathematical reference is not software provenance equivalence,
patent clearance or a legal conclusion. Reusing actual GEGL code later would
require a deliberate distribution/compliance decision and retained notices.

## Depth model: read-only findings, not a shipped backend

The official
[Depth-Anything-V2-Small-hf card](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf)
identifies a 24.8M-parameter float32 DPT/DINOv2 relative-depth model compatible
with Transformers, under Apache-2.0.
[The original project](https://github.com/DepthAnything/Depth-Anything-V2#license)
distinguishes Small's Apache-2.0 weights from Base/Large/Giant's CC-BY-NC-4.0
weights. Do not infer that all model sizes have Small's license, or that a weight
license automatically settles data rights and redistribution packaging.

Read-only official metadata gives reproducible candidate identifiers:

- Model repository: `depth-anything/Depth-Anything-V2-Small-hf`.
- [Observed immutable revision](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/commit/5426e4f0f36572d16453bbda7a8389317b1bef99):
  `5426e4f0f36572d16453bbda7a8389317b1bef99`.
- [Published model.safetensors metadata](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/blob/main/model.safetensors):
  SHA-256 `3152477ce0d8d6978d76b995120de97cb5b928701fd0f817769f59e249a16b70`,
  approximately 99.2 MB. This is upstream metadata, NOT a hash verified from
  downloaded bytes. Xet's separate hash is not interchangeable with SHA-256.
- [Configuration](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/blob/main/config.json):
  `DepthAnythingForDepthEstimation`, model type `depth_anything`, DINOv2 hidden
  size 384, patch size 14, feature stages 3/6/9/12. Its Transformers version is
  null, so this file does not pin or verify a compatible package release.
- [Processor metadata](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/raw/main/preprocessor_config.json):
  DPTImageProcessor, 518×518 target, preserve aspect, multiple-of-14 dimensions,
  rescale 1/255, mean [0.485,0.456,0.406], std [0.229,0.224,0.225], no padding.
  This is an explicit model-input preprocessing path, not the canonical HDR
  render buffer contract. Input rendering and output depth resampling need
  separate provenance and quality review.

The repository currently has no Transformers dependency in engine/pyproject.toml
or engine/uv.lock. CPU/CUDA Torch requirements have lower bounds rather than a
verified exact runtime lock; ROCm has its own exact variant. Merely finding the
model class in a historical Transformers release is insufficient acceptance.
For example,
[Transformers 4.57.6 metadata](https://pypi.org/pypi/transformers/4.57.6/json)
currently lists security advisories. No old release is approved by this note.
The adapter must separately establish an exact compatible, security-reviewed,
license-reviewed offline dependency/weight manifest. No weights, package,
runtime, import or inference was fetched/executed for this core task.

The isolated depth adapter is a separate owned module. Missing approved weights,
unresolved runtime pins or failed evidence must yield explicit unavailability;
manual depth must be labeled manual, not presented as successful AI analysis.

## What this core actually contributes

- Independent circular and four other numerically distinct artistic aperture
  kernels, strict finite relative-depth/focus inputs and source-pixel radii.
- Explicit partial-alpha/near-versus-far visibility rule, premultiplied signed-HDR
  operation, exact neutral/clear paths and rejected invalid data.
- Bounded real-source tiles, declared complete-image halo, cancellation,
  resource admission and transactional tile output.
- Versioned C ABI, kernel capability bits, isolated source/build inputs and
  authored fixtures. Missing-module/replacement semantics preserve saved intent.

See [core contract](../../core/lens_aperture/README.md) for equations and limitations.
Five distinct local kernels are not proof of equivalence to five proprietary
styles. In particular the local rim-weighted disk is not verified “圆形II”.

## Gates that remain open

All listed execution gates are **UNRUN**, not failed and not passed:

1. Rust build, C ABI struct validation, safe/native fixtures, release artifact
   loading and host availability gating for the exact final source.
2. Genuine pinned offline depth inference; convention verification, flat/invalid
   output handling, source/revision binding, transforms, proxy/full-size mapping,
   portrait hair, reflective/transparent objects and uncertain boundary behavior.
3. Subject focus requires source-owned subject evidence. Point focus requires
   exact image coordinate mapping. Interval edits must not silently reinterpret
   saved depth conventions. No fabricated automatic focus success.
4. Interactive preview and full-size export parity with true halos; 4×4 aperture
   quadrature motion quality, highlight shape/energy, fine edges, signed HDR,
   soft alpha, 16-bit source fidelity and scene-specific depth-error artifacts.
5. Current one-depth visibility has known hard-inner-edge/asymmetric-spread and
   missing-background limits. Layered occlusion, hidden colour recovery and
   photographic bokeh acceptance are NOT established by the current core.
6. Preview/source scaling, explicit brush radius/flow/feather rasterization,
   depth view, Apply/Cancel atomicity, stale completion rejection, undo/redo,
   project/recovery persistence, missing-module recipe retention and batch work.
7. CPU p50/p95/p99, memory, cancellation, high-radius full-resolution cost,
   GPU strategy and quality-preserving acceleration. The O(NR²) reference path
   must not be called interactive or product-ready without actual measurements.
8. The parent-owned transport/UI/history/export integrations must be reviewed
   together with this core. A standalone algorithm does not close the manual
   requirement, nor does a disabled surface prove a completed workflow.

No feature is removed from the requirement to make this increment look finished.
