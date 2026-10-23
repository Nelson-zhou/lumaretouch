# Common colour-key review: authored acceptance checklist

Status: UNRUN. Source implementation and fixtures only. No dependency import, test run, typecheck, build, product launch, inference, model download, UI session or export acceptance was performed for this change.

## Host ownership contract

- Keep useCommonBackgroundWorkflow mounted in App. Pass its owner through RetouchProps.commonBackgroundOwner, including when the tool family is collapsed or filtered.
- App mounts the workspace once, unconditionally, outside RetouchPanel and workspace selection; the filtered tool family contains a launcher only. Original-receipt and readback controls remain reachable from projects, library and creative workspaces. Draft controls are shared by the persistent owner.
- Context enabled must include common_background_protocol === 1, live engine, matching document/image load identity, supported retouch workspace and single-view state. Include all competing editor ownership and external busy conditions, but never include this owner's own active/pending flags in its enabled input.
- canStart represents queue idleness and external edit settlement. Queue activity during this owner's preview does not by itself invalidate the preview.
- contextKey includes engine epoch, host document revision, load identity, workspace, compare/inspection/crop state. Changed document or revision cancels only an unsent draft.
- Use owner.active || owner.pending in competing capture, body/hair, guide and edit guards. Permit .commonBackgroundPanel, .commonBackgroundWorkspace, original-receipt queries and safe Close controls through those guards.
- prepare cancels or settles existing editor ownership; the hook additionally awaits the existing curve-edit barrier before binding a preview.
- Confirmation separately settles the curve-edit barrier inside the lifetime-owned, cancellable confirming phase, before registering any apply request. Barrier rejection is explicitly unsent. A canceled, changed, dirtied or unmounted preview cannot submit when the old barrier finishes. The common-background native wrapper does not add a second deferred generic barrier.
- Preparation remains closed until its preflight succeeds, so a refused launch cannot disable and cancel a competing editor merely by opening a failure dialog. The launcher exposes cancellation while waiting.
- Unknown/requires_reload receipts intentionally remain pending; closing the window never clears them. This UI supplies explicit same-engine cached-result readback, not generic rollback/checkpoint recovery. Missing results, engine changes, genuine rollback uncertainty and returned unknown receipts remain blocked. A verified host checkpoint recovery escape is not supplied by this module; do not claim all unknowns are solved.

## Process-lifetime inventory and same-engine readback

- Query common_background_audit during every newly created owner bootstrap, regardless of engine liveness or capabilities. Pending, failed, malformed or inconsistent inventory keeps owner.pending true. Native process memory is the authoritative inventory, not localStorage and not disk durability across full application-process restarts.
- Inventory protocol 1 uses audit_scope application-process, at most 4096 unique originals, and a canonical positive u64 decimal client_generation. Store the generation losslessly. Every apply passes it as native-only clientGeneration; native rotates it during bootstrap and checks it under the audit-admission lock. A late old-client invoke cannot apply after a new bootstrap; already-admitted originals instead appear in the inventory.
- Bootstrap is bound to owner lifetime, not the asynchronously arriving UI PID. Native per-item engine_state remains authoritative; active readback callbacks are independently guarded by owner lifetime, original identity and engineKey. Inventory is never silently reloaded over a locally submitted request.
- Context readbackEnabled is the independent live-engine/common_background_readback_protocol === 1 capability gate. engineKey is the current engine identity. Neither is allowed to skip native bootstrap or erase an old-epoch record.
- Restore every unresolved original, retain every audit row, and reconcile originals sequentially. Readback gets a unique nonzero lowercase 32-hex identity and never resends apply. A timed-out readback can query the same readback ID without repeating its send.
- Only a fully validated, exact-identity found receipt with known outcome and no reload requirement settles. Validate original_receipt independently as null or an exact original apply receipt, including valid unknown receipts. A minimal unregistered readback status is non-evidence, never proof of noncommit.
- Original request/receipt, later original query envelope, independent readback status and authoritative result remain separately inspectable after settlement. Only native definitive submission:not_sent is evidence of pre-admission rejection; absence or transport failure is not.

## Authored workflow fixtures

workflow.unrun.test.ts covers strict images and lossless recipe revisions; native plus engine presentation acknowledgments; dirty drafts; set/clear preview barriers; no-change history; cancellation and revision invalidation; independent returned-composite identities; queue settlement; double click; late receipt; close/unmount while pending; uncertain result retention; no resubmission; missing proof; and stale image events.

readback.unrun.test.ts covers authoritative bootstrap and inventory failures; generation format and propagation; clean success/rejection versus genuine unknown; strict original/readback identities; every nonfound terminal phase; minimal unavailable status; lost-send/status timeout; serialized queries; late callbacks, close and engine changes; initial PID arrival; full owner remount and multi-original restoration; authoritative not_sent; rejected/canceled/dirtied/unmounted confirmation preflight; and a modeled stale-generation admission race. Modeled transport behavior is not proof of native execution.

The small PNG strings in the state-machine fixtures are transport placeholders, not valid visual verification evidence. The actual UI must decode both real engine-produced images and match their dimensions before requesting presented. This requires separate product/UI validation.

## UI and production checks still required

1. Original opaque SDR RGB8/RGB16 source: generate before/after, verify both actual pipeline images, adjust tol/softness/color, verify stale preview cannot apply, confirm once, undo/redo, save/reopen, export full-size and compare verified pixels.
2. Opaque SDR creative return: repeat on its own source and recipe binding, including after original-photo edits, source change, proxy-size change and session switch. Never borrow the original photo's matte.
3. Transparent and HDR inputs: verify explicit engine rejection and no mutation/history advance, not a fabricated successful preview.
4. Verify both image decode successes are necessary; reject image errors and dimension mismatches. Delay one load and reject native/server presented independently. Confirm stays disabled.
5. Exercise Escape, Close, double-click, search/category collapse, navigation, engine restart, modal keyboard trap, small viewport, stale callbacks and pending/unknown request recovery. Close after submit hides only the dialog and keeps the original request available. Remount the entire App/webview during confirmation preflight, native admission and terminal receipt loss; verify inventory restores all admitted originals and old generations cannot submit late.
6. Preserve the legacy diagnostics route and verify old neural/proxy limitations remain visible. This deterministic review does not establish neural-mask fidelity or final export quality.
7. No source report alone constitutes product-manual or AI-package completion. Visual quality, performance, rendered UI, native build, regression suite and real export remain UNRUN until separately observed.
