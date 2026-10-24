# Original waist-length ABI 1

Status: authored source and fixtures, **UNRUN**. No compiler, native load,
numerical test, inference, product execution or visual acceptance was performed.
GPL-3.0-or-later; original project implementation, no third-party dependency.

The distributor artifact is `engine/src/lumaretouch_engine/bin/liblrt_waist_length.so`.
`lrt_waist_length_abi()` returns 1. `build.sh` is an explicit packaging artifact,
not a runtime build path. There is no Python geometry fallback and no import of
the separately versioned upper-body length binary.

## Prepare

`lrt_waist_length_prepare(points, points_len, amounts, amounts_len, support,
support_len, width, height, out, out_len)` returns an integer status.

- Exactly 165 f64 observations: 33 actual Body33 rows, each x/y/z/visibility/presence.
- Exactly one f64 amount in [-1,1]: negative shorter, positive longer.
- Exactly 26 normalized original-source support values, in this order:
  - 0–5: outer_left, inner_left, inner_right, outer_right, upper_zero, upper_plateau.
  - 6–9: complete head/hair box x0/y0/x1/y1.
  - 10–13: complete anatomical left arm/hand box x0/y0/x1/y1.
  - 14–17: complete anatomical right arm/hand box x0/y0/x1/y1.
  - 18–19: waist_upper_left x/y.
  - 20–21: waist_upper_right x/y.
  - 22–23: waist_lower_left x/y.
  - 24–25: waist_lower_right x/y.
- Waist left/right refers to source/screen x ordering, NOT inferred anatomical
  side. All four actual visible waist endpoints must have been explicitly marked
  on and reviewed against this exact original. Pose hips are not waist endpoints.
- Source width and height are integral f64 in [2,1000000]. Scale normalized x by
  width−1 and y by height−1. Never pass crop or display dimensions.
- Exactly 11 output f64: x0, x1, x2, x3, upper_zero_y, upper_plateau_y,
  upper_waist_level U, lower_waist_level P, signed_forward_dy,
  source_width, source_height. Here U=max(upper marker ys), P=min(lower marker ys).

The immutable prepared state describes one continuous field, not a raster grid.
Preparation checks real landmarks 0 through 24, reviewed boxes, pose posture,
manual marker ordering/enclosure, support/image domain and sufficient derivative
bounds. No marker is derived, snapped, repaired or attenuated. The host must
separately enforce source/BodyRef/observation hashes, associated face ownership
and evidence, explicit manual-mark provenance, actual waist visibility, complete
upper-trunk contour review and all confirmation flags. Numeric plausibility alone
cannot establish anatomy or review.

## Describe

`lrt_waist_length_describe(state, state_len, out, out_len)` requires 11 input
and 16 output f64. Output order:

1. Support rectangle x0/y0/x1/y1 (four).
2. Rigid upper plateau rectangle x0/y0/x1/y1 (four).
3. Maximum displacement, global displacement-gradient bound, lower and upper
   forward Jacobian determinant bounds (four).
4. Signed head/upper-trunk translation y, marked upper-waist U, marked lower-waist
   P, inverse residual tolerance (four).

These are conservative source-derived pixel facts, not measured runtime or
image-quality evidence. The mathematical support image is the same rectangle.
A host may enlarge the foreign-person guard envelope, never shrink these facts.
State/fact layouts resemble upper-body length but their endpoint semantics are
distinct. Do not mix their operation IDs, binaries, states or supports.

## Evaluate

`lrt_waist_length_evaluate(state, state_len, xy, xy_len, count, out, out_len,
jac, jac_len)` requires state_len=11, xy_len=out_len=2×count, jac_len=count and
count≤1048576. Fractional points are allowed inside the closed source image.
It returns delta=destination−inverse_source and the inverse Jacobian determinant.
Horizontal delta is exactly zero. The common host samples destination−delta;
this kernel does not own or sample RGB, faces, masks or landmark pixels.

All buffers must be live, aligned, appropriately sized and mutually disjoint.
Null, lengths, address overflow, alignment and overlapping ranges are checked
before Rust slices are created; live-allocation validity remains the caller's
unsafe C obligation. The bridge snapshots inputs and uses private output buffers.
Inputs cannot be concurrently mutated. Production kernel paths have no allocations,
callbacks or unbounded iteration. Admission checks every inverse before writing
either output, so refusals leave both outputs untouched under that contract.

Codes: 0 success; 1 malformed input/state/buffer; 2 amount outside [-1,1]; 4 hidden
or cropped required actual Body33 point; 5 unsupported posture/marker placement,
size, orientation or enclosure; 6 support/contour/derivative/displacement budget;
8 image-domain refusal; 9 inverse residual or determinant-bound failure.
No error silently clips, attenuates, guesses waist geometry or drops the operation.

All authored fixtures remain UNRUN; the ABI source has not been compiled or loaded.
