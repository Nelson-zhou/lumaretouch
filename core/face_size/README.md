# Whole measured-face size, private ABI 1

Original dependency-free GPL-3.0-or-later Rust implementation. All code and
fixtures are **AUTHORED / UNRUN**. No build, tests, numerical execution, runtime,
integration, visual quality, performance or photographic acceptance has been
established. No external implementation, commercial code or weights were copied.

## Scope and traceability

Exact control: `LNX-REF-PC-32466-C-728fc62cdd`, 小脸. Positive amount shrinks the
**whole measured face**, including internal features; negative amount enlarges
it. This is not slim-face/contour narrowing, feature-pinned warping, 3D synthesis,
identity matching, pixel invention or a second image sampler.

Public semantic context supplied to this task:
https://wiki.pixcakeai.com/guide/9405.html. The identifier comes from project
traceability, not a claim that a commercial numeric slider was reproduced.
Inverse sampling background:
https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html.
These are conceptual references, not imported code or a new source-verification
claim. The gain, envelope and derivative floor below are explicit original local
product policies, not reference-product specifications.

Portable operation `lnx.face_size.v1` stores exactly
`{"version": 1, "amount": 0.0}`. Amount must be a finite Python int/float in
[-1,1]; booleans, other numeric/coercible types and unknown keys are refused.
No identity, landmarks, source bytes, masks, paths or caches are serialized.
The local mapping is `scale = 1 - 0.06 * amount`, hence 0.94..1.06. It is not
silently clamped, converted from legacy slim-face or composed with contour edits
inside this component. The host owns coexistence policy and measurement evidence.

## Analytic inverse field

For destination query q and measured center c, define the dimensionless ellipse
radius r = hypot(dot(q-c, right)/hx, dot(q-c, up)/hy). Then:

- w(r) = 1 for r <= inner.
- w(r) = 0 for r >= outer.
- Otherwise t = (r-inner)/(outer-inner) and
  w(r) = 1 - (6t^5 - 15t^4 + 10t^3).
- Return D(q) = q - source(q) = (1 - 1/scale) * w(r) * (q-c).
- The image host samples at source(q) = q - D(q), never q + D(q).

Inside the core, source(q) = c + (q-c)/scale exactly in the algebraic contract.
Both dimensions therefore scale uniformly, rather than narrowing the oval while
pinning eyes/nose/mouth. The actual floating-point evaluation has ordinary f64
rounding. The equivalent coefficient `(scale-1)/scale` avoids reciprocal
subtraction cancellation for representable nonneutral scales near one, and no
rounded-source subtraction is used to obtain delta. The center, neutral scale
and every at/outside-support point return
exact positive-zero delta. The quintic has zero first and second derivatives at
both support edges. Its symmetric piecewise evaluation uses the same polynomial
without strength clamps and avoids near-outer cancellation.

The host must choose a measured core that contains all intended facial anatomy,
derive/support the head frame and extents from current-source evidence, and
reject unavailable anatomy. Arbitrary caller parameters cannot establish those
facts. This evaluator does not infer an oval or manufacture missing pixels.

## Boundary and ownership

`lrt_face_size_abi()` returns uint32 1. The versioned C function is:

```c
int32_t lrt_face_size_evaluate_v1(
    const double *points, size_t points_len,
    const double *params, size_t params_len, size_t count,
    double *output, size_t output_len);
```

All lengths count f64/double elements, not bytes. Points and output are row-major
N×2, N in 1..65536. Parameters have exactly 11 elements:
[cx, cy, right_x, right_y, up_x, up_y, hx, hy, inner, outer, scale]. Center,
half-extents and queries share the same source-coordinate units; radii and scale
are dimensionless. Axes must be unit and orthogonal within 1e-6, hx/hy strictly
positive, and 0 < inner < outer. All values must be finite and scale in [0.94,1.06].
Both handednesses are allowed; the geometry host owns source-coordinate meaning.

The conservative radial/tangential inverse-derivative lower bound

`min(1, 1/scale) - abs(1/scale - 1) * 1.875 * outer/(outer-inner)`

must be finite and >= 0.2. This uses max quintic derivative 1.875 and rejects
fold-risk in narrow transitions. At scale 1 the bound is exactly 1, without
evaluating a needless radius ratio. It is not a photographic-quality guarantee,
condition-number bound for highly eccentric ellipses, or approval to compose
unbounded other fields. The host still validates its final composed mapping.

Null, unaligned, overflowing spans and output overlap with either input are
rejected before slice creation. Read-only inputs may overlap one another. The
caller must still provide accessible live allocations of the stated lengths,
keep every input immutable and output exclusively writable throughout the call.
Arithmetic checks cannot prove actual allocation extent, lifetime or provenance;
invalid non-null pointers remain unsafe caller violations.

All input validation and computation finish before a single output copy. Any
nonzero status leaves the entire caller output untouched. Scratch is checked
with `try_reserve_exact`, bounded to 1 MiB of f64 payload; allocation failure is a
normal error. Finite-input subtraction overflow, indeterminate projections or
nonfinite derived source coordinates are refused, not coerced. Infinite radius
from division by a tiny positive extent is safely outside finite support.
Unwind containment cannot recover invalid foreign memory, process abort or
allocator-internal process termination.

Status: 0 success; 1 ABI/count/length/pointer/alias; 2 nonfinite/out-of-range
values; 3 frame/extents; 4 support/fold risk/arithmetic overflow; 5 checked
allocation failure; 6 contained Rust panic.

Python `face_size_native.evaluate(points, params)` accepts exact native NumPy
float64 shapes, checks both before allocating, then takes independent contiguous
read-only snapshots even from contiguous or read-only caller arrays. Callers may
not mutate during copying. Output is separately owned, writable, contiguous
float64 N×2, published only after status, finite displacement/source coordinates
and exact neutral/center/outside-zero postchecks. It is delta, not source
coordinates. The caller batches larger grids. There is no Python deformation
fallback, image sampling, model download or runtime compilation.

The loader verifies the actual shared library, ABI and versioned symbol.
`face_size_state.capability()` reports only `face_size_available` and
`face_size_reason`, never claims usable anatomy or quality. Neutral state/check/
active/preset do not load or require native. A direct evaluator call, including a
neutral one, still requires native and validates all inputs.

## Authored verification and packaging

`tests.rs` covers both amount signs, uniform two-axis core without identity pins,
quintic midpoint/near-edge behavior, exact zeros, scale/roll/translation
covariance, malformed values/frame/support, fold-risk rejection, all-or-nothing
overflow, all lengths/pointers/overlaps and maximum batch. Python fixtures cover
strict shape/dtype/state checks, ownership snapshots, loader failure, status
refusal and output postchecks, plus installed-library contracts. All are UNRUN;
installed-library tests skip when absent and never build/download a substitute.

`packaging/build-face-size.sh` is an explicit dependency-free offline rustc build
recipe, not called from the application. It stages a private temporary sibling,
cleans up on failure and atomically renames only after successful compilation.
The script has not been run. Final-source local build, fixture execution,
measured-face integration, preview/export/cancellation/history, image review and
product acceptance remain separate gates.
