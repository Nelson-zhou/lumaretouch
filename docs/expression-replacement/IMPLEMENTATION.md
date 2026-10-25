# 同场次表情替换：有界数值基础，不是整项完成

Requirement: `LNX-REF-PC-32468-C-0e5f836ef1` / `AI完美表情`.
Status: original source authored; static inspection only; no product execution,
imports, builds, tests, inference, downloads, installation or photographic QA.
This document records the isolated core boundary. The subsequent source-connected
current-photo workflow and remaining gaps are recorded in [INTEGRATION.md](INTEGRATION.md);
no full-feature or runtime acceptance is claimed.

## Evidence and retained product scope

The supplied manual `manual-text.txt` lines 520–523 describes same-session group
photographs, manual/automatic replacement and candidate-face selection. The
supplied AI package mapping at lines 2883–2897 associates this exact control with
PORTRAIT-012 but explicitly records no dedicated acceptance case. That related
module case is not evidence that this control is implemented or tested.

The primary [expression-management guide](https://wiki.pixcakeai.com/guide/9406.html)
was read on 2026-10-24. It confirms automatic replacement as the default and a
manual donor-face choice, followed by saving a separate result. It also describes
other smile controls. Those separate controls are not implemented by this core.
The original full automatic/manual interaction and save-copy requirement remain
open. This is a manual source-owned replacement foundation, not an automatic
identity search, a substitute smiling-mouth warp, or an expression generator.

## What the new source actually does

`core/expression_blend` contains original dependency-free Rust numerical code,
versioned C declarations, ABI documentation and authored synthetic fixtures. It
aligns actual donor crop pixels using eight contour/nose anchors, preserving
donor eye/mouth geometry. It requires human visual pose/occlusion review and refuses incompatible
measured 2D geometry, missing review, reflection, unstable alignment and absent source support.
The actual reconstruction uses float32 Gaussian/Laplacian bands, editable capped
fusion, hard protections and optional conservative reviewed-skin colour matching.
Each successful call returns separate target-crop float32 RGBA, actual effective
fusion coverage and a numerical receipt. No generated stand-in pixels or unsupported interpolation
fallback are used. Pixels outside accepted fusion remain exact target values.

[ABI contract](../../core/expression_blend/ABI.md) includes memory ownership,
colour/landmark conversions, error codes, atomic output, numerical settings and
the parent-owned preview/apply provenance lease. It also specifies module-disable
and missing/incompatible-backend behavior: preserve the recipe and report the
capability unavailable rather than silently dropping a saved effect. This is an
isolated module boundary, not hot loading of arbitrary runtime plugins.

## Real limitations, not feature reductions

- Exact native face-context crops must fit 1024×1024. Larger faces are refused,
  never resized to pass. Full-resolution large portraits still need halo-correct
  tiled/multiscale processing and numerical equivalence acceptance.
- Only opaque linear-sRGB-D65 float32 SDR. HDR/transparency support remains open.
- Real source and measured landmark capture, same-session candidate selection,
  face ownership and human same-person confirmation are caller responsibilities.
- The existing detector does not retain measured pose angles. This module takes
  no invented yaw/pitch/roll, using explicitly limited 2D compatibility checks and
  human visual review instead. It does not claim those ratios prove 3D pose or
  occlusion. Actual edited-source analysis must be freshly bound to that source.
- Eligibility may use the reviewed interior of a genuinely measured face oval,
  including eyes/mouth. It is not semantic skin or occlusion. Hard protections
  include foreign faces and reviewed exclusions. Optional skin reference is
  independently authenticated; absence is valid only at colour_strength0.
- Automatic bad-expression detection/best-donor ranking, automatic matching,
  full-group workflow, full-resolution UI preview/apply, project persistence,
  history, export, saved-copy placement and actual product wiring remain open.
- MediaPipe runtime privacy/provenance and model distribution qualification are
  independent gates; the Rust source does not resolve them by merely accepting
  landmark arrays. No library or model was downloaded, loaded or run here.

No requirement is marked done. The 16 original authored numerical/ABI fixtures
cover deterministic contracts, not facial quality or identity preservation.
Every fixture remains UNRUN. The native code has not even been compiled; static
source and manifest inspection cannot establish Rust type correctness.

## Required acceptance before activation

1. Build the isolated library under the authorized QA environment and run its
   fixtures, then ABI and Python/host bridge tests with a single frozen artifact.
2. Exercise cancellation during validation, pyramid stages and immediately before
   publication; invalid pointers must only be tested as arithmetic/overlap cases,
   never invoke undefined behavior with deliberately dangling allocations.
3. Test immutable ownership and race fences, changed target/donor FaceRefs,
   source/landmark/mask/review revisions, cancelled jobs, stale/unknown receipts,
   repeated apply, undo/redo, save/reopen, module missing/disabled and export.
4. Evaluate licensed same-session portrait pairs with genuine donor expressions:
   closed/open eyes, natural mouths, skin tones, glasses, pose and occlusion,
   hair/face boundaries and group-scene bystanders. Hard cases must show honest
   refusals and recovery, not be silently omitted from acceptance.
5. Inspect pixel precision, boundary seams, ghosting, lighting and skin texture at
   full resolution; measure latency and peak memory on target hardware. Numerical
   fixtures and absence of 8-bit conversion do not prove photographic quality.
6. Meet the original manual's task/sample and workflow acceptance, including the
   unavailable automatic/default and save-copy paths, before closing the ID.
