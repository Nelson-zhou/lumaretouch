# Hair-volume native receipt adapter

Status: AUTHORED / UNRUN. No build, test, import, inference, installation, download, or image-quality acceptance was performed for this source-only slice.

## Ownership and wire contract

`hair_volume_api.rs` owns only the bounded process-lifetime receipt mailbox and mutation fence. `hair_volume_protocol.rs` owns transport validation. `hair_volume_protocol_unrun.rs` contains authored synthetic transport fixtures. None owns image rendering, semantic inference, source masks, the people graph, immutable support bank, or undo history.

The Tauri invocations are `hair_volume({request})` and `hair_volume_status({request_id})`. The first accepts command `hair_volume`, protocol `1`, operation `lnx.hair_volume.v1`, and `context`, `preview`, `presented`, `commit`, `clear`, or `status`. The UI recovers through the second invocation, which reads the original native receipt and never sends another engine mutation. A separately submitted engine status action is read-only and cannot settle or refresh the original operation.

Only current-photo face scope is admitted. The captured document ID/epoch/revision, people revision, association revision, target ID, and complete source-owned FaceRef remain immutable. Group, all-people, linked-person, preset, cross-photo, and alias activation are not inferred from this protocol.

## Review chain

1. Context validates the actual source PNG's canonical base64, bounded bytes, PNG framing/CRC, dimensions, and SHA-256. Original/derived provenance, exact source dimensions/hash, FaceRef, current recipe, and optional semantic evidence identity must agree with the request.
2. Preview admission requires a retained successful context from the same engine epoch and exact people context. Nonzero intent requires native availability and retained actual hair-evidence identity. Crown and each side have independent contour/probe vectors and confirmations. Source-pixel margins and tangent coverage are bounded before dispatch; the engine remains authoritative for genuine observations, anatomical protection, ownership, and numeric deformation safety.
3. A successful preview must echo its exact recipe, source, FaceRef, independent regions/protection, and semantic evidence. Full before/after/support PNG bytes and hashes are checked; all three images have identical bounded dimensions. Diagnostic source coordinates may be letterboxed into the complete final-frame review dimensions and do not impersonate a final crop.
4. Presented admission redeems that retained preview and the exact preview ID, review token, and three image hashes. It retains the candidate recipe/support asset/source proof for the subsequent commit.
5. Commit requires the successful retained presented ACK in the same epoch/context. A review may be claimed only once, including after receipt eviction. Successful publication must match the reviewed recipe and support asset digest, the original target/source, nonregressing revisions, and all canonical resolved leaves: `/crown/amount`, `/sides/linked`, `/sides/left`, `/sides/right`.
6. Clear requires a confirmed canonical neutral recipe but no native deformation core. It does not clear other operation families or pretend that an unknown earlier operation was reversed.

Protection vector caps follow the canonical support contract: two ear boxes, one neck box, and 64 other-person boxes. They are explicit user measurements, not inferred segmentation. The existing shared PNG transport parser is reused only for byte/framing validation; no unrelated source mask, algorithm, or acceptance authority is copied.

## Uncertainty and bounds

- A queue acknowledgment says only that this original request is retained. Any error after mailbox admission remains query-only; there is no automatic retry, new-ID fallback, or false `not_sent` claim.
- Request identities survive row eviction and engine replacement in bounded tombstones. Changed content under an old ID is rejected. Pending/unknown mutations are never capacity-evicted.
- Raw engine JSON is duplicate-key checked recursively before accepting a receipt. Wrong epochs, event names, request identities, payloads, sources, image hashes, publication leaves, or backend-forged reopen markers cannot settle a mutation.
- Only the original validated terminal mutation can release the shared recovery fence or refresh visible document state. First terminal outcomes are immutable. A late original terminal may settle an unresolved mutation until explicit authoritative workspace reopening retires it.
- Explicit `project_opened` in the live epoch retires unresolved receipts while preserving `success:false`, `outcome_unknown:true`, original request identity, and native-only `workspace_reopened:true`. This is recovery provenance, never proof of failure, success, or undo.
- Limits: 512 KiB requests, 25 MiB maximum reply, 4 MiB decoded PNG, 1024-pixel preview edge, 96 MiB live mailbox accounting, 64 rows, 16 MiB/16,384 process-lifetime tombstones. Admission fails closed instead of deleting unconfirmed mutation evidence.

## Required shared host hooks

The parent integration owns registration outside these files:

- Register both modules and the two Tauri commands.
- Call `reset`, `ready` (`hair_volume_protocol == 1`, `hair_volume_capability.available == true`), `ended`, and `project_reopened` alongside existing owned protocols.
- Call `blocks_mutation` before either ordinary or interactive sends; classify validated `read_only` commands before mutation invalidation.
- Admit `hair_volume` in epoch-bound dispatch and use `enqueue` for reads and writes.
- Call `observe_line` on raw stdout before generic JSON forwarding. Only its validated mutation marker may call the recovery fence and refresh document state. Add `guards_result` to owned-ID suppression and exclude `hair_volume_result` from generic fence settlement/document refresh.

## Authored validation coverage

Fixtures specify exact envelopes, independent confirmations, protection caps, retained source/evidence requirements, source-pixel geometry, PNG CRC/hash/dimension mismatches, ACK prerequisites, single-use commit, all four publication leaves, epoch/fence binding, unknown/late outcomes, native reopen provenance, missing-core neutral recovery, tombstone eviction, status non-authority, and duplicate JSON rejection. They have not been executed and are not a substitute for eventual full build, interrupted-flow, end-to-end current-photo, or photographic validation.
