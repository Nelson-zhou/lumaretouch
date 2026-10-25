# Acceptance specification: not executed

**Every item below is AUTHORED / UNRUN.** No compiler, tests, product import,
typechecker, native build, inference, benchmark, installation or real-photo
evaluation was run. A static source review is not a passing test result.

## Authored Rust fixtures

`core/skin_reference_match/tests.rs` specifies:

1. Independent 12×10 reference and 17×9 target ROIs recover both brightness and
   chroma shifts; no coordinate correspondence exists or is synthesized.
2. Apply reads actual current-stage RGB, not immutable fitting pixels. Interior,
   unconstrained shading ratios survive the common luminance gain.
3. Amount zero accepts absent evidence and copies negative-zero/current float
   bits exactly. Zero coverage and identical valid source populations are exact.
4. Missing reference/target support, black/white evidence and zero correction
   limits do not manufacture successful source evidence.
5. Low total confidence/weight mass and concentrated coverage fail evidence
   admission rather than relying on a nominal pixel count.
6. Separate brightness/chroma bounds preserve radial chroma direction and expose
   raw requested differences plus bound flags.
7. A minority contaminant population is downweighted; source output is not
   histogram-equalized or spatially smoothed.
8. Excessive population dispersion refuses instead of flattening distributions.
9. Streaming approximate medians are compared with a test-only exact sorted
   weighted oracle, including clustered values within one coarse bin, fractional
   weights, an exactly balanced binary-weight split and the finite-range bound.
10. A single full-region application and arbitrary 137-pixel partitions use the
    same transform and return identical bits without a halo.
11. Gamut-constrained correction uses one common vector coefficient, not three
    separately clipped channel results.
12. Unreliable current endpoints preserve bits; NaN/current or malformed fit
    refuses without modifying caller output, even at nominal neutral settings.
    Invalid source/coverage also refuses outside otherwise permitted support.
13. Fixed fit scratch and admitted pixel/byte ceilings are checked without
    allocating oversized images; a tile above 1,048,576 pixels refuses.
14. C ABI successful fit publishes both arrays; immediate and post-histogram
    cancellation leave both untouched. Neutral accepts null evidence. Overlapping
    fit outputs and output aliases of current/coverage/transform refuse before
    constructing mutable views.
15. Cancellation after apply staging has started preserves sentinel caller output.
16. Reviewed soft coverage scales the log correction against current pixels.

These fixtures may contain authoring errors. They are not validated by listing
them here. Compilation/FFI ABI checks and execution must be separately authorized
before anybody can report success.

## Additional required host and integration acceptance

- Actual native symbol/ABI capability detection. Missing/old/mismatched native
  code must not fall back to body-to-own-face, uniform tint or fake success.
- Reference/target photo identity, source version, declared working colour space,
  owner, reviewed support and selected-reference identity bind each fit/cache key.
- Reference-face exclusion is proved with full pixel bits after composing all
  target face/body applications, including overlapping/soft support edges.
- Target regions from multiple people and bodies are measured independently;
  a single pooled median must not masquerade as per-person matching.
- Source arrays stay unchanged; application uses the then-current render stage.
  Changing amount reuses a valid fit; changing source/reference/support invalidates
  it. No per-tile fitting, tile order dependence or accumulation on edited pixels.
- Host memory budget includes full-resolution source, ROI copies, masks, owner
  arrays, render/caches and concurrent tiles, not only the Rust accounting.
- Error/cancellation during any target/tile prevents partial frame publication.
  Missing evidence, stale review or a protected reference-face overlap blocks the
  active operation with an actionable reason rather than silently changing pixels.
- Recipe/undo/redo/zero-removal behavior, per-photo targeting, preview/export parity,
  native library packaging and normal regression coverage are independently tested.

## Photographic and performance gates

Use licensed/authorized full-resolution photos spanning faces and visible body
skin, multiple people, different exposure/colour under mixed illumination,
cosmetics, occlusion, textured skin, hair/clothing contamination, dark and clipped
sources. Review both improvement and failure/refusal cases. Do not classify
ethnicity or infer an intrinsic/global ideal skin tone.

Measure reference-face identity, out-of-support identity, brightness/chroma
movement toward the selected real reference, boundedness, local texture/shading,
absence of seams/halos, and output stability across tile splits. Separately record
neutral/error bit behavior and transactional publication. Actual memory/latency,
cancellation responsiveness and throughput at large admitted source sizes need
measurement; bounded source code is not proof of ordinary-photo usability.

## Explicitly open

Automatic brightest-face selection, person-instance/body segmentation and full
`control:PC-32465:19` completion remain open. No missing hashed LNX mapping is
reconstructed. This standalone numerical lane does not establish UI/host wiring,
an installed library, tested integration or photographic acceptance.
