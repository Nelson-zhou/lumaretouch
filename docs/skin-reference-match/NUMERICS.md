# Numerical and ABI contract

**AUTHORED / UNRUN.** This document specifies source behavior and acceptance
targets, not measured runtime results. Core ABI version is 1.

## 1. Independent source populations

Fit takes a real reference-face RGB ROI and a real target-face **or** target-body
RGB ROI, with separate dimensions and coverage. It never resizes either, forms
pixel correspondences, copies reference pixels into target geometry, or infers
identity/ownership. Both ROIs use the same declared working colour space.

The host performs one source-owned fit per target region before tile rendering
and retains the resulting transform unchanged throughout that frame. Current
render tiles do not change the fit. Source/context invalidation belongs to the
host; transforms cannot safely be treated as owner-free reusable presets.

## 2. Coordinates and reliability

Inputs/outputs are finite float32 encoded working-sRGB-D65 SDR [0,1]. Negative
zero is accepted. All source/current channels and all supplied coverage values
validate, even outside coverage and at amount zero. The sRGB piecewise transfer
function is decoded to f64 linear RGB; calculations do not use RGB8.

The luminance weights are [0.2126,0.7152,0.0722]. An observation has coordinates:

- L = natural logarithm of linear luminance Y.
- U = ln(R/G).
- V = ln(B/G).

Let S(a,b,x) be cubic smoothstep, with its scalar argument bounded to [0,1].
The reliability factor is the product of:

- S(0.01,0.04,Y), suppressing unstable dark luminance.
- 1-S(0.70,0.90,Y), suppressing bright luminance.
- S(0.002,0.008,min(linear RGB)), suppressing unstable channel ratios.
- 1-S(0.95,0.995,max(encoded RGB)), suppressing near-clipped channels.

Observation weight is actual coverage times reliability. Zero weights contribute
nothing. Positive weights prove positive linear channels, so no logarithm epsilon
or synthetic black/white sample is introduced. The same current-pixel reliability
gate attenuates application. These are declared numerical heuristics, not a
classifier or a claim about intrinsic complexion/illumination.

## 3. Streaming robust centre and admission

Every source pixel is visited at original resolution. There is no random sample,
thumbnail, full-image sample array, histogram equalization or variance transfer.

An initial scan accumulates total weight W, squared weight Q, positive-weight
count and coordinate extrema. Each population requires all of:

- At least 64 positive-weight observations.
- W >=64 full-confidence-equivalent pixels.
- Effective sample count W²/Q >=64.

Weighted median approximation uses three simultaneous 2048-bin histograms,
one per coordinate, for two refinement levels. Each bin stores its f64 weight
and the minimum/maximum **actual measured values** contributing to that bin.
The median bin is the first nonempty bin whose cumulative weight reaches half
the population weight. Refinement restricts the interval to that bin's measured
extrema and subtracts the weight below it from the desired rank. Actual extrema
avoid adding fake boundary observations or overlapping adjacent bin populations.
The final statistic is the midpoint of the final measured interval, not an
assertion that a pixel has that value. A constant population returns its exact
coordinate rather than a bin centre offset.

Ignoring floating-point weight/range rounding, error relative to the weighted
median is at most half the selected interval span, conservatively the original
span/(2×2048²). Histogram weights are accumulated in deterministic raster order
using f64. Near an exactly balanced split, roundoff may select either median side;
this is not an exact-quantile or permutation-bit-invariance claim. The sources'
reliability gates bound initial coordinate ranges, and expected coordinate
quantization is on the order of a few millionths or better. Authored oracle
fixtures must still be executed before relying on the error behavior.

The same two-level method computes weighted median absolute deviations (MAD)
around the initial centre. Reject if MAD(L)>0.50 or hypot(MAD(U),MAD(V))>0.30.
These gates reject a broad/incoherent population rather than forcing it into the
reference distribution. Constant colour support is valid; zero dispersion is
not itself a lack of evidence.

One bounded robust reweight then uses per-axis scales
max(1.4826×MAD,[0.04,0.025,0.025]). For each axis, let
r=abs(value-centre)/(4.685×scale). Multiply the original weight by (1-r²)²
when r<1, otherwise zero, for all three axes. Recheck positive count, W and W²/Q,
and reject if less than 50% of initial weight remains. Recompute the three
weighted centre medians with these robust weights. There is no iterative
convergence claim or learned model. Diagnostics retain the **initial** MAD and
the final robust counts/weights/effective counts/centres.

Including input validation, successful fitting takes nine complete pixel scans
of each ROI: validation; initial evidence/extrema; two centre passes; two MAD
passes; robust evidence; two final centre passes. Histograms are bounded work
between scans. Invalid/insufficient evidence exits earlier. Pixel cancellation
is polled every 256 visits and during histogram initialization/reset/selection.

## 4. Bounded transform

The raw requested difference is reference centre minus target centre, on each
of [L,U,V]. There is no covariance/contrast/variance/histogram matching.

Caller limits are two finite f64 values:

- maximum absolute L shift in [0,ln(2)] (at most one stop).
- maximum Euclidean norm of the [U,V] shift in [0,0.35].

Bound L symmetrically, and bound the two-dimensional chroma vector radially,
preserving its direction. After bounding, components with absolute value <=1e-7
are snapped to exact positive zero to suppress subprecision noise. This means
two nearly identical valid populations may deliberately produce neutral output.

Immutable transform[4] is [1,dL,dU,dV]. Application validates version, finiteness,
abs(dL)<=ln(2)+1e-12 and hypot(dU,dV)<=0.35+1e-12. The 1e-12 admission tolerance
is for f64 rounding at the hard bound, not extra artistic range. Fit diagnostics
expose the raw difference and which bounds were applied.

## 5. Current-pixel application and gamut

For each actual current pixel P, let s=amount×coverage×currentReliability.
For nonzero s and a nonzero shift:

1. Q=[P.r×exp(s×dU),P.g,P.b×exp(s×dV)].
2. Desired luminance Y'=Y(P)×exp(s×dL).
3. Desired RGB D=Q×Y'/Y(Q).
4. Delta=D-P. Find one alpha in [0,1] such that every component of
   P+alpha×Delta stays in [0,1], taking the minimum feasible positive/negative
   channel bound.
5. If gamut constrained, multiply that same alpha by 1-16×f64 epsilon as an
   inward numerical margin; encode P+alpha×Delta to float32 sRGB.

There is no independent channel clamp. Non-finite/out-of-range arithmetic refuses
the entire application rather than emitting a clipped partial result. Exact
black/white or unreliable channels naturally take the unchanged reliability
branch. The logarithmic transform is evaluated by multiplicative ratios, so
application never needs to take a logarithm of an unreliable current zero.

This pointwise mapping preserves current detail instead of replacing it with
reference/source pixels or blurring a neighbourhood. In a constant-support,
reliability-one, gamut-unconstrained region, it multiplies local Y by one common
gain, preserving luminance ratios. Near changing coverage, reliability or gamut
constraints the gain varies; no universal bit-exact shading/contrast invariance
is claimed. Strong differing illumination may need a different reviewed target
scope, and a bounded adjustment may intentionally fall short of a full match.

Amount zero copies current bits exactly and needs neither fit nor evidence.
Coverage and transform may each be absent then, represented at C ABI as (NULL,0).
Supplied data still validates. Zero coverage or an all-zero valid shift also
returns that pixel's original bits. Active calls require both transform and
coverage. Active all-zero coverage is numerically a valid protected tile, not
proof that a host-level target has adequate source evidence.

## 6. ABI layout and statuses

Both functions use C ABI, size_t lengths/dimensions, float32 RGB/coverage and
float64 fit limits/transform/diagnostics. The full signatures are in the header.
Arrays are contiguous and native-endian. No stride, alpha channel, RGB16,
display-P3, HDR/scene-linear-above-one or colour-management inference is supported.

Diagnostics[24], zero-based indexes:

- 0: version 1.
- 1,2: final robust positive-weight reference/target sample counts.
- 3,4: final robust reference/target total weights.
- 5,6: final robust reference/target effective sample counts.
- 7..9: final reference centre [L,U,V].
- 10..12: final target centre [L,U,V].
- 13..15: initial reference MAD [L,U,V].
- 16..18: initial target MAD [L,U,V].
- 19..21: raw requested centre difference [L,U,V].
- 22: integer flags represented exactly as f64; bit0 brightness bounded,
  bit1 chroma bounded, bit2 a nonzero tiny component was snapped to zero.
- 23: minimum retained robust/initial weight fraction across the two populations.

Statuses: 0 success; 1 invalid ABI/dimensions/length/overlap; 2 settings;
3 invalid pixels or numerical refusal; 4 cancelled; 5 resource refusal/allocation;
6 caught panic; 7 insufficient reference; 8 insufficient target; 9 excessive
dispersion or retained-evidence failure; 10 invalid transform. A failed fit
publishes neither transform nor diagnostics, so status9 does not identify an ROI.

Input-input overlap is allowed because inputs are read-only. Output must overlap
no supplied input and fit outputs must not overlap each other. Checked pointer
ranges validate alignment, integer overflow and obvious overlap, not allocation
provenance. The caller owns live valid buffers and callback lifetime; inputs
remain immutable and output remains exclusive. Callback must not unwind, reenter
or mutate/free buffers. Panic catching cannot make invalid pointers safe.

All native nonzero returns leave outputs unchanged. Fit calculates local arrays
then copies both on success without fallible work between them. Apply computes
a bounded staging buffer, checks cancellation, then publishes. Neutral uses a
validated final copy directly. Publication cannot be cancelled and does not
provide concurrent synchronization or protection against a process crash.

## 7. Work and memory admission

Dimensions must be 1..65536 and arithmetic is checked before allocation/reading.

- Fit: reference+target <=32,000,000 pixels. Conservative accounted bytes are
  16×(referenceN+targetN)+262144, limited to 2 GiB. The 16 includes RGB+coverage
  caller inputs. Native histogram storage is exactly 3×2048×24=147456 bytes;
  the fixed 256 KiB allowance covers the histogram and small bookkeeping, not
  whole-process/allocator overhead. Source work is bounded by nine visits per
  pixel plus fixed histogram scans, or 288M pixel visits at the admitted ceiling.
- Apply: <=1,048,576 pixels per tile; accounted bytes 40×tileN+4096 <=64MiB.
  This covers current RGB 12, coverage 4, caller output 12, and native stage 12 bytes
  per pixel. Neutral still obeys the same admission even though it skips staging.

The host must separately budget original full-frame source, ROI materialization,
reference masks, owner/protection arrays, caches, concurrent tiles and final
frame publication. These core budgets are not a total-process RAM guarantee or
proof that the maximum source size meets any latency target. No performance run
has been made. There is no arbitrary final-resolution cap beyond the host's
frame contract: apply the immutable global fit to bounded tiles at native pixel
sampling, without resizing and without a halo. Full-frame/tiled parity is an
authored, unrun acceptance target.
