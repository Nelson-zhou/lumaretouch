# Expression native boundary

Status: SOURCE-AUTHORED / UNRUN. This boundary is not an isolated feature acceptance claim. The immutable Python host, shared dispatch integration, UI mounting, full-image rendering and new-copy publication are now source-connected; all remain runtime-UNRUN. No product execution, import, test, compiler, typecheck, inference, installation or download was performed for this work.

## Ownership and modules

- `ui/src-tauri/src/expression_replacement_protocol.rs`: exact released `ui/src/expressionReplacement/model.ts` field validation, finite/duplicate-free original JSON parsing, raw-byte SHA-256, bounded full-frame three-PNG transport proof and new-copy receipt validation.
- `ui/src-tauri/src/expression_replacement_api.rs`: native epoch mailbox, process-lifetime request tombstones, one-dispatch admission, original status, explicit capability, cancellation control-lane admission and unknown-write fence.
- `ui/src-tauri/src/expression_replacement_protocol_unrun.rs`: authored, unexecuted adversarial contracts, plus mailbox contracts in the API module.

There is no separate renderer, invented landmark detector, fallback face identity, image publisher or second undo owner in these modules. A user confirmation never supplies measured evidence. The host remains responsible for exact retained assets, actual 478-point measurements and protection/eligibility facts, safe numerical compositing, cancellation inside expensive phases, candidate retention, atomic creation of the actual new image and canonical history.

## Tauri contract

Register all four commands:

1. `expression_replacement_capability()` returns `{protocol:1, operation_id:'lnx.expression_replacement.v1', available, reason}`.
2. `expression_replacement_request({request})`.
3. `expression_replacement_status({requestId})`, a read of the original native mailbox, not a new host action.
4. `expression_replacement_cancel({requestId,commandSha256})`.

The request and status return the direct result envelope, not a `done/result` wrapper. Packet actions return `{event:'expression_replacement_result',request_id,receipt}`, where `receipt` is exactly the released UI Receipt, including native pending/unknown/cancelling states. Capability absence rejects an admitted valid packet with `rejected`, `no_write:true`, never simulated availability. Malformed inputs, conflicting reused IDs, poisoned locks and exhausted hard budgets can reject the invocation. An invocation error is not generic proof that an earlier operation with that ID did not execute.

### Exact engine request envelopes

- Current: `{cmd:'expression_replacement',action:'current',request_id}`.
- Packet: `{cmd:'expression_replacement',action:'choose_donor'|'preview'|'apply',request_id:packet.command.request_id,packet:{command,command_json,command_sha256},path?}`. A path is allowed only for choose_donor and must be an absolute native path. No path means an actual dismissed picker, handled by the host, not native success.
- Release: `{cmd:'expression_replacement',action:'release',request_id,preview_token}`.

The native-only `host_epoch` field is stripped by `enqueue` and never enters these envelopes. The existing dispatcher may add its `_host_request_id` transport acknowledgement field; the server must strip that field before exact envelope admission.

Current terminal: `{event,request_id,phase:'current_ready',current}` or `{event,request_id,phase:'rejected'|'cancelled',no_write:true,message}`. Release terminal: `{event,request_id,phase:'released',preview_token}` or the rejected envelope. Native nonterminal current/release adds `command_sha256` to `{event,request_id,phase:'pending'|'unknown'|'cancelling',message}`. A missing/evicted native ID returns `{event,request_id,phase:'unknown',message}`, never terminal no-write.

Current cancellation hashes the exact sorted compact string-only JSON `{"action":"current","cmd":"expression_replacement","request_id":...}` as UTF-8, without ASCII escaping Unicode. UI retains the native-returned hash; it must not independently guess it. Packet cancellation uses the packet's original-byte digest.

### Cancellation is not completion

Native cancel accepts only a known, dispatched, nonterminal current/choose_donor/preview in the same actual engine epoch with exactly the original digest. Apply is never cancelable. A native dialog not yet submitted is not a host job: the UI keeps cancellation local until the dialog closes, discards any late path, then submits the original donor packet without path once.

Required `EngineHandle` method:

`pub(crate) fn cancel_expression_replacement(&self, request_id: &str, command_sha256: &str) -> Result<(), String>`

It writes `{cmd:'expression_replacement_cancel',request_id,command_sha256}` directly through the existing shared `EngineInput` whole-line writer, not the acknowledged serial dispatcher. Its reply `{requested:true,request_id,command_sha256}` acknowledges the cancel request only. The original host job must still emit its own terminal result. A repeated cancel does not write another control message; an uncertain control write is not retried. A terminal original returns `requested:false` and asks the UI to query the original result.

## Shared integration hooks

- Add sibling modules for the protocol and API in main, register the four Tauri commands.
- `reset(epoch)` on actual engine spawn, `ready(epoch,supported)` on matching engine ready, `ended(epoch)` on EOF/termination. Ready support requires protocol 1 and operation `lnx.expression_replacement.v1`; absent/wrong capability stays unavailable. EOF disables new work while allowing buffered original terminal stdout results to resolve rows.
- Add native dispatch `expression_replacement => expression_replacement_api::enqueue(handle,cmd)`. The API sends apply through the existing `AppState::send_to_engine`, preserving canonical invalidation and history handling. Current/donor/preview/release use direct dedicated enqueue and must not revoke unrelated editing captures or dirty history.
- `enqueue(handle,command)` requires an exact admitted original envelope and the original engine epoch, and consumes dispatch once. Generic external command paths must not bypass it.
- Call `blocks_mutation(epoch,&command)?` at both ordinary and interactive engine ingress. It blocks unrelated mutations, undo, save and export while a same-epoch apply remains unsettled. A valid first terminal apply settles this gate; timeout, malformed receipt, cancel acknowledgement and read completion do not.
- Exempt `read_only(&command)` from generic mutation/capture/recovery admission. The predicate has only current/choose_donor/preview/release for this namespace.
- Before generic recovery observation, consult `guards_result(epoch,id)` even if the event name is wrong. It includes retained tombstones, preventing late conflicting packets from settling another domain's fence.
- Feed matching result lines or guarded IDs to `observe_line(epoch,&raw_line)`. Do not feed a pre-parsed `Value` from stdout: normal serde parsing discards duplicate-key evidence. Unknown malformed expression lines mark outstanding rows uncertain rather than inventing a terminal. `observe` is only for trusted already-validated in-process values.
- If `observe_line` returns `Some(recovery_marker)`, pass only that marker to `project_recovery_fence::observed`. The marker is an internal normalized top-level phase emitted only for a validated original apply terminal. Do not send that marker to the UI. Do not additionally observe the raw nested receipt through generic recovery.

## Proof and lifecycle rules

Preview admission requires same-epoch native-retained current binding plus its exact measured target face and an exact donor-ready source/face. Host validation remains mandatory. The ready preview's complete before-image SHA and dimensions must equal the retained current photograph image; all three PNGs are separately byte-hashed, header/dimension checked, chunk-framed through IEND, and constrained to the same normalized full-source projection. CRC/DEFLATE decoding and perceptual quality are not independently asserted by this transport boundary.

Apply requires an unconsumed retained ready preview with the exact binding, preview request/hash, token, candidate/fusion digests and all three image digests. Admission consumes the token even if enqueue/write later becomes uncertain. A commit must identify a different actual new document, the exact original parent, candidate source SHA and a valid result revision. An accepted receipt does not itself prove visual quality.

The first validated terminal is immutable. Duplicate and contradictory late receipts cannot overwrite it. Invalid receipts preserve unknown state; a later valid original terminal may resolve that uncertainty. A lost/evicted result is never a reason to resend. Tombstones survive receipt eviction, preview release and engine replacement. Old status remains readable after source navigation; cancel or new apply cannot cross epochs.

Release cannot destroy preview proof while its apply is unsettled. Releasing or consuming a preview permits receipt eviction, but does not erase request identity. No automatic apply replay, undo synthesis or second publication exists.

## Explicit bounds

- Command JSON: 256 KiB. Complete submitted envelope: 768 KiB.
- Results: 49 MiB maximum; current/donor reservation: 17 MiB; other small operations: 32 KiB.
- Live mailbox: 64 rows and 128 MiB combined serialized request/result reservations. Unsettled rows and unconsumed/unreleased ready previews are pinned.
- Process identity tombstones: 16,384 IDs and 8 MiB accounting budget, never silently recycled.
- PNG base64: 16,000,000 characters each; longest preview edge 1,600, source pixels at most 100,000,000; face crop edge 1,024.
- Faces: 128, strokes: 128, total stroke points: 2,048. All source coordinates, finite density and exact confirmations are checked.

These are serialized retention/admission budgets, not claims of a total allocator or process memory limit. The shared stdout line reader and JSON transport still need their own ingress bounds. Transient parsed images and returned clones consume additional memory.

Epoch retirement preserves small validated cancelled/rejected/released receipts. Imagery-bearing or unsettled read-only leases become explicit expired no-write rejection and are reclaimable. This does not claim force-stopped inference. Apply uncertainty is never retired by that read-only path.
