# Local workflow core: bounded v1, not full handbook parity

Status: **SOURCE AUTHORED; BUILD, TYPECHECK, TESTS, IMPORT, EXPORT AND RUNTIME QA UNRUN.**

`core/local_workflow` is an independent Rust rlib (MSRV 1.77). It contains real graph validation, a finite scheduler, a durable event journal and a filesystem polling source. It does **not** contain a renderer, an image decoder, a fake engine, a fabricated review acknowledgment, a background timer, an ERP connection or an AI classifier. This core alone does not make an end-user workflow runnable. Native, engine and UI adapters must advertise availability only after the actual ports are connected and validated. No shared registration files are changed by this module.

## Sources and deliberate scope

- Official handbook, workflow `8YEKwsjJg7`, accessed 2026-10-25: <https://www.pixcakeai.com/guide/8YEKwsjJg7>. It describes local-folder ingestion, node configuration, preflight before activation, records, source/sink connection constraints and three error policies. Local filename/path labels are distinct from ERP tag templates. This implementation is a restricted local subset, not the handbook's full node catalog, branching system, templates or automation product.
- Notify **8.2.0** primary package metadata: <https://docs.rs/crate/notify/8.2.0>. The package declares Rust **1.77** and **CC0-1.0** for notify itself. Its transitive crates have separate licenses; no blanket CC0 claim is made for them.
- Notify's documented event limitations and polling alternative: <https://docs.rs/notify/8.2.0/notify/>. Filesystem events are not completion guarantees. Network mounts, editor save behavior and large watched trees require explicit handling.

No notify dependency or copied notify source is added. The first implementation uses explicit bounded polling, ordinary filesystem reads and SHA-256. Existing native dependency families are declared (`serde`, `serde_json`, `sha2 = 0.10.9`, Unix `libc`). No package install/download or lockfile generation was performed. The new code retains the repository's GPL-3.0-or-later license.

## Modules and ownership

| Module | Responsibility |
|---|---|
| `schema.rs` | Versioned graph JSON, semantic validation, immutable graph digest, labels and read-only path preflight |
| `ports.rs` | Exact serializable command, input proof and real-owner receipt contracts |
| `scheduler.rs` | Error-atomic pure state machine, finite admission and single in-flight command |
| `ledger.rs` | Single-writer Unix journal, intent-before-dispatch, checksum-chain replay, polling checkpoint coordination |
| `poll.rs` | Bounded scan, settling, full-byte stable read, source occurrence and resumable baseline |
| `tests.rs` | Authored UNRUN fixtures; all simulated receipts are test-local |

The parent application's `WorkflowHostPort` is an orchestration/UI contract, not a wire alias for `ports::Command`. A host adapter must map them explicitly. The Rust crate has no C ABI and is not added to the Tauri manifest by this module.

## Graph v1

`Graph` is `{ schema_version: 1, workflow_id, revision, nodes, edges }`. Revision is positive and at most 2^53−1 for exact UI round trips. Node and workflow identifiers use bounded ASCII tokens. Unknown JSON fields and future versions are rejected; input JSON is limited to 256 KiB. Array order is part of the graph digest, so reordered definitions are different exact configurations even if topologically equivalent.

Each node is `{ id, error_policy, operation }`, and each edge is `{ from, to }`.

| Operation `kind` | Required fields |
|---|---|
| `directory_source` | `root`, `recursive`, `include_existing`, `extensions`, `settle_ms` |
| `managed_import` | `project_id`, `project_path`, `managed_root` |
| `path_labels` | `rules: [{ target: filename / relative_path, contains, label }]` |
| `compatible_preset` | `preset_id`, `preset_sha256`, `when_all_labels` |
| `export` | `output_root`, `recipe_sha256` |

The only v1 order is source → managed import → optional labels → optional preset → export. Three through five nodes are accepted. No neutral preset is invented for the minimal import/export graph. A selected preset with matching conditions cannot be silently omitted because its adapter is unavailable. An explicitly configured `when_all_labels` mismatch deliberately bypasses only that preset and is retained as `preset_condition_matched: false`.

The source has no incoming edge; export has no outgoing edge. Duplicate ids, missing endpoints, cycles, self-edges, disconnected nodes, fan-in, branching and unsupported node order are refused. Unknown preset-condition labels are refused. Local labels use case-sensitive substring matching on the logical original filename or relative path, with a maximum of 64 rules. They are not AI judgments, regular expressions or ERP templates.

## Path and project preflight

All paths are absolute, bounded UTF-8 paths without parent/current-directory components. Read-only preflight refuses symlink ancestors and requires all roots and the saved project file to already exist. Source/export, source/managed and managed/export roots must be mutually disjoint in both ancestor directions. This is stricter than checking string equality and prevents recursive re-ingestion. The saved project must be outside all three trees.

`Graph::validate` is pure; `ValidatedGraph::preflight_filesystem` performs actual filesystem checks. `DurableRunner::create` checks paths, and `step` repeats the check before every new command. A path preflight is **not** an OS capability, a workspace lease, an authorization grant or a race-free mutation guarantee. Import/export owners must still perform descriptor-relative nofollow checks, source proof checks, current project CAS and destination checks at their real commit boundaries.

Managed import preparation must return an actual clean saved-project guard, project revision, owned workspace lease, exact full source hash and fewer than 256 retained managed-import receipts. The commit owner must enforce the same conditions again. This core cannot relax the interactive import guard or discard receipts. The dedicated engine ingest-session bridge can impose a smaller budget (currently designed as at most 64 imports/session); the host must honor both limits.

## Exact operation identity and ports

Every command and receipt carries schema version plus the exact workflow id/revision, graph SHA-256, run id, input occurrence id, source SHA-256, project id, document id (absent only before import), node id and operation id. Operation id is SHA-256 over the identity prefix and exact operation body. It therefore also binds document revision, preparation, review report or frozen export plan when present. All receipt identity fields must match the pending original command; a response from another run, document, graph revision or node is rejected without state changes.

Input occurrence is hashed from absolute source path, relative path, full source stat and full content hash. Equal bytes in different files remain separate business inputs. Repeated exact occurrences return the retained job, not another import. The source proof carries `completion: stable_read` and five decimal stat strings in this order: device, inode, byte size, mtime nanoseconds, ctime nanoseconds. Decimal strings avoid loss through JavaScript numbers. Content identity alone is never used as business deduplication.

| Phase | Real owner responsibility |
|---|---|
| `prepare_import` | Verify clean saved project, source proof, receipt capacity and dedicated lease; return immutable preparation handle |
| `commit_import` | Execute existing managed-copy transaction, recheck source/project proof at precommit, retain idempotent receipt and exact document identity |
| `query_import` | Resolve original preparation/commit identity; never replace an unknown attempt with a new import |
| `preflight_preset` | Load exact compatible preset hash, bind report to exact document revision and expose real review requirements |
| `apply_preset` | Resolve the owner-held preparation/review receipt and apply through the actual preset/history transaction |
| `query_preset` | Read original operation/review outcome without applying it again |
| `freeze_export` | Validate actual recipe and destinations, pin document revision and immutable exact output targets |
| `start_export` | Start existing export/render ownership using the frozen plan, without inventing new collision names on retry |
| `query_export` | Return actual pending/unknown/terminal owner state and verified output receipts |

The dedicated ingest bridge uses canonical UUID request/session/managed-operation ids, whereas the core operation key is a 64-character SHA digest. The adapter must retain an immutable mapping between these identities in its own durable owner record. It must not generate a fresh UUID after a lost response. Its trusted precommit hook must compare copied bytes and full source stat/hash to `InputOccurrence`; a dispatch-time stat check or a post-mutation comparison is insufficient.

No application adapter is implemented here, and test fixture values must never be used as application successes. Missing owners must be surfaced as unavailable, not passed through or simulated.

## Genuine review and error policies

There is deliberately no `ack_review`, `approve: true`, `resume_after_review` or client-generated acknowledgment action. Preset preflight returns a report id/hash and `requires_review`. A required review without an actual owner receipt leaves the preflight operation pending and the run paused. The only next command is a query of that same preflight operation. The real preset owner must validate its retained review and return a receipt bound to the same report, document id/revision and preset hash before application can be planned. The core checks bindings but does not authenticate arbitrary JSON as a genuine review. That trust boundary belongs to the real owner adapter.

- `stop`: definitive node failure stops further dispatch across the run; the failed input is terminal. Explicit resume can allow remaining inputs but does not replay the failed mutation.
- `skip`: definitive node failure terminates only that input; the remaining inputs continue.
- `keep_continue`: supported only on a preset node and only after a definitive failure with an exact, owner-readback retained document revision. That retained revision is exported with a warning. Without retained readback, the run pauses and queries instead of assuming partial effects are safe.

Source scan failures always stop. Keep-continue on source/import/labels/export is refused at graph validation. Unknown outcomes, timeouts and transport loss never use ordinary error policy: the original pending operation is retained and only queried. A definitive owner cancellation skips that input. `stop()` is a dispatch fence, not a promise to roll back or cancel an already-started import/export. Pending work remains queryable while stopped. The host may separately use an owner's authorized cancellation API, but it must wait for that owner's real outcome.

## Durable finite scheduling

`Scheduler` is a pure reducer useful for validation and tests. **Use `DurableRunner`, not an unjournaled reducer, for real effects.** `step()` computes one exact command, validates and durably appends its intent, then exposes it to the adapter. The next `step()` while unresolved is a query, never a repeated mutation. This deliberately favors a safe pause over at-least-once dispatch when a crash occurs between intent persistence and send.

Owner receipts are validated and durably appended before scheduling advances. Uncertain journal writes fence that runner; close/reopen and read back rather than dispatching from memory. On restart, checksum-chain replay restores all admitted occurrences and receipts. Pending preparation/commit/apply/freeze/start intents remain query-only. A missing or expired owner record is unknown, not evidence that the original mutation did not run.

The journal uses an OS-held nonblocking exclusive `flock`, immutable numbered JSON records, full SHA-256 chain validation, file fsync, exclusive hardlink publication and directory fsync. It never overwrites old records. The lock survives as a file but OS ownership is released on process exit; deleting the lock to steal a live owner is forbidden. No fallback replaces exclusive publication on filesystems that do not support hardlinks.

The selected private per-run journal directory must already exist, be empty when created and be disjoint from source/managed/output trees. It is application-owned storage, not an untrusted concurrent-write directory. Unexpected entries, gaps, corrupt records or symlinks fail closed. Interrupted private staging files are never dispatched or automatically promoted/deleted, and still count toward the storage bound. If an uncommitted staging name obstructs a future append, the run remains blocked for explicit recovery rather than erasing evidence. Cross-process correctness assumes cooperating owners honor the lock; this is not tamper-proof storage against the filesystem owner.

Bounds are 256 retained input jobs, 8 terminal receipts/job, 4,096 journal records, 2 MiB/record and 64 MiB total journal storage. No eviction or silent compaction is implemented. Capacity refusal requires an explicit product-level plan, not clearing old idempotency identities and resubmitting the same photos. `seal()` ends admission; a sealed run becomes complete only after every admitted input is terminal and no intent remains. Without sealing, the bounded run may accept newly observed photos until its capacity is reached. Graph edits require a separate run/revision, never mutation of an active graph.

For an owner with a smaller finite lease, use `DurableRunner::poll_source_bounded(source, monotonic_ms, maximum_jobs)`. The bound is cumulative retained jobs, including completed/failed jobs, and must be 1–256; the ingest-session host supplies its actual 1–64 limit. A scan admits no more new occurrences than the remaining budget. Exact already-retained occurrences consume no extra slot. Surplus eligible photos remain unacknowledged in the durable checkpoint rather than being dropped, and reaching the smaller budget is not a source failure. This call does not seal the run or enlarge an owner lease. The host must seal and drain its admitted batch at its actual limit. Pending observations survive sealing/restart, but automatic lease renewal or cross-run migration is not implemented; do not silently replace the preserved baseline with a fresh ignore-existing baseline. The original `poll_source` API retains its previous global-capacity refusal behavior.

`durable_sequence()` reports the last known fully persisted record number (genesis is zero); an uncertain later write still requires recovery. `pending_effects_settled()` checks only that no scheduler intent remains and the journal writer is not fenced. It is not a host lease-release receipt. UI `effects_settled` additionally requires actual owner outcomes and confirmed workspace-lease release, even when the run status is already stopped.

## Polling and recovery behavior

`DirectoryPoller` does not spawn a thread or claim OS notifications are reliable. The host schedules explicit monotonic `poll_source` calls. The first scan establishes the baseline; `include_existing` controls whether those existing files may later be admitted. A later scan must see an unchanged source stamp for the configured 250–300,000 ms settling interval. Eligible files then undergo a full SHA-256 read, checking descriptor identity before/after and current path identity afterward. Stable size alone is never a completed-file proof.

`DurableRunner::poll_source` persists each occurrence before acknowledging it and checkpoints the source baseline, including known stat identities and acknowledgment state. Idle scans do not add duplicate checkpoints. Restart restores that baseline and starts fresh settling intervals; photos arriving during downtime are not accidentally ignored as pre-existing files. An admission persisted before checkpoint failure is deduplicated on the next scan. If the very first baseline was never durably established, no claim is made about which files arrived before or after activation.

Each poll holds an open descriptor for the original source root. Its device/inode and the currently resolved root path are compared to the saved root identity after directory scanning, after each full-byte candidate read and immediately before candidate/checkpoint publication. Acknowledgment and checkpoint creation also revalidate a pinned current root. Replacement/disappeared/symlinked roots fail before staged observations are accepted. These bounded checks do not substitute for the engine's source-proof and descriptor-relative precommit checks, and do not claim to provide a transactional filesystem snapshot.

Scan limits: 10,000 entries, depth 16, 1,024 supported-file observations, 32 candidates/poll, 2 GiB/file, 2 GiB hashed/poll, 1 MiB/checkpoint and a 60-second checked time budget. The time budget is checked between calls, not a promise to interrupt a blocking filesystem syscall. Empty files are not offered. Symlinks and nonregular image candidates are refused. Extensions are a user filter, not a claim that a file decodes successfully; the existing import owner still enforces supported formats. Polling does not read image pixels, perform inference, rename/delete source files or write originals.

The polling/journal implementation currently uses Unix stat identity and Unix locking, matching the Linux product and managed-import proof. Non-Unix durable operation fails explicitly pending a platform identity/lock adapter; portable standard-library scanning alone is not presented as completed Windows support. Network filesystem semantics and hostile path races require real platform acceptance, not assumptions from this source.

## Authored acceptance fixtures and remaining gates

`core/local_workflow/tests.rs` contains 21 authored **UNRUN** fixtures covering minimal no-preset graphs; malformed edges/cycles; future schema and unsupported policies; clean-project/256-receipt guards; independent equal-byte inputs; source/receipt identity mismatch; unknown-query-only behavior; genuine-review binding and retarget refusal; keep-continue readback; skip/stop isolation; bounded admission; exact frozen export targets and sealed completion; overlap/symlink preflight; journal reopen/exclusive locking; corrupt journal refusal; downtime baseline recovery; finite owner-budget surplus/checkpoint recovery; invalid-budget and duplicate handling; stopped-but-pending owner settlement; and replacement-root refusal against a held original descriptor.

No compiler, formatter, test runner, product import, render, inference, dependency download, installation, Git write or external coding task was run for this module. Source review is not a passed build.

Required later acceptance includes actual bridge decoding and lease mapping, save/reopen and CAS conflicts, source mutation during copy/precommit, session cap/receipt cap, every crash point around intent/send/commit/receipt/fsync, partial journal/corrupt chain, disk full, permissions, unmounts, hardlink refusal, root replacement, symlink races, repeated events, stop during import/export, owner receipt loss, genuine review expiration, output collision/no-overwrite, graph edits during run, multiple concurrent owners and real supported-image import/export. End-to-end UI availability must remain gated until those owners are wired and their behavior verified.
