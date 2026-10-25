# Current-photo face-reference matching UI

Status: authored and statically inspected only. Tests, typecheck, build, browser interaction and real-photo acceptance are UNRUN. This is a partial face-skin colour and brightness match, not automatic brightest-face selection, body matching, identity recognition or a new body AI algorithm.

## Ownership and integration

`SkinReferenceMatchPanel({people, blocked, available})` owns ephemeral UI drafts only. `people` is the established `PeopleOwner`; there is no module-local transport, pending queue, graph, root command or history stack. `available` represents the dedicated protocol being present, not native matching readiness. The catalog's independent capability flag gates candidate creation while read/clear remain available when supported.

Every action is captured with the current document ID, epoch, document revision, graph revision and association revision. The target is exactly `{scope: 'all_people', target_id: binding.asset_sha256, face_ref: null}`. It never inherits the editing cursor. The UI binding includes all measured face records and source/document fences but not the selected cursor itself.

The parent admits the action family, validates exact request echoes before refreshing, retains a frozen preview for confirmation, and exposes only validated `lastSkinReferenceResult` receipts. `PeopleView.skin_reference_match` uses the exported `SkinReferenceCurrent` report, including the canonical bank digest. Existing document history remains authoritative.

`reviewGuard.ts` is a proof guard inside that existing owner, not another queue. It captures the pre-request view, keeps only hash-verified current catalogs, and records the two verified image sides for the frozen preview. Read receipts cannot contain a document or frame and do not request a mutation-style refresh. A completed mutation whose current status is still stale erects `skinReferenceRefreshRequired`: all further people submissions/patches for that document wait for actual status to reach the proven revision. `refreshCurrent()` is a readback only, never resubmission. Unknown results retain the original pending ID through the existing mailbox.

## Review stages

1. Catalog returns a real immutable source PNG with its byte digest, source proof, full-source dimensions, source-review digest and complete numbered face boxes. The PNG is byte-verified before display; its browser-decoded dimensions and visible presentation gate ownership confirmation. Boxes are normalized left/top/right/bottom on the uncropped source. No source thumbnail is manufactured from the current edited preview.
2. The user chooses a donor and a nonempty unique target list, then enters a strength above 0 through 100. Nothing is automatically selected. The donor cannot be a target. Unavailable faces disclose their reason. An explicit checkbox binds the user-observed source, donor and target list before preview; displayed labels are measured face indices, not inferred names.
3. Preview freezes the chosen reference, exact ordered target list, positive strength, source-review digest, owner, support bank, support digests and complete render proofs. It replaces the current operation's target list instead of accumulating. Previously active targets removed by replacement are disclosed.
4. Both full mixed before/after PNGs are fetched through the same people owner. Their token, side, review digest, byte SHA-256, PNG header dimensions, expected scaled extents and actual browser dimensions are checked. Actual visible presentation of each image gates a separate, never-automatic final ACK.
5. Confirmation submits only the frozen token and exact review/before/after digests. The proof and native post-state must match bank, donor, target set, per-target amount and support digest, with exactly one document and graph revision advance. Native report ordering may differ from preview order; membership and all per-face values may not.
6. Clear removes this operation's current-photo relations, requires an exact successful neutral post-state and uses existing history. Zero strength is not a hidden clear command.

The images are bounded display reductions up to a 1024-pixel edge and 4 MiB PNG; they are not original-resolution quality acceptance. Source and output geometries are separately identified. The selected reference and unselected people must still be inspected in the mixed review for unintended changes.

## Validation API

- `isSkinReferenceAction(action)` and `echoMatches(command, result)` identify the exact family and semantic captured request, including payload and target.
- `receiptCurrent(command, result, view)` fences validated reads to exact current revisions; mutation display receipts permit forward revisions only after strict confirmation/clear validation.
- `validCatalog(payload, view)` and `catalogImage(catalog)` validate catalog/source metadata and byte identity. The latter is asynchronous.
- `validPreview(payload)` and `validReview(review, view, preview)` bind explicit source ownership and the frozen candidate.
- `validImageReceipt(payload, command)` validates the page response against the exact capture. `reviewImage(payload, review, side)` additionally checks the frozen visual and bytes asynchronously.
- `ack(review)`, `sameAck(value, expected)`, `validConfirmation(review, result)` and `validClear(command, result)` implement exact mutation proof checks.
- `validCurrent(report, view)` validates the public native report without inventing a secondary graph.
- `validReleasedReceipt(command, result)` permits exact released read receipts only, never a released confirm or clear.

All failures remain fail-closed. The people owner retains uncertain request IDs for original-result queries. The panel never automatically resends mutations or turns malformed receipts into success. Draft changes, source changes, hidden-tab transitions and unmount invalidate appropriate image-view/ACK state; the user must explicitly acknowledge again.

See `ui/src/skinReferenceMatch/ACCEPTANCE_UNRUN.md` for the unrun interaction matrix, `model.unrun.test.ts` for authored protocol fixtures, and `reviewGuard.unrun.test.ts` for owner/admission/recovery fixtures. None were executed.

Unknown writes have no dedicated verified workspace-retirement protocol here.
Query the original request without resend. If its terminal proof remains
unavailable, full application restart and known saved-project reopen may be
needed; merely reopening a photograph does not establish that the old write
failed, and unsaved changes may not survive. No automatic pending reset added.
