# Lower-third length: original source implementation, acceptance UNRUN

## Requirement and distinct operation

Only **LNX-REF-PC-32466-C-1ae8316994**, `PC-32466 / 脸型/下庭`, is addressed.
Frozen mapping marks it P1 research, with no dedicated acceptance cases;
PORTRAIT-007 is a related module case, not coverage proof. Audit package 29 also
contains philtrum, middle-third and chin controls: this slice does not close it.

Primary official semantics inspected 2026-10-24:
<https://wiki.pixcakeai.com/guide/9405.html>. Negative shortens, positive lengthens.
The official text does not prescribe gain, anchors, exact influence, numerical
method or bilateral unlocking. Those choices below are original local policy,
not a claim of proprietary appearance equivalence.

`lnx.lower_face.v1` stores only `{version:1, amount:0}`, finite amount [-1,1].
It moves admitted lower-face interior, including lips, along the measured head
axis. Existing `small_chin` pins mouth landmarks and requests sparse screen-y
chin/control motions; that saved recipe and its problematic old topology are
unchanged. New `face_size.v1` scales the entire face in both axes, whereas this
map preserves its transverse coordinate and leaves its upper half-plane fixed.
No legacy parameter is automatically converted or silently reset.

Short-face, forehead and hairline controls are not claimed. The official short-
face description includes width and length below ears; 478 face landmarks cannot
be presented as measured ears or a measured hairline.

## Primary practice, topology and licensing

- Destination-to-source mapping and interpolation are distinct concerns:
  <https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html>.
  This implementation computes a checked inverse rather than negating a forward
  displacement and then sampling twice.
- Pinned factual topology:
  <https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py>.
  Nose connections include 94→2 and 97→2→326; the oval includes 377→152→148.
  Point 2 and point 152 are measured **proxies**, not clinically identified
  subnasale/menton or proof of visibility. Regional use is our own policy.
- Lower-face vertical anthropometry provides conceptual context, not validation
  of model points as clinical landmarks:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC10179155/>.
  No clinical accuracy, attractiveness norm or medical result is claimed.

New code is original GPL-3.0-or-later. Factual point identifiers are referenced;
no upstream implementation, images, model or weights are copied/downloaded.
Existing producer licenses and provenance remain required. MediaPipe upstream
code is Apache-2.0, but no new Apache code incorporation is part of this slice.

## Original compact monotone map

Origin is the retained nose-base proxy. An orthonormal head frame defines right
coordinate u and downward coordinate v. H is the projected nose-to-chin interval.
Strictly validated near-orthonormal axes receive documented roundoff
normalization, not anatomical pose correction. Width and pose evidence must be
measured; no template or extrapolated hidden face is introduced.

Let S(t)=t³(10+t(6t−15)). A lateral flat-top window L(u) contains the admitted
lower-face span, with a smooth compact outer feather. Let V(t) be S(t) for
0<t≤1, 1−S((t−1)/τ) for 1<t<1+τ, and zero elsewhere. The forward map is:

- u' = u
- v' = v + 0.08 × amount × H × L(u) × V(v/H)

Runtime τ is 0.5. The chin proxy interval in the lateral core becomes
H × (1+0.08×amount); the interior is a **nonuniform** smooth warp, not a uniform
vertical rescale. Lips move without identity pins. The new map leaves v≤0 and
its transverse coordinate fixed; that does not erase prior edits or guarantee
that prior relocated points remain in the same region.

The standalone vertical derivative is bounded below by
1−0.08×|amount|×1.875/min(1,τ). Runtime policy gives a lower bound of 0.7.
This mathematical bound is not numerical or photographic acceptance, and does
not prove injectivity of arbitrary combined edits between sampled locations.

The Rust kernel solves the scalar inverse with a bounded bracket and checked
residual, retaining physical displacement to avoid subtracting nearly equal
source/destination coordinates. It returns q−source(q), not a forward field.
Floating-point inversion is approximate with explicit checks, not claimed exact.
A small retained f64 displacement can still round away in source coordinates or
the established float32 joint map; a nonzero control is not a promise of visible
pixel change at every magnitude.
Neutral and outside support are exact zero. There is no fallback solver, runtime
compiler, model invocation, resize bitmap or second RGB sampling owner.

## Source admission and composition

Retained effective-source identity, exact FaceRef, canonical 478-point digest,
face-skin observation, excluded support and actual source RGB must agree.
Returned immutable composite sources use their own analysis, never original-
image analysis rebound under another digest. Landmark ordering and pose checks
alone cannot prove visibility; real observed lower-face evidence is also needed.
Measured coincident/touching inner lips are permitted within a bounded ordering
tolerance; this operation does not require or synthesize an open mouth.

A complete rotated support rectangle, including the below-chin feather, must fit
inside the actual source margin and avoid every retained same-source other face.
It is never clipped, filled from a proxy, silently attenuated or expanded around
an outlying landmark to make a request pass. The feather transports adjacent
neck/background content: it is not a measured neck mask or perfect isolation.
Known exclusion can veto; this is not full instance/occlusion segmentation.

The lower-third pullback is outermost, after existing contour/slim/whole-face-size
fields. Queries first pass through the lower-third inverse, then through the
previous face-image inverse. Output, intermediate and final source footprints
are protected. The legacy first four slots and mouth slot 3 remain unchanged.
The existing joint-map safety checks and common RGB/mask/recovery sampler remain
in charge. Existing bilinear reduction/detail limitations remain unvalidated.

## UI, presets, persistence and limits

The dedicated 下庭 control shows current selected-face value/provenance separately
from shared-target explicit intent. Shared edits require explicit input, not an
inherited value silently treated as every person's setting. Owner, source, target,
revision, pending and uncertain transaction fences remain active. Neutral reset
requires a valid owner but not new native/anatomy capability. Unmanaged documents
receive an honest refusal, not a global image transform.

Only the versioned scalar is portable. Targets rebuild their own measured field;
no face, source, mask, landmarks or control coordinates are copied. Generic
returned-source preset routing remains guarded; confirmed people mappings use
target-owned evidence and the full canonical renderer. Project snapshots,
dormant history, undo/redo and frozen export remain with the existing owner.
Original RGB16 and compatible opaque bounded derived float sources stay in their
current pipeline. Broader alpha/HDR is not supported by clipping.

All authored fixtures are **UNRUN**. No product imports, builds, tests, inference,
typechecks, numerical/performance/photographic acceptance or real UI/history/
preview/export/batch acceptance have run. No complete facial-family or all-32-
creative completion is claimed.

Integration ports: `core/lower_face`, `lower_face_native/state/runtime/people`,
canonical `people_algorithms` and `people_render_runtime`, derived operation
admission, `lower_face_scope` plus existing preset replay/transfer, dedicated
`ui/src/lowerFace`, ready capability and explicit offline staging. Original
legacy algorithms, face-size code, archives and the common sampler are unchanged.
