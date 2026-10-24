# Temple, cheekbone and jaw: source authored, acceptance UNRUN

This UI slice wires exactly these handbook leaves, not the whole facial-reshaping family:

- `LNX-REF-PC-32466-C-94bf91612d`, `脸型/太阳穴`.
- `LNX-REF-PC-32466-C-d24d97d234`, `脸型/颧骨`.
- `LNX-REF-PC-32466-C-3bc7e245b7`, `脸型/下颌`.

The official product guide at <https://wiki.pixcakeai.com/guide/9405.html> supplies the direction and unlock semantics: positive temple expands, positive cheekbone narrows, positive jaw expands; each permits independent left/right adjustment. This is product behavior evidence, not a claim to use the vendor's algorithms. Local `ui/src/spec/refine.json` lists all three exact paths with `left_right_unlock: true`. Original comparison feature source: <https://www.pixcakeai.com/guide/32466>.

## Independent intent and visible limitations

Operation `lnx.face_contour.v1` has exactly `{version: 1, temple: {linked: true, left: 0, right: 0}, cheekbone: {linked: true, left: 0, right: 0}, jaw: {linked: true, left: 0, right: 0}}` at neutral. Each numeric leaf is a finite number in `[-1, 1]`; each linked flag is Boolean. Display `[-100, 100]` is this product's scale, not a guide-prescribed range. Left and right always mean the subject's anatomical sides, not viewer or screen sides.

The controls describe measured visible 2D contour work on the current effective source, whether original or already returned composite. They are not aliases of old slim-face or chin controls, AI reconstruction, 3D shaping, bone correction, or synthesis of hidden anatomy. Only frontal/mild-yaw visible support is promised. Clipping, occlusion, unreliable contour and neighboring-face overlap can refuse application. A local outer background transition halo can move; background invariance is not promised. Capability readiness and nonzero intent are not proof of usable per-side support, changed pixels or acceptable photo quality.

## One canonical owner, distinct readback and targets

- The existing `people.patch` workflow remains the only transaction, queue, receipt, history and replay owner. No second gesture owner, legacy command, renderer or optimistic people graph is introduced.
- Selected-face effective numbers and linked state come exclusively from matching engine-resolved source, face and analysis identity plus graph/association revisions. Missing, nonfinite, out-of-range, stale or conflicted fields remain unavailable, never neutral placeholders. Their provenance is displayed independently of the write target's sparse explicit overrides.
- Nonzero work requires dedicated `face_contour_available` and `face_contour_reason`, a verified enabled selected face, coherent readback and all ownership/queue fences. Each shared target still needs its own evidence in the backend; the selected face does not establish another face's support.
- For face scope, inherited resolved link semantics are used only when the selected face matches that exact target. A valid explicit target link wins. For person/group/all-people scope, missing or invalid explicit link state blocks numeric editing until the user explicitly chooses link/unlink. One face's inherited link cannot silently choose semantics for other faces. Link choices never change either numeric value.
- The next linked numeric edit submits exactly both side leaves in one owner call; an unlinked edit submits only its named subject side. Numeric edits do not patch any linked flag, preserving inherited versus explicit state. Unequal side values remain unequal when link is first enabled.
- Pair recovery submits the current part's two numeric zeros. Family recovery submits exactly all six numeric zeros in one owner call, preserving all linked flags and sparse inheritance. These actions require valid source/target ownership and revisions, but not a working core, usable anatomy, readable values or a selected face under a valid shared target. Other scopes and legacy slim-face intent are not cleared. Other active scopes may still make rendering unavailable.
- Pending, uncertain, export/disabled-owner, competing portrait, hair, white-balance and external edit-queue fences apply. Source/target/revision/selection/analysis/value/link/refusal changes remount drafts. Mounted/current-control guards reject old handlers. Uncertain outcomes query only the original request; late query failures do not report against a different or unmounted control.
- Existing `PeopleView.refusals` and owner receipt messages are displayed unchanged, including other affected faces. The UI invents no per-side status fields or success badges. Backend control/side reasons must remain explicit in failed request text; internal prepared facts alone are not claimed as visible readback.

## Authored fixtures, not executed

`model.unrun.test.ts` covers exact identities, strict recipe/domain validation, subject-side paths, independent and atomic linked edits, flag-only toggles, six-value recovery, sparse link preservation, effective versus explicit values, shared-scope link fencing, stale/conflicted/invalid readback, dedicated readiness, missing-core/anatomy recovery, exact owner and mutation fences, draft invalidation and graph non-mutation.

`wiring.unrun.test.ts` covers the three exact leaf routes, preservation of neighboring legacy controls, dedicated capability and operation label, generic people owner, all competing-owner fences, mounted/current handlers, atomic recovery without current readback, original-request querying and visible scope/quality/refusal wording.

All fixtures are source-only and UNRUN. No product execution/import, test execution, build, typecheck, model inference, numerical validation, external download or real-photo acceptance was performed for this UI slice. Source review is not runtime acceptance.

## Required later qoder verification with authorization

1. Typecheck/build the integrated UI, run the authored fixtures and existing people/portrait regressions, and verify exact native capability fields against actual core availability. Verify backend registration/materialization validates every leaf and accepts six-zero recovery without altering flags.
2. Verify subject-left/right orientation, negative/positive/zero direction for all three controls, unequal side values on link toggle, next-edit atomic linking, independent side edits and all three controls composing without aliasing legacy slim-face.
3. Use frontal and mild-yaw real photos with varied skin tones, high/low resolution, hair crossing the outline, glasses, ears, occlusion, clipped borders, strong yaw and nearby/overlapping people. Inspect the moving local background halo, folds, seams, noise, face distortion and unsupported side refusals. Each affected target needs its own measured evidence. Numerical or synthetic checks do not replace photo acceptance.
4. Exercise person/group/all-people and face scope, sparse links and partial numeric overrides, shared explicit link choice, competing groups, unrelated selected face, reanalysis, source switch and returned composites. Confirm engine-only readback and provenance never pretend a shared default equals every person's final value.
5. Test pair/all-six recovery with missing core, unresolved anatomy, stale/conflicted numeric/link readback and no selection under a valid shared target. Reject stale/foreign target identity. Preserve inherited flags, other scopes, other contour parts on pair reset and all neighboring operations.
6. Exercise rapid repeated link/numeric events, pointer cancellation, number blur, Close/reopen, navigation, source/target/selection changes, late handlers, pending/uncertain receipts, queue/export/other-portrait contention and original-request lookup without resend.
7. Verify undo/redo, save/reload, confirmed transfer, batch history protection, neutral replay and proxy/full-resolution export parity through the canonical all-face engine path. This UI source slice does not establish native arithmetic, successful application or full facial-reshaping acceptance.
