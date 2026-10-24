# Lip-texture control: authored, acceptance UNRUN

## Identity and bounded behaviour

- Exact reference: `LNX-REF-PC-32464-C-b6315c40ca`.
- Verified catalogue leaf: `PC-32464|面部祛瑕疵/唇纹修整` in `ui/src/spec/refine.json`.
- Official source inspected on 2026-10-24: https://www.pixcakeai.com/guide/32464, section “唇纹修整”. The guide includes prominent lip texture, dry flakes/dead skin and small cracks. This implementation intentionally covers only measured dark narrow-furrow attenuation, not that broader promised result.
- Independent operation: `lnx.lip_texture.v1`, exactly `{version: 1, amount: 0..1}`. Display strength 0..100 is this product's range, not an official numeric specification. Zero is neutral; nonzero amounts do not prove changed pixels or acceptable results.
- This is not lip saturation, brightness, dimensionality, lipstick material, broad blur, facial mouth-surround wrinkles, AI removal, dry-flake repair or complete crack reconstruction. Existing controls and their data are unchanged. No manual paint/review flow, new segmentation claim or proprietary parity claim is added.

## Authority, source and neutral recovery

- Each target must use its own real lip support and current effective RGB source, whether the original photo or a returned derived composite. Capability `lip_texture_available` / `lip_texture_reason` only reports core readiness. Current-source geometry/photometry/support admission remains in the engine, not a UI readiness assertion or fabricated measurement.
- The selected face's resolved amount and provenance are displayed separately from the current target's explicit amount. A shared target never pre-fills its slider from a preview face's inherited value. Missing or invalid shared intent receives a blank deliberate choice, not implicit zero, copying, averaging or conversion.
- Nonzero changes require matching current source, document, selected-face identity, analysis revision, state revision and association revision; enabled verified analysis; dedicated capability; valid current target; and selected-face membership in a group or confirmed person link. Future, missing or unconfirmed association revisions cannot authorize the edit.
- Pending, unknown-outcome, disabled owner, hair/white-balance/portrait competitors and edit-queue in-flight/pending/closed fences remain effective. Owner callback identity and generation, mounted status, binding snapshots and a synchronous submission latch reject stale handlers and duplicate dispatch before the pending snapshot arrives.
- Source/target/selection changes, group/person/link membership changes, authority/provenance changes and refusals invalidate drafts. The shared choice starts blank and submits only on its explicit apply action, never on mount or blur.
- The standalone zero button sends exactly one `/amount = 0` patch for `lnx.lip_texture.v1` through the existing people owner. It works without available core, selected preview, readable parameter or usable anatomy when source/target ownership and request fences are intact. Valid shared scopes can recover with no faces selected. It does not restore inheritance, clear support, reset makeup/lipstick/skin/wrinkles, touch other scopes or remove history. Other active scopes can still be refused by the engine.
- The canonical people workflow owns commands, receipts, mutation queue, history, refresh, undo/replay and the existing preview/export path. No alternate render command, optimistic graph, capture pipeline or second preview is created. Unknown outcomes query only the original request and do not resend.
- Generic engine refusals are shown as generic current-person refusals, with face labels where known. They are not falsely attributed exclusively to lip texture.

## Authored fixtures, not proof of acceptance

`model.unrun.test.ts` covers strict finite unsigned recipe/patch validation, exact operation/control/source identity, blank-choice semantics, neutral-only recovery, distinct effective provenance and target intent, inherited face versus shared values, stale/missing/conflicted authority, face/group/person membership, foreign ownership, dedicated capability, runtime-anatomy separation, pending/unknown/concurrent guards, source and membership draft invalidation, and graph non-mutation.

`wiring.unrun.test.ts` records the exact single leaf mapping, unchanged adjacent mappings, dedicated capabilities, competing-owner fences, canonical transaction ownership, owner-generation/mounted guards, duplicate submission latch, blank shared choice, independent neutral action, original-request query and visible scope limitations.

These files have not been imported or executed. No application execution, local tests, build, typecheck, inference, downloads, numerical evaluation, photo acceptance or Git writes were performed for this UI slice. Static source inspection only is not a passing test result.

## Later acceptance required with authorization

1. Typecheck/build the integrated UI and run these authored fixtures and existing people, lip makeup, lipstick, facial wrinkles, skin texture and preview/export regressions. Confirm the native capability DTO matches the integrated core and absent-core reason.
2. Validate every target independently on real current-source RGB photos: original and returned composite, subtle/prominent dark furrows, light/dark lip colours, closed/open mouth, visible teeth/tongue/oral cavity, lip edges, lipstick edges/highlights, gloss, fine freckles, flat/no-furrow lips, noise, clipping, coloured light, small resolution, profile, occlusion, crop and adjacent faces. Assess boundary preservation, halos, over-lightening, colour drift and attenuation quality. Synthetic masks or arithmetic cannot establish photo quality or full-guide parity.
3. Prove runtime refusal/no-op behavior for missing, stale, foreign, truncated, occluded or inadequate target-owned lip support and absent dark narrow-furrow evidence. Do not equate global core availability with source admission, semantic segmentation, visibility or changed pixels.
4. Exercise face/group/person/all-people targets, preview nonmembers, candidate versus confirmed links, source changes, reanalysis, precedence conflicts and missing/invalid explicit amounts. Confirm shared edits never borrow the preview's inherited value, and each resulting target goes through engine validation.
5. Verify amount-zero identity, missing-core and unresolved-anatomy recovery, shared recovery with no selected face, source/owner mismatch refusal, other active scopes and preservation of adjacent operations. Confirm zero is explicit neutral, not restore inheritance or cross-scope cleanup.
6. Exercise numeric input, slider pointer and keyboard controls, cancellation, repeated click, rapid callback, confirmed fast failure, pending/unknown outcomes, export and other edit queues, original-request query, Close/reopen and source/target/membership changes. Ensure stale handlers cannot retarget edits or emit obsolete query errors.
7. Check ordinary preview, export, save/reload, undo/redo and history replay parity through the single canonical people path. UI, engine, native arithmetic and real-photo acceptance all remain UNRUN until performed; the complete blemish-removal family is not accepted by this leaf.
