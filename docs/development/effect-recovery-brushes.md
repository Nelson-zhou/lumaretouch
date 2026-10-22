# Tool-specific effect recovery

Status: implementation wired through authoring, real-pipeline proxy feedback,
one-gesture history, project v6, inspection and full-size 8/16-bit export.
Static source review only: no build, test, typecheck, product execution,
image-quality acceptance or timing measurement has been run for this package.
Qoder owns local execution/acceptance; this is not a validated-quality claim.

## Requirements and primary-source comparison

Frozen handbook `manual-text.txt` lines 634–654 establishes effect-specific
recovery and the restricted applicability matrix, not a universal erase tool.
The AI development pack's stable requirement IDs are:

| Requirement | Meaning | This package |
|---|---|---|
| LNX-REF-PC-32558-C-d5122cf2f7 | Recovery applicability matrix | Explicit supported and unsupported targets |
| LNX-REF-PC-32481-C-28cb894965 | Blemish recovery brush | Not claimed: existing manual repair is not an independent automatic blemish operator |
| LNX-REF-PC-32481-C-29dca0bb2c | Background adjustment brush | Not claimed for missing background cleanup/lighting operators |
| LNX-REF-PC-32481-C-0f284fcda5 | ID-photo background brush | Existing background replacement only; no new ID-photo generator claim |
| LNX-REF-PC-32481-C-269ed8adef | Sky brush | Unavailable: no genuine sky replacement stage |
| LNX-REF-PC-32481-C-35a8c63501 | Clothing crease brush | Existing measured fine-crease operator only |

Official current comparison, checked 2026-10-22:

- [PixCake official recovery FAQ](https://wiki.pixcakeai.com/guide/9682.html)
  includes selected smoothing, blemish, background, sky, hair and clothing
  families, but explicitly excludes oil-shine, lip lines, double chin and
  accessory breast corrections. The frozen original URL is
  https://www.pixcakeai.com/guide/32558; the current official wiki corroborates
  the matrix when that older URL cannot be fetched. No iPad-only behavior is
  used as a Linux desktop requirement.
- [darktable official per-module blending](https://darktable-org.github.io/dtdocs/en/darkroom/masking-and-blending/blend-modes/)
  combines each module's input and output before the next module. Recovery uses
  that operator-local boundary, never a final-frame blend with the unedited
  photograph. This preserves the other edits and the actual pipeline order.
- [darktable official drawn masks](https://darktable-org.github.io/dtdocs/en/darkroom/masking-and-blending/masks/drawn/)
  retains vector geometry and allows brush size, feather and opacity controls.
  LumaRetouch reuses its existing bounded Rust LMR2 evaluator rather than adding
  another Python/JS image-mask algorithm. This is a design comparison, not an
  algorithm, UI or proprietary quality parity claim.

The frozen recovery references do not establish exact numeric brush ranges or
a proprietary hardness curve. The UI therefore labels local choices honestly:
diameter 0.5–25% of the visible locator short edge; strength 1–100%; feather
0–100 mapping to the existing source-space box-filter radius 0–5% of the source
short edge. Feather is not mislabeled as measured commercial brush hardness.
Add strokes use LMR2's maximum-coverage union, not cumulative flow; the UI states
this explicitly. Subtract strokes reduce the existing coverage in saved order.

## Implemented operator boundaries

| Retained target | Before/after operands | Coordinate treatment |
|---|---|---|
| `skin_smoothing` | `lighten_source()` vs current strength/channel smoothing mix | Source grid; before deformation |
| `fabric_fine` | Fabric stage input vs measured fine-crease output | Source grid; before deformation |
| `background_replace` | Fully retouched/graded foreground vs background composite | Source coverage passed through the exact image deformation grid |

The true graph remains repair + smoothing/light → fabric → deform → enhance →
exposure → levels → curves → HSL → LUT → grade → independent local grades →
background → geometry. Do not follow old prose suggesting a different order.

The under-eye implementation has a combined source-derived delta including
dark circles, bags, veins and catchlights. This package does not incorrectly
attenuate that combined delta and label it independent blemish recovery. Hair,
sky, oil shine, lip lines, double chin and accessory-breast targets are not
offered. The capability report explains these boundaries to the user.

For a target's coverage `m`, the stage recovers between that operator's `after`
and `before`. Exact zero/full endpoints copy `after`/`before` respectively.
RGB remains floating point, including the 16-bit source/export path. Only
disposable mask coverage and UI PNG delivery are 8-bit. No proxy image or mask
raster becomes the project recipe.

## Authoring, feedback, history

The continuous tool workspace shows two separate photo views:

1. The native-fenced, immutable source-input LRCP view locates retained source
   coordinates. Crop/rotation inversion reuses `local_mask_geometry`.
2. Actual production-pipeline before/after PNGs show the evaluated result,
   including all other active retouch/color operations and deformation. Source
   contours are labeled positioning guides, never processed image feedback.

During a gesture, there is one in-flight preview and one replaceable latest
candidate. Old results retain their identity and cannot submit a later gesture.
On release, the final candidate is rendered, decoded and painted, then native
and engine presentation acknowledgements gate automatic single submission.
No per-stroke Apply dialog is required. A terminal post-history receipt permits
automatic continuation with a fresh source capture and current recipe revision.

Escape/cancel before submission discards the candidate. Once sent, the owner
queries only the original request ID; transport failure, timeout or process
exit cannot trigger a repeat mutation. Target changes, source changes, document
switches, competing edits, unmount, pointer loss and over-budget strokes stop
unsubmitted work. The App-scoped owner and photo workspace survive a collapsed tool panel.
Only launcher controls live in the retouch panel; a pending result remains
queryable even after its workspace closes. Final frame/doc-state publication
follows history recording, so the displayed undo depth is not a pre-commit count.

## Ownership and resource boundary

`_effect_recovery = {version:1, source:{sha256,width,height}|null, targets:[...]}`
holds independent `{target, enabled, recipe}` records. Each recipe contains only
ordered source-normalized add/subtract brush vectors. Full/intersect/range/
semantic/prompted objects are rejected for this tool. New stroke IDs cannot
overwrite an old stroke. The three target records are never merged.

Limits reuse LMR2: 64 strokes per target, 128 total, 8192 path points total,
64 MP per raster, 128M pixels across enabled target masks, and the combined
512M work budget. Original-dimension preflight happens before mutation.
Both source hash and source dimensions belong to the original decoded photo.

An unavailable preview recovery mask suspends the affected operator, reports
the reason, and retains the recipe. It does not silently restore the unwanted
automatic effect or replace a missing mask with full-image coverage. Full-size
inspection/export rejects missing/stale fields instead of exporting an
incomplete image. Full masks are regenerated at decoded source dimensions and
cut with the exact render-tile halo; background recovery uses the same warp.
These brushes are not transferred to other images by batch or presets.

## Integrated shared boundaries

Owned modules:

- `effect_recovery_state.py`: strict retained state, per-target transitions and
  original-size budgets.
- `effect_recovery_stage.py`: float operator-local mixer and field validation.
- `effect_recovery_runtime.py`: source identity, cache key, preview sync,
  source-decode guards, full-size preparation and tile attachment.
- `effect_recovery_preview.py`: one read-only actual-pipeline candidate and
  presentation gate. `view` is never committable.
- `effect_recovery_controller.py`: prepare before mutation/fence, rollback,
  receipt replay protection and finish after history.
- `ui/src-tauri/src/effect_recovery_{api,host}.rs`: native preview lease,
  native-bound source proof, single redemption and independent history receipts.
- `ui/src/effectRecovery/*`: App-scoped continuous workflow and actual-photo UI.

Applied wiring, retained here for lifecycle maintenance:

1. Pipeline initializes/resets `EffectRecoveryStage(device,(h,w))`. Smoothing
   calls `apply('skin_smoothing', base, out)` after its existing mix. Fabric
   calls `apply('fabric_fine', out, fabric.apply(out))` without reordering.
   Background calls `apply('background_replace', t, composite, align=
   align_source_grade_mask)` after its existing composite. Include resident
   mask bytes in the reported budget.
2. Server adds `_effect_recovery` to fresh/captured/applied document state, not
   `PROXY_BOUND`; source-normalized vectors survive proxy changes but remain
   source-bound. All production render sync sites call runtime `sync`. Report
   capabilities as `effect_recovery_protocol:1` and `doc_state.effect_recovery`.
3. Add `effect_recovery` to edit/handled lists; prepare before revision fencing;
   finish after history; never coalesce two gestures. Add read-only
   `effect_recovery_preview` handler. Preserve its source capture and snapshot
   context only for read-only preview commands, never exempt actual edits.
   Invalidate preview candidates with the existing source-capture lifecycle.
4. Project writer uses v6 to reject older-reader silent loss. It retains v1–v5
   support and preserves v5 independent groups; only pre-v5 initializes them.
   Strict validation is recursive through document/history/version recipes.
   Explicit null or unknown recovery version must fail, not become empty.
5. Snapshot names: `effect_recovery`, `effect_recovery_path`,
   `effect_recovery_stamp`. Call `verify_snapshot` before full decode and
   `check_export_decode` after decode. `configure_export(spec,snap,(h,w),
   for_document=...)` refuses cross-document reuse. ExportSpec declares these
   fields plus disposable `effect_recovery_fields`. Full export calls
   `export_prepare(spec,(h,w),cancelled=...)`, and each tile calls
   `attach_tile(pipe,spec,(cy0,cx0,cy1,cx1))`. Source changes abort output.
6. Native AppState fields: `effect_recovery: Mutex<RecoveryHost>` and
   `recovery_preview: Mutex<RecoveryPreviewHost>`. Initialize/reset/end both;
   route result/preview events; advertise readiness to receipt host; invalidate
   preview on mutations; enqueue `effect_recovery` through its API; register
   the four recovery IPC functions. Do not add preview to edit/coalescing routes.
7. UI owns `useEffectRecoveryWorkflow` once in App and includes it in competing
   capture exclusivity, pending guards and context cancellation. Render
   `EffectRecoveryPanel` with its report and keep `EffectRecoveryWorkspace`
   mounted beside the main viewer. No new Viewer image algorithm is
   required: the standalone tool workspace displays the two verified photos.
   Keep existing App/main/server line caps through real module extraction.
   `capture_lifecycle.rs` owns reset ordering for existing and new receipt hosts.
8. Independent-group numeric live gestures are mutually exclusive with recovery
   and other capture tools. Their temporary main-canvas pixels are invalidated
   and restored at the engine boundary before unrelated commands, including
   save/export/inspection. Recovery previews never replace that main-canvas
   buffer and retain their own actual-output presentation acknowledgement.

The integration listing is not execution evidence. End-to-end behavior,
photo quality, 8/16-bit parity, deformation alignment, repeated gestures and
undo/project round trips remain unrun until the authorized local validation.
