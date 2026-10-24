# 下巴长短 UI: authored, not runtime accepted

Status: AUTHORED / UNRUN. Source reading and source editing only. No project imports, execution, tests, builds, type checks, application runs, inference, downloads or real-photo acceptance were performed. Fixtures are written assertions, not evidence that any test passed.

## Identity and product boundaries

- Exact leaf: `LNX-REF-PC-32466-C-44a42baef4`, `PC-32466|脸型/下巴长短`.
- Current semantic reference provided by the implementation task: https://wiki.pixcakeai.com/guide/9405.html . Frozen reference: https://www.pixcakeai.com/guide/32466 . The handbook distinguishes chin length from lower face, mid face, chin sharpness and historical chin controls. It does not calibrate this product's numeric scale or geometry gain.
- New route `chin_length.amount`; new operation `lnx.chin_length.v1`; strict state `{version: 1, amount: number}` with finite amount in `[-1, 1]`. Positive lengthens, negative shortens, zero is neutral. Display `[-100, 100]` is a product-local scale.
- Existing 瘦脸, 小脸, 中庭, 下庭, 尖下巴, 太阳穴, 颧骨, 下颌, 收下巴, other facial features and historical presets preserve their routes and operation identities. The old 收下巴 route still edits `lnx.deform.v1 /small_chin` with its existing positive slider; its managed wrapper only adds truthful scope/provenance, conflict and request fences. Unmanaged historical edits still use the existing legacy handler. Negative historical values remain saved and are disclosed without automatic conversion.
- Unmanaged documents explicitly report the new feature unavailable. There is no fallback to legacy small chin, lower face, mid face, sharp chin, another deform recipe or a direct-native mutation path.

## Geometry and limitations

The intended effect uses each target's current effective source image, including an already returned composite. Its support is measured below all 40 lip vertices and toward chin tip 152; the lower-chin arc is `150–149–176–148–152–377–400–378–379`. This is source-owned proxy anatomy, not clinical measurement. The existing Rust lower-face scalar inverse is only a numerical primitive; the new operation does not reuse the lower-face nose-to-chin anatomical measurement or source support.

The newly added map moves in the measured head-local vertical direction with gain `0.08 × amount` times the source lip-plane-to-tip interval, with compact lateral and neck feathering. It is not uniform scaling of all chin pixels. Its local horizontal coordinate and the region above the lip boundary stay fixed in that map, not necessarily in the final composed image. Head rotation can change screen-horizontal position; earlier geometric operations can move pixels into the new feather. The UI never promises unchanged final lips, upper face or background.

Source skin, RGB and exclusion evidence are engine-owned checks, not new segmentation or proof that all occlusion is detectable. Tilt, yaw, clipping, occlusion, neighboring faces, neck and background can make support invalid or produce visible transitions. The UI does not invent support dimensions, measured quality or acceptance scores. Core availability is not per-face support, anatomy, safety, quality or preview/export acceptance.

Historical `small_chin` behavior is not repaired or relabeled as this new feature. Its source uses chin 152 plus historical points 54 and 314, which are not a correct pair of jaw support points. The UI describes this defect while preserving the old numerical meaning and behavior for saved works. The old number is never copied, scaled, negated or silently migrated.

## Ownership, replacement and recovery

- Existing `PeopleOwner.patch` is the only mutation, queue, receipt, history, undo and replay route. This control does not own a second people graph or send independent native commands.
- Effective new and old readings and their provenance are displayed separately from target-owned explicit new and old values. Shared all-people, group and person inputs use that target's explicit number or a blank user choice, never the selected preview face's inherited number. Individual face edits require an exact selected/target face match.
- Raw blank, malformed, nonfinite and out-of-range inputs are rejected, not coerced to zero. Inputs never submit on mount or blur. Source, epoch/revisions, face/analysis revision, target, memberships, provenance/conflicts, both explicit intents, refusals and owner patch/check identity invalidate stale drafts and callbacks.
- Opening the new panel, changing the new operation to zero or using its dedicated reset never alters the old operation. New reset writes only `lnx.chin_length.v1 /amount = 0`, not an unset, migration, inherited reset, other scope clear or legacy reset.
- Replacement is explicit opt-in. A separately blank input requires a new number chosen by the user and a replacement button click. Exactly one owner patch transaction contains `lnx.deform.v1 /small_chin = 0` and `lnx.chin_length.v1 /amount = chosen`. It is never two requests and never clears the old operation before testing the new one.
- Replacement can be offered when the selected face has active legacy effect or the current shared target has a known nonzero explicit legacy value. A selected face's neutral old reading does not erase or hide a shared target's nonzero old intent. These facts do not imply every affected face has the same value.
- Nonzero new and legacy effects cannot coexist effectively on any affected face. UI gates known effective and explicit conflicts. The engine must validate the final candidate for every affected face and refuse the whole transaction if another scope's overrides still cause coexistence. No UI check substitutes for all-target transactional validation.
- Current source and target plus confirmed owner/queue state are required even for zero. New-only reset does not require readable effective values, native readiness or usable anatomy. Pending, uncertain, disabled-owner and external-editor states block writes; an uncertain outcome queries its existing original receipt, not a new request. Raw engine refusals remain visible.

## Authored fixtures, all UNRUN

`model.unrun.test.ts` covers strict exact identity/state, both signs and bounds, independent capability, exact atomic replacement, new-neutral preservation, effective versus explicit shared intent, old/new conflict gates, no inherited shared prefill, unknown/malformed/conflicted values, source/revision/target/owner fences, neutral recovery, binding invalidation, explicit raw choices and nonmutation of neighboring operations.

`wiring.unrun.test.ts` covers exact route and preserved legacy routes/presets, unavailable unmanaged new state, dedicated capability DTO, canonical owner reuse, queue fences, truthful shared inputs, blank-start replacement, separate new-only reset, source/owner-keyed drafts, stale/repeated callbacks, original receipt lookup, raw refusals and honest limitations.

Unverified: every fixture assertion, TypeScript compatibility, compilation, mounted React behavior, bridge capability delivery, original-request receipt behavior, exact rapid face/source/scope/owner transitions, all-target replacement/refusal atomicity, malformed-state recovery, source skin/exclusion checks, geometry signs and measured support, tilt/yaw/occlusion/clipping, neighboring-face protection, neck/background quality, earlier-operation composition, real photographs at full resolution, history/undo/redo/replay, preview/export parity, packaging and complete handbook/development-pack acceptance. This leaf does not complete the 面部重塑 feature family.
