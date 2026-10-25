# Hair unification native transport

Status: AUTHORED / UNRUN. This is source implementation and unexecuted fixture
coverage, not compilation, Tauri/product execution, inference, image-quality or
acceptance evidence. No dependency installation or runtime download is added.

## Public boundary

- Invoke `hair_unification({request})` with exactly `cmd`, `protocol`,
  `operation_id`, `request_id`, `action`, `people_context`, and `payload`.
  The constants are `hair_unification`, `1`, and `lnx.hair_unification.v1`.
- Actions are `context`, `preview`, `presented`, `commit`, and `clear`.
  Context is the exact existing six-field people context, restricted to a
  source-owned face. No parallel document, person graph, renderer or history.
- `hair_unification_status({request_id})` queries only the original native
  mailbox, without sending, replaying, generating a replacement ID, or requiring
  the original engine to remain alive. Return phase is `pending`, `done`, or
  `unavailable`, with the original request ID and optional result/error.
- Successful admission is `{requested:true,request_id}`, not applied pixels.
  Only a request known never to have been admitted receives
  `{requested:false,not_sent:true,request_id,error}`. After native registration,
  any dispatch failure is conservatively query-only. Exact duplicate admission
  returns the original identity without another enqueue; changed content under
  that identity is rejected without falsely claiming the old request was unsent.

## Review and result binding

Preview accepts a nonzero finite amount in [-1,1], source-normalized manual
brush/radial root and tip vectors, and explicit ownership confirmation. Existing
vector limits apply: 64 objects per mask, 1,024 points per brush, 8,192 points per
mask; no full-image, semantic, prompted, intersect, screen-space or face-box
shortcut. The engine remains responsible for genuine hair/source evidence.

The result must have event `hair_unification_result`, exact protocol/operation,
request ID, action, document ID, complete retained people context, and a
`request_payload` copy of the original incoming payload. Explicit boolean
success/outcome_unknown are required. A success needs an object payload and
known outcome; a failure needs a nonempty bounded error string. Comparisons use
JSON values and numeric meaning, not cross-language reserialization hashes.

Successful commit/clear receipts additionally need the actual confirmed/cleared
publication payload and canonical `doc_state.people`: matching document, epoch,
source and selected face; nonregressing document/people revisions; unchanged
association revision; and the resolved operation amount matching the receipt.
An empty metadata payload, wrong source, or readback/reload-required result
cannot settle a mutation. The validated complete mutation receipt is returned
to the parent so it can update recovery and, only on success, visible state.

The native bridge verifies the actual PNG byte hashes and IHDR dimensions of all
three preview images, source and face ownership, recipe, and sample vectors.
It does not claim PNG header checks decode the images or establish visual
quality. The UI owns actual load/display confirmation; the engine owns candidate
rendering, complete graph/source fences and publication.

`presented` contains the exact preview ID, review token, and before/after/support
PNG hashes. It must match a retained same-epoch successful preview. The commit
payload stays exactly `{preview_id,review_token,confirmed:true}` and must match a
retained same-context successful presented acknowledgment, which already binds
all three hashes. That retained proof also carries the exact preview recipe and
sample-asset digest; successful commit must publish that recipe and that asset,
not merely any correctly formatted hash. An admitted commit consumes that identity even if its dispatch
later becomes uncertain. The engine independently enforces the same review.

The first verified known terminal is immutable. Invalid or uncertain results
cannot settle recovery. A later exact original terminal can resolve uncertainty,
including while old-engine stdout is draining. Unavailable is never evidence
that a request did not execute.

## Capacity and lifecycle

- Request bound: 512 KiB. Each PNG data URL: 8 MiB. Preview result: 25 MiB;
  context result: 9 MiB; other result reservations: 8 MiB.
- At most 64 retained rows and a 96 MiB combined serialized request/result
  reservation budget. Result capacity is reserved before dispatch, not after
  admitting several concurrent large images.
- At most 16,384 process-lifetime tombstones, with a separate 16 MiB serialized
  request/key budget. Tombstones retain exact original requests, not ambiguous
  hashes, and survive terminal eviction and engine replacement.
- These are serialized payload budgets, not exact allocator/RSS bounds. Parsing,
  PNG base64 decoding and the UI/engine own additional bounded working copies.
- Only settled or explicitly retired rows may be evicted. Unknown commit/clear
  rows stay pinned with their response reservation. Engine start does not clear
  their result, replay protection, or mutation barrier. Old terminal receipts
  remain readable until ordinary bounded terminal eviction.
- Explicit authoritative `project_opened` from the current engine can retire
  uncertainty for the newly read workspace, while preserving old unknown status
  and request tombstones. It does not rewrite unknown as failure/success.
  Only after the actual project-open event has a numeric `docs` and its native
  epoch matches the current live mailbox, the native path adds
  `workspace_reopened:true` to each retained unresolved result, including reads
  already retired when an old engine ended. These status results still have
  `success:false` and `outcome_unknown:true`, with the original protocol,
  operation, request, action, document, people context, and request-payload echo.
  The marker authorizes the UI to leave the old request's blocking recovery
  state, not to report that operation as applied or failed. Settled results are
  unchanged. Any backend result containing `workspace_reopened`, even false or
  null, is rejected; only local mailbox status can expose this native proof.
- `hair_unification_protocol == 1` is command support, independent of
  `hair_unification_available`. Missing core/ABI never fabricates an algorithm:
  preview/commit are not admitted, while context and neutral clear remain
  reachable. Presented is a read-only image acknowledgment.

## Shared integration points owned by the parent change

1. Declare `mod hair_unification_api` and register the two Tauri commands.
2. Call `reset(epoch)` when establishing a new engine and
   `ready(epoch, protocol_supported, native_available)` from its ready event.
   Call `ended(epoch)` only after stdout receipts drain.
3. Add this command to the `send_to_engine_at_epoch` allowlist. In shared native
   dispatch, use `enqueue(handle, command)` for both reads and writes. Read-only
   actions bypass generic mutation invalidation/history; only commit/clear can
   mark history dirty. The exact seven-field envelope goes to the engine.
4. In both EngineHandle send paths, call `blocks_mutation(epoch, command)` and
   recognize `read_only(command)` before generic recovery/history admission.
5. On raw stdout, call `observe_line(epoch, line)` before generic recovery
   observation. Its unique-JSON parser rejects duplicate keys at every depth.
   Forward only its returned validated marker to recovery observation.
6. Exclude raw `hair_unification_result` and every request ID protected by
   `guards_result(epoch, id)` from generic recovery settlement, including wrong
   event names, duplicates, stale/contradictory terminals and tombstones.
   `receive(epoch, value)` is for trusted in-process fixtures, not a second
   unvalidated stdout route. Do not settle from unrelated metadata events.
7. Forward verified current-engine project-open events to
   `project_reopened(epoch, value)`. Refresh visible graph state only from the
   accepted successful original mutation receipt, never from a rejected raw
   event with an attached `doc_state`.

## Authored fixtures

The Rust file contains unrun fixtures for exact envelopes; manual vector bounds;
source/context/payload/action/epoch mismatch; immutable terminals; uncertainty
without recovery settlement; PNG bytes/hash/dimension binding; presented proof;
single-use commit; missing-core neutral clear; old-epoch retention; terminal
eviction with replay tombstones; bounded pending reservations; duplicate JSON
keys; trailing JSON; and numeric-equivalent cross-language echoes.
Additional unrun fixtures cover native-only reopen provenance, stale-epoch
reopen rejection, retired unknown reads, immutable settled outcomes, and
backend marker forgery rejection.

Remaining local acceptance: compile/type checks, actual Tauri invoke and engine
integration, load/display/close/reopen interruption flows, partial pipe failure,
real source/people/recovery/history paths, unavailable-core behavior, original-ID
query, and full-resolution export/undo checks. None were run for this change.
