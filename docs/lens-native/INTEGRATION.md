# Shared integration contract: lens protocol 2

The files in this lane intentionally do not edit main registration, engine
lifecycle, dispatch, engine stdin, Python server routing or the App mount. Their
owning integration lane must connect these exact hooks once.

## Rust modules and Tauri registration

Declare `mod lens_blur_protocol; mod lens_blur_api;` in the Tauri crate root.
Register lens_blur_api::{lens_blur_request,lens_blur_status,lens_blur_cancel,
lens_blur_capability} in generate_handler. No command-name aliases should route
this domain through body-slim/expression receipts.

## Epoch lifecycle and negotiated capability

- On engine reset/start: `lens_blur_api::reset(epoch)`.
- On a matching ready hello: require `lens_blur_protocol == 2`, then call
  `lens_blur_api::ready(epoch, &hello["lens_blur_capability"])` with the exact
  LensCapability object. If protocol is wrong, pass an unavailable capability
  or leave the mailbox unsupported. An available flag alone is insufficient.
- On EOF/shutdown/end: `lens_blur_api::ended(epoch)`. Never clear identities or
  turn unknown writes into cancellations here.
- Source-changing/editor refresh events are not authoritative lens receipts.

## Single dispatch and recovery observation

Route AppState's `cmd == lens_blur` through `lens_blur_api::enqueue(handle, cmd)`.
The new API calls AppState::send_to_engine only for apply, so the existing shared
mutation invalidation and history refresh path remains authoritative. Read-only
calls directly use the dedicated enqueue path and must not dirty history.

Both EngineHandle::send and EngineHandle::send_interactive must consult
`lens_blur_api::blocks_mutation(epoch, &cmd)` once before new mutation admission.
This consumes the dedicated enqueue path's one-use ingress permit for lens
envelopes. Do not add an earlier AppState precheck that consumes the same permit
twice, or skip it for read-only/direct/interactive lens traffic.
Both must treat exact `lens_blur_api::read_only(&cmd)` operations as non-mutating
for generic recovery/capture invalidation. This classifier is not authorization:
all lens envelopes still require the dedicated admission/enqueue checks.

When a RAW engine stdout line is a lens result, call
`lens_blur_api::observe_line(epoch, &line)` BEFORE generic recovery settlement.
Do not parse into Value and then pass it to a lens observer: duplicates at any
nested field are evidence that only the original raw parser can detect. There
is deliberately no public Value-only observation shortcut in this lane.

Only the returned normalized internal Value, if Some, may be forwarded to
project_recovery_fence::observed. It carries the exactly validated ORIGINAL apply
request ID, phase:done and outcome_unknown:false. It is not the UI receipt and
must not be used as fake image/document/history evidence.

Always exclude raw lens_blur_result events from generic fallback settlement.
Also include lens_blur_api::guards_result(epoch,id) in generic ID guards, including
terminal/evicted tombstones. A duplicate event key, late contradiction, wrong
result domain or unrelated same-ID event must never bypass the raw lens validator.
Do not allow a generic creative_document/state event to settle an unknown lens
apply. The actual common-host new-copy event can refresh UI independently.

## EngineHandle read-control hook

Implement:

    pub(crate) fn cancel_lens_blur_read(
        &self, request_id: &str, request: &serde_json::Value
    ) -> Result<(), String>

Use the existing EngineInput::with_writer mutex for ONE complete JSON line:
`{cmd:"lens_blur_cancel_read",request_id,request}`. Verify handle liveness.
Write all bytes plus newline and flush under the same writer lock. On uncertain
write/flush failure, close dispatcher/input and return uncertainty; never retry.
Do not send through the serialized job dispatcher, or cancellation would wait
behind the very source job it should stop. Do not create a second stdin writer.

The API alone fetches the original retained envelope and restricts cancellation
to current/manual-plane/preview in the same epoch, once, after original dispatch.
This hook must not mutate the original envelope or add/remove nested fields.
The Python reader's `lens_blur_jobs.Jobs.ingress` supports this exact-proof form.
No cross-language float-based cancellation hash is exposed to the UI.

## Host and UI companions

The host dispatches current/prepare_manual_plane/preview/submit/receipt, emits
lens_blur_result, and exposes an exact LensCapability in ready hello. It owns
source capture, explicit manual plane, real aperture rendering, canonical
new-image publication and positive original-provenance-linked readback.

The UI native port polls lens_blur_status for the exact admitted transport ID.
Writes are preserved outside the mounted workspace; refresh failure retries
refresh only. To resolve an unknown original write, it sends a fresh receipt
query carrying the unchanged original command, never another submit.

A lens result is not committed merely because native request returned, a Cancel
button disappeared, a new tab opened or a creative state changed. Show only
validated real context/review and exact final receipt facts.
