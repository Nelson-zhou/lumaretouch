# Versioned white balance and neutral picking

Status: integration design. A standalone Rust scalar candidate now exists in
core/white_balance. Candidate 0c452175 passed seven scalar tests in CI39723480395;
all non-GPU jobs passed, GPU jobs skipped. No production WB
algorithm, project schema or picker is enabled. Legacy rendering must not be changed in place.
Requirement anchor: LNX-REF-PC-32455-C-b220a0c332; see action-eyedropper-plan.md.

## Proven legacy issues and compatibility boundary

`ops/exposure.py` constructs XYZ whites, applies Bradford and its inverse, then
uses XYZ-channel ratios as though they were linear RGB gains. The inverse and
forward matrices cancel at zero tint; nonorthogonality does not change that fact.
An explicit XYZ-to-working-RGB conversion is missing. Independent daylight
coefficients also differ from the standard CIE D approximation: the low branch
uses -4.6048 instead of -4.6070, and the high branch uses -3.1558 instead of -2.0064
with t=1000/T. Correcting only the colour basis would leave the second defect.

Freeze existing code, operation order and accepted/rejected domains as a named
legacy algorithm. Old projects/presets must retain those exact pixels, including
existing coefficient behavior. Existing positive temperature shift means a cooler
result; do not silently reverse that convention.

This stage receives encoded sRGB after RAW camera processing and upstream retouch.
It is not sensor-space RAW white balance and cannot recover already clipped RAW
headroom. Default6500 K is a tuning reference, not a claim about EXIF illumination.

## Proposed corrected scalar algorithm

Provisional ID: linear-srgb-d-white-ratio-v1. Freeze the identifier only after
independent golden/domain tests. Use explicit pinned linear-sRGB↔XYZ matrices,
correct CIE D polynomial branches, and the existing dimensionless tint calibration
in Bradford coordinates. Transform the tinted white back to XYZ and then linear
sRGB before forming normalized white ratios. Preserve current ratio orientation
and the 0.1 tint calibration; the latter is a product choice, not a physical law.

At zero manual shifts, both whites are identically evaluated, yielding exactly
unit gains. Preserve the whole-stage inactive bypass so transfer-function roundoff
cannot alter a neutral image. Require finite positive whites/gains before mutation.
The corrected daylight domain is4000–25000 K for both reference and shifted white;
default6500±2000 K lies inside it. Full slider-domain positivity is not yet verified.
A full Bradford chromatic-adaptation matrix would be a different algorithm, not
something to claim for this diagonal ratio method.

For a neutral picker, decode individual wb-input samples before averaging, apply
manual gains but exclude EV and previous picked gains, then let k be the sample's
linear-sRGB Y. Replace picked multipliers with k/q per channel. This preserves
sample Y by design; it differs from green-normalized community pickers. Never
accumulate old picks or invent equivalent Kelvin/tint for arbitrary RGB gains.
Darkness/clipping/gain/coverage thresholds need a versioned explicit sample policy
and representative validation. No threshold is accepted by this plan alone. Geometry resampling and nonlinear
sRGB decoding do not commute: the action protocol must explicitly specify whether
linearization precedes projection. Prefer projecting the linear stage before
aggregation for a physical linear-domain sample; do not claim this is equivalent
to decoding already interpolated encoded samples. This scalar candidate accepts a
linear mean only and does not settle capture/projection provenance.

## One WB operation, not two overlapping scopes

Keep lnx.white_balance.v1 as the sole transferable WB operation. Add a reviewed
structured `options` parameter through registry-extensions, leaving frozen P0
source untouched. Existing temperature_shift/tint_shift remain the only manual
values. Live state keeps `_exposure` and `_exposure_ref_k`; add `_wb_options` with
version, algorithm and picked_gains only. Do not duplicate reference/manual owners.

The transfer options additionally contain explicit reference_k. An adapter combines
live options/reference when saving and splits them atomically when applying. New
params_of emits complete options even for legacy-mode documents. Scope state_fields
must cover all three owners; EV-only transfers must leave WB/reference/picks alone.

A missing options field in an old preset is distinct from a new-photo default:
- Keep existing missing-scalar neutral behavior.
- Select legacy algorithm and reset picked gains to identity.
- Preserve the target reference, matching current old-preset semantics.
Explicit options must be complete; null, unknown versions/algorithms, booleans,
coercible strings and nonfinite numbers reject before mutation.

Implement an early WB-specific branch in check_params, before generic default
filling. Preserve ordinary key omission through every repeated validation/JSON
round trip; test membership, not `.get()`. No non-JSON sentinel or null default is
needed. A complete registry neutral object (legacy algorithm, identity picks,
reference6500) is valid when explicitly supplied, but is NOT the migration value
for an omitted field. Add a structured-neutral registry agreement test and update
the blanket missing-parameter-reset docstring for this deliberate exception.

This keeps all-module scopes valid without advertising two competing WB modules.
Old readers already reject the new unknown preset parameter instead of silently
applying a partial WB preset.

## Project migration and explicit UX

The old project loader filters unknown state fields and records a generic note.
Adding options under unchanged lrt.project.v1 would therefore drop the correction
without refusing the project, potentially rendering different pixels. Introduce
a v2 writer and a v1/v2 reader, validating a complete candidate before mutation.
Missing v1 options migrate to explicit legacy state; save as v2 with a compatibility
notice. Old apps then reject v2 instead of recolouring it. A min_reader hint alone
is insufficient because old readers do not enforce it.

New photos may default to corrected WB only after its validation gates pass.
Opening an old project or adjusting its sliders never automatically upgrades it.
Provide a distinct undoable 'use corrected WB' action; do not claim pixel-preserving
conversion. A picker can use legacy manual gains without switching algorithms.
Reset WB zeros manual/picked correction while retaining algorithm/reference.

## Module boundaries and required regression evidence

Pure Rust owns corrected scalar validation/matrices/daylight/gain/picker math;
retain the old Python numerical implementation for legacy exactness until separately
proven equivalent. Existing NumPy/Torch vector application consumes one gain vector.
Python adapters own migration/state/transfer, not a duplicate mutable WB model.

Cover initialization/fresh state, DOC_FIELDS/capture/replay, history, session and
project reattachment, both export snapshot constructors, ExportSpec and frozen
batch. Picked-only correction must activate rendering with otherwise-zero exposure.
Reattachment failures must propagate to rollback, not clear the exposure layer.

Independent evidence must include: frozen legacy gains/pixels; CIE D anchors and
7000±epsilon behavior; exact selected matrix/white convention; ratio direction;
full-domain finite/positive checks; mean-after-decode discriminator; replacement
and identity picks; source geometry/coverage/provenance fences; old/new project
round trips and downgrade rejection; old-preset target-reference semantics; one
WB scope/all-module saves; EV isolation; frozen batch conflicts and one-step undo;
preview/CPU/GPU/export parity. Explicitly update both snapshot constructors,
export layer activation and both master16 passthrough predicates so picked-only
WB can never export the unedited source. GUI and photographic acceptance remain separate.

## Source basis

- [W3C CSS Color4 conversion code](https://www.w3.org/TR/2026/CRD-css-color-4-20261020/#color-conversion-code):
  explicit transfer functions and linear-sRGB/XYZ matrices, distinct from adaptation.
- [ICC Bradford construction](https://www.color.org/chadtag/): actual adaptation
  matrix and D65→D50 reference, not a claim this proposed method is a full CAT.
- [Colour CIE D implementation](https://colour.readthedocs.io/en/latest/_modules/colour/temperature/cie_d.html):
  daylight polynomial branches/domain and independently documented examples.
- [darktable white balance](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/white-balance/):
  coefficients may not have corresponding temperature/tint. Its source uses
  explicit parameter migration and green-normalized picker coefficients.
- [RawTherapee colortemp source](https://github.com/RawTherapee/RawTherapee/blob/b2ee504c47e5e6d5e054395aa12bf1fe43bd1c3c/rtengine/colortemp.cc):
  explicit XYZ-to-RGB and daylight/blackbody distinction. Its pipeline is not
  assumed identical to this application's already-decoded sRGB adjustment stage.

Pin upstream commits before adapting code/goldens; preserve license/author notices.

Pinned code reference: darktable release5.2.1 resolves to
[be9171cf](https://github.com/darktable-org/darktable/blob/be9171cf8bb2feab8bd115efd9b96a4ce7103039/src/iop/temperature.c),
blob059186c971fa17fffd7d7b60b854d3cd891c2773. RawTherapee dev at lookup resolves to
b2ee504c47e5e6d5e054395aa12bf1fe43bd1c3c, blobf8a4b60b2a375d3702dd766a0cc8630e17799b72.
These are exact tree/file pins, not claims of last-modifying commits.

Project validation nuance: current envelope validation does not validate all curve
recipe semantics; check_curves in _apply_state rejects unsupported known curve
versions before live field assignment. The project workspace can already have
been replaced earlier. Do not describe the existing whole project-open operation
as globally transactional merely because that later curve check is safe.
