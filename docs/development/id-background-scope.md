# PC-32475 reviewed ID-background source delivery

Status: source-integrated, NOT runtime/quality accepted. Tests, compiler, build,
product imports, inference and UI execution were not run during this delivery.

## Evidence and original implementation

- Baseline manual lines 575–579, and AI开发资料包/功能需求验收映射.json PC-32475 were read individually.
- Official behavior checked 2026-10-23: https://www.pixcakeai.com/guide/32475 .
- Blend definitions: https://www.w3.org/TR/compositing-1/#blendingsoftlight . The
  new dependency-free Rust implementation is original GPL-3.0-or-later code,
  evaluating all three modes in explicitly fixed linear sRGB, not promising CSS
  display-space equivalence. No proprietary PixCake code/assets were copied.
- Existing imagecodecs (BSD-3-Clause): https://github.com/cgohlke/imagecodecs .
  Its PNG decoder retains RGB16 and alpha. Existing LittleCMS (MIT):
  https://github.com/mm2/Little-CMS . Existing true RGB16 ICC transforms are reused.
- Recommended backgrounds are original solid colours. User-file bytes only;
  no downloaded stock imagery, pretrained weights or licence-unclear assets.

## Canonical paths

One `_id_background` recipe and immutable `_id_background_bundle` drive direct
transactional changes, undo/redo, per-document retention, project serialization,
presets, batch preflight, preview, full-source inspection and export. Native UI
is mounted in App. Direct Apply does not pretend to have a prior rendered-preview
commit proof. Receipts correlate document, request and runtime recipe revision;
uncertain rollback quarantines the pipeline and locks UI editing.

Assets are at most 10,000,000 bytes, JPG/PNG/TIF/BMP, with original bytes, ICC,
RGB/alpha precision, decoded pixel digests and dimensions bound. PNG16 and
unassociated TIFF alpha are supported in source. Associated/unspecified TIFF
extra channels and unsupported high-bit non-RGB layouts fail explicitly.
Project bundles use immutable chunks at most 7MB, compatible with project limits.
Clearing the selection never deletes a source file. Centered material permits
position and scale; uncovered or transparent pixels use the explicitly selected
solid base in linear light. Stretch fixes position and scale. Six distinct saved
colours maximum, RGB and HEX controls.

Three support categories each retain their own reviewed local-mask snapshot:
subject, subject plus contact-associated objects, and subject plus all objects.
No person/contact relation is inferred. Semantic/full-image operands cannot
stand in for the review. Manual vectors replay at output resolution using the
existing 8-bit coverage raster. Prompted masks retain the existing immutable
source/model contract and regenerate for full-source workflows, but their model
candidate is inherently lower-resolution and resampled: NOT automatic hair
matting or native full-resolution alpha. The old proxy uint8 background path
remains separate and is not used to advertise this capability. Existing custom
BiRefNet structure is NOT an official-compatible BiRefNet checkpoint.

New shadows are original 2D soft/hard/silhouette projections, not physical 3D
lighting or extracted original shadows. Rust applies source-pixel edge morphology,
opacity, finite-support box blur, gradient, xy, distance and angle. Shadow halo
is retained outside the output canvas before blur and cropped only afterward.
Background opacity never reduces the foreground opacity. Full-source fields are
prepared once and cropped for tiles, then aligned with existing source geometry
and composited with CURRENT edited pixels before final manual warp. Neutral is
an exact bypass. Source ≤32MP, shadow halo ≤64MP, native estimate ≤2GiB, and host
memory admission are enforced; cancellation is checked by the native loops.

## Deliberate incomplete items

All three picker modes now use private-capture/proven-presentation float
sampling, never canvas RGB. Original mode captures current source-proxy pixels;
subject/associated mode displays those real pixels and restricts sampling to the
independently reviewed contact-support snapshot. Reference mode uses the actual
sample-library selected reference, checks its active catalog row, exact frozen
source/render/asset identities, and displays an aspect-preserving float proxy of
that verified frame. Any visible reference colour is sampleable, including an
edited background; original-scene authenticity is not confused with visibility.

The native descriptor and every sample bind picker_mode and source_binding in
addition to document/recipe/capture/ticket/generation. Changing the selected
sample, deleting it, corrupting its bundle, changing the source or support review
invalidates sampling. Reference decoding is admitted against the complete asset
before resizing. No current-image or thumbnail fallback can impersonate a
reference. All three modes remain proxy-float colour sampling, not native
full-resolution colour proof. Read-only picker access from comparison views is
separate from the unchanged mutation gates; Apply still requires normal editing.

Original-shadow extraction 442ced0175/ab010073e3 and decontamination
e999ab085a/4bc238dfa1 are excluded and not claimed. Restoring arbitrary regions
is outside these three delivered slices. No test or image-quality acceptance is
inferred from source wiring or authored fixtures.

## Required local acceptance (all UNRUN)

1. Compile Rust/native/UI, package and check real startup capabilities.
2. Pixel-neutral and opaque-foreground invariance; RGB16 low-bit differences;
   ICC PNG/TIFF and alpha/base compositing, EXIF orientations and exact hashes.
3. Original/reference/subject picker identity swaps, reference removal/corruption,
   subject-only support rejection, comparison-view launch, cancelled/repeated
   capture and visible reference background sampling. Six-colour bound, clear without file deletion, exact 10MB boundary, corrupt
   file rejection, center movement/size and stretch disabled controls.
4. Independently review all three categories, hair/props/contact boundaries,
   wrong-source rejection, prompted model mutation suspension and full replay.
5. Every shadow mode/blend and slider, off-canvas blur halo, tile size invariance,
   cancellation, memory rejection and prior body/face geometry alignment.
6. One gesture/one history entry, duplicate receipt idempotence, stale recipe,
   engine restart, failed rollback quarantine, cancel/back/repeated-click cases.
7. Save/reopen with source background file moved/deleted; undo/redo; portable
   preset/batch target-own mask and asset preservation; frozen preflight changes.
8. Full-source inspection/export parity including RGB16; no source edits lost.
9. Sky/studio/legacy mutual exclusion; all previous people/body/colour preview
   gates remain valid. Source-render screenshot and quality review are required.
