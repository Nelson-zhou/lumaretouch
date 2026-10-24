# Lower-third length, private ABI 1

Original dependency-free GPL-3.0-or-later Rust implementation. Code, fixtures and
packaging are **AUTHORED / UNRUN**. No build, tests, numerical execution, runtime,
integration, photographic quality, performance or product acceptance is claimed.
No external implementation, commercial code, model weights or assets were copied.

## Scope and traceability

Exact control: `LNX-REF-PC-32466-C-1ae8316994`, 下庭. Operation
`lnx.lower_face.v1` stores exactly `{"version":1,"amount":0.0}`. Amount is a finite
Python int/float in [-1,1], excluding booleans and coercible numeric types.
Positive lengthens the measured lower facial third; negative shortens it.
Neutral is zero, not scale one. Unknown keys and versions are refused. Identity,
landmarks, pixels, paths, support geometry and caches never enter portable state.

The official semantic context supplied and verified by the parent task is
https://wiki.pixcakeai.com/guide/9405.html. It establishes the control meaning,
not this implementation's numeric calibration. The 0.08 gain, lateral envelope,
vertical tail, frame tolerance and numerical solver below are original local
policies. They are not advertised as a reproduction of a proprietary algorithm.

This control is distinct from legacy `small_chin`, which pins the mouth and
alters a chin contour. It does not pin mouth/interior features: supported points
move along the measured head axis. It is also distinct from whole-face size,
which changes both face axes. This component preserves lateral coordinates,
fixes the upper boundary and changes lower-third length only. No anatomy is
inferred here; no RGB pixels are sampled; no 3D or identity synthesis is done.
The geometry host owns current-source measurement, evidence, coexistence,
compositing, global sampling and final composed-field acceptance.

## Original forward map and true inverse

Let o be the measured upper boundary origin, right/down be an orthonormal frame,
u=(p-o)·right, v=(p-o)·down, and t=v/H. H>0 is measured lower-third height.
The lateral weight is 1 for |u|<=inner_x, zero for |u|>=outer_x, and a quintic
fade between them. Require 0<inner_x<outer_x. Define

- S(z)=z³(10+z(6z−15)), evaluated symmetrically near its endpoints.
- V(t)=0 at t<=0 and t>=1+tail.
- V(t)=S(t) for 0<t<=1.
- V(t)=1−S((t−1)/tail) for 1<t<1+tail.
- Forward map: u′=u; v′=v+0.08·amount·H·L(u)·V(t).

The ABI permits tail in [0.25,1]; the runtime policy is 0.5. V and L have zero
first/second derivatives at their joins. In real arithmetic the axial forward
derivative is at least

`1−0.08·abs(amount)·1.875/min(1,tail) >= 0.4`.

The shear term from the lateral feather does not change this Jacobian
determinant: u′=u. This monotonicity gives a unique inverse and keeps the same
fixed support endpoints. It is not a photorealism, combined-field, condition
number or anatomy guarantee. Extremely narrow lateral feathers can still have
large shear; host evidence and final combined mapping checks remain necessary.

For each destination q, the native kernel solves its scalar inverse shift d:

`d = k·V(tq−d/H), k=((0.08·H)·amount)·L(uq), tq=vq/H`.

The root is bracketed by min(0,k) and max(0,k). Safeguarded Newton steps stay in
that bracket, falling back to bisection, for at most 96 iterations per point.
This solves the inverse, rather than negating a forward displacement evaluated
at q. The returned vector is `D(q)=down·d=q−source(q)` in the algebraic contract;
the image host samples at `q−D(q)`, not q+D(q).

Solving d directly avoids subtracting almost equal source/destination values.
Multiplying 0.08·H before amount can preserve a subnormal amount when a large H
makes its physical shift representable. Exact neutral and at/outside-support
queries return positive zero. Nonzero supported motion that underflows to exact
zero, numerical overflow, a failed residual or exhausted solve is refused, not
silently replaced by a neutral edit. There is no arbitrary minimum slider
strength or hidden strength clamp.

## Floating-point limits

The scalar residual is verified against
`max(64·f64_epsilon·max(abs(d),abs(kV)), 8·smallest_subnormal)`.
The computed representable source is also checked for finite coordinates,
lateral preservation and a forward roundtrip with absolute tolerance
`max(256·f64_epsilon·max(abs(q components),abs(o components),H,abs(d)),
8·smallest_subnormal)`.

These are explicit f64 bounds, not an exact floating-point inverse claim or a
pixel-error-quality guarantee. A tiny finite returned delta can be representable
while subtracting it from q rounds back to q. A downstream float32 joint map or
pixel sampler can lose still more effective motion. Therefore a nonzero amount
does not guarantee a changed or visibly different pixel. The host must not
confuse native residual acceptance with effective pixel movement or commercial
quality; it may reject geometry whose required target cannot be represented.
No attempt is made to hide these limits with a different algorithm.

Frames must be finite, unit-length and orthogonal within 1e-10. After validating
that tight tolerance, right is normalized and down becomes its signed
perpendicular. This removes roundoff only; larger skew is rejected, not repaired.
Both handednesses are allowed and anatomical orientation stays with the host.
Python `canonical_frame(right, down)` exposes the same convention so measurement,
support and target construction use matching axes. Floating-point operations
still have ordinary rounding; lateral preservation is exact only in the real
arithmetic contract.

## Boundary, safety and ownership

`lrt_lower_face_abi()` returns uint32 1. The versioned C evaluator is declared in
`lower_face.h`. All lengths count f64/double elements, not bytes. Points and output
are row-major N×2, with N in 1..65536; parameters have exactly 11 elements:

`[ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,tail,amount]`.

Origin, H, lateral widths and queries share source-coordinate units. Tail and
amount are dimensionless. Every point and parameter must be finite, including
for a direct neutral call. The caller batches larger grids.

Null, unaligned, overflowing address spans, incorrect lengths/counts and output
overlap with either input are refused before constructing slices. Read-only
inputs may overlap each other. The caller still guarantees accessible live
allocations covering declared lengths, immutable input and exclusively writable
output for the entire call. Address checks cannot prove allocation extent,
lifetime or provenance. This is not a hostile-process memory-safety boundary.
Panic containment cannot recover invalid foreign memory, process aborts or
allocator-internal termination.

All validation and computation precede the only output write. Any nonzero status
leaves the entire output untouched, even if a later point fails after earlier
successful computations. `try_reserve_exact` bounds scratch payload to 1 MiB and
reports allocation failure normally. Derived offset/projection overflow and
nonfinite source coordinates are refused. Division by tiny H that produces an
infinite normalized query is safely outside the finite vertical support.

Status: 0 success; 1 ABI/count/length/pointer/alias; 2 nonfinite or amount range;
3 frame/H; 4 support/arithmetic/precision/residual; 5 allocation; 6 contained panic.

Python accepts exact native NumPy float64 arrays with the exact shapes, checks
both shapes/dtypes before any copying, and takes independent contiguous read-only
input snapshots. Callers must not mutate during copying. Returned delta owns
writable contiguous storage and is published only after native status, finite
output/source, exact unchanged-support zero, direction, axial amplitude and
lateral-preservation postconditions. These checks are not a Python deformation
fallback or a second inverse solver.

The loader verifies actual library loading, ABI 1 and the versioned symbol.
`lower_face_state.capability()` reports only `lower_face_available` and
`lower_face_reason`, not available anatomy or quality. Native is imported by state
only when capability is requested. Neutral/check/active/preset are native-free;
a direct evaluator call, even at neutral, requires the native core. No runtime
compilation, model loading, network request or fallback exists in this component.

## Authored fixtures and explicit packaging

Rust fixtures cover signed chin targets versus forward-negation, inverse
roundtrips, monotonicity across tail/lateral regions, derivative bounds,
endpoints, exact zero, bracket bounds, lateral preservation, roll/scale/translation,
both frame handednesses, roundoff canonicalization, tiny amounts, finite-value
refusal, output atomicity, all pointer/shape/alias failures and maximum batches.
Python fixtures cover strict state/dtype/shape checks, independent ownership,
frame helper, no-fallback loading, statuses, output postconditions and installed
core behavior. All are UNRUN; installed-core fixtures skip when absent and never
build/download a substitute. No fixture result is asserted here.

`packaging/build-lower-face.sh` is an explicit dependency-free offline rustc
recipe. It stages a temporary sibling, cleans it on failure and atomically
renames only after successful compilation. It is not called by application
runtime and has not been run. Final-source build, fixture execution, measured-face
integration, preview/export/history/cancellation, image review, performance and
product acceptance remain separate unpassed gates.
