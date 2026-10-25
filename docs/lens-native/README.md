# Lens native protocol 2 mailbox: AUTHORED / UNRUN

This source lane adds only:

- `ui/src-tauri/src/lens_blur_api.rs`
- `ui/src-tauri/src/lens_blur_protocol.rs`
- `ui/src-tauri/src/lens_blur_protocol_unrun.rs`
- `docs/lens-native/`

It is a dedicated Tauri request/status/read-cancel/capability boundary, not an
image renderer, depth model, source importer, document publisher, file exporter,
or independent history implementation. Genuine pixels and new-image publication
remain owned by the serialized Python lens host and its common creative host.
No local product, import, test, build, typecheck, inference, model download,
dependency installation or Git write was executed for this lane. Test names and
fixtures describe expectations, not passing evidence. Rust compilation and
photographic acceptance remain open.

## Transport and exact UI contract

The inner command and returned context/review/write receipt match
`ui/src/lensBlur/model.ts` protocol 2. Recipe and depth versions remain 1, and
the operation ID remains `lnx.lens_blur.v1`. Revisions are decimal u64 strings,
not rounded JavaScript numbers. Unknown/missing/extra fields reject.

Tauri invocation names/arguments:

- `lens_blur_capability()` returns exact `LensCapability`: version, operation_id,
  status, kernels, reason. Available means the matching current engine actually
  advertised known native kernels, not that AI depth exists or quality passed.
- `lens_blur_request({request})` accepts an exact outer engine envelope.
- `lens_blur_status({requestId})` reads only the retained native mailbox; it does
  not contact the engine, recreate missing pixels or replay the original action.
- `lens_blur_cancel({requestId})` requests cancellation only of an admitted,
  dispatched `current`, `prepare_manual_plane` or `preview` read. It returns
  `{requested, request_id, message}`. Requested is not a cancellation receipt.

Outer envelope:

    {cmd: "lens_blur", action, request_id, command?}

`current` has only cmd/action/request_id. `prepare_manual_plane` and `preview`
include the matching exact inner protocol-2 command with the same request ID.
`submit` includes an exact inner apply or cancel command and the same ID.
`receipt` includes the unchanged original write command but a fresh outer query
ID, distinct from command.request_id. This is authoritative readback, never a
resubmission. It is admitted only against the complete original native write
in the same engine epoch. A query can reconcile that original unknown outcome.

Each native result is an outer `lens_blur_result` event with its transport
request_id. Read pending/unknown results have status and message. Read terminals
use exact host ready/context, ready/review, rejected/message or cancelled/message
shapes. A current capability refusal has context:null and message.

Write and query responses have `{event, request_id, status:"ready", receipt}`.
The inner receipt is the exact LensReceipt: phase pending/unknown (not terminal)
or done with rejected/cancelled/applied. A completed query returning unknown is
evictable as a query result, but the original unknown write remains pinned and
fenced. An unavailable local status without the original command is only an
outer unknown, never an invented matching terminal. Invalid input, identity
collision and pre-admission capacity failure throw without dispatching.

## Evidence and publication boundaries

Current source capture must return a real bounded full-frame PNG, immutable
full-grid source SHA-256, exact document/epoch/revision owner and session. The
native boundary verifies canonical Base64, PNG signature, exact IHDR dimensions,
CRC for every chunk, bounded contiguous IDAT structure, final IEND, and whole
PNG byte SHA-256. It does not claim to inflate or perceptually inspect those
pixels. The existing host encoder and UI decode/presentation gates still apply.

There is no implicit depth or AI fallback. The accepted host path requires an
explicit prepare_manual_plane action with acknowledged_manual:true. Native
validates owner, the returned acknowledgement ID, depth_value, full-frame u16-le
byte count/hash, and every sample against floor(depth_value*65535 + .5). Model
provenance, subject focus and an unrequested supplied-depth substitute are not
accepted by this host lane. This does not rewrite the broader saved UI format.

A preview must match retained owner, session, source-image hash and dimensions,
manual-depth token/hash/provenance and exact requested recipe. Both displayed
PNGs are byte-verified. Apply redeems exactly that unconsumed review, including
recipe_sha256, before_sha256, after_sha256 and result_source_sha256. The latter
is the canonical full-resolution output asset, never the display PNG digest.

A successful receipt requires return_mode:new_image, distinct result_document_id,
copied_original_document_id equal to the original owner, exact result revision,
and matching result_source_sha256. A no-change result still creates a distinct
new image and is true exactly when its full asset SHA equals the source asset.
An added history_entry_id, aliased result document, changed source owner or
unmatched result digest is rejected. The engine host additionally owns source
file/original provenance, actual transaction and positive new-document readback;
the native mailbox does not claim to prove those independently from pixels.

## One dispatch, unknown outcomes and epochs

Native admission records a permanent bounded request identity before dispatch.
The same original request can only return its retained result; altered contents
with the same ID reject. Eviction never removes the identity tombstone. The
preview's one-copy authority is consumed before queue/write/flush uncertainty.
The native private host_epoch is checked and stripped before engine stdin.
A per-row single-use ingress permit is consumed at EngineHandle entry and cleared
on every send return, including another domain's refusal. Even an exact repeated
lens envelope cannot bypass the mailbox through generic/direct/interactive sends.

An uncertain send, malformed receipt, timeout, panel disappearance, read cancel
ACK, unrelated event or engine EOF cannot become a rejected/cancelled write.
Unknown apply remains non-evictable and blocks new writes, undo, save and export.
Only the one exactly registered apply may pass its own ingress fence; exact
read/status paths and hello/shutdown are explicit exceptions, not a generic
`action == state` bypass. New source capture/preview is additionally refused at
mailbox admission while an original session write is unresolved.

The first validated small terminal is immutable, including across engine end.
A late exact write terminal from draining the original epoch may resolve that
original unknown. Old identities are never dispatched into a replacement epoch.
A later contradictory receipt query cannot overwrite or contradict a retained
validated original terminal. Successful query receipts preserve the exact inner
JSON object; only the native outer transport ID is readdressed when updating the
original status slot. No UI receipt is replaced with a generic success flag.

## Bounded memory and idle expiry

Native retains at most 128 rows, a 128 MiB serialized request/result reservation
budget, and 16,384 replay identities within an 8 MiB identity budget. Full-frame
PNG bytes cap at 4 MiB each and 1280 px per edge. Depth caps at 1024 px per edge.
Context result admission reserves 9 MiB; previews reserve 12 MiB before dispatch;
write/query outcomes reserve 32 KiB. Unknown writes keep their small reservations.
These are explicit payload bounds, not a guarantee of total allocator/RSS use:
transient JSON/base64 verification and Value/string overhead still exist.

Source/manual session TTL is 600 seconds. Candidate TTL is 180 seconds, also
bounded by session expiry. Manual-plane preparation does not renew the original
session lease. The maintenance thread checks deadlines every 15 seconds; 15
seconds is NOT the source or review TTL. It performs no rendering or IPC. It
reclaims idle completed large read payloads even when nobody polls. A failed
maintenance-thread creation closes admission rather than retaining unbounded
image leases. Expired read status explains that its lease ended and that a new
explicit read/preview is required; it does not pretend cancellation stopped work.

Only successful image-bearing read terminals are compacted on expiry/end.
Small validated rejected/cancelled/applied terminals are not rewritten by lease
cleanup. Completed compact rows may be evicted under bounded capacity, while
identity tombstones remain. Outstanding reads are bounded to one source job;
query rows cannot permanently pin image reservations. The actual host has its
own stricter retained source/candidate/working-set limits and cooperative job
budgets. Neither set of limits demonstrates interactive performance.

## Exact read cancellation, not numeric hash folklore

Native resolves requestId to its immutable admitted outer read envelope and
passes it through the dedicated same-writer EngineHandle control hook:

    {cmd: "lens_blur_cancel_read", request_id, request: original_envelope}

The Python reader validates the outer and nested ID/action/schema and computes
its own digest from the retained parsed proof. Native and JS do not reproduce
Python float JSON formatting or pretend a reserialization is the original byte
hash. Changed envelope/owner/recipe proof cannot cancel the uniquely bound read.
The control only sets cancellation intent. Only the serialized host can report
that the original read actually unwound. Apply/receipt/write cancellation is
never dispatched over this control lane. An uncertain cancellation control is
not retried.

See `INTEGRATION.md` for shared hooks, `ACCEPTANCE_UNRUN.md` for remaining gates.
