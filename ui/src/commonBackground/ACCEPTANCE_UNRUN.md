# Common colour-key review: authored acceptance checklist

Status: UNRUN. Source implementation and fixtures only. No dependency import, test run, typecheck, build, product launch, inference, model download, UI session or export acceptance was performed for this change.

## Host ownership contract

- Keep useCommonBackgroundWorkflow mounted in App. Pass its owner through RetouchProps.commonBackgroundOwner, including when the tool family is collapsed or filtered.
- RetouchPanel mounts the workspace once outside the filtered tool family; the family contains a launcher only. A hidden pending operation retains a fixed original-receipt query control. Draft controls are shared by the persistent owner.
- Context enabled must include common_background_protocol === 1, live engine, matching document/image load identity, supported retouch workspace and single-view state. Include all competing editor ownership and external busy conditions, but never include this owner's own active/pending flags in its enabled input.
- canStart represents queue idleness and external edit settlement. Queue activity during this owner's preview does not by itself invalidate the preview.
- contextKey includes engine epoch, host document revision, load identity, workspace, compare/inspection/crop state. Changed document or revision cancels only an unsent draft.
- Use owner.active || owner.pending in competing capture, body/hair, guide and edit guards. Permit .commonBackgroundPanel, .commonBackgroundWorkspace, original-receipt queries and safe Close controls through those guards.
- prepare cancels or settles existing editor ownership; the hook additionally awaits the existing curve-edit barrier before binding a preview.
- Preparation remains closed until its preflight succeeds, so a refused launch cannot disable and cancel a competing editor merely by opening a failure dialog. The launcher exposes cancellation while waiting.
- Unknown/requires_reload receipts intentionally remain pending; closing the window never clears them. A verified host reload/reconciliation escape is not supplied by this UI module. If host guards block every reload action, an engine-ended unknown can remain blocked; do not claim that recovery path is complete or release its lock merely because a query is unchanged.

## Authored workflow fixtures

workflow.unrun.test.ts covers strict images and lossless recipe revisions; native plus engine presentation acknowledgments; dirty drafts; set/clear preview barriers; no-change history; cancellation and revision invalidation; independent returned-composite identities; queue settlement; double click; late receipt; close/unmount while pending; uncertain result retention; no resubmission; missing proof; and stale image events.

The small PNG strings in the state-machine fixtures are transport placeholders, not valid visual verification evidence. The actual UI must decode both real engine-produced images and match their dimensions before requesting presented. This requires separate product/UI validation.

## UI and production checks still required

1. Original opaque SDR RGB8/RGB16 source: generate before/after, verify both actual pipeline images, adjust tol/softness/color, verify stale preview cannot apply, confirm once, undo/redo, save/reopen, export full-size and compare verified pixels.
2. Opaque SDR creative return: repeat on its own source and recipe binding, including after original-photo edits, source change, proxy-size change and session switch. Never borrow the original photo's matte.
3. Transparent and HDR inputs: verify explicit engine rejection and no mutation/history advance, not a fabricated successful preview.
4. Verify both image decode successes are necessary; reject image errors and dimension mismatches. Delay one load and reject native/server presented independently. Confirm stays disabled.
5. Exercise Escape, Close, double-click, search/category collapse, navigation, engine restart, modal keyboard trap, small viewport, stale callbacks and pending/unknown request recovery. Close after submit hides only the dialog and keeps the original request available.
6. Preserve the legacy diagnostics route and verify old neural/proxy limitations remain visible. This deterministic review does not establish neural-mask fidelity or final export quality.
7. No source report alone constitutes product-manual or AI-package completion. Visual quality, performance, rendered UI, native build, regression suite and real export remain UNRUN until separately observed.
