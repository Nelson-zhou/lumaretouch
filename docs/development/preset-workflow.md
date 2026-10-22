# Module preset workflow: implementation contract

Status: integrated c1afbf7 passed the basic CI checks recorded below; local Qoder
and physical acceptance remain open. No-photo protocol coverage is being extended.
Backend-only cd96304 has CI evidence below; this is not physical acceptance.
Existing LUT looks remain separate.

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

## Native/UI implementation

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
- The application-lifetime hook is mounted in App; PC-32452 now renders the
  module-preset panel alongside the existing LUT block. The unmounted old
  StudioPanel is not used as completion evidence. Legacy P0 string-label adapters
  reject ambiguous matches rather than applying the first matching preset.
- A status ticket/revision fence is rechecked after asynchronous filmstrip reads;
  an older refresh cannot restore prior-document controls after a newer accepted
  refresh. Explicit workflow refresh errors propagate without changing a confirmed
  mutation outcome. Receipt doc_state is never installed directly.

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


## Verified backend baseline and remaining checks

Remote `cd96304bc3369715876d83184a02fd09d79d98a4`, tree
`d0b0979f4f22eb99b8509b9ca3f740faaac57094`:
[CI 39712807553](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39712807553)
passed all non-GPU jobs. Engine: 1120 passed, 428 skipped, 72.06s. Frontend:
147 passed, zero failures/skips. GPU jobs skipped. This CI did NOT exercise the
new two-case real HSL/preset protocol: its environment lacked Torch and those
cases use importorskip. Do not count the skipped protocol as a pass.

Qoder fetched and verified the exact detached candidate but local helper/pytest
never ran: its chat was not bound to the product workspace, and the artifact Write
was denied. The task was paused without a shell bypass. Project binding is awaited.

The integrated candidate adds a dedicated CI step installing the official pinned
CPU-only Torch 2.10.0 wheel AFTER the existing lightweight suite, then running the
real preset protocol cases. It checks wheel identity and JUnit count with no
skips/failures/errors; evidence is retained as an artifact. This does not replace
local Qoder or physical UI/GPU/performance acceptance. No local dependency change
is performed by this workflow.

Official references for the UI/CI additions:
- [Tauri dialog](https://v2.tauri.app/plugin/dialog/): native file selection and
  explicit destructive-operation confirmation, using the already-present plugin.
- [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/):
  official 2.10.0 CPU-only index. Only torch is needed for these synthetic image
  cases; torchvision/torchaudio and GPU wheels are not installed.


Integrated `c1afbf7fb91e6eaa46827ec61c73a89d67a4bb8c`, tree
`24a3ff0ba0ac8560b30fd82fe84a943be46baddf`, passed
[CI39715962929](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39715962929):
frontend166/0skip, TypeScript/build, Rust checks and five preset-host plus five
batch-host tests. Engine lightweight suite1122 passed/428 skipped/41.94s;
separate pinned Torch2.10.0+cpu run: both real synthetic-image protocol cases
passed/0skip in2.71s, with exact count enforced and JUnit retained. All non-GPU
jobs passed; GPU jobs skipped. Qoder local execution remains blocked before tests
by project binding, not represented as a pass. Desktop installation unchanged.

The next coverage increment adds a third real protocol case without an open
photo: list, import, conflict without overwrite, import as a new ID, builtin
protection, delete, missing-file rejection and final catalog/disk evidence.
This added case is not yet executed as of this edit. A positive result must not
be inferred from c1afbf7's two-case run.
