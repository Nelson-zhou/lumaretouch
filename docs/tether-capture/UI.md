# Tether capture UI and host contract

Status: source implementation only. No build, typecheck, tests, product imports,
device operations, downloads, installation, inference or Git writes were run in
this task. Hardware compatibility and end-to-end application wiring remain
unverified. The panel never substitutes demonstration data for a real runtime.

## Scope and files

- `ui/src/tetherCapture/protocol.ts`: versioned UI/host ABI and actual receipt DTOs.
- `ui/src/tetherCapture/model.ts`: format restrictions, naming checks and gates.
- `ui/src/tetherCapture/controller.ts`: async identity, lifecycle and receipt fences.
- `ui/src/tetherCapture/TetherCapturePanel.tsx`: accessible Chinese-language panel.
- `ui/src/tetherCapture/tetherCapture.css`: isolated panel styles.
- `ui/src/tetherCapture/index.ts`: public exports.

This directory does not import shared application APIs, native bindings, camera
drivers or product import functions. Parent integration supplies the real
`TetherHostPort` and owns the managed-file importer. No dependency is added.

## Workflow reference

The workflow was checked against the official desktop wired-capture guide:
<https://www.pixcakeai.com/guide/47251> (read 2026-10-25; page updated 2026-09-18).
The reference informs these controls, not camera compatibility claims:

1. Choose an actually detected device and inspect connection/capability status.
2. Verify the selected device explicitly, without taking a picture or changing
   any camera setting.
3. Select the destination using the host's real directory picker, choose an
   import format, and choose one of the five naming patterns.
4. Start receiving files, use the camera's physical shutter, inspect actual
   transfer/import states, and stop the session explicitly.
5. Follow the latest successfully imported document or keep the current document.
6. Expose optional live view and remote shutter only where the runtime actually
   declares those operations. First-use labels distinguish advertised from
   verified support. A remote capture always requires an explicit button click.

Known RAW+JPEG recording enables all three import options. Known RAW-only or
JPEG-only recording enables only its matching option. If a driver cannot identify
the camera's recording setting, the UI says so and offers only receive-all:
`import_format = raw_jpeg` means retain actual supported RAW/JPEG objects, not a
claim that both exist. Single-format selection is disabled in that case. No
missing companion file is fabricated. If recording settings change on the
camera, stop and reverify before starting a new frozen session.

Synchronizing previous edits, applying presets, overlays and AI culling are
explicitly pending; there are no decorative controls pretending to implement
them. This panel issues no camera-setting writes, delete requests or image-edit
operations. Its acknowledgments are transport receipts, never UI/pixel-review
ACKs or claims of image quality.

## Parent integration

Render `TetherCapturePanel` with a stable port object. With no port, the component
renders an honest unavailable state. Do not create a new port on every render.
Replace its immutable `host_id` when the runtime itself is replaced. A panel
unmount unsubscribes only; it does not silently stop a camera or forget a request
on the host. The host must own session lifetime outside the panel.

Required port methods:

- `readSnapshot()`: actual devices, session, transfers and unresolved requests.
- `subscribe(listener)`: fresh snapshots, actual import notifications and actual
  live-view frames. Unsubscribe must prevent further observer delivery.
- `pickDestination()`: real system directory picker; returns a host-owned opaque
  destination token plus display path, or null on user cancellation. Do not
  accept an arbitrary UI path as proof of authorization/writability.
- `send(request)`: one command carrying host, request, revision and session
  identities. Record the identity durably before any operation can execute.
- `queryReceipt(requestId)`: strictly read-only lookup of that original request.
  Null does not prove non-execution and must never trigger an automatic resend.

The `onImportedDocument` callback is an optional navigation/refresh notification.
It receives a host-issued completed import receipt plus `make_current`. The host
already imported the file before emitting it. The callback must not import the
same file again or acknowledge pixel review. `keep_current` always reports
`make_current: false`; an unresolved preview-mode change also suppresses focus
changes. Host/application integration must preserve idempotence across panel
remounts and must not replay historical notifications as new captures.

### Saved-project admission

`snapshot.ingestion_target` is required (and explicitly null when absent). It
identifies the actual saved project using `project_id`, `path` and `name`, plus
real `available`, `reason` and `remaining_operations` admission state. The UI
shows the project identity/path before start, and refuses missing, unavailable or
exhausted admission. Start echoes `project_id` and `path` as well as the expected
snapshot revision. The host must compare its private workspace/disk-digest binding
and obtain an engine ingestion lease; it cannot silently choose whichever project
happens to be open when an asynchronous callback arrives.

Freeze the admitted target in `session.ingestion_target`. Import receipts include
`project_id` and `project_path`, checked against both that frozen target and the
transfer's completed receipt. A changed current target produces a visible warning,
blocks new capture/retry requests, and suppresses follow-latest navigation. It
never switches the currently edited project. The host must enforce actual lease
bounds (at most 64 operations per engine lease, with the engine's remaining
operation budget) and preserve the user's current editing/library context. The UI
displays the budget; it does not mint, renew or fabricate engine permission.

### Low-level native mapping

Native `DeviceId { model, port }` becomes a stable host `device_id` only after
fresh detection. The native `Support` values map to `unknown`,
`driver_advertised`, `verified`, `unsupported`; keep the operation-specific
reason. Never convert a camera brand/model list into verified support.

Native event polling and original-download support are separate capabilities.
The start gate requires connected/freshly detected device, verified event polling
and advertised or verified original download. `probe_device` provides the
bootstrap step: bounded open, capability/settings read, one bounded event poll,
close. It performs no shutter action, original download or settings write. An
event timeout can verify only that the polling API worked, not that a physical
shutter generated a file. The host must clean up failed probes and scope verified
evidence to the relevant runtime/device connection.

`FileAdded(CameraObject)` is not an imported document. The host must download the
actual camera object into bounded, exclusively allocated managed storage, verify
size/hash/type, and use the real importer. Camera object folders/names are opaque
device identifiers, never local filesystem paths. A local filename must be
sanitized and collision-safe, with original extension and bytes preserved.

The five naming modes are `custom_counter`, `custom_filename`, `date_counter`,
`date_filename`, `original`. The host defines and freezes its date/time-zone and
counter-allocation policy per session; it must never overwrite an existing file.
UI naming validation is advisory and does not replace native path validation,
exclusive allocation, reserved-name checks or maximum-length handling.

### Snapshot and receipt invariants

- `protocol_version = 1`; `host_id` must match the port.
- `revision` increases monotonically for the whole host lifetime, including
  session replacement; equal revisions identify immutable identical snapshots.
- Every replacement session has a strictly newer `generation`. An old session
  cannot become active again after stop. Publish a new generation instead.
- Requests bind `expected_revision`, `expected_session_id`, and
  `expected_generation`. The host must validate them before action. Receipts echo
  the original identity even when `start` creates a new session.
- Persist unresolved requests in `pending_requests`, including requests whose
  response was lost. Resolve them using their original immutable identity. A
  missing entry or transport failure is not proof that a command did not run.
- A terminal receipt has `phase = done`, `outcome_unknown = false`, and a real
  `success` boolean. Return a fresh authoritative snapshot when possible.
- Stop invalidates producer callbacks before terminal success and cleans up the
  actual camera/live-view resources. Old-generation downloads/import callbacks
  must not attach documents or display frames in a newer session.
- A completed `imported` transfer carries an actual `imported_document` receipt
  containing document ID, managed path, bytes and SHA-256. The UI checks that an
  import event matches that same current-session transfer before notifying the
  application. A download receipt alone cannot set `phase = imported`.
- `retryable` can be true only for a confirmed failed, safely repeatable transfer.
  The UI allows retry only in the same active session. An unknown download or
  import outcome must be queried/reconciled, never retried automatically.
- Byte counts are measured values only. Omit unknown totals; the UI shows no
  percentage when total size is absent or inconsistent.
- Live frames require host/session/generation identity, increasing sequence,
  actual positive dimensions and a host-owned blob URL or base64 JPEG/PNG/WebP.
  Supply a verified live-view capability before emitting a successfully captured
  frame. The host owns object-URL lifetime and must revoke it when no longer used.

The controller rejects stale revisions/generations, suppresses stopped-session
resurrection and detaches all late observers after unmount/host replacement.
When an asynchronous mutation times out after 12 seconds, its identity remains
pending and only its read-only query is offered. There is no resend, local
"discard unknown outcome" button, speculative success state or fabricated
receipt. Stop intent immediately suppresses further import/navigation and frame
notifications while the host reaches its actual terminal state.

## Acceptance plan (UNRUN)

Source was manually inspected only. These checks still require separately
authorized execution with a real host, actual hardware and final app wiring:

1. Missing runtime, missing device, disconnected device and unknown capability
   show truthful unavailability without samples, simulated images or timers that
   generate transfer progress.
2. Advertised device capabilities can be explicitly probed without a shutter,
   download or setting write; polling timeout is not mislabeled physical-shutter
   verification. Probe failures release resources.
3. RAW-only, JPEG-only, RAW+JPEG and unrecognized recording-setting cases show the
   correct format restrictions. Unrecognized mode receives only actual files.
4. Cancel the real folder picker; no directory changes. Change session while the
   picker is open; stale selection is discarded. Check collision-safe naming,
   Unicode, path separators, reserved names and original extension preservation.
5. Double-click start/probe/capture/retry. One request is sent; pending requests
   block all later mutations. Verify original camera files remain unchanged.
6. Lose or delay a mutation response beyond 12 seconds. The original request ID
   remains visible. Null/wrong-identity/pending/unknown query results never cause
   a resend or unlock the mutation barrier.
7. Remount or replace the panel while requests are in flight. The host mailbox
   restores unresolved identities; obsolete results cannot update the new host.
8. Capture physically, transfer real bytes, validate and import once. Download
   success alone is not import success. Verify multiple RAW/JPEG objects and
   repeated file events do not duplicate document imports.
9. Receive imported callbacks out of order or after stop, session replacement or
   unmount. Only current-generation completed imported receipts may notify the
   current application, and duplicate receipt IDs do not refocus the image.
10. Change follow-latest/keep-current during an import. Keep-current and pending
    mode changes never move the current selection. Reopening the panel does not
    jump to historical captures.
11. Remote capture/live view are absent for unknown/unsupported capability. First
    advertised use has an explicit trial label and is never auto-triggered. Only
    actual session-bound frames appear; wrong generation or old sequence drops.
12. Disconnect during transfer/live view; stop still remains a cleanup action
    even when runtime availability is false. Unknown commands remain query-only.
13. Confirm failed transfers can retry only when the host asserts a known safe
    retry. Unknown outcomes and other sessions cannot retry. Inspect source
    preservation, managed-storage boundaries and importer idempotence.
14. Verify keyboard focus, select labels, status/error announcements, long
    filenames/path wrapping, narrow panel layout and real thumbnail/full-image
    review. No screenshot, build result or device compatibility is claimed here.
15. Save a project, inspect its visible identity/path and admission budget, start,
    then switch or externally modify the project. The original binding must be
    rejected or paused by the host/engine, never redirected to the new project.
    Expired/exhausted admission blocks capture/retry/start; stopping remains
    possible. Import events for a different project cannot change selection.
