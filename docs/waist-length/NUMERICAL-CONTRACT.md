# Waist length: original numerical contract

**AUTHORED / UNRUN.** This document is an analytic source-level argument and an
unexecuted fixture plan. It does not establish that a binary builds, native code
runs, floating-point checks pass, photographs look natural, or the control has
reached product acceptance. Compilation, numerical, integration and visual gates
remain open. No source argument below is a runtime certification.

Exact control `LNX-REF-PC-32473-C-5d33f285bb`; independent operation
`lnx.waist_length.v1`. The only portable recipe is `{"version":1,"amount":a}`,
finite −1≤a≤1. Negative/left shortens, positive/right lengthens; zero is neutral.
This is not upper-body/torso length, waist slimming, leg length or head scaling.
The [official mobile body-shaping guide](https://www.pixcakeai.com/guide/125979),
under “腰部长度”, describes those slider directions (read 2026-10-24; its page
labels the section separately from “上身长度”). This directional cross-reference
is not evidence of a vendor kernel, gain, desktop calibration or parity.
All numerical policy, support design and refusal thresholds here are original.

## Actual waist observations, never pose-derived waist anatomy

Body33 contains observed shoulders 11/12 and hips 23/24 but no actual waist
endpoints. Preparation therefore requires four manually marked, visible,
source-bound waist endpoints:

- `waist_upper_left`: source/screen-left actual upper-waist endpoint.
- `waist_upper_right`: source/screen-right actual upper-waist endpoint.
- `waist_lower_left`: source/screen-left actual lower-waist endpoint.
- `waist_lower_right`: source/screen-right actual lower-waist endpoint.

Each is an explicit normalized [x,y] pair on the EXIF-normalized full original.
These left/right labels refer only to source x order, not inferred anatomical
sides. No hip can stand in for a waist endpoint. No midpoint, ratio of torso
height, symmetry copy, hidden joint, clothing guess or default point is used to
create or repair a waist mark. If the actual endpoints cannot be seen and marked,
the active control refuses; a checkbox cannot make hidden anatomy visible.

Support is tied to the original content digest, dimensions/orientation, BodyRef
and retained actual Body33 observation digest. Manual source geometry is not a
portable preset or a substitute for retained nonmanual pose/face evidence.
Reanalysis or source/ownership/evidence change invalidates stale support.

Required actual Body33 landmarks 0…24 must be strictly inside the source with
visibility and presence each in [0.8,1]. Numeric validation does not establish
that manual marks are real anatomy. The host requires explicit
`bilateral_waist_endpoints_visible`, `waist_endpoints_manually_marked` and
`complete_upper_trunk_reviewed` confirmations alongside the actual-joint,
upright-posture, ownership, complete-head/hair, complete-arms/hands,
background-transition and no-occlusion/contact confirmations. They are nested in
`confirmations` and never automatically checked or inferred.

Reviewed support also supplies four strictly ordered horizontal boundaries
x0<x1<x2<x3, upper-background zero level y0, and full-upper-plateau start y1.
Separate complete head/hair and anatomical left/right arm/hand boxes must lie
strictly inside the horizontal plateau, below y1 and inside source clearance.
Each contains its corresponding actual head or shoulder/elbow/wrist/finger
observations. Every required point and waist mark must stay in that horizontal
plateau. The complete upper-trunk contour must be explicitly reviewed as fully
inside it; a few joints or box coordinates do not prove the complete contour.

The complete head box must end above the lower actual shoulder level. The host
requires an explicitly associated, uniquely confirmed source FaceRef, verified
nonmanual face evidence and source dimensions/orientation matching this body.
The full associated face box lies strictly within the complete head box and its
rigid plateau. This supports common face/body transport, not a separate face
image sampler. Foreign retained faces or actual bodies in the conservative
transport envelope refuse, including disabled retained evidence.

## Source-pixel anatomy admission

All values below are original-source pixels, not preview pixels. Let
S=max(y11,y12) and H=min(y23,y24). With upper waist marks UL,UR and lower marks
LL,LR, define U=max(UL.y,UR.y), P=min(LL.y,LR.y), W=P−U. Admission requires:

- S<min(UL.y,UR.y), U<P, max(LL.y,LR.y)<H, and W≥64 pixels.
- Each marked left-to-right pair has horizontal span ≥32 pixels and vertical
  difference ≤0.25 of its horizontal span.
- Each same-side marked upper-to-lower span has vertical difference ≥64 pixels
  and absolute horizontal difference ≤0.35 of its vertical difference.
- Each marked left x is strictly left of both the shoulder-pair and hip-pair
  midpoint x; each marked right x is strictly right of both midpoint x values.
  These are conservative consistency guards, not generated waist points or
  claims that pose joints measure the external waist contour.
- Each actual shoulder→hip side has vertical span ≥64 pixels and horizontal
  and depth differences each ≤0.35 of that span. Each actual shoulder/hip pair
  has horizontal span ≥32 pixels, vertical difference ≤0.25 of that span and
  depth difference ≤0.35 of that span. Depth uses normalized Body33 z scaled
  by original width−1. Strong bend, tilt, foreshortening or tiny spans refuse.

The pose only admits an enclosing observed shoulder-to-hip region. Neither S,
H, their difference nor the midpoint check creates a mark or sets the requested
waist displacement. Provided admission still holds, moving only the observed
hips while retaining the same explicit marks leaves the waist field unchanged.

## Forward field and exact endpoint effect

Use the marked waist span W, not the torso span H−S:

- Δ=−0.08aW, with no clamp, amount attenuation or automatic support expansion.
- Q(t)=6t⁵−15t⁴+10t³ for 0<t<1, 0 for t≤0, and 1 for t≥1.
- X(x) rises via Q from 0 at x0 to 1 at x1, stays 1 through x2 and falls
  via Q to 0 at x3; it is zero outside.
- Y(y) rises via Q from 0 at y0 to 1 at y1, stays 1 through U and falls
  via Q to 0 at P; it is zero outside.
- F(x,y)=(x,y+ΔX(x)Y(y)).

Both marked upper endpoints lie at or above U and inside the upper plateau,
so each translates by exactly Δ. Both marked lower endpoints lie at or below P
and remain fixed. Each side's vertical upper-to-lower waist span changes by −Δ;
the common axial span becomes W(1+0.08a). The Euclidean distance of each actual
marked side changes in the requested direction because horizontal separation
is unchanged and vertical separation remains positive. Sloped/asymmetric sides
need not have exactly an 8% Euclidean change; no such claim is made.

The entire reviewed head, hair, face, shoulders and upper trunk above U receive
one rigid translation. Their mutual distances are unchanged; the operation is
not head scaling or a torso-wide stretch. Complete arms/hands remain in the same
continuous field: portions above U translate rigidly, portions between U and P
follow the smooth waist transition, and portions at/below P stay fixed. The
operation does NOT promise that the whole arms translate rigidly when they hang
below the waist. All actual hips are below every lower-waist mark and stay fixed.

The compact upper/background and lateral transitions can move background and
clothing. No straight-line or texture-quality promise follows from invertibility.
Contacts, hidden contours, occlusion or incomplete visible anatomy refuse rather
than being separated into invented body parts.

## Analytic sufficient inverse bound, not executed evidence

Q′(t)=30t²(1−t)², so 0≤Q′≤15/8=1.875. For
mx=min(x1−x0,x3−x2) and my=min(y1−y0,P−U), the displacement d=F−I has the
following sufficient global Euclidean operator-norm bound in exact arithmetic:

L=1.875|Δ|sqrt(1/mx²+1/my²).

Preparation requires L≤0.45. This makes d globally Lipschitz with constant at
most 0.45. For each target q, p↦q−d(p) is a contraction on the complete plane;
its unique fixed point is F inverse(q). F is injective and onto that plane.
The analytic forward Jacobian is triangular:

DF=[[1,0],[ΔX′Y,1+ΔXY′]].

Thus 1−L≤det(DF)≤1+L, including 0.55≤det(DF)≤1.45. Every x-column is strictly
monotone in y for either sign. The inverse determinant lies within
[1/1.45,1/0.55]. This is a sufficient source-derived analytic argument, not a
sampled-grid heuristic, machine-checked proof or measured runtime result.

The map is identity at and outside every support boundary. At any fixed x,
strictly monotone columns with fixed upper/lower support endpoints send that
interval onto itself. Therefore an inset support sends the closed original image
domain onto itself in exact arithmetic for both signs. This does not permit
clipping inputs that other composed operators have moved outside the source.

## Bounded inverse and explicit floating-point refusal

The authored Rust evaluator starts p0=q and iterates p(n+1)=q−d(pn) at most
64 times, stopping only for a source-y step ≤1e−9 pixels. With |Δ|≤128 and
L≤0.45, the ideal contraction bound after 64 iterations is far below the explicit
acceptance residual. That does not establish floating-point behavior: each point
still must have a finite forward determinant within its analytic bound (1e−12
comparison slack), reconstruction residual ≤1e−7 pixels, inverse displacement
≤|Δ|+1e−7 and source/destination coordinates inside the closed image domain.
A failure refuses the band, not just one pixel. No clipping, identity fallback,
previous-success substitution, hidden guessed mark or amount reduction occurs.
Exactly zero is the identity map.

Native limits are 1048576 off-grid points per band, source side ≤1000000 pixels,
|Δ|≤128 pixels and a support inset of at least one source pixel. The full head
also has explicit translated-image clearance checks. The global derivative check
may reject an otherwise anatomically plausible requested amount when background
transition room is insufficient. It must not silently make the effect smaller.

The C ABI checks lengths, nulls, alignment, address overflow and overlap before
creating slices. Allocation liveness and no concurrent mutation are caller
obligations. The host snapshots all inputs and uses private output arrays. An
admission pass solves every point before writing either output buffer, so a
refusal leaves both outputs untouched under that contract. The source contains
no production allocation, pixel sampling, inference, callbacks or unbounded loops.

The Python bridge validates and copies buffers and calls the installed independent
Rust ABI; it contains no Python geometry/solver fallback. Its immutable state is
11 f64 over immutable bytes. Source-pixel maps must be conjugated by actual x/y
source-to-render scales for proxies, not rebuilt from cropped or resized pose.
A common compositor transports body, face, masks and landmark geometry together.
ABI details and exact buffer order are in `core/waist_length/ABI.md`.

## Established technique and original implementation boundary

[ITK's inverse-displacement filter](https://docs.itk.org/projects/doxygen/en/latest/classitk_1_1InvertDisplacementFieldImageFilter.html)
documents fixed-point inverse-field composition, and the
[Kitware fixed-point inverse-field module](https://github.com/KitwareMedical/ITKFixedPointInverseDisplacementField)
is a primary reference for that general technique. These references were read,
not imported, downloaded, installed or executed. This implementation reuses the
project's own original compact analytic technique, while giving waist length an
independent versioned kernel and explicit source-anatomy contract. The profile,
limits, derivative argument, admission rules and GPL-3.0-or-later source here do
not copy ITK, proprietary vendor code, models or hidden vendor calibration.

## Required evidence still UNRUN

- Both signs and neutral: marked upper/lower endpoint effects, entire rigid
  head/upper-trunk effect, fixed hips and independent torso/waist semantics.
- Marker provenance/source binding; missing, hidden, hip-substituted, reversed,
  displaced, tilted, tiny, stale or strongly bent supports refuse.
- Off-grid inverse residuals, analytic versus finite-difference determinants,
  monotone columns, transition continuity and image-domain preservation.
- Narrow support, source-edge, headroom, depth and displacement refusals;
  shape/range/alignment/overflow/alias checks and atomic refusal.
- Head/face/body evidence and current association, independent multiple people,
  foreign retained disabled evidence, undo/reset, presets and project roundtrip.
- Common face/body/mask sampling, proxy/full-resolution agreement, cancellation
  and late-result guards, packaged-library availability and supported ABI.
- Actual photographic review across supported poses, bodies, visible waist
  endpoints, varied clothing, hair, hands, faces and structured backgrounds.

Synthetic fixtures are solely authored numerical cases. They cannot stand in
for real model observations, manual user review, product execution, visual
acceptance or a completed gate. Static reads and content hashes are not tests.
