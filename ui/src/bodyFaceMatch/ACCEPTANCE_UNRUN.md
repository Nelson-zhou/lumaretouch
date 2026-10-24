# Body toward own-face chroma matching: partial source implementation, acceptance UNRUN

## Exact scope

- Requirement `LNX-REF-PC-32465-C-d8b09012a9`, exact official leaf `PC-32465|肤色统一（身体）`, source https://www.pixcakeai.com/guide/32465. Visible label: **身体向本人脸部色度匹配（手绘审核）**.
- Operation `lnx.body_face_match.v1`, exactly `{version: 1, amount: 0..1}`. Display 0–100 is product policy, not official calibration. This does not implement the separate own-body evenness or face-evenness leaves, and does not imply full skin-family acceptance.
- Only independently reviewed visible body skin is edited, toward that same person's measured face reference. There is no arbitrary donor/reference-face selector, cross-person reference, reference RGB copy, brightness matching, or automatic body-skin instance segmentation. No learned-AI, proprietary-equivalence, physical-lighting decomposition, makeup-awareness or accepted photo-quality claim.
- The numerical reference is the immutable effective source **before portrait effects**, including verified frozen repairs when present. Effective source may be an original or an already returned composite. It is not necessarily raw unretouched pixels and is never the face after later whitening, rosiness or other portrait effects. The operation preserves actual input linear luminance at its own stage, not the final result after other effects. RGB SDR only.

## Independent ownership and first use

- Dedicated capability `body_face_match_available` / `body_face_match_reason`; family `body_face_match`; descriptor `body_face_match_visibility`; report `people.body_face_match`. Colour, finish and body-evenness reports/actions cannot authorize this family. Existing untagged colour and tagged finish/evenness payloads retain their previous semantics.
- Source/document/state/association/FaceRef ownership, selected-target membership, enabled verified analysis, valid resolved provenance, and the canonical people request owner remain required for active changes. Shared scopes expose explicit intent separately from selected-face effective values; blank is not zero or copied inherited intent. Engine admission must verify every active target, not rely on the selected person's UI report.
- Direct positive scalar writes require an attached current own-family review plus exact target-owned `own_face_reference` identity. That metadata includes exact FaceRef, original producer observation, landmark digest and `effective-source-stage-own-face-robust-log-chroma`; it does not prove render observability or quality.
- First use stages only a private `{review, amount > 0}` candidate. The review has a real associated BodyRef, body-points digest, new source-normalized add/subtract strokes, and independent visible/unoccluded/ownership confirmations. No active scalar is persisted before confirmation.
- `body_face_match_reference` supplies raw `source_preview` for body painting and separate `reference_overlay` displaying the **actual sampled source stage** in magenta. `reference_source_stage` is exactly `immutable-source` or `verified-repair-base`. `reference_support` identifies the same source/face/producer, bounded proxy-grid window, support/sample counts and protected foreign-face count, with `runtime_quality_accepted: false`.
- The reference overlay must load at declared display dimensions and be explicitly accepted before candidate generation/confirmation. The UI states actual decoded and display dimensions: this is a review proxy, not a 100%/full-resolution measurement. Full-source numerical reference is recomputed independently for the real candidate and export.
- Preview echoes the exact disclosed reference identity, source stage and proxy support facts; these remain separate from the independently recomputed full candidate. The existing body overlay is raw source-space cyan support, not a magenta overlay on unretouched pixels. The sampled-source reference disclosure remains visible alongside before/after/body-overlay review.
- All three actual comparison images must load at declared sizes; unchanged body/amount draft and separate explicit acceptance are required. Confirm sends only `{preview_id, reviewed: true}` and publishes the exact support plus amount atomically as this face's independent override, not a person/group/all default.
- Amount, geometry, person, source, analysis, owner, membership, resolved state, review identity or acceptance changes invalidate drafts. Review-session, canvas, preview-ID, mounted-state and draft-snapshot fences discard late image callbacks across close/reopen, new references and changed candidates. Unknown outcomes query the original request rather than resend. Closing does not claim to cancel an already sent request.

## Neutral recovery and batch coverage

- Reset writes exactly `/amount = 0` for this operation and current owned target. It does not restore inheritance, detach support, clear other scopes, change older smoothing or neighboring skin effects. It remains available without usable reference/support/anatomy/core/readback, subject to current owner and idle/known request state. Other active targets can still cause engine refusal.
- Detach requires authoritative selected-face amount zero and removes only this family's review. It cannot silently reset or restore shared/inherited values. Retained stale support remains removable after verified neutral recovery.
- `body_face_match_coverage` is `{version: 1, support_transfer: 'none', targets: [...]}`. Each active target has exact `face_ref`, `scope: 'reviewed-body-own-face'`, its own review digest and `own_face_reference`; neutral targets have `scope: 'neutral-no-effect'` and both digest/reference null.
- Coverage validates exact target membership and owned source/face/producer identity, rejects extra fields/pixels/masks/reference colours/donor identities, and never borrows the other three families' coverage. UI visibly identifies each target's own reference and preserves target refusal explanations. Only the scalar amount is synchronized; masks, reference samples and identity links are not transferred.

## Authored fixtures and limitations

- `model.unrun.test.ts`: exact leaf/operation/recipe, dedicated capability, authority/provenance, shared intent, owner/member fences, attached-review/reference independence, neutral recovery, binding invalidation and no graph mutation.
- `bodyReview.unrun.test.ts`: tagged actions, first-use positive amount, exact review/body/source matching, actual reference overlay/producer/source-stage validation, echoed proxy facts/identity, correlated and released receipts.
- `reference.unrun.test.ts`: strict reference metadata/observation schema, donor/source/stage substitution rejection, bounded decoded-grid windows/counts, no pixel/colour/mask transport.
- `wiring.unrun.test.ts`: exact route, unchanged adjacent families/legacy, canonical request owner and busy fences, atomic staging, proxy image/acceptance guards, neutral-only detach and honest scope disclosures.
- `../people/bodyFaceMatchCoverage.unrun.test.ts`: active/neutral domains, exact independent target reference, malformed/copy/donor rejection, mixed four-family coverage and visible refusal semantics. Existing colour/finish coverage and evenness source assertions were adjusted only for the added family/shared safety naming.

Only source reads, edits and manual static inspection were performed. No product imports, test execution/collection, build, typecheck, inference, downloads, photo/numerical evaluations or Git writes. All fixtures are **AUTHORED / UNRUN**, not passing evidence.

## Required later local validation

1. Run typecheck/build and these UNRUN fixtures with all existing skin/people transaction/batch/history/source-editor regressions.
2. Exercise neutral-first review, blank/zero/invalid amount, independent body selection/strokes/confirmations, actual reference loading and acceptance, candidate amount changes, atomic confirm, active edit, reset and neutral-only detach. Verify no cross-family permission or body-mask/reference copying.
3. Test original/composite sources with and without frozen repairs; compare proxy disclosure with recomputed full-source candidate/reference. Verify source-stage, FaceRef, observation and landmark changes force new review. Confirm later edited faces are never substituted.
4. Cover face/person/group/all scopes with independently valid, missing, stale and foreign target reviews; frozen batch rechecks; no face-only fallback; independent refusal reasons; no target-identity/reference transfer.
5. Exercise rapid/repeated events, fast failures, uncertainty/query, close/reopen, pending close, owner replacement, source/person switching, unmount, image failures/wrong dimensions and obsolete callbacks. Nothing stale may authorize another candidate.
6. Use representative actual RGB SDR photos across skin tones, makeup, coloured lighting, body/face exposure differences, clipping, low resolution, occlusion, edge/crop cases and adjacent people. Measure actual stage luminance, support boundaries, unchanged outside support, tile/full consistency and preview/export/history/save/load behavior. No such acceptance has run yet.
