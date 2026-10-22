# PC-32464 facial wrinkles: implementation and integration contract

Status: isolated implementation and shared UI/protocol/preview/export/recovery hooks written.
Preset/batch registration is in the coordinated optics transaction snapshot. No local
product execution, build, typecheck, inference, model download or test execution
was performed. Static inspection is not full-resolution visual acceptance.

## Baseline and official verification

Verified official https://www.pixcakeai.com/guide/32464 on 2026-10-22. The page
is dated 2026-09-17. The authoritative subgroup is eight controls, not one eye
slider; independent anatomical left/right nasolabial adjustment is explicit.
The supplied Linux manual lines 501–505 and supplied acceptance mapping agree.
Numeric ranges, masks and algorithms below are original implementation choices,
not claims that the proprietary implementation or numeric scales were copied.

| Control | Official mapping | Stored strength |
|---|---|---|
| Family | PC-32464-C-d9e8e03577 | no global fake slider |
| Forehead | PC-32464-C-294d9a2188 | wrinkle_forehead |
| Glabellar | PC-32464-C-3e1a0bb386 | wrinkle_glabellar |
| Eye surroundings | PC-32464-C-24f710ab2b | wrinkle_eye_area |
| Nose bridge | PC-32464-C-fcd0c13b5f | wrinkle_nose |
| Nasolabial | PC-32464-C-942d0bfb79 | wrinkle_nasolabial_left/right |
| Cheek | PC-32464-C-f28262041d | wrinkle_cheek |
| Marionette | PC-32464-C-5aa8868572 | wrinkle_marionette |
| Mouth surroundings | PC-32464-C-22b2d6e2a0 | wrinkle_mouth_surround |

## Source, ownership and composition

Analysis is frozen repaired working-sRGB source, matching existing under-eye
analysis. The actual selected MediaPipe 478-point face and actual six-class
semantic skin edit-weight are required. A person matte, template face, fabricated
landmarks, another face's index or missing skin mask never substitutes for them.

The cache owns source/landmarks/skin copies; load_face replaces ownership and
repair_version refreshes the frozen source. Parameter keys include all nine
pixel strengths. Link metadata is excluded. The analysis never consumes studio,
fabric, smoothing or previously wrinkle-corrected pixels, so those recipes are
not fictitious cache dependencies. Their real RGB remains at the consumer and
receives only the isolated bounded correction, never an original-image paste.

Each region has anatomical geometry, semantic support, inward boundary clearance,
and hard eye/lash, brow, nostril and lip/mouth exclusions. Hair receives semantic
exclusion and the upstream dark-line rejection. These rules are not a perfect
occlusion classifier; confident semantic errors and pose failures remain possible.
Per-region and per-side support/rejection reasons are returned honestly. Bilateral
controls may process only the supported side and report partial support.

Pinned line detection produces source-derived proposal fields. A Rust maximum
combines amount × region support × proposal, capped at 12 Lab L units. This is
not an additive stack. Identical overlapping proposals cannot increase the lift.
One relight runs from the frozen Lab source; unchanged support remains exact zero.
Fine texture is retained through upstream line-vs-pore detection, and broad folds
retain 60% depth at full strength. There is no geometry warp or whole-face blur.

The RGB delta runs after studio/fabric and BEFORE automatic deformation. The
existing enhance consumer currently follows deformation and must not be reused
for source-coordinate wrinkle pixels. Later deformation moves the corrected skin
and recovery together. This does not fix or claim to fix old eye-enhance ordering.

## Shared hooks (in order)

1. `ops/enhance.py`: append `facial_wrinkle_state.INTENT_KEYS` to AMOUNT_KEYS.
   Call S.check on original inputs before numeric coercion; wrap invalid values
   as EnhanceError. Keep ENH.SUBS restricted to sclera/iris/teeth.
2. `server.py`: ENHANCE_KEYS derives the new whitelist automatically. Replace
   enhance any(amounts.values()) checks by S.active_enhance in `_enhance_intent`,
   `_restore_enhance`, `_apply_state`, `cmd_enhance` (both gates), effects summary,
   `_recipe_needs_landmarks`, batch-export targeted gating. Restore validates
   new fields before legacy permissive coercion; an invalid saved unlock value
   must fail, not silently become zero. Neutral unlock-only edits persist the
   flag in engine + pipe while keeping all pixel layers absent.
3. `vram.py`: initialize/clear face via runtime.clear_face; `load_face` calls
   runtime.install_face(self, precompute). `build_enhance` calls build_preview
   after the face is attached. `clear_enhance_field` calls clear_layer, not
   clear_face. `set_enhance` refreshes the repaired source and solve_preview.
   The export-tile path must attach a precomputed field BEFORE parameter setting
   or explicitly skip local solve for tiles; a tile has no local full-face solver.
   `has_enhance` also sees the wrinkle delta; resident bytes include runtime
   resident_bytes. At retouch, refresh_source then apply the family delta before
   automatic deform, wrapped by effect_recovery.apply('facial_wrinkles', I, O).
   No recovery wrapper around all enhance or the entire original photograph.
4. Payloads: publish full per-region facts, including partial side support and
   changed_px, in doc_state.enhance.facts and enhance_done. Keep link state in
   amounts, but omit from gated/active/sub-effect summaries. Existing reason and
   gated_px maps remain backward compatible.
5. `ExportSpec`: transient facial_wrinkle_skin/backend fields. Validate finite
   mask shape and budget; do not persist them. `export_recipe` uses
   active_enhance (unlock alone does not require landmarks), sets full amounts,
   then calls runtime.configure_export after spec.landmarks is assigned.
   Export prepares repaired source first, then runtime.prepare_export once for
   the entire selected face. Each tile receives attach_delta using its actual
   expanded origin. No proxy RGB, tile-local detection, measured-field resize
   or uint8 intermediate. Export stats include layer.facts and resident bytes.
6. `scope.py`: register facial_wrinkle_scope.OP with params=('recipe',),
   state_fields=FIELDS, single_face=True, transferable=True, cmd='enhance',
   read=params_of/write=install; dispatch check_params. Target must have its own
   real landmarks/skin. Preserve non-wrinkle enhance controls. Do not transfer
   recovery, face/source ownership, masks or cached correction. Add module label
   to preset UI and explicit standalone batch option with single-face warning.
7. `native.ts` / Tauri enhance: use model.transportPatch(opts) as optional
   `wrinkles` envelope; Tauri enhance adds `wrinkles: Option<Value>` and calls
   facial_wrinkle_api::append(&mut cmd, wrinkles)? to strictly flatten the nine
   strengths and unlock metadata. Declare mod facial_wrinkle_api in main.rs. UI renders FacialWrinkleControl for each official
   leaf, passing doc.enhance.facts and existing enhance commit. Family row is an
   explanatory heading, not another strength. Restored amounts/undo retain
   independent values. Link activation changes only metadata; unequal sides
   remain mixed until a deliberate linked slider move sets both.
8. `packaging/stage-engine.sh`: call build-facial-wrinkles.sh with staged
   bin/liblrt_facial_wrinkles.so, copy core source with distributed source package.
   No install/download/runtime compilation fallback. Add attribution below to
   NOTICE; existing AGPL text must accompany the redistributed adapted sources.

## Recovery ownership extension (facial_wrinkles and lip_makeup)

Add target `facial_wrinkles`, label 面部祛纹, stage `pre-deform-facial-wrinkles`.
A row for this target requires `owner` checked by facial_wrinkle_recovery;
other targets retain their exact old fields. This is a backward-compatible
extension: old records without this target remain valid. A facial row missing
owner is rejected, never migrated by guessing the current face/index.

At first stroke bind owner from current source SHA + actual normalized 478×3
landmark SHA + backend. Subsequent strokes/enable verify it. Clear/delete must
remain possible when ownership is stale. prepare_stage verifies enabled facial
rows, and stage_key includes current actual landmark identity so switching or
reanalyzing faces cannot reuse another face's cached recovery. Mismatch suspends
this target's correction, not other operators. Whole-photo skin/fabric/background
recovery stays independent. Export verifies against the snapshot's actual
selected landmarks/source before full-size rasterization. Existing no-transfer
recovery rule remains. The original source locator authorizes brush coordinates;
existing producer-rendered review + presented receipt still authorizes commit.

## Limits and pending acceptance

- Canonical field cap: 32 MP face ROI, explicit rejection, never silent resizing.
  Admit the full source/semantic/ROI working budget before allocation. Estimate
  currently exposed by runtime.working_bytes; add to existing render budget.
- Local tests were written but NOT run: state/owner contracts, synthetic line
  source isolation, exact neutral, native max/atomic validation, tile consistency,
  link persistence. These tests do not certify real-portrait quality.
- Qoder must build the Rust kernel, execute targeted runtime/UI tests, then
  examine all eight regions on authorized real portraits at 100% and full-size
  8/16-bit output: front/tilt/profile, eyes closed/glasses/hair/hand occlusion,
  deep and light skin, expression folds, tiny faces, image edges, multiple faces,
  repaired source edits, undo/project reload, mixed linked sides, batch target
  analysis/refusal, recovery face switch/reanalysis, and tiled seams.
- Full-resolution quality, performance, CPU/GPU agreement, polish and proprietary
  parity are not verified. Do not mark manual acceptance completed from a proxy.

## Attribution to merge into NOTICE

Facial wrinkle line measurement reuses the already adapted RapidRetouch
`eyes.py` helpers `_line_strength`, `_wrinkle_lift`, `_relight`, `_inner_feather`,
plus `filters.py` and `colour.py`, copyright Chris Cork, AGPL-3.0-only, pinned
commit `5e9d9c1d2770ff29d11a3879e5a90aad5887e028`:
https://github.com/crispin81/RapidRetouch/tree/5e9d9c1d2770ff29d11a3879e5a90aad5887e028

Upstream contains eye-specific wrinkle treatment, NOT this complete eight-region
family. LumaRetouch adds anatomical region geometry, semantic gates, selected-face
ownership, max-overlap composition, UI and persistence/export/recovery wiring.
Python derivative modules retain AGPL-3.0-only identification; original Rust
composition is GPL-3.0-or-later. Combined distribution remains subject to the
applicable AGPL obligations, including corresponding source and license notices.

## Integrated delivery status (2026-10-22)

The following hooks are now written, not merely proposed: enhance validation and
processing-key distinction, all eight RetouchPanel controls, sparse Rust command
transport, document/history replay, frozen repaired-source preview lifecycle,
pre-auto-deform family delta and operator recovery, full-face original-resolution
export solution with tile slicing, 8/16-bit float processing, memory admission,
and native helper packaging/source attribution. Zero strength and unlock-only
metadata do not constitute processing intent. Old enhance face-box ownership is
retained when its field is dropped, rather than erased and accidentally rebound.

Recovery rows for facial_wrinkles and lip_makeup require the optional owner
record; existing whole-photo targets retain their old row shape. Source SHA256,
actual little-endian float32 478×3 landmark SHA256 and MediaPipe backend are
strictly checked. Stale identity suspends only that target in preview and rejects
full export. Clear/delete/disable remain available. No migration guesses an owner
from a detected-face index. Lip's pixel stage is supplied by its separate package.

The existing source-bound project encoder stores the extended enhance amount
record and recovery owner without cached rasters; no project schema downgrade or
extra standalone project format was introduced. Existing history receipts remain
the transaction boundary. Presets transfer only regional numeric intent and exact
link metadata, preserving every unrelated enhance amount and target-owned data.

Cross-package dependency: server's read-only prepare_optics callback is supplied
by optics_transfer_engine and its matching PresetPorts/BatchEditor definitions.
Wrinkle scope/labels/batch option are registered in the optics-owned transaction
files. Root must snapshot these before publishing a combined tree.

Static syntax/whitespace inspection only. New focused contract fixtures are
unexecuted. Qoder still needs native compilation, runtime/round-trip/undo checks,
8/16-bit and tile-boundary checks, real selected-face/occlusion cases, and visual
review across all eight regions. No proxy or synthetic fixture is full-resolution
photo-quality acceptance; no parity with PixCake's proprietary algorithm is claimed.
