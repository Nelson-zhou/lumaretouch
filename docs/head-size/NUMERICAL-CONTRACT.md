# Small head: complete head and hair, original numerical contract

Status: AUTHORED / UNRUN. This document is a source-level contract, not a test,
build, image-quality, host-integration or release-acceptance report.

Requirement: `LNX-REF-PC-32473-C-dc1b0ba40a`, 小头. The official reference
[PixCake local portrait adjustment guide](https://www.pixcakeai.com/guide/125979)
defines this as the head including hair (the recorded source excerpt is lines
121–123). It is distinct from the face-size control. A face oval, synthetic
hairline or inferred extension of pose facial points does not satisfy this scope.

## Ownership boundary

- A source-bound, person-bound manual review supplies the complete visible head
  and hair box, outer transition box and explicitly marked pivot. All hair,
  including disconnected-looking strands, must be reviewed. The core does not
  inspect pixels or prove that the review is truthful.
- Source/person/face ownership, crop revision, review digest, stale-evidence
  rejection and forbidden-person/contact exclusion belong to the host. A face
  box must not be used as a substitute for complete head-and-hair evidence.
- Body33 head points 0–10 and shoulders 11–12 are observed veto evidence only.
  Neither a head box nor a pivot nor a hairline is synthesized from them.
- A serialized state is not a review certificate. Every numeric state is fully
  revalidated on describe/evaluate. Numerically valid forged state cannot prove
  source/person ownership; host review remains mandatory.

## ABI 1

All arrays are contiguous native-endian binary64. Lengths count doubles. The C
header is `core/head_size/head_size.h`. ABI discovery returns unsigned integer 1.

`lrt_head_size_prepare(points, 165, recipe, 2, support, 10, width, height, out, 13)`
accepts:

1. Body33 as 33 rows of `[x_normalized, y_normalized, z, visibility, presence]`.
2. Versioned recipe `[1, amount]`; finite amount lies in `[0,1]`. Positive shrinks;
   negative enlargement is not silently reinterpreted. `k = 0.08 × amount`.
3. Normalized support10 in this exact order:
   `[head_x1, head_y1, head_x2, head_y2, transition_x0, transition_y0,
     transition_x3, transition_y3, pivot_x, pivot_y]`.
4. Exact original-source integer dimensions, each in `[2,1_000_000]`.

Normalized x/y become source pixels by multiplying by width−1 / height−1.
No crop, preview, thumbnail, display or proxy coordinate substitution is allowed.
The resulting state13 is:

`[x0,x1,x2,x3, y0,y1,y2,y3, cx,cy, k,width,height]`.

`lrt_head_size_describe(state, 13, facts, 16)` returns:

`[x0,y0,x3,y3, x1,y1,x2,y2, cx,cy, 1−k, D,L,(1−L)^2, 1e−7,64]`.

These are outer transition box4, head-and-hair plateau box4, pivot2, plateau
scale, conservative displacement upper bound, conservative derivative upper
bound, forward-determinant lower bound, inverse residual tolerance in source
pixels, and maximum fixed-point iteration count. Metadata is not empirical
evidence that the control has passed a quality gate.

`lrt_head_size_evaluate(state, 13, xy, 2N, N, delta, 2N, inverse_det, N)` evaluates
at destination query pixels, including off-grid points. The displacement
convention matches the existing geometry owner: `source = query − delta`.
The determinant output is the inverse map's local area scale, not the forward
determinant. `N` is in `[0,1_048_576]`; empty input still validates the state.

## Admission and full prepared-state revalidation

Every state must be finite and satisfy all of these, including at amount zero:

- Strict nesting `x0<x1<x2<x3`, `y0<y1<y2<y3`.
- At least one original-source pixel clearance: `x0,y0 >= 1`,
  `x3 <= width−2`, `y3 <= height−2`.
- Both plateau dimensions at least 32 pixels; each of the four transition
  margins at least 16 pixels. These are not rounded or enlarged automatically.
- Pivot strictly inside the plateau; `0 <= k <= 0.08`.
- The unchanged requested strength satisfies `L <= 0.45` and `D <= 128 pixels`.

Prepare additionally requires every value in all 165 pose entries to be finite.
The 13 required observations have x/y strictly inside normalized `(0,1)` and
visibility/presence each in `[0.8,1]`. All head points 0–10 must be strictly
inside the plateau. Outer bottom is strictly above both shoulder y coordinates.
Shoulder screen separation is at least 32 pixels; absolute y difference is at
most 0.25 times that separation and absolute normalized-z difference times
width−1 is at most 0.35 times the separation. Unsupported/hidden/strongly tilted
or foreshortened shoulders are refused, not reconstructed. Unused limbs 13–32
need only be finite and never establish head/hair evidence.

No source clipping, amount clamping, automatic margin widening, pivot repair,
inferred support, identity-on-error or silent strength attenuation is permitted.
The conservative bound can refuse high strengths when the available reviewed
head-to-shoulder clearance is small. Such refusal is not a claim that the full
slider range is acceptable for that portrait. A new strength/support must be
explicitly requested and reviewed, not secretly substituted by this kernel.

## Forward map and safety argument

For one coordinate, let the window be 0 outside `[a,d]`, 1 on `[b,c]`, and use
quintic `S(t)=6t^5−15t^4+10t^3` to transition from a to b and c to d. This makes
the window and its first two derivatives continuous at support/plateau edges.
Its derivative magnitude is bounded by `1.875 / margin`.

For `p=(x,y)`, explicit pivot c and separable weight `w=wx(x)wy(y)`:

`d(p)=−k w(p) (p−c)` and `F(p)=p+d(p)`.

Every plateau point, including reviewed hair, therefore follows the same
isotropic transform `c+(1−k)(p−c)`. It has no eye/nose/mouth pins or selective
facial sub-control. Outside the outer transition the map is exactly identity;
the shoulders below it consequently remain fixed.

Let R be the greatest distance from the pivot to the four transition corners,
mx the smaller horizontal margin, and my the smaller vertical margin. The
Euclidean operator-norm bound is:

`L=k[1+R×1.875×hypot(1/mx,1/my)]`, and `D=kR`.

This follows from `Dd=−k[wI+(p−c)⊗gradient(w)]`, `0<=w<=1`, and
`|gradient(w)| <= 1.875×hypot(1/mx,1/my)`. It is conservative; an admitted state
has `|Dd|<=L<1`. Thus the global map has distances bounded between `(1−L)` and
`(1+L)` times their original value. The compact identity exterior plus global
contraction inverse gives a unique inverse. The determinant remains positive
by continuity from the identity, with bounds `(1−L)^2` and `(1+L)^2`.

This is an analytic source argument, not a substitute for executed precision,
seam, hair coverage, contact-exclusion or perceptual quality tests.

## Inverse and refusal behavior

Starting at `p0=q`, iterate `p_next=q−d(p)` for at most 64 iterations. Stop when
the Euclidean step is at most `1e−9` pixels. Independently verify final Euclidean
forward residual `|F(p)−q| <= 1e−7` pixels, displacement `|q−p| <= D+1e−7`,
finite Jacobian, positive bounded determinant and exact original-source domain.
The determinant bound admits `1e−12` numerical slack. Query and final inverse
coordinates outside the source domain are rejected; they are never clamped.

Error codes: 1 malformed buffer/state/version/numeric input; 2 invalid amount;
4 unsupported required observation; 5 shoulder exclusion/posture failure;
6 support/pivot/minimum-size/safety-budget failure; 8 source-domain failure;
9 inverse convergence/residual/determinant failure. Nonzero status never means a
successful neutral result.

## FFI and Python boundary

Pointers must reference live, aligned, valid allocations of the declared sizes.
All input and output regions are disjoint and must not be concurrently mutated.
Checks reject null/misaligned pointers, invalid lengths, address arithmetic
overflow, oversized batches and overlapping ranges before dereferencing. These
checks cannot prove that a fabricated numeric pointer is mapped live memory;
that remains the unsafe caller's obligation. Empty buffers still need nonnull,
aligned pointers.

Prepare/describe publish only after all checks. Evaluate uses a complete
allocation-free validation pass before its deterministic output pass. Under
the immutable-buffer caller contract, all refusals leave both output buffers
untouched. No Rust heap allocation or partial pixel rendering occurs.

The Python wrapper accepts bounded, materialized arrays/lists/tuples, rejects
oversized query bands before conversion, then snapshots all borrowed inputs as
independent C-contiguous binary64 arrays. State and returned displacement use
bytes-backed read-only arrays, rather than reversible WRITEABLE flags. Output
finiteness, native fact budgets, determinant bounds and source-domain limits
are checked before publishing. Empty bands do not bypass native validation.

The only loader target is installed `bin/liblrt_head_size.so`. Capability checks
are ABI/symbol checks, not numerical acceptance. Missing binaries or refusals
are explicit; there is no Python inverse, RGB sampler, model download or build
fallback. This kernel is not a second renderer and must enter the existing
single owned source-remap/composition chain.

## Originality, conceptual sources and remaining gates

All implementation is original GPL-3.0-or-later. Local waist-length conventions
were consulted for ABI structure, displacement sign and immutable snapshots.
No OpenCV, ITK or other external implementation was copied or linked. Conceptual
primary references previously reviewed for this task:

- [OpenCV geometric transforms and inverse remapping](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html)
- [ITK iterative inverse displacement-field filter](https://docs.itk.org/projects/doxygen/en/stable/classitk_1_1IterativeInverseDisplacementFieldImageFilter.html)

Authored fixtures cover version/order, whole-head/hair uniformity, explicit
pivot, neutral/exterior exactness, fixed shoulders, source-displacement sign,
off-grid inverse residual, Jacobian differentials, strict observations and
shoulder posture, unsafe requested strength, forged states, no inferred limbs,
bounded FFI buffers, empty bands and refusal atomicity. They are all UNRUN.

Still required before any completion/quality claim: authorized native build,
Rust/Python test execution, installed-ABI verification, real source-bound review
fixtures, preview/export off-grid single-remap-chain checks, cancellation and
memory-budget checks, visual comparison across hair textures/lengths and
backgrounds, boundary/contact exclusion, and human photographic acceptance.
