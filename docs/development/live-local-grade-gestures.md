# Independent local-grade numeric gestures

Status: implementation wired; static review only. No application run,
build, typecheck, test, GPU benchmark or visual acceptance has been performed.

## User-visible behavior

- The four numeric controls use the actual main-canvas renderer while dragging.
  They are not curve readouts, DOM color filters or source-image simulations.
- A pointer drag or held adjustment key is one gesture. Release commits one
  history entry. Returning to the starting values creates no history entry.
- Escape, pointer cancellation/lost capture, an interrupted control, window
  blur, hidden document or a changed photo/tool cancels uncommitted values.
- A disabled group stays disabled and clearly says it cannot affect the photo.
- An uncertain commit is queried using its original request identity. It is
  never resubmitted, and a later blur cannot pretend to undo an accepted commit.

## Actual render and persistence contract

`local_grade_live.py` temporarily replaces only the selected group's four grade
parameters in the retained `LocalGradeStage`, calls `_write_current_frame`, and
restores the canonical stage in `finally`. Its mask tensors are reused. Thus
the existing grade operator, actual source-mask deformation, legacy grade/LUT,
other groups, background and output geometry keep the same ordering and code.

Preview does not update `_local_grade_layers`, mark the project dirty, clear
redo, append undo or publish `doc_state`. Commit updates only the selected
group's grade and records history once after successful production rendering.
Project/export retain the normal canonical group schema; preview pixels never
become project assets or an export substitute.

Every unrelated engine command must invalidate the session and restore the
canonical frame **before** capture, inspection, save, export or other edits.
A restore failure blocks that command and invalidates the pipeline. This
boundary belongs to engine dispatch, not a UI-only lock. Genuine geometry/SAM
operations still redeem their original reviewed capture proofs; numeric edits
do not manufacture or consume irrelevant source-image presentation proofs.

## Scheduling and identities

The UI owns one in-flight command and one replaceable latest numeric value.
Begin, final commit and cancellation are barriers, never replaceable previews.
Every command has a unique request ID, photo ID, group ID and gesture ID. Native
receipts additionally bind the engine epoch. The engine binds the retained
recipe revision, source stamp, actual pipeline and complete group collection.
Changing another group cannot be overwritten by a stale selected-group draft.

After uncertain delivery the UI only queries the existing receipt. Missing or
malformed receipts leave an explicit uncertain state. No success is inferred
from coincidentally equal values. The App-scoped owner survives panel collapse.

## Hashing and cache scope

Admission and commit perform full source/model verification. During a verified
numeric gesture only, unchanged retained masks/model data can be reused under
before/after dependency stamps: device, inode, size, nanosecond mtime and ctime,
plus runtime-file membership. The lease cannot survive another command or
commit. A changed dependency fails immediately; it is not deferred or ignored.

## Relevant mature patterns

- Qt exposes distinct press/move/release signals and live value tracking:
  https://doc.qt.io/qt-6/qabstractslider.html
- GTK's scale uses value-changed for actual value updates, not only formatting
  the displayed number: https://docs.gtk.org/gtk4/class.Scale.html
- Existing repository patterns: `parametricGesture.ts` gesture finalization,
  `edit_queue.rs` adjacent latest-value coalescing with barriers, and
  `receipt_host.rs` epoch-bound terminal receipts. The new numeric previews
  differ deliberately from ordinary optimistic persistent sliders: only the
  final release changes history, so cancellation preserves the previous redo
  chain and no uncommitted value leaks into a saved project.

## Required later acceptance (not performed)

Inspect real photographs with overlapping groups, nontrivial legacy grade/LUT,
automatic deformation and crop; compare drag/commit/export values; interrupt
mouse and keyboard gestures; undo/redo; switch photo/group/tool; collapse the
panel; request save/export/capture/inspection mid-gesture; change source/model
files; interrupt engine delivery and query the original commit receipt. Measure
input-to-present latency on target CPU/GPU rather than claiming an FPS result
from the coalescing design alone.
