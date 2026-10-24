# Mid-face length with retained lower-face plateau, private ABI 1

Original dependency-free GPL-3.0-or-later Rust implementation using this project's
existing checked numerical-boundary patterns in a new versioned component.
Code, fixtures and packaging are **AUTHORED / UNRUN**. No build, test execution,
numerical execution, runtime integration, photographic quality, performance or
product acceptance is claimed. No external implementation, commercial code,
model weights or assets were copied. Existing lower-face and face-size source
files are not changed by this component.

## Scope and traceability

Exact control: `LNX-REF-PC-32466-C-ea67c9d99f`, 中庭. Operation
`lnx.mid_face.v1` stores exactly `{"version":1,"amount":0.0}`. Amount is a finite
Python int/float in [-1,1], excluding booleans and coercible numeric types.
Positive lengthens the measured visual mid-face interval; negative shortens it.
Neutral is zero, not scale one. Unknown keys and versions are refused. Identity,
landmarks, pixels, paths, support geometry and caches never enter portable state.

The official semantic context supplied and verified by the parent task is
https://wiki.pixcakeai.com/guide/9405.html. It establishes the control meaning and
direction, not an exact anatomical boundary, proprietary deformation, numeric
calibration or quality target. The upper boundary, 0.08 gain, plateau construction,
lateral envelope, support padding, tail, frame tolerance and numerical solver
are original local policies, not a claimed reconstruction of another algorithm.

This component is distinct from lower-face length: its vertical envelope rises
from an upper-eye boundary toward the nose, stays flat through the retained
lower-face extent including the chin, and only then feathers into the neck.
It does not shorten or lengthen the nose-to-chin interval for retained source
points lying inside both flat cores. Lower-face length instead has a rise-and-fall envelope
without this lower-face translation plateau. This is not legacy `small_chin`,
whole-face size, rigid face translation or an identity-pinning operation.

The rising band can change nose geometry and other interior features; no
nose-preservation, unchanged expression or universal anatomy claim is made.
No anatomy is inferred here, RGB pixels are not sampled, and no 3D or identity
synthesis is done. The geometry host owns current-source measurement, evidence,
coexistence, compositing, global sampling and final composed-field acceptance.

## Original forward map and true inverse

Let o be the measured upper-eye-boundary origin, right/down be an orthonormal
frame, u=(p-o)·right, v=(p-o)·down, and t=v/H. H>0 measures the interval from this
upper boundary to the selected nose boundary. Let P=`plateau_end`. The host
measures P to include every claimed retained lower-face source point, including
the chin, plus measured support padding. P is **not** a fixed facial ratio or the
coordinate of a single chin landmark. Native guards are P in [1.25,8] and tail
in [0.25,4]; runtime may reject more strictly on its actual measured evidence.

The lateral weight L(u) is 1 for |u|<=inner_x, zero for |u|>=outer_x, and a
quintic fade between them. Require 0<inner_x<outer_x. Define:

- S(z)=z³(10+z(6z−15)), evaluated symmetrically near its endpoints.
- V(t)=0 for t<=0.
- V(t)=S(t) for 0<t<1.
- V(t)=1 for 1<=t<=P.
- V(t)=S((P+tail−t)/tail) for P<t<P+tail.
- V(t)=0 for t>=P+tail.
- Forward map: u′=u; v′=v+0.08·amount·H·L(u)·V(t).

On the vertical plateau, equal-u points translate equally. All nose/lips/chin
and other retained source points inside the flat lateral core share one translation,
so their lower-face intervals are preserved in the real-arithmetic model.
The host must establish these source-support conditions. A negative amount may
move a nose target from source t=1 to destination t=.92; the target need not stay
in the same source-coordinate plateau. Points at different lateral feather
weights do not receive identical motion, and this
kernel alone cannot prove anatomical preservation or composited-image behavior.

Runtime derives `tail=max(0.25,0.5*(P−1))` from measured plateau extent. State
exposes `TAIL_FACTOR=0.5`, `MIN_TAIL=0.25` and `MAX_TAIL=4.0`; it stores none of
these geometry parameters in a portable recipe. P and tail are dimensionless.
V and L have zero first/second derivatives at their joins. In real arithmetic
the forward axial derivative and two-dimensional Jacobian determinant are at
least:

`1−0.08·abs(amount)·1.875/min(1,tail) >= 0.4`.

This bound is independent of P. The lateral shear term does not change the
determinant because u′=u. The map is strictly monotone along each head-axis line,
with a unique inverse and fixed support endpoints. This is not a combined-field,
condition-number, anatomy or photorealism guarantee: an extremely narrow lateral
feather can have large shear. Host evidence and final joint-map checks remain
necessary.

For each destination q, the native kernel solves the physical inverse shift d:

`d = k·V(tq−d/H), k=((0.08·H)·amount)·L(uq), tq=vq/H`.

The root lies between min(0,k) and max(0,k). Safeguarded Newton steps remain in
that bracket, with bisection otherwise, for at most 96 iterations per query.
This is an actual inverse solve, not a negated forward displacement or forward
displacement evaluated at q. The algebraic result is `D(q)=down·d=q−source(q)`;
the image host samples at q−D(q), not q+D(q).

Solving d directly avoids subtracting almost equal source/destination values.
Multiplying 0.08·H before amount can preserve a subnormal amount when a large H
makes its physical shift representable. Neutral and at/outside-support queries
return exact positive zero. Nonzero supported motion that underflows to zero,
arithmetic overflow, a failed residual or exhausted solve is refused, not
silently replaced by neutral or another algorithm. There is no hidden slider
threshold, minimum strength or strength clamp.

## Floating-point limits

The scalar residual is checked against
`max(64·f64_epsilon·max(abs(d),abs(kV)), 8·smallest_subnormal)`.
The computed representable source is also checked for finite coordinates,
lateral preservation and a forward roundtrip with absolute tolerance
`max(256·f64_epsilon·max(abs(q components),abs(o components),H,abs(d)),
8·smallest_subnormal)`.

These are explicit f64 bounds, not an exact floating-point inverse or pixel-error
quality promise. A tiny finite delta can be representable while subtracting it
from q rounds back to q. Downstream float32 map conversion or a pixel sampler can
lose still more effective motion. A nonzero amount does not guarantee a changed
or visibly different pixel. Native residual acceptance does not prove effective
movement or commercial quality. The host may reject geometry whose required
target cannot be represented; no substitute algorithm hides those limits.

Frames must be finite, unit-length and orthogonal within 1e-10. Only after this
tight validation is right normalized and down made its signed perpendicular.
This removes roundoff, not pose, skew or anatomical errors. Both handednesses
are accepted; the host must supply anatomical orientation. Python
`canonical_frame(right, down)` exposes the same convention so measurement,
support and targets use matching axes. Lateral preservation is exact in the
real-arithmetic model, but floating-point operations retain ordinary rounding.

## Boundary, safety and ownership

`lrt_mid_face_abi()` returns uint32 1. The versioned evaluator is declared in
`mid_face.h`. Lengths count f64/double elements, not bytes. Points/output are
row-major N×2, N in 1..65536. Parameters have exactly 12 elements:

`[ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,plateau_end,tail,amount]`.

Origin, H, lateral widths and queries share source-coordinate units. Every
point/parameter must be finite, including a direct neutral call. Larger grids
must be batched by the host.

Null, unaligned or overflowing address spans, wrong lengths/counts and output
overlap with either input are refused before constructing slices. Read-only
inputs may overlap each other. The caller still guarantees accessible live
allocations of declared extents, immutable inputs and exclusively writable
output for the full call. Address checks cannot prove allocation extent,
lifetime or provenance. This is not a hostile-process memory-safety boundary.
Panic containment cannot recover foreign faults, invalid memory, process aborts
or allocator-internal termination.

All validation/computation precedes the only output write. A nonzero status
leaves the entire output untouched even if a later point fails. Bounded
`try_reserve_exact` scratch is at most 1 MiB f64 payload and reports allocation
failure normally. Derived offset/projection overflow and nonfinite source
coordinates are refused. Division by a tiny positive H that makes a normalized
query infinite is outside the finite vertical support and returns zero.

Status: 0 success; 1 ABI/count/length/pointer/alias; 2 nonfinite or amount range;
3 frame/H; 4 support/arithmetic/precision/residual; 5 allocation; 6 contained panic.

Python accepts exact native NumPy float64 arrays of the declared shapes, checks
shapes/dtypes before copying, and takes independent contiguous read-only input
snapshots. The caller must not mutate during copying. Output is owned, writable
and contiguous, and is published only after native status, finite output/source,
exact unchanged-support zero, direction, axial amplitude and lateral-preservation
postconditions. These checks are not a Python deformation fallback or second
inverse solver.

The loader checks actual library loading, ABI 1 and the versioned evaluator
symbol. `mid_face_state.capability()` reports `mid_face_available` and
`mid_face_reason` only, not usable anatomy or quality. State imports native only
when capability is requested. Neutral/check/active/preset operations are
native-free. A direct evaluator call, even neutral, requires the installed core.
There is no runtime compilation, model loading, network access or fallback.

## Authored fixtures and explicit packaging

Rust fixtures cover signed nose targets, genuine inverse behavior in the rise
and neck, preserved nose/lips/chin/retained intervals, plateau-independent
monotonicity, determinant bounds, quintic joins, exact zero, amplitude bracket,
lateral preservation, roll/translation/scale, both handednesses, frame roundoff,
tiny physical shifts, all finite/range/frame/support refusals, output atomicity,
pointer/length/alias failures and maximum batches. Python fixtures cover strict
state/dtype/shape, independent ownership, frame helper, no-fallback loading,
status/output rejection, signed plateau behavior, rotation and float32 limits.
All fixtures are **UNRUN**. Installed-core fixtures skip when absent and never
build/download a substitute. No fixture result is asserted here.

`packaging/build-mid-face.sh` is an explicit dependency-free offline rustc recipe.
It stages a temporary sibling, removes that file on failure and atomically
renames only after successful compilation. The application never invokes it,
and it has not been run. Final-source build, fixture execution, measured-face
integration, preview/export/history/cancellation, image review, performance and
product acceptance remain separate unpassed gates.
