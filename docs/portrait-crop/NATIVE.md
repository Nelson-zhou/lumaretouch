# Portrait crop dedicated native transport

Status: **AUTHORED / UNRUN**. Source-only implementation and synthetic fixtures.
No product imports, builds, type checks, tests, inference, image rendering or UI
execution were performed for this change. No real-photo acceptance is claimed.

## Registration contract

The parent application registers `portrait_crop_api` and `portrait_crop_protocol`
and the following Tauri commands:

- `portrait_crop({ request })`: immutable exact engine request, sent at most once.
- `portrait_crop_status({ original })`: exact retained original request. Native
  creates a separate `portrait_crop` / `status` request with a fresh query ID and
  `target_request_id`; it never sends the original mutation again.
- `portrait_crop_cancel_read({ original, command_sha256 })`: snake-case arguments.
  Only a retained dispatched `current` or `preview` can be cancelled, using the
  digest received from the actual server, never a client-side substitute.

Initial send and status wait on a condition variable in a blocking-worker task
for at most four seconds. They return a genuine server receipt, or an error if
none is available. Timeout, failed invoke, process death and missing receipt are
not proof of no write. UI transport may poll status without reissuing a command.
The engine normally emits `unknown` immediately before the apply boundary;
status-only polling can recover its real terminal without resending apply.

Engine integration must call:

1. `reset(epoch)` at process creation, then `ready(epoch, hello.portrait_crop)`.
   The capability is the exact host object, not a lens protocol surrogate.
2. `blocks_mutation(epoch, command)` on ordinary and interactive send paths.
   `read_only(command)` prevents current/preview/status/cancel from creating a
   generic mutation/recovery fence or coalescing with editing commands.
3. `enqueue(handle, envelope)` in the shared native apply dispatch path. Its
   private `host_epoch` tag is removed before stdin. The one-shot registration
   must match the full retained request and engine epoch.
4. `observe_line(epoch, original_line)` before generic JSON parsing or recovery
   settlement. Only a validated original terminal yields the internal `done`
   marker. `guards_result` prevents ordinary events from settling retained IDs.
5. `ended(epoch)` on process termination. It never translates EOF into rejection,
   cancellation, an undo operation or permission to repeat an old mutation.
6. `EngineHandle::cancel_portrait_crop_read(id, server_digest)` writes exactly
   `{cmd: "portrait_crop_cancel", request_id, command_sha256}` through the shared
   `EngineInput` mutex and closes the writer/dispatcher on uncertain write or
   flush failure. Its ingress acknowledgement is not cancellation completion.

## Authority and receipt validation

The complete echoed `original_request` and pinned server `command_sha256` are
required on working and terminal receipts. Rust uses a separate local signature
only for identity collision/replay detection. It does not pretend that its JSON
number formatting is Python canonical serialization. Raw JSON with duplicate
keys, trailing content, oversized content or nonfinite values is rejected.

A successful current capture binds document ID, revision, workspace epoch,
load ID, original/derived source provenance, whole state, non-crop edits, people,
repair state, fresh proxy/model analysis, genuine face IDs and uncropped edited
raster hash. All image payloads require complete bounded RGB PNG bytes, canonical
base64, content SHA-256, chunk CRCs, one header, contiguous image data, final IEND,
no trailing content/APNG and whole-frame aspect/dimension mapping.

The measurement image is the entire current edited **uncropped** source. The
`before` image is the complete **already-edited, already-cropped** current photo.
They are separately retained and must not be substituted for each other. Native
accepts a preview only when its before-image proof is exactly the captured
before proof, its after image is the complete actual crop output, and its source,
selected real face, confirmed crown/chin/center, explicit rules, backend,
continuous geometry, canonical integer bounds and achieved ratios agree.
A partial viewport, overlay rectangle or screenshot cannot stand in for these
full before/after images. PNG decompression, visible presentation and actual
full-resolution canonical rendering remain distinct host/UI acceptance gates.

Apply requires the current capture, an unconsumed matching preview ID/token,
full before/after image digests, exact candidate state digest and explicit full
photo review. Preview authority is consumed before queue/write uncertainty.
Committed receipts must name the same document and candidate, with exactly one
canonical revision advance for applied, or unchanged revision/state for no-change.
No new-copy mode, other algorithm's session fields, new renderer, history writer,
project recipe or export pipeline is introduced here.

## Unknown outcomes and canonical reopen

An unresolved apply fences editing, undo, save and export. Only original-status
query, hello/shutdown and narrowly named canonical recovery operations remain
available. A different request ID, closed panel, navigation, rejected cancel,
read timeout or capability result cannot release this fence.

An explicit canonical project reopen is an escape from the *old workspace*
fence, not proof of the old mutation outcome. Native records a prior project
open/create/new or recovery restore ingress. The raw duplicate-key-safe event
must then be `project_opened` or `project_created` in the same live engine epoch,
with `open: true`, a bounded nonempty path, project ID, unsigned document count,
boolean dirty state, and no error/unknown/reload/readback failure flags.
The already-parsed `project_reopened` integration hook only wakes waiters; raw
`observe_line` is the authority and cannot be bypassed by duplicate-key JSON.

For a still-unknown retired request, status returns this separate native wrapper:

```json
{
  "workspace_reopened": true,
  "authority": "native_verified_project_reopen_v1",
  "original_request": "the exact retained request object",
  "outcome_unknown": true,
  "authoritative_event": "the actual verified project event object",
  "message": "Old historical outcome remains unknown; do not replay."
}
```

The explanatory strings above stand for objects in the real wrapper. There is
no server `phase`, `event` or fabricated command digest. The UI handles this
explicit recovery acknowledgement separately, retains historical uncertainty,
and may clear only its old workspace edit lock. A real retained terminal always
wins. Ordinary context changes alone do not generate this wrapper.

## Bounded retention

The mailbox budgets 128 MiB for receipts/reservations, at most 512 rows and 128
write receipts. Read/status responses reserve 24 MiB; other records reserve
256 KiB. Session proof excludes base64. Current image leases last at most 600
seconds and previews at most 180 seconds, bounded by their current session.
A maintenance thread releases idle image payloads. Expiry does not fabricate a
new server refusal or rerun the read. Old read rows can be removed, but their
identity tombstones remain (16,384 IDs / 8 MiB limit). Capacity exhaustion fails
closed. Unresolved and completed writes are not evicted to admit another write.
Status wrappers are not recursively stored or allowed to duplicate large images.

## Future verification

`portrait_crop_protocol_unrun.rs` and inline mailbox fixtures cover malformed
JSON, exact request fields, genuine digest pinning, complete PNG/hash/CRC,
uncropped-vs-cropped-before identity, geometry/provenance, terminal revision,
one-shot ingress, status-only settlement, late terminal immutability, read
retention, epoch boundaries and authoritative-reopen semantics. All are UNRUN.
Still required: Rust compile and test runs, UI type checks, end-to-end real photo
capture/face analysis, actual full-before/after visual review, cancellation
unwind, queue/EOF/reopen races, history/undo/project/export verification,
performance and memory observation on the supported product build.

The reopen acknowledgement deliberately does not reconcile an old process epoch.
If the original engine has ended or restarted, its unresolved write stays an
unresolved historical outcome; a new engine is not queried as if it owned that
write. Recovery beyond that boundary requires the explicit application/project
restart workflow, not a synthetic failed/cancelled receipt or automatic replay.
