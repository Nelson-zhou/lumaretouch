# Native bounded-ingestion receipt boundary

Status: authored, statically reviewed, **UNRUN**. No test, build, type check, import, camera operation, download or runtime acceptance was performed for this slice. The fixtures specify the intended boundary; they are not evidence of a passing implementation or hardware support.

## Pure module and required integration

`ui/src-tauri/src/ingest_receipt_validation.rs` contains only JSON/protocol checks and deterministic name-address derivation. It owns no store, epoch, engine dispatch, filesystem, worker, camera, recipe mutation or recovery fence.

- `valid_request(request)` checks the exact protocol-1 command schema from `engine/src/lumaretouch_engine/ingest_session_protocol.py`.
- `accept(request, prior, event)` is the context-free convenience boundary. It is not a permissive fallback for a session-owned operation.
- `accept_with_context(request, prior, event, &ValidationContext)` is the storage/fence boundary. Context contains optional `arm_request`, `arm_receipt`, `original_import_request` and `original_import_prior` references.
- `operation_id(session_id, request_id) -> Result<String, String>` and `uuid_v5(namespace, name) -> Result<String, String>` expose canonical UUIDv5 recovery/target address derivation to native owners. They do not issue or retry an operation.

The caller must resolve these references only from previously accepted receipts in the **same engine epoch**. The original admitted request is immutable; never obtain owner evidence from the new event, renderer claims, a different epoch, or an unvalidated raw engine event. Retain successful arm receipts and original imports for their session's lifetime. Query/cancel lookup matches both the requested session and the original operation ID. An absent, conflicting or ambiguous lookup fails closed.

Validate before storing a new receipt **and** before allowing it to settle `project_recovery_fence`. The recovery fence must consume the acceptance decision for that exact event, not separately accept any matching action/status. Rejection leaves the original stored result and pending/unknown write fence unchanged. An accepted pending/unknown event is still not settlement. Epoch checks, store bounds, admission synchronization and dispatch order remain responsibilities of the integrating transport.

The engine emits an original `import` terminal before the `query`/`cancel` readback when reconciliation proves the write. A query receipt is never relabeled as the original import or used directly to settle its write fence. Continue observing the independently correlated original event.

## Evidence checked

Every envelope requires exact event name, protocol integer `1`, original request ID, action and allowed fields/status. Unknown fields, noncanonical identities, mismatched protocol, malformed state, inconsistent counters, false runtime-certification claims and over-budget payloads are rejected. Request/source validation preserves five decimal-string stat components without converting them through floating-point numbers.

Every import request also requires `root_identity: [dev_decimal, ino_decimal]` from the destination directory originally pinned by the native owner. It must contain exactly two canonical, nonnegative `u64` decimal strings: no JSON numbers, signs, whitespace, leading zeroes (except `"0"`), extra components or overflow. The original admitted command retains this identity unchanged. The engine must compare it with the actual opened managed-root directory file descriptor **before any writes**; a matching path string is not sufficient when a directory is replaced. This pure validator checks the command evidence and does no filesystem inspection. Receipts need not echo the root identity: the exact retained original request and engine-side FD check carry that obligation, while source and managed-path receipt proofs remain unchanged.

An arm success must reproduce the requested owner, operation budget and complete saved-project binding, including disk SHA-256. A session-owned receipt must match the retained arm's session ID, owner, budget and stable `project_id`, `path` and `workspace`. A zero-use session must still have the original complete binding. The disk hash is a changing compare-and-swap base, not an immutable session ID: an original import's own proven success may advance it; a pending/unknown/failed progression may not.

The engine emits a pre-dispatch pending event with a null inner receipt. The first observed pending pins the inner operation ID, and all later proof must agree with it. The validator also checks the protocol's UUIDv5(session ID, original outer request ID) address. If the pending event was lost, a fully validated original terminal can still reconcile using the retained original request and arm owner, actual managed receipt, and all required source/document evidence. A query can likewise recover that original operation when `original_import_prior` is absent, but `original_import_request` remains mandatory. Knowing the deterministic address alone never authorizes replay, proves completion, or overrides a contradictory retained pending event.

Successful imports require all of the following:

1. The original session, original outer request ID and pinned inner operation ID.
2. An actual `managed_import_result` for that inner ID, `succeeded`, with the exact imported count and no contradictory readback requirement.
3. Exactly the completed-source document set, with no missing/extra/duplicate sources, document IDs or managed paths. Equal byte hashes remain distinct occurrences.
4. Per-document exact original path, SHA-256, integer byte size, all five original stat strings, occurrence ID and completion kind; original basename; nonempty bounded document/source/recipe identities; decimal revision; and the original inner receipt ID.
5. The exact protocol-derived managed target: requested root plus UUIDv5(inner operation ID, original path), with the Python host's lowercase final extension rule.
6. A coherent session that no longer claims that original operation as pending or unknown. A failed/cancelled original instead needs the exact matching failed/cancelled inner receipt, no documents, a stopped session and an unchanged binding.

The private UUIDv5 helper uses SHA-1 only to reproduce the protocol's deterministic UUID name/address. It is not a security primitive, credential, content-integrity proof or replacement for the source SHA-256. An authored RFC UUIDv5 vector documents compatibility without adding a crate dependency.

Query/cancel readbacks require the retained original import request and, when available, its previously accepted operation proof, in addition to the arm owner. A missing prior receipt uses the exact derived operation ID and complete actual operation evidence, never a status-only fallback. Their operation identity cannot substitute another outer request or session. Completed original operations are immutable even when queried while a newer session operation is active. A release success requires an owned idle released session and a null current session; pending/unknown sessions cannot release.

## Transitions and dispatch failures

- First `succeeded`, `failed` or `readback` receipts are immutable. Only an identical repeat is accepted. New snapshots need new read request IDs.
- Pending imports may advance with matching ownership/operation evidence. Unknown never regresses to pending.
- Unknown-to-terminal is not arbitrary overwrite permission. Only a validated original operation proof can reconcile import/query/cancel; a generic error cannot clear an admitted write. Unknown arm/release/state receipts do not acquire terminal proof merely because another result arrives.
- A normal first pre-admission error may be recorded when its available session/owner evidence matches. It cannot replace an earlier pending or unknown result.
- The dispatcher may emit `status: "failed"`, `session: null`, a nonempty `error`, and `dispatch_rejected: true` only when a guard rejects **before invoking the handler**, with the exact ordinary envelope identity. This shape is accepted only as the first receipt, or as an identical repeat of that terminal receipt. It cannot contain operation/publication proof or clear an already pending/unknown import. The marker is not a renderer-provided bypass, an exception wrapper around a possibly executed handler, or proof of rollback.

If a response is missing, malformed, contradictory or lacks original ownership evidence, preserve uncertainty. Do not issue a second import, mint a replacement operation identity, infer that a cancellation rolled back, or release the lease. Reconcile using the original engine operation and persisted project through the existing host route.

## Authored coverage and remaining acceptance

Inline Rust fixtures cover canonical command/source schemas, mandatory two-string root device/inode identity (including precision, canonical form and `u64` boundaries), exact arm binding, first-pending admission, lost-pending reconciliation versus contradictory pending, protocol/action/request/session mismatches, derived and pinned operation IDs, all completed-source proof fields, duplicate/missing documents, exact managed targets, equal-byte distinct occurrences, immutable terminal/readback receipts, pending progression, unknown reconciliation, original-owner query/cancel, release refusal, dispatch rejection and a UUIDv5 reference vector. They are all **UNRUN**.

This module cannot authenticate an engine process or verify actual files/disk publication by itself. The Python host remains responsible for byte/stat checks, original root device/inode verification against the actual directory FD before writes, saved-project integrity, atomic managed registration and truthful operation proof. Integration still needs explicit acceptance for epoch changes, raw-event/fence ordering, concurrent receipt delivery, destination-directory replacement races, saturation/readback headroom, engine restarts and post-replace reconciliation. Actual camera completion, decoded image quality and end-to-end workflow/tether behavior remain unverified.
