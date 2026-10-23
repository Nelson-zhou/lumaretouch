# Reviewed original-shadow estimate: implementation-owned narrow method

Baseline `c05471a43230321484ab746b238d185f085ca673`. Source work and authored
fixtures are not numerical, runtime, photographic or product acceptance.

## Method and applicability

This is **manual-assisted source-data estimation, not AI shadow retention**.
The user selects lit samples and a separate retention region on the same uniform,
diffuse floor, using the source-owned geometric local-mask editor. The selected
foreground matte protects people and props. The method measures actual original
or immutable creative-return source pixels, not the projected person silhouette.
For this first method the subject support must also be source-geometric manual
coverage. Prompted/model subject mattes remain available to ordinary ID editing,
but their upsampled low-resolution fields are not admitted as native-full shadow
extraction evidence. A genuinely refined model-matte path remains unfinished.

In linear sRGB, a constant lit-floor RGB estimate U supplies a restricted model
I(x) approximately equals t(x) U. The least-squares scalar projection is
t = dot(I,U) / dot(U,U). Accepted attenuation becomes black shadow opacity 1-t.
The implementation rejects inadequate/dark/nonuniform lit samples and suppresses
chromatically inconsistent source measurements. It does not copy source-floor
RGB onto the new background or claim to fit a general affine lighting model.

**Same-hue stains, neutral texture and dark floor markings can satisfy this model
just as a shadow can.** Chromatic residual is not a texture detector. The explicit
homogeneous-floor confirmation and actual before/after review are essential;
textured floors, colored illumination, gradients, glossy surfaces and multiple
receiving materials are outside the supported assumption. No quality claim is
made for feet/props contact boundaries or fine penumbrae without photo acceptance.

The full source is measured once before export tiling. Preview may resize the
completed scalar field, but cannot fit a proxy/RGB8 surrogate and promote it to
full resolution. Native RGB16 and canonical float source precision must survive
measurement; unsupported alpha/HDR is refused, not clipped. The saved recipe
contains source-owned authored inputs, not one raw float field per history frame.
Native PNG16 can use ordinary RGB8 delivery while retaining full source precision
until final quantization. Existing ordinary RAW/TIFF16-to-RGB8 delivery still
decodes early to RGB8, so this effect refuses that route; use the genuine full
16-bit export/review path instead. This slice does not quietly accept the older
lower-precision input or claim that all output-format combinations are supported.

## Composition

The scalar field acts on the replacement background before foreground source-over.
User strength enters once. No second continuous foreground-opacity attenuation is
applied to a field already restricted by foreground eligibility. Designed/projected
shadows are a different family and are mutually exclusive with this first estimate.

The estimated layer is achromatic black. For layer opacity q and background B:

- Normal: `(1-q) B`.
- Multiply: `(1-q) B`; identical to Normal for this black layer, deliberately.
- Soft Light: `(1-q) B + q B²`; an artistic blend, not physical relighting.

Blending uses linear RGB. These formulas do not promise parity with another
editor's blend-space configuration. Disabled/zero strength/zero retained support
must be exact bypass. Numeric thresholds and 0–100 strength are our choices, not
published official defaults.

For the live low-resolution canvas, textured replacement assets have an explicit
resampling approximation: shade the full background first, reduce shaded and
unshaded RGB identically, and apply their bounded transmission ratio to the
existing display background. This keeps neutral and small-strength behavior
continuous without pretending that multiplication and resampling commute.
The full-source review pair, 100% inspection and export retain the full field;
pixel-exact parity with the low-resolution canvas is not claimed.

## Ownership and user flow

An explicit ID-background v3 edit adds independent original-shadow intent while
preserving old v1/v2 records. Spill edits and scoped spill undo must preserve this
sibling. Lit and retention masks retain separate reviewed source bindings and
digests. Neither person alpha, spill coverage nor recovery is relabelled as an
original-shadow estimate.

Preview is an isolated complete before/after render, not apply-then-undo. Apply
requires the same source, recipe revision, full-state/people identity and image
hash acknowledgment. Actual installation and rollback must be checked against
their frozen expectations. Unknown delivery is queried, never blindly resent.
Existing unified document history, project validation and ID recovery own the
same nested recipe and full prepared background contribution.

While this effect is active, ordinary background/support replacement is refused
until a reviewed disable; users can clear the background as an escape.
When the processing library is absent and the parent background is inactive,
the panel permits only a reviewed disable of retained shadow intent, preserving
its other fields; it does not pretend the missing kernel can generate a shadow.
Whole-ID
transfer cannot copy source samples or silently recompute an active estimate.
The initial portability fence also refuses nonneutral retained shadow intent
when disabled; there is no separate clear-samples action in this slice. Other
parameter-only scopes keep their existing ownership rules. This conservative
whole-ID limitation is not claimed as complete preset/batch support.
Dedicated per-target original-shadow batch/preset review is not implemented.
The first retention interaction uses existing source-local brush objects; a new
in-panel direct erase/restore canvas is not claimed.

## Seven requirement statuses remain separate

Prefix `LNX-REF-PC-32475-C-`; all statuses are source scope, never acceptance:

| Suffix | Requirement | Boundary |
| --- | --- | --- |
| 442ced0175 | Original-shadow entry | Narrow manual-assisted method only |
| ab010073e3 | AI retention | **Unimplemented**; no verified deployed model/weights |
| 48553e2d03 | Strength | Local 0–100 scale; quality UNRUN |
| c959928d7a | Normal | Standard black-layer Normal |
| b1b766d4ce | Multiply | Standard Multiply; black-layer result equals Normal |
| 9e1c732ff8 | Soft Light | Standard artistic Soft Light, linear blend space |
| 0513155f3d | Retention brush | Independent reviewed source-local mask selection; direct panel painting unfinished |

The family therefore remains **partial**, even if all bounded source paths are
connected. Do not count UI wiring, transport adapters or tests as extra features.

## Primary grounding and licensing

Read 2026-10-23. The [official guide](https://www.pixcakeai.com/guide/32475)
distinguishes photographed original shadows from added designed shadows.
[SID](https://arxiv.org/html/2012.13018v2#S3) provides a broader affine-plus-matte
formulation, not this exact restricted estimator. Its adjacent prose and equations
disagree on matte endpoints; this implementation defines identity as t=1 directly.
[Shor and Lischinski's publisher abstract](https://onlinelibrary.wiley.com/doi/10.1111/j.1467-8659.2008.01155.x)
supports user assistance identifying lit/shadowed regions of the same surface.
[Shadow Matting and Compositing](https://grail.cs.washington.edu/projects/digital-matting/papers/sig2003.pdf)
uses richer observations; this single-image approximation is not their full
physical scene reconstruction. Exact blend functions follow
[W3C Compositing](https://www.w3.org/TR/compositing-1/#blending), and sRGB decoding
follows the [standard conversion](https://www.w3.org/TR/css-color-4/#color-conversion-code).

The Rust kernel is original project code, GPL-3.0-or-later. No model, weights,
dataset, binary or third-party implementation was downloaded or copied. SID,
SynShadow, ShadowFormer and PyMatting code licences and separate checkpoint-rights
limitations are recorded in [the research record](REQUIREMENT-AND-RESEARCH.md).
MIT repository code does not establish separately hosted weight redistribution
rights. Unverified rights mean unverified, not a claim that use is prohibited.

## Acceptance still required

All fixtures are **AUTHORED / UNRUN**. Required checks include no-shadow identity,
uniform-floor attenuation, neutral dark texture false positives, colored surfaces,
dark/clipped samples, opaque foreground protection, lit/retention overlap,
full-source/RGB16/derived/tile parity, dependency tampering, source relocation,
undo/reopen, canceled preparation and unknown receipts. No compiler, tests,
typecheck, inference or photo evaluation ran during this source slice.
