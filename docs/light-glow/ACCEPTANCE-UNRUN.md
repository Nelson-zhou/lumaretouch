# Unrun light-glow gates

All items below are **UNRUN**, not failed and not passed. This source-only task
did not execute product imports, compilers, tests, build/typecheck, application,
benchmark, model inference, installation or downloads. Existing unrelated CI is
not evidence for these files. No whole-feature or whole-product completion claim.

## Authored numerical and ABI fixtures

`core/light_glow/tests.rs` covers declared struct sizes and math identity; exact
neutral bits; SDR/HDR/alpha/NaN/Inf rejection even when neutral; future math;
source geometry and pre-allocation budget checks; complete dispersed halo; three
non-aliased responses; alpha/domain preservation at control extremes; unchanged
unselected sources; true final-difference coverage; full-source tile/whole-source
comparison including alpha and image edges; finite support under strong tint;
early/late cancellation; error-atomic C output; length and overlap errors; and
bounded tint/exposure, and an independently written direct-window convolution
oracle. Merely authoring these cases establishes none of them.

Still required: compile on supported toolchains, FFI-size/layout across platforms,
sanitizer and malformed-input fuzzing, allocation failure injection, maximum-radius
edge cases, repeated operation
determinism, half-alpha analytic cases, callback lifetime/reentrancy harness, and
full adapter/native protocol tests against the exact packaged binary.

## User workflow and quality

- Genuine current edited source, source owner/revision/hash binding and stale
  completion rejection. Verify neutral RAW/TIFF/JPEG/PNG, RGB16 precision and
  supported mixed-edit captures separately. Unsupported HDR/negative/alpha routes
  must fail clearly, never clip, silently reduce or omit edits.
- Real before/after and coverage display. Preset expansion, manual edits after
  presets, each mode's default, cancellation, navigation and source change.
- Apply exactly once into an independent derived image with authoritative
  readback, query-only uncertain writes, original-history preservation, undo/redo,
  save/reopen and normal full-resolution export. A baked image must not be called
  an editable effect layer. Multi-photo work needs each target's source and review.
- Portrait eyes/hair/jewellery/wedding whites, specular points, coloured lighting,
  flat fields, deep blacks, transparent edges, fine texture and already clipped
  highlights. Assess black-mist local contrast, white veil/detail loss, chromatic
  dispersion/fringes, tint banding and artificial large-radius halos. Compare
  against actual user expectations, not only synthetic pixel invariants.
- Measure CPU wall time, cancellation latency and peak RSS at actual source
  sizes/radii. Tiling bounds scratch but repeated halo extraction increases work.
  Do not call it interactive or claim 24MP/100MP feasibility from asymptotic math.
- Verify root GPL notices and packaging. No external model or runtime is needed,
  but a missing native binary still means unavailable, not successful no-op.

Advertised learned illumination detection and physical-filter equivalence remain
outside this deterministic implementation. They cannot be closed by test success
for a luminance threshold. Keep the original capability visible as partial.
