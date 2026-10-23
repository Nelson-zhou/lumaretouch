# Black/white fringe review workspace: source-only status

Authored on 2026-10-23. No import, project execution, build, typecheck, test,
browser launch, model inference, image benchmark or photographic acceptance was
performed. `workflow.unrun.test.ts` is an authored fixture suite, not a pass report.
The image placeholder in that fixture is only a protocol-boundary input and is
not a valid photographic test or decoder demonstration.

## Behavior reference and exact catalogue IDs

Primary manual: https://www.pixcakeai.com/guide/AlCcjw85ql (read 2026-10-23).
Prefix `LNX-REF-PC-AlCcjw85ql-C-`:

- `6d78bc490e`: dedicated entry and local Ctrl/Command + Shift + M binding.
- `f4f0ead111`: entry requests `{action:'enter'}` and requires enabled real output.
- `2173a021fd`: strength updates the draft and invalidates previous presentation.
- `8dbd34ce2a`: additive normalized circle/vector gesture coverage.
- `c205301c9f`: subtractive coverage, not a destructive image eraser.
- `eb7a67cd87`: explicit update computes a real new candidate before reviewed apply.

The reference establishes behavior, not proprietary kernels, Linux shortcut
behavior, quality equivalence or numeric ranges. This implementation's 0–100 /
initial 50 is a declared local choice supplied by Rust, not an official fact.

## Integration contract

`useFringeRepairWorkflow` belongs at App scope. `FringeRepairPanel` supports
`launcher` and `workspace` mounts with one shared owner. The parent must include
active/pending state in mutual exclusion, edit-intent invalidation, and truthful
feedback surfaces. An optional `onInspect` routes a confirmed apply to existing
main-viewer full-size inspection; it must not manufacture unsaved-candidate ROI.

Five native commands are required: `fringe_repair_preview`,
`fringe_repair_preview_status`, `fringe_repair`, `fringe_repair_result`, and
`fringe_repair_audit`. Audit bootstrap is mandatory and returns an admission
generation. There is no unsafe optional fallback. Native process-level inventory
owns unresolved operations across WebView remounts, not local component state.
The process ledger is not a disk-persistent or engine-restart recovery guarantee.

Set mutation fields: `enabled`, `strength`, required `reset_coverage`, and complete
session-new `strokes`, each with id, mode add/subtract, points [x,y], radius as a
fraction of final review short side, opacity and feather. Rust composes this list
against the immutable entry baseline on every update; it must NOT repeatedly add
the same list to the previous candidate. No source descriptor is user-selectable.
The native/backend boundary must enforce 128 strokes, 1024 points per stroke,
8192 points total, valid normalized coordinates and unique nonzero 32-hex IDs.

Drawing is on the final-cropped review. Rust inverses only full-size crop/rotation
once, retaining affine vectors in `post-optics-pre-crop-normalized-v1` destination
coordinates. It must not inverse body/manual/optical effects. The ready envelope's
top-level source descriptor is required. Recipe source may be null only with no
retained vectors; otherwise it must match that top-level source.

Preset/batch integration synchronizes enabled/strength only, recalculates each
target, and resets target manual coverage/source rather than transplanting another
photo's strokes. Existing batch review must warn that the target coverage resets.
No separate UI-local recipe or history owner is introduced here.

## Visual and interaction checks still required

- Load actual RGB8/RGB16 original and derived-source photos. Validate before,
  after and coverage PNG dimensions, no fabricated preview, and full-source
  computation before downsampling. Review fine hair, legitimate rim light, white
  clothing, jewelry and texture. This UI cannot establish kernel quality.
- Verify final-cropped pointer coordinates with crop, rotation, optics, body
  deformation and manual liquify combinations. Confirm vector position at export.
- Confirm final result reflects every pending addition/deletion/reset only after
  Update. Computed coverage image is hidden while dirty; colored pending vectors
  are explicitly instructions, not purported real correction coverage.
- Confirm pointer cancellation, capture loss, window blur, visibility changes,
  viewport motion, point/time budget overflow and repeated clicks do not save a
  partial gesture. Resizing or scrolling during a stroke must cancel it.
- Decode both photo PNGs and coverage before presentation. Keep full before and
  after visible, focused and without diagnostic overlay for the acknowledgment.
  Fit view handles portrait/landscape; proxy zoom never claims 100% source pixels.
- Repeat an update whose before PNG and neutral after PNG are byte-identical.
  Displayed-review identity must differ from the pending request identity, and
  every candidate/side image key must change so decode completion can be observed
  again. The corresponding workflow/key fixture is authored, but browser image
  load and paint timing still need a real UI check.
- Test narrow windows, keyboard focus trapping/restoration, launcher/workspace
  dual mounting, hotkey conflicts, Escape during preparation and pending apply.
- Change photo/source/upstream edits, close/reopen, undo/redo, and delayed image
  events; confirm the prior candidate cannot commit. No dedicated undo button is
  shown without proof that this operation is still the current history head.
- Exercise lost apply responses, missing/malformed/unknown receipts, native
  remount audit, changed engine, stale admission generation and late curve
  barriers. Query the original request, never resubmit to resolve uncertainty.
- Verify project reopen, presets, per-target batches, full-image inspection and
  original-size RGB8/RGB16 export separately after parent integration.

No whole-feature or whole-product completion/quality claim follows from these
source files. The source-owned workflow and original-size backend routes need
runtime and photographic evidence in the authorized test environment.
