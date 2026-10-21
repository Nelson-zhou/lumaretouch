# Rust point-curve compiler (integration in progress)

This is the shared mathematical core for desktop and headless recipe replay.
RGB/master point-curve code is wired into the application; integrated regression
verification is in progress. Do not count the full handbook curves requirements
as complete: native UI acceptance and the explicitly missing modes below remain.

- Rust standard library only; no new runtime package or third-party source copied.
- Shape-preserving PCHIP derivatives, normalized interval coefficients, 2–64 points.
- Fixed endpoint x coordinates, editable endpoint y, minimum x spacing 1e-5.
- Intentional nonmonotone curves supported; no interpolating overshoot per interval.
- Endpoint tangent extrapolation; exact identity bypass also outside [0,1].
- Display-referred sRGB encoded-value RGB/master curves. This does not claim the
  existing exposure/HSL pipeline preserves HDR values, or imply Lab L* processing. Recipe v2 adds the explicit luminance mode described below.
- The headless adapter compiles one bounded control-point request into a small JSON
  coefficient bundle. It does not load photos, open a network connection, or accept
  filesystem paths. Never trust externally supplied coefficients as validated recipes.

Algorithm references (independent implementation):
https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html
https://doi.org/10.1137/0905021

Tests: `rustc --edition=2021 --test core/curves/curve.rs -o /tmp/lrt-curves-test`
then `/tmp/lrt-curves-test`. CI also compiles and checks the headless adapter.

Engine adapter status: the Python wrapper validates full control-point recipes,
invokes the packaged Rust compiler with bounded stdin (no shell), caches immutable
coefficients, and only evaluates them on NumPy/Torch. Resident pipelines now have
an independent curves stage between exposure and HSL; it is identity by default.
The binary is built by packaging/build-curve-compiler.sh into staging; headless
source-tree development must run that build script once with the existing Rust
compiler. It adds no download or startup compilation.

Application wiring (awaiting integrated verification): the versioned control-point
recipe now participates in document state, history gesture IDs, project restore,
module presets/batch sync, and both active/per-document export snapshots. Nonneutral
curves block the 16-bit original passthrough fast path. The original frozen registry
is untouched; `docs/p0/registry-extensions.json` records the RGB/master extension
and is checked alongside it. Tauri validates points with this Rust core and returns
samples from the same compiler for the SVG editor, not a separate browser spline.

The point editor supports channel selection, add/move/delete, numeric coordinates,
keyboard adjustment, enable/reset, final-command barriers and pointer cancellation.
Parametric curves, eyedropper and input histogram remain unimplemented;
those controls are not represented as complete. Native UI visual/interaction QA
is still outstanding. Added protocol and 16-bit export tests require the real Torch
runtime, not only frontend compilation or the pure-Rust mathematical tests.

UI reconciliation uses a bounded request UUID and an authoritative `curves_result`
receipt, including failures. Repeating identical error text cannot leave a fake
pending edit; JSON object-key order does not determine recipe equality. The
application's whole-image sync choice includes the curves module. Dense legal
nodes preserve x when editing y. Regression helpers cover these cases; desktop
pointer/keyboard/screenshot acceptance remains pending.

## Recipe v2 luminance channel (candidate)

The unchanged RGB/master/per-channel sequence is followed by an optional
linear-sRGB relative-luminance Y curve. Decode the extended sRGB transfer function,
compute Y using the sRGB/D65 primary matrix weights, apply the same Rust-compiled
PCHIP curve, scale linear channels by target Y / input Y, then encode. This is not
Lab L*, and preservation of linear RGB ratios does not guarantee perceptual hue
or saturation after downstream clipping.

For extended-domain stability, define n=max(0,-min(linear RGB)) and
D=max(Y,1e-7)+n, then output channel c + (target-Y)*(1+(c-Y)/D).
Ordinary nonnegative RGB with Y>=1e-7 gives the exact ratio formulation
mathematically; near-black and negative values use this continuous regularization.
It avoids discontinuous switches at zero/channel sign changes and cancellation
amplification. Black lifts neutrally and target=Y is unchanged mathematically.
This is our explicitly versioned rule, not claimed to match darktable bitwise.

Negative and HDR finite values use signed extended transfer functions and
endpoint extrapolation; this operation adds no clipping and does not promise
ratio preservation in the regularized region. Arbitrary floating-point extremes
may overflow and are not a supported image range. Identity skips conversion
exactly. Old v1 recipes retain their exact previous behavior; v2 requires its
explicit luminance_space tag.

Rust owns PCHIP compilation, native schema validation, and a scalar colour
reference. Existing NumPy/Torch vector paths evaluate pixels, including on GPU;
the scalar reference is not described as the production GPU pixel backend.
`curve-compiler` additionally accepts a bounded `luminance` reference-vector mode
for cross-language tests. No full images are serialized through that mode.

References, independently implemented:
- https://docs.darktable.org/usermanual/4.6/en/module-reference/processing-modules/tone-curve/
- https://raw.githubusercontent.com/darktable-org/darktable/master/src/iop/rgblevels.c
- https://www.w3.org/TR/css-color-4/#color-conversion-code

Required checks: v1 parity, v2 identity/domain rejection, black/negative/HDR Rust
reference parity, NumPy/Torch equivalence, state/module propagation, and RGB16
shared export. Deep real-photo/GPU/GUI optimization remains deferred; passing
this channel's checks must not be reported as the entire professional colour
workstation (levels, histogram, parametric curve, eyedroppers) being complete.
