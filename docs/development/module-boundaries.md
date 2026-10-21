# Module boundaries and incremental migration

This is a behavior-preserving extraction, not a rewrite or a claim that every
legacy responsibility is already isolated. New feature work must not be mixed
into its acceptance. The unfinished luminance feature remains a separate patch.

## Ownership

- `App.tsx`: interactive application composition and production lifecycle.
- `projects/useProjectWorkflow.ts`: owns project form/error/recent-list state and
  local persistence. Mounted unconditionally so workspace changes do not reset it.
- `projects/projectActions.ts`: project create/open/save/recent action policy over
  named I/O ports, independently testable without React or Tauri runtime.
- `projects/ProjectWorkspace.tsx`: project rendering only; no native I/O or storage.
- `diagnostics/useViewportProbe.ts`: opt-in static viewport evidence.
- `diagnostics/useBenchmarkAutomation.ts`: environment-opted-in acceptance scenarios.
- `diagnostics/useEmptyStateProbe.ts`: empty-state observation.
  These hooks receive named typed ports, never import App, never own production
  startup, retain packaged-build support and original StrictMode guards.
- `edit_commands.rs`: native exposure/HSL/crop/curve validation and dispatch.
  It owns no engine state. Algorithms remain in dedicated cores; AppState owns
  queue ordering/transport. Main registers qualified commands explicitly.
- `inspection_controller.py`: sole owner of inspection transaction, worker,
  request identities, publication-preparation state and teardown. It receives
  document, proxy-dimension, busy, snapshot and event callbacks, not Engine.
- `batch_sync.py`: owns batch IDs, commit/undo ledger, target planning and result
  summaries. Explicit documents/editor ports borrow current session rows; no Engine
  object is passed or cached. Scope validation remains in scope.py.
- `history_controller.py`: owns active undo/redo stacks and gesture identity,
  bounded record/bind/undo/redo with rollback through an explicit restore-frame port.
  Session still owns parked row histories and their existing copy/bind timing.
- `history_policy.py`: pure state identity and gesture grouping. No engine,
  renderer, project, session, transport or heavy runtime dependency.
- `server.py`: command ordering and integration. Compatibility properties expose
  inspection fields for existing embedding/tests but never duplicate their state.

## Migration safeguards

Preserve IPC names/arguments, event fields/order, snapshot budgets, cancellation
leases, protocol ACK order, history signatures and exact neutral behavior.
Move code with its focused tests. Source-location assertions must resolve the
actual module and still prove registration/call sites; do not delete assertions
merely because files moved. Do not concatenate all modules into a fake App string.

Architecture tests enforce dependency direction and coordination-file growth
ratchets. Line caps are not a quality metric; deliberate wiring growth requires
reviewing the boundary. Never split files into arbitrary fragments or pass a
whole Engine/App object just to conceal coupling.

## Still to migrate

Engine document/session/project transactions and export orchestration remain
coupled and need explicit ports before extraction. App still combines several
interactive workflows. Benchmark scenarios are now isolated from production but
remain a sizeable suite; future scenario extraction must preserve each historical
assertion. No claim of complete modularization is made by this first batch.

Validation: CI compile/unit suites plus Qoder's focused functional regression.
Deep GUI/performance/visual optimization remains deferred per current priority.

## Existing batch behavior deliberately not changed by extraction

The current commit loop's frame variable is overwritten for each target, so only
its final target's live frame may be emitted. Also, all recipes are validated
before writes, but a live replay exception is not a transactional rollback of
already written rows. These are separate correctness tasks; the extraction must
not silently claim stronger atomicity or a frozen preflight-token contract.

## Existing project behavior deliberately preserved

Dialog create/open paths still perform their authoritative refresh after a cancel
or caught failure. Recent-open errors remain local; dialog action errors also show
in the global notice. Direct Save still propagates rejection. These differing old
behaviors are pinned by action-port tests, not silently rewritten during extraction.
The registry adapter's legacy project-error reporting for other actions remains an
explicit compatibility call. Correcting these UX quirks is a later functional fix.

History extraction retains its original dedicated busy/loaded guards and
history-specific face/precompute replay. No stacks move until restore/render
succeeds; rollback failures still emit their warning. Dirty-state policy is not
changed. General editor guards/replay helpers are not equivalent substitutes.

## Levels boundary review (2026-10-21)

New levels work is not appended as another large Engine/App handler. Rust
`core/levels` defines scalar math; `levels_api.rs` validates IPC. Python
`levels_controller.py` owns transactional recipe state via five narrow ports;
`levels_stage.py` owns vector-stage state, while `ops/levels.py` owns schema/math.
UI `LevelsEditor`, `levelsModel` and shared `editReceipts` separate interaction,
parameter math and asynchronous acknowledgement policy. Shared export recipe,
scope/history and document snapshots carry the complete versioned recipe.

Server line cap changes 6980→7010 for explicit state/command/export registration
and document-token wiring only. New algorithms and controllers stay outside it.
App and native main retain their existing caps. Tonal receipts now use a matched
request/document plus an atomic host snapshot revision, including clear/restart
mutations; an identical recipe is not a completion signal. Snapshot document IDs
prevent separately sampled image/report fields from authorizing cross-photo edits.
Legacy curve callers remain supported without a document token; the new UI always
supplies one. This is not a claim that all older editing commands are token-fenced.

Basic Qoder/CI validation passed for the corrected candidate; exact evidence is
in levels-verification-2026-10-21.md. Deep GUI/performance remains deferred.

## Colour scopes boundary review (candidate)

Rust owns histogram/color mathematics and bounded protocol. Dedicated Python
sampling/controller/bridge modules own only stage extraction, request policy and
transport. Native ScopeHost owns request tickets/results; HistogramPanel owns UI
state. No Engine/App object is passed into the new controller. Optional stateless
pipeline taps preserve stage order and do not retain full tensors.
Native-main cap is reviewed 2030→2040 for module/state/IPC wiring only. Scope
requests use a separate read-only queue path and must not invalidate inspection.
Explicit refresh avoids adding another render to every slider/status event; live
cached capture, eyedroppers and full-source analysis remain unfinished scope.

## Identified colour capture boundary review (unverified candidate)

Capture lifecycle, bounded sampling, native ticket ownership, binary transport,
frontend async state, React subscription, display and readout are separate modules.
App/Viewer only pass bindings and a portal target; no capture work enters the long
WebGL render loop. Main gains state/module/command wiring; server gains a narrow
port factory and pre-command invalidation. Reviewed caps: native main 2040→2060,
server 7010→7040. App remains capped at 2150. These are growth ratchets, not quality
or feature completion scores. Basic CI/Qoder checks subsequently passed; see
color-capture-verification-2026-10-21.md. GUI acceptance remains pending.

Frozen sampling uses producer-bound presentation dimensions, not fixed proxy
raster aspect. The ordinary live-preview crop-aspect defect is still open.
Point/neighbourhood readout does not complete white balance, black/white-point,
curve or HSL action eyedroppers, full-source sampling or comparison sampling.
