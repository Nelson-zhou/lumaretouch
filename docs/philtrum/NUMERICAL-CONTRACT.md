# Philtrum length: measured nose-safe gap over a shared inverse primitive

**AUTHORED / UNRUN.** This is a source contract, not a passed import, build,
test, numerical experiment, real-image review, performance result or product
acceptance. The unchanged shared Rust source has been read, not executed here.

## Exact control and portable intent

The sole control is **LNX-REF-PC-32466-C-2605502c27**, 人中. Its operation is
`lnx.philtrum.v1`, with exactly `{"version":1,"amount":0.0}`. Version is an
exact Python integer 1. Amount is an exact Python int/float, finite and in
[-1,1]; booleans, NumPy scalars, strings, extra keys and unknown versions are
refused. Negative shortens, positive lengthens and zero is neutral. Geometry,
landmarks, face/source identity, pixels, paths, masks and caches never enter
portable state. `check`, `active`, `neutral` and `preset` do not load native.

The [official PixCake guide](https://wiki.pixcakeai.com/guide/9405.html), inspected
2026-10-24, describes leftward shortening and rightward lengthening of the
philtrum. This supports the control's scope and direction only. It does not
specify landmarks, margins, gain, support, a numerical kernel, a clinical
measurement or a protected anatomical segmentation. The original .08 gain,
measured planes and compact support below are local policy, not commercial
calibration or proprietary implementation/appearance reproduction.

This is not the mid-face eye-to-nose/cheek interval, lower-face nose-to-chin
length, below-lips chin length, chin width/sharpness, legacy `small_chin`, mouth
shape or broad 收下巴. No existing recipe is reinterpreted or silently reset.

## Source measurement, not anatomy invented by a numerical ABI

All measurement uses the retained actual-source geometry in the same canonical
head frame that the native boundary uses. The upper plane is strictly below the
maximum head-down projection of the complete retained nose set, with the host's
declared measured safety margin. The lower plane is strictly above the minimum
head-down projection of **all outer and inner lip points**, with its declared
margin. H is the positive gap between these two measured planes. Neither plane
is a convenient replacement chosen to satisfy the numerical bounds.

The host must reject absent/incomplete geometry, insufficient resolution,
reversed/overlapping planes, unavailable support or source evidence, and any
ratio outside the shared contract. A single nose-base point 2, upper-lip point
0, or lower-lip point 17 cannot establish protection for the complete sets.
Canonical coordinates, invented faces and clinical proportional templates are
not runtime substitutes for measured source points.

Factual topology comes from pinned [MediaPipe v1.1.1 face-landmarker
source](https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py).
Its nose connections contain 24 distinct vertices:

`168,6,197,195,5,4,1,19,94,2,98,97,326,327,294,278,344,440,275,45,220,115,48,64`.

Its lips include 20 outer and 20 inner vertices. The inner contour is
`78,191,80,81,82,13,312,311,310,415,308,324,318,402,317,14,87,178,88,95`.
These factual identifiers do not establish visible tissue, occlusion status,
clinical philtrum endpoints, semantic segmentation or anatomical ground truth.
"Complete-nose-safe" means safe relative to this complete retained topology
and source evidence, not proof that every real-world nose pixel is segmented.

The origin is on the measured head-axis line through the selected nose-base
proxy at the upper plane. Every claimed lip/lower-face source point must have
head-frame v in [H,D] and lateral coordinate inside the flat core. D is the
measured farthest retained lower-face extent relative to the origin, including
the host's documented measured support padding. The plateau ratio is the
actual floating result `P=D/H`, not a clipped minimum, rounded anatomical
template, or repurposed mid-face ratio. The host checks that finite measured
ratio and passes the same value to the bridge.

All 24 nose points are audited as fixed; all 40 lip points and each retained
source lower-face point whose rigidity is claimed are audited as receiving
the same translation. A source point on the plateau can land above its source
plateau after shortening. Requiring its **destination** to remain in [H,D]
would be wrong: the true inverse must recover the original plateau point.

Source identity, exact FaceRef, retained geometry, current-source RGB/skin/
exclusion evidence, complete support, other-face guards, history, prefix-field
transport and final composition remain host responsibilities. Native capability
does not certify them. Standalone fixed-nose and rigid-plateau properties do
not undo earlier operations or prove those properties under arbitrary composed
fields. The lower feather can transport nearby neck/background content; it
does not claim observed neck segmentation or perfect photographic isolation.

## The shared plateau limit can refuse a valid-looking short gap

The existing ABI permits `1.25 <= P <= 8` and `.25 <= tail <= 4`. Philtrum
requires the exact policy `tail=max(.25,.5*(P-1))`. Thus its derived tail is at
most 3.5, without widening the shared ABI. P and tail remain measured inputs;
the bridge never writes replacements into them.

Since `P=D/H`, the upper cap implies **H >= D/8** in real arithmetic. A short,
otherwise ordinary-looking nose-to-lip gap combined with a long retained
lower-face plateau can exceed the cap. It is then unavailable under this
bounded policy. For example, numerical H=4 and D=40 yield P=10 and must be
refused. This is an illustrative ratio, not a claim about typical anatomy.

The implementation must not move either plane, enlarge H, discard retained
lower-face points, shorten measured support, clamp P to 8, pick a different
tail, or relabel an eye-to-nose operation to make this case pass. Increasing
the cap or designing a different envelope would require a separately reviewed
numerical policy; neither occurs in this slice. A ratio slightly above 8 is
still refused, not admitted through an undocumented epsilon.

## Why the existing Rust implementation is reused unchanged

`core/mid_face/lib.rs` is the project's original GPL-3.0-or-later scalar
head-axis inverse with a rise, flat plateau and tail. Its twelve parameters
contain no landmark indices or mandatory eye/nose meaning. Supplying the
separately admitted philtrum planes reuses an anatomy-agnostic primitive, not
the mid-face operation. `philtrum_native.py` delegates to `mid_face_native.py`
for actual loading, parameter rules, snapshots, evaluation and output checks.

There is no `liblrt_philtrum.so`, independent loader/cache, second inverse,
Python deformation fallback or new build recipe. The existing
`packaging/stage-engine.sh` already stages `bin/liblrt_mid_face.so` and the
shared source/license. That path was inspected, not run for this slice.
Existing modules, kernel sources, tests and packaging stay unchanged.

New code is original GPL-3.0-or-later. No external implementation, model,
weights, asset or canonical mesh is copied or downloaded here. MediaPipe's
referenced source declares Apache-2.0; factual topology does not replace
producer provenance/license obligations or authorize stripping notices from
copied assets. Existing project/model license gates remain applicable.

`available()` uses the actual shipped library's ABI-1 and versioned-symbol
checks. `capability()` exposes `philtrum_available` and `philtrum_reason`, not
anatomical readiness or quality. Errors identify 人中 and, where relevant,
the shared 中庭 Rust core rather than pretending a philtrum library exists.

## Forward definition, rigid plateau and actual interval change

For orthonormal right/down axes and origin o, define u=(p-o)·right,
v=(p-o)·down and t=v/H. Define S(z)=z³(10+z(6z-15)) on [0,1]. The lateral
flat-top window is L(u)=1 for |u|<=inner_x, zero for |u|>=outer_x and
S((outer_x-|u|)/(outer_x-inner_x)) between them, with 0<inner_x<outer_x.

With P=D/H and τ=max(.25,.5*(P-1)), the vertical window is:

- V(t)=0 for t<=0;
- V(t)=S(t) for 0<t<1;
- V(t)=1 for 1<=t<=P;
- V(t)=S((P+τ-t)/τ) for P<t<P+τ;
- V(t)=0 for t>=P+τ.

The original shared forward map is

`u'=u; v'=v+0.08*amount*H*L(u)*V(v/H)`.

The measured upper plane and all admitted nose points on/above it stay fixed.
All admitted lip/lower-face source points in the lateral core and plateau
translate by exactly the same real-arithmetic `Δ=.08*amount*H` along down.
Pairwise vectors within this retained plateau are unchanged. The plane gap
changes from H to `H*(1+.08*amount)`.

The actual nose2-to-lip0 projection is generally **not H**, because H is trimmed
between protective planes. With those source points admitted, that actual
interval changes additively by Δ. It does not generally change by 8% of its
own length. Host acceptance must audit that actual interval and the nose/lip
targets rather than report the plane ratio as a clinical length result.

The rise, plateau and tail meet with zero first/second derivatives. In real
arithmetic the vertical derivative is at least

`1-.08*abs(amount)*1.875/min(1,τ) >= .4`.

Because u'=u, lateral shear does not change this determinant. The standalone
inverse is unique with fixed support edges and displacement magnitude bounded
by `.08*abs(amount)*H`. These are not claims about full-image injectivity under
arbitrary composition, conditioning, realism or speed. An arbitrarily narrow
lateral feather can have arbitrarily large shear.

For a destination q the unchanged Rust kernel solves

`d=k*V(tq-d/H), k=((.08*H)*amount)*L(uq), tq=vq/H`.

The root is bracketed between min(0,k) and max(0,k). Safeguarded Newton/bisection
is bounded by 96 iterations and refuses unresolved results. The returned
inverse displacement is `D(q)=down*d=q-source(q)`. The existing sampler uses
q-D(q), not q+D(q), and no new RGB sampler is introduced. This is an actual
inverse solve, not the negation of a forward field evaluated at q. See
[OpenCV's geometric-transform documentation](https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html)
for the established destination-to-source sampling convention, not as a source
of the project's original deformation algorithm.

## Strict bridge, exact policy and bounded ownership

Inputs must be exact native-endian NumPy float64 arrays: points [N,2],
params [12], N=1..65536. Both shapes/dtypes are rejected before any copying.
The parameter order remains

`[ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,P,tail,amount]`.

Origin, H, widths and points share source-coordinate units; P, tail and amount
are dimensionless. Every input value must be finite. Axes must be unit and
orthogonal within 1e-10; only after that check does the shared code normalize
right and choose its signed perpendicular down. Both handednesses work.
`canonical_frame` exposes exactly that convention to host measurements and
audits; it does not repair skew or infer anatomy.

The bridge creates a private read-only parameter snapshot, calls the shared
parameter validator on it, and compares its tail to the exact floating
expression `max(.25,.5*(float(P)-1.0))`. Even a one-ULP mismatch is refused.
The same snapshot values, including the unchanged P, H and tail, are delegated
to the shared evaluator. That evaluator takes independent bounded snapshots
of both inputs before native use. Callers must not mutate during copying.
No parameter is clipped, silently inferred, coerced or rewritten. The ABI
cannot independently reconstruct D or certify the host's actual ratio.

The unchanged native boundary rejects invalid count/length, null/unaligned
pointers, overflowing spans and output aliasing either input. Read-only inputs
may overlap one another. The caller still guarantees live, correctly sized,
immutable input allocations and exclusive writable output: address checks
cannot prove allocation extent, provenance or lifetime. Contained Rust panics
do not recover invalid foreign memory, process aborts or foreign faults.
Every native failure leaves output untouched. Its private scratch float64
payload is at most 1 MiB for 65536 points.

Statuses remain 0 success; 1 ABI/count/length/pointer/alias; 2 nonfinite/range;
3 frame/H; 4 support/arithmetic/precision/residual; 5 allocation; 6 contained
panic. Python publishes only an owned writable contiguous output after native
success and the inherited finite output/source, exact positive zero on
neutral/upper/outside-support queries, axial direction/amplitude and lateral
preservation checks. These postconditions are not an alternate inverse.
Direct neutral evaluation still requires the installed shared core; portable
neutral does not. Runtime building, inference, network access and fallback
are absent from the bridge.

## Floating-point limitations remain explicit

The shared solve requires scalar residual at most

`max(64*f64_epsilon*max(abs(d),abs(kV)), 8*smallest_subnormal)`.

It also checks the representable source and forward roundtrip against

`max(256*f64_epsilon*max(abs(q components),abs(o components),H,abs(d)),
8*smallest_subnormal)`.

Overflow, unresolved inverse residual, exhausted iteration budget and nonzero
supported motion that underflows to exact zero are refused, not treated as a
successful neutral edit. There is no arbitrary minimum amount. Computing
(.08*H) before multiplying amount can preserve a representable physical
displacement even for a subnormal control amount.

A finite nonzero displacement can still round away on subtraction from q;
the existing float32 joint field and pixel interpolation can lose further
effective movement. Rigid translation and the interval equations are
real-arithmetic properties with explicit f64 checks, not exact machine
arithmetic or visible-pixel promises at every magnitude. Host target/source
audits must reject unresolved requested targets rather than mistake numeric
residual acceptance for anatomical or photographic proof.

## Authored fixtures and unpassed gates

`engine/tests/test_philtrum_native_unrun.py` authors strict portable state;
actual shared loader/ABI capability; exact measured-P/derived-tail preservation;
one-ULP tail refusal; short-gap/plateau rejection without rewriting; snapshot
ownership; shapes/dtypes/count/frame/finite checks; native status propagation;
direction/amplitude postconditions; and neutral/nose-half-plane/support zeros
using fixed-output doubles. Installed-core fixtures cover signed plateau
translation, nose-safe versus eye-to-nose distinction, additive actual interval
change, known-source inverse points, tiny representable displacement and
roll/scale/translation/both-handedness covariance. Missing native means skip,
never an implicit build, download or alternate implementation.

These fixtures have **not been imported or executed**. Existing Rust tests
remain authoritative for the shared primitive; no new Rust solver or tests
are introduced here. Final-source imports, builds, tests, typechecks, measured
source integration, prefix-composition/history/cancellation/preview/export,
real-image review, performance and product acceptance remain unpassed. This
slice does not close the whole facial reshape family or claim a clinical,
3D, semantic-segmentation or identity-preserving workflow.
