# PC-32466 nose geometry v1: source implementation, acceptance unrun

Status at integrated source handoff: shared preview/export/history/project,
UI/native receipts and target-recomputed preset/batch hooks are wired in source.
This is not executed product completion; Qoder acceptance remains required.
No application, test, build, typecheck, Rust compiler, inference, install or
model download was executed. Static source inspection is not photographic
acceptance and this document must not be read as a completed product claim.

## Source evidence and corrected semantics

- Frozen handbook `baseline_probe/manual-text.txt` lines 514–517 lists nose
  size/height/horizontal position/bridge/wing/tip. The accompanying
  `AI开发资料包/功能需求验收映射.json` contains all seven exact IDs below and
  explicitly says related module cases do not establish control-level coverage.
- Original https://www.pixcakeai.com/guide/32466 was inaccessible to the research
  tool. Current official replacement https://wiki.pixcakeai.com/guide/9405.html
  was inspected on 2026-10-22, nose section lines 264–297. It specifies scaling,
  vertical and horizontal position, bridge width, wing width and tip size.
- Important correction: the provisional longitudinal-scale interpretation of
  鼻高 was wrong. Official 鼻高 is vertical POSITION. Implementation moves the
  nose along the measured head-local up axis. It does not elongate the nose or
  raise a 3D bridge. 左右 is a single horizontal POSITION value, not a lockable
  left/right-identity parameter. Roll is respected; positive horizontal is
  viewer-right in the unrolled head coordinate frame.
- The guide supplies no numeric bounds/defaults used here. Our normalized
  [-1,1], displayed [-100,100], neutral 0 and conservative multipliers are
  expressly LumaRetouch product policy, not commercial implementation parity.

| Control | Exact ID, prefix PC-32466-C- | Positive amount at +1 |
|---|---|---|
| 鼻子 family | ba582ff45d | Six independent scalar parameters |
| 大小 / size | 0025490aa7 | +12% projected extent about root/base midpoint |
| 鼻高 / height | 180241806a | Upward translation 8% measured nose length |
| 左右 / position | 1ef85157f8 | Rightward translation 8% measured wing width |
| 鼻梁 / bridge | 6598ad2758 | +18% lateral bridge cross-section extent |
| 鼻翼 / wing | aed80c5608 | +15% lateral wing extent |
| 鼻尖 / tip | aec9e15569 | +15% local tip contour extent around tip point |

Negative reverses direction. All operations move original 2D texture. Nostril
support triangles translate rigidly even during global size changes: aperture
shape is conservatively protected rather than scaled. This is a documented local
geometry policy, not a claim to reproduce PixCake's proprietary rendering.
No texture generation, missing-nose reconstruction, surgery or 3D claim.

## Topology and licensing

Fixed `mediapipe==1.1.1`, verified directly against official upstream:
https://github.com/google-ai-edge/mediapipe/blob/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py

`FACE_LANDMARKS_NOSE` lines 261–287 supplies chain
168,6,197,195,5,4,1,19,94,2 and lower outline
98,97,2,326,327,294,278,344,440,275,4,45,220,115,48,64.
Eye/lip connectivity and bridge/tip/nostril support vertices are from this fixed
tessellation. Our cross-section roles and nostril support triangles are anatomical
uses of those vertices, not upstream per-pixel semantic labels.

MediaPipe: Copyright 2023 The MediaPipe Authors, Apache License 2.0,
https://www.apache.org/licenses/LICENSE-2.0 . Ship existing archived upstream
license with nose source. Original bounded Rust geometry is GPL-3.0-or-later
under this repository's license. Existing TPS implementation is reused. No
unrelated AGPL colour operator or commercial algorithm is imported.

## Geometry, visibility and explicit refusal

Only real selected normalized 478x3 MediaPipe landmarks are accepted. Scene/
person ownership is captured in document state; queued commands compare explicit
source document and face fingerprint, including after face switching. Presets
carry numeric intent only; target ownership and controls are reconstructed.

Landmarks alone never authorize visibility. Model-provenance-backed semantic
hair/clothes/background exclusions plus actual source RGB are required. Global
size/vertical/horizontal requests require bridge, tip and both nostril supports.
Bridge width requires its local visible support; wing width requires both
nostril supports; tip requires tip and both nostrils. Photometric evidence is a
conservative contrast/dark-support heuristic, NOT complete nose, spectacles,
mask or occlusion segmentation. Low-contrast/overexposed/underexposed regions,
missing provenance, sideface/foreshortening, clipped support and degenerate
triangles refuse explicitly per requested control. False negatives and missed
occluders remain photographic acceptance risks; prediction is not proof.

Rust computes forward control displacement in the measured head frame. Existing
TPS solves at target P+D to obtain source pullback. Outer compact support, eye/
iris/lip identity controls, hard-zero eye/lip polygons and local nostril rigid
pullbacks constrain geometry. Nose never inherits automatic nose-tip identity
anchors or eyebrow bridge hard-zero masks. TPS dedupe conflicts refuse, and an
explicit control-hit check refuses protection that would cancel requested
motion. Numerical fold probes reject sampled determinant below 0.15; they are
not proof of global injectivity between probes. Native requests larger than
28% of max(nose width,height) refuse instead of silently clipping.

## One-sampler composition contract

Let A(x)=x-D_auto(x), B(q)=q-D_brow(q), N(r)=r-D_nose(r).
Final source coordinates are N(B(A(x))). `nose_shape_field.compose_delta` takes
UNCOMPOSED automatic delta plus optional brow and nose fields, evaluates each
at its actual float64 off-grid input, and casts only final displacement to
float32. Never call old brow composition first and pass that result with brow
again. Never sum nose/brow/automatic fields at the same x and never run three
full-image warps. No image sampling happens in the composer.

If nose is neutral, delegate the existing brow composition exactly; no new
version/cache invalidation on repeated neutral sync. With no brow either, retain
input auto-delta object identity. Preview caches add nose version only when
active. Export recomputes full-resolution controls from actual RGB8/RGB16 and
uses actual final component peak for halo, not per-layer guessed maxima.

Every source-bound consumer uses the final prepared warp: source selection/
semantic masks, eye enhancement weights, under-eye deltas, local grades,
background mattes and effect-recovery masks. Retain existing manual liquify and
optics order. Export tiles adopt the one combined full-resolution displacement
slice; do not attach full-frame nose/brow fields to tile pipelines or recompose.

## Shared integration hooks (wired in source, acceptance unrun)

1. `server.py`: import NOSES/NOSER; initialize/default/remember/capture/replay
   `_nose_shape` and `_nose_shape_owner`; ready protocol; doc_state status;
   editing/history command allowlists; active/targeted checks; all lifecycle sync
   points beside BROWR.sync; strict replay; face-switch refresh; current/parked
   export and inspection snapshots; snapshot-to-fields conversion; enabled list.
2. `portrait_geometry_dispatch.py`: delegate command to correlated
   `nose_shape_receipts.apply` and finalizer to `.finish`; use shared eyebrow
   result/status dispatcher integration and explicit gesture history grouping.
   Do not report native `requested:true` as completed editing.
3. `project.py`: add nose record validation at all load/save/nested history/redo
   validation sites beside existing brow validations; reject orphan active state.
4. `vram.py`: initialize/reset/clear nose beside brow; active early-return gate;
   append active nose version to warp key; replace BROWR.joint_delta with
   NOSER.joint_delta ONCE (it includes brow); count resident bytes; broaden all
   source-mask/enhance/background alignment conditions to nose and tile-combined
   nose. Reuse `brow_shape_consumers.apply_enhance`, not a second sampler.
5. `color_action_readiness.py`: identical active/version cache key expansion so
   picker actions cannot reuse a pre-nose warp. Preserve exact neutral keys.
6. `export.py`: ExportSpec nose recipe/face fields and validation; build both
   source-domain fields; replace compose_brow_delta call with final nose composer;
   use final peak in margin; flag nose_shape_combined on adopted tile delta;
   report full-resolution nose facts. No proxy fallback or silently omitted effect.
7. `export_recipe.py`: forbid generic cross-document active nose export; call
   NOSER.configure_export for bound document snapshots, validate recipe.
8. `scope.py`: register lnx.nose_shape.v1, recipe-only check, state fields and
   single-face/recompute policy. `batch_preflight_controller.py`, `batch_sync.py`,
   `preset_controller.py`, `local_grade_preset_review.py`: install/check target
   original RGB via NOSE.validate_target, both frozen preflight and commit;
   strict replay. Auto-optics paths validate through their frozen candidate full
   upstream render, which now includes nose export validation on the target.
   No new face inference or source-face substitution is introduced.
   Parked target applied status requires successful actual-target support check.
9. `ui/src/native.ts`, `ui/src-tauri/src/main.rs`: nose capability, typed report,
   correlated command/result/status API and native registration. Reuse the
   eyebrow one-inflight/latest-intent owner with explicit gesture IDs; match
   request/document/face, wait post-history receipt, stop on uncertain outcomes.
10. `RetouchPanel.tsx`: exact PC-32466 鼻子 family plus six paths; render one
    NoseShapeControls family and consume six child leaves without disabled
    duplicates. Keep existing skin/wrinkle/eyebrow/lip/tool placement intact.
    `batchScopeOptions.ts` and `presetModel.ts`: independent nose module labels.
11. `packaging/stage-engine.sh`: build-nose-shape.sh + package Rust source,
    GPL license, this document and archived MediaPipe Apache license. No runtime
    compilation/download or Python substitute if the bounded Rust core is absent.
12. `docs/p0/registry-extensions.json`: add the six-control recipe envelope;
    correct the existing brow/lip recipe omissions separately from the immutable
    baseline. Numeric policy is explicit; registry entries do not prove acceptance.

## Acceptance still required locally

Added source tests cover strict recipe data, identities, exact IDs, neutral
cache/object reuse, nonconstant order and band invariance, no nose identity pin,
RGB-depth admission and parked-target keyword/identity contracts. They are NOT
executed. Rust and UI model tests are also source-only.

Required Qoder gates: package native ABI; typecheck/build; per-control positive/
negative/zero real photos; roll/mild yaw/strong side/occluders/low contrast;
nostril and eye/lip grid integrity; high combined settings and Jacobian failures;
fast continuous and repeated gestures, keyboard/reset, reordered/stale receipts,
photo/face switches and timeout uncertainty; undo/redo/save/reopen; target batch
preflight/commit/refusal; no wrong source owners; combined auto+brow+nose plus
local masks/enhance/recovery; RGB8/RGB16 full-vs-multiple-tile sizes and halo;
neutral bitwise/cache regression; preserve all previous tool slots/features.
