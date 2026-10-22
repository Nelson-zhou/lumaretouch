# Parametric curves: implementation contract and status

Status: mathematical core and headless binary adapter under development, **not a
usable product feature yet**. Native schema/editor, engine vector evaluation,
project/preset/frozen batch/export integration and verification are still pending.
Existing point curves remain; this stage must not replace them.

## Requirement and upstream evidence

Product-guide mapping PC-32455-C-5dec857e40 / LNX-REF-PC-32455-C-5dec857e40
references https://www.pixcakeai.com/guide/32455 : highlights, lights, darks,
shadows, with slider and direct curve adjustment. Its proprietary arithmetic and
numeric ranges are not disclosed here. Three adjustable region splits are a
mature-workflow addition, not a claim about the PixelCake requirement.
COLOR-001 covers ICC, not this feature's acceptance.

The parametric basis adapts RawTherapee 5.12 (GPL-3.0-or-later):
- https://raw.githubusercontent.com/RawTherapee/RawTherapee/5.12/rtengine/curves.h
- https://raw.githubusercontent.com/RawTherapee/RawTherapee/5.12/rtengine/diagonalcurves.cc
- https://raw.githubusercontent.com/RawTherapee/RawTherapee/5.12/rtgui/diagonalcurveeditorsubgroup.cc
- https://raw.githubusercontent.com/RawTherapee/RawTherapee/5.12/LICENSE

Retain source attribution in core/curves/parametric.rs and distributed NOTICE.
This is not a bit-exact RawTherapee/Lightroom pipeline claim. Our port uses
log-domain evaluation rather than an upstream intermediate logarithm floor.

## Frozen arithmetic proposal

- Algorithm: lrt-rt512-parametric-splitgrid-lut-v1; display-encoded sRGB stage.
- Values in shadows/darks/lights/highlights order: finite [-100,100], default 0.
- Splits: [.25,.5,.75]; each of four regions at least .01. Validation tolerates
  8*binary64 epsilon in gap comparisons, solely for decimal boundary roundoff.
- Stage disabled or all zero: exact original-value/array/tensor bypass, regardless
  of split positions. Overall curves disabled bypasses all curves stages.
- Identity continuation outside [0,1]; fixed endpoints 0/1. Not an HDR mapper,
  no promise of derivative continuity at endpoints.
- Rust owns the shape, fixed 65537-entry f32 LUT, scalar reference, native preview
  and drag inversion. NumPy/Torch evaluate this table; no second curve algorithm.
- LUT grid split-aligned-4x16384: 16384 equal-width intervals in each of the four
  tone regions, linear-in-x interpolation. 257 UI samples use that same lookup
  rule; no JavaScript spline. Inverse drag is restricted to the matching region midpoint (not arbitrary x).
  It alters one parameter, clamps unreachable
  targets, and reports actual output. A flat attainable range preserves the value.
- Dedicated LUT cache at most 16 immutable entries, separate from point-cache256;
  upload only after recipe/device changes, not every frame.
- Headless input: `parametric enabled shadows darks lights highlights s c h`.
  Existing point/luminance/levels commands retain their existing protocols.
- Binary output: exactly 262188 bytes. 40-byte header: LPC1, u16LE version1,
  u16LE header-size40, u32LE count65537, u32LE gridID1, three f64LE splits;
  f32LE payload. Consumers verify exact requested splits, grid ID, sizes, header,
  finite/monotone samples. No alternative grid is silently accepted.
  No external table is trusted as a validated recipe.

## Integration still required

Recipe v3 retains every v2 field and adds explicit parametric parameters. v1/v2
remain unchanged. Point interpolation/boundary metadata applies only to points;
parametric metadata declares its own rule. Unknown versions/fields/algorithms and
invalid values reject atomically. Negotiate v3 capability, never silently ignore.
Order: exposure/WB -> levels -> parametric -> master -> RGB -> linear Y -> HSL.
Preserve operation ID lnx.curves.v1, history/request/document identity, final-command
barriers, full-recipe cancellation, project/preset/batch snapshots and shared export.
Nonneutral parametric curves must disable the unedited-original export fast path.

Editor pages: parameter and point editing, not exclusive rendering modes. Four
sliders/numeric entries/reset, vertical curve handles, three split handles/reset,
independent parametric enable/reset plus existing global enable/reset. Action
photo eyedroppers and live/full-resolution histograms remain separate open work.

## Acceptance gates, not claimed results

Exact neutral/disabled identity; old recipe parity; invalid schema atomic rejection;
reference-basis comparison; finite monotone extreme splits/controls; dense midpoint
LUT error <=2e-6 (improve representation if it fails, do not quietly lower the gate);
NumPy/Torch parity; cache bounds/immutability; correct v3 project/preset/frozen batch
and export behavior; native drag/numeric/slider equality and request-race handling.
GUI/real-photo 16-bit gradient/skin/performance/hardware checks remain deferred,
not removed. Root does static edits; Qoder/CI execute checks. Preserve failures.

Static review correction before first publication: a uniform 65536-interval grid
could exceed the 2e-6 gate at the first dark interval with all controls +100 and
splits [.01,.02,.03]. The proposal now concentrates 16384 intervals in each tone
region. Default splits retain the original uniform lattice. Actual dense error
must still be measured by Qoder/CI; static reasoning is not a passed test.
