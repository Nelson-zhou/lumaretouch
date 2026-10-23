# M14 returned-source local masks

Status: source implementation only; all authored fixtures UNRUN. No application,
model inference, native build, typecheck or visual acceptance was executed.
Baseline: `6280028cc371fa7b6d45710e4260a1a5f8da266b`.

## Requirement boundary

The supplied handbook's local-colour section (manual-text lines 612–616) calls
for semantic, selection, brush, gradient, colour/luminance range and combined
masks, visibility/edit/delete, undo and separately specified transfer semantics.
Exact supplied mapping entries: `LNX-COLOR-004`,
`LNX-REF-PC-47246-C-a7f1077928` (local colour),
`LNX-REF-PC-32454-C-a9c276d86e` (mask list),
`LNX-REF-PC-32454-C-87f3048354` (visibility),
`LNX-REF-PC-32454-C-8f39290e88` (edit),
`LNX-REF-PC-32454-C-965ab69fff` (delete),
`LNX-REF-PC-32454-C-9a62fb04b5` (full-image mask),
`LNX-REF-PC-32454-C-f9aeb20bec` (combination/add/subtract).
M14 return and history remain `LNX-REF-WF-127932-a9c143a25d` and
`LNX-REF-WF-127932-c7783ea5fb`. These identifiers are traceability, not completion
claims. Existing six-category analysis is not generic pet/subject segmentation;
this slice does not add all handbook semantic categories or batch matching.

## Implemented source chain

- `creative_derived_mask_commands` admits only native exact mask, capture,
  prompted and live-grade envelopes, or exact composed-mask grade scope.
  Global grade keeps its existing owner. Face-only recovery keeps its narrower
  validator. Repair capture and repair consumers remain refused.
- `source_patch_capture` retains internal effective identity alongside existing
  presentation, document, projection, source extent and eligible review proof.
  Identity is not fabricated from the original file digest. Retained capture
  refuses after source changes, including changing back to the physical source.
- `creative_derived_masks` validates every retained recipe source, including
  disabled groups and inactive legacy masks. Only active semantic dependencies
  require a measured analysis bank. Selected disabled diagnostics intentionally
  require their own current analysis before showing a result.
- Semantic snapshots own readonly float32 fields, exact model/analysis identity,
  field hashes and original-file provenance. Original-path semantic inference is
  never a fallback for a returned composite. Preview verifies actual pipeline
  pixels against the derived analysis proxy. Cached coverage requires unchanged
  actual pixels, recipe, analysis/model, provenance and prompted dependencies.
- Primitive/range/composed and independent local-grade groups reuse their
  existing Rust raster/compositing consumers. Local-mask editing, group changes,
  live grade, receipts, history and cancellation keep existing owners. UI labels
  now call this the current immutable source rather than the original photo.
- `creative_derived_prompted` uses the same bounded immutable RGB8 packet as the
  body path: explicit half-up conversion and LANCZOS maximum extent 2048 from the
  canonical float32 SDR source, at most 12 MiB. Preview uses retained owned bytes;
  full export derives the same input from full-resolution canonical floats.
  The killable worker reads a private bounded regular file and validates hashes.
  Candidate input/source/model and presentation fences remain mandatory.
- Export snapshots freeze derived context from the actual target state, not the
  active row's analysis. The canonical exporter stamps an ephemeral rowwise
  full-float digest immediately after resolving the real derived asset. Local
  mask/group consumers verify that stamp, rerasterize normalized recipes at full
  resolution and force prompted regeneration from those actual pixels.
  Physical original paths remain provenance only. No raw image/analysis bank is
  embedded per project history snapshot. Existing creative assets, package,
  autosave/recovery and source-switch full snapshots retain their owners.
- Fresh creative documents from supported current edits use this same canonical
  export path. This is source output, not generative M13 output.

## Integration map

Admission: creative_document_host -> creative_derived_mask_commands.
Capture: source_patch_capture -> effective source and actual proxy checks.
Mutations: local_mask_controller -> derived binding; local_grade_edit -> existing
single mutation/history owner; live lease -> source and measured dependencies.
Preview: local_mask_state / local_grade_runtime -> creative_derived_masks.
Prompted: prompted_mask_controller -> immutable packet -> prompted_mask_job /
worker -> exact presented candidate -> prompted_mask_resolver source-owned cache.
Export: export_snapshot -> creative_mask_context -> export_recipe / ExportSpec ->
export_source actual floats -> stamp_pixels -> local mask/group preparation.
Source verification: server export guard, local_mask_state, local_grade_source.
Return/fresh-current admission: creative_document_base validates frozen context.

## Explicit remaining work

Shared transfer, presets and cross-image planners remain fenced until every
actual target owns its own source, analysis and identity review; source masks
must never simply be copied. Skin/brush legacy grade scope and local colour
editor scope remain fenced. Arbitrary semantic categories, model availability,
quality and preview/export parity need real local acceptance.

Next coherent repair slice is source-patch plus clone, not generic inpaint:
1. Bind presented repair capture to effective source AND ordered repair-stack
   identity. Preserve it through source_patch_controller proof filtering.
2. Add durable source ownership for active and redo RepairOp stacks through
   repair_record, project validation, state/history, recovery/package and export.
   Never merge original and derived stacks across return/undo; legacy unbound
   records can remain original-only.
3. Add verified float32/divisor1 full export alongside unchanged RGB8/RGB16.
   Reuse normalized vector rerasterization and ordered atomic vram replay.
4. Replace repaired-input refusal in people preview/export only with genuine
   source/replay proof, then admit only the validated repair family.
5. Keep legacy proxy-RLE inpaint separate until coordinate/source review exists.
   Source patch clips reconstructed SDR tone by design; do not claim HDR.

Global recovery's smoothing/fabric/background consumers still need adaptation.
Existing supported face-only recovery is unchanged. Photo return still refuses
alpha and HDR rather than flattening or clipping; creative layer storage and
compositor precision are not downgraded. M14 and the 32 AI tools are NOT complete.

## Verification and primary practice

Authored UNRUN fixtures cover exact admission/replay, wrong/disabled sources,
semantic mutation, actual pixels, provenance, cached coverage, immutable prompted
input, worker result identity and dispatcher separation. Only static AST/JSON,
source diff, whitespace and file hashes were checked. No acceptance implied.

[MediaPipe Image Segmenter](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter/python)
requires actual image input and a compatible category model; category coverage
must not be invented from labels. The
[pinned SAM2 predictor](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/sam2/sam2_image_predictor.py)
uses RGB image input. Our bounded SDR conversion is application policy, not an
upstream HDR guarantee. Existing pinned dependencies and licence notices remain;
no upstream implementation or model was copied/downloaded in this slice.

## Subsequent source adaptation

[Derived repair and clone](DERIVED-REPAIRS.md) records the next source-only slice.
The repair residual above is historical; generic inpaint/global recovery remain open.
