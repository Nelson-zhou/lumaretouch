# Rust point-curve compiler (integration in progress)

This is the shared mathematical core for desktop and headless recipe replay.
It does not yet enable a curve tool in LumaRetouch. Do not count it as completed
curves support until pipeline, history, project, presets, batch, export and UI
integration and their regression tests pass.

- Rust standard library only; no new runtime package or third-party source copied.
- Shape-preserving PCHIP derivatives, normalized interval coefficients, 2–64 points.
- Fixed endpoint x coordinates, editable endpoint y, minimum x spacing 1e-5.
- Intentional nonmonotone curves supported; no interpolating overshoot per interval.
- Endpoint tangent extrapolation; exact identity bypass also outside [0,1].
- Display-referred sRGB encoded-value RGB/master curves. This does not claim the
  existing exposure/HSL pipeline preserves HDR values, or implement luminance mode.
- The headless adapter compiles one bounded control-point request into a small JSON
  coefficient bundle. It does not load photos, open a network connection, or accept
  filesystem paths. Never trust externally supplied coefficients as validated recipes.

Algorithm references (independent implementation):
https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html
https://doi.org/10.1137/0905021

Tests: `rustc --edition=2021 --test core/curves/curve.rs -o /tmp/lrt-curves-test`
then `/tmp/lrt-curves-test`. CI also compiles and checks the headless adapter.
Packaging of the adapter and actual consumption by the engine are not yet wired.
