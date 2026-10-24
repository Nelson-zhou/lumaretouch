# 人中: measured visual nose-to-mouth gap

Status: source authored; all numerical, photographic, UI, workflow and performance
acceptance **UNRUN**. One exact handbook leaf is connected by a bounded original
interpretation. This is not clinical philtrum measurement, isolated segmentation
or completion of the facial-proportions family.

## Exact requirement and primary evidence

`LNX-REF-PC-32466-C-2605502c27`, `PC-32466 / 脸型/人中` is a P1 research item
in the frozen AI development mapping, with no dedicated acceptance cases.
Related `PORTRAIT-007` is not evidence of acceptance. The original portrait audit
groups it with several other proportion controls; implementing this leaf does
not close that entire group. Frozen refine metadata does not specify a numeric
range, gain, defaults or bilateral unlock for this control.

The official guide <https://wiki.pixcakeai.com/guide/9405.html> specifies negative
shortening and positive lengthening, separately from mouth up/down, midface,
lowerface and chin length. It does not specify a solver, landmarks, segmentation,
support or gain. Frozen URL <https://www.pixcakeai.com/guide/32466> is retained
without asserting a redirect or content identity.

Pinned MediaPipe v1.1.1 factual connection source:
<https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py>.
The complete nose-connection vertex union is:

    168,6,197,195,5,4,1,19,94,2,98,97,326,327,
    294,278,344,440,275,45,220,115,48,64

The existing `face_contour_geometry.G.NOSE` is a smaller subset. It remains
unchanged for saved operations and cannot substantiate a complete nose-connection
claim. The new operation uses all 24 vertices and all 40 outer/inner lip vertices.
Factual connectivity is not a clinical label or proof of visibility. No canonical
mesh coordinates, invented philtrum point, hairline, ear or 3-D measurement is used.

The same upstream tessellation connects actual retained point164 with nose/lip
neighbors. That is factual adjacency, not authorization to replace missing
coordinates or to call a point a clinical philtrum landmark.

The mature primary reverse-mapping/interpolation model is documented at
<https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html>.
New code and the reused original Rust primitive are GPL-3.0-or-later. No upstream
code, image, model or weights are copied or downloaded. Existing MediaPipe
producer and license records remain unchanged.

## Distinct from existing controls

- Mouth vertical changes lip-ring controls by a mouth-width-scaled displacement
  and uses TPS with distant upper anchors. It does not guarantee a fixed chin or
  a common lower-face plateau. This control does not rename or reuse that recipe.
- Lowerface changes a nose2-to-chin interval nonuniformly, including lips.
- Midface changes its above-nose band, including measured nose geometry, before
  translating lower points.
- Chin length fixes all lips and changes the below-lip-to-tip interval.
- Chin shape changes the bilateral horizontal lower profile.

New `lnx.philtrum.v1` measures the remaining gap between protected nose and lip
planes, changes that band, and translates lips/lowerface together. Existing
recipes, source geometry, parameter meanings and history are not reset, negated,
converted or migrated. Existing chin-length/legacy compatibility stays intact.

## Actual measured planes and support

In the canonical measured head frame, the fixed upper plane lies below the
maximum downward projection of **all24** nose vertices plus a measured margin.
Plateau onset lies above the minimum projection of **all40** lips minus margin.
Their positive, resolved separation is H. The lateral axis uses actual nose2,
not a fabricated center. The lower plateau includes every retained source point
at/below onset, explicitly all lips and chin152, through its maximum measured
extent plus padding. The lateral flat core encloses every claimed plateau point.

The operation audits all478 actual source targets, the complete measured nose
set and upper half-plane, all lips and retained lower-face common translation,
relative lip/chin geometry and signed actual nose2-to-lip0 change. Statements
apply to admitted source positions under this map, not arbitrary points moved
by earlier operations. Nose-connection preservation is not complete semantic
segmentation or proof that every anatomical nose pixel lies inside that set.

The full-width rising band also changes cheek tissue at the same height. It is
not isolated philtrum editing. The plateau and below-chin feather can transport
neck/background texture. Complete source-frame and retained foreign-face bounds
must admit the influence; it is not clipped or silently attenuated to fit.

Admission requires exact effective immutable original/derived source and FaceRef,
retained478 digest, source-owned skin/RGB and known-exclusion evidence. A genuine
central gap corridor is separately observed, with support on both vertical halves;
broad cheek or lip evidence cannot stand in for it. Resolution/count thresholds
are derived from that small measured gap/corridor, not blindly copied broad cheek
area thresholds. Moved side-band/lower-face and actual lip evidence are separately
required. Missing or occluded evidence refuses rather than synthesizing anatomy.

## Shared original Rust inverse, not another solver

Persistent intent is exactly `{version:1, amount:finite [-1,1]}`. No pixels,
source identity, analysis, landmarks, masks or fitted support travel in state.

The unchanged `core/mid_face` primitive accepts twelve f64 parameters:

    [ox,oy,right_x,right_y,down_x,down_y,H,inner,outer,P,tail,amount]

It is anatomy-agnostic. The new thin bridge retains strict ABI/snapshot/shape,
finite, source-roundtrip and atomic-output checks, preserving the measured P and
requiring `tail=max(.25,.5*(P-1))` exactly. It does not call midface's eye-to-nose
measurement/build or infer new geometry. Existing packaging already ships the
original Rust library with its source/license; no new binary, solver or sampler
is claimed and there is no runtime build/download/fallback.

The original forward policy keeps head-axis u fixed and adds
`.08*H*amount*L(u)*V(v/H)` to v. V rises quintically over the measured gap, is
one over the lower plateau, and falls to zero over the measured tail. Rust solves
the actual inverse, not a negated forward displacement. Python's forward formula
is for retained-target audits only. One existing common sampler remains the only
image interpolation owner.

H is a **margin-trimmed plane gap**, not point2-to-lip0 or clinical philtrum length.
Only that constructed plane gap scales as `H*(1+.08*amount)`. The actual fixed
nose-to-plateau-lip interval changes by additive `delta=.08*amount*H`, not generally
8% of its original value. The gain, margins and support are original local policy,
not commercial calibration. See NUMERICAL-CONTRACT.md for the exact bridge limits.

### Important inherited proportional limit

The shared ABI retains `1.25<=P<=8` and `.25<=tail<=4`. If D is the padded lower
plateau distance from the upper plane, `P=D/H<=8` requires `H>=D/8`. A genuinely
short measured gap can fail this constraint despite otherwise valid anatomy.
The chosen tail is at most3.5 for admitted P, so the plateau cap is the tighter
restriction. Refusal prevalence is **UNMEASURED**.

No implementation may inflate H, drop nose vertices, move onset into the lips,
truncate lower points or reduce strength to evade this bound. Such faces remain
unsupported in this slice. Extending the primitive safely is separate work;
this reuse is not full official-feature acceptance.

## Canonical integration and transfer

The new wrapper follows chin length, preserving all prior fields, the initial
four geometry slots and mouth slot3. It checks output, intermediate and genuine
source footprints around the prefix pullback. The existing canonical render,
history, undo, inspection and export owner serves original/derived images.
No parallel history or output bitmap source identity is created.

The exact handbook UI route uses its own signed control and actual shared-core
capability. Source/selection/owner/revision and pending/uncertain fences remain.
Shared scopes use explicit values or a blank deliberate input, not a selected
face's inherited number. Neutral recovery keeps ownership but needs no anatomy
or native core. A library-ready flag is not proof that the actual gap is supported.

Presets carry only scalar intent. Explicit reviewed target-person associations
recalculate actual geometry and full candidate rendering from each target's own
immutable source. Generic derived presets remain guarded. No donor landmarks,
masks, analysis or support geometry is copied. Candidate refusal rolls back
rather than publishing a partial effect.

## Remaining limits

- 2-D existing-texture transport only, not AI, clinical anatomy, full visibility,
  isolated segmentation, 3-D proportions or proprietary equivalence.
- The P bound and conservative independent source evidence can refuse otherwise
  valid-looking faces; no empirical availability or photo-quality rate is known.
- Surrounding cheeks, lower face and neck/background participate; prior geometry
  can enter this map's transitions. Source invariants are not global invariants
  of arbitrary compositions.
- The inherited bounded inverse can refuse underflow/stagnation. Tiny accepted
  f64 deltas can disappear in subtraction or downstream float32 coordinates.
  Source/hash inspection is not numerical, interpolation or performance proof.
- Existing malformed multi-enabled chin-conflict recovery limitations are not
  widened or fixed here. Prior valid history and neutral paths remain unchanged.
- Broader alpha/HDR and other handbook leaves stay unfinished, with no clipping
  or flattening workaround. Every fixture and real workflow/quality gate is UNRUN.
