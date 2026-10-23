# Original length kernel ABI v1 — source only, UNRUN

33 × 5 f64 pose values `(x,y,z,visibility,presence)`, two f64 strengths
`(thigh,calf)`, twelve reviewed support values: left then right, each
`(outer_left,inner_left,inner_right,outer_right,foot_end,support_end)`.
Coordinates are normalized full original source; x boundaries scale by width−1,
y boundaries by height−1. `lrt_leg_length_prepare` writes 26 f64 values.
Each side has `(x0,x1,x2,x3,hip_y,knee_y,ankle_y,foot_end_y,end_y,thigh_dx,thigh_dy,calf_dx,calf_dy)`.
`lrt_leg_length_evaluate` consumes state + Nx2 off-grid destination xy, produces
`delta=destination−inverse_source` and inverse Jacobian determinant. The shared
host samples at `destination−delta`. Maximum band: 1,048,576 points.
Caller must own correctly sized, valid, non-aliasing buffers. No RGB sampling here.

Codes: 1 invalid input/state; 2 amount range; 4 hidden/cropped required joint;
5 unsupported posture/foot/depth; 6 contraction/displacement/support budget;
7 overlapping leg supports; 8 cropped support; 9 inverse/Jacobian refusal.
No runtime compilation or fallback. Explicit distributor build script is UNRUN.
