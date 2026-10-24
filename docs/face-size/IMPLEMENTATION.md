# Whole-face size: source implementation, acceptance UNRUN

## Exact requirement, not another slim-face alias

**LNX-REF-PC-32466-C-728fc62cdd**, `PC-32466 / 脸型/小脸`, is a distinct
whole-face-size control. Frozen mapping lists P1 research and no dedicated
acceptance case; related PORTRAIT-007 is not implementation or photo evidence.
The frozen manual lists it separately from slim face, V face, short face and
face width. `ui/src/spec/refine.json` does not prescribe range, default, step
or left/right unlock.

Primary official semantics were inspected on 2026-10-24:
<https://wiki.pixcakeai.com/guide/9405.html>, 小脸. Negative enlarges the whole
face, positive reduces it. The guide does not reveal a solver, center, influence
region or gain. All such numeric choices here are original local policy.

This operation does **not** reuse `FaceContourField`: that field intentionally
pins eyes, brows, lips and nose, which would contradict uniform whole-face size.
The new core moves their contents, sizes and mutual distances together in its
uniform region. It is neither global canvas resize nor a renamed contour slider.

## Primary technique and licensing

- OpenCV geometric transforms describe destination-to-source mappings and the
  separate interpolation/border problem:
  <https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html>.
- Schaefer, McPhail and Warren's similarity-transform discussion distinguishes
  uniform scale from affine shear:
  <https://people.engr.tamu.edu/schaefer/research/mls.pdf>. This implementation
  is not their MLS algorithm and copies none of their code.
- GIMP documents aspect-preserving selected-region scale separately from affine
  shear: <https://docs.gimp.org/3.0/en/gimp-tool-handle-transform.html>.
- Factual topology is the existing verified 36-point MediaPipe oval and actual
  retained 478 landmarks:
  <https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py>.
  That upstream file is Apache-2.0. Point numbers are factual references; no
  upstream algorithm/model/weights were copied or downloaded. Existing producer
  licenses remain in force; estimated landmarks do not prove visibility.

New Rust/Python/UI code is original GPL-3.0-or-later. There are no new model or
weight requirements. References support mathematical and architectural practice,
not proprietary equivalence or photographic acceptance.

## Versioned analytic inverse map

New portable operation `lnx.face_size.v1` stores only
`{version:1, amount:0}` with a finite scalar in [-1,1]. Scale is
`s = 1 - 0.06 * amount`, hence 0.94 through 1.06. These modest limits are
unmeasured policy, not official values or a validated optimum. Zero bypasses
new anatomy/native work and leaves existing geometry unchanged.

The native parameter vector is
`[cx,cy,right_x,right_y,up_x,up_y,hx,hy,inner,outer,scale]`.
Coordinates are source pixel centers, normalized landmarks mapped with N-1.
The measured orthonormal head frame defines elliptical radius r. The flat core
contains every measured source and intended target landmark, including interior
features, with padding. Measured runtime uses inner radius 1 and outer radius 1.25;
the complete ellipse must fit, not be clipped or silently weakened. This transition
width is unvalidated local policy. Outside it the added field is exactly zero.

For destination q, the native displacement is
`D(q) = (1 - 1/s) * w(r) * (q-c)` and the source point is q-D(q).
The coefficient is evaluated as `(s-1)/s` to avoid reciprocal-subtraction
cancellation near unity. A nonzero amount whose scale rounds to 1 is refused,
not silently published as an applied effect. Inside the core w=1, so the pullback
is exactly c+(q-c)/s. In the transition,
w is one minus the quintic smoothstep. This defines the inverse field directly;
it is not an approximation obtained by negating an arbitrary forward field,
and it is not the inverse of an independently claimed forward blend formula.

With k=1/s-1, inverse radial/tangential factors have a conservative lower bound
`min(1,1/s) - abs(k)*1.875*outer/(outer-inner)`.
The native boundary refuses a bound below 0.2. This follows from the quintic
derivative maximum and addresses the standalone analytic map, not floating-point
implementation acceptance or injectivity after arbitrary other fields.
The existing final combined map still checks its sampled Jacobian.

The ABI validates finite coordinates, exact array sizes, orthonormal frame,
positive axes, ordered radii, bounded scale, pointer spans and non-overlap.
Native calls are bounded to 65,536 points with bounded scratch. Python snapshots
inputs independently and has no fallback or runtime compiler. Packaging uses an
explicit atomic build script, not executed during authoring.

## Real source and composition

Active work requires the exact enabled FaceRef, effective source dimensions and
digest, retained actual MediaPipe landmarks and their canonical float32 hash,
source-owned face-skin observation and same-source exclusion. Original images
and returned immutable creative sources use their independently owned analysis.
No original analysis is rebound to a returned composite.

Admission conservatively checks frontal/mild-yaw geometry, resolution, measured
oval/feature layout, real skin/RGB support and known exclusion. Complete influence
must lie inside the image and avoid all other retained same-source face boxes,
including disabled/manual/unresolved neighbors. Tiled evidence scans and bounded
native bands avoid full-grid temporary coordinate meshes. Existing retained
semantic validation still has its established full-frame working-set admission.
Resampled semantic support retains producer metadata and is not fresh full-source
segmentation or proof of exact silhouette/occlusion ownership.

The size map is an **outermost pullback** of the prior face image:
first q1=q-Dsize(q), then qsource=q1-Dprior(q1). The displacement sum uses those
actual off-grid coordinates, not independently sampled grids. All four legacy
feature slots and mouth protection slot 3 remain intact; contour/slim may be in
the prefix. Existing prior edits intentionally change proportions themselves;
the uniform-core guarantee concerns this new scaling map, not a claim that all
other effects become uniform or remain wholly inside its flat core.

Composition guards compare output, intermediate and final source footprints
against image bounds and foreign faces. They do not certify unchanged legacy
prefix behavior. Existing stable-face ownership, joint-map admission and the one
canonical RGB/mask/recovery sampler remain authoritative. No second resized RGB
bitmap, image-generation output or independent history owner is introduced.
The existing final bilinear sampling policy is unchanged; reduction of fine
texture has no newly validated antialiasing or detail-retention guarantee.

## User workflow, persistence and target transfer

The exact 小脸 route gets its own signed control and authoritative readback.
Shared-scope intent must be deliberate, not a selected face's inherited value
silently treated as every target's setting. Pending/uncertain receipts, source and
target revisions, competing edits and core readiness remain fenced. Neutral reset
still requires the correct editable owner. Unmanaged documents do not receive a
global resize fallback. Existing saved deformation operations/presets are unchanged.

Canonical graph leaves retain project save/reopen, dormant documents, virtual
copies, undo/redo, frozen export and returned-source ownership. Actual RGB16 or
compatible opaque bounded derived float sources remain in the shared pipeline;
no RGB8 proxy is promoted to an export master. Presets carry one scalar, never
source images, masks, landmarks or fields. Each explicitly confirmed target
rebuilds its own field and support. Generic derived preset routing remains refused.

## Remaining limits / integration map

All fixtures are authored **UNRUN**. No product imports, tests, native build,
typecheck, inference, visual inspection, numerical/performance or photographic
acceptance were executed. PORTRAIT-007 and full feature-family acceptance remain
pending. No all-32-creative completion is claimed.

The transition transports adjacent hair, neck and background; there is no perfect
segmented-background invariance. This is visible 2D source-content transport,
not 3D pose correction, hidden-feature synthesis, AI reconstruction or a new
person-instance segmentation model. Strong yaw, clipped/occluded/ambiguous support
may refuse. Broader alpha/HDR remains unsupported rather than clipped.

- `core/face_size/`, `face_size_native.py`, `face_size_state.py`: new checked
  analytic scale and portable recipe, distinct from contour core.
- `face_size_runtime.py`, `face_size_people.py`: measured source admission,
  continuous field and guarded outermost composition.
- `people_algorithms.py`, `people_render_runtime.py`, `creative_derived_effects.py`:
  actual original/derived consumers, separate facts and existing common sampler.
- `face_size_scope.py`, `people_scope.py`, `scope.py`, `workflow_ports.py`:
  exact owner/source/target preset capture and existing replay/transfer owner.
- `ui/src/faceSize/`, RetouchPanel, native capability and operation labels:
  source-owned interaction without a second edit queue or history.
- Explicit package staging includes Rust source, header, tests and GPL license.
  Registry/route documentation records source connection, not acceptance.
