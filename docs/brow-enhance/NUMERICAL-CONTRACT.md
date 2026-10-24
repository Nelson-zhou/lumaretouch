# Existing-brow enhancement numerical contract

Status: **AUTHORED / UNRUN**. This records intended behavior of original Rust,
Python boundary/state and authored fixtures. Source review, AST parsing and hashes
are not compilation, testing, inference, performance or photographic acceptance.
No new model, dependency, third-party code or binary is introduced. All execution
and real-image review remain separate, unrun gates.

## Scope, intent and provenance

The exact feature is `LNX-REF-PC-32471-C-18765fa8ea`, **existing-brow enhancement**.
The official [PixCake makeup guide](https://www.pixcakeai.com/guide/32471), checked
2026-10-24, describes a slider that reduces the existing brow effect to the left,
strengthens it to the right, and unlocks for independent sides. It does not supply
an algorithm, numerical limits, source assets or a code license. This operation
is not the separate fourteen-pattern brow makeup, brow geometry, hair restoration,
makeup removal, painted replacement brow or a generic exposure/curve operation.

Portable state is exactly:

    {"version": 1, "linked": true, "left": 0.0, "right": 0.0}

Operation is `lnx.brow_enhance.v1`. Sides are person-relative. Amounts are finite
plain numbers in [-1,1], never booleans; linked amounts must be equal. Unknown
keys, versions, masks, source references, radius and cached results are rejected.
`None` creates fresh neutral state. Only nonzero side amounts activate the edit;
unlinking by itself does not. Capability keys are `brow_enhance_available` and
`brow_enhance_reason`. Capability means required native symbols and ABI 1 load,
not that any photograph or brow is supported.

Mature conceptual background, not copied implementation:

- [He, Sun and Tang, Guided Image Filtering, author project](https://people.csail.mit.edu/kaiming/eccv10/index.html)
  discusses local models and linear-time filtering. This implementation is **not
  a guided filter**: it uses independently supported forehead-reference box sums.
- [Durand and Dorsey, Fast Bilateral Filtering, author project](https://people.csail.mit.edu/fredo/PUBLI/Siggraph2002/)
  documents log-domain base/detail contrast and chromatic-ratio reconstruction.
  Neither their bilateral algorithm nor their HDR tone mapper is implemented here.
- The specific [OpenCV guided_filter.cpp header](https://github.com/opencv/opencv_contrib/blob/4.x/modules/ximgproc/src/guided_filter.cpp)
  carries BSD-3-Clause terms. It must not be described as Apache-only based on a
  repository-level license. No lines of that implementation were copied or vendored.

The new implementation is original GPL-3.0-or-later, consistent with existing
original local Rust cores. Existing project buffer, sRGB and FFI patterns are
reused; no old kernel is silently changed. Coefficients below are conservative
original product policies, not official PixCake values, calibrated physiological
measurements or proof of visual equivalence. Public research access is not a
license to redistribute its figures/assets, nor a patent-clearance conclusion.

## Source and colour boundary

    apply(source_rgb, target_coverage, amount, *, reference_coverage, radius,
          cancelled=lambda: False)

- `source_rgb`: exact float32 H×W×3 encoded working-sRGB-D65 SDR [0,1]. This is
  the authenticated ORIGINAL effective source on the current render grid, not a
  previous enhanced result, proxy-derived field or synthesized/painted reference.
- `target_coverage`: exact float32 H×W [0,1], restricting correction to source-
  supported existing brow pixels. Coverage grants permission, not proof of hair.
- `reference_coverage`: separate float32 H×W [0,1] actual adjacent forehead
  support, positively disjoint from target coverage. Its RGB comes directly from
  the same source, never translated brow pixels, edge replication or filled data.
- `radius`: strict Python integer 2..128 from source measurements in this render
  grid. It is neither portable recipe data nor an arbitrary global face size.
- Return: new owned C-contiguous float32 effected RGB, **not a delta**, with all
  values checked before publication. The host derives its local effect delta.

There is no implicit dtype/profile/transfer conversion, alpha interpretation,
premultiplication, HDR clipping or array/tensor conversion. Float32 retains the
source RGB16 low bits; no RGB8 intermediate exists. Modified samples are still
subject to ordinary float32 rounding, so preservation does not mean reversibility.
Strided arrays are accepted only by independent contiguous snapshots. Callers
must not mutate them while snapshotting. Required native capability is checked
for `apply` even at neutral strength; there is no alternate Python algorithm.

Host ownership is essential: the core cannot establish face identity, source
revision, valid transformed landmark geometry, foreground semantics, occlusion,
foreign-person exclusion, or that forehead is unobstructed. The source layer must
make and authenticate this evidence anew on each target grid, preserve all its
vetoes and refuse an unsupported requested side. It uses conservative source-
derived support, not a user-painted/manual brush or a new segmentation model.
The source layer excludes black/noisy/clipped/unsupported target pixels and checks
adjacent forehead quality before calling Rust. Rust remains strict independently.

The crop contains all positive target and reference support for this side on the
same grid. The source layer derives radius from measured brow thickness plus
actual forehead-reference gap/depth and margin, refusing an unrepresentable
radius rather than clamping or increasing caps. One radius neighborhood is used.
Because every positive reference pixel is retained, samples outside the crop
have zero reference weight; no fake halo or full RGB radius-border duplication
is necessary. If generalizing to a crop of a larger nonzero reference field,
retain its true radius halo instead. No resampling is done inside this core.

## Local actual-reference estimator

Decode standard sRGB into f64 linear RGB. Luminance is
`Y = .2126R + .7152G + .0722B`. The independent reference supplies four actual
weighted statistics per square radius-r neighborhood:

    W = sum(w), Q = sum(w*w), A = sum(w*Y), B = sum(w*Y*Y)
    F = A/W
    variance = max(B/W - F*F, 0)

Only in-domain reference-supported pixels contribute. Missing neighbors are
absent, not replicated. Horizontal and vertical rolling sums cost O(N) with
bounded initialization, independent of radius-square area; horizontal statistics
are f64. Source RGB is not blurred or averaged into the output.

For **every** positive target-coverage pixel on an active side, require:

1. All statistics finite, W≥4 and Q>0.
2. Effective reference count `W*W/Q`≥4.
3. Finite 0<F≤1.
4. Local luminance coefficient of variation ≤.25, equivalently
   `variance ≤ .25²*F²`.

A negative variance below -1e-12 is refused; smaller negative floating-point
roundoff is set to zero for this statistic only. This is not RGB clipping.
Reference heterogeneity, insufficient mass, absent or invalid reference at even
one requested pixel refuses the **whole side** with status 7. It does not silently
publish a partly supported brow. Required reference is checked even where the
source pixel later proves black, bright or below the dark-residual deadzone.
Neutral strength or entirely zero target coverage needs no reference mass, but
all input types, SDR ranges, disjointness, settings and native capability remain
validated.

These sample/moment rules are heuristic restraint, not a skin classifier, a
calibrated confidence score or a physical estimate of what lies behind brow hair.
Smooth shadow, dark makeup, false landmarks or a consistently contaminated
forehead can still pass them. Upstream checks and user preview remain necessary.

## Original bounded signed dark-residual kernel

For target coverage m and signed amount a, let Y be original pixel luminance and
F its independently measured actual local forehead reference. Exactly copy
black Y=0, Y≥F, zero strength and zero coverage. Otherwise calculate:

    d = log(F/Y)
    r = min(max(d - 0.04, 0), log(4))
    g_requested = exp(-a * 0.40 * m * r)
    RGB_target_linear = RGB_source_linear * g

If r=0, copy original bits without transfer-function round trip. The residual
has a small deadzone and saturates; its derivative with respect to d is 0 or 1
away from the two corners. No steep darkness-derived smooth gate is multiplied
inside the core. Positive amount strengthens **existing** dark contrast by a
scalar less than one. Negative amount weakens it with a scalar greater than one,
without moving the source up to or through the reference. No brow locations,
colours, strokes, lost hairs or clipped detail are invented.

The requested scalar is bounded by approximately .57435..1.74111. For lifting,
limit it to `1/max(R,G,B)` in linear light. If this gamut restriction is active,
apply a `1-1e-12` interior factor to the common feasible gain, never separate
channel clamps. If the feasible scalar is exactly one, copy source bits. Thus a
source pixel with an already clipped channel is not lifted by distorting its
chromaticity. Deepening always stays inside SDR. Check every result before encode
and after float32 encode; numerical failure is a refusal, not repair/clipping.

For fixed F, coverage and chromatic ratios, before gamut limitation, the derivative
of log output Y with respect to log input Y is 1 or `1+a*.40*m`, bounded .6..1.4.
The negative control therefore retains source contrast rather than flattening or
reversing it. Gamut saturation can make a tone plateau, not an inversion for that
fixed chromatic direction. This narrow mathematical statement is **not** global
ordering across spatially varying reference, coverage, source-derived eligibility
boundaries or different chromaticities. Geometric feather and source selection
can still produce spatial artifacts requiring photographic review.

All target-zero pixels, reference-only pixels, neutral results, exact black,
bright/equal pixels and zero residual remain bitwise source copies. There is no
RGB averaging, sharpening or spreading a correction beyond positive target
coverage. Linear RGB ratios are preserved by a single gain, subject to float32
rounding; perceptual hue/appearance constancy is not claimed. Existing texture is
modulated, not reconstructed, and fine-contrast amplitude need not remain equal.

## Resource admission, cancellation and atomicity

Limits remain 32,000,000 pixels, dimensions 1..65536 and measured radius 2..128.
No existing renderer/global budget is raised. Native peak image scratch is 44
bytes/pixel: four f64 horizontal sums (32) plus private float32 RGB staging (12).
Referenced source/masks/output add 32 bytes/pixel, for native 76 bytes/pixel,
capped at 3 GiB. No full decoded RGB copy or new model allocation exists.

Python accounts for caller inputs (20 bytes/pixel), independent snapshots (20),
output (12) and native scratch (44), plus 8 MiB allowance: total 96*N+8MiB capped
at 4 GiB. Pure `memory_estimate((H,W))` returns additional `76*N+8MiB`, checks
shape/pixel/total limits, and never loads native, allocates images or reads live
memory. `apply` also checks it against the existing fail-closed CPU/cgroup budget
helper before snapshots. The host must reserve combined source, analysis,
parallel sides and all renderer stages. This estimate is not an OOM guarantee.

Native allocations use `try_reserve_exact`; validation, initialization, staging
and filter/adjustment loops poll at most 256 pixels apart and at row/column
boundaries. Initial sums are bounded by radius+1≤129 entries. Python copies and
validates at most 4096 pixels per chunk. System allocator latency is not bounded.

Native computes entirely in private staging. Returned errors and cancellation
leave the caller output untouched. After the final cancellation poll, success
commits through one non-cancellable contiguous copy. Cancellation racing after
that commit can still cause the Python post-check to discard its private output;
there is no partially published image. This is not a claim of hardware-atomic
visibility to an illegal concurrent observer or interruption of memory copy.

ABI symbols are `lrt_brow_enhance_abi` (returns 1) and
`lrt_brow_enhance_apply_v1`, declared in `core/brow_enhance/brow_enhance.h`.
Lengths count float32 elements. Statuses: 0 success, 1 invalid ABI/lengths/
dimensions/alignment/output alias, 2 invalid amount/radius, 3 invalid SDR/mask
intersection/numerics, 4 cancellation, 5 resource refusal, 6 contained Rust panic,
7 inadequate/heterogeneous actual local reference.

Spans and overflow are checked before forming slices. Input spans may overlap
one another but output may overlap none. These checks cannot validate allocation
ownership/lifetime; callers retain pointer and callback responsibilities.
Callbacks must not unwind, reenter or mutate buffers. Python stores callback
exceptions and re-raises outside FFI. Panic containment needs unwind-enabled
builds and cannot contain invalid pointers, foreign faults or process aborts.
The build hook only stages and atomically replaces its output library if later
explicitly executed; no runtime compilation or installation is attempted.

## Authored verification, all UNRUN

Rust fixtures cover signed selectivity/unchanged protected pixels, neutral and signed-zero exactness,
black/bright/deadzone identity, no invented brows on flat fields, achromatic dark
contrast, common-gain chromatic ratios and gamut, fixed-reference ordering,
RGB16 low bits, actual reference independence/crop agreement, inadequate or
heterogeneous reference refusal, overlap/SDR/settings/resource/ABI rejection,
mid-work cancellation and unchanged destination on refusal.

Python fixtures cover exact recipe and linked state, fresh objects, required
reference, strict dtype/shape/amount/radius/SDR, independent strided snapshots,
disjointness before native, pure memory estimate and unchanged 32M cap, resource
and cancellation ordering, callback propagation, missing capability, all refusal
statuses, protected-pixel/sign postconditions and independent input pointers.
Their protocol double is boundary instrumentation, not a numerical fallback.

Compiler/type checks, all numerical tests, native build/loading, sanitizer/FFI
stress, cancellation timing, large-photo memory/performance, target integration,
real-image preview/export parity, skin tones, lighting, tattoos/makeup,
occlusions, geometry edge cases and photographic quality remain **UNRUN**.
