# Module preset workflow: implementation contract

Status: backend-only candidate, not yet executed. Native receipts and the mounted
preset UI are still to be implemented. Existing LUT looks remain separate.

## Backend module boundaries

`preset_controller.py` owns catalog/operations/receipts behind narrow callbacks;
`preset_store.py` owns validated disk storage; `preset_transaction.py` owns image
apply/rollback. Engine retains dispatch/history integration, not duplicated preset
business logic. Legacy command/event behavior remains available.

New callers use `request_id` (1–128 UTF-8 bytes), action and action-specific fields.
Ready advertises `preset_result_protocol: 1`. Apply/save require the active
`DocState.document_id` (Engine load ID, not a batch-row UUID). Save requires a
nonempty explicit module-scope string array and name. Unknown fields, nonboolean
force, empty scope, non-finite JSON and commands over 64 KiB are rejected.

Terminal `preset_result` follows history recording, not just queue acceptance or
`command_done`. It includes protocol, request ID, action, boolean success and
outcome_unknown. Apply/save echo document identity. Successful apply contains the
post-history document state. Every changed preset apply is a distinct undo step;
no-op/replayed operations do not add steps. Apply failure attempts rollback;
rollback failure invalidates the image cache and reports requires_reload.

Within one engine lifetime, identical retained IDs return the cached result,
without mutation; changed arguments reject. The cache is bounded to 64 receipts
and 16 MiB serialized accounting, with 8 MiB per result. UTF-8 validity and actual
ASCII-escaped stdout encoding are checked. This is NOT permanent exactly-once
execution: eviction/restart removes deduplication. Recovery must query the native
receipt mailbox for the SAME request, never resubmit uncertain mutations.

Storage uses a unique same-directory temporary file, fsync, atomic no-clobber
link for ordinary saves, and replace only with explicit force. The parent
folder is fsynced after save/delete. `operation_committed` is tri-state: true
means the mutation syscall completed, false means definite pre-commit failure,
null means the commit syscall itself is uncertain. Durability failure may be
outcome_unknown even when operation_committed is true. Cleanup errors cannot
turn a confirmed save into an automatic retry. Imports pin a nonblocking file
descriptor, reject non-regular files and enforce a bounded actual read as well
as the initial file size. No executable preset content is run.

## Required native/UI stage, not completed here

- Epoch-bound bounded receipt mailbox, advertised protocol capability gate,
  register-before-enqueue and query-only uncertain recovery.
- Application-lifetime workflow ownership, independent of tool-panel mounting.
- A reachable module-preset panel with name, explicit module checkboxes, stored
  scope preview, stable IDs, real save/apply/import/delete outcomes.
- Builtins protected; exact-identity delete confirmation; no automatic force on
  import/name conflict. Selected preset is not proof it was applied.
- Retain form data on failure/uncertainty; don't erase text edited after submit.
- Apply/save require an editable photo; list/import/delete do not require one.
- Refresh failure must not change a successful mutation into failure or retry.
- Existing old StudioPanel controls are not proof of completion: that panel is
  not mounted. Existing PC-32452 renders LUT looks, not this new workflow.

## Tests added, awaiting execution

Controller malformed/stale commands, cache replay/count/byte bounds, wire byte
limits, disk/error outcomes, apply rollback and separate undo steps; real
synthetic-image protocol runs both legacy and correlated paths through pixels,
SHM, save/apply, undo, project reopen, stale rejection and no-mutation replay.
Storage tests cover no-clobber races, unique temporary names, replacement,
write/commit/durability errors, descriptor-pinned pathname replacement and
bounded growth/FIFO rejection. Root has not run these tests; Qoder/CI own execution.

## Official implementation references

- [Python os.link](https://docs.python.org/3/library/os.html#os.link) and
  [Linux link(2)](https://man7.org/linux/man-pages/man2/link.2.html): create a new
  directory entry without replacing an existing destination; failures may need
  reconciliation on some filesystems, so uncertain writes are not retried.
- [NamedTemporaryFile](https://docs.python.org/3/library/tempfile.html#tempfile.NamedTemporaryFile):
  unique temporary name, not a predictable `<id>.json.tmp` target.
- [Linux fsync(2)](https://man7.org/linux/man-pages/man2/fsync.2.html): file fsync
  alone does not ensure the containing directory entry is durable.
