# Reference-guided black/white edit-halo kernel, ABI 1

**Status: AUTHORED UNRUN.** Source inspection only. Rust compilation, linking,
unit tests, numerical fixtures, Python/native loading, full-resolution timing,
visual quality, real-image acceptance and product integration are **UNRUN**.
The source is not evidence that the feature is ready or that a quality target
has been met. The assertions in `core/fringe_repair/tests.rs` await local QA.

## Product target and honest scope

The target is a dark or white boundary halo introduced by editing around a
person, hair, clothing or accessories. It is not coloured lens fringing, an
alias of mask erosion/dilation, ordinary denoise, or a renamed detail filter.
The [PixCake official guide](https://www.pixcakeai.com/guide/AlCcjw85ql), read
2026-10-23, describes default-on entry, strength, add/erase manual coverage,
explicit update, presets and batch synchronization. This isolated kernel
provides detection and correction, not those application workflows. None of
those workflows is claimed complete by this document.

The kernel requires a **co-registered pre-edit structural guide**. A dark natural
strand and a newly introduced dark halo are not reliably distinguishable from
one edited raster alone. The guide must carry the same geometry, dimensions,
crop, sampling grid and RGB encoding as the edited image. It must precede the
halo-producing tonal/background operation, while including the same geometric
transforms. Supplying the final edited image as its own guide does not repair
halos; it supplies no evidence of a newly introduced artifact. Supplying an
unwarped original after liquify/body deformation is invalid integration, even
though the raw ABI cannot verify semantic registration.

This intentionally conservative v1 targets a locally coherent neutral lobe
beside a stable edge. Large background replacements, new geometry/occlusions,
strong colour spill, textured/nonmonotone boundaries, intersections, very curved
or short halos, low-contrast edges and effects already present in the guide can
be missed. Thin original features are preferentially rejected or retained, not
guaranteed safe under every texture, scale or registration error. Real hair,
fabric, lace and accessories still require blinded visual evaluation. These
limitations are not permission to substitute morphology or an unvalidated
edited-only fallback.

## Original algorithm

This implementation is original Rust; no third-party implementation was copied.
[Guided filtering](https://people.csail.mit.edu/kaiming/eccv10/index.html)
motivates using an independent structural reference and local transfer model.
[Farbman et al., 2008](https://www.microsoft.com/en-us/research/wp-content/uploads/2008/08/Farbman-EPD-small-SG08.pdf)
motivates explicit spatial-scale control and caution around gradient reversals.
Neither publication supplies this halo detector. The code does not implement
the guided-filter equations or a WLS solver and must not be described as either.

For each covered output pixel:

1. Inspect four normal directions (horizontal, vertical and both diagonals), at
   three scales `s = max(0.5, radius_source × scale × f)` for `f = 0.5, 1, 2`.
   Each profile samples both full-raster images at offsets `-3s, -2s, -s, 0,
   +s, +2s, +3s` using bilinear sampling with float64 arithmetic.
2. Average the two far samples on each side into anchors. Require stable side
   plateaus, a significant same-polarity guide/edited edge, little backtracking
   in the original profile, and the principal edge inside the middle interval.
   This rejects many natural thin ridges and conflicting structures rather
   than blurring them into a base layer.
3. Let `t` be the original center's luma position between its original anchors.
   Predict edited RGB as the **actual original center RGB** plus the linear
   interpolation of edited-minus-original anchor deltas. This retains original
   center detail rather than copying a flattened edge or reverting the entire
   edit. `t` is permitted only just outside the anchor range for numerical and
   texture tolerance, then bounded to `[0,1]` for the prediction.
4. Compute signed edited-minus-predicted residual. Require center prominence
   relative to the two nearer residuals, thresholded against local edited edge
   contrast, and approximately equal residual across RGB channels. Purely
   chromatic fringes are intentionally outside this detector.
5. Choose the strongest candidate once. Reject strong opposite-polarity evidence
   across scales/directions. Require the same lobe and edge polarity on both
   tangential neighboring profiles, at distance `max(1, s/2)`. Isolated noise,
   unsupported spots and missing border evidence do not trigger repair.
6. Subtract a common RGB delta, limited to the smaller of residual magnitude
   and 35% of local edited edge contrast, multiplied once by confidence,
   strength and manual coverage. This preserves channel differences before
   float32 rounding and cannot pass the selected predicted luma target. Each
   pixel reads the immutable inputs, never earlier repaired neighbors.

The minimum residual prominence is `threshold × abs(edited_edge) + 4ε`, with
`ε = 10^-6 × max(1, local absolute luma)`. Extremely weak edges, excessive
original backtracking, unstable anchors and residuals above 1.5 times local
edited contrast are rejected. These are exposed source design choices, not
measured optimal thresholds. The three spatial scales do not downsample the
image; no preview-resolution result is reused as full-resolution export.

## Pixel, coverage and precision contract

- Tightly packed native-endian interleaved float32 RGB, `height × width × 3`.
- Both frames use the same working RGB encoding. Current pipeline compatibility
  follows `photo_detail`'s RGB convention; Rec.709 coefficients are a **luma
  proxy**, not a claim of photometric luminance on transfer-encoded data.
  There is no ICC, transfer-function, gamma, premultiplication or alpha bridge
  here. A linear-working caller must keep both frames linear and validate its
  quality calibration separately, rather than mix encodings.
- All accessed RGB must be finite. Signed and above-one data are accepted. RGB
  is never clipped to `[0,1]`, quantized to uint8 or arbitrarily limited to
  65504. Arithmetic is widened to float64. An unrepresentable float32 result
  fails instead of saturating. Upstream provenance limits remain upstream.
- The optional full-source coverage mask contains finite float32 `[0,1]`.
  Null means automatic coverage of one. Zero leaves that pixel bitwise intact;
  fractional coverage attenuates **detected** repair. Manual adding does not
  force a repair where no candidate exists. Add/erase vector strokes and their
  composition are the caller's responsibility, not competing kernel modes.
- Strength zero copies edited storage bits exactly, including negative zero.
  Coverage zero or no accepted candidate also copies actual bits. Neutral
  pixels do not read guide data. Validate full immutable snapshots separately
  before caching, including guide pixels outside the requested tile.
- Alpha is not accepted or silently discarded. An RGBA caller must choose a
  deliberate opaque RGB stage or develop and validate an alpha-aware extension.

## ABI, dimensions, ownership and memory

Exact prototypes are in `core/fringe_repair/fringe_repair.h`.

- `lrt_fringe_repair_abi()` returns 1.
- `lrt_fringe_validate_rgb` and `lrt_fringe_validate_coverage` validate complete
  immutable snapshots once, with exact lengths; they do not allocate.
- `lrt_fringe_required_halo(radius_source, scale)` reports processing-raster
  support, or zero for invalid arguments.
- `lrt_fringe_repair_tile` receives complete edited and guide rasters, optional
  complete coverage, and an integer global tile origin/dimensions. All lengths
  count floats, not bytes. The output contains exactly tile width × height × 3
  floats. No arbitrary input window is accepted under this ABI.

Settings are finite: strength `[0,1]`, radius_source `[0.5,32]` original-source
pixels, scale `[1/32,8]` processing/source ratio, threshold `[0.001,0.25]` local
edge fraction. Defaults are strength 0.5, radius 2, scale 1, threshold 0.02.
At native-size inspection/export scale must be 1. Enlarged export explicitly
uses its enlargement ratio; preview uses its actual processing/source ratio.

Full source limit: 100,000,000 pixels, each RGB raster at most 1.2 GB. Tile limit:
65,536 pixels. Staged output is at most 196,608 float32 values = 786,432 bytes
(768 KiB). The kernel allocates no full-image intermediate, pyramid or cached
guide. Stack profiles and twelve candidate records have fixed size. Caller-side
retained snapshots, simultaneous render jobs, total source memory and mask
memory require a separate aggregate budget. Limits are not allocation targets.

Input pointers must reference live aligned readable allocations of their exact
declared lengths and remain immutable throughout the call. Output must be a
valid aligned writable span disjoint from all inputs, including partial overlap.
The two immutable input frames may alias each other. Numeric span, length,
alignment and overlap checks cannot prove that an address names a live buffer.
Fabricated/dangling pointers violate the ABI. A cancellation callback must not
unwind, mutate inputs, invalidate buffers or introduce a data race. It is polled
before allocation, each row, every 16 columns, after rendering and before commit.

Return codes: 0 success, 1 layout/dimension/length/overlap, 2 settings, 3 invalid
pixel/coverage, 4 staging allocation failure, 5 nonfinite float32 result,
6 contained panic, 7 cancellation. **Every nonzero render result leaves every
output byte unchanged.** Rendering and final commit are separate. Build with
panic unwinding if relying on the containment guarantee; panic-abort and an
invalid foreign callback cannot be contained by this boundary.

## Full-frame support, tiles and borders

The largest profile step is `smax = max(0.5, 2 × radius_source × scale)`.
A conservative support halo is
`ceil(3 × smax + max(1, smax/2) + 1)` processing pixels, including tangential
corroboration and a bilinear tap. Default parameters require 15 pixels; the
maximum radius/scale requires 1793. This is an access bound, not a promise that
every halo up to that width is detected.

Output tiles use global source coordinates and always read complete source
images, including evidence beyond the output tile boundary. They never clamp
at a tile boundary. This makes tile partition equivalence structurally intended;
bitwise equivalence remains an **UNRUN** acceptance assertion. The real source
boundary is different: a direction with missing profile/tangential evidence is
rejected instead of treating edge extension as evidence. Safe unsupported
border bands can therefore remain unchanged.

Runtime is bounded per output pixel, not proportional to an unbounded radius:
twelve seven-point paired profiles and, for a surviving best candidate, two
additional tangential profiles. Bilinear accesses have constant footprint.
This is a scalar reference-quality implementation, not a performance result.
Native-size multi-megapixel timing and interactive latency are **UNRUN**;
future acceleration must preserve global coordinates, original guide evidence,
bounded output staging and cancellation behavior.

## Local QA handoff, still UNRUN

Authored Rust assertions cover bitwise neutral and no-op identity, original
thin features, additive/affine grade neutrality, positive/negative edit lobes,
zero/fractional coverage, strength linearity, whole/tile equivalence, signed HDR,
single-pixel rejection, chromatic non-alias behavior, invalid input/settings,
required halo, cancellation, output atomicity and output alias rejection.

Required additional acceptance work: real original/edited portrait pairs with
recorded registration; blonde/dark hair on bright/dark backgrounds; flyaway
strands, glasses, jewelry, lace and cloth seams; white rims and intended specular
highlights; background/sky replacement failure modes; diagonal/curved/multiple
edges; varied radii and preview scales; rotated/cropped/liquified sources;
8K/100-megapixel resource limits; cancellation mid-tile; malicious ABI spans;
platform FFI calling convention and Rust toolchain; full pipeline order and
independent preset/batch/update/manual-coverage state. Record measured identity,
halo energy, protected-detail error, seams, throughput and memory separately.
Do not mark these passed merely because fixtures or assertions exist.
