# Workflow engine owner bridge (source-only implementation)

## Supported boundary

The v1 bridge supports the native core's actual directory source → managed-copy
import → optional path labels → per-document export. Managed-import errors must
use the `stop` policy: the genuine ingestion lease stops on failed/cancelled
imports, so pretending `skip` could advance another file would be unsafe.
It does not switch the active
editor photo, modify a saved image recipe, save an unrelated project, fabricate
preset reviews, or implement another renderer. Imports remain native-host calls
to the existing `ingest_session` owner. The engine export bridge admits only
`freeze_export` and `start_export` core commands after a successful graph preflight.

A graph containing `compatible_preset` fails preflight before the native host may
start ingestion. The established preset controller requires a loaded target and,
for review-dependent modules, a real target-image review and its exact owner
receipt. This saved-project lease forbids arbitrary photo switching. There is no
safe immutable preset transaction under this lease in this version, so no preset
is silently skipped and no client acknowledgment is accepted. `open_review` does
not pretend to open a nonexistent review.

## Exact engine envelopes

All commands use `cmd: workflow_owner`, integer `protocol: 1`, a canonical UUID
`request_id`, no unknown fields, and at most 1 MiB of transport JSON.

- `profile`: the base fields only, no session. Read-only profile discovery.
- `preflight`: base fields plus `session_id`, `graph`, `graph_sha256`.
- `execute`: base fields plus `session_id`, `command` (the exact Rust core Command).
- `query`: base fields plus `session_id`, `original_request_id`, `operation_id`.
- `open_review`: base fields plus `session_id`, `operation_id`, `review_id`.

Events are `workflow_owner_result`, with protocol, request/action/session identity,
status, and `runtime_verified: false`. Profile/preflight return `recipe_sha256` and
`recipe_profile`. Preflight adds `supported` and diagnostics with severity/code/
message. Execute and known query return the exact core Receipt in `receipt`.
A query whose original receipt is not retained returns outer `unknown` without a
fabricated core identity; the native adapter retains its original Command and must
keep its intent unknown. It must not retry a mutation or manufacture another key.

Graph and command hashes reconstruct the precise Rust serde DTO field order,
including tagged operation fields. They are not alphabetically sorted JSON.
`recipe_sha256` is a separate, alphabetically canonical profile fingerprint.

## Explicit export profile

`lrt.workflow-export.jpeg-srgb.v1` uses the genuine existing export command:

- JPEG, quality 95, RGB8, sRGB output; tile 1024.
- Scale 1, Lanczos3 selected but not used for enlargement, sharpening 0.
- No GPS, watermark, layout, or target-size conversion.
- The pinned chosen output root must already exist, with no retained hierarchy.
- Destination collision policy is `ask`; no implicit rename, skip, overwrite,
  acknowledgment, or directory creation. A conflict prevents starting the output.
- The legacy `conflict_policy` option remains `skip_and_report`, but the real
  destination plan is mandatory and its stronger exact-target no-clobber runtime
  governs writes. Any non-write plan disposition is rejected before queueing.

The current canonical profile SHA-256 is
`e46986eeec5dcd36761027317365c1989963d0e6c4221c3101bf0644f6d48ca5`.
The UI must obtain it from the engine's profile read and let the user deliberately
pin that returned profile. It must not guess a hash or silently replace the graph.
This is an export-settings profile, not a hash pretending to describe all future
images: each image's genuine saved recipe is separately encoded, compared,
stamped, and frozen by the existing export implementation.

## Ownership and genuine receipts

1. Preflight verifies an existing `owner: workflow` ingestion lease, saved clean
   project identity/disk fingerprint, exact graph digest, and disjoint watched,
   managed-original and output roots. No symlink ancestor or missing root is
   accepted. The project file must be outside those roots. The output directory's
   actual nofollow-opened descriptor device/inode is captured at successful
   preflight and retained for the session. Later preflights/execution recheck the
   original pin rather than rebasing it onto a replacement directory.
2. Each export document must resolve to a successful managed import operation
   owned by that exact session. The bridge re-reads the real persisted import
   receipt, source hash/stat, provenance, document revision and immutable source
   identity. The original path/stat/hash must reproduce the core occurrence hash.
   The document receipt ID must be the genuine ingestion operation UUID.
3. The active saved recipe version is compared with the established project
   codec's lossless encoding of the actual row recipe. The imported row cannot be
   the active editor row. Current editor parameters never substitute for it.
4. Freeze calls `Engine.cmd_export(action=preview)` through an in-process,
   observation-only `trusted_result` callback. The real destination planner's
   payload and per-document recipe stamp are retained. Targets are never guessed.
5. Start revalidates the same row, graph/run/source identity and original plan,
   then invokes the real `Engine.cmd_export(action=start)` once. It retains the
   unique actual export task ID, even when dispatch raises after task admission.
   The unchanged output-root descriptor pin crosses the internal
   `trusted_destination_roots` port into real task options. The canonical output
   commit checks its actual parent descriptor and pathname before temporary-file
   creation and again before publication; an async root replacement cannot adopt
   a new directory merely because its text path is unchanged.
6. Query inspects only that original task and its immutable `_task_args`, exact
   destination payload, original destination-root pin, document/source identities
   and terminal item receipt.
   Success requires a completed real worker, successful actual item, exact frozen
   path and full nofollow byte-hash readback of the exported file, with the
   original output directory identity rechecked before and after reading. A task whose
   worker disappeared without a terminal receipt remains unknown. Query emits
   the original execution's terminal receipt before its separate readback event,
   so the native original-write fence is settled by real engine evidence.
7. Partial outputs, lost task identity, or uncertain receipt/readback remain
   unknown. No retry is issued and the lease remains held. Post-admission failure
   without an output does not prove that no output was ever committed.

An exact, structurally validated core command rejected by pre-dispatch lease,
source or directory admission retains a definitive typed Failed receipt; it does
not become an unrecoverable bare-error/unknown query loop.

Mutation receipts are never evicted (256 owner operations; 64 graph preflights).
Repeated exact operations replay their retained receipt without another dispatch.
A different transport request ID cannot re-run the same operation. A lease is
bound to one graph and one run. Pending/unknown export prohibits releasing the
lease, starting another import, editing, or issuing another output mutation.

## Integration hooks

Parent-owned shared integration:

- Add `workflow_owner` to the command registry and ready protocol advertisement.
- Route `cmd_workflow_owner` to `workflow_owner_host.handle(engine, payload, emit)`.
- Call `workflow_owner_host.guard_command` before the existing ingestion guard.
- `IngestSession.blocks` may admit only `workflow_owner` envelopes for which
  `workflow_owner_host.ingest_passthrough` returns true. This is not a generic
  workflow bypass, and all other pending subsystem guards remain in force.
- Dispatch the command before ordinary history/capture invalidation and exempt it
  from project-recovery recipe-taint bookkeeping, just as ingestion is exempt.
- `dispatch_rejected(engine, payload, error, started, emit)` reports a correlated
  `dispatch_rejected: true` only when the original handler was not entered and
  no retained exact operation exists. Existing operation receipts take precedence;
  missing state after handler entry is unknown, never an invented rollback.
- `cmd_export(..., *, trusted_result=None, trusted_destination_roots=None)` emits
  its normal exact reply first and sends a deep copy to this internal callback. It is not a JSON parameter and does
  not replace validation, planner, renderer, atomic output or queue ownership.
  The unchanged root mapping is retained as `_trusted_destination_roots` in both
  task inputs and task arguments; query verifies both copies before readback.

## Verification status

Only source reading, Python AST parsing, literal extraction and file hashing were
performed in this development pass. The isolated test file is deliberately named
`test_workflow_owner_contract_unrun.py`; it was authored but not run. No engine
imports, product execution, image decoding/rendering, models, dependencies,
builds, typechecks, Git operations or runtime tests were performed. End-to-end
import/export acceptance and real image output remain unverified.

Post-admission export failure/cancellation without a full successful output
receipt remains **unknown**, even when the target path is absent. The existing
writer can commit before a later metadata read fails, and another actor may
move/remove that file. No affirmative never-committed task bit exists. The
bridge must not call that rollback or allow automatic retry/release. Definite
pre-dispatch validation refusals remain retained Failed receipts. This is a
known recovery limitation, not claimed complete cancellation support.
