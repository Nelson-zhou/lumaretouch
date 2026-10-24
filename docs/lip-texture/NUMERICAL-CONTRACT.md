# 唇纹修整: bounded original dark-furrow contract

**AUTHORED / UNRUN.** Feature `LNX-REF-PC-32464-C-b6315c40ca`.
This is an original conservative source-window photometric heuristic, not a
mature or validated lip-repair method and not commercial visual equivalence.

## Scope and research boundary

The [official feature description](https://www.pixcakeai.com/guide/32464) includes
visible lip texture, dry flakes/dead skin and small cracks. This implementation
attempts only attenuation of narrow **dark source furrows**. Bright flakes,
missing texture reconstruction, deep cracks, hydration synthesis, complete
occlusion/visibility diagnosis and general semantic defect removal remain
unfinished. Existing lip makeup deliberately preserves high-frequency source
texture; it is not duplicated or relabeled by this feature.

The [author-hosted Steger 1996 report](https://mv.in.tum.de/_media/members/steger/publications/1996/fgbv-96-03-steger.pdf)
motivates attention to line surroundings and asymmetric lateral contrast. No
code, formula implementation, coefficients, model or image from it is copied.
In particular, this is not Steger detection, scale-space analysis, subpixel line
localization, width recovery, linking or bias correction. The paired-flank
stencil, compatibility thresholds and gain restraint below are **original
unvalidated product policies**, not values calibrated by that publication.

## Exact API, ownership and colour contract

    apply(source_rgb, coverage, amount, *, across, radius,
          cancelled=lambda: False)

- `source_rgb`: exact native-endian numpy float32 H×W×3, encoded
  working-sRGB-D65 SDR, all values finite in `[0,1]`. It is the original effective
  source before this texture edit or lipstick/lip makeup, not an accumulated
  prior result. Its labelled transfer/profile is a host responsibility; values
  alone cannot authenticate a colour space.
- `coverage`: exact float32 H×W, finite `[0,1]`, source-owned geometric lip
  permission. It must not be a face box, inferred mouth fill, paint-only claim,
  semantic-confidence attenuation, or reused makeup-review approval.
- `amount`: finite scalar `[0,1]`, no booleans; `0` and `-0` are bit-exact neutral.
- `across`: two finite coordinates forming an already measured unit mouth axis,
  norm tolerance `1e-4`. No automatic normalization, missing-axis default, angle
  discovery, axis inference from the mask or portable axis field.
- `radius`: exact Python integer `1..12` in this source grid. It is measured
  current-grid scale, never serialized recipe intent and never silently reduced
  to make unsupported geometry or a resource refusal pass.

Only `{version:1, amount:float[0,1]}` is portable under `lnx.lip_texture.v1`.
`lip_texture_available` and `lip_texture_reason` describe required-symbol/ABI
loading, not photographic eligibility, successful correction or readiness.

Alpha, premultiplication, HDR/out-of-range floats, tensor inputs, wrong dtypes,
implicit profile conversions and RGB8 adapters are refused. RGB16 is converted
by the host directly to float32 with division by 65535, without an 8-bit round
trip; float32 can represent distinctions between adjacent RGB16 codes. This is
not a promise that every modified distinction survives final output quantizing.

Strided arrays are allowed but independently copied into owned contiguous
read-only snapshots. Source and coverage snapshots never alias each other,
even if the caller's arrays do. Caller inputs must stay immutable during
snapshotting. Returned RGB owns its storage and is not retained by the wrapper.

## Real support and geometry, not endpoint-only sampling

The host authenticates the photograph/revision, measured 478-point anatomy,
current grid/transform and selected person. Upper and lower lip surfaces are
built separately from real outer and inner contour chains, with mouth-cavity
seam, commissure connectors, other retained people and known occluders excluded.
Existing coarse exclusion evidence is not complete lip segmentation or proof of
visibility; a dark line that fits the photometry is not certified as a defect.

The source support layer chooses requested radius
`max(1, floor(measured_mouth_width * .012))`, refuses values above 12, and tests
the **actual measured surface thickness** through complete native-equivalent
footprints on each surface. It does not silently shrink the requested width
scale. At least four eligible centers on each surface are required by that host
layer; otherwise it raises an explicit insufficient-footprint refusal. These
are conservative policies, not anatomy/model confidence calibration.

Native candidate `(x,y)` must have an entirely allowed inclusive raster square
from `(x-3r,y-3r)` through `(x+3r,y+3r)`. Every pixel must have coverage at least
float32 `0.999`; the square must be in the actual array domain. An exact u32
bad-support prefix count establishes this without a radius-squared scan.
The host uses geometric inward feather with binary evidence eligibility, giving
unit-valued interior plateaus. A confidence such as 0.95 must not be smeared over
the entire lip as opacity and then presented as adequate native support.

This square is deliberately stricter than the union of sample corridors. It
contains all bilinear vertices and every intervening segment of all three
oriented stencils. A single excluded cell, even one not hit by a sample center,
can invalidate a candidate. A stencil cannot jump over a cavity/seam hole or
bridge disconnected upper/lower surfaces. Native cannot authenticate that a
malicious or mistaken all-one mask actually means lip tissue; host provenance
and contour exclusions remain necessary.

Use the complete real source window. A tiled/cropped computation needs a real
`3*r+1` source/coverage halo before cropping the result. No edge clamping,
reflection, repeated boundary samples, invented outside pixels, resampling,
proxy resolution or global radius substitution is allowed. Thin upper lips,
small mouths, occluded contours and very shallow interiors can have no complete
footprint and must be refused distinctly from a supported image with no eligible
furrow. Rotated-grid floating-point coordinates can introduce small numerical
differences; no universal bitwise full/tile equivalence is promised.

## Original float32 source-only measurement

All native photometric arithmetic and image scratch are float32. Decode standard
sRGB to linear RGB; compute `Y=.2126R+.7152G+.0722B`. Normalized chromaticity is
`c=RGB/(R+G+B)`; this is not CIELAB or perceptual hue. Reliable luminance keeps
the denominator positive. No fixed red, skin-hue, ethnicity or sex threshold is
used. Grayscale dark lines can qualify if the host supplies genuine lip support.

For each candidate, use normal/across directions `a`, `rotate(a,+30°)` and
`rotate(a,-30°)`; the along-line direction for each is `(-a_y,a_x)`. The measured
mouth axis is the expected cross-furrow direction, not a claim every lip furrow
is vertical. Curved/oblique furrows outside this sparse model can be missed.

For one orientation:

1. Test five cross-sections at along-line distances `0,-r,+r,-2r,+2r`.
2. Each section samples its center and four flanks at across distances
   `-r,+r,-2r,+2r` using bilinear interpolation in linear RGB. Every one of the
   four raster vertices must have full support and reliable colour, including
   a zero-weight vertex at an integer coordinate. Samples are never clamped.
3. A vertex is reliable only if every encoded channel is strictly between
   `.001` and `.985` and its linear luminance is at least `.02`. Black/crushed
   and near-clipped samples cannot contaminate a positive interpolation.
4. Let `yc` be center luminance, `l`/`h` the minimum/maximum of the four flank
   luminances, `q` their mean linear RGB and `ya=Y(q)`. Measure dark residual
   `d=l-yc`, not a blur residual or an invented replacement colour. Require:
   - `yc >= .02`;
   - `d >= max(.0015, .02*ya)`;
   - `d <= min(.06, .30*ya)`;
   - `h-l <= max(.002, .20*d)`;
   - every flank normalized chromaticity differs from `c(q)` by at most `.018`
     in each channel, and center chromaticity differs by at most `.025`.
5. **All five sections** must qualify, with their minimum residual at least
   half their maximum. The orientation's residual is their minimum. This
   requires persistence on both sides along the line and restrains a single
   dark point from being filled. It does not identify every possible blob or
   distinguish long dark pigment from a furrow.
6. Use the largest qualifying orientation residual, or exactly zero if none.
   Each orientation residual is still bounded by its own center's supported
   dark contrast. Amount and prior output never participate in these estimates.

Flank agreement rejects a simple step edge or strongly unequal surroundings;
near/far agreement limits broad depressions; continuity rejects isolated short
spots; only dark contrast is eligible, so bright flakes are not treated as dark
furrows. These are intentions embodied in authored synthetic fixtures, not proof
that all real edge/blob/pigment cases are distinguishable. Deep or near-black
cracks intentionally remain unchanged, not “recovered.”

## Common gain, residual restraint and honest texture claims

For measured residual `d`, source linear RGB `p`, source luminance `Yp` and center
coverage `w`, request luminance lift `L=amount*.35*w*d`. Use one gain:

    g = min(1 + L/Yp, (1-f32::EPSILON)/max(p))
    effected_linear_rgb = p * g

If `g<=1`, keep source bits. The shared gamut factor is chosen once, never by
clipping channels separately. Thus in exact arithmetic isolated output retains
source RGB ratios/chromaticity, stays inside gamut and raises luminance by no
more than 35% of the measured supported residual. At least 65% of that contrast
to the qualifying flanks remains. No flank colour or neighbor RGB is copied into
the output. Unlike an additive equal-channel offset, this gain does not bleach
the source channel ratios. Float32 encoding/rounding requires tolerances for
ratio/bound assertions and is not a perceptual hue guarantee.

Only modified pixels are re-encoded. If a vanishingly small correction would
re-encode any channel below its original code because of float32 roundoff, the
whole pixel is copied instead. Invalid numerical output is refused, not clipped
into validity. Zero amount, absent support, failed evidence, dark/clipped pixels
and exact endpoints bypass transfer round trips and retain their original bits.

No neighborhood RGB is blurred into the image and no missing texture is
synthesized. This does **not** promise exact high-frequency amplitude, texture
identity, global tone ordering or visual equivalence: a spatially varying gain
changes local contrast. Existing fine texture is attenuated only where the
original narrow-line model finds dark residual; photographic assessment is
still required. Dark pigment, suitable makeup patterns, shadows and repeated
strokes may fit this model, so explicit user review remains important.

The shared downstream renderer can extract this original source correction as
a linear-RGB source vector and compose it onto other authorized stages using
one headroom scalar. The isolated native ratio guarantee does **not** imply that
such a combined result preserves the current intermediate's channel ratios.
No other stage or strength change may redefine the original evidence source.

## Memory, ABI and cancellation

- Dimensions are `1..65536`, with the unchanged global `32,000,000`-pixel limit.
  No exception, larger-image bypass, reduced-resolution fallback or new global
  processing ceiling is introduced.
- Work is O(N) for decode/support plus at most three fixed 25-sample stencils per
  eligible pixel, each using four vertices. Cost does not grow with radius.
  This is a complexity bound, not measured speed or interactive latency.
- Native scratch is 28 B/pixel: 12 decoded-linear RGB, 12 private commit RGB,
  4 prefix counts, plus the prefix's extra row/column. Native input/output plus
  scratch is 56 B/pixel plus 8 MiB allowance, limited to 3 GiB.
- Python additional memory is 56 B/pixel: 16 independent source/coverage
  snapshots, 12 returned output and 28 native scratch, plus 8 MiB. Caller-owned
  RGB/coverage bring the local total to 72 B/pixel, limited to 4 GiB.
  `memory_estimate((H,W))` is pure arithmetic and validation, with no allocation,
  native loading, cgroup read or source analysis. `apply` separately checks the
  existing fail-closed CPU budget. The host must account for analysis, document
  intermediates and other owners. Allocation success is not guaranteed.
- Native uses checked sizes/address spans, explicit pointer alignment, exact
  float-element counts and output/input disjointness checks before making slices.
  Read-only inputs may overlap. These checks cannot establish pointer liveness,
  allocation ownership or foreign callback safety.
- `lrt_lip_texture_abi()` returns 1. `lip_texture.h` declares
  `lrt_lip_texture_apply_v1`. Codes: 0 success, 1 ABI/span/dimension/length,
  2 settings, 3 pixel/numerical refusal, 4 cancelled, 5 resources, 6 caught panic.
- Input validation, native initialization and pixel loops poll at least every
  256 pixels and at row boundaries. Python copy/validation blocks are at most
  4096 pixels. Native allocation uses `try_reserve_exact`; allocation latency
  itself cannot be bounded by the cancellation interval.
- Rust solves into private owned memory and checks cancellation immediately
  before final copy. All error/cancel returns leave the caller output untouched.
  Final copy has no callback/fallible work afterward: this is all-or-nothing at
  call return, not atomic concurrent publication. The caller must not inspect
  or mutate output while the call is running. A cancellation arriving during
  final copy is observed by the wrapper's post-call poll, which discards output.
- Python keeps its output private until every return code, callback exception,
  finite/gamut, monotonicity and protected-pixel check succeeds. Callback
  exceptions are re-raised outside ctypes; no partial output is returned.
  Panic containment requires unwind-enabled builds and cannot contain invalid
  pointers, process aborts or foreign faults. Callback/context must remain live
  and must not unwind, reenter or mutate participating arrays.

An installed ABI1 library is mandatory even for direct neutral `apply`.
There is no runtime compiler, downloader, installer, inference or Python image
algorithm fallback. The explicit offline packaging build hook and GPL source
files are documented in [`core/lip_texture/README.md`](../../core/lip_texture/README.md).

## Authored acceptance intentions, all UNRUN

Rust fixtures cover chromatic common-gain positives, retained source ratios,
bounded residual/strength, grayscale and rotated positives, pigment/asymmetric
flank negatives, edges, bright lines/flakes, broad/deep grooves, isolated spots,
black/clipped pixels, seam/intermediate-hole rejection, zero-weight bilinear
vertices, out-of-support independence, RGB16 adjacent codes, complete
supporting-neighbourhood crop agreement,
signed-zero/unsupported bit copies, late cancellation with untouched output,
strict settings/resources and safe/C ABI parity plus invalid spans.

Python fixtures cover exact portable identity, capability truthfulness, strided
independent snapshots, alias independence, RGB16 low bits, alpha/HDR/type/shape
refusals, pure memory arithmetic, pre-allocation resource refusal, native error
mapping, callback exceptions, protected-pixel corruption and missing-library
behavior. A test-only copy protocol is not the image algorithm. The installed
core smoke fixture skips when the required binary is absent and never builds it.

No build, compiler, test, type check, product import, model inference, sanitizer,
large-image resource/performance check, real portrait before/after review or
preview/export parity check has run. The exact acceptance assertions may still
need correction after separately authorized execution. No pass count, mature
algorithm claim, completed dry-flake repair or production-readiness claim is
supported by source authorship alone.
