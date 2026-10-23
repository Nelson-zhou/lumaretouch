# Reviewed visible waist inverse field (AUTHORED, UNRUN)

Original GPL-3.0-or-later numerical geometry, not an AI model or commercial
algorithm reproduction. Official PC32473 defines inward waist contour movement;
the 0–1 amount, gain 0.22, nine stations, 1.8 transition factor, visibility and
perspective thresholds here are explicitly original implementation policy.

Actual shoulders 11/12 and hips 23/24 supply only an orientation axis. The user
must measure both visible contours separately and upper/lower axial bounds.
Neither a pose-derived waist radius nor mirroring a missing side is supported.
Loose garments mean visible garment silhouette, never hidden anatomy.

The 25-f64 state is [start x/y, unit axis x/y, reviewed interval length, amount,
falloff factor, nine negative widths, nine positive widths], in exact canonical
source pixels. Evaluation transforms actual off-grid render coordinates into
source pixels, then transforms inverse displacement back using both decoder
scales. This handles ALIGN=8 proxy rounding without mistaking it for new evidence.

The inverse is p=q+n*k*v*(1-v²/R(t)²)³ for 0<t<1 and |v|<R(t), otherwise identity.
k=0.22*amount*64*t³*(1-t)³. R(t) is the independently reviewed side's nine-width
profile with quintic interpolation times 1.8. The analytical determinant is
1+k*(1-z²)²*(1-7*z²), z=v/R(t). Axial variation contributes shear but not another
determinant term. Bounds and support edges are C2 identity transitions. Side
widths remain independent, including when their values differ substantially.

The ABI only returns q-p and determinant, never samples RGB. The registered common
body/face solver owns composition, fold/overlap/budget checks and the single RGB
sampling stage. Background and cloth inside the transition may move. There is no
claim of background preservation or photographic quality acceptance.

Build explicitly via packaging/build-waist-shape.sh only when execution is
permitted. No load-time compiler or Python deformation fallback exists. Rust
fixtures are authored but UNRUN; no build, ABI load or photographic validation
has been performed in this implementation turn.
