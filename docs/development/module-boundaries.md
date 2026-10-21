# Module boundaries and incremental migration

This is a behavior-preserving extraction, not a rewrite or a claim that every
legacy responsibility is already isolated. New feature work must not be mixed
into its acceptance. The unfinished luminance feature remains a separate patch.

## Ownership

- `App.tsx`: interactive application composition and production lifecycle.
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
