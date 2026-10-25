# Local workflow native host, version 1

Status: source-authored integration. Runtime, builds, type checking, import,
rendering, export, tests, downloads, camera use and inference are all UNRUN.
This is an explicitly registered built-in module, not a hot plug-in system.

## Owner boundaries

The `local_workflow_host` module owns renderer request deduplication, private
definition storage, current-project lease acquisition, preflight tokens, the
durable core runner, bounded directory polling, and actual owner receipt
translation. It never switches a project, saves unsaved edits, loads an editor
photo, copies source bytes itself, fabricates a preset ACK, or invokes ordinary
export commands around an ingestion guard.

The exact currently loaded clean saved project is leased exclusively. The
renderer legacy `dedicated: true` field means exclusive ownership of that exact
project, not a second engine or a hidden project. A mismatching project ID/path
is rejected. The lease lasts at most one hour for new dispatch, admits no more
than the engine's remaining capacity capped at 64 imports, and is never silently
rotated. The directory source remains active until the cap is reached, an
explicit stop is requested, its lease expires, or an authoritative failure
stops the run. Reaching the cap seals discovery and drains admitted files.
The actual ingestion owner stops its lease after either failure or cancellation,
so managed-import currently advertises and accepts only the Stop policy; a
confirmed cancelled import also stops new native admission before release.

The actual usable graph is directory source → managed import → optional path
labels → export. Preset nodes currently fail real engine preflight. A later
preset adapter must return and retain a genuine owner review; opening a review
is not approval. Current capabilities therefore do not advertise preset
execution or review opening. No preset node is silently skipped.

## UI API

All requests and responses use the DTOs in `ui/src/localWorkflow/contracts.ts`.

- `local_workflow_workspace()` returns port version, stable persisted
  `host_scope_id`, workspace revision, actual lease, definitions, run snapshots,
  unresolved requests, and the real engine export profile/hash when available.
- `local_workflow_definition(workflow_id)` reads a saved definition.
- `local_workflow_preflight(input)` checks the schema, filesystem, exact lease,
  graph/profile compatibility and owner support. Tokens expire after 60 seconds
  or at lease expiry, whichever comes first.
- `local_workflow_submit(input)` persists identity before effects and accepts
  save, acquire lease, release lease, start, stop and open-review commands.
- `local_workflow_request(request_id)` only reads the original result.
- `local_workflow_run(run_id)` only reads the latest monotonic run snapshot.

The application adapter reads workspace first, binds its port `scope_id` to the
returned `host_scope_id`, and does not change it on a rerender. A repeated request
ID with identical content reads the stored result. A conflicting ID is rejected.
An unresolved request is never evicted or converted to a fresh operation.

`release_project_lease` is explicit for an acquired lease with no active run.
An active run releases its lease only after its core owner operation has a
validated terminal result and the real engine confirms release. Stop is a
dispatch fence, not cancellation or proof of rollback. While any owner result
or release remains unresolved, `effects_settled` stays false, including stopped
or failed runs. The UI must keep querying and must not unlock editing/start.

## Ingestion bridge

The native host calls the existing `ingest_session_api::submit/read_receipt`
ports, using state → arm → state preparation → import → original-identity query
→ release. One fully hashed, stat-bound occurrence is submitted per import.
Canonical nonnegative decimal timestamps are required by this engine protocol;
unsupported pre-epoch proofs are rejected, never reinterpreted.

The managed root's device/inode is captured through no-follow directory FD
traversal during preflight, retained in the token and run, compared again at
start, and sent as `root_identity` with every import. The engine checks the same
opened destination before its first copy, not merely after copying. Exact input
SHA, byte size, stat, occurrence, completion kind, original request UUID,
UUIDv5 operation, saved-project binding and document receipt are verified.
DocumentState.receipt_id is the actual ingestion operation UUID.

## Export owner bridge

The narrow engine envelope is `cmd: workflow_owner`, `protocol: 1`; it has
read-only profile/preflight/query, exact core-command execute and open_review
actions. The app routes `workflow_owner_result` to `receive(epoch, event)`.
This receiver performs its own contextual validation before settling the
generic project fence. Do not settle the fence from raw events or merely from
the receiver's boolean acceptance result.

Query receipts must match the full original core identity, exact original
request/session and phase-specific result proof. A bare failed response without
a core receipt remains uncertain unless the real owner explicitly provides a
validated `dispatch_rejected: true` no-dispatch proof. The engine republishes
the original execute terminal event before its query response, so the original
mutation fence is settled by real owner evidence rather than a native rewrite.

The returned real export profile must be explicitly adopted by the user,
saved, and preflighted. No placeholder digest is inserted. The current profile
is JPEG 95, RGB8, sRGB, scale 1, no GPS, watermark or layout, with an existing
chosen output root. Actual per-document saved recipes, target planning,
rendering, durable task state and verified output byte hashes remain owned by
the existing engine export path. Collisions do not authorize overwrite,
automatic renaming, or fabricated success. See `ENGINE.md` for exact wire and
profile details.

## Persistence and recovery

Private native state is owner-only, no-follow, checksummed, bounded, fsynced and
single-writer locked. A definition save uses independent storage-revision CAS.
Core per-run journals retain intents before dispatch and verified receipts after
readback. Native exact transport intent and engine epoch are persisted before
any send; neither timeout nor missing transport response triggers redispatch.
Owned transport uses `send_to_engine_at_epoch`, which rechecks the pinned epoch
under the final dispatch lock without bypassing the normal owner/project guards.
Only consumed successful readbacks can be pruned from in-memory read mailboxes.
Recovery slots are reserved; mutation and uncertain receipts are not evicted.

On process restart, the original core journal is read for an honest snapshot.
An old engine lease cannot be recreated: outstanding lease/owner/request state
remains fenced and read-only, with original identities preserved. No automatic
retry, replay, fresh export filename, project adoption or false settled state
is performed. A storage publication failure similarly fences further effects.

Shutdown is cooperative and nonblocking: it records a core Stop where possible,
does not wait for an arbitrary export/import duration, and does not claim those
effects settled. Application shutdown must call `shutdown()` before stopping
the engine. An eventual process restart will expose unresolved ownership.

## Authored acceptance checks (not run)

Pure fixtures in `tests_unrun.rs` cover strict renderer envelopes, explicit lease
release identity, pending/unknown non-settlement, full original receipt identity,
frozen destination containment, duplicate targets, phase confusion, and exact
output hashes/byte counts. Required future runtime acceptance also includes:

1. Save/reopen CAS; stale graph/profile/preflight/lease refusal.
2. Actual stable file → managed project receipt → frozen export → verified file.
3. Stop during copy/export and delayed completion: no next dispatch and no early
   effects_settled/release.
4. Lost original response; query succeeds without a second import/export.
5. Engine/process restart before/after each intent and commit: original identity
   remains visible and no old lease is adopted.
6. Managed/output directory replacement, source growth, output collisions,
   owner capacity, journal capacity and unread mailbox retention.
7. Preset graph refusal and no fabricated owner review or ACK.

No acceptance result is claimed from source fixtures alone.
