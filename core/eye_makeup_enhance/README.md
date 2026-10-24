# Existing eye makeup enhancement v1

AUTHORED / UNRUN. Standalone GPL-3.0-or-later Rust cdylib, no dependencies.
This is original deterministic source-image processing, not learned AI, cosmetic
segmentation, a PixCake algorithm reproduction, or a photo-quality acceptance.

## Numerical operation

Input is encoded working-sRGB/D65 float32 RGB in [0,1], exact source grid. The
caller supplies independently validated reviewed makeup coverage and two disjoint
optional bare-skin reference coverages. The four signed [-1,1] controls are amount,
saturation, brightness, structure for ONE subject-relative eye. The host solves
both active sides against the same original effective source, never sequentially
against a previously altered result.

1. Convert original RGB to Oklab in f64. Form a five-channel summed-area table of
   coverage-weighted L/a/b, coverage mass, and permitted sample count.
2. A small normalized box mean B at measured radius r estimates source low/mid
   frequency appearance. Fine source residual P-B is never directly amplified or
   replaced. Every sample in a used footprint must have positive allowed coverage;
   missing/occluded/protected pixels are not extended, reflected or reconstructed.
3. With nonzero amount, two real user-reviewed neighboring bare-skin regions must
   each have at least 16 samples, sufficient mass, low within-region variance,
   similar lightness/chroma and plausible lightness. R is their equally weighted
   mean in Oklab, not known skin underneath makeup. Only measurable moderate
   source-to-reference differences are eligible. Amount adds .45*a*(B-R).
4. Saturation adds .40*s*B.a and .40*s*B.b, keeping the existing low-frequency hue
   direction. Brightness adds .075*b to L only. No palette or hue replacement.
5. Structure adds .65*d*(B.L - B3.L), where B3 uses radius 3r. This modifies actual
   midscale variation, not eye shape or pore contrast. Missing complete footprints
   and flat structure are refused for an active structure request.
6. Add the simultaneous correction to ORIGINAL Lab, weighted by reviewed coverage.
   Inverse conversion uses one segment gain found by bounded bisection when needed
   to stay in RGB gamut. No RGB component clipping. Gamut limitation can attenuate
   the requested effect and is not a perceptual guarantee after other edits.

The .005/.985 encoded-channel eligibility bounds, 32px minimum eye width, all
numeric gains and support/reference thresholds are conservative product policy,
not official calibration or validated perceptual constants. High-frequency
preservation is an algorithmic base/detail property, not an untested guarantee
that all makeup textures will look unchanged. Box kernels can have visible artifacts;
photographic checks remain mandatory before any quality or parity claim.

Negative amount is bounded appearance fading toward an estimable neighboring-skin
reference. It does NOT reconstruct underlying bare skin, remove all makeup,
remove liner/lashes, identify pigment, or promise a correct reference under
uneven lighting. Ambiguous references cause explicit refusal, not fake success.

## ABI

Symbols: lrt_eye_makeup_enhance_abi() -> 1 and
lrt_eye_makeup_enhance_apply_v1, declared exactly in eye_makeup_enhance.h.
Four independent explicit-count input arrays: RGB, coverage, reference A, B.
Output is separate and may not overlap any input; source arrays must remain valid
and immutable through return. Pointer allocation validity remains caller duty.
All lengths, non-null/alignment/address overflow, dimensions, controls and pixels
are checked before numerical work. Invalid input is rejected even at zero intent.

Status: 0 success; 1 ABI/length/alias; 2 controls/radius; 3 pixels/numerics;
4 cancellation; 5 allocation/resource; 6 contained panic; 7 ambiguous/missing
reference; 8 inadequate visible support or no measurable structure.
Output is untouched on all errors. Polling occurs during validation, conversion,
reference measurement, table construction and solve, before final atomic copy.
Rust panic is caught; catastrophic process allocation failure is not claimed recoverable.

Limits: 4 million pixels per full-source window, dimension <=65536, r in 1..64.
Native peak scratch is approximately 76 bytes/pixel plus 40*(w+h+1), excluding
caller inputs/output. Python uses independent source/mask snapshots and enforces
112 bytes/pixel plus prefix extras and 16 MiB additional-memory estimate. The host
also accounts for geometry, all simultaneous sides, merged delta and source owner.
No runtime build, native download, proxy fallback, alpha flattening or HDR clipping.

build_eye_makeup_enhance.sh is an explicit packaging script only. It and tests.rs
were authored, not run or compiled. Do not advertise the ABI available until an
independently authorized build installs the library and capability actually loads it.
