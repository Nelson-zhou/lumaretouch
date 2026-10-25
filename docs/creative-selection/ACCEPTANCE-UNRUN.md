# Acceptance ledger: authored, not run

Date: 2026-10-25 UTC. Everything listed below is **UNRUN** unless a later,
separately authorized execution record explicitly replaces this status.
No build, test, typecheck, import, inference, install, benchmark, hardware probe,
external coding task or Git write was performed for this core work. Text/source
inspection and primary-reference browsing are not execution evidence.

## Authored native fixtures

`core/creative_selection/tests.rs` contains specifications for:

1. ABI version and platform struct layouts.
2. Exact fractional rectangle area.
3. All four float-coverage combination modes.
4. Ordered inversion, inverse(empty), double inversion.
5. Empty recipes and zero-area regular shapes.
6. Lasso automatic closure and direction independence.
7. Duplicate closure and self-intersection/even-odd area.
8. Ellipse fractional boundaries and approximate analytic area.
9. Continuous brush coverage between sparse points.
10. Independent brush opacity/hardness/subtract behavior.
11. Repeated brush points without opacity buildup.
12. Feather impulse and exact finite support.
13. Zero-extension canvas-border feather behavior.
14. Exact dyadic accumulator carrying, borrowing and subnormal preservation.
15. Bit-identical irregular tiles versus whole output, including mixed geometry,
    inverse, source-border halos and radii 0/1/4/16/256.
16. Immediate and delayed cancellation with unchanged output/stats.
17. Invalid geometry and each caller budget with unchanged output.
18. Wrong ABI, null output and integer-overflow/outside tiles.
19. Rejected output/input aliasing.
20. A bounded tile addressed inside a 6000×4000 authoritative canvas, without a
    performance assertion or full-image allocation.
21. Rejected empty brush, invalid brush mode/diameter/hardness, too-short lasso,
    nonzero unused fields and reserved recipe fields.
22. Entirely outside geometry and a lasso enclosing the complete canvas.

Test count and fixture text are not passing assertions. The build script and
Cargo manifest are provided for future authorized verification only.

## Required native verification before acceptance

- Compile both release cdylib and Rust test target, with recorded compiler,
  platform and command. Confirm exported symbol signatures against the header.
- Run every fixture, record failures honestly, then rerun after any changes.
- Add randomized bounded recipes checking finite range, no panic, no invalid
  output mutation, mixed-mode composition and independent tile equivalence.
- Exercise all limit edges, invalid/unused fields, pointer alignment, count
  overflow, feather extremes and optional stats/limits/callback variants.
- Use an independent slow numerical oracle on small fixtures, particularly
  rotated capsules, coincident lasso crossings, very thin shapes and feather.
- Measure cancellation during expensive geometry and large buffer allocation;
  never claim a hard time bound from callback placement alone.
- Measure real peak resident memory, not only `working_bytes`, and benchmark
  representative full-resolution source tiles plus pathological recipes.
  There is currently **no 24 MP performance result**.

## Required host/editor/compositor verification

- Native library unavailable/wrong version must fail closed and preserve the
  existing document, not substitute a Python, display or zero mask.
- Display coordinate conversion at noninteger zoom, pan, reverse drag and
  viewport resize; fixed size/ratio and pointer cancellation; undo/redo drafts.
- Source fingerprint/dimensions, recipe version and coordinate-space validation;
  byte-identical source-grid masks regardless of preview resolution.
- Identity, integer translation, negative translation, rotation, scale, shear,
  canvas clipping and group-composed affine projection to a selected leaf.
- Mask-before-affine application, explicit existing-mask merge/replacement,
  non-target layers unchanged, and stale/locked/missing/group targets rejected.
- Before/after preview receipt, stale review refusal, tile cancellation and
  failure rollback, bounded projection/cache/staging and source-mask completeness.
- History/undo/redo preserve exact old/new mask identities and coverage assets;
  interrupted asset writing never publishes a partially generated mask.
- Real native-window interaction and screenshot review, not only component or
  synthetic output tests. Visual quality must be judged separately from syntax.

## Completion gate

`ui:18`, `ui:19` and `workflow:127932` must not be marked fully complete merely
because these files or a fixture exist. Keep implementation, runtime integration,
numerical tests, native visual evidence and measured performance as distinct
statuses. This deliverable is an original modular foundation with explicit
unverified limits, not an accepted shipping implementation.
