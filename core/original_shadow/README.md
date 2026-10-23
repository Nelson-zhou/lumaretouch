# Reviewed original photographed-shadow retention

Original, dependency-free Rust under GPL-3.0-or-later. Source-only delivery;
all authored tests are **UNRUN**. No imported implementation, neural model,
inference, model weights, general shadow detector, relighting model or AI
requirement-completion claim is made.

This module estimates a scalar black shadow layer from the **actual immutable
photograph**, independently of the existing synthetic projected shadow. It never
projects a subject mask, expands a silhouette, changes subject alpha, copies
source RGB onto the replacement floor, or regenerates the photographed shape.

## Required applicability and review

The supported model is one reviewed, diffuse, spatially uniform floor material
under approximately uniform unshadowed illumination. The user identifies both:

1. Representative **lit-floor sample coverage**, outside the reviewed subject.
2. A **shadow-retention coverage** region on the same floor in which the observed
   photographed shadow is intended to remain.

Both are float coverages, not a declaration that all selected dark pixels are
shadows. The caller must bind all inputs to the same immutable effective source,
dimensions, reviewed subject matte and review generation. For a derived creative
image, that effective source is the derived image, not its physical-original
provenance. This ABI cannot authenticate those relationships or a review receipt.
Require explicit homogeneous-floor applicability confirmation and a before/after
result review in the controller; do not silently accept extraction as truth.

The automatic sample-spread checks reject unsuitable **lit sample sets**. They
do not establish that the whole retention region has the same material or
lighting. In particular, a same-hue darker material, stain, print or painted
patch can be indistinguishable from a real shadow. Chromatic residual cannot
resolve that ambiguity. The method cannot promise general texture rejection,
recover very dark shadows, distinguish dark albedo, or recover coloured lighting
and specular or spatially varying floors. Wrong review/selection may produce a
wrong but numerically valid estimate. These are model limits, not missing tests
that a passing unit suite would remove.

## Estimator and fixed conservative thresholds

All channels are straight linear-sRGB D65 float32 in [0,1]; masks are finite
coverage float32 in [0,1]. Negative or HDR RGB and nonfinite values fail rather
than being clipped. Alpha is read only and never output or modified.

Let I be source RGB, a reviewed subject alpha, L lit-sample coverage and R
retention coverage. A sample is eligible only at a <= 0.001, R=0, and every
source RGB channel strictly below 0.995; its weight is
w = L (1-a). Support must satisfy both sum(w) >= 32 and effective sample count
(sum(w))² / sum(w²) >= 64. Foreground-marked samples never manufacture support.
Any retention overlap, including fractional feather coverage, excludes that
pixel from the lit baseline. Geometric overlap is otherwise allowed if enough
independent lit support remains; an inadequate remainder returns status 5.
Selecting two different mask object IDs is not evidence that geometry is disjoint.
The channel ceiling conservatively excludes clipped or near-saturated lit
references, including any individually saturated channel on a coloured floor.
The remaining samples must meet all support requirements: an all-white/clipped
reference or an inadequate unsaturated remainder returns status 5, not a fitted
baseline. This heuristic may reject genuinely bright unsaturated references;
the threshold is an abstention guard, not proof that lower values are unclipped.

Three fixed 1024-bin weighted histograms seed an RGB median. Two full-source
Huber-weighted RGB mean passes refine it: relative RGB distance d uses the norm
of the prior estimate (at least 0.025), and the robust weight factor is
min(1, 0.04/d), with factor 1 at d=0. Each pass must still meet the support
requirements. The histogram seed and final fitted floor must have luminance
Y >= 0.025, where Y = 0.2126 R + 0.7152 G + 0.0722 B. The conservative seed
threshold can abstain within roughly half a histogram bin of that boundary.

Call the fitted constant lit-floor RGB U. Validate the ORIGINAL weighted sample
distribution, not only the robust inliers:

- RMS of (Y(I)-Y(U))/Y(U) must be <= 0.04.
- RMS of norm(I-tU)/norm(U), t=(I dot U)/(U dot U), must be <= 0.03.
- At most 2% of sample weight may have relative luminance error > 0.08 or
  relative chromatic residual > 0.05.

Failure refuses the floor estimate rather than manufacturing a fallback. These
are original conservative engineering thresholds, not production-validated or
dataset-tuned quality guarantees. A severe sample set may fail robust support
before reaching the nonuniform-floor diagnostic; both require better samples.

For every source pixel in the retention region, estimate:

    t = (I dot U) / (U dot U)
    raw_shadow = 1 - t

This is a **zero-offset achromatic least-squares attenuation** model, not an
RGB six-parameter affine model or an albedo/illumination decomposition. The
attenuation is derived from the source image signal, not subject geometry.

Pixels with t <= 0.08 or t >= 1 are exact zero. Relative chromatic residual is
norm(I-tU)/max(norm(tU),0.02). Its gate is one through
max(0.015,2*sample_chroma_RMS), fades to zero at
max(0.04,4*sample_chroma_RMS), and stays zero thereafter. The conservative
attenuation noise threshold is e=max(0.01,3*sample_luma_RMS): shadow <= e is
zero, and the gate reaches one at 2e. A dark-measurement gate fades from zero
at t=0.08 to one at t=0.15. All fades use bounded cubic smoothstep.

Foreground exclusion is exact at a >= 0.02. Below that threshold, alpha is NOT
an additional opacity multiplier: the existing parent source-over compositor
already applies (1-a) to the shaded background. Finally multiply by R. This
conservative eligibility rule may omit real contact/edge shadows under mixed
foreground coverage; it does not reconstruct them. No morphology, feathering
of alpha, blur, spatial extrapolation, colour paste or mask projection is used.
The result is a finite [0,1] **source-owned scalar opacity** for an achromatic
black layer. Missing evidence is zero; retention coverage cannot create evidence.
If there is no eligible retention, including an exactly opaque reviewed alpha,
preparation returns bit-exact zero after validating every input, without requiring
lit-floor support. This does not imply that a floor model was successfully fitted.

## Applying the layer and blend semantics

Preparation does not include the user's shadow-strength setting. Apply it once:
q = prepared_shadow * opacity. For each replacement-background channel b,
with a straight achromatic source-layer channel s=0:

    result = (1-q) b + q Blend(b,0)
    Normal:     Blend(b,0) = 0
    Multiply:   Blend(b,0) = b*0 = 0
    Soft Light: Blend(b,0) = b - (1-2*0)*b*(1-b) = b²

Normal and Multiply therefore **coincide for this black layer**. Soft Light
differs and is a stylistic rendering, not physical linear attenuation. A zero
prepared shadow or zero strength copies background float32 bits exactly,
including signed zero. Full opacity does not alter the reviewed subject alpha.
The parent compositor owns compositing the subject over the shaded background.

Arithmetic uses f64 intermediates and stores f32. Background and scalar inputs
must be finite SDR [0,1] even for neutral calls. Unsupported HDR is refused;
there is no working-image clipping or colour-space conversion in this ABI.

## ABI 1

Library name: `lrt_original_shadow` (`liblrt_original_shadow.so` on Linux).
There is no runtime compilation or fallback if a packaged library is absent.
The following signatures use `size_t` for Rust `usize`, `uint32_t` for `u32`,
`int32_t` status/callback results and C calling convention:

```c
uint32_t lrt_original_shadow_abi(void); /* returns 1 */

int32_t lrt_original_shadow_prepare(
    const float *source, size_t source_len,
    const float *alpha, size_t alpha_len,
    const float *lit_samples, size_t lit_len,
    const float *retention, size_t retention_len,
    float *out, size_t out_len,
    size_t width, size_t height,
    int32_t (*cancel)(void));

int32_t lrt_original_shadow_apply(
    const float *background, size_t background_len,
    const float *shadow, size_t shadow_len,
    float *out, size_t out_len,
    size_t width, size_t height,
    float opacity, uint32_t mode,
    int32_t (*cancel)(void));
```

All lengths count float32 values, not bytes. RGB is contiguous interleaved HWC
with exactly 3*width*height values; every mask is contiguous HW with exactly
width*height values. Prepare output is HW; apply output is HWC RGB. There are
no hidden row strides, inferred cropping, resampling or alpha channels.
The same dimensions/lengths cannot prove the same source-grid identity; callers
must reject mismatched source bindings before invoking this module.

Modes are 0 Normal, 1 Multiply, 2 Soft Light; other values fail. Opacity must be
finite in [0,1]. A null cancel callback means no cancellation requested; a
nonzero callback result requests cancellation. Callback must not unwind or
modify/free inputs/outputs, and all input memory must remain immutable.

Statuses:

- 0: complete output, subject to the caller's final cancellation/generation check.
- 1: invalid ABI, dimensions, lengths, null/misaligned/overlapping output span,
  address arithmetic, opacity or blend mode.
- 2: unsupported/nonfinite source, background or coverage values.
- 3: cancelled.
- 4: pixel or referenced-byte resource budget exceeded.
- 5: inadequate original or robust-weighted lit-floor support.
- 6: lit floor too dark for this estimator.
- 7: lit-floor luminance/chromatic spread incompatible with the uniform model.

The caller allocates and owns every buffer. Output must be disjoint from all
inputs. Read-only inputs may alias each other, but the caller still owns their
meaning and correct extents. Nullness, alignment, exact length, arithmetic and
output overlap are checked before constructing slices. No ABI can prove that
an arbitrary foreign pointer is mapped, accessible or truly that long.

**Never install, cache or display any output from a nonzero result.** All
validation/model-fit refusals happen before output writes; cancellation during
the final output pass can leave partial output. A successful core return is
not permission to publish a now-stale generation or cancelled task. Check again
before publishing; old working state must remain installed on any failure.

## Source grid, bounds and cancellation

Estimate over the entire immutable effective source domain, before export
tiling. Crop the prepared scalar using exact source tile coordinates; application
is pointwise and tile-equivalent. Do not fit a different floor independently in
each tile, reuse a preview scalar as export evidence, or rescale mismatched
coverages in this core. Every preparation, including a preview, uses the entire
full-resolution effective source, reviewed matte and masks. Apply the field to
the full-resolution replacement background first; only then may the completed
shaded RGB background be reduced for display. Never downsample estimator inputs,
fit on a proxy, or substitute a preview field as export evidence. Resource or
source-availability failure must not trigger a proxy-fitting fallback.

Dimensions are positive and at most 65,536 each; maximum 32,000,000 pixels.
Checked admission also requires seven referenced float32 values per pixel plus
24,576 histogram bytes to fit within 1 GiB. At 32MP the referenced spans total
896,000,000 bytes, plus histogram scratch. This is NOT a total application-memory
guarantee: source copies, cached masks, replacement backgrounds, other fields,
Python/tensor allocations and export buffers must be admitted by the caller's
shared memory budget. Native release paths allocate no heap buffers, use three
fixed histograms and bounded scalar scratch, and have no iteration-to-convergence.

Preparation makes one validation/histogram pass, two robust refinement passes,
one original-sample quality pass and one scalar extraction pass: five bounded
full-source passes, plus constant histogram work. Apply validates then renders
in two passes. Polls occur after at most 4096 source pixels in every full-source
pass, including within a very wide row, and once after the last pass. Neutral
clearing is also polled in 4096-value chunks. These bounds cover scan work, not
wall-clock scheduler or foreign-callback latency. Any cancellation invalidates
all output, including already written chunks.

## Verification status

The `unrun_authored_tests` Rust module contains authored fixtures for actual
source-ratio extraction, coloured floors, weighted support, retention gating,
overlapping-mask exclusion, saturated-reference exclusion/refusal, no-shadow
neutrality, foreground exclusion, opaque
neutrality, refusal diagnostics, chromatic and dark
boundaries, the same-colour-albedo ambiguity, nonfinite/HDR rejection, ABI/overlap
bounds, blend semantics, exact neutral behaviour, tile equivalence and explicit
initial/partial-output cancellation. They are **UNRUN**. No imports, runtime execution, compiler,
typecheck, tests, inference, download, installation or Git write was performed
for this delivery. Numerical, visual, runtime and performance QA remain pending.
