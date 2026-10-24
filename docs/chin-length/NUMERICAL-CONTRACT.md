# Chin length: shared inverse primitive, distinct measured operation

**AUTHORED / UNRUN.** This document records a source contract, not a passed test,
build, numerical experiment, performance result, photographic review, UI/runtime
acceptance or equivalence to a commercial implementation.

## Exact requirement and intent

The sole control is **LNX-REF-PC-32466-C-44a42baef4**, 下巴长短. Its portable
operation is `lnx.chin_length.v1`, exactly `{"version":1,"amount":0.0}`. Version
is an exact Python integer 1. Amount is an exact Python int/float, finite and in
[-1,1]; booleans, NumPy scalars, strings, extra keys and unknown versions are
refused. Positive lengthens, negative shortens, and zero is neutral. Geometry,
landmarks, face/source identity, pixels, paths and caches are not portable state.
`check`, `active`, `neutral` and `preset` do not load a native core.

The [official PixCake guide](https://wiki.pixcakeai.com/guide/9405.html), inspected
2026-10-24, describes shortening to the left and lengthening to the right. It
lists 下庭 and 尖下巴 separately, and describes 收下巴 as affecting both jaw and
chin over a larger area. That evidence supports direction and distinct scope;
it does not specify this implementation's anchors, gain, support or solver.
The .08 gain, .5 tail and below-lips measurement are original local policy, not
reverse-engineered commercial calibration or a claim of appearance equivalence.

The new operation is not:

- `lnx.lower_face.v1`: its upper plane is a measured nose-base proxy and its H is
  nose2-to-chin152, so admitted lips may move.
- `lnx.chin_shape.v1`: its independent signed sides change horizontal chin width,
  preserving the measured tip/vertical coordinate within explicit tolerance.
- Legacy `lnx.deform.v1/small_chin`: its older sparse-control recipe is neither
  migrated nor silently reinterpreted. Active chin length requires its amount to
  be neutral; `check_coexistence` uses the legacy `D.check_amounts` unchanged.
  Neutral chin length returns before importing or validating that dependency.
- 收下巴 or another broad jaw retraction operation. No broader jaw control is
  claimed by changing a label or applying the whole lower-third operation.

## Measured host contract, not anatomy supplied by the kernel

The host measures the origin strictly below **all** outer and inner lip vertices
in the canonical head-down direction. The head-down centerline has actual
retained chin proxy 152's lateral coordinate; H is its positive distance from the
below-lips plane. The actual point, not an invented center or average of nearby
vertices, must be in the full lateral core and at t=1 within declared measurement
roundoff. A finite arbitrary parameter array is not proof of these facts.

Factual connections come from the pinned [MediaPipe v1.1.1 face-landmarker
source](https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py):
its lip connections include both contours, and its oval contains
150→149→176→148→152→377→400→378→379 when traversed in the chosen direction.
These indices identify model topology, not clinically measured landmarks,
visibility, occlusion status or an anatomical ground truth. Taking the maximum
projection over all retained lip vertices is a local protective policy; using
only lower-lip center 17 would not establish protection for the other vertices.

Source identity, exact FaceRef, all 478 retained targets, current-source
skin/exclusion/RGB evidence, complete below-chin/lateral support, other-face
guards, coexistence and final composition belong to the separate chin-length
runtime host. The bridge cannot certify them. Lips and the upper half-plane are
fixed by this new map at their admitted source positions. This does not undo
earlier edits or promise that arbitrary previously relocated positions never
enter its support. The below-chin feather can transport neighboring neck or
background; it is not an observed neck segmentation or perfect isolation.

## Why the existing Rust ABI is reused

`core/lower_face/lib.rs` already implements an original, anatomy-agnostic scalar
head-axis inverse map. Its 11 scalar parameters contain no landmark indices or
nose-specific assumption. Replacing its measured origin and H with the admitted
chin interval is therefore reuse of a numerical primitive, not reuse of the
lower-face operation. `chin_length_native.py` delegates to the existing
`lower_face_native.py` ABI loader, evaluator, snapshots and postconditions.

There is no new `liblrt_chin_length.so`, no duplicate solver and no new native
build recipe. Existing `packaging/stage-engine.sh` stages
`bin/liblrt_lower_face.so`, its source and GPL license. That packaging path has
only been inspected, not executed for this slice. Reusing it does not change the
original shared kernel's GPL-3.0-or-later license or any producer license gates.
No external implementation, models, weights or assets are incorporated here.
The upstream MediaPipe source declares Apache-2.0; this slice references factual
topology rather than copying its implementation.

`available()` delegates to actual library loading plus the ABI-1 and versioned-
symbol checks. `capability()` reports only `chin_length_available` and
`chin_length_reason`, never source/anatomy readiness or acceptance. Loader and
numeric failures identify 下巴长短 and, when applicable, the shared 下庭 Rust
core, rather than falsely probing for a nonexistent chin-specific library.

## Forward definition and inverse sampling

For orthonormal axes right/down and origin o, let u=(p−o)·right, v=(p−o)·down,
t=v/H, with H>0. Let S(z)=z³(10+z(6z−15)) on [0,1]. The lateral weight is

- L(u)=1 for |u|≤inner_x;
- L(u)=S((outer_x−|u|)/(outer_x−inner_x)) between the widths;
- L(u)=0 for |u|≥outer_x, with 0<inner_x<outer_x.

For the fixed tail τ=.5, V(t)=0 for t≤0 or t≥1+τ, V(t)=S(t) for 0<t≤1, and
V(t)=S((1+τ−t)/τ) for 1<t<1+τ. The forward map is

`u′=u; v′=v+0.08×amount×H×L(u)×V(v/H)`.

At an admitted chin152 in the lateral core and t=1, the forward interval becomes
H×(1+.08×amount). This is a nonuniform compact axial warp, not uniform vertical
resizing. The rise and tail meet with zero first/second derivatives. In real
arithmetic, the vertical derivative is bounded by

`1−.08×abs(amount)×1.875/min(1,.5) ≥ .7`.

Lateral shear does not change this determinant because u′=u. The inverse is
unique with the same fixed support edges, and |D|≤.08×abs(amount)×H. These are
standalone real-arithmetic statements, not bounds for arbitrarily composed maps,
full-image injectivity, conditioning, photographic plausibility or runtime speed.
Arbitrarily narrow lateral feathers can have arbitrarily large shear.

For destination q the shared kernel solves

`d=k×V(tq−d/H), k=((.08×H)×amount)×L(uq), tq=vq/H`.

It brackets d between min(0,k) and max(0,k), uses safeguarded Newton/bisection for
at most 96 iterations per point, and refuses failure. It returns
`D(q)=down×d=q−source(q)` in the algebraic contract. The common sampler uses
q−D(q), not q+D(q). It is a checked inverse, not the negative of the forward
field evaluated at q. [OpenCV's geometric-transform documentation](https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html)
provides the established destination-to-source sampling convention; it is not
the source of this original scalar deformation or a new sampler dependency.

## Strict bridge, ownership and ABI bounds

Points and parameters must be exact native-endian NumPy float64 arrays with
shapes [N,2] and [11], N=1..65536. Both shape/dtype checks precede any copying.
The exact parameter order remains

`[ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,tail,amount]`.

Origins, H, widths and queries share source-coordinate units; tail/amount are
dimensionless. All input values must be finite. Unlike the wider shared ABI
range [.25,1], this chin bridge accepts tail **exactly .5**, including for direct
neutral calls. It never overwrites an invalid tail with .5, rescales H, inserts
missing parameters, coerces dtype or clamps strength. The chin-specific check
runs on an owned read-only parameter snapshot and delegates those same values,
preventing later caller mutation from changing the validated tail. The shared
boundary then snapshots both inputs independently before its ABI call. Callers
must not mutate any input during copying.

Axes must be finite unit/orthogonal within 1e-10. Only after that validation does
the shared implementation normalize right and choose its signed perpendicular
for down. Both handednesses work. `canonical_frame` exposes the same operation
for host measurement/support/targets; it does not repair skew or infer anatomy.

The unchanged ABI rejects invalid lengths/counts, null/unaligned pointers,
overflowing spans and output aliasing either input. Input allocations may overlap
one another. The caller still guarantees live, correctly sized, immutable input
allocations and exclusive writable output; address checks cannot prove those
properties. Catching Rust panics cannot recover invalid foreign memory, process
aborts or foreign faults. Every native error leaves caller output untouched;
the private scratch f64 payload is at most 1 MiB for 65536 points.

Status codes remain 0 success; 1 ABI/count/length/pointer/alias; 2 nonfinite/range;
3 frame/H; 4 support/arithmetic/precision/residual; 5 allocation; 6 contained
panic. Python publishes only an owned writable contiguous result after native
success, finite output/source, exact positive zero on neutral/outside-support
queries, axial direction/amplitude and lateral-preservation postconditions.
These checks are not another inverse solver or a deformation fallback. A direct
neutral evaluation still requires the actual shared core; portable neutral does
not load it. Runtime compilation, inference, networking and fallback are absent.

## Explicit floating-point limits

The shared scalar solve requires residual at most

`max(64×f64_epsilon×max(abs(d),abs(kV)), 8×smallest_subnormal)`.

It also verifies the representable source and its forward roundtrip against

`max(256×f64_epsilon×max(abs(q components),abs(o components),H,abs(d)),
8×smallest_subnormal)`.

The shared ABI's general derivative floor is .4 for its full permitted tail
range; the stricter chin policy gives .7 in real arithmetic without modifying
that kernel. Nonzero supported motion that underflows to exact zero, an
unrepresentable solve, overflow or exhausted iteration budget is refused rather
than silently neutralized. There is no arbitrary minimum control magnitude.
Computing (.08×H) before multiplying amount can retain a representable physical
shift even for a subnormal amount.

A finite nonzero returned displacement can still round away when subtracted
from q, and the existing float32 joint map or pixel interpolation can lose more
effective movement. Lateral preservation, exact source roundtrip and the chin
length formula are real-arithmetic properties with explicit f64 checks, not a
claim of exact floating arithmetic. Nonzero amount never promises visibly changed
pixels at every magnitude. Host target/source audits must refuse unresolved
requested targets rather than treating numerical residual acceptance as visual
or anatomical proof. No performance or photographic threshold is inferred from
these numerical limits.

## Authored verification and unpassed gates

`engine/tests/test_chin_length_native_unrun.py` authors strict state and
coexistence cases; fixed-tail/no-rewrite checks; actual shared-capability behavior;
shape/dtype/batch/frame/finite refusal; independent ownership; native statuses;
output postconditions; and neutral/edge guarantees through fixed-output doubles.
Planned installed-core cases cover signed actual-chin targets, a below-lips
interval distinct from nose-to-chin, native equivalence on identical parameters,
and tiny representable physical shifts. They skip absent native without building
or downloading anything. They have **not been imported or executed**.

The existing Rust source/ABI tests remain authoritative for the shared numerical
primitive; no new Rust test or duplicate kernel is introduced. Source-only review
is not execution. Final-source builds/tests/typechecks, measured-source integration,
combined-field/history/cancellation/preview/export, real-image review, performance
and product acceptance remain unpassed. This slice does not close the broader
facial family, 收下巴, a 3D/identity-preserving workflow or all creative controls.
