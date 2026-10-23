# M14 returned-source repair and clone

Status: source implementation only. Baseline
`4827f758110aa7afc5c8723d9a4e20eb97a44379`. Fixtures are authored but UNRUN;
no product imports, execution, inference, build, typecheck or visual acceptance.

## Exact scope and guidance

Supplied handbook manual-text lines 630–633 distinguishes spot healing, patch
repair and clone stamp. Patch selects target/sample regions; clone selects a
sample then paints. Cross-layer sampling and exact parameters are not disclosed.
Mapping: `LNX-REF-PC-32482-C-99d39b0e3f` (patch),
`LNX-REF-PC-32482-C-ec6361e1f3` (clone). The adjacent spot-healing requirement
`LNX-REF-PC-32482-C-7fd32754e9` remains outside this derived-source slice.
M14 return/history remain `LNX-REF-WF-127932-a9c143a25d` and
`LNX-REF-WF-127932-c7783ea5fb`. No identifier is a completion/quality claim.

This adapts the existing normalized-vector source-patch and clone operators,
not a new AI inpainting algorithm. Sampling is the current immutable source plus
preceding ordered repair operations, before later effects. It does not silently
sample the physical original, final display, or all creative layers independently.

## Source and history contract

`RepairOp` gains a trailing optional `source_binding`, preserving old positional
construction. Legacy unbound records are original-only. Derived records require
exact content SHA256/full extent and source_patch or clone_stamp kind. Both
active and redo stacks are checked, including inactive project/history versions.
Project v23, asset encoding, package/recovery and original legacy records keep
existing owners. No rendered repaired bitmap or new history owner is persisted.

`creative_derived_repairs` hashes ordered active and redo records, canonical
parameters, source, identities, coverage shape and every coverage byte. History
signatures use that exact digest rather than truncated array stringification.
Source changes restore whole source-owned frames; original and derived repair
banks cannot be unioned. Fresh creative return still creates a clean photo state,
while update-original undo retains the old state and physical source.

## Capture, replay and consumers

- Server pipeline installation calls `creative_derived_repair_runtime.bind`
  only on a fresh pipeline. It verifies the actual derived proxy pixels and
  source before any ordered replay, including the empty-stack case.
- vram validates source-owned records and computes completed source/input/stack/
  output evidence before its existing atomic commit. Failure leaves previous
  recipes and pixels intact. Loading another source clears ephemeral proof.
- `source_patch_capture` retains effective identity, ordered stack digest and
  actual repaired float digest alongside existing document/projection/presented
  proof. Repair and local-mask captures remain separate domains. Matching,
  preparation and commit recheck the proof, never relabel stale pixels.
- `source_patch_controller` preserves internal source/stack proof through its
  pre-fence copy and attaches the exact source to the new record. Existing
  one-shot receipts, cancellation, no-change behavior, rollback and single
  document-history transaction are unchanged.
- `creative_derived_repair_commands` narrowly admits native patch/clone envelopes
  and repair captures before the separate mask guard. Generic heal, light,
  batch, unsupported recovery and unrelated tools remain fenced.
- People preview checks actual replay proof before cache reuse, then passes
  verified repaired pixels to its existing consumers. Immutable-source analysis
  and support ownership do not change or masquerade as analysis of the physical
  original. These operations do not create a new AI analysis identity per stroke.

## Full resolution and precision

Export snapshots validate source-owned stacks. Recipe reconstruction explicitly
preserves each binding while existing normalized vectors rerasterize at final
resolution. The exporter stamps actual canonical float input and ordered exported
operations immediately after resolving the derived asset. `apply_repair_full`
accepts float32 only with that exact internal proof and its owned operation list,
using divisor 1. Original uint8/uint16 still use 255/65535 respectively.

Successful full-resolution replay creates ephemeral output evidence. The people
export adapter verifies it before accepting repaired pixels; direct unproved
float input or foreign-source recipes refuse. Existing fresh-current creative
creation and full-resolution inspection share this canonical export path.
No quantized preview bitmap is used as the export repair definition.

This is opaque SDR only. Source patch already clamps reconstructed SDR tone;
this slice does not claim HDR preservation. Alpha/HDR photo return remains an
explicit refusal, not flattening/clipping. Creative layer precision is unchanged.

## Integration map

Durable: repair_record -> creative_derived_repairs -> project/state validation.
Installation: server._attach_pipeline -> runtime.bind -> vram atomic replay.
Review: creative_document_host -> repair command owner -> source_patch_capture.
Mutation: source_patch_controller prepare/apply -> RepairOp -> existing history.
History: history_policy digest + existing whole-frame restore/server validation.
Export: export_snapshot -> export_recipe -> export.py canonical stamp/replay ->
creative_derived_repair_export -> people_export / people_engine_runtime /
people_render_runtime. Preview cache validation also runs in people_host.

## Residuals and acceptance work

Generic inpaint still consumes proxy-coordinate RLE without this presented
capture contract. It needs its own normalized coordinate/source review and
full-resolution replay design, not simple admission. Global recovery remains
blocked because smoothing, fabric and background consumers are unadapted.
Shared transfer/planners still need actual target-owned identity/analysis review.
No source-mask copying is permitted. Other M14 gaps and the 32 AI tools remain
open; this is not full handbook completion.

UNRUN fixtures cover foreign active/redo records, source switching, persistence,
ordered digest mutation, exact receipts, reviewed proof ownership, atomic replay,
stale pixels, float divisor1 export, unchanged integer scaling and dispatcher
separation. Static AST, source/whitespace review and exact hashes are the only
completed checks. Real local acceptance must cover visual quality, sequential
sample behavior, repair + portrait/body effects, 100% inspection, full export,
undo/redo, save/reopen/package/recovery and memory budgets on ordinary images.

## Primary practice and licensing

[GIMP Clone documentation](https://docs.gimp.org/3.0/en/gimp-tool-clone.html)
distinguishes choosing a sample source, alignment and merged sampling.
[GIMP Heal documentation](https://docs.gimp.org/3.0/en/gimp-tool-heal.html)
distinguishes source copying from destination-aware healing. These support
keeping explicit sampling and operator semantics; they do not establish
algorithm equivalence or our quality acceptance. No GIMP implementation or other
upstream code/model was copied or downloaded. Existing algorithm licences and
notices remain in force; this slice changes ownership/transport, not licensing.
