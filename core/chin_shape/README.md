# Bilateral horizontal chin taper, private ABI 1

Original dependency-free GPL-3.0-or-later Rust implementation, using this
project's existing checked numerical-boundary conventions in a new component.
Sources, fixtures and packaging are **AUTHORED / UNRUN**. No compilation,
imports, tests, numerical execution, inference, downloads, performance checks,
image review or product acceptance are claimed. No upstream deformation code,
commercial implementation, model weights or assets were copied.

## Scope and portable intent

Exact requirement: `LNX-REF-PC-32466-C-ed7837df9a`, 尖下巴. Operation
`lnx.chin_shape.v1` has exactly this neutral state:

`{"version":1,"linked":true,"left":0.0,"right":0.0}`.

Version is exactly integer 1; linked is exactly boolean; left/right are finite
Python int/float values in [-1,1], excluding booleans and coercible numeric
types. Linked state requires equal amounts. An unlinked recipe allows independent
amounts, including opposite signs. Relinking unequal values refuses, rather than
averaging, choosing a side, or hiding a value. `adjust` propagates an explicit
adjustment only when already linked. Unknown keys and versions are refused.
Portable state contains no identity, geometry, landmarks, pixels, paths or caches.

The official semantic reference supplied by the parent task is
https://wiki.pixcakeai.com/guide/9405.html: the control's leftward slider direction
is rounder and rightward direction sharper, with independent left/right handling.
Those slider directions are distinct from anatomical left/right. Positive local
amount contracts horizontal chin width; negative expands it. The reference is
not evidence for this gain, landmarks, envelope, boundaries, solver or quality.
These are original local policies, not a reconstruction of proprietary code.

This is not `small_chin`, chin shortening, lower-face length, whole-face scaling,
face-contour slimming, identity pinning or tip translation. The host must measure
a plane strictly below every lip vertex, a head-oriented frame, chin152 lateral
center, H from that plane to chin152, and sufficient full-side support. The kernel
does not infer anatomy. The host also owns current-source authorization/evidence,
support conflicts, compositing, sampling and final combined-field acceptance.

## Forward map and original bounds

Let o be the measured origin on the below-lips plane, right/down be an orthonormal
frame, u=(p-o)·right, v=(p-o)·down and t=v/H. H>0. Origin is chosen on chin152's
head-axis line, so the mathematical tip has u=0 and t=1. Define r=|u|,
`a(u)=left` for u>0 and `right` for u<0. Anatomical orientation belongs to the
host, not screen x or the library. At u=0 the displacement is zero regardless
of either amount. There is no positive-width dead zone, snap or side blending.

Require inner>0 and **outer=2·inner exactly** in the supplied f64 parameters.
The ABI refuses any other ratio, even one numerically close to two.

- S(z)=z³(10−15z+6z²), with symmetric evaluation near its upper endpoint.
- L(r)=1 for r<=inner; S((outer−r)/inner) for inner<r<outer; 0 for r>=outer.
- V(t)=0 for t<=0 and t>=1.5; S(t) for 0<t<1;
  S((1.5−t)/0.5) for 1<=t<1.5.
- Forward: `u′=u·(1−0.08·a(u)·V(t)·L(|u|)); v′=v`.

Positive amounts narrow the named side toward its fixed center; negative amounts
expand it. Head-axis coordinates do not change in the real-arithmetic model.
Since the multiplier is in [.92,1.08], nonzero horizontal positions never cross
the center. The support boundary is fixed, not shifted by the inverse.

In the feather let z=(outer−r)/inner and B=L+rL′. S′(z)=30z²(1−z)² is in
[0,1.875]. Since 1<=r/inner<=2, `B=S(z)−(r/inner)·S′(z)` lies in [-3.75,1].
Inside the flat lateral core B=1, and outside support B=0. Therefore

`0.7 <= ∂u′/∂u = 1−0.08·a·V·B <= 1.3`.

The bound is conservative but independent of amount signs and side asymmetry.
At u=0 unequal amounts can produce distinct one-sided slopes
`1−.08·right·V` and `1−.08·left·V`, each in [.92,1.08]. The map is continuous,
strictly monotone, sign-preserving and horizontally bi-Lipschitz across this
derivative cusp. It is deliberately **not globally C1** for unequal sides.
There is no assertion of a classical Jacobian at the cusp; the determinant bound
holds elsewhere. This is not a hidden smoothing approximation.

For each fixed finite geometry the vertical shear is bounded by
`.08·outer·max|V′|/H <= .3·outer/H`, because max|V′|=3.75. This is finite in
real arithmetic, but can be arbitrarily large across geometries. Thus the bound
is not a uniform two-dimensional condition-number, anatomy, composited-field,
photographic quality or identity-preservation guarantee.

## True inverse and floating-point limits

For a destination q, v is unchanged and the horizontal sign is known. Set
q_r=|u_q|>0 and use that side's amount and weight V(t_q). Solve the physical
radial displacement d=q_r−r_source:

`R(d)=d+.08·(q_r−d)·a·V(t_q)·L(q_r−d)=0`.

The derivative R′ lies in [.7,1.3]. For positive amount, d is in
`[max(−B,q_r−outer),0]`; for negative amount it is in `[0,min(B,q_r)]`, where
`B=(.08·outer)·abs(a)·V`. These brackets keep source radius within [0,outer]
and include the unique root. Safeguarded Newton steps stay strictly inside
the bracket, otherwise a bisection step is used. There are at most 96 iterations.
The signed horizontal displacement is sign(u_q)·d, and output is
`D(q)=right·sign(u_q)·d=q−source(q)`. The host samples q−D(q), not q+D(q).
This is neither forward displacement at q nor a negated-forward approximation.

The scalar residual is bounded by
`max(64·f64_epsilon·max(abs(d),abs(target)),8·smallest_subnormal)`.
Computing (.08·radius) before multiplying amount can preserve a subnormal
amount when the physical displacement is representable. Supported nonzero edits
that yield zero V, zero scalar motion or zero vector motion are refused. A
positive physical v whose normalization v/H underflows to zero is refused for
an otherwise moving point, rather than treated as the upper boundary. Normalized
infinity from positive tiny H is outside the finite vertical support.

The representable source q−D is separately checked for finite values, unchanged
head-axis coordinate, unchanged horizontal sign, nonzero forward displacement
and a forward roundtrip. Its absolute tolerance is
`max(256·f64_epsilon·max(abs(q components),abs(o components),H,outer,abs(d)),
8·smallest_subnormal)`. Overflow, residual failure, stalled/exhausted solves,
nonrepresentable support motion and failed source checks refuse the entire batch.

These are explicit f64 acceptance limits, not an exact floating-point inverse.
A finite nonzero displacement may disappear when subtracted from a large
coordinate; subsequent float32 conversion or image sampling can lose still more
effective motion. No changed-pixel or visible-change guarantee is made. The
mathematical centerline is fixed exactly; a measured/rotated tip may have a tiny
projected u from roundoff. The host must check actual tip invariance within its
declared f64 geometry tolerance, never insert a fake snapped landmark.

Frames must be finite unit orthogonal axes within 1e-10. Only after validation
is right normalized and down replaced by its signed perpendicular. Both
handednesses are allowed. `canonical_frame(right,down)` exposes the same rule
to the host. This removes roundoff, not pose, skew or anatomical errors.

## C ABI, ownership and failure atomicity

`lrt_chin_shape_abi()` returns uint32 1. The versioned evaluator in
`chin_shape.h` accepts points/output as row-major N×2 f64, N=1..65536, and exactly
11 f64 parameters:

`[ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,left,right]`.

There is no tail parameter: the .5 tail is fixed. All lengths count f64 elements,
not bytes. All point and parameter entries must be finite, even for a neutral
call. Origin, widths, H and queries share source-coordinate units.

Null, unaligned and overflowing spans, invalid count/lengths and output overlap
with either input are rejected before slice construction. The read-only inputs
may overlap each other. The caller still guarantees live accessible allocations
of declared extent, immutable inputs and exclusively writable output throughout
the call. Address checks cannot establish allocation provenance, bounds or
lifetime. This is not a hostile-process memory-safety boundary. Panic containment
does not recover foreign faults, invalid memory, aborts or allocator termination.

All validation and evaluation occur in private bounded scratch before the only
output write. A failure on a late point leaves the entire caller output untouched.
Scratch uses try_reserve_exact, at most 1 MiB f64 payload, and reports allocation
failure. Status: 0 success; 1 ABI/count/length/pointer/alias; 2 nonfinite/range;
3 frame/H; 4 support/arithmetic/precision/residual; 5 allocation; 6 contained panic.

Python requires exact native NumPy float64 arrays with the declared shapes,
takes owned contiguous read-only snapshots and never mutates caller arrays.
Caller mutation during copying is unsupported. Returned output is owned,
contiguous and writable. It is published only after status, finite output/source,
positive-zero unchanged support, nonzero moving support, horizontal direction,
amplitude, head-axis and no-side-crossing postconditions. These are boundary
checks, not a Python deformation fallback or second inverse implementation.

The loader requires actual shared-library load, ABI 1 and the versioned symbol.
`chin_shape_state.capability()` reports only `chin_shape_available` and
`chin_shape_reason`, not anatomical usability or image acceptance. State-only
neutral/check/active/preset/adjust/link do not load native. Direct evaluate,
including a neutral call, requires the core. There is no runtime compilation,
download, model loading or alternate algorithm.

## Unrun fixtures and packaging

Rust fixtures cover signed widths, fixed center/tip and head-axis coordinate,
independent and opposite sides, asymmetric near-center continuity/one-sided
slopes, monotone roundtrips and no sign crossing, inner/outer/vertical edges,
genuine inverse behavior, roll/translation/scale and both handednesses, frame
roundoff, tiny represented deltas lost by coordinate subtraction, tiny weights,
underflow refusal, invalid values/geometry, atomic late failure, pointer/alias
errors and maximum batches. Python fixtures cover strict state, linked equality,
shape/dtype/ownership, loader/status rejection, boundary postconditions and
installed-core signed/asymmetric/rotated/tiny-motion behavior. Every fixture is
**AUTHORED / UNRUN**; installed-core fixtures skip when the library is absent.

`packaging/build-chin-shape.sh` is an explicit offline rustc recipe with no
dependencies or registry access. It stages a temporary sibling, cleans it up on
failure, and atomically renames after successful compilation. The application
never invokes it and it has not been run. Final-source build, fixture execution,
measured-face integration, combined maps, preview/export/history/cancellation,
image review, performance and product acceptance remain separate unpassed gates.
