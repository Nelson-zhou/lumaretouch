# Leg inverse field ABI v1

Original GPL-3.0-or-later Rust. Source-only, NOT compiled or tested in this tranche.
See `docs/leg-shape/README.md` for requirements, policies, limitations and licensing.

- `lrt_leg_shape_abi() -> 1`.
- `lrt_leg_shape_prepare(points, values, support, width, height, out) -> status`.
  Inputs are f64: 33 actual points × `(x,y,z,visibility,presence)`, two amounts
  `(thigh,calf)`, four segments × seven reviewed support values (three negative
  contour half-widths, three positive half-widths, radius), all widths normalized
  by the source short side. Output is four × seven f64 values `(ax,ay,ux,uy,L,R,a)`.
- `lrt_leg_shape_evaluate(state, xy, count, delta, jacobian) -> status` evaluates
  actual off-grid inverse coordinates. `delta=q-p`, not p. `count <= 1048576`.
- Status: 1 invalid shape/state, 2 amount range, 3 scale, 4 visibility/crop,
  5 extreme/ambiguous pose, 6 reviewed support budget, 7 opposite-leg overlap,
  8 cropped support, 9 inverse determinant gate. Refusal never clamps amounts.

The caller owns and bounds valid non-aliasing buffers. Python checks exact shapes
and finite values before FFI; Rust checks again. Rust never samples or generates
RGB. Native state is immutable after prepare. The separate shared body geometry
owns shoulders/legs/face composition and all image/support/recovery sampling.
No native binary or model is included. `packaging/build-leg-shape.sh` is an explicit
distributor build recipe and has not been run. Authored Rust `#[test]` cases cover
inverse sign, exact neutral/boundary identity, analytical Jacobian consistency and
off-grid composition; they are not photographic acceptance evidence.
