# Parametric curves: implementation contract and status

Status: mathematical core passed an initial Qoder candidate check. Native schema,
editor, engine vector evaluation and shared recipe wiring are now implemented as
an unverified integration candidate; **do not claim feature completion**. Full
integration checks and physical UI acceptance remain pending.
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

## Integration candidate (verification pending)

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

## Initial core evidence (not integrated-product acceptance)

Remote d77f719ad4ff9c07c7c2fad2c0980bde6d95514e, tree
e76590195745cea04b6eeec105f7a5699c312441. Qoder local 2026-10-22:
9 parametric tests passed (00:57:48–00:58:01 UTC, 13.18s); 10 existing point
core tests passed; main helper compiled. 168 profiles, maximum tested error
9.998432835001125e-7, worst values [-100,100,100,100], splits [.01,.02,.03],
x=.03002960205078125. The 2e-6 gate was not relaxed.
Uniform/nonuniform binary protocols passed; 10 malformed cases returned rc2
and empty stdout. Protocol checks ran 01:03:37–01:03:38 UTC. Candidate and
baseline tracked files stayed clean; no installed app changes.

Evidence limitations: complete binary stdout blobs were checked in memory but
not retained, though byte counts, headers, assertions and sample values were logged.
Steps 2–3 and 4–7 have grouped timestamps, not individual subprocess timestamps.
The protocol verifier accumulated assertions rather than fail-fast; no failures
occurred. Do not describe this as perfect/full raw-output retention.
Subsequent integration changes (local-coordinate lookup, scalar reference mode,
vector wrappers, UI) need their own checks and cannot inherit these passes.

Integration additions: recipe-v3 capability gate; separate native curve API;
version-preserving point editor; parameter/point tabs; four sliders/numeric values,
four native-inverted vertical handles, three split handles/numeric controls;
per-stage/global enable/reset; shared request/receipt lifecycle. Async inverse
solves are bounded; final barriers await the newest solve, cancellation restores
the complete pre-upgrade recipe, and late replies after abort are ignored.
Parameter stage CPU cache is independently bounded to16 immutable tables. Native
scalar references are compared unconditionally against NumPy; Torch checks remain
separate and must run in Qoder's real environment. Render rollback restores the
previous compiled tuple without recompilation/allocation.

Further static-review corrections before integration publication: decoder snapshots
mutable buffers; raw v1 recipe retained separately from editable v2 view for exact
cancel/history restoration; pointer completion belongs to one owning element and
pointer ID, destination focus occurs before gesture start; untouched handle clicks
send no edit. A shared native-call barrier settles active parameter gestures and
waits for final host enqueue before external mutations (including Undo/Redo), while
own curve writes/read-only state queries remain exempt and idle dispatch stays
synchronous. Physical range->graph, graph->range, multi-pointer, window deactivation,
and toolbar history interaction checks remain pending, not inferred from unit tests.
