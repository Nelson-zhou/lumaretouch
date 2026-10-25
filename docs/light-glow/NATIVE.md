# Dedicated light-glow native transport

Status: **AUTHORED / UNRUN**. Source-only implementation and manual source review.
No product import or execution, test, build, type check, image download, inference,
installation, camera operation or Git write was performed for this module.
The authored fixtures are not photographic or end-to-end acceptance evidence.

## Ownership and replacement boundary

`ui/src-tauri/src/light_glow_api/mod.rs` is the compile-time integration facade.
Internal files separate bounded JSON, PNG-byte verification, wire contracts,
engine-lifetime mailbox state and Tauri/engine transport. The TypeScript facade
is `ui/src/lightGlow/nativePort.ts`, implementing the existing `LightGlowPort`.
These are replaceable built-in modules, not an arbitrary shared-library loader,
live hot-plug API, independent renderer, document writer or second undo owner.

The adapter sends only dedicated `light_glow` and `light_glow_cancel_read`
commands. It neither aliases lens/expression commands nor edits their recipes,
numeric cores or transports. Pure validation/lifecycle patterns follow the
existing mature native receipt architecture, but all glow identities, payloads,
capabilities and cancellation controls are separate.

Python owns current edited-source capture, source/file/people/repair fences,
native glow math and the canonical new-copy transaction. See [ENGINE.md](ENGINE.md)
for its frozen contract. Wire protocol **1**, ABI **1**, math **65537**, and
current edited-source capture evidence **3** are different version dimensions.
There is no claim that the transport itself is protocol 3.

## Shared integration contract

The parent integration must declare `mod light_glow_api;` and register exactly:

- `light_glow_api::light_glow_capability(state)`
- `light_glow_api::light_glow_request(state, request: Value)`
- `light_glow_api::light_glow_status(state, request_id: String)`
- `light_glow_api::light_glow_cancel(state, request_id: String)`

All four return `Result<Value, String>`. Tauri JS arguments use `request` or
`requestId` respectively. The facade keeps the Tauri command macros at the
registered module path rather than relying on generated-macro re-exports.

The native engine hooks are:

    reset(epoch: [u8; 16])
    ready(epoch: [u8; 16], capability: &Value)
    ended(epoch: [u8; 16])
    observe_line(epoch: [u8; 16], raw_line: &str) -> Option<Value>
    guards_result(epoch: [u8; 16], request_id: &str) -> bool
    read_only(command: &Value) -> bool
    blocks_mutation(epoch: [u8; 16], command: &Value) -> Result<(), String>
    enqueue(handle: &EngineHandle, command: Value) -> Result<(), String>

1. Reset on engine creation. Feed the actual Python capability object only when
   the engine declares `light_glow_protocol == 1`; otherwise feed null. Capability
   is unavailable until the exact ABI/math/modes contract is validated. A library
   filename, successful unrelated effect or transport connection is insufficient.
2. Call `observe_line` on the **original raw stdout line**, before generic receipt
   recovery. It rejects duplicate JSON keys, non-finite/out-of-range data,
   oversized lines and trailing JSON. Parsing to `Value` first destroys duplicate
   field evidence and is not an equivalent hook.
3. An optional returned marker is for `project_recovery_fence::observed` only.
   Never substitute it for the exact UI receipt. Exclude `light_glow_result` and
   IDs guarded by `guards_result` from generic parsed-result settlement, so an
   invalid/malformed response cannot clear the pending write fence.
4. Consult `blocks_mutation` on both ordinary and interactive engine sends,
   before enqueue. It admits only the registered one-use exact envelope and
   blocks unrelated work while any original glow write is unresolved. The gate
   also prevents direct raw-command bypass/replay. `hello` and `shutdown` remain
   lifecycle exceptions, not ways to confirm or cancel a write.
5. `read_only` returns true only for current/preview/receipt, consistent with the
   frozen engine adapter. Session cancellation is serialized `submit`, not an
   out-of-band pretend terminal. Both apply and session-cancel validated terminal
   receipts produce internal settlement markers if a recovery fence was issued.
6. Route shared native `light_glow` dispatch to `enqueue`. Its private
   `host_epoch` binding is verified and removed before stdin. Apply uses the
   existing `AppState::send_to_engine` mutation/invalidation route; dedicated
   read/query and session-cancel transport use the same engine handle/dispatcher.
7. Call `ended` on engine termination. Retire read/image leases, never settle an
   unconfirmed write by timeout or engine death. A genuine late raw terminal from
   the old epoch may still establish its original outcome.

Add this dedicated engine-handle method, using the shared complete-line stdin
writer mutex but **not** the serialized dispatcher:

    cancel_light_glow_read(
        &self, request_id: &str, original_request: &Value
    ) -> Result<(), String>

It writes and flushes exactly:

    {"cmd":"light_glow_cancel_read","request_id": ORIGINAL_ID,
     "request": EXACT_RETAINED_CURRENT_OR_PREVIEW_ENVELOPE}

On uncertain write/flush, close the affected control/dispatch input as existing
engine controls do; do not resend. Python ingress must run before serialized
dispatch and shutdown must stop its job controller. This bypass is necessary to
reach an in-flight read; merely queueing cancel behind the render is not an
out-of-band cancellation implementation. The echoed envelope lets Python compute
its own domain-separated digest; Rust never assumes cross-language JSON hashing
is identical. The cancel acknowledgement is only a request acceptance. The
original read's actual rejected/cancelled/ready terminal must still be queried.

## Source and review evidence

Current success validates exact owner/document epoch, u64 decimal revision,
canonical source hash/grid/orientation, capture version 3, original hash,
people-graph hash, ordered repair-stack hash, load ID and capture token.
The source context must carry an available matching capability and real PNG.

Preview must match its exact retained session/owner/recipe. Native retains a small
source proof and compares **all** source evidence and the before PNG hash/grid
against the original acquisition; a newly invented but well-formed capture token
or repair hash cannot pass. Before, after and coverage are independently checked:

- Exact bounded fields and canonical base64 encoding.
- SHA-256 of the complete actual bytes, not a claimed filename or metadata hash.
- Complete PNG signature, one valid first IHDR, per-chunk CRC, dimensions,
  non-interlaced 8-bit RGB/RGBA, contiguous IDAT, final IEND and no trailing bytes.
- No APNG, unexpected critical chunk, oversized image, cropped-grid substitute
  or mismatched three-image extent; maximum edge 1280 and one million pixels.
- Coverage must be RGBA rather than an opaque RGB illustration.

Rust does not inflate these PNGs or claim the UI actually displayed them. UI
decode/load, byte verification and review acknowledgement remain separate gates;
Python/core own actual coverage derivation and its numerical consistency with
the source/result. Three 4 MiB PNGs can exceed 16 MiB after base64, so the total
preview response budget is 17 MiB including envelopes. Current gets 6 MiB.

Apply consumes one unredeemed candidate before dispatch and binds the source,
candidate token, recipe hash, canonical full-resolution result hash, full-grid
coverage hash and all three presented PNG hashes. `reviewed: true` and
`return_mode: 'new_image'` are mandatory. A positive applied receipt must name a
distinct new document, identify the unchanged original document, carry an exact
u64 result revision and match the original requested full-result hash/no-change
fact. It cannot substitute a PNG hash or invent an original history entry.

## Known/unknown state and bounded lifetime

Native keeps at most 128 write records without eviction, whether known or
unknown, and at most 256 total live rows within 128 MiB reserved payload budget.
Small non-evicting identity tombstones are separately bounded at 16,384/8 MiB.
Capacity refusal happens before new submission; freeing imagery never permits a
previous request ID to run again. Source/preview leases are 600/180 seconds and
an idle cleanup thread releases expired imagery without modifying valid small
write receipts.

- A local admission rejection before dispatch is a known rejected write.
- An uncertain queue/send/flush, malformed result, timeout or lost response is
  unknown, never proof that apply failed or cancellation completed.
- Synchronous shared-dispatch errors are conservatively unknown in this slice,
  even if a particular underlying queue refusal did not enqueue. Cross-domain
  recovery registration may already exist, and this module has no exact
  command-bound no-enqueue settlement hook. It does not clear a possibly
  unrelated fence with a generic same-ID rejection. This can require manual
  investigation rather than allow a blind retry; it is an explicit limitation.
- Readback uses a fresh outer **read-only** query ID and the unchanged original
  inner write. It cannot render or execute the write. Its validated receipt may
  settle only that retained original request.
- First valid small terminal receipts are immutable. Contradictory later replies
  do not change them. Unknown writes are never evicted, cancelled by UI teardown,
  auto-retried or moved to a replacement engine.
- Engine replacement does not clear unresolved native write barriers. A query
  cannot be routed to a new engine to guess the old write's outcome.

This is engine/application-process lifetime retention, not a new durable journal.
After a full application restart absent proof remains unknown; no restart path
is licensed to reconstruct and resubmit a past write. Durable restoration or
cross-process reconciliation is outside this isolated module's acceptance scope.

## UI binding

Create one App-lifetime port:

    createLightGlowNativePort({
      engineKey: () => CURRENT_APP_ENGINE_KEY,
      beforeRead: async previewCommand => { /* existing safe read preflight */ },
      beforeWrite: async writeCommand => { /* existing safe write preflight */ }
    })

`LightGlowNativeOptions` and `LightGlowNativePort` are exported. Hook callbacks
must read current App state, not close over the mounting render's epoch/revision.
Do not recreate this port on hide/close. No no-argument singleton silently invents
an engine key. The port keeps source proof rather than many full PNG copies,
reserves read/write IDs before async preflight, never resubmits a timed-out
request, and cancels only reads with original native ownership. The sole
document mutation notification is emitted for an explicitly submitted apply.

`requestReconciliation` permits a fresh readback after an explicit user check.
Ordinary polling reuses the original/query IDs instead of consuming unbounded
query identities. Preview waiting is bounded; expiry of the wait preserves the
original pending read and exposes it via `pendingReads`, `checkReads` and
`cancelReads`. There is no alternate fake renderer, fallback frame, download or
model installation path.

## Authored fixtures and remaining acceptance

`light_glow_api/tests_unrun.rs` contains source-only fixtures for exact envelopes,
capability/math gates, capture v3 and revisions, real PNG byte integrity,
retained-source proof, all apply hashes, distinct new-document receipts,
cancellation acknowledgement versus actual unwind, immutable terminals,
readback/original correlation, non-evicting unknown writes, engine replacement,
direct-ingress bypass and finite scalar bounds.

All remain **UNRUN**. Still required after separate execution authorization:
Rust compile/tests, TypeScript type check, Tauri invocation coverage, integrated
engine source capture, actual out-of-band cancellation under load, displayed
three-image review, real native math, canonical new-copy readback, original and
undo integrity, restart/late-event scenarios, memory measurements, packaging and
representative photographic review. No pass is claimed by this document.
