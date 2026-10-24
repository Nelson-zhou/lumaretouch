# Whole-person width ABI v1

AUTHORED / UNRUN. No compilation, ABI load or numerical execution performed.

Original dependency-free Rust, GPL-3.0-or-later. No new crate/model/asset dependency.

- lrt_body_slim_abi returns 1.
- prepare: actual normalized 33x5 x/y/z/visibility/presence points (165 doubles), one signed amount, support vector (20–260 even doubles), exact integer original width/height, 11-double output state.
- support: collar_box [left, top, right, bottom] followed by 8–128 original-source normalized polygon xy pairs. Polygon must be simple, non-degenerate, without repeated first vertex, and contain every actual body point. The native kernel measures extrema itself, never constructs a silhouette from keypoints.
- state: outer_left, measured_left, measured_right, outer_right, outer_top, measured_top, measured_bottom, outer_bottom, k=-0.08*amount, source_width, source_height. Immutable Python bridge returns state backed by bytes.
- describe: 16 doubles: support box (4), measured plateau box (4), max displacement, analytical gradient bound, forward determinant min/max, whole-person width factor, measured center x, measured whole-person width, inverse residual tolerance.
- evaluate: n xy query points in SOURCE pixels, delta_xy with convention source=destination-delta, and inverse Jacobian determinants. n <= 1,048,576. Y delta is exactly zero.
- codes: 0 accepted; 1 malformed/nonnumeric/buffer/state; 2 amount outside range; 4 missing actual visible/cropped point; 6 invalid contour or support/gradient/displacement budget; 8 source domain; 9 inverse residual/Jacobian. No clipping or strength reduction.
- All pointers must name aligned, live allocations. All input and output ranges must be mutually disjoint; lengths/address arithmetic are checked before Rust slices. This cannot prove caller allocation provenance, which is an unsafe caller obligation. Output buffers are unchanged for any checked refusal, including a late bad query, through a complete admission pass before writing. The bridge copies borrowed inputs before entry.

## Continuous mapping

Let L/R/T/B be the measured full silhouette extrema, c=(L+R)/2, and k=-0.08*a.
Inside the complete measured rectangle, F(x,y)=(c+(1+k)(x-c),y). Therefore every visible part, including head/hair, arms/hands and feet, shares the same width factor 1+k. It is not a waist/leg combination and never resamples pixels independently.

Outside that rectangle, two separable compact quintic windows wx and wy return the horizontal displacement k*(x-c)*wx(x)*wy(y) to exactly zero at the explicit outer collar. The quintic 6t^5-15t^4+10t^3 has derivative bounded by 1.875. The measured silhouette, its internal negative-space background and the bounded collar are the disclosed affected region. All points outside the collar are exactly identity for this subfield.

Let Rmax be the farthest horizontal collar edge from c, mx the smaller horizontal margin, and my the smaller vertical margin. The kernel bounds the displacement gradient norm by abs(k)*hypot(1+1.875*Rmax/mx,1.875*Rmax/my) and refuses values above 0.45. Hence horizontal forward derivative is within [0.55,1.45] and y is fixed: every source row is a strictly increasing, boundary-fixed bijection. Fixed-point inversion uses <=64 iterations, 1e-9 step threshold, 1e-7 source-pixel residual check and an explicit determinant certificate.

Measured width/height must be >=64/128 original pixels. Maximum displacement is <=4096 and <=0.125*min(source dimensions). One source-pixel fixed margin is mandatory. Insufficient collar or unsupported strength is refused, not silently attenuated.

This is mathematical source reasoning, not executed or photographic acceptance. Face/body association and consent are host policies, not claims inferred by this coordinate ABI.
