# Face-skin texture and clarity: authored, acceptance UNRUN

This source-only UI slice wires exactly two leaves referenced by https://www.pixcakeai.com/guide/32465:

- `LNX-REF-PC-32465-C-1c80d411ce`, `皮肤质感/纹理度`.
- `LNX-REF-PC-32465-C-46e0c819b6`, `皮肤质感/清晰度`.

The independent operation is `lnx.skin_texture.v1`, `{version: 1, texture: -1..1, clarity: 0..1}`. Texture left/negative reduces existing texture; right/positive increases it. Clarity is unsigned local skin-detail sharpening, not global coarse-scale contrast. Both zero are neutral. Display ranges -100..100 and 0..100 are this product's own choices, not numeric specifications attributed to the official guide.

## Scope and honesty

- Face only, requiring genuine current-source semantic face-skin support and 478-landmark anatomy. Global capability readiness does not prove this selected face usable.
- The current effective source is the original image or an already returned composite. No detail is invented or reconstructed. AI repair, skin repair and regeneration are not claimed.
- No body workflow, copied colour/finish review, body-scope authority, automatic whole-body support or hidden-skin reconstruction is added. The guide does not establish a body-coverage guarantee for texture; this implementation does not imply one.
- Legacy smoothing/detail retention, existing skin gloss, colour and finish controls, and global image sharpening remain separate. The two leaves are not aliases of legacy `detail_gain` or whole-frame sharpening.
- RGB SDR only. A nonzero setting is not proof of changed pixels or acceptable photo quality. Noise, edge, coloured-light and overall real-photo acceptance are UNRUN; the whole skin family is not accepted by this slice.

## Authority and recovery

- Effective readback comes only from the engine-resolved selected face with matching source, face, analysis identity, state revision and association revision. Missing, invalid, stale or conflicted values remain unavailable, not zero placeholders.
- Selected-face effective value and its source scope are separate from the current write target and explicit target override. A shared default is not represented as every person's effective value.
- Both scalar edits use the existing people workflow. It remains the only transaction, receipt, queue, undo and replay owner. There is no second optimistic people graph or alternate renderer command.
- Nonzero edits require dedicated `skin_texture_available` readiness, authoritative readback, enabled verified selected-face analysis and all existing mutation fences. `skin_texture_reason` supplies the unavailable reason without borrowing readiness from another operation.
- Each leaf has an independent visible zero button. The two-leaf zero button submits exactly two patches in one owner call, not sequential requests. Both recovery routes retain source/target ownership, revisions, pending, uncertain, external-queue and competing-portrait-owner fences, but do not require a working core, current readback, selected face or usable anatomy. A valid shared target may therefore recover with no selected face.
- Zero writes an explicit neutral override only for the current target. It does not restore inheritance, clear another scope, erase the sibling leaf on an individual reset, or alter other operations. Another nonzero leaf/scope can still keep the renderer unavailable and is not silently cleared.
- Changes of source, document, revision, selected face/status, target or authoritative operation readback invalidate input drafts. Mounted/current-control guards refuse late old handlers. Uncertain work can query only the original request, not resubmit it, and a late query failure cannot emit a stale control message after navigation/unmount.

## Authored, not executed

`model.unrun.test.ts` records exact identities, asymmetric ranges, finite-value validation, explicit neutral values, atomic reset, authoritative readback and provenance, sparse overrides, stale/conflicted/missing data, readiness separation, recovery without core/anatomy, ownership and mutation fences, draft invalidation and graph non-mutation.

`wiring.unrun.test.ts` records only the two exact leaf routes, preservation of existing neighboring mappings, dedicated capability keys, operation label, one people owner, current/unmount guards, single-request two-leaf reset, original-request query, competing-owner fences and visible scope/quality limitations.

These fixtures have not been imported or executed. No application execution, unit/integration tests, builds, type checks, model inference, numerical validation, downloads or real-photo acceptance was performed.

## Required later verification with authorization

1. Typecheck/build the integrated UI and run the authored fixtures plus existing people, skin, and image-detail regressions. Confirm both native capability fields match the actual core and missing-core behavior.
2. Inspect negative/positive/zero texture and zero/positive clarity on real light/dark skin photos with low/high noise, fine pores, flat areas, wrinkles, freckles, clipped detail, gradients, high saturation and coloured lighting. Evaluate oversharpening, noise amplification, halos, edge transitions, hair, eyebrows, eyes, lips, teeth, facial hair, glasses, occlusion and adjacent people. Synthetic arithmetic is not photo acceptance.
3. Verify original versus returned-composite source identity, real semantic/478-landmark evidence, stale source and reanalysis, and face/group/person/all-people targets. Inspect source provenance and conflicting shared overrides without displaying them as every person's value.
4. Verify individual zero and atomic both-zero with missing core, unresolved anatomy, no selected face under a valid shared target, and rejected/foreign targets. Check no sibling reset for the individual action, no loss of other scopes and no change to smoothing, colour, finish, gloss or body review.
5. Exercise pending/uncertain replies, queued/export/portrait edits, repeated input, pointer cancellation, number blur, Close/reopen, navigation, source/target/selection changes, late handlers and original-request querying. Runtime interaction acceptance remains UNRUN.
6. Verify preview/export parity, neutral replay, undo/redo and save/reload through the existing engine-owned people path. This UI source fixture does not establish native arithmetic or photograph quality.
