# Face-skin gloss: authored, acceptance UNRUN

This UI slice wires exactly `LNX-REF-PC-32465-C-1eed7cf9a9`, `皮肤质感/光泽度`, with the official source reference https://www.pixcakeai.com/guide/32465. Its independent operation is `lnx.skin_gloss.v1`, `{version: 1, amount: -1..1}`. Negative amounts suppress existing face-skin highlights; positive amounts enhance them; zero is neutral. Display -100 to 100 is this product's range, not a range attributed to the guide.

## Scope and honesty

- Face only. No body support, body-review workflow, copied colour/finish support, automatic whole-body detection or hidden-skin reconstruction is added.
- The UI describes conservative estimation of existing highlights from the current effective immutable source (the original image or a returned composite) and actual face-skin support. It does not paint new highlights, claim precise specular segmentation, promise perfect oil removal, recover clipped detail or fabricate an observed highlight count.
- A permitted nonzero setting is not proof of changed pixels. No observable highlight can yield no visible effect. Photographic acceptance remains UNRUN.
- RGB SDR only; HDR support is not claimed. Existing temperature/tint, whitening/rosiness and smoothing controls remain separate, unchanged operations.

## Authority and recovery

- Selected-face effective `/amount` comes only from matching authoritative resolved face, source, analysis, state revision and association revision. Missing, stale, conflicted or invalid readback is not replaced with zero or a neighboring effect value.
- Write target and its explicit override are displayed separately. A shared default is not presented as the selected face's effective value or every person's value.
- Patches use the existing people transaction, revision, ownership, uncertain-receipt, undo and replay owner. No alternate native command, history owner, optimistic graph or body-review action is introduced.
- Negative and positive changes require the dedicated readiness capability plus enabled, verified selected-face analysis and authoritative readback. Global core availability is not asserted to prove this face or its highlights usable.
- Neutral recovery is a visible independent button. Valid source-owned target and mutation fences remain mandatory, but a working core, observable highlight, selected face, or current usable anatomy is not required for zero recovery. It writes neutral only to the current target and does not restore inheritance or erase other targets.
- Pending, uncertain, external edit-queue and competing portrait owner fences also cover reset. An uncertain request offers only a query of the original request. Changes of document, revision, source, selected-face identity/status or target remount the input draft, and unmounted controls refuse late commits.

## Authored but not run

`model.unrun.test.ts` covers exact identity, signed range, neutral recipe, selected-face readback, distinct overrides, missing/stale/conflicted/invalid data, operation isolation, capability separation, neutral recovery, ownership and revision fences, mutation locks, and stale-draft binding changes.

`wiring.unrun.test.ts` covers the single exact leaf, unchanged neighboring leaf mappings, readiness keys, operation label, existing transaction route, all competing-owner fences, no body integration, and visible limitation wording.

These fixtures have not been imported or executed. No application execution, tests, builds, type checking, model inference, downloads, numerical validation or photo acceptance was performed for this UI slice.

## Required verification in an authorized runtime

1. Typecheck/build the integrated UI and run the authored fixtures, then existing people, colour and finish regressions. Verify native readiness keys agree with the actual core and a missing-core build.
2. On genuine light/dark skin photos, inspect negative/positive/zero on face skin with real observable highlights and with none. Check clipped highlights, flat bright areas, gradients, shadows, pores, freckles, high saturation, glasses, occlusion, hair, eyes, lips, teeth, facial hair and adjacent people. Confirm no invented highlight and no unsupported photo-quality claims.
3. Verify face/group/person/all-people targets, explicit zero versus inherited value, conflicts, selected-face provenance, missing or stale readback, source/analysis changes and disabled/synthetic analysis. Confirm the slider never displays another operation or another selected face's value.
4. Verify zero recovery with unavailable core, unresolved anatomy, no selected face under a valid shared target, and invalid targets. Confirm it changes only `/amount` in the current target and preserves temperature, tint, whitening, rosiness, other scopes, history and body support.
5. Exercise pending/uncertain replies, in-flight export/edit/portrait owners, repeated input, numeric blur, pointer cancel, Close/reopen, document/selection/target switches and late input after unmount. Query the original uncertain request without resending. Runtime gesture behavior is not claimed validated.
6. Verify actual engine preview, export, undo/redo, save/reload and neutral replay. Dedicated UI state must not invent renderer readiness, highlight measurements, changed-pixel counts or HDR support.
