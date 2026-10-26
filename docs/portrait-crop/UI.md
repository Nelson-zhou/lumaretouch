# Current-photo portrait composition UI

Status: authored source and static review only. Tests, TypeScript checking, builds,
product execution, image decoding, detector inference, real-photo inspection,
photographic quality, persistence and runtime acceptance are **UNRUN**.

## Scope and preserved controls

The isolated module is `ui/src/portraitCrop/`. It covers the current-photo
workspace `control:PC-32478:9`, headroom `control:PC-32478:15`, head proportion
`control:PC-32478:16`, and horizontal face position `control:PC-32478:17`.
Preset saving `control:PC-32478:18` now has a separate local rules-only catalogue
and explicit draft-only load; see RULE-PRESETS.md for its source-only/UNRUN scope.
There is no batch recalculation, hidden automatic crown detection, official
ID-photo compliance claim, fabricated preview, or automatic apply.

The official guide, <https://www.pixcakeai.com/guide/32478>, does not disclose
numeric defaults/ranges, denominator conventions or independent face-position
axes. This implementation therefore starts with **blank rules** and describes
its own conventions instead of inventing official ones:

- Aspect ratio is frame width divided by height. The UI's local bounded input
  range is 0.001–1000, not an official product range or a solver claim.
- Head fraction is the vertical crown-to-chin height divided by frame height,
  strictly greater than zero and at most one.
- Headroom is the vertical frame-top-to-crown distance divided by frame height,
  from zero to one. Headroom plus head fraction must not exceed one.
- Face position is the selected face center's horizontal fraction of frame
  width, from zero to one. Vertical position is derived and displayed, not an
  independently editable overdetermined constraint.
- All three anchors are in the full current edited, uncropped source-edge pixel
  grid: X in [0, width], Y in [0, height]. Browser pointer coordinates are mapped
  through the full-grid SVG transform. Numeric entry uses the same full grid,
  never proxy pixels or old pre-edit landmark coordinates.

## Ownership and integration

The ready-to-mount `PortraitCropWorkspaceHost` accepts `enabled`, `contextKey`,
`onChanged`, optional `onBusy`, and optional `onReopenProject`. It owns a separate launch button/overlay and
keeps the existing ordinary CropModal intact. Mount the host at App lifetime,
not only when its overlay is open. Parent admission excludes its own busy bit;
the `onBusy` callback fences other edits while the overlay is open or an
original request remains. The launch button, overlay and panel carry
`data-portrait-crop-workflow` so guarded recovery stays reachable.

Alternatively create exactly one `PortraitCropController` at App lifetime, not inside a modal.
Its constructor accepts a `Transport` and an optional confirmed-publication
callback. The component is `PortraitCropPanel` with `controller`, optional
external `disabled`, and optional `onClose` props. The parent owns route/modal
registration, native commands, global edit fences and refresh.

Use `setContext(contextKey)` whenever the current source/document epoch,
revision, edit state, repairs or analysis change. A file path alone is not a
context identity. Use `setContext(null)` if no current document exists.
`setEnabled(ready)` reflects external engine/export/other-tool admission, not
the controller's own busy flag. Keep its original request and global write
fence alive while `snapshot().pending` is non-null, even if the window closes.
Use `dismiss()` for all route/outer-window dismissal paths, not only the
component's close button. The controller preserves unresolved apply outcomes
and checks their original document even after navigation.

The controller exposes `snapshot`, `subscribe`, `acquire`, `selectFace`,
`useFaceProposal`, `mark`, `confirmAnchor`, `setRules`, `prepare`,
`confirmReview`, `apply`, `cancel`, `dismiss` and `reconcile`. Image components
report exact session/token/image-key readiness, ignoring late callbacks.
Editing an anchor, rule or pending numeric anchor input invalidates review.
Selecting a different face clears all marks and confirmations.

Transport:

- `send(request, onReceipt?)` sends the immutable original command **once**.
  Optional progress supplies the host's genuine `working`/`unknown` receipt.
  The native transport settles pending curves before current/apply, rechecks
  exact context/admission, and notifies inspection only immediately before an
  actual apply invoke. It invokes `portrait_crop` once, then polls
  `portrait_crop_status` by retained original, with 10-second individual waits
  and a 120-second polling window. A lost initial reply is reconciled by status.
  Unknown apply progress stays fenced while these read-only checks run; only a
  proven terminal receipt clears it. Timeout or missing evidence leaves the
  original available for explicit recovery. No timeout re-enqueues a command.
  Only a typed local error before actual enqueue proves that this UI did not
  send a request; it is not a fabricated engine rejection receipt.
- `status(original)` queries the original immutable command's request ID.
  It may return the original receipt or the host `status` wrapper. A missing,
  malformed, nonmatching or unknown outcome never clears the write fence.
- `cancelRead(original, commandSha256)` is optional reader ingress cancellation
  via `portrait_crop_cancel_read` for a current/preview job, using the already observed host digest. An ingress
  acknowledgement is not cancellation completion. The original must resolve.
- Ordinary `cancel` retires only its exact capture session. Cancellation never
  clears an unknown apply. Closing while a read is active discards late UI
  results; closing during apply retains the original mutation for recovery.

The isolated `transport.ts` is the only UI adapter importing native invoke,
inspection intent and the existing curve barrier. No other module is edited. The host remains
sole owner of full capture, fresh detection, Rust planning, full rendering,
current crop, history, project state and export. A confirmed commit callback
must refresh the actual current document; a refresh failure is not permission
to reapply.

## Exact request and receipt binding

All commands are `{cmd: 'portrait_crop', action, request_id, ...}`. Protocol v1
matches `portrait_crop_host.py`: current, preview, apply, status and cancel.
Every receipt contains `version: 1`, `event: 'portrait_crop_result'`, original
request ID/action, `command_sha256`, `original_request`, and phase.
The entire echoed request is compared structurally with the retained original.
The first host-issued command digest is then pinned for every later receipt.
The UI intentionally does **not** pretend JS numeric JSON bytes match Python
float canonicalization.

Capture validation requires the exact document/source/state/non-crop/people/
repair/uncropped hashes, effective source proof, source-edge grid, fresh current
full-frame proxy inference metadata, detector/semantic hashes, proxy identity
and bounded genuine face proposals. Source raster hash must match the binding.
The displayed source is the immutable current edited **uncropped** image.

A detected face is explicitly selected, never first-face auto-selected. Its
chin and center can be adopted only as unconfirmed proposals; adopting them
also clears any crown. FaceMesh forehead point 10, the face bounding box and a
face center are never labelled a measured crown. The user marks and separately
confirms the real crown, chin and chosen face center on the actual image.

Preview must echo the original request's anchors/rules, capture and original
preview request ID; use the Rust backend and source grid; retain all anchors;
and report actual integer bounds, normalized actual bounds, output dimensions,
requested and achieved ratios. The UI validates their internal consistency.
Nonzero current rotation is refused by the host and disclosed in the UI, not
silently reset. The full before image must equal the captured current before
image; the after image must match actual output dimensions.

## Photographic review and apply

`PortraitCropImage` displays the supplied immutable full-frame PNG and checks
its SHA-256 bytes plus decoded natural dimensions. Its display scaling is not
an image crop or an input to the final sampler. A load, digest or dimension
failure prevents anchor confirmation / candidate approval. Source mapping
remains the full grid even when the PNG is a bounded display/inference proxy.

Before apply, both the complete current-before and actual complete candidate-
after images must load and verify, and the user must check an explicit review
confirmation. The apply request binds capture/session, original preview request,
preview token, candidate state digest and both actual image digests. There is
no apply triggered by image load, slider movement, opening the panel or preview
completion. The host checks source/edit staleness again before its existing
canonical crop/history mutation.

A successful UI outcome requires a `committed` receipt with matching original
apply ID, original request echo, pinned command hash, candidate/token and
captured document, plus actual `applied` or `no_change` status. An `unknown`
outcome remains fenced across close/reopen and source changes. A cancellation
or rejection is terminal only with explicit `no_write: true`.

## Authored UNRUN fixtures and remaining acceptance

`workflow.unrun.test.ts` contains synthetic protocol fixtures only. They cover
blank/nonfinite/conflicting rules, no automatic crown or first face,
source-analysis mismatch, actual before/after review gating, request and achieved
geometry consistency, edit invalidation, cancel-without-apply, unknown apply
across close/navigation, original-request recovery and late-source suppression.
They have **not been run** and their placeholder fixture bytes are never used
by production UI or claimed as photographic evidence.

Still required in an authorized execution environment: TypeScript/build,
fixture execution, real detector/model admission, image hash/decode browser
verification, keyboard/pointer/numeric interaction, double-click races,
viewport resize, source switches, repair/analysis mutation, source loss,
late callback and status replay, existing nonzero rotation refusal, genuine
full-resolution output review, undo/redo and project save/reopen acceptance.

## Authoritative project-reopen recovery

Any uncertain pending original request exposes a recovery button when the parent
supplies `onReopenProject`. It invokes the existing confirmed project picker /
open flow, not a new writer, after explicitly warning that reopening a saved
project discards unsaved edits. Callback completion, choosing a file, changing
context, restarting an engine and an absent receipt do not clear the pending
request. The UI then queries the same original request.

The only nonterminal recovery exception is the native-owned wrapper:
`workspace_reopened: true`, `authority: native_verified_project_reopen_v1`,
exact `original_request`, `outcome_unknown: true`, complete `authoritative_event`
and `message`. It is deliberately not a server crop receipt: no phase, event,
command digest, success, no-write, cancelled or committed result is invented.
The native owner requires explicit project-open/create/new or recovery-restore
ingress followed by the actual valid project-opened/created event in its live
engine epoch. The UI also validates the exact original request and authoritative
project event's open/path/project-ID/document-count/dirty fields and rejects
error, failed, unknown, reload-required or readback-required events.

Only that evidence retires the old workspace edit lock and discards old source,
anchors and candidate. A persistent historical-unknown notice retains the old
request ID and never calls the operation failed, cancelled, undone or applied.
Application wording is reserved for apply; source/candidate reads and session
cleanup are identified as non-application requests, without inventing completion
or cancellation after engine/receipt loss.
A new operation requires a new complete capture and review. A genuine terminal
receipt retains priority in the native owner. Additional authored UNRUN fixtures
cover verified recovery, context-only non-recovery, mismatched original identity,
invalid authority, failed project events and fake terminal fields.
