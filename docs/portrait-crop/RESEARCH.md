# Portrait composition: evidence and honest scope

Research/source review date: 2026-10-25. Implementation and all runtime,
numerical and photographic acceptance remain **AUTHORED / UNRUN**.

## Preserved requirements

`docs/development/handbook-traceability.json` preserves:

- `control:PC-32478:9`: 裁剪/AI智能裁剪.
- `control:PC-32478:15`: AI智能裁剪/头顶留白.
- `control:PC-32478:16`: AI智能裁剪/头部占比.
- `control:PC-32478:17`: AI智能裁剪/人脸位置.
- `control:PC-32478:18`: AI智能裁剪/保存裁剪预设, a distinct requirement.

The [official desktop crop guide](https://www.pixcakeai.com/guide/32478)
describes detecting facial landmarks and computing a crop from configurable
rules for headroom, head proportion and face placement. It separately describes
saving crop settings as presets. The page does not disclose numeric defaults,
ranges/steps, a head-proportion denominator, the face-position axes or conflict
resolution priorities. Therefore this slice documents its own mathematics;
it does not assert vendor-parameter compatibility or official-ID compliance.

No lost LNX alias is invented. Applied image geometry uses the existing
`lnx.crop.v1` identity. Saving the resulting rectangle through project state is
not a re-editable rule preset or per-photo automatic recalculation; `:18` stays
outside this scalar slice unless separately implemented and verified.

## Actual pre-existing gap

Source inspection of `ui/src/components/CropModal.tsx` finds centred aspect/zoom
math and a schematic frame, not source-owned crown/head-proportion/face-position
planning or genuine crop-photograph review. Existing `server.py::cmd_crop`,
preview/export owners and `ops/geometry.py` already own applying and sampling a
rectangle. New work should feed those owners, not replace their sampling or
introduce an incompatible hidden crop operator.

## Established landmark component and limits

Google's [Face Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
describes 478 facial landmarks from a model bundle. These are face-surface
observations, not a hair/skull crown detector. The [official Face Mesh V2 model
card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf)
identifies facial-surface output and explicitly states Apache License 2.0. It
also documents pose, partial-visibility and imaging limitations. The [upstream
MediaPipe code license](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE)
is Apache-2.0; code and model licensing are separate evidence, not inferred from
one another.

The repository already retains all detected faces, selected index, detector
digest and effective input-source binding in `face.py::FacePrecompute`. A fresh
host analysis may propose a chin and a clearly labelled center, but a forehead
landmark or top of a face box must not be relabelled a measured crown. The
selected person, visible crown, chin and center need genuine image review.

The existing `docs/model-licenses/models.json` pins FaceLandmarker float16/1:

- Artifact: `face_landmarker.task`.
- Byte count: 3,758,596.
- SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.
- Official artifact: [Google model distribution](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task).

Read-only local size/hash inspection of the existing bundled artifact matched
that record during this authoring pass. **No model was downloaded, installed,
initialized or run.** A hash match does not validate face accuracy, local
runtime compatibility or current-composite coordinate correctness.

## Why the first slice is manual-assisted

The original scalar planner accepts reviewed full-grid observations and local
headroom, head-height fraction, width/height aspect and horizontal placement.
Headroom plus head fraction imply vertical placement; an independently imposed
extra vertical target may be inconsistent. The planner rejects infeasible
constraints, clipping, rounded-out marks and empty windows instead of padding,
moving the subject, inventing pixels or silently changing requested fractions.

Capture must be from the current uncropped edited composite, with current
source, repair and geometry identity. Original import-time proxy landmarks may
be wrong after face/body deformation or optics. A source hash alone cannot
establish that the displayed photograph and the reviewed anchors share the
current destination grid. The host owns this complete proof and image review.

This supports an honest manual-assisted portrait-composition workflow; it is
not automatic crown detection, a guarantee that a whole hairstyle fits, face
recognition, or certification of official document-photo regulations. Full
current-source capture, actual candidate imagery and an explicit final review
are essential even when the scalar result is numerically feasible.

## Original code and verification boundary

All newly authored planner/state/adapter code is original GPL-3.0-or-later.
No MediaPipe implementation, model bytes or other upstream algorithm source
was copied into this module. Mature reuse is of the already owned landmark and
crop-renderer interfaces, not a new model disguised as independent geometry.
No change to repository model-licensing records is made by this isolated slice.

See `CORE.md` for the versioned ABI, exact public schema, local numerical
convention and authored fixtures. These sources are implementation evidence,
not a claim that native packaging, tests, real photographs, save/reopen or
preview/export acceptance has passed.
