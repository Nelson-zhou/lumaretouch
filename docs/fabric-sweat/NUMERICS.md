# Reference-assisted fabric stain correction, numerical contract

Status: **AUTHORED / UNRUN**. No build, compiler, product import, type check,
unit test, benchmark, inference or photograph was executed. The source is not
quality acceptance, automatic detection, production enablement or completion of
PC-32477. The independent host must connect source ownership, review, history,
rendering and export. `tests_unrun.rs` contains unexecuted fixtures.

## Requirement and research

The original captured specification `ui/src/spec/refine.json`, PC-32477,
retains sweat-mask addition/subtraction, original/mask viewing and explicit update.
Related leaves are `control:PC-32477:5`, `:6`, `:14`–`:17`. Existing fabric fine-fold
softening is a different operation and is not reused or renamed here.

Official primary sources read on 2026-10-25:

- [OpenCV 4.12 seamless cloning](https://docs.opencv.org/4.12.0/df/da0/group__photo__clone.html)
  documents selected-region illumination changes via gradient-domain operations.
  Its public image contract is 8-bit. Its texture-flattening operation intentionally
  removes texture; neither API is imported or substituted for this float pipeline.
- [darktable contrast & texture](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/contrast-texture/)
  documents multiscale local contrast processing in linear RGB. This informed
  separating broad colour/brightness corrections from fine detail, not an assertion
  that this core implements darktable's guided filter or has its quality.

The implementation is original dependency-free Rust, GPL-3.0-or-later. No OpenCV,
darktable or RapidRetouch implementation code, model or asset was copied. General
low-frequency statistics are not a trained sweat detector. No licence acceptance,
installation or download is performed by this module.

## Frozen ABI and stage contract

`core/fabric_sweat/fabric_sweat.h` is the authoritative ABI 1 / algorithm 1 header.
Symbols: `lrt_fabric_sweat_abi`, `lrt_fabric_sweat_algorithm`,
`lrt_fabric_sweat_measure_v1`, `lrt_fabric_sweat_apply_v1`.
Library name from the Cargo crate is `liblrt_fabric_sweat.so` on Linux.

Measurement requires the genuine full source grid, contiguous native float32 HWC
**linear working-sRGB-D65 SDR [0,1]**. This differs from the neck module's encoded
measurement input. The canonical source resolver, not the numerical core, must
establish the colour conversion and authenticate full-grid source, revision,
identity, original/approved return source and repair stage. No implicit gamma,
ICC, proxy upsampling, HDR compression, uint8 conversion or current edited preview
is accepted as a measurement source by this contract.

Four independent HW inputs:

- garment weight float32 [0,1]: manually confirmed same material sampling region;
- target weight float32 [0,1]: affected area and boundary feather;
- clean-reference weight float32 [0,1]: manually confirmed clean same-material area
  with comparable illumination;
- hard protection uint8 exactly 0/1: excluded from both correction and all donor
  statistics, not merely masked at final output.

Target and reference may not overlap and each must be <= garment. Protection can
override painted target/reference without exposing protected samples. No mask
implies automatic garment identity, correct segmentation or same illumination.
The host must not assign a person's face oval to cloth or copy another photograph's
mask/reference. One field belongs to one same-source garment review.

Radius is an explicit integer 2..128 **source pixels**, default selection belongs
to the host. Small radii can follow texture and large radii can cross broad folds;
there is no claimed universal setting. Width/height are 1..65,536 and total pixels
<=32,000,000. Measurement emits a FULL-grid, not ROI, f32 HWC natural-log RGB gain
and HW u8 eligibility. All buffers are fixed lengths and caller-owned; no pointer
is retained. Host wrappers can make these arrays immutable but cannot call them
project/review authority.

## Original algorithm

1. Validate all source RGB and masks, including unedited pixels. Zero painted,
   unprotected target returns an all-zero field without requiring reference mass.
2. Compute clean-reference channel log means and weighted population variances
   using stable weighted Welford accumulation. Every unprotected selected reference
   RGB channel must be strictly between 1e-5 and 0.995. Require weight mass >=16
   and maximum channel log standard deviation <=0.35. These are conservative
   admission heuristics, not semantic proof of a clean garment; complex prints,
   deep shadows, saturated cloth or large illumination gradients may refuse.
3. Compute source-grid box low-frequency log RGB with two separable rolling sums.
   Samples use garment weights only, excluding protection, black and clipped
   channel observations. The square window is clipped at actual image boundaries;
   no reflection/replication, proxy fit or virtual edge pixels are introduced.
   The source-clipped box must contain >=75% effective donor mass. Soft garment
   confidence counts against mass. A target pixel with near-black/clipped RGB is
   ineligible. Complete lack of eligible context refuses with status 4.
4. At each eligible target, subtract local log channel means from clean-reference
   log means. Split the result into the arithmetic common-channel log component
   and channel residuals. Clamp common component to ±ln(2) and each chromatic
   residual to ±ln(1.25), then multiply by the target weight. Each final component
   is bounded by ±ln(2.5). Values below 1e-7 in magnitude are explicitly zero.
   Residual clamping need not retain exact zero-mean chroma; no perceptual hue
   preservation is claimed. No reference texture or spatial donor patch is copied.
5. Apply frozen gains once to the **current linear SDR RGB**. One common scalar
   `t <= amount` is reduced, when necessary, by all positive-gain channels'
   available headroom, with a small rounding margin. Then each channel becomes
   `current[c] * exp(t * log_gain[c])`. There is no independent channel clipping.
   Amount zero, zero field, zero channels and blocked headroom preserve original
   bits. A channel already at 1 with positive gain freezes the whole pixel.

Only broad locally measured multiplicative changes are proposed. This avoids
replacing cloth high-frequency pixels with blurred pixels, but does **not** prove
texture, printed-pattern, gradient, shadow, colour or contrast fidelity. A global
clean-reference colour can flatten legitimate lighting differences. The UI must
label the result reference-assisted, show before/after, and permit cancellation,
mask correction and a different reference. Do not describe it as proven sweat
removal, lossless texture recovery, Poisson cloning or automatic AI.

## Diagnostics and failures

`counts[4]`: unprotected positive target pixels, eligible target pixels,
context-rejected target pixels, pixels with any nonzero measured proposal.
The final count is not the rendered number of changed pixels. Amount/headroom,
float rounding and downstream processing may leave a displayed pixel unchanged.

`metrics[4]`: reference weight mass, max reference channel log standard deviation,
max absolute stored gain, minimum effective local support fraction over positive
unprotected targets. Zero target returns `[0,0,0,1]`; this is no-op metadata, not
proof of valid reference. A supported field with zero proposals succeeds honestly.

Status 0 success; 1 buffer/ABI; 2 domain; 3 radius/amount; 4 reference/context;
5 resources; 6 cancellation; 7 numerical; 8 contained Rust panic. Nonzero status
leaves every output buffer unchanged. Diagnostics are committed only on success.
The host should translate status 4 into a request to revise support/reference,
not automatically expand masks or silently fall back to another algorithm.

No foreign pointer, callback fault or caller mutation is made safe by catching
Rust panics. Pointer validity, native alignment, stable ownership and exact lengths
remain caller obligations. Inputs may overlap other read-only inputs, but no
output may overlap any input or another output. Callbacks may not unwind,
mutate buffers or reenter. Cancellation is checked during validation, row/column
passes and before output publication; no claim of sub-millisecond response.

## Memory and publication

Measure budget: `128*N + 8 MiB`. Native live arrays include caller RGB/masks
(25N), caller gain/eligibility (13N), private gain/eligibility (13N), horizontal
f64 rolling accumulator (32N), constant-size row/column sums, and diagnostics.
The conservative allowance also covers full private wrapper snapshots (25N) and
bounded bookkeeping. Host must charge its other live source images, other effects,
repair buffers, concurrency, review rasters and transport separately. This estimate
is not a whole-process memory guarantee.

Apply budget: `80*N + 1 MiB`, covering caller current/field/output (36N), private
output (12N), optional wrapper current/field snapshots (24N) and overhead.
No radius-squared loop or full integral image is allocated. Allocation uses
`try_reserve_exact`; budget admission occurs before pixel-sized allocations.
The host should refuse insufficient budget rather than retrying a smaller proxy.

`build_fabric_sweat.sh` is an explicit maintainer build recipe, not executed in this
slice and never a runtime auto-build hook. Existing packaging remains unchanged
until the designated integrator connects this optional native library and source.
The lockfile is authored for the dependency-free crate, not Cargo-validated.

## Authored fixtures and remaining acceptance

`tests_unrun.rs` covers neutral signed-zero identity, uniform-reference no-op,
bounded dark-target proposals, target/protection exclusion, common headroom,
overlap refusal, budget failure atomicity, buffer alias rejection and cancellation.
None has run or compiled. Required later checks include numerical fixtures across
radius/stride/source edges, reference weight/variance thresholds, static patterns,
complex garments, photographic stain/shadow distinction, colour-management parity,
full-resolution performance and full preview/export/undo integration. No completion
percentage or real-machine usability is established by these files.
