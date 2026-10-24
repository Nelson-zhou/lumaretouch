# Dedicated native whole-body width boundary

AUTHORED / UNRUN. Exact requirement: LNX-REF-PC-32473-C-bc54b9eb3c. This boundary owns only request validation, epoch-bound transport receipts and validation of the canonical publisher's evidence. It does not own body state, people associations, history, pixels, model acquisition or a second rendering path.

## Family-owned files

- `ui/src-tauri/src/body_slim_api.rs`: exact `body_slim` Tauri command and `body_slim_result` protocol 1; current-photo `view`, `select`, `status`, `edit`; local `mailbox_status` and `release`.
- `ui/src-tauri/src/body_slim_api_unrun.rs`: 22 synthetic authored-unrun Rust fixtures, included through the API module's `cfg(test)` path. These do not represent detected anatomy, decoded images or photographic acceptance.
- This integration note. No shared registration files were edited by the native-boundary worker.

## Exact request and ownership contract

The recipe is precisely `{version:1, amount:number}` with finite signed amount in `[-1,1]`. Other operations, head boxes/pivots, unsigned-only semantics, inferred silhouettes and transfer actions are not aliases.

Support review has precisely `data`, `points_sha256`, `visible_anchors` and `ownership_confirmed`. Anchors must be the ordered complete set 0 through 32 and ownership must be true. Draft data contains version 1, method `user-traced-complete-person-silhouette-v1`, `outline`, `collar_box` and all seven exact `body_slim_state.FLAGS` confirmations set to true. The outline contains 8–128 finite normalized vertices, without repeated closing point, degenerate edges, redundant/reversing collinear vertices, self-crossing/touching edges or negligible area. The complete contour must lie strictly within the explicit four-sided collar.

Persisted support additionally requires the complete canonical `associated_face_ref`, `associated_face_box` and `associated_face_evidence_sha256` triple. A caller may provide either no factual triple or the entire triple, never a partial triple. Full face boundaries must lie strictly inside the actual polygon, including segment checks for concave contours. Cross-source face references are rejected. The engine alone attaches or verifies the current confirmed same-person face and actual source observations; native geometry checks cannot create ownership evidence or replace the single-person census and all-33-point visibility checks.

Requests retain document ID/epoch/revision, body and people graph hashes, association revisions, exact BodyRef, operation ID and independent inner edit identity. View validation permits genuinely absent support/association to remain visible for correction, but never treats missing required fields, duplicate bodies, face references substituted for body references or cross-source support as evidence. Source previews retain the existing full-source/ALIGN8, dimensions, orientation and normalized-full-frame contract. They are references for manual review, not effect proofs.

## Actual publication evidence

A successful inner receipt must distinguish rendered output from retained but unapplied intent. Both require matching publication/request identity, published frame ID, output digest and `runtime_quality_accepted:false`.

- Unapplied output requires a nonempty matching reason, `rendered:false`, `applied:false` and `retained_intent:true` from the canonical publisher. A saved review/reset is not mislabeled an effect.
- Rendered output requires matching document render revision, geometry/output digests, original dimensions, canonical whole-source or ALIGN8 render dimensions, original-resolution flag, known output precision, the existing body-then-face composition identity and exactly one source sampling pass. Frozen order is structurally checked but not re-derived here; `body_pose_geometry` remains its sole authority.
- Actual body fields must identify their unique operation/BodyRef and source. An active selected body-slim intent cannot be silently omitted. A body-slim field must match its current body, all-point digest, reviewed source support, face binding/evidence, signed recipe, requirement ID and field facts. Claims of AI segmentation, inferred hidden anatomy or vertical movement are rejected. Native validation checks evidence consistency; it does not recompute pixel/map hashes or claim numerical/image quality verification.

## Unknown-result behavior

Exact serialized outer request content is retained in a process-lifetime replay ledger, including after release and engine-epoch changes. An identical retry reads retained status only; changed content under the same ID is rejected. Limits are 32 retained records, 32 MiB receipt reservations, 16 MiB serialized identity/signature retention and 65,536 tombstones. These are bounded payload budgets, not a claim of total allocator use.

An engine exit or invalid response becomes unknown, never rollback or proof of nonexecution. Original uncertain edits cannot be released. Only an authoritative terminal inner receipt for the original request, in the original engine epoch and matching the retained source binding on success, may settle its recovery fence. Status remains queryable after the current source is switched or deleted. It neither replays the edit nor invents a replacement outer result.

## Required parent-owned shared hooks

These hooks were observed in the working tree during final static inspection. This is source integration evidence only, not executed acceptance.

1. `main.rs`: declare `mod body_slim_api` and register only `body_slim_api::body_slim` in the Tauri handler.
2. `capture_lifecycle.rs`: call `body_slim_api::reset(epoch)` when resetting capture/receipt hosts.
3. `engine.rs`: invoke `ready(epoch, body_slim_protocol == 1)` and `ended(epoch)` in the exact lifecycle. Capability protocol support is independent of optional native-core availability.
4. Before generic recovery observation, include `body_slim_api::guards_result(epoch, request_id)` in the request-ID guard and exclude raw `body_slim_result` from generic observation. The ID guard also blocks a forged or late result with a wrong event name. Route the event through `receive` before adopting document state.
5. `engine.rs` send and interactive-send paths: exempt only exact `view`/`status` from recovery issuance and unrelated capture invalidation, using this module's `read_only`.
6. `native_dispatch.rs`: route exact body-slim read-only queries through epoch-checking `enqueue`, route `body_slim` mutations through the same enqueue, and mark history dirty only for its `edit` action.
7. Engine registry/host/transport: register only the dedicated family and event; wire its canonical receipt ledger, body/people bank, source binding, common preparation/publisher and existing history. Add the family to the arm-proposal safe-query allowlist so its read-only queries do not cancel unrelated work.
8. UI: `runBodySlim`, protocol/availability capabilities, `doc.body_slim`, app-lifetime owner and exact current-photo control. The owner retains original identities on close/source navigation. Missing core leaves status, zero reset and disable available; no build/download or JavaScript/Python warp fallback.

No preset, batch, transfer, model acquisition or unrelated family route is introduced by this module.

## Static verification and frozen hashes

Only source inspection, standard-library source processing and SHA-256 hashing were performed. No product imports, tests, compilation/build, typechecking, inference, installation/download or Git/GitHub operations were performed by this worker. All authored fixtures remain UNRUN.

- `body_slim_api.rs`: `9aa2aaf3b8bd045e2b70ca7e857e036495293445e2426735fb95c7a5aef2e730`
- `body_slim_api_unrun.rs`: `2eb4967aae2db3aeb29ed698cacc99ebe12de6aff320bfe7cb35f7a24d08a363`

Native compilation, protocol execution, decoder correspondence, interrupted UI flows, real photographs, numerical accuracy and performance remain explicit future acceptance gates.
