# Neck fine-line review UI

Status: **AUTHORED / UNRUN**. This is the isolated UI slice for
`control:PC-32464:19`, not photographic acceptance, official algorithm parity,
or an enabled product capability by itself. No test, build, typecheck, product
import/execution, inference, installation, download or hardware probe was run.
The recovered checkout has no root `README.md` or applicable `AGENTS.md`; the
complete requirement/design document and the existing relevant UI/host patterns
were read. Existing package scripts were inspected, not invoked.

## Integration boundary

Import `NeckWrinkleControl` from `ui/src/neckWrinkle`. Its props are
`{port?: NeckWrinklePort | null, blocked?: boolean}`. The parent alone registers
the panel, native action allowlists and canonical people receipt integration.
This directory does not import `native.ts`, own a second request queue, poller,
support bank, graph, undo stack, or cross-image transfer mechanism.

The injected port must have stable **application-lifetime identity**, not be
constructed when this collapsible panel opens. `getSnapshot()` returns a cached
immutable `NeckSnapshot`; `subscribe(listener)` observes the existing people
owner. `submitCaptured`, `check`, and `refreshCurrent` delegate to that same owner.
Pending and unknown outcomes survive panel close, unmount, photo changes, and
later remount. Closing clears only local review drafts. It never retries a write,
claims cancellation, or removes the owner's unresolved receipt. Do not wire a
temporary native adapter that loses pending state when the panel disappears.

The snapshot contains `value: PeopleView|null`, `enabled`, `pending`, `uncertain`,
optional `refreshRequired`/`message`, `lastResult: NeckReceipt|null`, optional
`report: NeckReport|null`, and `capability: {protocol?, available?, reason?}`.
Missing protocol/capability is unavailable, not an implicit ready state. Reference
reads require protocol 1; nonzero preview/confirm also require `available:true`.
`blocked` adds the application's existing conflicting-edit/export fence.

Read and image validators are exported from `model.ts` for canonical-owner
integration. The UI validates bytes before displaying a reply, but this does not
replace owner-side validation. In particular, the owner must validate returned
canonical `doc_state`, exact action/request/document/source/FaceRef fences and
post-write amount/support state even if the panel has unmounted. A malformed or
uncertain write is fenced and reconciled by querying its original request ID,
not by a second dispatch or by treating refresh as proof of non-execution.

`validWriteResult(command,result,capturedBeforeView,frozenPreview?,inspectedAck?)`
is the dedicated post-state guard. Confirm requires the owner's cached exact
preview and matched-pair inspection ACK. It checks explicit face-local amount,
`doc_state.people.neck_wrinkle`, retained attachment state for a neutral-only
reset, atomic detached/zero state, unchanged association and non-neck visible
state. The canonical owner still owns publication and receipt-query decisions;
this helper does not itself mutate or reconcile the document.

## Exact commands

All commands use the existing people envelope: `document_id`, `document_epoch`,
`document_revision`, `state_revision`, `association_revision`, `request_id`, and
the exact current face-scoped `target`. The UI does not submit raw masks, image
paths, arbitrary source arrays, hashes as source authority, or donor support.

- `neck_wrinkle_reference`: `{}`.
- `neck_wrinkle_preview`: `{review, amount}`. Amount is explicitly chosen in
  `(0,1]`; blank and zero do not create a nonzero candidate.
- `neck_wrinkle_crop`: exactly one of
  `{reference_id, plane:'source', rect:[x,y,width,height]}` or
  `{preview_id, plane:'before'|'after', rect:[x,y,width,height]}`.
- `neck_wrinkle_confirm`: `{preview_id, reviewed:true, before_sha256,
  after_sha256, support_sha256, inspection:{rect, before_sha256, after_sha256}}`.
- `neck_wrinkle_detach`: `{}`. This operation atomically writes amount zero and
  removes only this person's neck pointer; immutable support history remains.
- The existing `patch` action is used only for an explicit face-local
  `lnx.neck_wrinkle.v1` `/amount` value of zero. It does not unset overrides or
  reactivate inherited intent. The existing `select` action picks an actual
  retained FaceRef, not a row-number-derived or synthetic face.

Requests are rejected before dispatch above 192 KiB. Vectors are never silently
decimated or truncated to fit. Source and output crop rectangles are integer
pixel-edge coordinates, positive in-bounds extents, at most 1024 per edge, with
no resizing. Exactly one immutable reference/candidate ID accompanies each crop.

## Exact result DTOs

`NeckImage` has only `mime:'image/png'`, `base64`, `width`, `height`, `sha256`.
Display PNGs are bounded to 1280 pixels per edge and 4 MiB; the coordinated host
uses a conservative 1152 edge. Native inspection PNGs are at most 1024 per edge
and exactly match their rectangle's width and height. SHA-256 is over the PNG
bytes, not an invented source-pixel claim. The UI verifies canonical base64,
signature, IHDR dimensions, SHA-256, subsequent browser decoding, and visible
presentation. Image loading never checks the user's consent boxes.

All reference/preview/crop results carry the exact family
`neck_wrinkle`, operation `lnx.neck_wrinkle.v1`, `source:{sha256,width,height}`,
existing `source_proof:{asset_sha256,original_sha256,creative_source}`, and
host-owned 64-hex `input_sha256` plus `repair_sha256`. These bind the actual full
effective input and exact repair stack; they are not accepted from UI input.
Returned creative-source pixels must have their own actual asset/dimensions;
the physical original is provenance only.

- Reference: `kind:'reference'`, `reference_id`, `face_ref`, `bodies`,
  `source_image`, `attached`, plus the common fields. Each body choice has exactly
  `body_ref` and `points_sha256`. Zero choices is an honest unavailable review;
  duplicates, mismatched sources or over 64 choices refuse.
- Preview: `kind:'preview'`, `preview_id`, `face_ref`, exact `review`, `amount`,
  `before`, `after`, `support`, `before_output_size:[width,height]`,
  `after_output_size:[width,height]`, `runtime_quality_accepted:false`, plus the
  common fields. Full output dimensions must match before/after. The complete
  display images must preserve the full output frame. Support is a full-source
  overlay, not remapped retouched/cropped output.
- Crop: `kind:'crop'`, the one request ID field, `plane`, exact `rect`,
  `domain:'source'|'rendered_result'`, `image`, plus common fields. Source is the
  only source-domain crop. Both before and after are rendered-result crops.
- Confirmed: `{kind:'confirmed',family,operation_id,attached:true,amount}`.
- Detached: `{kind:'detached',family,operation_id,attached:false,amount:0}`.

These DTOs use strict field checks. A host extension must be coordinated before
adding fields. Result `source_image` is the final agreed spelling; do not use the
earlier proposed `source_preview` spelling. `support_sha256` in the confirmation
is the exact displayed support PNG digest, not the immutable support-asset key.
The host additionally fences complete float-render hashes and its canonical
support store; displayed image hashes alone are not source authority.

## Independent neck review

The review shape is the design's exact outer `body_ref`, `points_sha256`,
`recipe`, `visible:true`, `unoccluded:true`, `ownership_confirmed:true`, and
`neck:{version:1,domain:'source-normalized',line_half_width,protect_recipe,
protections_reviewed:true,visible_neck_skin_reviewed:true}`.

The source editor starts empty. It supports manually painted neck/context
add/subtract strokes and a separate hard-protection stack. Protection strokes
are enabled opaque unfeathered `add` brushes only; no subtract, disabled,
partially opaque or feathered veto can be undone by later positive painting.
Removing a protection stroke is an explicit local draft edit that invalidates
all prior confirmations. The draft has no persisted history or second undo
owner. At most 64 strokes per stack, 1024 points per stroke and 4096 points across
both stacks are authored by this UI. Reaching a limit stops adding points and is
disclosed rather than silently simplifying geometry.

The actual FaceRef is selected through the canonical people owner; an associated
BodyRef is explicitly chosen from that source-bound reference. No nearest-chin,
pose outline, hidden-skin fill, demographic restriction, or another feature's
review authorizes neck pixels. Manual vectors map full-source pixel edges.
Painting on a true source crop maps that crop back to full-source normalized
coordinates. Rendered-result crops are never accepted by the source editor.

Observed line half-width starts blank. A verified, visibly displayed native
source crop is required before entry/confirmation. The explicitly entered
1.4–12 source-pixel half-width is serialized as a fraction of the canonical
short side, never of face size, brush radius, display size or pose. The UI labels
thumbnail pixel 1:1 honestly and does not call it source 100%. No synthetic image
or inferred contour is provided when the actual source is unavailable.

Separate unchecked confirmations cover actual visibility, occlusion review,
same-person ownership, observed visible neck/scale, and hard protections. The
empty-protection text explicitly acknowledges reviewed-none without asserting
the scene has no occluders. The UI names jewelry, clothing, hair/beard, tattoos/
marks, hands, other people, Adam's-apple/tendon edges, jaw/collarbone structural
shadows and undesired lines. There is no instance/jewelry segmentation claim.

## Candidate and 100% inspection

Preview stages a private candidate; it does not change the live graph. Full
mixed before/after images retain the other existing effects, not merely a
single-operator mockup. The independently returned support image must truthfully
show cyan final admissible region, magenta hard protection and orange
context-rejected region after the detector's full finite sampling requirement.
A generic body-skin/manual-brush overlay must not be labeled final admission.
If the host cannot produce that image, review remains unavailable.

All three whole-frame display PNGs must verify, decode and become visibly
presented. The user then explicitly picks a bounded output rectangle and loads
both exact native-pixel before/after crops. The pair must match candidate,
source/repair, rectangle, domain and dimensions. They display at one CSS pixel
per image pixel, with scrolling rather than downsampling. A separate unchecked
inspection acknowledgement discloses that only this rectangle, not the entire
photo, was inspected at 100%. The final unchecked acknowledgement independently
accepts the full mixed candidate. Both acknowledgements and all image identities
are checked again at click time before sending the exact ACK payload.

Amount, geometry, protection, body choice, observed scale or confirmation changes
invalidate the candidate. Source/FaceRef/document/association/people-state changes
remount the local review session; the application-lifetime request owner remains.
Old async hashes, stale image callbacks, hidden-document acknowledgement, different
crop positions with identical PNG bytes, repeated clicks and released-image
receipts cannot silently authorize a different candidate. Cancelled pointer
gestures are not committed as strokes. A crop of a deformed output never becomes
source-painting geometry.

## Verification still required

`review.unrun.test.ts` contains authored, **never executed** structural fixtures
for explicit scale/amount, independent consent, hard-protection constraints,
bounded vectors, source/body mismatch, crop pairing and exact confirmation
hashes. Its metadata-only image objects are deliberately not valid photographs
or PNG acceptance fixtures.

Still UNRUN: TypeScript/build, DOM/layout, actual browser decoding and painting,
visibility/scroll and pointer cancellation, stale/duplicate callbacks, owner
unknown-result reconciliation, crop/repair/derived-source round trips, canonical
write post-state, undo/redo, save/reopen, missing backend/stale neutral reset and
atomic detach, real portraits, fine-line/pore/occluder quality, full-size export,
and peak memory. No authored fixture or static file/hash check closes the
handbook leaf or establishes photographic acceptance.
