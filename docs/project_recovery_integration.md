# LNX-CORE-008: integrated local recovery workflow

Status: **implemented and wired, runtime acceptance UNRUN**. This is not a claim that crash safety, latency, memory use or the complete handbook acceptance case passed. No product execution, tests, build, compiler, typecheck, inference, download, installation or Git write was performed by this worker.

## Baseline and scope

Handbook line 1047 requires recoverable committed history, autosave independent of background rendering and verified backup before schema migration. Mapping `ENGINEERING-persistence / CORE-008 / LNX-CORE-008` remains unexecuted. Existing `project.py` already supplied atomic manual save (temporary file, file fsync, replace, directory fsync), schema validation/migration and document asset encoding; this was inspected, not declared absent.

`HistoryController.record` also records partial changes after command exceptions. It is not a commit signal. Recovery instead observes actual normal handler return AND emitted failure/unknown evidence, then waits for the native transport and cross-domain receipt fence. It never clears manual-save dirty state.

## Enabled path

1. App-lifetime `useProjectRecovery` polls every five seconds, independent of project-panel visibility. Pointer/composition interaction and a one-second settling window pause polls. Successful checkpoint captures no more often than every 30 seconds and only for a new committed revision with dirty work.
2. Native recovery admission requires a drained acknowledged dispatcher and no unsettled request in `project_recovery_fence`. All direct and ordinary EngineHandle sends register request IDs; read-only scopes are exempt. Terminal domain result settles its request; unknown/pending/running results do not. A new explicit opened/created workspace clears prior-workspace receipts. Snapshot and checkpoint proof is generated natively, not accepted from UI assertions.
3. The serialized engine boundary records handler return plus errors and false/unknown receipts. Failed/partial mutations taint capture until a successful explicit project open/create. Admission rejection before invoking the handler does not taint. No generic dirty flag or history-finally callback blesses a graph. Receipt-finalizer exceptions also taint.
4. Runtime also checks active/pending/uncertain/job/worker state on existing controllers/owners/hosts, batch owner, benchmark/export/thumbnail/pick workers, and unresolved effect/live previews. Package/import/relocation and recovery requests have reciprocal guards, including direct host entry points. Recovery checkpoints bypass capture invalidation and edit-history paths.
5. Capture retains current complete encoded recipes, inactive named versions, immutable assets, exact FacePrecompute numpy landmarks/masks, virtual-copy canonical IDs, people graph/scopes/history, undo/redo, managed-import provenance/receipts and source-relocation aliases. Existing project codec is used. FacePrecompute decode is explicitly recognized; recovered retained precompute does not trigger replacement inference on open. Unsupported objects, missing assets, hash mismatch or ANY dropped record block rather than produce partial recovery.
6. One background writer plus one coalesced frozen-byte snapshot bounds the disk queue. Named snapshots cannot be coalesced away. Epoch invalidation protects project switches and shutdown. UI state says queued/writing/saved/blocked; enqueue is not durable success.
7. Fully fsynced project plus hash receipt is published by an atomic directory rename and destination/source directory fsync. Only complete, validated candidates are listed. Incomplete staging remains counted, never offered as committed. Post-rename fsync error is not success.
8. Opening an old schema first stores and verifies an exact-byte backup, then migrates and validates those same bytes in memory. Original is unchanged; future schema is rejected. Existing current-schema load remains unchanged.
9. Recovery panel works without an open project (including a corrupt original): review candidates, inspect full source identity, restore only into a fresh child directory/new project ID, explicitly open that new copy, or move a candidate into recoverable trash. Trash can be inspected/restored, never silently purged.
10. Missing/moved originals may be explicitly relinked only to an equal full SHA256 and byte count; all linked virtual-copy rows and relocation aliases follow together. Independent source records cannot be silently merged. This publishes a NEW candidate, retaining the old candidate; changed pixels never inherit old masks.
11. Restore/discard/relink write immutable started/result operation records. An interrupted started record is shown as unresolved, not replayed. Unknown outcomes retain the destination and native/UI pending fence. After restart, the local operation journal exposes interrupted work for inspection. No automatic retry of an uncertain write occurs.

## Boundaries and limitations, not acceptance waivers

- Safe scope is current-schema graphs that the existing codec can preserve completely, under the configured budget, and whose command/receipt owners reach the settled boundary. Historical projects already carrying `dropped` records remain blocked; this implementation does not pretend previously lost assets can be reconstructed. Unsupported runtime objects also remain blocked with an explanation.
- Native request-fence coverage is conservative: a new protocol with no recognized terminal receipt pauses autosave rather than assuming completion. Unknown requests require explicit reconciliation/reopen. Existing registered protocol/result combinations still require local fixture coverage.
- Engine-side capture/encoding runs on the serialized command owner so a graph cannot be concurrently sampled. Disk publication is asynchronous and preview rendering is not invoked. Large capture CPU/memory/latency has NOT been measured; this is not a responsiveness claim.
- Capture budget is 64 MB; serializer cap remains 256 MB. Store defaults retain 1.024 GB, 64 MB free reserve and at most 64 active candidates. Trash, backups, operation records and staging all count. No automatic deletion frees space; exhaustion pauses autosave visibly. User-configurable storage/retention settings and interrupted-staging cleanup are not added in this change.
- Source verification uses existing bounded, cancellable no-symlink full-hash I/O (2 GiB per source, 16 GiB/120 seconds per scan). Unknown/full-hash-less sources cannot be guessed. Cancellation stops before the next safe file/commit boundary; shutdown does not claim queued dirty work was flushed.
- Operation journal supports inspection, not unattended repair/replay of an ambiguous write. A destination from an interrupted operation must be checked before a new restoration. Originals and candidates are retained.
- No external upload or network call is added. Portrait assets remain in local private recovery storage. This is not portable-package permission to export sensitive descriptors.

## Concrete wiring

- `server.py`: emit observation; serialized handler boundary; recovery command; special failure receipt; HANDLED entry; shutdown cleanup.
- `project_package_project_commands.py`: exact pre-migration backup and successful project-switch epoch; retained-precompute reopen.
- `project.py`: explicit FacePrecompute reconstruction, same project.v23 identity schema.
- `project_package_host.py`, `managed_import_host.py`, `source_relocation_host.py`: reciprocal recovery guard.
- `project_recovery_runtime.py`: committed revision, taint, settled-owner checks, checkpoint capture and status.
- `project_recovery_capture.py`, `project_recovery_scheduler.py`, `project_recovery_store.py`, `project_recovery_host.py`: lossless capture, bounded scheduling, durable candidate/operation storage and request host.
- Tauri `main.rs`, `engine.rs`, `native_dispatch.rs`: registered commands, correlated result routing, native issued/result fence, read-only recovery dispatch.
- `project_recovery_api.rs`, `project_recovery_fence.rs`: receipt readback, native queue proof and all-request settlement.
- `App.tsx`, project hook/workspace and `ui/src/projectRecovery`: persistent polling plus explicit review/relink/trash/restore/open UI.

Exact touched file hashes are in `project_recovery_manifest.json` (manifest excludes itself).

## Validation to run locally

Authored Python fixtures: `engine/tests/project_recovery_cases.py`. Authored Rust native-fence fixtures: `project_recovery_fence.rs`. Acceptance scenarios: `engine/tests/fixtures/project_recovery/acceptance_unrun.json`. These are all UNRUN.

Qoder must run Python fixtures, TypeScript/Rust compile and tests, UI interaction/restart, crash injection before/after every fsync/rename/journal phase, source drift/relocation, exact FacePrecompute/people/history/managed-import roundtrip, disk/permission/backpressure/cancel/shutdown and performance measurements. Static AST, JSON parsing and source hashes are not runtime evidence.

Primary practices checked 2026-10-23:
- Krita saving/autosave/backups: https://docs.krita.org/zh_CN/user_manual/autosave.html . Explicit saves, autosave recovery and backup versions have distinct roles.
- SQLite atomic commit: https://www.sqlite.org/atomiccommit.html . Ordered file/directory synchronization and I/O failure handling matter; rename alone is not proof of power-loss safety.

These sources informed implementation, not a test-pass claim.
