# Original upper-body length ABI 1

Status: authored source and fixtures, **UNRUN**. No compiler, native load,
numerical test, inference, product execution or visual acceptance was performed.
GPL-3.0-or-later; original implementation with no third-party code or dependencies.

The installed artifact is `engine/src/lumaretouch_engine/bin/liblrt_torso_length.so`.
`lrt_torso_length_abi()` returns 1. `build.sh` is an explicit packaging artifact,
not a runtime build path. There is no Python geometry fallback.

## Prepare

`lrt_torso_length_prepare(points, points_len, amounts, amounts_len, support,
support_len, width, height, out, out_len)` returns an integer status.

- Exactly 165 f64 observations: 33 actual Body33 rows, each x/y/z/visibility/presence.
- Exactly one f64 amount in [-1,1]; negative shorter, positive longer.
- Exactly 18 normalized original-source support values: outer_left, inner_left,
  inner_right, outer_right, upper_zero, upper_plateau, followed by complete
  head/hair, anatomical left arm/hand and anatomical right arm/hand boxes.
  Each box is x0/y0/x1/y1. These are reviewed visible bounds, not inferred anatomy.
- Source width and height are integral f64 in [2,1000000]. Scale normalized x by
  width−1 and y by height−1. This API must not receive crop/display dimensions.
- Exactly 11 output f64: x0, x1, x2, x3, upper_zero_y, upper_plateau_y,
  lower_shoulder_y, upper_hip_y, signed_forward_dy, source_width, source_height.

The immutable prepared state contains only a continuous deformation description,
not a displacement grid. Preparation rechecks actual landmarks 0 through 24,
observed head/arm containment, posture, domain and global derivative bounds.
Face ownership/ref/evidence and review confirmations are checked by the source
host, not guessed from these numeric arrays.

## Describe

`lrt_torso_length_describe(state, state_len, out, out_len)` requires 11 input
and 16 output f64. Output order:

1. Support rectangle x0/y0/x1/y1 (four).
2. Rigid upper plateau rectangle x0/y0/x1/y1 (four).
3. Maximum displacement, global displacement-gradient bound, lower and upper
   forward Jacobian determinant bounds (four).
4. Signed head translation y, shoulder level, hip level, inverse residual
   tolerance (four).

These are conservative source-pixel facts, not an aesthetic acceptance result.
The image of the support is the same rectangle. A host may use a larger envelope
for foreign-person guards; it must not make the conservative facts smaller.

## Evaluate

`lrt_torso_length_evaluate(state, state_len, xy, xy_len, count, out, out_len,
jac, jac_len)` requires state_len=11, xy_len=out_len=2×count, jac_len=count and
count≤1048576. Each point may be fractional, but must remain in the closed image
domain. It returns `delta = destination − inverse_source` in `out` and the inverse
Jacobian determinant in `jac`. Horizontal delta is exactly zero. The existing
shared host samples at destination−delta; this core never samples any pixels.

All buffers must be live, appropriately sized, aligned and mutually disjoint.
Address overflow, alignment, null, length and overlapping ranges are checked
before creating Rust slices; live-allocation validity remains the caller's unsafe
C obligation. The bridge snapshots all inputs and uses private output buffers.
No input may be mutated concurrently. No callbacks, allocations or unbounded
iteration exist in production kernel code. Exact size checks precede indexing.
An admission pass checks every inverse before writing either output buffer, so
refusal leaves both outputs untouched under the stated nonmutation contract.

Codes: 0 success; 1 invalid input/state/buffer; 2 amount out of range; 4 hidden
or cropped required real upper-body point; 5 unsupported posture/size/depth;
6 contour/support/derivative/displacement budget; 8 image-domain refusal;
9 inverse residual or determinant certificate failure. No code clips, attenuates,
repairs geometry or silently drops a requested operation.
