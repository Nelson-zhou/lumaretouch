# Acceptance plan: not executed

AUTHORED / UNRUN, 2026-10-25. Only source inspection, source text consistency and
file hashes are permitted in this implementation window. Do not interpret fixture
presence, source review or hashes as a Rust build, test pass, measured quality,
performance benchmark or end-to-end delivery. No product imports, builds, tests,
typechecks, native loads, inference, downloads or installs have been performed.

## Authored native fixtures

`core/hair_unification/tests.rs` contains future assertions for:

1. C-layout sizes and explicit signed root/tip direction with different samples.
2. Zero bit identity without evidence, preserving NaN payload and negative zero.
3. CURRENT-stage linear luminance preservation rather than source-luminance reset.
4. Exact protected-reference and uncovered-pixel identity when host excludes them.
5. Exact deep-black/white protection by the reliability gate.
6. Wrong-sign reference rejection without output mutation.
7. Empty, dark and low-support reference refusal.
8. Root/tip overlap rejected as ambiguous.
9. Incompatible bimodal reference refusal rather than silent mean color.
10. Late invalid input rejected without partial output.
11. In-place alias refusal even for neutral operation.
12. Cancellation and work-budget refusal without publication.
13. Row-tile versus whole-tile bit identity with one full-source reference.
14. Common-vector gamut contraction preserving Y without per-channel clipping.

Every item above is UNRUN. Rust syntax, linkage, ABI layout on supported targets,
ctypes agreement, assertions and bounds require an authorized execution window.

## Required additional acceptance before enabling broadly

- Randomized strict nonfinite/range/shape/overflow/alias cases for both ABI calls,
  including aliases against masks, references and limits; output sentinels intact.
- Cancellation mid-measurement and just before commit; no partial mask/reference
  publication and host sequence discard when cancellation races final commit.
- Explicit hard/soft memory limits at tile/source boundaries, allocator failure,
  source max dimensions, tiny budgets and multirow chunk planning.
- Quantified output luminance error after f32 encode/decode, [0,1] gamut containment,
  amount monotonicity, same-reference color identity tolerance, deterministic tile
  order and reference statistics across supported target architectures.
- Effective sample boundary and quantized-MAD behavior: a narrow coherent minority
  must not override a broad majority; varying soft mask weights and clipped channel
  contamination; wrong-color manual samples should be understandable as user error.
- Real multi-person hair, wigs, reflected light, dyed root/tip boundaries, blue/green
  dyes, gray/white hair, near-black hair, thin hairs, transparent edges, scalp and
  mixed white balance. Check protected samples and background pixel equality.
- Confirm that luminosity-only mismatch remains unchanged and does not falsely
  advertise full tonal matching; intentional gradients must be easy to preserve.
- Host source-ID, mask-version, person-ID, reference-sign, raster-transform and
  working-color-space freshness; manual evidence serialization and undo/redo.
- Provider startup with native library absent: neutral remains a strict no-op;
  active requests report a truthful blocked state without palette fallback.
- Current-stage ordering with existing hair_colour, later local effects and export:
  no stale source RGB overwrite, no applying cached additive delta, no clip repair.
- Build packaging for supported OS/architectures, C-header/ctypes native layout,
  panic-unwind behavior, performance and memory profiling on full-resolution work.

## Hold points

The official requirement establishes only negative=tip reference and positive=root
reference. Target extent and this numerical method are original, conservative v1
choices. Source inspection cannot establish vendor quality parity or AI equivalence.
Do not mark visual or numerical acceptance complete until results are recorded.
