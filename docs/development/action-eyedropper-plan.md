# Action eyedroppers: requirement and source-stage plan

Status: research/design only. Existing identified RGB/Lab readout is not an action
eyedropper. No controls below are marked implemented by this document.

## Requirement anchors

The supplied AI development mapping has these P1 references (no dedicated
acceptance_case_ids supplied):
- WB: LNX-REF-PC-32455-C-b220a0c332.
- Levels picker family: LNX-REF-PC-32455-C-8ebf8ee682; black:
  LNX-REF-PC-32455-C-58fb48cdf9; white: LNX-REF-PC-32455-C-73ee12d5c4.
- Curve image picker/drag: LNX-REF-PC-32455-C-d30dc5a133.
- HSL image picker/horizontal hue drag: LNX-REF-PC-32455-C-3791959b40.

https://www.pixcakeai.com/guide/32455 requires neutral-region WB picking, RGB
black/white picking, image click-and-drag curve adjustment, and horizontal HSL hue
drag. Selecting a colour band or adding an unmoved point is not full acceptance.
Sampling sizes, sensitivity and cross-band allocation below are product design
choices, not a claim to reproduce an unpublished proprietary algorithm. COLOR-001
is ICC acceptance, not a substitute for these interaction cases.

## Existing foundations and missing contracts

Reuse the capture generation/ticket/document checks, native epoch/SHM instance and
sequence checks, copied/presented acknowledgements, source rectangles and boundary
rejection. Keep the readout panel read-only and add separate action modules.

Current capture is proxy-output only. Existing levels-input/curves-input scope taps
are before crop/rotation, whereas displayed output is after geometry. Screen x/y
must not directly index those tensors. A colour mean after LUT/HSL/curves cannot
be inverted into reliable WB input. Aggregate samples after their required upstream
operations; averaging and nonlinear transforms do not commute.

Required input stages:
- wb-input: before the complete exposure/WB/tone stage.
- levels-input: before levels, then current master levels per sample for RGB pickers.
- curves-master-input: after parametric; channel-input: after parametric+master.
- curves-luminance-input: after parametric+master+RGB, converted to linear Y.
- hsl-input: after all curves, before HSL.

Bind stage/domain plus the exact geometry version, source dimensions, integer crop,
rotation, resize and valid coverage. First use the existing production geometry
helper on the selected stage, then gather the small sample, accounting for temporary
proxy buffers in memory admission. A later sparse inverse implementation must match
that path, including two-stage interpolation and rotation fill, not approximate it.
Reject fill/no-source coverage. If background replacement obscures the upstream
source, an explicitly labelled adjustment-input preview is preferable to secretly
sampling the old background. Do not count temporary disabling of crop/background
as complete feature support.

## Proposed module/API boundaries

- core/color_actions: pure Rust finite sample validation and candidate recipe math;
  bounded versioned scalar/sample protocol, never whole-image IPC.
- engine/color_action_sampling.py: stage and geometry-correct production samples.
- engine/color_action_controller.py: bounded begin/update/commit/cancel sessions,
  baseline recipe, frozen input samples, revision fence, atomic apply/rollback.
- native color_action_host/API: redeem a presented capture into a one-use action
  session; UI cannot submit invented sampled RGB as trusted engine evidence.
- frontend controller/hook/overlay; tool-specific entry points in WB, levels,
  curves and HSL panels. Do not inflate App/server/RetouchPanel orchestration.

begin(capture_id,ticket,generation,point,kind,channel,gesture_id) validates without
writing history. update(action_id,expected_revision,delta), commit and cancel return
request/document/action identities and complete authoritative state. Validate the
session before advancing its own fence. Normal external edits invalidate it;
late updates/cancel cannot overwrite another edit. Release the frozen input canvas
for live result display during drag, but keep frozen samples rather than repeatedly
sampling the changing output. One explicit gesture is one history step.

## Action arithmetic choices

WB: decode each sampled RGB to linear before averaging. Let q be that mean after
current manual WB gains; choose k = linear-sRGB Y(q), then picked gains k/q per
channel. Replace rather than accumulate picked gains. This preserves sampled Y by
design, unlike G-normalized alternatives; disclose that choice. Reject dark/clipped/
invalid samples and excessive gains using explicit reviewed thresholds, not silent
clamping. Preserve manual temperature/tint as independent micro-adjustments; do not
invent an equivalent Kelvin value for arbitrary sampled gains. Test neutrality at
WB output as downstream creative looks may intentionally recolour it.

Levels: in RGB picker mode, run each sample through current master levels, then set
three corresponding single-channel input black/white endpoints together. Preserve
opposite endpoints, gamma and output endpoints. Reject the whole action if any gap
is <1e-5. Explain mapping to current output black/white, not guaranteed final pure
black/white after later grading.

Curves: compute actual selected-channel input in Rust, hold its x and adjust output
from baseline by drag delta. Preserve the complete v3 recipe and other channels.
Adding a point on a PCHIP curve can alter neighboring slopes, so a click with no drag
must not insert a supposedly neutral point. Zero displacement/Esc restores the full
original recipe; define nearest-node reuse, minimum spacing and 64-node admission.

HSL: current production operation uses HSV windows/smoothstep, not a true HSL model;
retain its existing pixel semantics. Readout may show true HSL, but hue action must
reuse production gates/weights. Proposed bounded minimum-change band allocation is
Delta*w/sum(w^2), with active bounds and actual reachable hue reported. Preserve
saturation/value and unweighted bands. Reject near-gray hue samples and use circular
hue arithmetic. This allocation is an original design, not attributed to PixCake.

## Existing WB basis issue: separate versioned repair

Static evidence in ops/exposure.py: rgb_white constructs Bradford*XYZ then solves
Bradford against that result, normalizes it and treats the result as RGB. At tint=0
this algebraically returns XYZ, not working-linear-sRGB. The resulting diagonal
ratios are multiplied directly into RGB. The accompanying inverse/transpose rationale
also needs correction. Neutral identity alone does not validate the colour basis.

Do not silently change existing wb_gains and recolour old projects. Preserve a
frozen legacy algorithm for versionless old state and old white_balance.v1 presets.
A new explicit algorithm should use the working RGB matrix A: a diagonal RGB
approximation obtains white RGB with inverse(A)*XYZ; a full Bradford CAT is
inverse(A)*inverse(B)*diag((B*Wd)/(B*Ws))*B*A. These are distinct choices and must not
share a misleading algorithm identifier.

Before implementation, settle one authoritative representation: retain existing
manual exposure tuple fields as the sole temperature/tint source, and store versioned
WB algorithm/picked-gain options separately, or migrate atomically into a dedicated
stage. Do not maintain two independently editable copies of manual values. Old
load/save must keep exact legacy pixels; switching algorithms is an explicit,
undoable edit. New full-module presets must preserve all WB options and reject
ambiguous simultaneous v1/v2 WB operations. Test the legacy repair and eyedropper
neutralization separately.

## HSL persistence gap and acceptance

The historical HSL persistence gap was closed by `9f35e43e`: lnx.hsl.v1 now
transfers the explicit legacy-hsv8-smoothstep-v1 recipe and 24 bands through
registry, presets, frozen batch, UI scope selection and export. Basic Qoder and
CI evidence is recorded in hsl-scope.md. Integrated preset UI candidate c1afbf7
adds real legacy/correlated CPU protocol coverage. This is not an HSL action
picker or a replacement of the existing HSV pixel semantics.

Acceptance must cover independent requirement IDs, Rust golden/error/identity cases,
nonneutral upstream/downstream stages, v3 curves, arbitrary crop/rotation/resize,
background coverage, stale epoch/sequence/document/revision and late cancellation,
one-step undo/redo, click-without-drag, actual GUI image dragging, save/reopen,
preset import/export, batch subset isolation and CPU/GPU/export parity. Physical
GUI and performance checks remain deferred, not removed.

## Primary/community implementation references

- https://docs.gimp.org/3.0/en/gimp-tool-levels.html
- https://docs.gimp.org/3.0/en/gimp-tool-curves.html
- https://github.com/GNOME/gimp/blob/master/app/operations/gimplevelsconfig.c
- https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/white-balance/
- https://github.com/darktable-org/darktable/blob/master/src/iop/temperature.c
- https://www.w3.org/TR/css-color-4/#color-conversion-code

Pin upstream revisions before adapting source; retain author/SPDX/modification
notices and distributed NOTICE attribution. Do not hand-edit the generated runtime
THIRD_PARTY_NOTICES inventory or claim it was regenerated without executing its
actual generator in the approved testing environment.
