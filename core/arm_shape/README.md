# Original arm inverse kernel (AUTHORED, UNRUN)

GPL-3.0-or-later, no dependencies. This is original numerical geometry, not a
commercial algorithm reproduction and not a trained deformation network.

The only ABI consumes one source-reviewed segment state and actual off-grid
coordinates. It returns inverse displacement `q - source(q)` and the analytical
inverse determinant. It never consumes or resamples RGB, semantic/recovery masks,
photo paths, raw models or detector outputs. Python performs provenance/admission
and packs the numerical state; Rust owns deformation evaluation.

State has 25 f64 elements: source/render start xy, unit axis xy, visible length,
amount, falloff factor, nine negative-side widths, nine positive-side widths.
The widths are explicit manual source measurements or actual SAM candidate
cross-sections; pose centres cannot supply them. Station positions are 0.1–0.9.

Width interpolation uses quintic smoothstep between measured stations. The inverse
is `p = q + normal * 0.22 * amount * 64t³(1-t)³ * v * (1-v²/R(t)²)³` inside
`0<t<1, |v|<R(t)`, and identity outside. `R(t)` comes from the actual side's
interpolated contour width, multiplied by original local falloff policy 1.8 for
manual or 1.4 for SAM. No sign/default/range is attributed to PixCake.

The axial coordinate is unchanged, so variation of width along the axis introduces
shear but not a missing determinant term. The transverse derivative is computed
analytically. Endpoints and their first/second displacement derivatives vanish.
Both independently reviewed segments therefore meet at an unchanged elbow with
C2 identity end taper, rather than guessing a hidden joint or summing maps.
This taper can leave a less-adjusted zone near joints; do not call it commercial
visual parity. Strong folding/crossing/contact/foreshortening is conservatively
refused by admission. The common whole-body/face geometry still applies its
Jacobian, ownership, budget and overlapping-support checks.

Build only through `packaging/build-arm-shape.sh` when local validation is allowed.
The build script, Rust tests, ABI loading, image rendering and quality checks have
NOT been run. Python never invokes a compiler or falls back to a fake result.
