# 尖下巴: source-owned bilateral lower-chin taper

Status: **source authored; every numerical, photographic, UI, performance and
end-to-end acceptance gate is UNRUN**. This is one bounded interpretation of one
handbook control, not completion of the facial-reshaping family.

## Requirement and primary research

Exact requirement: `LNX-REF-PC-32466-C-ed7837df9a`, `PC-32466 / 脸型/尖下巴`.
The frozen AI development mapping lists it as P1 research, without dedicated
acceptance cases. Related `PORTRAIT-007` is not evidence that this control passed.
The frozen manual's facial-reshaping section separately lists chin length,
pointedness and retraction. The original portrait audit groups this with several
other proportions; implementing this leaf does not close that whole group.

Primary official semantics checked at
<https://wiki.pixcakeai.com/guide/9405.html>: negative moves toward rounder,
positive toward sharper, with independently unlocked left/right adjustment.
The guide separately describes chin length and the larger jaw-and-chin retraction
region. It does **not** prescribe the algorithm, gain, exact support, tip pinning,
curvature metric or image-quality tolerance below. The frozen mapping URL remains
<https://www.pixcakeai.com/guide/32466>; no redirect or content identity is assumed.

Topology is factual connectivity from pinned MediaPipe v1.1.1:
<https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py>.
The contiguous lower oval is
`150–149–176–148–152–377–400–378–379`. Intermediate vertices 176 and 400
must not be skipped when checking real boundary segments. These are retained
image observations, not clinical anatomy labels. No canonical mesh positions,
invented hairline, ears or 3-D measurements enter the algorithm.

Inverse mapping and resampling are distinct responsibilities, consistent with
the mature image-transform model documented by OpenCV:
<https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html>.
This implementation is original GPL-3.0-or-later code. No upstream code, image,
model or weights are copied or downloaded. Existing measured-landmark producer
and license records remain unchanged; MediaPipe source is Apache-2.0.

## Deliberately distinct operation

`lnx.chin_shape.v1` horizontally tapers the admitted below-lip lower profile.
Positive narrows lateral distances from the measured tip axis; negative widens.
This operator preserves head-axis height and the measured tip position within
the stated floating-point checks. It does **not** guarantee a curvature metric
or that a particular photograph perceptually appears sharper or rounder.

Legacy `small_chin` moves points vertically and remains unchanged, including its
historical topology defect: `ops/deform.py` selects 152, 54 and 314 as moving
points, with 67/338 as alleged lower support pins. Pinned topology does not place
these at the claimed bilateral jaw/below-chin positions. Existing projects retain
their exact old recipe and code; there is no silent migration or correction.
The new control is not an alias for this legacy operation, chin length, lowerface,
midface, whole-face size, generic liquify or AI reconstruction.

## State and original numerical policy

The only persistent intent is
`{version: 1, linked: boolean, left: number, right: number}`.
Both amounts are finite in `[-1,1]`; linked requires equal values. Linking unequal
amounts does not silently pick one or average them. The UI requires a deliberate
common value and commits all relevant leaves atomically. Neutral is linked with
both amounts zero. State contains no identity, mask, pixels, landmarks or cache.

Native parameters are eleven f64 values:
`[ox, oy, right_x, right_y, down_x, down_y, H, inner, outer, left, right]`.
The frame is checked/canonicalized; `outer == 2 * inner`, both positive and
finite. H is the actual measured below-lip-plane to point-152 interval.
The influence tail is fixed at one half of H.

For local coordinates u, v and t=v/H, the forward map is:

    u' = u * (1 - 0.08 * amount(side(u)) * V(t) * L(abs(u)))
    v' = v

`S(t)=t^3(10-15t+6t^2)` on [0,1]. V rises as S(t) from t=0 to1,
then falls as S((1.5-t)/.5) until t=1.5, zero outside. L is one inside
inner, falls as S((outer-r)/(outer-inner)) to outer, zero outside. u>0 is
the subject-left coefficient, u<0 subject-right; zero is fixed. S uses stable
symmetric evaluation near its endpoints. The 0.08 gain and all admission
thresholds are original bounded policy, not commercial calibration.

For B=L+rL', the conservative bound is `-3.75 <= B <= 1` because outer=2inner
and max S'=1.875. Therefore the horizontal derivative is within [0.7,1.3]
on either open side for all allowed amounts: each horizontal slice is strictly
monotone. Unequal amounts produce different one-sided derivatives at u=0.
The map is continuous and horizontally bi-Lipschitz, **not globally C1**.
This proof is not a bound on total 2-D shear or arbitrary composed-map conditioning.

Rust solves the actual inverse with a bounded safeguarded scalar solver and
checks residual/source roundtrip before publishing displacement q-source(q).
It does not negate the forward displacement. Python's forward expression is
used only to audit measured targets, never as an inverse fallback. Neutral and
outside influence are zero; finite arithmetic and extremely small values have
explicit refusal/roundoff limits. A subnormal absolute tolerance is not universal
relative accuracy. Small f64 shifts can vanish in subtraction or in the existing
float32 coordinate map. No numerical acceptance has been run.

The bounded C ABI accepts at most 65,536 points, validates spans and shapes,
computes in private scratch and publishes atomically. There is no RGB sampler,
runtime build, package installation, model inference or Python deformation
fallback in this core. Native readiness means library/ABI availability only,
not anatomical suitability, source admission or photo quality.

## Actual source ownership and integration

Admission uses the effective immutable original/derived source, exact canonical
FaceRef and retained 478-point digest, source-owned face-skin evidence and known
occluder exclusion. The upper plane must be strictly below all protected outer
and inner lip vertices, not merely point17. The tip, ordered bilateral lower
arc, interval and lateral extent must be measurable in this actual image.
Connected boundary strips and interior skin/RGB checks are operation-specific;
landmarks alone are not proof of visibility. Full compact influence, including
its interpolation margin, must fit the source and avoid every retained foreign
face, even disabled or unresolved neighbors. Unsupported requests refuse rather
than clipping support, reducing gain or borrowing another person's evidence.

The canonical renderer appends this pullback after existing contour/slim,
whole-face size, lowerface and midface. It retains the original first four
geometry slots and mouth slot3, composes the prefix at the newly mapped point,
and checks output/intermediate/final source footprints. One existing common
joint-map owner and image sampler serve preview, inspection and export. No
temporary bitmap is promoted to a genuine source and no source history is lost.

The UI routes the exact handbook leaf to its separate bilateral control, keeps
effective-source/selection/owner/revision and pending/uncertain fences, and does
not infer values for blank shared scopes. Neutral recovery retains ownership
checks but does not require anatomy or a native core. Project state, history and
undo use the existing canonical operation owner.
An unlinked zero/zero recipe is neutral for this geometry, but the unchanged
export passthrough guard conservatively treats it as noncanonical intent and
enters checked preparation. Only the exact canonical neutral recipe is asserted
eligible for that existing fast path; no export-owner rule is weakened here.

Presets carry only intent. Explicit reviewed target associations recalculate
support and complete rendering from each target's own source and anatomy.
Generic derived-image preset transport remains guarded; parameter transfer does
not copy landmarks, masks, pixels, source proof or fitted support. Full candidate
failure rolls back rather than publishing a partially applied effect.

## Residual limits and acceptance

- This is 2-D transport of existing texture, not generative reconstruction,
  semantic chin segmentation, clinical measurement or 3-D reshaping.
- Only admitted frontal/mild-yaw measured faces are supported; missing, clipped,
  occluded or insufficient source evidence can refuse the operation.
- A one-sided request requires photometric support only on its moving side, but
  still needs a genuine bilateral measured frame/ordered arc. The conservative
  complete influence rectangle includes the neutral side and can refuse nearby
  faces or image edges there; it is not a tighter active-half-plane admission.
- The finite support feather can transport adjacent neck/background texture.
  It does not isolate a perfect foreground boundary.
- Previous operations can relocate lip/other pixels into this operator's support.
  Source-landmark pinning is not a guarantee of global feature invariance after
  arbitrary prior edits. Full combined-map safeguards remain in force.
- Independent amounts may create a centerline derivative cusp. No automatic
  smoothing, averaging or invisible side coupling conceals that limitation.
- Alpha/HDR limitations of the broader retouch pipeline remain unchanged.
  No clipping, flattening or source identity substitution is introduced.
- Chin length, forehead/hairline, AI facial smoothing, 3-D proportions and other
  handbook leaves remain separate; this control does not count as those features.
- All fixtures are authored and UNRUN. Source/AST/hash inspection is not passing
  tests, working UI, numerical accuracy, measured speed or photographic acceptance.
