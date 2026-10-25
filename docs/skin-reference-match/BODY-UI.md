# Selected reference face to independently reviewed body UI

Status: source authored and manually inspected only. All tests, typecheck, build, browser interaction, engine execution, inference, real-photo and hardware acceptance are **UNRUN**. This is the body-only lane of control:PC-32465:19, not a new colour algorithm or automatic body segmentation.

## Module and ownership

- `ui/src/skinReferenceBody/SkinReferenceBodyPanel.tsx` exports `SkinReferenceBodyPanel({people, blocked, available})`. It owns temporary selections, brush vectors and explicit review checkboxes only.
- `model.ts` owns the exact `lnx.skin_reference_body_match.v1` request, catalog, independent body consent, frozen review, image ACK and post-state validators.
- `reviewGuard.ts` exports `createSkinReferenceBodyReviewGuard()` and `isSkinReferenceBodyRead()`. This adapter runs inside the existing canonical `PeopleOwner`, with no transport, poller, pending queue, publication path or history of its own.
- `ReviewedImage.tsx` owns this panel's local decoded/visible presentation state. The generic immutable PNG verifier is reused, never another operation's proof or consent.
- The only body-family UI primitive reused is `SkinBodySourceEditor` and its source-normalized brush type. No `bodyReview()`, `SkinBodyPanel`, old-family confirmation, face-reference controller or old-family support token is reused.
- Existing `SkinReferenceMatchPanel` and face v1 schema are unchanged.

The shared people model adds `SkinReferenceBodyAction`, `skin_reference_body_request`, `skin_reference_body_match` and an operation label. The existing workflow adds one independent guard, `lastSkinReferenceBodyResult` and `skinReferenceBodyRefreshRequired`. The existing hook checks `skin_reference_body_protocol === 1` before admission. Protocol availability is distinct from installed native matching readiness; catalog capability may prohibit preview while read/clear remain reachable.

Every request uses the current photograph's exact all-people envelope: document ID, epoch, document revision, people state revision, association revision and `{scope: 'all_people', target_id: asset_sha256, face_ref: null}`. Editing cursor changes do not grant ownership and do not change this envelope. Measured face changes, confirmed-link changes and source/revision fences invalidate drafts.

## User flow and boundaries

1. Read this operation's real immutable full-source PNG, byte digest, source proof, complete measured face list and explicitly eligible owner/body list. Source PNG dimensions/bytes and visible browser decoding must pass before source ownership can be acknowledged. The PNG is a full-frame reduction, not the edited preview or an ALIGN8 pose preview.
2. Select an actual same-photo reference face and one target `FaceRef`/`BodyRef` pair. No selection or strength is prefilled. Owner and reference can be the same face. A body target need not have usable donor face skin: `faces.available` describes reference eligibility, while the independently verified `targets` list describes body eligibility.
3. Check the explicit person/body association against the people graph. Numbered rectangles are owner **face** boxes, never inferred body boxes. Paint the target's visible unoccluded body skin on the immutable full source using add/subtract brushes. No nearest-body, semantic instance or anatomy completion is claimed.
4. Separately acknowledge this operation's visible skin, absence of occlusion, actual reference/owner identity and protected-reference condition. The exact manual review carries this operation ID, body reference, pose digest, bounded recipe and four true flags. A generic body-family or face-only approval cannot substitute.
5. Preview one target at a time. Its body amount/support are replaced; other active body targets and their amounts/support remain unchanged. Current face/body matching uses one common selected donor. A face-lane donor may therefore be disclosed even when the body target list is empty. The UI conservatively keeps that donor until relevant active matching is explicitly cleared in the corresponding panel. Clearing bodies never clears face matching.
6. Fetch both complete actual mixed before/after PNGs through `PeopleOwner`. Match token, side, review hash, PNG digest, header dimensions, expected whole-output reduction and real browser decoding. Then require a separate explicit final ACK tied to this exact image pair.
7. Confirm only the frozen token and ACK. The returned proof includes the complete unchanged frozen review, selected owner/body, candidate report, support hash, common donor and exact native document/people revision advances. Retained target rows must match exactly. No face operation is enabled, even for donor=owner.
8. Clear is reachable without a catalog or new source/body preview and removes only this body's reference-matching lane on the current photo. The native report must have empty body target/amount lists; a donor retained by the face lane is valid. Existing photo history remains the undo/redo authority.

Source and mixed review displays have a maximum 1024-pixel edge and bounded PNG bytes. Enlarging them does not supply original-size detail. UI copy explicitly disclaims original-resolution/visual-quality acceptance, strongest-value equality, a new AI algorithm and identity recognition.

## Fail-closed review lifecycle

The full frozen review binds source proof, manual body recipe/consent, actual `BodyRef`, body-bank digest, current/candidate support-bank digests, complete before/candidate body reports, exact owner and full mixed visual metadata. Source-catalog review IDs and body-bank/live association checks remain host-owned. Public current reports retain metadata even when live evidence is stale so clear stays reachable.

Read replies cannot include a mutated document, frame or batch. All successful and failed replies require the original exact eight-field captured request echo. Released payloads are allowed for terminal reads only, never confirm/clear. Image bytes are checked in both the owner admission guard and panel display route. Final ACK is never inferred from loading or from another family.

Changing selection, amount, brush strokes, source, ownership or engine revisions invalidates consent/candidate state. Hidden tabs clear observed-image and explicit ACK/consent state. Unmount clears local callbacks/drafts but does not cancel the canonical pending owner. Duplicate submissions are rejected by that owner, not redirected into another queue.

A confirmed mutation whose engine status is still stale fences all further people submissions and queued scalar changes for that document. `refreshCurrent()` only reads status; it never resends the mutation. Unknown requests retain their original ID for query. There is no newly invented workspace-retirement/reset flow: if no terminal result can be recovered, full application restart and known saved-project reopening may be needed. Merely reopening a photograph does not prove the old write failed, and unsaved work may not survive.

## Authored acceptance, all UNRUN

`ui/src/skinReferenceBody/model.unrun.test.ts` covers independent consent, same-person and different-person references, cross-photo/stale refs, bounded manual brushes, explicit associations, body-only owners without donor face-skin eligibility, real PNG page identity, complete target retention, captured body recipe, exact post-state and clear with face-lane donor retained.

`ui/src/skinReferenceBody/reviewGuard.unrun.test.ts` covers catalog-before-preview admission, cross-family rejection, both-images-before-confirm, ownership invalidation, read-with-write rejection, immutable mutation receipts, stale-status fencing and canonical owner read/uncertainty handling without resend.

Still requiring actual execution after authorization: TypeScript/build and authored tests; complete browser source/brush/scroll/decode flows; duplicate click, interrupted pointer stroke, tab hide/show, panel collapse/unmount, navigation/back/forward and source replacement; source reanalysis and person/body unlink during review; stale and released reads; known-failed and unknown-write recovery; native missing capability; shared-source refusal; mixed face/body saved-project/history/export preservation; and before/after real-photo skin-edge, all-face protection, unselected target and background acceptance. None is claimed passed.
