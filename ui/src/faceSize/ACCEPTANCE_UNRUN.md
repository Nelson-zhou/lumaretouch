# 小脸 UI: authored, not runtime accepted

Status: AUTHORED / UNRUN. No code imports, tests, builds, type checks, application runs, inference, downloads, or photo acceptance were performed for these changes. Source inspection and source editing are not runtime verification.

## Exact requirement and scope

- Frozen AI development mapping: `LNX-REF-PC-32466-C-728fc62cdd`, `PC-32466`, `脸型/小脸`. The source mapping lists `PORTRAIT-007` only as a related module case, not proof that this leaf is implemented or accepted; its dedicated acceptance-case list is empty.
- The handbook's 面部重塑 list names 小脸 separately from 瘦脸, V脸, 短脸, 脸宽, individual features, and 3D塑颜. It does not prescribe a numerical range or require bilateral unlocking for this leaf.
- Frozen source: https://www.pixcakeai.com/guide/32466 . Current semantic source, verified by the coordinating task: https://wiki.pixcakeai.com/guide/9405.html . Positive decreases the whole face size; negative increases it.
- Exact UI route: `PC-32466|脸型/小脸` → `face_size.amount`. Operation: `lnx.face_size.v1`, recipe `{version: 1, amount: 0}`, finite `amount` in `[-1, 1]`. The product-local core scale is `1 - 0.06 * amount`; display `[-100, 100]` is not an official range or quality claim.
- Existing 瘦脸, bilateral contour, feature routes and historical presets remain unchanged. Unmanaged documents have an explicit unavailable panel, with no old slim-face or image-resize substitute.

## Ownership and intended behavior

The original people owner is the only command, queue, receipt, undo, and replay authority. The new control sends only `/amount` through `people.patch`. Reading requires the exact selected face, document/asset identity, analysis revision, and state/association revisions; unknown and conflicted reads stay unknown. Selected effective value/provenance are separate from the target's explicit value. A shared scope without its own amount starts with an empty deliberate choice, never another selected face's inherited amount.

Source/target/revision/selection keys discard obsolete input and callbacks. Pending, uncertain, disabled-owner, and other editor queue fences block all writes. Zero recovery needs current source/target ownership but not a working native face-size core, a readable effective amount, or verified anatomy. It writes exactly one explicit zero, does not unset inheritance, and does not reset any other operation. Uncertain requests are queried, never recreated or resubmitted by this control.

The control describes actual-source, measured-face local whole-face scaling: facial features move uniformly together in the core; background, hair and neck in the smooth transition also move. Only frontal and mild-yaw measured faces are in scope. This is not 3D, AI reconstruction, segmentation, or whole-image resizing. Geometry coexistence remains the engine's source-owned decision; the UI relays original engine refusals rather than inventing compatibility flags or bypassing manual-liquify restrictions.

## Authored verification, all UNRUN

- `model.unrun.test.ts`: strict recipe and signed finite domain; positive/negative scale direction; exact IDs; dedicated capability; selected effective/provenance vs explicit target; shared targets and blank choices; missing, stale, conflicted, disabled and synthetic reads; source/target/revision/owner fences; neutral reset; exact patch isolation; nonmutation and lack of UI composition guesses.
- `wiring.unrun.test.ts`: exact route, old routes/presets retained, unmanaged refusal, distinct capability fields, existing owner and competing editor fences, authoritative displays, no placeholder or borrowed shared baseline, late callback/repeated click guards, query-only uncertain recovery, reset independent of native/anatomy, and visible semantic/quality limits.

Still unverified: compilation, TypeScript compatibility, test assertions, mounted React interaction, native bridge availability, actual measured geometry, rapid switching/dragging, shared-scope engine outcomes, existing active-geometry combinations, neighboring faces, occlusion/clipping/yaw refusals, background/neck/hair quality, zero/undo/redo/history/replay, preview/export parity, full-resolution real photos, packaging, and complete handbook/development-pack acceptance. These source-contract fixtures do not substitute for behavioral tests or photo QA, and this leaf does not complete the 面部重塑 family.
