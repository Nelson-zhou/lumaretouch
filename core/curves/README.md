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

Engine adapter status: the Python wrapper validates full control-point recipes,
invokes the packaged Rust compiler with bounded stdin (no shell), caches immutable
coefficients, and only evaluates them on NumPy/Torch. Resident pipelines now have
an independent curves stage between exposure and HSL; it is identity by default.
The binary is built by packaging/build-curve-compiler.sh into staging; headless
source-tree development must run that build script once with the existing Rust
compiler. It adds no download or startup compilation.

Still not complete: application protocol, persistence/history, batch/preset/export
state wiring, and the interactive curve editor. Until those are integrated this
is an internal operator, not an available end-user editing tool.

Application wiring (awaiting integrated verification): the versioned control-point
recipe now participates in document state, history gesture IDs, project restore,
module presets/batch sync, and both active/per-document export snapshots. Nonneutral
curves block the 16-bit original passthrough fast path. The original frozen registry
is untouched; `docs/p0/registry-extensions.json` records the RGB/master extension
and is checked alongside it. Tauri validates points with this Rust core and returns
samples from the same compiler for the SVG editor, not a separate browser spline.

The point editor supports channel selection, add/move/delete, numeric coordinates,
keyboard adjustment, enable/reset, final-command barriers and pointer cancellation.
Luminance/parametric curves, eyedropper and input histogram remain unimplemented;
those controls are not represented as complete. Native UI visual/interaction QA
is still outstanding. Added protocol and 16-bit export tests require the real Torch
runtime, not only frontend compilation or the pure-Rust mathematical tests.

UI reconciliation uses a bounded request UUID and an authoritative `curves_result`
receipt, including failures. Repeating identical error text cannot leave a fake
pending edit; JSON object-key order does not determine recipe equality. The
application's whole-image sync choice includes the curves module. Dense legal
nodes preserve x when editing y. Regression helpers cover these cases; desktop
pointer/keyboard/screenshot acceptance remains pending.
