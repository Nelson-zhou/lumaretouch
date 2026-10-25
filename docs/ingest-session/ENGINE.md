# Bounded current-project ingestion lease

Status: source authored; tests, imports, type checks, builds, execution, hardware, transfer and image-quality acceptance are UNRUN. This is not complete automation or certified USB camera support.

## Public engine contract

The command is `ingest_session`, the event is `ingest_session_result`, and protocol is `1`. Every request has an exact canonical UUID `request_id`; every event echoes that identity and `action`. Status is `pending`, `readback`, `succeeded`, `failed` or `unknown`. Acceptance is not completion.

- `state`: returns `state.current_binding` containing `project_id`, `path`, `workspace` and `disk_sha256`, plus availability and remaining receipt capacity. This observation never adopts a changed project into an existing lease.
- `arm`: requires `owner` (`workflow` or `tether`), exact `expected` binding and explicit `max_operations` between 1 and 64. The existing managed-import saved/clean/preview/background guard remains mandatory. Returns `session.session_id` and the frozen binding.
- `import`: requires `session_id`, explicit file `paths`, managed-copy `root`, and ordered `completed_sources`. Only copy mode is supported. It records the original operation identity before calling the existing managed importer. The managed operation UUID is UUIDv5(namespace=session UUID, name=outer request UUID); this deterministic recovery address is not retry permission.
- `query` and `cancel`: require `session_id` and the original `operation_id`. Query is readback, not import replay. Unknown permits query only. Cancellation asks the original worker to stop at its existing safe boundary; it is not a rollback claim.
- `release`: requires `session_id` and succeeds only after the original operation is terminal/reconciled and the frozen project still matches. It never releases a pending or unknown write.

Each completed source contains exactly `path`, `sha256`, `size`, `stat`, `occurrence_id` and `completion`. `stat` is the five-element `[dev, ino, size, mtime_ns, ctime_ns]` sequence encoded as decimal strings, preserving values beyond JavaScript's exact integer range. Size is a positive integer at most 2 GiB; at most 512 files and 16 GiB are admitted per operation. `completion` is `stable_read` for a local workflow or `completed_transfer` for tether input. The former is explicitly a filesystem stability heuristic, not proof that an external producer will never append later. The latter records the native adapter's completion claim, not camera certification.

The native adapter must hash complete bytes and record exact stat after its read. The existing managed importer rechecks source identity during copying, verifies complete copied bytes and hashes the managed destination again before registration. The trusted in-process precommit closure also checks every prepared source, exact stat, size, SHA-256 and expected exclusive target against the frozen native proof. Changed bytes are rejected before project replacement. There is no renderer-supplied flag to bypass this callback.

The logical filename is the basename of the chosen input path, which may already reflect user-selected native naming. Original camera filename/device/transfer identity must remain separately in the native immutable receipt; this engine bridge does not invent or authenticate those facts. Equal content from distinct input occurrences is not deduplicated.

Confirmed readback includes exact registered `document_id`, revision, source/recipe identities, full source hash, precise stat, occurrence and original managed receipt ID. Project disk SHA advances only after this session's own durable receipt and actual registered rows are verified. The current editing selection is never changed. No auto-save, force-open, project creation, recipe apply or export is performed.

## Shared integration owned by the host

New modules expose `controller(engine, emit)`, `handle(engine, payload, emit)`, `guard_command(engine, name, payload)` and `managed_passthrough(engine, payload)`. The controller is stored as `_ingest_session_host`, so existing recovery ownership inspection sees its active lease.

Required shared files and wiring:

1. `engine/src/lumaretouch_engine/server.py`: register command/capability, call `guard_command` before any command-side mutation or recovery capture, and dispatch the new command as a path transaction before recipe fences/history. Include this lease in the background `_owned_tick` gate and shutdown/finally close path.
2. Keep `ManagedImport.blocks` intact. Only when `managed_passthrough` validates the exact live session and its original operation may an outer `ingest_session query/cancel` cross that gate. All package/recovery/lens/expression/creative/source-relocation guards still apply. Never exempt the command name globally. `state` is not a passthrough during an active managed write; use its original owned query.
3. `engine/src/lumaretouch_engine/managed_import_host.py`: add keyword-only `trusted_precommit=None` to `handle` and `work`; forward it only to copy work, and invoke it from the existing `recheck` after full managed-file hashing and before atomic project replacement. Do not put the callback in JSON or relax the existing guard.
4. `engine/src/lumaretouch_engine/project_recovery_runtime.py`: classify session-only/readback actions correctly so they cannot taint image history or create fictitious project mutations. The actual managed transaction still owns durable registration. Autosave must not snapshot through an active lease.
5. `ui/src-tauri/src/ingest_session_api.rs`, `main.rs`, `engine.rs`, `native_dispatch.rs`: exact epoch/request-bound transport, capability registration and event observation; polling and cancellation must not invalidate unrelated capture owners. A known terminal must remain immutable; only an exact original unknown can reconcile. The Python host emits a correlated terminal for the ORIGINAL outer import when a query proves the inner transaction, separately from that query's readback.
6. The native workflow/tether owner must retain its immutable mapping from domain operation identity to canonical outer request/session/managed operation IDs. Lost sends are queried, not assigned a fresh UUID. While a managed import is active, `state` is blocked by its existing gate: compute and retain UUIDv5(session, outer import request) before submission, then use the exact owned `query`. Do not depend on a later `state` request to discover an unknown operation identity.

## Bound and stop behavior

The lease limit is the explicitly selected value, at most 64 operations, further limited by the minimum remaining persisted managed receipt capacity and current managed-host request capacity (both 256). No mutation or uncertain receipt is evicted and no project is silently rotated. The outer ledger has 256 slots, with 16 reserved for state/query/cancel/release: arm/import stop at 240. Only state/query envelopes whose own outer status is exactly `readback` are pruned. A completed read reporting an unknown original operation is disposable; the original mutation and operation remain retained. Failed/unknown read envelopes are not disposable. Polling can therefore exceed 256 completed queries without losing original mutation identities, while repeated unresolved read failures remain explicitly bounded. Failed/cancelled work stops new intake; verified but unregistered managed copies remain for inspection. A full or unresolved session stops and requires an explicit end/review/new session. There is no continuous/unbounded monitoring claim and no durable receipt-rotation implementation.

The legacy native `managed_import_api.rs` also retains at most 256 original starts. It needs readback headroom if reused directly; at exactly 256 retained starts, a new query envelope cannot be admitted. The dedicated session transport must preserve query capacity rather than reproduce this trap.

## Restart boundary and proposed persisted readback

Current implementation does NOT recover an old ingestion lease after engine/app restart. The new host has no prior session or operation map, so reopening the same project does not make an old `ingest_session query` valid. Native UI must report this limitation, retain the original mapping/proofs, stop automatic intake and never label reopen as successful reconciliation. The managed project contains only the original inner success receipt plus per-document managed-source records, not the outer request/session/occurrence ledger. Absence of a success record cannot prove that a failed/uncertain operation wrote no files.

Smallest proposed future route, NOT IMPLEMENTED: an explicitly read-only `recover_persisted` action receives the original session UUID, outer import UUID, derived inner operation UUID, original expected project identity/path/disk fingerprint, exact managed root and completed-source proof, plus a fresh observed current saved-project binding. It must require the same project ID/path and exact current disk snapshot, validate the project schema, find the exact durable inner success receipt, compare every recorded managed source/hash/stat and expected exclusive target to the original proof, verify all registered document/source identities and rehash the managed files. It returns verified historical completion and original document IDs only, without adopting a lease, changing current selection, loading a different project, rewriting rows, releasing unrelated fences or permitting automatic restart. Missing/contradictory evidence remains `unknown`.

The old disk fingerprint is evidence of the original pre-import base, not an equality constraint on the post-import file. A correct durable operation necessarily changes it. This route cannot prove the complete historical session chain from the current persisted fields alone; it may establish only an exact imported-operation match. Native reconciliation must retain that distinction and bind the outcome to its own persisted original request. A stronger replay/restart guarantee requires separately persisted immutable outer session/request/occurrence evidence, which is outside this bounded slice.

## Existing preset/export ownership, intentionally not bridged here

- `ui/src-tauri/src/preset_api.rs` → `preset_controller.py` / `workflow_ports.py` is the real current-document preset route. Correlated apply/preflight/save bind the actual `_load_id`, and `_guard_editable` requires the loaded image and no export/bench. Source-bound modules require target review. Dispatcher history is recorded before `PresetController.finish` emits its result. Calling the controller from an automation thread, switching the active photo behind the user, or reporting its acceptance as success would bypass ownership/history and is unsupported.
- `batch_api.rs` → `batch_preflight.py` / `batch_sync.py` owns frozen target preflight/commit and batch undo/redo. Unknown originals remain query-only; arbitrary recipe dictionaries are not a substitute for this route.
- `export_destination_port.rs` → `server.cmd_export_destination` → actual `server.cmd_export` and `export_destination_runtime.py` is the integrated route. `export_destination_controller.py` describes an older adapter and explicitly says it is not registered; do not mistake it for the live queue integration.
- Export selects explicit document IDs, freezes per-document recipes/source fingerprints and unique output names, validates a destination plan, then creates one task ledger before its worker starts. Same-session retry uses the original per-task frozen recipe; restarted tasks without that snapshot are refused. Filename collision policy is never silent overwrite. Source-bound masks and manual effects cannot simply transfer to a newly arrived file.

Therefore this slice delivers bounded verified ingestion only. Automatic preset/export chaining needs separately reviewed, target-owned ports and must not release the lease or secretly select documents to imitate support.

## Required unrun acceptance coverage

Schema and host fixtures specify exact binding, dirty-project denial, immutable request replay/conflicts, no hidden rotation/eviction, native-precision stat strings, changed bytes/stat/target precommit rejection, distinct equal-byte occurrences, editing/project exclusion between jobs, exact own recovery passthrough, original-request terminal re-emission, unknown query-only behavior, and refusal to release unresolved writes. Real filesystem races, post-replace failure/readback, engine restart, native transport saturation, UI lifecycle, image decoding, actual USB completion and end-to-end integration remain unverified.

## Native destination ownership

Protocol-1 import requires `root_identity: [device, inode]`, both canonical u64
 decimal strings, from the native destination/preflight pin. The internal-only
`trusted_root(fd)` callback validates the actual managed output descriptor
immediately after opening it and before `IO.prepare` creates any output, and
again inside transaction recheck. It also verifies the path still resolves to
that identity. A replacement directory is not authorized by a matching path.
This callback is not accepted from JSON. Existing generic managed-copy callers
without the internal callback retain their historical behaviour. The new
swap-directory and callback-order fixtures are authored, not run.
