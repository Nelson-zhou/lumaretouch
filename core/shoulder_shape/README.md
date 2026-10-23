# Shoulder shape Rust ABI 1

Original GPL-3.0-or-later 2D math, no external crate, pose model, mesh, texture or
sampling dependency. See `docs/shoulder-shape/README.md` for source requirements,
licensing, model caveats and all unrun acceptance gates.

- `lrt_shoulder_shape_prepare`: 33 rows of x,y,z,visibility,presence (165 doubles),
  four values [square_left,square_right,width_left,width_right], render width and
  height; writes two [center_x,center_y,radius,dx,dy] lobes (10 doubles).
- `lrt_shoulder_shape_evaluate`: prepared lobes, up to 1,048,576 finite xy pairs;
  writes inverse delta q-source(q) and determinant of source(q). All output is
  derived from actual coordinates, not an interpolated displacement map.
- Anatomical left is MediaPipe 11/13/23, right 12/14/24. Coordinates are normalized
  EXIF-normalized source-frame values. z is only a conservative pose rejection cue.
- Kernel phi = (1-r²)^3 within its disk, zero outside. |grad phi| <= 1.718/radius.
  The forward derivative norm is <= 0.65. Fixed-point inverse tolerance and final
  residual checks reject failure; amounts are never silently weakened.
- Uniform zero recipes are bypassed by the adapter for exact identity without
  requiring native resources. Fixed outside/head/elbow/hip anchors do not move.
- Geometry safety thresholds and bounded amounts are local implementation policy,
  not undisclosed official values. Nearby background deformation is unavoidable.

Explicit build entry: `packaging/build-shoulder-shape.sh`. Authored Rust tests are
not executed in this tranche. No compiler or native library build has been run.
