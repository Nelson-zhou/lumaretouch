# Skin whitening and rosiness: authored, acceptance UNRUN

This slice wires exactly:

- `LNX-REF-PC-32465-C-d82f09f52f` 肤色美白, `/whitening`.
- `LNX-REF-PC-32465-C-60936d5259` 皮肤红润, `/rosiness`.

Both belong to the independent canonical `lnx.skin_finish.v1` recipe `{version: 1, whitening: 0..1, rosiness: 0..1}`. Display 0–100 is a local product range, not a handbook-specified range. The [official skin-adjustment guide](https://www.pixcakeai.com/guide/32465), read 2026-10-24, describes whitening as brightening with a cool-white direction and rosiness as a whole-body skin appearance change. The controls therefore are not exposure, temperature, tint, smoothing, local blush or a health-assessment alias.

The implemented UI is expressly manual-assisted: measured face skin plus an optional independently reviewed visible body-skin extension. It does not claim automatic whole-body recognition, hidden-skin recovery, completed skin-family coverage, health assessment or photographic quality acceptance. Different skin tones are not ranked as healthier or preferable. The two scalar controls display selected-face authoritative readback while separately labeling their write target and explicit override.

## Identity and authority boundaries

- Existing people transactions own scalar patches, pending/uncertain receipts, undo and replay. No second mutation/history owner is introduced.
- Existing colour controls and default untagged colour DTOs remain unchanged. The reusable body panel defaults to `skin_colour`.
- Finish uses `skin_finish_body_reference`, `skin_finish_body_preview`, `skin_finish_body_confirm`, `skin_finish_body_detach`, and `people.skin_finish_body`. Each finish response/report must contain both `family: "skin_finish"` and `operation_id: "lnx.skin_finish.v1"`.
- Colour bodies, vectors and confirmations are not copied into finish. Finish begins with an empty local draft, a fresh source reference and three explicit visible/unoccluded/current-person confirmations. All three genuine source-overlay/full-rendered-before/full-rendered-after images must load at declared dimensions before separate final consent.
- The 192 KiB UTF-8 UI request budget and native 256 KiB request cap remain unchanged. Geometry is not silently decimated. Native bridge acceptance is not operation completion.
- Missing core or missing analysis does not hide neutral recovery for a valid, unblocked target. Detach does not require a working effect core or usable body observation. Stale retained descriptors are not labeled usable.

## Authored but not run

`model.unrun.test.ts`, `bodyFamily.unrun.test.ts` and `wiring.unrun.test.ts` cover exact leaf/operation identities, unit bounds, authoritative values, invalid/stale readback, source/owner fences, neutral recovery, family isolation, fresh review requirements, real-image gating, bounded requests, and exact request/action correlation. One existing colour source assertion now follows the parameterized detach action. These files have not been imported or executed.

No application execution, builds, type checks, tests, inference, model download, numerical validation or photographic acceptance were performed for this UI slice.

## Required local verification

1. Compile/typecheck the final integrated UI and run both colour and finish fixtures. Exercise native people admission and actual engine finish capability reporting, including a missing native core.
2. Verify independent whitening, independent rosiness, combination and exact neutral recovery on measured light/dark skin, gradients, shadows, high saturation, protected lips/eyes/hair, glasses, occlusion and neighboring people. Confirm whitening is not merely exposure and rosiness is not a localized blush overlay. Numerical identity, gamut behavior and visual quality remain unverified here.
3. Verify independent face/group/person/all-people overrides, selected-face readback, conflicts, reset-one/reset-both semantics, existing undo/redo and project replay. Colour, exposure and blush values must remain unchanged. Do not erase non-neutral overrides in other scopes during recovery.
4. Attach only a colour body range and verify finish remains face-only. Repeat with only finish attached. Attempt cross-family payload/candidate reuse, source switches, person changes, reassociation, analysis changes, changed vectors and retained historical support. Every incompatible review must refuse without widening coverage or replaying an uncertain request.
5. In finish review, draw add/subtract strokes on the actual full source canvas, including edges, non-square dimensions, zoom/pan, radius and feather. Confirm protected face regions, actual semantic intersection, no copied colour vectors, and competing-person vetoes. Test point/byte limits and pointer cancellation without silent reduction.
6. Load real before/after/overlay images, break one image, alter declared dimensions, edit vectors, close the panel, switch family/person/document, and interrupt pending/uncertain requests. Final consent must remain blocked for stale, incomplete or released images. Closing must not pretend to cancel an already submitted operation.
7. Save/reload a valid, stale and detached finish descriptor. Attachment status must come from the finish report, with exact tags and current face/source identity. Detach must remain reachable without the native core and must not detach the colour support.
8. Recheck all existing colour controls and body-review flows. Generic edit-queue ownership still conservatively blocks in-flight scalar interactions; uninterrupted dragging is not claimed. Runtime gesture behavior and accessibility still require actual application review.
