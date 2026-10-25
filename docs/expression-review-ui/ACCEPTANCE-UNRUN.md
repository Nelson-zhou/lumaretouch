# Expression review acceptance: all runtime stages UNRUN

No check below is marked passed. Source and AST inspection alone cannot establish them.

## Source fixtures authored

- `model.unrun.test.ts`: source-owned FaceRefs, absent pose data, 478-point proof, mask bounds, required confirmations, immutable packets, canonical command changes, receipt substitution, forged write claims, malformed image rejection and distinct save-copy identity.
- `controller.unrun.test.ts`: unknown-save duplicate suppression, cancel and module-detach fences, stale preview release, source change during save, late donor choice, explicit cancellable acquisition identity, cancellation-requested versus actual job exit, mask/source-display review revocation and unavailable capability.
- `fixtures.unrun.ts`: explicitly invalid placeholder PNG strings used only to test metadata and rejection paths. They are not donor pixels, output renders or evidence of image acceptance.

## Required real-host and browser checks

1. Choose actual donor image bytes, cancel the native chooser, select among multiple genuine detected faces and deliberately choose a different person. No automatic identity selection occurs. No unconfirmed same-person review can submit.
2. Start from edited source pixels, including returned creative pixels; independently analyze the captured full render. Confirm original-source faces, wrong retained IDs, wrong people graph, stale load/epoch/revision and copied donor landmarks fail closed.
3. Display both complete source images, not cropped thumbnails. Failed SHA, malformed PNG, wrong IHDR/natural dimensions, cropped image mapping and reload after confirmation must revoke eligibility. Verify that shrinking/zooming layout does not shift the source-pixel mask.
4. Paint add/erase, a single dot, rapid motion, boundaries, pen/touch cancellation, lost capture, pointer leaving the crop and re-entry. Abort over-budget strokes whole. Undo and clear mask without editing pixels. Any mask/settings/face/source change invalidates old review and candidate.
5. Show actual full before, full candidate after and effective protected fusion mask. All must load with matching provenance. User must re-confirm after any regenerated candidate. Check pixels outside fusion, foreign people, hair, mouth, eyes, occluders and background at actual output resolution.
6. Compare original-resolution crop sampling and landmark compatibility against core fixtures. Reject >1024 contexts without hidden downscale. Colour matching stays disabled and must not synthesize skin observations. All input/output is real float, not PNG proxies.
7. Double-click candidate/save, lose the send response, return pending/unknown/malformed/foreign receipts, navigate, hide/reopen the panel, disable/replace module, and race source reload with save. The original request owns reconciliation; no automatic write retry or false cancellation.
8. Atomically create a distinct result through the existing save-copy owner. Confirm copied original ID, new result ID, full canonical candidate source identity and result revision. Original and donor stay unchanged. Identical pixels still require a real copy identity. Exercise failure rollback, project save/reopen/recovery and result deletion through normal lifecycle.
9. Missing core, wrong core ABI/capability, unsupported historical recipe and removed module must disable new actions while preserving historical assets and exact old recipes. No dynamic native replacement is claimed.
10. Exact command_json bytes/hash/parsed-object equivalence across languages, exact float-mask serialization, token single-use, candidate resource release and status retention must be tested through the real native/host bridge. Unit fixtures do not replace these checks.

Manual same-person confirmation, conservative 2D geometry and visual mask review are not automatic identity recognition, 3D reconstruction, hidden-face completion or guaranteed natural expression.
