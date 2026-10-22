# PC-32471 lip makeup three-control subgroup

Status: source implementation and shared portrait integration written.
Preset/batch registration is coordinated with the optics package. Nothing here
has been executed, compiled, typechecked, tested,
visually validated, or benchmarked. Qoder owns local tests. Do not mark the
family accepted merely because these files exist.

## Requirement and comparison evidence

Supplied Linux manual lines 541–545 describes lip enhancement and the saturation,
brightness and dimensionality controls. The supplied AI package's requirement
mapping has these four exact IDs, each previously research/uncovered:

- Family: PC-32471-C-944899f5fd.
- Saturation: PC-32471-C-3d1502871b.
- Brightness: PC-32471-C-d5fc30a763.
- Dimensionality: PC-32471-C-21e4a8d464.

Official https://www.pixcakeai.com/guide/32471 was read on 2026-10-22. Its lip
section says the three controls can be adjusted independently. Its page date
was 2026-07-09. It does not disclose numeric ranges or algorithm. Our recipe
uses signed [-1,1], UI [-100,100], neutral zero. These are product-defined,
not copied official ranges. The overall page also describes a master lip
strength and separate lipstick assets/textures; this delivery is specifically
the three-control subgroup, NOT the entire makeup page or lipstick system.

Official MediaPipe FACEMESH_LIPS topology was checked directly at
https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/mediapipe/python/solutions/face_mesh_connections.py
on 2026-10-22. Inner and outer contours are distinct. The inner chain follows
its 20 edges; outer chains reuse this repository's existing enhance topology.
MediaPipe topology source: Copyright 2021 The MediaPipe Authors, Apache-2.0;
retain the project's MediaPipe attribution and Apache-2.0 notice when packaging.

Community comparison used the pinned RapidRetouch reference at
https://github.com/crispin81/RapidRetouch/tree/5e9d9c1d2770ff29d11a3879e5a90aad5887e028
and its available engine/tests/test_mouth_fabric.py. That test covers pale-teeth
vs gums and a hue rotation preserving chroma/lightness. It does NOT establish
lip saturation/brightness/dimensionality implementation or visual parity.
The pinned mouth.py was unavailable locally and the official GitHub fetch
returned cache miss; it was NOT reviewed. No code from that file is claimed
reused. RapidRetouch is AGPL-3.0-only; no new RapidRetouch derivative is included
in this subgroup. Existing project attribution for existing AGPL code stays.
The new point math is original Rust; NumPy/OpenCV and existing polygon-distance
math are reused instead of inventing another model or copying skin relighting.

## Measured support and honest limitations

Actual selected 478-point MediaPipe geometry is mandatory. A synthetic face,
face box, opposite teeth mask, inverted background or first detected face is
never a substitute. The mask is outer vermilion minus inner oral cavity with
inward-only distance clearance. Teeth, tongue, opening, exterior skin and
boundary pixels are hard-excluded. Open and closed mouths have separate cavity
handling: a collapsed real inner contour is protected as a line.

Reject tiny lips, strongly asymmetric/foreshortened pose, clipped/crossed or
invalid contours, and inadequate support. Actual hashed six-class semantics
provide only hair/clothes/background vetoes. There is NO lip model class.
Face-skin confidence is deliberately not required for lipstick. A robust
source-colour veto removes outliers and clipped/crushed samples; it is not a
lip classifier and does not assume red lipstick. Skin-coloured hands and other
confident model errors can remain: no claim of complete occlusion detection.
Recovery must be available for this exact operator. Real-photo QA may require
adjusting these conservative thresholds; no untested visual quality claim.

## Computation and ordering

One immutable repaired working-sRGB face ROI owns copied source, landmarks,
known-occluder field and face hash. All controls are solved together, never
feeding a previous correction back into analysis. The key is the recipe tuple;
repair_version or selected-face changes rebuild source analysis.

Rust adjusts Lab chroma for saturation, L for brightness, and only measured
low/mid-frequency L shading for dimensionality. A normalized Gaussian weighted
by eligible lips isolates existing smooth shading from teeth/skin and fine lip
texture. Original L, including high-frequency texture, remains the starting
value. Dimensionality scales this existing smooth shading about its weighted
mean; it does not sharpen, invent a highlight, rotate hue or change geometry.
Source-derived RGB contribution is bounded per channel at 0.18 then support
weighted. It is ADDED to the current upstream pixels, never pasted over them.
Final gamut clipping can limit contrast/texture in extreme colours; quality
must be measured, not asserted. All-zero recipe returns None before analysis,
OpenCV/native loading or colour conversion. Zero delta and outside mask pixels
remain exact original current pixels via torch.where.

Apply before automatic deformation, after earlier source-coordinate effects.
Wrap only its before/after pair in effect_recovery.apply('lip_makeup', ...).
Frozen analysis input remains repaired source, not studio/fabric/wrinkle output.
Recovery has shared source SHA256 + canonical float32 478×3 hash + backend owner;
face index is insufficient. Use the generalized facial_wrinkle_recovery helper
and target-specific suspension. A different detected landmark set is a different
owner until explicitly reconciled, even if visually the same person.

Original RGB8/RGB16 export creates the repaired full-source ROI once, divides
original integers by 255/65535 only, solves once, then attaches cropped delta to
each expanded tile origin. Never resize a measured correction, solve inside a
tile, run from a proxy JPEG, or quantize through RGB8 before RGB16 output.
Known-occluder semantic fields alone may be resized to original size. Budget
admission must combine working_bytes with other stages; reject oversized ROI,
never downsample the actual correction as a hidden fallback.

## Shared integration map and static review checklist

These hooks are written in the current source tree. This is a review map, not
a claim of executed acceptance. Preset/batch registration must be present in
the final combined snapshot; the owning optics package supplies those rows.

1. server.py: imports state/runtime/command; engine field `_lip_makeup` defaults
   to S.neutral(). Include in document capture/apply/defaults/undo/redo/versions,
   reset, snapshots for project/export, and named effect summary. Restore runs
   R.sync (non-strict reports suspended; export remains strict). Expose doc_state
   `lip_makeup: R.report(self)`. Add command `lip_makeup` to EDIT_CMDS/HANDLED;
   handler calls lip_makeup_command.apply(self,p,emit). Existing transaction
   history records the whole recipe, not three sequential actions. Add actual
   protocol capability only after all host/render wiring exists. Ensure the
   request's document_id is preserved; stale photo requests reject.
2. vram.py: initialize lip_makeup recipe and R.clear_face; load_face installs
   actual selected face. Repair refresh calls R.refresh_source before render.
   BEFORE automatic deform apply local delta and recovery for lip_makeup only.
   Requested edits and exports fail explicitly when required support is absent.
   Reopening an unsupported saved recipe preserves its values and visibly
   suspends this target instead of blocking the entire document. Drop/reload includes R.resident_bytes;
   source/face reload clears and rebinds. Export tiles skip source solve and use
   only the precomputed attached field. No enhance_amounts additions are needed.
3. export.py: ExportSpec has lip_makeup (recipe) and transient lip_makeup_face.
   export_recipe sets recipe from snapshot, assigns selected spec.landmarks,
   then R.configure_export(spec,snap,h,w). R.prepare_export runs after repaired
   source is complete, once per full image. Attach its delta before each tile
   render with actual expanded tile origin. Both original RGB8/RGB16 branches
   need this. Record facts in export result and include working/resident budget.
4. project.py: call lip_makeup_project.validate_records on nested project rows,
   versions/history and encode/decode dictionaries. Optional legacy absence is
   neutral, present malformed/null fails. Preserve _lip_makeup in every state
   whitelist; do not serialize runtime face/field caches. If schema is bumped,
   update all accepted prior schemas coherently, not just one latest constant.
5. scope.py: register lip_makeup_scope.OP, params=('recipe',), FIELDS,
   single_face=True, transferable=True, cmd='lip_makeup', read=params_of,
   write=install; use check_params. Preflight target's own true landmarks and
   visibility; never copy recovery or cached support. Standalone preset, batch
   operation selector and recipe-needs-landmarks gate include lip activity.
   Batch must use target-owned precompute and explicit selection rules. Numeric
   presets do not authorize transferring source photo/person recovery masks.
6. recovery: wrinkle worker owns shared extension FACE_TARGETS including
   facial_wrinkles and lip_makeup. Add exact target to state/runtime/UI/host
   whitelists and labels, strict owner verification in sync and export snapshot;
   do not add another owner schema. Binding suspension affects only this target.
7. ui/src-tauri/src/main.rs: add mod lip_makeup_api; tauri lip_makeup command
   calls its strict command(recipe,document_id,control), then state.send_to_engine.
   Register handler. ui/src/native.ts adds typed recipe/facts/status/doc state,
   command invocation and actual doc_state-bearing frame receipts. The auxiliary
   lip_makeup_done event is not relied on as a host result slot. This is an accepted-command
   preview path, not an unimplemented provisional preview/cancel system.
8. RetouchPanel.tsx imports LipMakeupControls; App supplies the existing panel
   and blocks overlapping optics/studio/capture workspaces. Bind engine-acknowledged recipe,
   selected-face eligibility, engine readiness, errors, history refresh and
   Slider. Place in makeup enhancement, show all three controls together. Bind
   family and exact child IDs; connect only these four registry rows. No broad
   makeup-page completion claims. Add recovery target and preset/batch labels.
9. packaging: invoke build-lip-makeup.sh in every shipped build lane and include
   liblrt_lip_makeup.so. Missing library gives explicit failure, never fallback.
   Retain MediaPipe topology copyright/Apache source notice in NOTICE.

## Qoder acceptance work, not executed

- Run authored Rust, Python and TS tests after packaging the core; execute full
  typecheck/build/test lane only locally with authorization. Static checks do
  not prove imports or integration work.
- Real selected-face fixtures: closed/open mouth, visible teeth/tongue, neutral
  and dark/purple lipstick, fine lip lines, multiple persons, sideface, tiny
  lips, hand/hair/straw occlusion. Prove outer/inner exclusions and rejection.
- Positive/negative each control alone plus combined; zero exact identity;
  dimensionality changes low/mid shading while high-frequency texture is
  preserved in eligible interior. Record gamut clipping and edge behavior.
- Upstream repair/fabric/studio/wrinkles + lip change: unrelated prior RGB edits
  preserved. Repair version invalidation, new selected face, detection refresh,
  GPU reload, source change, stale command must never reuse another field.
- Recovery local remove/restore, undo/redo, project/reopen/inactive versions,
  preset and standalone batch; invalid owner fails only this target.
- Original RGB8 and RGB16 whole ROI versus awkward overlapping tiles/halos,
  identical source recipe, no seam. Inspect full-resolution crops, not proxy.
- Reject bad versions, NaN/Infinity/bools/unknown fields, unsupported backend,
  missing native library, memory budget failure and render rollback failures.

## Isolated file manifest (shared files listed below)

core/lip_makeup/lib.rs
packaging/build-lip-makeup.sh
engine/src/lumaretouch_engine/lip_makeup_state.py
engine/src/lumaretouch_engine/lip_makeup_geometry.py
engine/src/lumaretouch_engine/lip_makeup_native.py
engine/src/lumaretouch_engine/lip_makeup_layer.py
engine/src/lumaretouch_engine/lip_makeup_runtime.py
engine/src/lumaretouch_engine/lip_makeup_scope.py
engine/src/lumaretouch_engine/lip_makeup_project.py
engine/src/lumaretouch_engine/lip_makeup_command.py
engine/tests/test_lip_makeup_contract.py
ui/src/lipMakeup/model.ts
ui/src/lipMakeup/model.test.ts
ui/src/lipMakeup/LipMakeupControls.tsx
ui/src-tauri/src/lip_makeup_api.rs
docs/LIP-MAKEUP-INTEGRATION.md

## Transaction details

A slider sends the complete versioned recipe plus its explicitly changed control.
The engine merges only that control with its current recipe before solving all
three together. This prevents rapid switching between controls from overwriting
an earlier accepted adjustment with stale UI values. Reset uses control=all.
Document identity is checked before mutation. On a failed solve/render, restore
both the numeric recipe and solver cache, then redraw the previous frame. History
coalesces consecutive changes to the same control, not three different controls.
The frame carries engine-acknowledged doc_state; native queue acceptance is not
reported as completed processing. All-zero state never requires the Rust core.

## Shared file manifest

NOTICE
packaging/stage-engine.sh
engine/src/lumaretouch_engine/server.py
engine/src/lumaretouch_engine/vram.py
engine/src/lumaretouch_engine/export.py
engine/src/lumaretouch_engine/export_recipe.py
engine/src/lumaretouch_engine/project.py
engine/src/lumaretouch_engine/history_policy.py
ui/src/App.tsx
ui/src/native.ts
ui/src/components/RetouchPanel.tsx
ui/src-tauri/src/main.rs

The pre-existing facial_wrinkle_recovery extension owns lip_makeup recovery
source/person binding. Do not duplicate it. The optics-owned registry additions
are scope.py, ui/src/presets/presetModel.ts, ui/src/batch/batchScopeOptions.ts.
No runtime face landmarks, masks, corrections or recovery ownership are put into
the portable lip recipe or copied to another batch destination.
