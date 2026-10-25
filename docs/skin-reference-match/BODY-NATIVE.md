# Body-reference native transport

Status: AUTHORED / UNRUN. This change has received source inspection only. No
tests, build, typecheck, product launch, inference, downloads, hardware checks,
photographic validation or numerical acceptance were performed.

## One native lane, existing ownership

`ui/src-tauri/src/skin_reference_body_people.rs` owns the strict transport for
`lnx.skin_reference_body_match.v1`, inside the existing people mailbox. It does
not register another Tauri command, create another mutation/history owner,
introduce an image decoder, infer body regions, or add a colour solver. The
existing Rust selected-reference solver remains the only numerical path.

The only actions are:

- `skin_reference_body_catalog`
- `skin_reference_body_preview`
- `skin_reference_body_image`
- `skin_reference_body_confirm`
- `skin_reference_body_clear`

Native admission requires `people_protocol == 1` and the independent
`skin_reference_body_protocol == 1` ready capability. Native numerical
availability is a separate catalog value. In particular, an unavailable solver
does not erase retained state or make body clear unreachable.

## Exact current-photo context and consent

Every action captures the same eight fields into
`skin_reference_body_request`: action, payload, document ID, document epoch,
document revision, people state revision, association revision and target.
`cmd`, request ID and host epoch are transport fields, not additional members
of that echo. The existing receipt host compares the captured echo even on a
claimed safe refusal.

The target is exactly `{scope: all_people, target_id: effective source SHA-256,
face_ref: null}`. Neither an editing cursor nor a selected person grants
ownership. A preview selects one same-photo reference FaceRef, one target-owner
FaceRef and one exact target BodyRef. Reference and owner may be the same face;
one face instance with inconsistent analysis revisions is refused.

Manual body review has its own operation ID, points digest, BodyRef and four
affirmations: visible, unoccluded, ownership confirmed and reference unchanged.
Its source-normalized recipe accepts only bounded manual add/subtract brushes.
It cannot borrow a face-only, own-face body match, skin colour, evenness or
generic mask review. At least one enabled positive add stroke is required.

Limits include 64 source faces/target owners, 64 brush objects, 1–1024 points per
brush, 8192 total points, a 256 KiB native request/binding budget and an 8 MiB
receipt budget. The UI may impose a smaller request/point budget. IDs, numeric
ranges, independent brush axes and nonblank printable names are checked before
dispatch. These checks validate vectors; they do not rasterize them.

## Catalog, frozen review and publication

Catalog validation binds source dimensions/proof, decimal document revision,
source-review digest and a full-source bounded PNG. Every body target must
have a unique owner and BodyRef, exact source/orientation, points digest and
explicit association at the captured people-association revision. Target
eligibility is not the donor-face `available` flag. A target may have valid body
evidence while being unavailable as a face-skin donor.

A preview includes complete before/candidate body reports, support-bank hashes,
body-bank hash, source/owner proofs, exact manual consent, one candidate state
revision and full mixed before/after image metadata. Native validation requires
that the selected target is the only added/replaced row. Every other target
FaceRef, amount and support digest survives exactly, with the same common
reference. Reordering report arrays is not an edit.

Confirm uses only the frozen token and three-hash full-image ACK as input. Its
receipt includes the complete frozen `review`, in addition to selected-target
proof fields. Before dispatch, the existing native receipt ledger must still
contain one successful exact preview and both actual verified image receipts
for that context/token/review. Missing or released records fail closed and
require explicit re-review, not an automatic confirmation retry. The ledger
retains only one additional 64-character native digest beside the confirmation
record, rather than another review store or copied image set. This local digest
binds the parsed frozen review, including manual consent; it is not a substitute
for the engine's review SHA-256. A success carrying altered but structurally
valid consent becomes unknown instead of publication.

Native validation rechecks the review, each redundant selected
field, before/after ACK hashes, exact candidate bank and the complete published
body report. Document revision and state revision must each advance exactly
once; source, epoch and association revision must remain exact. The Python
host separately owns token expiry, served-image admission and live source,
analysis, graph, body-bank, support-bank and complete-render rechecks.

Clear proves an empty active body target/amount list and one exact publication.
Its cleared FaceRefs may include disabled, neutral or dormant body-owned rows.
An independently active face lane may retain a nonnull common donor after body
clear. This is not authority to change or clear the face lane.

PNG byte verification reuses existing pure validators: canonical base64,
4 MiB decoded limit, 1024-pixel edge bound, RGB PNG framing/chunk CRC and SHA-256.
No decompression or image inference occurs in native receipt validation. Source,
revision, context, metadata and scalar helpers are also reused without changing
the face operation's validation semantics.

## Failure and recovery boundaries

Reads cannot publish `doc_state`, emit a frame or become edits. A failed receipt
cannot carry a payload, document publication or emitted frame. A released read
is an exact terminal tombstone, not an image, preview or mutation ACK.

The existing receipt host can reconcile only the family's exact captured late
read after a transport unknown. A known terminal remains immutable. Confirm and
clear do not gain retry, cancel, reset or late-success reconciliation authority.
Unknown mutations stay in the existing recovery fence; unrelated mutations,
history/save/export and replacement clear requests cannot bypass it. Original
status queries and owned reads remain available. A bare attempted reopen does
not release the fence; a verified opened/created workspace or a new engine
epoch is required under existing recovery semantics.

The authored Rust fixtures cover wrong consent families, cross-photo/stale
BodyRefs, own-face selection, invalid vectors, changed retained targets,
candidate/report mismatch, donor-preserving clear, malformed PNGs, exact echo
capture, read tombstones, late read reconciliation, immutable unknown writes
and recovery-fence collisions. Additional fixtures cover absent preview, a
missing image side, wrong ACK and shape-valid replacement of captured manual
consent. They remain UNRUN.
