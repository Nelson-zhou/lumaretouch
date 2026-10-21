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
