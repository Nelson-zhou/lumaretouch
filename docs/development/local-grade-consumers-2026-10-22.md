# Independent local-grade consumers: implementation and outstanding validation

This change is a static implementation review, not a completed runtime acceptance.
No tests, Python imports, application execution, builds, typechecks, model
downloads, model installation, or inference were run for this change.

## Retained document and project data

- Document state uses `_local_grade_layers = {version: 1, layers: [...]}`.
  Every ordered group retains its own ID, name, enabled flag, four grade values,
  and complete `LocalMaskState`. Operands are not flattened across groups.
- `lrt.project.v5` is the writer format. v1–v4 migrate explicitly to empty new
  groups while preserving scalar grade, local masks, white balance, and existing
  repair migration rules. New groups are not retroactively inferred from an old
  scalar grade.
- Nested histories, redo data and inactive document versions are traversed by
  the existing project validation walk. An explicit malformed/null new-group
  record fails, rather than being added to a best-effort dropped-data list.
- A file labeled v1–v4 but containing `_local_grade_layers` fails validation.
  Existing v4-only readers reject the new top-level v5 schema instead of silently
  discarding new effects.

## Actual pixel order and coordinate space

The existing order remains:

`repair/smoothing/light → fabric → deformation → enhancement → exposure/WB →
levels → curves → HSL → LUT → legacy grade → independent groups → background →
crop/rotation`.

The new groups execute in retained order with the existing `grade_t` and
`mix_masked` operators. Later groups see the result of preceding grades. RGB
remains in the existing float buffer; there is no new RGB8 quantization step.
Empty groups return the input tensor unchanged and do not reorder old effects.

Selections and range predicates are evaluated against immutable source-domain
working-sRGB pixels. Their source masks are aligned at grade time with
`PreviewPipeline.align_source_grade_mask`, which reuses the same real displacement
grid, border handling, unchanged-pixel handling and high-precision RGB16 warp as
the image. This does not put grade before deformation.

Export first computes every enabled group's full-source mask through the existing
bounded Rust LMR2 bridge, then slices all masks using the same expanded source
tile bounds as the image and displacement. Each tile applies the same alignment
as preview. The legacy `objects` export mask now uses this source-domain entry
point too; it is no longer incorrectly installed as a legacy display brush mask.

## Failure, source identity and memory

- Runtime field validation requires one mask for every enabled group, in exact
  retained order, with matching ID/grade and exact `(H,W) uint8` shape. Missing,
  reordered, mismatched or stale fields never mean a full-image mask.
- A suspended preview stage applies none of its retained runtime fields. The
  retained document intent remains available for diagnosis/recovery. Export
  raises on a missing enabled-group field instead of producing a partial result.
- Snapshot/export helpers verify source SHA-256 and original dimensions.
  Decode-to-render file identity stamps are checked before raster preparation,
  after preparation, and before returning rendered export pixels. The inspection
  worker verifies identity and original dimensions before and after its full
  decode, then uses the same export consumer before cropping its ROI.
- The existing schema budgets remain eight groups, 128 total operands and
  128,000,000 enabled full-mask pixels. Per-recipe Rust raster size/work/transport
  bounds continue to apply. This is not an OOM guarantee.
- Stage-resident coverage is uint8, bounded to 128,000,000 payload bytes. An atomic
  replacement can briefly hold old and new stage masks, up to 256,000,000 bytes.
  Export additionally retains full masks on the CPU, at most 128,000,000 bytes,
  and only uploads the current expanded tile to the stage.
- One group's float coverage and warp temporaries are created at a time, not
  retained for every group. RGB/HSV operator temporaries, existing image/warp
  buffers, semantic inference and its probability buffers, decoder memory,
  Torch allocator caches and Python/container overhead are additional costs.
  No total-process peak memory figure has been measured or asserted.
- `grade_resident_bytes()` includes every new stage-resident tensor. Export
  reports full-mask CPU payload bytes, enabled group count and a separate
  `local_grade` timing segment. These counters do not claim to measure total RSS
  or allocator-reserved GPU memory.

## Connected server integration

The command/session owner captures, restores and replays `_local_grade_layers`
as document/history state, invokes `local_grade_runtime.sync`, and surfaces the
stage's suspended reason. Both live and stored-document export snapshots carry
`local_grade_groups`.

Before full decode, the server captures `local_mask_state.file_stamp(path)` whenever
legacy objects or `local_grade_source.has_groups(snap)` are present. It invokes
`verify_snapshot(snap, path)` at snapshot preparation and
`check_export_decode(snap, path, before, (height, width))` after full decode. The
latter adds runtime-only `local_mask_source_path` and `local_grade_source_stamp`
to the snapshot; these are not document fields. Cross-photo reuse of retained
groups is rejected by `build_export_spec` unless an explicit transfer has already
produced a target-bound document recipe.

## Authored but unexecuted regression coverage

`engine/tests/test_local_grade_consumers.py` covers v5 round trips and ownership,
all four explicit migrations, rejection of false legacy schema tags, malformed
live/inactive/history records, source hash/dimension/decode-race guards, complete
ordered field validation, independent float sequencing, real deformation-grid
alignment, tiled RGB8/RGB16 export, shared inspection pixels, and missing-field
rejection. Consumer tests stub mask production to isolate the renderer contract;
they are not semantic inference or Rust raster acceptance evidence.

`engine/tests/test_local_grade_transfer.py` additionally specifies whole-group
selection, unsafe brush rejection, geometric consent, mixed subtract operand
protection, append preservation, selective replacement, scoped undo, frozen
preset token consumption and RGB16 passthrough blocking. It is also unexecuted.

Still required on an authorized execution machine: run these regressions plus
existing project/repair/grade/deformation/export/inspection suites; exercise the
real Rust bridge and installed semantic models; inspect interactive history,
proxy switching and project reopening; compare multiple tile sizes and RGB16
source gradients; measure CPU/GPU peaks and frame responsiveness. No visual,
numeric, throughput or memory acceptance is claimed before those results exist.
