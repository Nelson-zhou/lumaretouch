# Dedicated eye-white purification

Status: **AUTHORED / UNRUN**. This is original source, a release-build hook and
unrun fixtures, not a finished-feature, compiled-library or photographic-quality
claim. No imports, execution, builds, tests, inference, benchmarks or downloads
were performed to implement this slice. Local Qoder validation remains required.

## Distinct purpose and source ownership

This is a non-generative, supported local rank correction plus colour-cast
reduction. It is not an alias for sclera brightness, red-vein reduction, red-eye
correction, blur, replacement sclera, segmentation or geometry. It is intentionally
partial: small dull specks and mild casts may improve; broad blemishes, severe
darkness and poorly supported regions are not reconstructed. Separate optional
brightness and red-vein controls remain separate work.

The host passes **one source-owned eye ROI** as encoded working-sRGB float32
H×W×3 and matching finite float32 coverage in [0,1]. The host must authenticate
source identity/revision, face/eye, transform, geometry and raster dimensions.
Coverage is intended to exclude iris/pupil, lids/lashes, corners, skin, reflections,
unsupported pixels and protected regions. The current host uses a documented
geometric-plus-photometric **candidate**, not certified sclera segmentation or
semantic occlusion proof. It can misclassify glasses, lashes, reflections and
other anatomy. Source binding is verified by the host; anatomical correctness is
not. A rectangle alone is not anatomical evidence. The kernel cannot verify that
an array belongs to the claimed photograph or that its support is safe anatomy.

Positive coverage selects candidate targets. Reliable donor samples require
coverage **at least 0.75**, independent of whether a lower-confidence target may
be corrected. Zero and low-confidence pixels never supply the rank reference.
Masks must express confidence as well as feathering; there is no unmasked donor
fallback, dilation, boundary padding, reflected sample or fallback white colour.
No source sampling crosses this ROI or merges statistics between eyes/faces.
The 0.75 cutoff reflects supplied confidence, not a calibrated probability or
proof of clean sclera; real-image inspection remains necessary.

Input must be finite, unpremultiplied, encoded working-sRGB SDR [0,1]. Alpha,
negative/HDR values, float16, wrong dtypes/shapes and nonfinite values are refused,
including outside coverage or at amount zero. Array values cannot reveal colour
space: the host must perform any required conversion, not label linear RGB as
encoded sRGB. This operator internally linearizes for actual luminance work and
encodes its result back; the host must not double-convert it.

## Method

All choices below are original conservative engineering heuristics, not recovered
PixCake internals, measured naturalness thresholds or claims of equivalent output.

1. Validate every source channel and coverage value before any output writes.
   Decode eligible sRGB pixels into an f64 relative-luminance plane, using standard
   sRGB transfer and linear Y = 0.2126R + 0.7152G + 0.0722B.
2. Around each positive target, collect reliable donors from the square of radius
   r, excluding the centre. Only real in-ROI donors are considered. Require at
   least eight donors and at least ceil(r²/4) donors in **each strict quadrant**;
   also require quadrant coverage mass at least 0.125r². Missing support means
   exact preservation of that target, including its colour. Axial samples may
   contribute to the rank reference but never substitute for missing quadrants.
3. Sort those donors by Y and take their coverage-weighted lower median (first
   cumulative weight reaching half total). A compact dark-outlier gate additionally
   requires at least 75% of donor weight in every quadrant to exceed the target
   Y by t = 0.012 + 0.06Y. Flat shadows, ordinary steps and monotone ramps fail
   this directional condition. The median is a reference, never a replacement
   image or a low-pass filter of all luminance.
4. Only when that gate passes, original Y > 0.015 and deficit d = median − Y
   exceeds t, propose lift min(0.35(d − t), 0.045), multiplied by smoothstep(t, 2t, d).
   At full amount this corrects **less than 35% of the local deficit**, retaining
   more than 65%, and adds at most 0.045 linear Y. Black remains black. This is
   not enough to erase a shadow even if a compact structural depression passes
   the heuristic; it cannot identify the semantic cause of a dark spot.
5. Independently of the outlier decision, reduce chroma by moving linear RGB
   0.45 × amount toward [original Y, original Y, original Y]. Its Y is unchanged:
   no neighbour RGB is copied and no fine luminance is smoothed. This is mild
   cast reduction, not selective vein detection or blanket brightening.
6. Scale the proposed lift by amount and reduce it to available **shared** linear
   RGB headroom. Add that same nonnegative offset to every channel. Never clip
   channels independently. Mix the result with its own source pixel in **linear
   light** using target coverage, then encode to sRGB float32. Colour-only output
   retains source Y up to float conversion; outliers receive exactly the bounded
   positive Y change before float conversion.

Amount is a scalar in [0,1]. Amount zero, zero target coverage, insufficient donor
support and unchanged neutral pixels use direct-copy branches, retaining source
bits including signed zero. A neutral cast-free ramp or broad neutral step is
unchanged; a coloured ramp may lose mild cast while retaining its luminance.
The algorithm cannot guarantee semantic shadow classification on every real
photograph. Its strict gates and partial cap are protections, not visual acceptance.

Radius is **explicit source-raster pixels**, integer 1..32, never silently inferred,
capped or scaled in the kernel. The host derives it from authenticated geometry
and uses the same source-scale convention for previews/exports. Insufficient
resolution/support or excessive requested work must be refused or reported
unchanged, not replaced with whole-eye whitening or a downsampled approximation.
Repeated renders must start from the owned original snapshot, never accumulate
these corrections on the previous output.

## Primary-source research and licensing

Sources were actually read on 2026-10-23. No source code, assets, model or data
from them was copied, imported or added as a dependency.

- [SciPy median-filter documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.median_filter.html)
  and [rank-filter documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.rank_filter.html)
  establish neighbourhood order statistics and explicit footprint/boundary choices.
  Their implementation is **not** used here; this kernel selects only reliable
  masked samples and does not inherit SciPy padding or undefined NaN behaviour.
  The [SciPy license](https://github.com/scipy/scipy/blob/main/LICENSE.txt) was read:
  BSD-3-Clause, with notice/disclaimer and non-endorsement conditions if copied.
  No SciPy code is redistributed by this change.
- [W3C CSS Color 4, sRGB and linear-sRGB](https://www.w3.org/TR/css-color-4/#predefined-sRGB)
  corroborates encoded versus linear-light RGB and transfer conversion. The
  [W3C relative-luminance definition](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html#dfn-relative-luminance)
  corroborates the standard linear Y coefficients, not image-retouching claims.
  [W3C document licensing](https://www.w3.org/copyright/document-license-2023/)
  was read; documents and marked code components have distinct terms. This
  implementation independently expresses standard mathematical relations; it
  does not reproduce W3C sample code or redistribute specification text.
- [Official PixCake eye enhancement guide](https://www.pixcakeai.com/guide/202667),
  section “眼白净化” (retrieved lines 116–118), corroborates only product scope:
  dull blemishes/casts, optional additional brightening and complementing vein
  removal. User-supplied reference ID: **LNX-REF-PC-32470-C-26ab900915**. That
  identifier is not a fetched attachment or implementation license. No PixCake
  pixels, proprietary code, algorithm or claimed numerical equivalence is used.

The new original kernel follows this repository's GPL-3.0-or-later license. It
has no external Rust crates. Reading public documentation did not establish a
license to copy proprietary retouching implementations.

## Python and C ABI

`sclera_purify_native.apply(rgb, coverage, amount, radius, cancelled=...)` returns
independent, writable contiguous float32 HWC encoded working-sRGB. Exact NumPy
arrays are required. Torch hosts explicitly stage float32 CPU source/coverage,
call this bridge and restore their device; there is only one numerical kernel.
The bridge snapshots both inputs into owned read-only allocations, including
already-contiguous and strided input. Caller storage must remain unchanged during
snapshot copying. No caller storage is mutated or retained. Missing library,
invalid input, failed budget and cancellation never invoke another operator.

`lrt_sclera_purify_abi()` returns 1. C ABI 1 arguments, in order:

1. source float32 pointer and source element count;
2. coverage float32 pointer and coverage element count;
3. width and height (`size_t`);
4. amount (`float`), radius (`size_t`);
5. output float32 pointer and output element count;
6. optional `int (*cancel)(void*)` and opaque context.

RGB/output lengths are 3×width×height and coverage length is width×height. Lengths
are elements, not bytes. Null/alignment/range overflow/length/output alias checks
precede slice construction. Read-only input overlap is permitted; output overlap
with either input is forbidden. Pointer arithmetic cannot prove a live allocation:
native callers still guarantee valid immutable inputs, exclusive writable output
and a callback that neither unwinds, reenters nor mutates the buffers.

Codes: 0 success, 1 ABI/pointer/length/dimension/alias error, 2 settings error,
3 invalid SDR input/output, 4 cancellation, 5 resource refusal, 6 contained Rust
panic. Validation precedes output writes. Rendering cancellation may leave partial
output: **discard all output on every nonzero status**, including final cancellation.
The Python bridge owns unpublished output, captures callback exceptions without
unwinding across C, validates returned SDR rows and checks bitwise zero-amount
and zero-coverage preservation per row. It returns only on total success.

## Work, memory, cancellation and delivery gates

Limits: nonzero dimensions <=65,536; <=64,000,000 pixels; r <=32; and the conservative
footprint budget width×height×(2r+1)² <=64,000,000. Budgeting includes even unsupported
and out-of-ROI candidates, preventing sparse-mask exceptions. Sorting is in-place
on at most 4,224 samples, bounding uninterruptible per-pixel rank work; there is
no image-sized sorting allocation or unbounded radius. Large high-resolution eyes
may fail the work budget rather than silently reducing scale or correction radius.

Native allocation is an f64 Y plane (8 bytes/pixel), allocated with checked reserve,
plus a fixed 4,225-sample window. Python admission counts caller inputs, snapshots,
native Y and output at 52 bytes/pixel plus 8 MiB scratch, under a 3 GiB static cap;
additional allocations require 36 bytes/pixel plus scratch within the readable
CPU budget. Failed/ambiguous budget sources fail closed. Estimates cannot guarantee
allocation success. No proxy, HDR clipping, precision reduction or resize bypass.

Cancellation is polled before/after allocation, during input validation, decoding
and copy loops at <=4,096 pixels, during neighbour gathering at <=4,096 visits,
and before return. One bounded sort, allocator operation or maximum-width Python
row cannot be interrupted. Zero-coverage rendering still polls at pixel intervals.

`packaging/build-sclera-purify.sh` is an explicit, unrun system-rustc build hook
with no crate download. It replaces the target only after compilation succeeds.
The bridge expects `engine/src/lumaretouch_engine/bin/liblrt_sclera_purify.so`.

Rust fixtures cover bit-exact neutrality/exclusion, dark-speck partial lift,
neutral steps/ramps, cast-only Y retention, fine texture, support exclusion,
linear feathering, gamut bounds, invalid pixels, work admission, cancellation,
C pointer checks and output ownership conditions. Python fixtures cover snapshots,
strict arrays/settings, ABI error publication, missing-library behaviour, budget
and cancellation handling, optional real-native numerics and explicit Torch staging.
All are **AUTHORED / UNRUN**. Real-native fixtures skip if the binary is absent;
absence or a skip is not numerical acceptance or evidence that the feature works.

Before release: separately authorize build and tests, then inspect real portraits
with reviewed per-eye candidate support across lighting, skin tones, iris/corner geometry,
glasses/reflections, shadows, coloured sclera, partial occlusion and varied source
sizes. Check preview/export parity, source/revision rebinding, boundary protection,
load cancellation and actual memory/time. No photographic or production acceptance
has been performed, and this is not a diagnostic/medical treatment feature.
