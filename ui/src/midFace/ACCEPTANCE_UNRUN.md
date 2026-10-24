# 中庭 UI: authored, not runtime accepted

Status: AUTHORED / UNRUN. No product imports, tests, builds, type checks, application runs, inference, downloads, or photo acceptance were executed for these changes. Source inspection and source editing are not runtime verification.

## Exact requirement and scope

- AI development mapping supplied by the coordinating task: `LNX-REF-PC-32466-C-ea67c9d99f`, `PC-32466`, `脸型/中庭`.
- The repository's frozen `ui/src/spec/refine.json` lists 中庭 separately from 下庭, 人中, 下巴长短, 尖下巴, 收下巴, 小脸 and 短脸. Its range, default, step and left/right-unlock fields are unspecified. `docs/development/handbook-traceability.json` still marks this exact leaf `pending_independent_verification`; this UI work does not promote that status.
- Frozen source: https://www.pixcakeai.com/guide/32466 . Current semantic source, direction verified by the coordinating task: https://wiki.pixcakeai.com/guide/9405.html . Positive lengthens; negative shortens. No official numerical gain or anatomical boundary is established by that evidence.
- Exact UI route: `PC-32466|脸型/中庭` → `mid_face.amount`. Distinct operation: `lnx.mid_face.v1`, recipe `{version: 1, amount: 0}`, finite signed `amount` in `[-1, 1]`. Display `[-100, 100]` is a product-local range, not a handbook-prescribed quantity or quality claim.
- Existing 下庭, 小脸, 瘦脸, bilateral contour, feature routes and historical presets remain untouched. Unmanaged documents show an explicit unavailable panel with no lower-face, whole-face, old small-chin, chin-length or short-face fallback.

## Geometry language and boundaries

This is a distinct original local policy, not clinical middle-third measurement, true apple-cheek segmentation, nose preservation, uniform whole-region scaling, AI/3D reconstruction or an alias of `small_chin` or `lnx.lower_face.v1`. The control describes the current effective source's measured 478-point analysis, not clinical anatomy or proof that occluded points are visible. The source can be the original image or an already returned composite; each edited target needs its own measured analysis.

In the head-local frame, a fixed upper plane lies below all retained eye contours. Within the lateral core, vertical displacement rises smoothly and nonuniformly across the cheek AND nose band from that eye boundary to the nose-base proxy. The nose participates in deformation. Below the nose-base proxy, lower-face regions including lips and chin receive equal translation in a plateau, followed by neck/background feathering. Outer lateral support is also feathered. Equal core translation is not a promise that the entire image region moves equally.

Only the newly added map preserves the head-local horizontal coordinate and the half-plane above the fixed eye boundary. Prior edits can move points into the transition or neck/background feather, so that invariant is not a claim about original points in the final composed image. The control explicitly defers source-owned compatibility and anatomy suitability to the engine and relays raw engine refusals.

The original, uncomposed eye-boundary/nose-base proxy endpoint interval in the lateral core changes by `1 + 0.08 * amount`, from `0.92` to `1.08`. Gain, fixed boundary and transition shape are local product policy, not official calibration. The displayed ratio is derived from the amount, not measured rendered geometry, a uniform scale, or a photo-acceptance result. No new clipping/occlusion, AI, reconstruction, or segmentation claim is made.

## Ownership and intended behavior

The existing people owner is the only command, queue, receipt, undo and replay authority. The control sends only `/amount` through `people.patch`. Reading requires the exact selected face, document/source identity, analysis revision, state revision and association revision. Unknown, stale and conflicted reads remain unknown. The selected effective value and provenance are distinct from the editing target's explicit value. Shared all-people, group and person scopes without an explicit amount start blank and require a deliberate new choice; they never borrow a selected face's inherited amount.

Source/target/revision/selection keys discard obsolete callbacks and drafts. Owner identity, pending, uncertain, disabled-owner and competing-editor queue fences guard writes. Neutral recovery needs current source and valid target ownership but not a working native core, readable effective value or verified anatomy. It writes exactly one explicit zero, does not unset inheritance, and changes no other operation. Uncertain requests are queried through the original owner, never resent here. Raw engine refusal text and owner errors remain visible; no compatibility flag or bypass is invented.

## Authored verification, all UNRUN

- `model.unrun.test.ts`: strict recipe and signed finite amount; exact IDs; positive/negative endpoint direction; dedicated capability, not a lower-face capability; authoritative selected effective value/provenance vs target explicit values; shared blank choice; missing/stale/conflicted/disabled/synthetic reads; source/ref/revision/target/owner fences; neutral reset; isolated patch; nonmutation and no guessed coexistence restrictions.
- `wiring.unrun.test.ts`: exact route and preservation of old routes/presets; unmanaged refusal without fallback; dedicated capability fields; existing single people owner and competing-editor fences; no fake zero or borrowed baseline; stale callback/owner/repeated-click guards; query-only uncertain recovery; neutral action independent of anatomy/native; explicit eye-boundary, cheek/nose ramp, lower-face plateau, feathering, proxy and composition limits.

Still unverified: TypeScript compatibility, compilation, every authored assertion, mounted React interactions, native bridge availability, source-owned geometry, retained eye contours and both amount signs, nose-band deformation, lips/chin plateau, yaw/occlusion/clipping refusals, rapid photo/face/scope switching, shared-scope engine outcomes, earlier-geometry composition including points entering the feather, neighboring faces, neck/background quality, zero/undo/redo/history/replay, preview/export parity, full-resolution real photographs, packaging and complete handbook/development-pack acceptance. Source-contract fixtures do not substitute for runtime or photo QA. This leaf does not complete the 面部重塑 family.
