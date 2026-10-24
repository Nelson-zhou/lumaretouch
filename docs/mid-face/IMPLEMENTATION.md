# Midface length: source implementation candidate, acceptance UNRUN

## Exact scope and primary semantics

This slice addresses only **LNX-REF-PC-32466-C-ea67c9d99f**, `脸型/中庭`.
The frozen mapping lists a separate P1 research item without dedicated
acceptance cases; related PORTRAIT-007 is not coverage proof. The audit's
package 29 also includes philtrum and other lower-face/chin controls. This
implementation does not close that whole package or the facial reshape family.

The official guide, inspected 2026-10-24, describes leftward shortening and
rightward lengthening of the apple-cheek region to adjust midface length:
<https://wiki.pixcakeai.com/guide/9405.html>.
The frozen original reference is <https://www.pixcakeai.com/guide/32466>.
No redirect relationship is asserted. The official prose does not specify
landmarks, boundaries, pins, gain, range, segmentation or a numerical algorithm.

New `lnx.mid_face.v1` retains `{version:1, amount:0}`, finite signed [-1,1].
Negative shortens and positive lengthens a measured cheek-to-nose interval.
The original local policy below also deforms visible nose content. It is not
nose-preserving, apple-cheek-only, clinically measured middle-third anatomy,
3D reconstruction or a proprietary implementation/appearance reproduction.

## Distinction from existing controls

- `lower_face.v1` changes its nose-proxy-to-chin interval, with lips participating
  in a nonuniform lower-face warp. Its nose-origin plane stays fixed.
- This new midface map changes a band **above** the nose-base proxy and then
  translates the admitted lower-face points together in a flat plateau.
- `face_size.v1` uniformly scales both axes of the whole measured face in its core.
- Legacy `small_chin` pins the mouth and requests sparse screen-y chin/control
  displacements. Its historic topology, parameters and appearance are unchanged.

No existing recipe is reinterpreted, reset, migrated or used as a renamed midface
algorithm. Forehead, hairline, ear-defined short face and clinical proportions
are not inferred from a face mesh.

## Factual topology, mature practice and licensing

Pinned factual connectivity is from:
<https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py>.
The full eye contours are used, not only lower-eye points 145/374. Nose topology
includes 94→2 and 97→2→326; the oval includes 377→152→148. The cheek-area surface
triangles include 118–117–50 and 346–347–280. These are factual connectivity,
not official clinical landmark or apple-cheek segmentation labels.

The pinned canonical mesh was consulted only to understand relative topology:
<https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/modules/face_geometry/data/canonical_face_model.obj>.
Runtime never injects canonical coordinates or a synthetic face. Every location,
ordering, interval and support check uses retained actual-source measurements.
A direct cheek-proxy interval audit supplements endpoint and source evidence.

Destination-to-source image mapping, inverse construction, interpolation and
out-of-source handling are separate concerns:
<https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html>.
The new inverse is actually solved, not a negated forward field. The existing
single RGB/mask/recovery sampler is unchanged.

New code is original GPL-3.0-or-later. No external implementation, asset, model
or weights were copied or downloaded. MediaPipe source carries Apache-2.0;
existing producer provenance/licenses remain in force. Factual identifiers are
not a license to copy upstream assets or code without their notices.

## Measured original policy

A measured head frame supplies right and downward axes. Strict near-orthonormal
validation followed by roundoff normalization is not anatomical pose repair.
The fixed upper plane lies below the maximum downward projection of **all**
retained eye-contour vertices, plus a documented measured margin. Origin is on
the head-axis line through nose-base proxy point 2 at this plane. H is the
positive projected distance to point 2, subject to resolution/ordering guards.

The lateral flat core contains all retained geometry below the upper plane with
measured padding. The plateau endpoint is not blindly chin point 152: it extends
to the actual maximum projection of retained lower-face support plus padding.
Every lower-face source point whose common translation is claimed is audited
inside both the lateral core and the vertical plateau. Negative adjustment can
move the nose target below t=1 in destination coordinates; that is valid. The
true inverse must recover its original plateau point, not require destination
coordinates to occupy the same source plateau.

Let u,v be source coordinates in that frame, t=v/H, P the measured plateau end,
and τ=max(0.25,0.5×(P−1)). Let S(t)=t³(10+t(6t−15)). A compact lateral flat-top
window L(u) uses quintic edge transitions. V(t) is zero above 0, S(t) from 0 to 1,
exactly 1 from 1 through P, and a descending quintic from P to P+τ, then zero.

The forward map is u'=u and v'=v+0.08×amount×H×L(u)×V(t).
This is a nonuniform cheek-and-nose deformation followed by a constant lower-face
translation. The uncomposed upper-plane-to-nose interval becomes
H×(1+0.08×amount) in the lateral core. That local ratio is not a uniform scale
for the whole region, an aesthetic norm, an official gain or a quality result.

The standalone vertical derivative is bounded below by
1−0.08×|amount|×1.875/min(1,τ). The ABI bounds admit a floor of 0.4.
Lateral shear can remain nonzero; a positive determinant is not a photographic,
conditioning or arbitrary-composition guarantee. The final joint-map checks
remain authoritative and cannot prove between-sample injectivity.

Rust computes the bounded scalar inverse by solving physical shift
`d=k V(tq−d/H)`, where `k=0.08×H×amount×L(uq)`, and returns downward-axis vector d
as q−source(q). A safeguarded bracketed solve checks its residual and actual
representable source roundtrip before output. Native input validation, scratch
limits and transactional output are explicit; there is no runtime compiler or
fallback inverse. Neutral and at/outside support return zero.

These are floating-point checks, not exact arithmetic or executed validation.
Tiny returned displacements may round away during source subtraction or in the
existing float32 joint map. Difficult supported queries may be refused instead
of silently substituting another algorithm or reducing strength.

## Evidence, composition and workflow

Active edits require exact effective-source identity, canonical FaceRef, retained
478-point digest, authenticated face-skin observation, actual RGB and known
exclusion. Returned composite sources use independently owned analysis, never
original-source analysis rebound to a new identity. Actual upper/lower bilateral
cheek evidence is checked separately from the nose; nose pixels cannot substitute
for both cheeks. The translated lower region also requires its own measured
ordering, lip/source evidence and lower-interior support.

Known exclusion vetoes, real source skin and RGB establish conservative observed
support, not perfect visibility or apple-cheek/person-instance segmentation.
The complete rotated support rectangle, including neck/background feather, must
fit the real image margin and avoid every retained same-source foreign face.
No clipped halo, proxy-master promotion, synthesized hidden anatomy or silent
gain reduction is used to make admission pass. Closed lips are not forced open.

Midface is the outermost pullback after existing lower-face, whole-face-size,
contour/slim and legacy feature fields. Output, intermediate and final sampling
footprints are checked. The first four legacy slots and mouth slot 3 stay intact.
Prior effects can relocate eyes or other points into the new transition: upper-
plane and transverse invariance concern this map and its audited source geometry,
not arbitrary previously edited positions. Neck/background content moves in the
feather. No perfect background isolation is claimed.

The native UI separates selected effective readback/provenance from deliberate
shared explicit or blank input. Owner/source/target/revision/queue/pending/
uncertain fences remain. Neutral recovery needs the correct owner but not new
analysis/native capability; unmanaged documents receive an honest refusal.

Presets transfer only version and amount. Every explicitly confirmed target
reconstructs its own geometry and support. Generic derived preset admission stays
guarded. Existing snapshots, dormant history, undo/redo, frozen export and source
ownership remain the only owners. Original RGB16 and compatible opaque bounded
float derived sources retain the common pipeline; broader alpha/HDR is not
supported by clipping or flattening.

## Verification and remaining gaps

All fixtures are **AUTHORED / UNRUN**. No product imports, test collection/tests,
native builds, typechecks, inference, numerical/performance/photographic checks
or real UI/history/preview/export/batch acceptance were run. Source-connected
is not functional acceptance. Other facial-proportion requirements and the full
feature family remain incomplete.

Integration map: `core/mid_face`, `mid_face_native/state/runtime/people`,
`people_algorithms`, `people_render_runtime`, derived operation admission,
`mid_face_scope` and canonical preset replay, `ui/src/midFace`, native ready
capability and explicit offline packaging. Old lower-face, face-size, contour,
slim, deform, archive/migration and common sampler code remain unchanged.
