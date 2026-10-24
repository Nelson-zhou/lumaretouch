# 下巴长短: explicit versioned replacement, not legacy reinterpretation

Status: source authored; numerical, photographic, UI, workflow and performance
acceptance **UNRUN**. This closes a bounded source-wiring slice for one exact
handbook leaf, not the complete reshaping family or an accepted photo-quality gate.

## Exact requirement and primary semantics

`LNX-REF-PC-32466-C-44a42baef4`, `PC-32466 / 脸型/下巴长短` is a separate
P1 research item in the frozen AI development mapping, with no dedicated
acceptance cases. Related `PORTRAIT-007` does not establish this control's success.
The frozen manual separately lists chin length, pointedness and retraction.

The official guide <https://wiki.pixcakeai.com/guide/9405.html> specifies negative
shortening and positive lengthening for 下巴长短. It describes 收下巴 separately
as affecting a larger jaw-and-chin region. Neither statement specifies the exact
numeric gain, support or algorithm. Frozen source URL
<https://www.pixcakeai.com/guide/32466> remains recorded without assuming a
redirect or content identity.

Factual connectivity comes from the pinned MediaPipe v1.1.1 primary source:
<https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py>.
The complete lower oval includes
`150–149–176–148–152–377–400–378–379`. Both inner and outer lip boundaries
matter; the new plane must lie below all 40 measured lip vertices. These are
actual retained observations, not clinical chin/hairline/ear or 3-D measurements.

Inverse mapping is distinct from interpolation, as in the mature primary
transform model documented at
<https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html>.
No upstream code, models, weights or assets are downloaded or copied. New code
and the reused original Rust primitive are GPL-3.0-or-later. Existing MediaPipe
producer/license records remain unchanged.

## Why this is not a renamed old effect

Legacy `lnx.deform.v1 /small_chin` displaces 152, 54 and 314 and uses 67/338 as
alleged below-chin support pins. Pinned topology shows the latter points do not
have the claimed bilateral jaw/below-chin roles: upper oval and lip points are
involved. Its existing code, saved numbers, presets and appearance remain intact.
This change does not silently correct old projects or reinterpret their signs.

New `lnx.chin_length.v1` measures the actual gap from a plane below every lip
vertex to tip proxy152. It moves only along the measured head-down axis with a
compact feather. The lip plane and upper half-plane stay fixed for this operator;
head-axis width is unchanged within the explicit numerical checks. This differs
from lowerface's nose2-to-chin interval, midface's eye-to-nose band and lowerface
translation, whole-face scaling, and chin-shape's horizontal bilateral taper.
It does not reconstruct hidden anatomy or claim precise clinical proportions.

## Safe opt-in and history

Persistent state is exactly `{version: 1, amount: finite [-1,1]}`. Positive
lengthens, negative shortens, zero is neutral. No source identity, landmarks,
support geometry, pixels or masks are embedded in portable intent.

Active new chin length and effective nonzero legacy small_chin are mutually
exclusive. The complete resolved canonical recipe is checked before preparation,
not one scalar at a time. The wrapper repeats the check defensively. Existing
legacy intent is never automatically erased, negated, rescaled or copied.

The user may explicitly choose a new amount and request replacement in one
canonical transaction: set the old small_chin leaf to zero in the chosen scope
and set the new amount to the separately entered value. The normal owner handles
revisions, pending/uncertain receipts, publication and undo. Reverting that
transaction restores its old intent through existing history, not a new migration
owner. Shared/inherited values remain visible as such; a local zero override does
not rewrite another scope's stored recipe. Conflicting effective overrides can
still refuse the transaction.

Resetting the new control only resets its new amount and leaves legacy intent
untouched. Neutral new state requires no anatomy/native core and does not block
old rendering. A preset carrying active new intent into a target with active old
small_chin refuses visibly; scalar installation is not permission to replace it.

## Real shared Rust primitive, new actual anatomy

No new Rust library is necessary. The existing original `core/lower_face` inverse
is anatomy-agnostic: it accepts an origin, canonical orthonormal axes, H, lateral
core/outer widths, tail ratio and signed amount. The new thin bridge fixes the
tail to .5 and delegates strict shape, finite, bounds, ABI, atomicity and residual
checks to the unchanged implementation. It exposes its actual installed core
availability, without downloading, compiling or pretending a different core is
present. Existing packaging already stages the Rust library and its original
source/license; this task does not duplicate it.

The original numerical formula is a compact vertical rise/fall map with gain .08:
head-axis u stays fixed; v gains `.08 * H * amount * L(u) * V(v/H)`. V rises
quintically from zero at the below-lip plane to one at the measured tip level,
then falls to zero over .5H. L fades laterally outside its measured core.
The shared Rust primitive solves its actual monotone inverse, not a negated
forward displacement. Python's forward expression audits retained measured
targets only and never replaces the inverse or image sampler.

The source measurements, evidence, target audit, control intent, conflict policy
and canonical wrapper are new. They do not call the lowerface operation's build
or reuse its nose-based support. Shared mathematical code does not imply shared
anatomical semantics or a new independently invented solver.

The .08 gain, margins and admission thresholds are original bounded policy, not
commercial calibration. See NUMERICAL-CONTRACT.md for exact reuse and precision
limits. Extremely small deltas can vanish in f64 subtraction or the existing
float32 map; bounded failure may refuse underflow/stagnation. Neither successful
source inspection nor library readiness is numerical or photographic acceptance.

## Canonical source, export and target-owned transfer

The new runtime requires effective immutable original/derived source pixels,
exact FaceRef and retained478 digest, verified measured frame/oval, actual
below-lip/tip ordering and source-owned skin/RGB/exclusion evidence. It checks the
actual lower arc and affected interior rather than treating an upper-oval or lip
index as a jaw landmark. Unknown visibility, clipped influence and protected
foreign-face interference refuse, not silently attenuate or fabricate support.

The new wrapper follows chin shape and preserves all earlier geometry fields and
the original mouth slot3. Output, intermediate and final source footprints remain
guarded. The same canonical joint-map owner and sampler serve original/derived
preview, inspection and export; no new bitmap, analysis identity or history owner
is introduced. PNG16/float source handling remains on the existing path.

Presets transfer only version and amount. Explicit reviewed target associations
must rebuild each target's own evidence and complete candidate. Generic derived
preset transport remains guarded; no donor mask, source, landmarks or fitted
support is copied. A whole-candidate failure retains the old graph and output.

## Remaining limits

- This is measured 2-D existing-texture transport, not AI reconstruction, clinical
  anatomy, a full visibility mask, 3-D proportions or proprietary equivalence.
- The lateral/below-chin feather can transport neighboring neck/background.
  Prior effects can relocate pixels into the support; source lip pinning is not
  global invariance after arbitrary earlier geometry.
- Conservative measured/frame/source guards can refuse difficult, occluded,
  clipped or neighboring faces. No missing anatomy is filled by canonical meshes.
- Old legacy topology remains intentionally unchanged. Replacement is explicit
  and target-owned; the larger 收下巴 requirement is not silently declared fixed.
- Read/materialization remains available for conflict disclosure and neutral
  recovery. Compatibility admission checks enabled faces on the actual current
  source, not unchanged disabled/other-source intent. All rendered faces remain
  subject to the strict check. An externally restored invalid graph containing
  multiple simultaneously conflicting enabled faces on one source still needs
  an explicit multi-face recovery facility; individual transactions cannot
  publish a partially compatible render. That facility is not supplied here.
- Broader alpha/HDR pipeline limits remain; no flattening or clipping workaround.
- All authored fixtures and UI/history/export/preset/quality acceptance remain
  UNRUN. Static parsing and source hashes do not establish working behavior.
