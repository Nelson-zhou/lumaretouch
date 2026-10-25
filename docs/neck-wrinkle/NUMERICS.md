# Neck fine-wrinkle numerics: authored source, all execution UNRUN

Requirement: `control:PC-32464:19`. Algorithm version:
`rapidretouch-neck-full-grid-v1`, ABI 1. No compiler, build, product import, test,
benchmark, inference, hardware probe or photographic acceptance was run. This
source does not enable a UI control, certify safety/quality, or close traceability.

## Provenance and separation

`core/neck_wrinkle/lib.rs` explicitly translates/adapts the pinned RapidRetouch
line/depth/relight method, **AGPL-3.0-only**, copyright Chris Cork. Pin:
`5e9d9c1d2770ff29d11a3879e5a90aad5887e028`. Exact original paths, helpers and Git
blob identities are recorded in `core/neck_wrinkle/NOTICE`; its full `LICENSE`
is copied byte-for-byte from the local archived upstream licence. Its SHA-256 is
`0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`.
No local existing derivative was changed. The Python ctypes and checked-array
integration files are original GPL-3.0-or-later integration, not a relicensing of
the numerical method. Existing combined-work/source obligations remain.

## Stable Python boundary

`neck_wrinkle_measure` exports:

- `ABI=1`, `ALGORITHM_VERSION`, `MAX_LOG_GAIN=log(1.25)`, `available()`.
- `plan(source_shape_hw, line_half_width_px, candidate_window_yxhw)`: pure metadata
  admission; no pixels, allocation, native load, source read or hardware access.
- `measure(source_rgb_f32, admitted_weight_f32, hard_protect_bool, *,
  line_half_width_px, byte_budget, cancelled=None) -> PreparedNeckField`.
- `apply(current_rgb_f32, log_gain_f32, *, amount)` for same-sized scalar field
  and **current LINEAR RGB**, returning a new array or the original on exact no-op.

A prepared field has `window_yxhw`, `source_shape_hw`, `algorithm_version`,
`log_gain` float32 and `eligible_mask` bool. Both are immutable bytes-backed
contiguous ROI arrays: callers cannot re-enable their write flags. `facts` is a
fresh JSON-safe dictionary decoded from immutable stored JSON. This object is
transient numeric evidence, NOT a source/person/review authority or portable
recipe. Its creator does not load files, invent source proofs or mutate owners.

Measurement input is exact native float32 HWC RGB encoded working-sRGB-D65 SDR,
finite [0,1], plus HW float32 [0,1] weight and a separate HW bool protection.
There are no alpha, HDR, uint8, implicit ICC or clipped conversion paths. Arrays
may be strided; private owned snapshots become contiguous. The caller must hold
its source/support capture stable while snapshots are made. Full RGB is validated,
including unedited/protected pixels. The adapter cannot tell a forged proxy from
an array; the canonical resolver must establish full-source identity and grid.

The output window encloses every positive unprotected input weight. A real
source-grid sample halo surrounds it, clipped only at actual source borders.
Clipping never makes unavailable border context eligible. A whole-source candidate
plan is permitted and conservatively larger than the actual mask-bounding plan.
A truncated candidate that omits positive support is refused by the C ABI.

## Finite method and exact dependency radius

Observed half-width `s` is 1.4..12 canonical pixels. Unsupported values refuse,
never clamp. The three Gaussian sigmas are `(0.5s,0.75s,s)`. RGB is decoded to
linear and Rec.709 luminance Y, then CIE L* using its exact rational low-light
constant. No corrected pixel feeds back into measurement.

The derivative follows these operations:

1. Gaussian at each sigma, radius `ceil(3 sigma)`. Two central finite-difference
   gradient passes have radius 2. Compute Hessian eigenvalues `l1>=l2`, maximize
   `sigma² max(l1,0) (1-clamp(abs(l2)/max(l1,1e-6),0,1))` across scales. This
   favors dark anisotropic valleys over similarly curved round features.
2. Smoothstep line strength through 0.4..1.1 L*; square maximum radius
   `ceil(1.5s)`; Gaussian sigma s. The resulting smooth line weight is not a
   semantic classifier or proof that a feature is a wrinkle.
3. Morphological closing uses a square dilation followed by square erosion,
   **each** radius `ceil(2.5s)`. This explicit separable square differs from the
   upstream elliptical footprint. Blur the closed L* at sigma `max(0.5,0.5s)`;
   nonnegative depth is closed-smoothed L* minus original L*. Smooth depth at
   pore sigma `max(0.5,0.3s)`.
4. Broad-fold evidence is maximum depth at radius `ceil(3s)`, Gaussian sigma s.
   Fold multiplier is `1-0.6 smoothstep(near,8,18)`. At deep-fold threshold the
   proposal removes at most 40% of estimated depth, before other caps. This does
   not prove 60% of actual physical fold depth remains. Dark-strand rejection is
   `1-smoothstep(depth,22,30)`.
5. Lift is depth × line weight × fold attenuation × dark-strand gate × admitted
   target weight, capped at 6 L*. No chroma is measured or borrowed. Derive
   target luminance from L*, cap positive gain at 1.25, and store natural log gain.
   Source luminance <=1e-8 and lift <=1e-6 make no positive proposal.

Let `G=ceil(3s)`, `M=ceil(2.5s)`, `C=ceil(3 max(0.5,0.5s))`,
`P=ceil(3 max(0.5,0.3s))`, `W=ceil(1.5s)`, `F=ceil(3s)`.

- Depth branch dependency: `D = 2M + C + P`.
- Line-weight branch dependency: `Q = G + 2 + W + G`.
- Broad-fold branch dependency: `B = D + F + G`.
- Complete conservative Chebyshev dependency radius: `R = max(Q,B)`.

For s=2, R=27 pixels, not the largest individual radius of 6. At s=12, R=161.
The actual eligible centers are the input permission `(weight>0 AND !protect)`
eroded by the entire square radius R, including source boundaries. This handles
both closing passes, both gradient passes, every spread/filter and the broad-fold
path. Eligibility is independent of signal. Invalid sample placeholders can never
reach a valid output because no valid target footprint intersects them. Protected
pixels are not donor observations. Merely masking a finished RGB correction would
not meet this condition.

All kernels are finite on the genuine source grid; no resize-based wide Gaussian,
reflection, replication, adaptive radius, masked-chroma fill or reduced-grid fit
is used. A narrow/occluded neck may have no complete context and must refuse.
The implementation is bounded, not a speed or latency guarantee.

## Current-stage application and truthful counters

Current input to `apply` is linear RGB SDR, not the encoded measurement source.
The current pixel receives one common gain:

`g = min(exp(amount*log_gain), 1+(1/max(current)-1)*(1-1e-12))`.

No independent RGB clipping is performed. Amount zero returns the original input
before native load, validation or allocation; no support is needed. Zero field,
all-black current and any channel already 1 leave the entire pixel bit-exact,
including signed zero. Positive edits preserve linear channel ratios subject to
float32 rounding, not guaranteed perceptual hue or preserved pore amplitude.
Output tiles slice the already measured field using their true source origins;
the core has no spatial dependency during application and never solves a tile.
The host must compose each owner once and reject foreign positive-region overlap.

Facts distinguish:

- `supported_pixels`: eligible full-context centers, mirrored by eligible_mask.
- `context_rejected_pixels`: positive unprotected target weight lacking context.
- `line_pixels`: eligible centers with positive smoothed line weight and depth.
- `changed_pixels`: positive **source-measured proposals**, not proof of a changed
  displayed/exported pixel. `changed_pixels_kind` states this explicitly. Current
  headroom/amount/float32 precision may block an otherwise positive proposal.
- Maximum proposed L* lift and stored log gain, sigmas, radius, no-signal reason,
  source grid, required/retained bytes and `runtime_quality_accepted: false`.

Valid context with no line signal is an honest successful zero field,
`no_detected_wrinkle_lines`. Line-like evidence with no surviving positive lift
(for example dark-strand rejection) is `no_positive_wrinkle_lift`, not a claim
that no line-like feature was detected. No admitted input or no full context instead raises
`NeckWrinkleContextError`. The host must inspect actual rendered differences before
claiming visible correction and must show actual eligibility, not raw painted skin.

## Resources, cancellation, C ABI and packaging

Source dimensions are 1..65,536 per side, total <=32,000,000 pixels. The operation
has a 4 GiB absolute accounting bound. Let N be full source pixels, S the real
halo-sample rectangle pixels, O the output ROI pixels:

`required_work_bytes = 34N + 80S + 15O + 8 MiB`; `retained_bytes = 5O`.

34N covers caller RGB/weight/protection (17N) and full private snapshots (17N).
80S conservatively covers all simultaneously live native L*/line/depth/fold
float64 intermediates and eligibility/erosion/filter scratch. 15O covers private
native, ABI output and immutable-retention field/eligibility pairs (5O each).
The 8 MiB allowance covers bounded validation chunks, row/kernel storage, Python
metadata and diagnostics; it is not a whole-process OOM guarantee. No unbounded
histogram, prefix plane, model or FFT workspace exists. Native vectors use
try_reserve_exact with mapped resource errors.

Admission happens before image-sized allocation, and is checked again by native.
The wrapper also compares incremental need to the existing fail-closed CPU memory
estimate. The host must charge repairs, analysis, rasterization, other operators,
retained people and concurrent work separately, without double-counting the
explicit resident 17N. A plan for one person is not aggregate multi-person
admission. Composition charges `56*current_pixels+8MiB`, including its current and
field residents, snapshots, output and private native result.

Cancellation is checked during validation, each finite filter pass/row and bounded
pixel chunks, and immediately before native publication. Native outputs and
statistics are untouched on every nonzero status. Python retains only private
buffers and polls again before returning immutable evidence. No partially solved
field or graph is published. Native apply exposes a callback; the minimal Python
apply contract is synchronous and its caller controls cancel-before/cancel-after.
A future responsive composition API needs an explicit contract extension, not an
unannounced Python fallback.

C ABI status separates ABI/buffer invalidity, invalid pixels, unsupported scale,
missing context, memory refusal, cancellation, numerical error and contained panic.
It validates dimensions, checked lengths/address ranges, alignment and pairwise
buffer nonoverlap before slices. Calls retain no pointers. Callers must provide
live allocations, stable input, exclusive output and a non-unwinding callback;
no FFI can validate arbitrary foreign memory or catch its access violations.

Only an installed matching `bin/liblrt_neck_wrinkle.so` is loaded. No native binary
is available merely because source exists. `available()` checks symbols/version,
not photo quality. The parent owns packaging/notice-stage integration. The full
AGPL licence and corresponding source/notice must travel with the derivative.

## Authored fixtures, pending acceptance

Rust/Python fixtures cover flat versus valley evidence, full dependency radius,
actual eligible output, protection adversaries, no-context versus no-signal,
strict scale/SDR/amount, immutable snapshots, cancellation, no-partial-output,
resource refusal, headroom/common gain and arbitrary field tile slicing. Every
fixture remains **UNRUN**, and backend-absent skips must not be called passes.

Further authorized runtime work must include isotropic spot/elongated pores,
wrinkles crossing pores, broad and deep folds, dark-strand thresholds, smooth
illumination ramps, RGB16 precision, adversarial masks at each dependency distance,
random tile layouts, peak memory and cancellation at every pass. Actual 100%
portrait review across neck tones, light, noise, age, profile/rotation, jewelry,
beard, marks, collars, hair, hands and multiple people remains mandatory. No
synthetic fixture can establish aesthetic or vendor-equivalence acceptance.
