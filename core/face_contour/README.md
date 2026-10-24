# Face-contour forward controls, private ABI 1

Original GPL-3.0-or-later, dependency-free Rust. All implementation and fixtures
are **AUTHORED / UNRUN**. No compilation, numerical execution, integration, visual
quality, performance or product acceptance has been established by this change.
No commercial code, solver or weights have been copied.

## Scope and semantics

This kernel returns bounded **forward 2D displacements at existing control
points**. It is not TPS, an RGB deformation algorithm, a landmark detector,
identity matching, anatomy validation or 3D face reconstruction. The host must
derive roles from its verified face oval and reject unavailable/occluded anatomy.
The host reuses its existing normalized TPS to fit the pullback at displaced
controls and its common one-sampler image pipeline. This kernel does not resample
or inspect an image and must not become a second sampler or replacement solver.

Public semantic reference: https://wiki.pixcakeai.com/guide/9405.html. The original
`/guide/32466` page was unavailable in the parent verification; that is not
represented as newly inspected source. Traceability identifiers supplied by the
project baseline, not statements of proprietary numerical equivalence:

- Temple: `LNX-REF-PC-32466-C-94bf91612d`.
- Cheekbone: `LNX-REF-PC-32466-C-d24d97d234`.
- Jaw: `LNX-REF-PC-32466-C-3bc7e245b7`.

Subject left means **+head-right** (MediaPipe LEFT, viewer right for a frontal
unmirrored image); subject right means **-head-right**. Do not use display-left
as anatomical identity. Every region has its own left/right values. Positive
temple and jaw expand; positive cheekbone narrows. Negative values reverse each
region's direction. Motion is strictly parallel to the supplied head-right unit
axis; no vertical movement or invented depth/3D projection is introduced.

## Exact boundary

The `lrt_face_contour_abi()` symbol returns uint32 value 1. C `double` maps to Rust
f64, `size_t` to usize and return status to int32. All lengths count double
elements, not bytes. Row-major contiguous arrays:

```c
int32_t lrt_face_contour_controls_v1(
    const double *points, size_t points_len,
    const double *roles, size_t roles_len,
    const double *sides, size_t sides_len,
    const double *frame, size_t frame_len,
    const double *values, size_t values_len,
    size_t count, double *output, size_t output_len);
```

- `points`: N×2 existing source-control coordinates, all finite.
- `roles`: N×3 unitless weights in [0,1], ordered temple, cheekbone, jaw.
- `sides`: N exact +1 or -1 values, relative to the head axis above.
- `frame`: [right_x, right_y, up_x, up_y, center_x, center_y, width]. Both axes
  must be unit and orthogonal within 1e-6; all values finite; width strictly
  positive. Width and points must use the same source coordinate units. Center
  and points are validated metadata, not a license to infer region or side.
- `values`: [temple_left, temple_right, cheekbone_left, cheekbone_right, jaw_left,
  jaw_right], all finite [-1,1].
- `output`: N×2 forward displacements, not destination positions or an inverse
  sampling field. N must be 1..256. All exact lengths must match, including 7 for
  frame and 6 for values. No arrays may be truncated, padded or coerced.

The original local product gain is 0.035×face-width per region at full weight and
amount. At each point, the sum of absolute regional contributions may not exceed
0.08×face-width, even if opposing signed contributions cancel. The final vector
is independently bounded to the same 0.08×width. These gains and limits are
original product policy, not reference-product specifications. Requests outside
the envelope are refused, not clamped or normalized. Neutral values and all-zero
roles produce exact positive-zero displacement. A zero value does not bypass
input, frame, pointer or length validation.

## Safety, ownership and availability

Status 0 is success; 1 invalid ABI/count/length/pointer/alias; 2 nonfinite or
out-of-range input; 3 invalid frame; 4 displacement-budget refusal; 5 contained
Rust panic. Any nonzero status leaves caller output untouched. The implementation
uses fixed 4 KiB stack scratch, validates all points before one final output copy,
and allocates no heap on its production path. Panic containment requires unwind
builds and cannot recover process abort, foreign memory faults or invalid FFI use.

Null, unaligned, byte-range-overflowing pointers and writable overlap with any
input are rejected before creating slices. Read-only inputs may overlap each
other. Range arithmetic cannot prove allocated extents or lifetime: callers must
supply accessible live buffers, keep inputs immutable and output exclusively
writable for the complete call. In particular, non-null invalid memory is not
made safe by length checks. This ABI is private, not a security boundary against
an adversarial in-process caller.

Python `controls(points, roles, sides, frame, values)` accepts exact NumPy native
float64 arrays, rejects all shapes/dtypes before allocating, then takes owned
contiguous read-only snapshots. Noncontiguous arrays are accepted by copying, not
coercion. Caller must not mutate during copying. Returned output is a distinct
owned writable float64 N×2 array, published only after status, finiteness, bound,
lateral-direction and neutral-control checks. There is no Python algorithm
fallback, runtime compilation, model download or silent identity substitution.

`native()` verifies actual library loading, ABI and the versioned control symbol.
`available()` probes the same loader. `face_contour_state.capability()` reports
`face_contour_available` and `face_contour_reason`; this establishes only native
load capability, not usable anatomy or photographic acceptance. A missing core
is an explicit refusal. An entirely neutral host recipe can bypass deformation
at the existing pipeline level; calling this numerical API still requires the
native core.

## State and authored verification

Portable state uses operation `lnx.face_contour.v1` and version 1; only temple,
cheekbone and jaw settings with boolean linked and finite [-1,1] subject-left and
subject-right values are admitted. Relinking preserves unequal amounts. The
next explicit linked adjustment writes both; state checks/preset serialization
never perform hidden linking or carry face IDs, pixels, cached fields or paths.

`tests.rs` and `engine/tests/test_face_contour_native_unrun.py` contain fixtures
for neutral/side/sign/roll/scale behavior, malformed inputs, overflow/alias
rejection, untouched output on failure, snapshot ownership, loader failures,
boundary postchecks and bilateral state transitions. They have not been run.
The explicit packaging recipe is `packaging/build-face-contour.sh`; it is not
invoked by application code and has not been executed here. It builds into a
private temporary sibling and replaces the destination only after success; the
staged source includes the matching C header and project license. Real-image anatomy,
TPS inverse composition, preview/export, history, cancellation, project round
trips and UI acceptance require separate integration and local execution.
