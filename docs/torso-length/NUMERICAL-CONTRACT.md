# Upper-body length: original numerical contract

**AUTHORED / UNRUN.** This is a source-level contract and unexecuted fixture plan,
not proof that a binary builds, a product runs, numerical fixtures pass, photographs
look natural or an experience has reached acceptance. Those gates remain open.

Control `LNX-REF-PC-32473-C-f1662d2dec`; operation `lnx.torso_length.v1`.
The only portable recipe is `{"version":1,"amount":a}`, finite −1≤a≤1.
Negative/left shortens, positive/right lengthens; zero is neutral. This is not
waist length, waist slimming, shoulder width, neck length or a face-size alias.
All gains, tolerances and refusal thresholds below are original local policy,
not reverse-engineered or claimed vendor calibration.

## Observations and review, not synthetic anatomy

The source is the EXIF-normalized full original, tied to its content digest,
dimensions, BodyRef and retained actual Body33 observation digest. Shoulders are
11/12 and hips are 23/24. No waist, hairline, hidden joint or replacement point is
manufactured. Required upper-body landmarks 0…24 must be inside the image with
visibility and presence at least 0.8. User confirmation cannot override a failure.

Reviewed normalized support supplies four ordered horizontal boundaries
x0<x1<x2<x3, upper background zero level y0, and full upper plateau start y1.
Three separately reviewed boxes describe the actual complete head including hair,
and the full left/right arms including hands. Every box is strictly inside the
horizontal plateau, below its upper start and within image clearance. Actual
head points 0…10 must lie in the head box and actual shoulder/elbow/wrist/finger
points in the corresponding arm box. Observed points alone do not prove the
complete contour; explicit visible-contour and no-occlusion/contact review is
still required. All review flags are nested in `confirmations`, never defaulted
to true by inference.

The complete head box lies above the lower shoulder level. All three boxes may
overlap naturally. Arms may extend below the hips: portions above shoulders
translate rigidly, shoulder-to-hip portions follow the same smooth torso map,
and portions at/below the upper hip level remain fixed. Arms are NOT separately
cut out, teleported or promised to be rigid below the shoulders. Contacts, hidden
contours, incomplete hair/head, source-edge cuts and uncertain ownership refuse.

Support also binds the exact associated FaceRef, its reviewed full face box and
canonical face-evidence digest. The host requires a current explicit body/person
association, exactly one confirmed source face with verified nonmanual evidence,
the same source dimensions/orientation, and the whole face box strictly within
the full head box and rigid plateau. Reanalysis, reassociation or changed evidence
invalidates stale support. Foreign retained faces or observed bodies in the
conservative transport envelope refuse rather than silently moving another person.

## Forward map and true endpoint length change

All following values use exact source pixels. Define:

- S = max(y11,y12), P = min(y23,y24), H = P−S.
- Δ = −0.08aH, without clamping or automatic reduction.
- Q(t)=6t⁵−15t⁴+10t³ for 0<t<1, extended as 0 for t≤0 and 1 for t≥1.
- W(x) rises via Q from 0 at x0 to 1 at x1, is 1 through x2, then falls
  via Q to 0 at x3; outside it is 0.
- B(y) rises via Q from 0 at y0 to 1 at y1, remains 1 through S, then falls
  via Q to 0 at P; outside it is 0.
- F(x,y)=(x,y+ΔW(x)B(y)).

Both actual shoulders are in the upper plateau, hence translate by exactly Δ;
both actual hips are at or below P and stay fixed. Each actual side's vertical
shoulder-to-hip distance changes by −Δ, and its Euclidean shoulder-to-hip distance
changes in the requested direction because vertical ordering remains positive.
The reference axial span H becomes H(1+0.08a). This is a real length change, not
an interior warp with both endpoints fixed. Sloped/offset sides need not change
their Euclidean distance by exactly 8%; no such claim is made.

The complete associated face/head/hair in the upper plateau receives exactly
the same translation as shoulders. Body, face, masks and landmarks enter the
existing common composition/sampler path; there is no detached face image sampler.
Surrounding background in the reviewed transitions can move. A conservative
guard is not a promise that straight backgrounds or clothing remain attractive.

## Sufficient global inverse certificate

Q′(t)=30t²(1−t)², so 0≤Q′≤15/8=1.875. Let
mx=min(x1−x0,x3−x2) and my=min(y1−y0,P−S). The original displacement d=F−I has
the global Euclidean operator-norm bound

L = 1.875 |Δ| sqrt(1/mx² + 1/my²).

Preparation requires L≤0.45. Consequently d is globally Lipschitz with constant
at most 0.45, F is injective and its inverse exists by the contraction mapping
p↦q−d(p) on the complete plane. The analytic forward Jacobian is triangular:

DF = [[1,0],[ΔW′B,1+ΔWB′]].

Thus 1−L≤det(DF)≤1+L, in particular 0.55≤det(DF)≤1.45. Every x-column is strictly
monotone in y; inversion cannot fold or reverse the source order for either sign.
Inverse determinants lie in [1/1.45,1/0.55]. This is a mathematical sufficient
bound, intentionally conservative, not a sampled-grid guess or visual guarantee.

F is identity at all four support rectangle boundaries and outside that rectangle.
Within a fixed x-column, strict monotonicity and fixed y endpoints imply that
the entire support interval maps onto itself. Therefore the closed source image
domain maps onto itself for both signs when the support is inset. This rules out
edge extrapolation; it does not clip out-of-domain input from other operators.

## Bounded inverse and numeric refusal

The Rust evaluator uses p0=q and p(n+1)=q−d(pn), at most 64 iterations. Stop only
when the source-y step is ≤1e−9 source pixels. With |Δ|≤128 and L≤0.45, the
contraction bound after 64 iterations is far below the explicit acceptance
threshold in ideal arithmetic. Binary floating-point remains checked: every
point must have a forward reconstruction residual ≤1e−7 pixels, inverse
displacement ≤|Δ|+1e−7, a finite certified determinant (1e−12 comparison slack),
and source/destination coordinates inside the exact closed image domain. Failure
refuses the whole band; no clipping, identity fallback, amount attenuation or
previous-success substitution occurs. Exactly zero produces identity.

Native maximums are 1048576 off-grid points per band, source side 1000000 pixels,
|Δ|≤128 source pixels, and source supports inset by at least one pixel. H and
each actual shoulder→hip vertical span must be ≥64 pixels. Each side's horizontal
and depth differences must be ≤0.35 of its vertical span. Shoulder and hip pairs
must each have ≥32-pixel horizontal span, vertical difference ≤0.25 of that span,
and depth difference ≤0.35 of that span. Strongly bent/tilted/foreshortened/tiny
poses refuse rather than being reconstructed. Depth uses the Body33 convention
of normalized z scaled by original source width−1.

The Python bridge only validates/copies buffers, calls the installed Rust ABI,
and exposes conservative facts. No Python warp/solver fallback exists. The state
is an 11-f64 view over immutable bytes. Render proxies must conjugate the same
source-pixel map by actual x/y source-to-render factors, not recompute a different
pose on a crop. Support and maximum displacement are scaled conservatively in
the field layer. ABI details are in `core/torso_length/ABI.md`.

## Mature technique reference and original implementation boundary

Inverse displacement evaluation by fixed-point composition is an established
technique documented by [ITK's InvertDisplacementFieldImageFilter](https://docs.itk.org/projects/doxygen/en/latest/classitk_1_1InvertDisplacementFieldImageFilter.html)
and its [fixed-point inverse displacement module](https://github.com/KitwareMedical/ITKFixedPointInverseDisplacementField).
These primary references inform the choice of inverse-field technique. No ITK
source, library, sampled-field implementation, proprietary algorithm or model was
downloaded, imported or copied. The compact analytic profile, certificate, limits,
ownership rules, implementation and GPL-3.0-or-later source here are original.

## Required, still-UNRUN evidence

- Positive/negative/neutral exact shoulder, hip and whole-head endpoint effects.
- Off-grid inverse residuals and analytic versus finite-difference determinants.
- Monotone columns, continuity at every transition, image-domain preservation.
- Both signs at narrow support, source-edge, depth, tilt and displacement refusals.
- Immutable state, snapshots, ABI/shape/range/alias checks and atomic output refusal.
- Real pose/support/face binding, stale evidence/association, independent multiple
  people, foreign disabled retained evidence, undo/reset/preset/project roundtrip.
- Common body/face/mask sampling, proxy/full-resolution agreement and actual
  photograph review across supported varied subjects/clothing/backgrounds.

Synthetic unit fixtures describe numerical cases only. They are never production
anatomy, model evidence, user review, an image-quality result or a completed gate.
