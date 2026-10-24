# 人中 UI: authored, not runtime accepted

Status: AUTHORED / UNRUN. Source reading and source editing only. No project imports, execution, tests, builds, type checks, application runs, inference, downloads or real-photo acceptance were performed. Fixtures are written assertions, not evidence that any assertion passed.

## Exact identity and separation

- Exact leaf: `LNX-REF-PC-32466-C-2605502c27`, `PC-32466|脸型/人中`.
- Current semantic reference supplied by the implementation task: https://wiki.pixcakeai.com/guide/9405.html . Frozen reference: https://www.pixcakeai.com/guide/32466 . This leaf is distinct from mouth vertical position, middle/lower face, chin length and chin sharpness. The reference does not calibrate this implementation's numeric range, gain, source-support boundaries or quality.
- Route `philtrum.amount`, operation `lnx.philtrum.v1`, strict state `{version: 1, amount: number}` with finite amount in `[-1, 1]`. Positive lengthens, negative shortens, zero is neutral. Display `[-100, 100]` is a product-local control scale, not a measured anatomical ratio.
- Existing controls, historical presets, chin-length replacement, managed legacy small-chin controls and their operation identities remain unchanged. This operation never clears another operation, migrates an old number, copies a mouth position or derives state from middle/lower face.
- Unmanaged documents explicitly report the new leaf unavailable. There is no fallback to another warp, an old deform recipe or a direct native mutation path.

## Geometry contract and limits

The operation uses each target's current effective source image, including an already returned composite. In the source head-local coordinates its upper plane lies below every one of the 24 measured nose vertices; its lower plane lies above every one of the 40 measured lip vertices. The planes include boundary margins. The positive remaining plane gap `H` is the support interval, not the simple point-2-to-point-0 distance, clinical philtrum length, an eye-to-nose mid-face interval, or isolated segmentation of philtrum skin.

The shared Rust mid-face inverse is a numerical primitive only. Reusing it does not authorize reusing mid-face source anatomy. The local policy uses additive displacement `Δ = 0.08 × amount × H`. The actual nose-to-lip interval changes additively by that displacement in the lateral core for the uncomposed map; it is not an eight-percent change of the actual nose-to-lip interval. The UI intentionally displays no geometry formula, derived interval, invented measurement or effect percentage.

The newly added map fixes the upper half-plane containing the measured nose vertices and preserves local horizontal coordinates. The gap ramps nonuniformly into a plateau translating lips and the lower face together. Same-height cheeks may change. Lateral feathering and the tail toward the neck/background move adjacent pixels; this is not upper-lip-only motion, uniform scaling of all philtrum pixels, 3D reconstruction or a segmentation claim. Head tilt can change screen-horizontal positions even though local horizontal coordinates are fixed.

Preservation applies to this added map in its source frame. Earlier geometric operations can relocate nose, lip or other pixels into its support/feather, so the final composition does not carry a general unchanged-nose, unchanged-upper-face, unchanged-lips or unchanged-background guarantee. Source image, skin/exclusion evidence, neighboring faces, occlusion, yaw, tilt and clipping remain engine-owned support and compatibility checks. Landmarks alone do not prove occluded anatomy is visible.

The existing conservative core bound `P ≤ 8` remains in force. A short source gap can fail it; no relaxation or fallback is implied. Not every frontal portrait is guaranteed to work. Refusal prevalence and real-photo quality remain unmeasured, with no quantitative success/refusal claims. Core capability is not per-face support or preview/export acceptance.

## Ownership, recovery and uncertainty

- `PeopleOwner.patch` remains the only mutation, queue, receipt, history, undo and replay route. This control does not own a second people graph or transport.
- Selected-face effective value/provenance and the target's explicit value are shown separately. All-people, group and person edits start from that target's valid explicit number or a blank deliberate choice, never a selected face's inherited number. Individual edits require the exact selected/target face reference.
- Missing, conflicted, malformed, nonfinite or out-of-range readings remain unknown, not a zero slider. Blank input never writes on mount or blur. A user may explicitly choose zero, including when nonzero writes are gated.
- Source/epoch/document revision, people/association revision, selected face/analysis revision, target, group/person/link membership, resolved authority/provenance/conflicts, explicit intent, refusals and owner patch/check identity invalidate stale drafts/callbacks. A submitted guard prevents repeated dispatch before a confirmed owner snapshot; uncertain results query the original request instead of resending.
- New neutral recovery sends exactly one `lnx.philtrum.v1 /amount = 0` patch. It does not unset inheritance, clear another scope, reset an old operation or invoke chin replacement. Native readiness, a readable effective amount and usable anatomy are not needed for this reset, but current source/target and confirmed owner/queue state are.
- Nonzero writes require the dedicated `philtrum_available` capability and enabled verified selected face, valid effective reading and ownership fences. The UI relays `philtrum_reason` and raw engine refusals. The engine still must validate every affected target's own source, geometry and final combination; previewing one face never proves all shared targets are valid.

## Authored fixtures, all UNRUN

`model.unrun.test.ts` specifies exact identity/state, signed bounds, dedicated capability, effective/explicit separation, shared blank choices, malformed/conflicted/missing authority, source/revision/target fences, neutral recovery without native/anatomy, membership/provenance/refusal binding changes, raw numeric choices, and preservation of neighboring state including chin-length replacement intents.

`wiring.unrun.test.ts` specifies exact route, preserved neighbors/presets/chin replacement, unavailable unmanaged documents, dedicated capability DTO, canonical owner reuse, competing-editor fences, truthful unknown/shared values, owner-keyed drafts, stale/repeated callbacks, original receipt lookup, raw refusals, neutral-only writes and honest geometry/refusal/acceptance text.

Unverified: every fixture assertion, TypeScript compatibility, compilation, mounted React behavior, bridge capability delivery, rapid face/source/scope/owner changes, repeated clicks, pending-to-failure recovery, original receipt behavior, per-target source support and all-target atomicity, malformed-state recovery, measured plane margins, signs and short-gap refusal, head tilt/yaw/occlusion/clipping, nose preservation within the single map, lips/lower-face translation, same-height cheeks, neighboring-face protection, neck/background quality, composition with earlier edits, photographs at full resolution, history/undo/redo/replay, preview/export parity, packaging and complete handbook/development-pack acceptance. This leaf does not complete the 面部重塑 feature family.
