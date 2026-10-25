# Native people-mailbox validation

Status: **AUTHORED / UNRUN**. This change is source and authored Rust fixtures
only. No tests, test collection, product imports, build, typecheck, inference,
image decoding, installation, download or photographic acceptance was run.
Static source inspection is not runtime or numerical verification.

Implementation: [`skin_reference_match_people.rs`](../../ui/src-tauri/src/skin_reference_match_people.rs).
Engine payload owner: [`skin_reference_match_host.py`](../../engine/src/lumaretouch_engine/skin_reference_match_host.py).
The numerical, source-ownership and support contracts remain in
[CORE.md](CORE.md), [SUPPORT.md](SUPPORT.md), [RUNTIME.md](RUNTIME.md) and
[NATIVE-HOST.md](NATIVE-HOST.md).

## One existing command and receipt owner

This family uses the existing `people` command, `people_result` receipt,
`ReceiptHost` mailbox, engine epoch and project-recovery fences. It adds no root
command, history owner, ledger, support store, numerical fallback or portable
reference recipe.

Exports for the existing people integration:

- `ACTIONS`, `MARKER`, `action(value)` and `command(value)` classify and validate
  the five exact actions.
- `binding(value)` captures one immutable `skin_reference_match_request`.
- `read_only(value)` validates a complete engine command before classifying
  catalog, preview or image reads. Confirm and clear are always writes.
- `receipt(value)` validates this family's replies; `valid_result(value)` is its
  alias. Non-family receipts are left to their original validator.
- `released_read(value)` recognizes a known-success read tombstone only.
- `image(value)` checks the bounded PNG transport, not decoded image pixels.

The people integration calls `begin_command`, not `begin_bound`, for all five
actions. Its existing `ReviewBinding` retains the returned fields with
`strict_failure_identity: true`. Exact echo equality against that retained
capture is a mailbox responsibility, including failed replies. A shape-valid
echo supplied by a result is not proof that it is the original request.

Read-only classification is also wired through the existing `engine.rs`,
`native_dispatch.rs`, `project_recovery_fence.rs` and
`preset_alias_recovery_fence.rs` paths. `receipt_host.rs` captures the strict
identity and permits bounded eviction of these reads. Its narrowly scoped late
read reconciliation requires the original exact binding and a validated known
terminal result. A read cannot erase or release an outstanding mutation fence.
Unknown confirm/clear outcomes remain query-only under the existing request
identity, never a reason to replay a write or reopen mutation authority.

`people_api.rs` requires ready capability `skin_reference_match_protocol:1`
separately from the numerical library's availability. A protocol-capable engine
can therefore explain a missing native extension or clear an existing effect
without pretending that active numerical processing is available.

## Request identity and action payloads

Every request carries the existing document ID, epoch, document revision,
people-state revision and association revision. The target is exactly:

```json
{"scope":"all_people","target_id":"<current effective asset SHA-256>","face_ref":null}
```

This target intentionally does not depend on the face-editing cursor, selected
person or group. Both native validation and engine source verification reject
another photograph. No request can substitute a single-face target to borrow
another effect's review.

The five action names and exact payloads are:

1. `skin_reference_match_catalog`: `{}`.
2. `skin_reference_match_preview`: `{version:1, reference_face_ref,
   target_face_refs, amount, source_review_sha256, ownership_confirmed:true}`.
   Amount must be finite and strictly greater than zero through one. The
   reference and every target must have exact three-field FaceRefs from this
   asset. Targets are a distinct nonempty list, and none can be the reference,
   including the same instance with a changed analysis revision.
3. `skin_reference_match_image`: `{token, side, sha256, review_sha256}`.
   Side is exactly `before` or `after`.
4. `skin_reference_match_confirm`: `{token, ack:{review_sha256,
   before_sha256, after_sha256}}`.
5. `skin_reference_match_clear`: `{}`. Neutral changes use this explicit write,
   not an amount-zero preview that might bypass evidence.

The captured `skin_reference_match_request` has exactly eight fields: action,
payload and the six existing context fields. `cmd`, `request_id` and
`host_epoch` are not duplicated inside it. The outer mailbox retains the
original request ID and engine epoch. Successful and failed replies must carry
the exact captured request; a generic claimed payload kind is insufficient.

## Catalog and source bytes

The catalog proves operation `lnx.skin_reference_match.v1`, current-photo
face-only scope, current document/revision and exact effective-source proof.
It contains canonical source dimensions, a display-only full-source PNG with
actual byte hash, the source-review digest and the complete bounded face list.
Creative-source dimensions must agree with the canonical source dimensions.

Each face has a same-source FaceRef, finite normalized nonempty box, explicit
enabled/available flags, reason and scalar amount. IDs are unique. Available
faces must be enabled, and an unavailable face must give a nonempty reason.
Boxes locate the overlay only; they do not establish skin ownership. The
catalog explicitly forbids body matching and automatic reference selection.
Native-capability availability also carries a consistent null/nonempty reason.

`current` is the source-wide report, independent of the editing cursor:

```text
{version:1, operation_id, reference_face_ref, target_face_refs,
 amounts:[{face_ref, amount, support_sha256}], bank_sha256}
```

An inactive report is exactly a null reference and empty target/amount arrays.
An active report has one distinct reference and one positive amount/support
hash per unique target, with no omitted or extra target. Catalog target amounts
are reconciled with enabled catalog faces. A disabled retained face may still
have a dormant scalar; it is not a current active target.

The engine owns authentication of actual immutable source bytes, retained
landmarks, named face-skin evidence, complete face inventory and source-review
digest creation. Native source-image framing and hashes cannot establish those
facts by themselves.

## Full mixed preview

A preview success has exactly `{kind, review}`. Review version, operation,
session token, owner, canonical source, selected reference, ordered complete
target list, amount, source-review digest and next state revision are validated
against the captured request.

The owner is the existing six-field transfer proof: exact document/epoch/revision,
people scope, state and association revisions, graph hash and effective-source
proof. Scope may be the current document or project. This does not authorize
additional source-identical documents; the engine separately refuses an
unreviewed alias closure.

The review also carries the prior complete active target set, before/candidate
canonical support-bank digests and a support-hash map whose keys are exactly
the selected target instance IDs. No omitted, extra or foreign target is admitted.

Its `visual` is a full mixed before/after proof, not a face crop: current
document/revision, effective-source proof, canonical source size, identical
before/after output geometry, before/candidate complete-state hashes and people
hashes, and two compact image records. Inline image bytes or unrecognized fields
in that proof are refused. Compact dimensions must match the existing
`portrait_review_render.preview_size` round-half-even 1024-edge reduction.
No native validator claims that these opaque fingerprints prove rendered quality.

## Image and publication receipts

An image reply must match the exact token, side, PNG hash and review hash in
its captured request. The returned image's actual byte digest must match that
hash. A previous photo, opposite side or unrelated review is not acceptable
merely because its payload claims `skin_reference_match_image`.

Confirm success must echo the exact token/acknowledgment, provide the selected
reference, complete target set, positive amount, per-target support map,
candidate support-bank hash and candidate state revision. The accompanying
`doc_state.people` must prove:

- Same document, epoch and effective asset as the captured request.
- Exactly one document revision and one people-state revision advancement.
- Unchanged association revision and exact candidate state revision.
- The complete source-wide report contains the same reference, targets,
  per-target amounts and support hashes, and the exact candidate bank digest.

Current report ordering is canonical by face ID, while preview order is the
user's captured order. Confirmation therefore compares unique exact FaceRef
sets and per-face values, never detector indices or approximate identities.
The editing cursor and its resolved single-face operation are not authority
for this multi-target receipt.

Clear success requires a nonempty same-source list of cleared faces, the same
exact publication revision/binding rules and a final report with no active
reference, targets or amounts. Cleared faces may include dormant support or
scalar leaves. The engine remains responsible for enumerating/removing the
complete current-photo relation; a generic empty success is rejected.

Read successes must not carry document state or emit a frame. Failures retain
their exact request, bounded diagnostic and known/unknown flag but must not
carry success payloads or stale document state. Extra receipt families,
non-null created/batch identities and unrecognized fields are rejected.

## Released reads and limits

The engine may release cached display payloads while retaining their original
known-success receipt. A released tombstone has exact terminal fields, the
original captured request, `payload_released:true`, no payload/document state,
no emitted frame, null error/created/batch identities and `outcome_unknown:false`.
Only read actions qualify. This preserves historical read status, not usable
source review, pixels, image acknowledgment or mutation authority. Confirm
and clear can never be released this way.

Bounds are compatible with the existing people mailbox:

- 256 KiB serialized request; 8 MiB serialized result.
- At most 64 catalog faces and 63 distinct selected targets.
- Clear can name all 64 retained faces, including dormant relations.
- Canonical dimensions are positive `u32`; compact PNG dimensions are 1..1024.
- PNG payload at most 4 MiB; canonical base64 at most 5,592,408 bytes.
- Lowercase 64-hex digests and 32-hex session tokens.
- ASCII people identifiers are 1..128 bytes using the existing identifier alphabet.
- Numeric revisions are nonnegative safe integers through 2^53−1; decimal
  visual revisions must be the exact canonical string for the captured number.
- Diagnostic strings are nonempty, at most 4096 bytes and contain no NUL.

PNG admission checks canonical base64, digest, signature, chunk bounds/CRC,
IHDR dimensions and the host's 8-bit RGB format through the existing strict framing helper. It
does not decompress the image. The WebView must decode the actual images and
observe successful loading before permitting acknowledgment, and the engine
must verify its own immutable frozen image pages and served sides. There is
no new image decoder, image-model execution or inference in this native family.

## Authored fixtures

The inline Rust fixture module covers exact all-people targeting, explicit
positive amount/consent, duplicate/foreign/reference targets, strict fields and
bounds, read classification, immutable request capture, source/owner/full-visual
mismatch, incomplete support maps, report order independence, exact publication
fences, clear with no active targets, missing failure identity, stale failure
payloads, canonical PNG transport, catalog availability consistency, exact
image token/side/review matching, read tombstones and mailbox preservation of
unknown mutation outcomes after changed echoes or old-document successes.

All fixtures remain **UNRUN**. The existing host/runtime/photographic gates,
real PNG decoding, complete UI interaction, native packaging and engine/native
integration still require authorized execution; these source-only fixtures do
not claim any of those results.
