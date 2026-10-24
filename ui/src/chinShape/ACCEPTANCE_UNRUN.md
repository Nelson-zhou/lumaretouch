# 尖下巴 UI: authored, not runtime accepted

Status: AUTHORED / UNRUN. Source inspection and source editing only. No project imports, execution, tests, builds, type checks, application runs, inference, downloads or real-photo acceptance were performed. Authored fixtures are not evidence of passing tests.

## Exact requirement and scope

- Exact leaf: `LNX-REF-PC-32466-C-ed7837df9a`, `PC-32466|脸型/尖下巴`.
- Frozen reference: https://www.pixcakeai.com/guide/32466 . Current semantic reference inspected on 2026-10-24: https://wiki.pixcakeai.com/guide/9405.html , section 尖下巴. It distinguishes rounder versus sharper direction and explicitly supports left/right unlocking. It does not establish a numeric scale, gain, exact support boundary, curvature metric or acceptance threshold.
- Exact UI route: `PC-32466|脸型/尖下巴` → `chin_shape.v1`. Distinct operation: `lnx.chin_shape.v1`; strict state `{version: 1, linked: boolean, left: number, right: number}`, finite side values in `[-1, 1]`. Linked states require equal left/right numbers. Neutral state is linked with both values zero.
- Display `[-100, 100]` is product-local, not an official calibrated quantity. No support measurements, numerical gain, curvature result or photograph-quality score are invented in the interface.
- Existing 瘦脸, 小脸, 中庭, 下庭, 太阳穴, 颧骨, 下颌, 收下巴, feature routes and historical presets are preserved. No `small_chin` migration, equivalent-strength claim or legacy auto-reset is introduced.
- Unmanaged documents explicitly report 尖下巴 unavailable; there is no historical small-chin, chin-length, lower-face, jaw, slim-face or direct-native fallback.

## Geometry language and limitations

The intended local effect is lower-chin horizontal taper: positive narrows inward toward sharper appearance; negative expands outward toward rounder appearance. It is not 下巴长短, 收下巴, 下庭, 小脸, 瘦脸, V 脸, jaw-angle editing, precise curvature control, clinical correction, AI reconstruction, 3D sculpting or an alias of an older operation.

Only the newly added map is described as not moving the chin along the head-local vertical axis. A rotated head frame can still produce screen-vertical displacement. Earlier composition may already have moved points; the UI does not promise unchanged final chin position, global image rows or preserved geometry under every stack. Link equality is numeric, not a guarantee of visually symmetric results on an asymmetric face.

The current effective source may be the original photograph or an already returned composite. The renderer recalculates each target's own source-owned chin support. The UI does not fabricate support facts or claim that landmark detection proves visibility, occlusion safety or anatomy suitability. Native readiness is only core availability, not per-target support or acceptance. Existing compatibility and source validation remain engine-owned; raw refusals are shown without translation into invented capability flags.

Warnings include head tilt, yaw, occlusion, crop/clipping, adjacent faces, neck/background/edge feather motion, and earlier geometry composition. The UI makes no promise to reconstruct unseen areas or leave all background unchanged.

## Ownership and intended interaction

- Existing `PeopleOwner` remains the sole command, queue, receipt, undo/history and replay authority. Only `/linked`, `/left` and `/right` of `lnx.chin_shape.v1` are written.
- Selected effective values and per-leaf provenance are distinct from target-owned explicit values. Independent face scopes may edit the exact selected face's actual values. All-people, group and person scopes without their own explicit mode or number start blank; a preview face's inherited mode or side value is never used to seed a shared write.
- Raw empty, malformed, nonfinite and out-of-range numeric text is rejected, not coerced to zero. Drafts never submit on mount or blur.
- Unlock writes `/linked=false` only and retains the side values. Enabling/re-enabling linked requires an explicit new numeric choice and atomically writes `/linked=true`, `/left=value`, `/right=value`; it never copies or averages an existing side. While linked, numeric adjustment atomically writes both sides equally. Independent numeric adjustment writes only the selected side.
- Neutral recovery atomically writes only `/left=0` and `/right=0`; it does not change linked mode, unset inheritance, migrate legacy state, modify another operation or clear overrides at other scopes. It needs a valid source-bound target and confirmed owner/queue state, but not native readiness, readable effective values, selection/anatomy support or successful inference.
- Source identity, document epoch/revision, state revision, association revision, face identity/analysis revision, target, selected face, read provenance/conflicts, explicit values and refusals participate in the binding. Owner `patch`/`check` identity changes reset draft keys too. Mounted/current-binding/current-owner checks fence late callbacks; a submission latch prevents repeated-click writes before the owner responds.
- Pending, uncertain, disabled-owner and competing-editor queue states block mutation. Uncertain work queries the existing original request rather than resending it. Engine refusals and owner errors remain visible. Structural linked inconsistencies remain unknown until a valid response or explicit neutral recovery.

## Authored verification, all UNRUN

`model.unrun.test.ts` covers exact identity, strict state and equality, both signs, bounds, dedicated capability, atomic equal linking, flag-only unlock, provenance versus explicit values, shared raw-blank behavior, malformed/stale/conflicted reads, linked-inconsistent reads, owner/source/revision/target fences, neutral recovery without native/anatomy, nonmutation and no guessed coexistence policy.

`wiring.unrun.test.ts` covers exact route, old routes and presets, unmanaged refusal, dedicated DTO fields, the single existing people owner, competing-editor fences, no borrowed or fake-zero inputs, atomic linking and preserved unlock/reset state, source/owner-keyed drafts, stale callback and repeated-click guards, query-only uncertain recovery, raw refusals and honest source/geometry/acceptance text.

Still unverified: TypeScript compatibility, compilation, every fixture assertion, mounted React interaction, bridge capability delivery, actual renderer/native geometry, subject-left versus viewer-left, both signs, linked/unlinked writes, rapid source/face/scope/owner switching, shared-target outcome validation, conflict recovery, malformed-state recovery, tilt/yaw/occlusion/clipping refusals, adjacent-person protection, neck/background quality, earlier-operation composition, history/undo/redo/replay, preview/export parity, full-resolution photographs, packaging and complete handbook/development-pack acceptance. These source contracts do not substitute for runtime or visual QA. This leaf does not complete the 面部重塑 family.
