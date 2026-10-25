# Full-resolution lens renderer: implementation design, not acceptance

Status: DESIGN AUTHORED / IMPLEMENTATION NOT STARTED / ALL ACCEPTANCE UNRUN.
Date: 2026-10-25. Ownership in this lane is only this new documentation directory.
No existing core, host, UI, dependency, build, test, or packaging file was changed.
No product imports, execution, tests, build, typecheck, inference, downloads, or Git
writes were performed. Reading source and primary public documentation is the
evidence for the findings below, not evidence of working image output.

## Decision

Full-resolution working-set and throughput are core lens functionality, not a
polish task. Implement two changes together, with separate owners:

1. A truly bounded source/field/output storage contract. A tiled loop around the
   existing whole-image byte/array pipeline is not this contract.
2. An aperture-preserving accelerator: exact-value cohorts, bounded overlap-save
   FFT convolution, and explicit residual/visibility evaluation. Keep a direct
   receiver-gather reference. Never replace a requested aperture with a Gaussian,
   quantize radii/depth into hidden bins, remove paint/protection, or reduce the
   final image resolution to fit admission.

The first useful 24MP target is an already canonical full-resolution source with
an explicitly acknowledged constant manual depth plane, all five apertures,
constant radius or a small number of exact radius cohorts, and bounded painted
residuals. This is a target, not an established runtime capability. Arbitrary
dense varying depth and feathered radius fields remain a separate major
performance gate. Their exact fallback can be bounded in memory without being
fast enough for a 24MP image.

Start parallel implementation from [FIRST-MODULE.md](FIRST-MODULE.md).
See also [RENDERER-CONTRACT.md](RENDERER-CONTRACT.md),
[STORAGE-AND-INTEGRATION.md](STORAGE-AND-INTEGRATION.md), and
[RESEARCH-AND-ACCEPTANCE.md](RESEARCH-AND-ACCEPTANCE.md).

## Why the current 24MP path fails

These are source-inspection deductions, not measured performance results.
For 6000 × 4000 pixels, N = 24,000,000:

- `lens_blur_stage.prepare` reserves 128N additional bytes: 3,072,000,000 bytes,
  before its retained source, depth, display reserve and other allowances. The
  host working ceiling is 2,000,000,000 bytes. Even a neutral requested render
  goes through that admission.
- `creative_document_base.capture_current_asset` admits non-neutral edited
  capture at 96 × max(input_pixels, output_pixels), plus original-file bytes.
  96N is already 2,304,000,000 bytes. RAW capture also uses a 96-byte-per-pixel
  limit. Fixing the aperture core does not fix this earlier blocker.
- Even neutral JPEG/PNG/TIFF capture without an existing creative baseline
  calls `creative_document_import.import_bytes`, whose header/decode preflight
  also uses 96N + 2×original_bytes. Therefore 'neutral photo' alone does not
  establish a 24MP starting path. Already-existing canonical input can take the
  direct neutral return; original file import needs its own bounded rewrite.
- The current gather work estimate is N × min(W, 2H+1) × min(H_image, 2H+1),
  where halo H = ceil(max_radius + 0.5) above the delta threshold. For any
  requested max_radius > 0.5, the minimum halo is 2: at least 600,000,000
  candidates at 24MP, above 250,000,000. At radius 128, H = 129 and the bound
  is 1,609,944,000,000 candidates, with up to 25,759,104,000,000 aperture
  transmission evaluations. Smaller output tiles do not reduce that total.
- The current refinement estimate includes N × (2 + 2 × active_strokes).
  One active stroke therefore contributes at least 96,000,000 examined pixels,
  already above 64,000,000 before capsule evaluations.
- Native ABI 1 requires a complete source, complete depth and optional complete
  refinement. Its Python bridge copies those inputs, allocates complete output,
  and the stage creates complete canonical output bytes. The existing immutable
  AssetStore is a whole-byte store; `get` does not copy immutable bytes, but it
  also does not provide an independent file/tile input contract.

Do not raise any of these existing global ceilings to make the old estimator
pass. New algorithms need explicit counters for their actual different work,
plus the unchanged memory, deadline, cancellation and aggregate-session limits.
Do not relabel FFT butterflies as old gather taps to conceal their cost.

## Honest scope and completion order

1. Author/reference-verify bounded source and destination region interfaces,
   exact field sampling and local brush rasterization.
2. Preserve ABI 1 and saved recipe 1. Add a new, explicit numerical-renderer
   identity before any reordered/FFT result can be saved or reviewed.
3. Implement the constant-depth/cohort accelerator for every existing aperture,
   then genuine clear/blur paint with exact residual handling.
4. Integrate candidate storage, full-resolution hash, review and existing
   one-shot new-image commit without converting back to a whole byte string.
5. Migrate full edited-source capture and all downstream canonical consumers.
   Until then, label the supported source subset precisely.
6. Establish 24MP throughput/RSS/cancellation and photographic quality, then
   tackle dense varying-depth performance without declaring this step optional.

There is no prototype in this directory. Any numerical prototype requires a
separate ownership agreement; this design does not authorize edits to the
existing core or shared pipeline.
