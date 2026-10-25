# Neck fine-wrinkle correction: requirement, provenance and isolated design

Status: **DESIGN ONLY / NOT IMPLEMENTED / ALL EXECUTION AND PHOTO ACCEPTANCE UNRUN**.
Research date: 2026-10-25. This document is the only file authored in this slice.
It does not close the handbook leaf, enable a control, or claim PixCake parity.

## 1. Exact missing requirement

`docs/development/handbook-traceability.json` contains:

- ID: `control:PC-32464:19`.
- Parent: `refine:PC-32464`; source child index: 18.
- Title: `面部祛瑕疵/祛颈纹`.
- Status on inspection: `pending_independent_verification`.
- Implementation and verification arrays: empty.

The [official PixCake page](https://www.pixcakeai.com/guide/32464), opened on
2026-10-25 and dated 2026-09-17, describes removing fine lines or wrinkles from
neck skin. It does not disclose a numerical slider scale, a neck measurement
model, a texture metric, or an algorithm. Its placement under facial blemishes
does not make neck pixels part of a face-oval mask. Do not alias this leaf to
facial wrinkles, neck length/width, generic smoothing, or source-patch repair.

The bounded first implementation proposed here is **manual-assisted,
source-measured neck fine-line softening**. The region and protected anatomy are
reviewed independently; deterministic line measurement supplies the correction.
It is not automatic AI neck detection, hidden-neck reconstruction or a claim that
every wrinkle disappears. No demographic restriction is established by this leaf;
do not copy collarbone's category restrictions into it.

## 2. Primary-source and licence findings

All upstream references in this section name the same immutable RapidRetouch
revision: `5e9d9c1d2770ff29d11a3879e5a90aad5887e028`.

1. [eyes.py](https://github.com/crispin81/RapidRetouch/blob/5e9d9c1d2770ff29d11a3879e5a90aad5887e028/engine/src/rapidretouch_engine/tools/eyes.py),
   blob `5e743fc551fb284815675252735d10ca8fc2bbbc`, was read through the
   read-only GitHub connector after web retrieval of that file failed.
   `_line_strength` measures positive Hessian curvature across a dark valley,
   suppresses similarly curved round features, and maximizes over scales.
   `_wrinkle_lift` combines morphological closing depth, line support,
   pore-scale-smoothed depth, fold attenuation and dark-strand rejection.
   `_relight` converts the measured lightness increment to linear-light gain,
   then additionally blends surrounding chroma. These are actual algorithms,
   not a generic blur relabelled as wrinkle removal.
2. [skin.py](https://github.com/crispin81/RapidRetouch/blob/5e9d9c1d2770ff29d11a3879e5a90aad5887e028/engine/src/rapidretouch_engine/tools/skin.py),
   blob `c23391ec338417cc79387c73c5e90adf54d0f6a4`, contains an actual
   `_neck_lines` consumer, approximately lines 1210–1217. It calls the same
   wrinkle and relight primitives with `NECK_LINES=((.02,.035,.055), .4)`
   in estimated eye-width units. This is useful numerical precedent, not an
   acceptable ownership implementation for this application. Its `body_regions`
   locates neck bands from chin/face-width offsets and assigns skin to the
   nearest chin. Its body processing uses a reduced working face-width target
   (`BODY_WORK_FW=400`). **Do not copy these contour, owner or reduced-grid
   assumptions.** No source from skin.py is vendored by this document.
3. [filters.py](https://github.com/crispin81/RapidRetouch/blob/5e9d9c1d2770ff29d11a3879e5a90aad5887e028/engine/src/rapidretouch_engine/tools/filters.py),
   blob `b3fd98ffb2324989c8c9ea800e3aff239e97f8db`, uses resize-based wide
   Gaussian filtering when sigma exceeds 8. `masked_blur` can expand its search
   to 64 times the starting sigma. Neither may silently stand in for a finite,
   source-grid, neck-owned sampling contract.
4. [colour.py](https://github.com/crispin81/RapidRetouch/blob/5e9d9c1d2770ff29d11a3879e5a90aad5887e028/engine/src/rapidretouch_engine/tools/colour.py),
   blob `52725cdcbce8d0fac0b1286285c3c59beececc1d`, supplies the ordinary
   piecewise sRGB/linear transfer functions. Local adapted transfer helpers
   remove the upstream row dispatcher but retain the attribution.
5. [README licence statement](https://github.com/crispin81/RapidRetouch/blob/5e9d9c1d2770ff29d11a3879e5a90aad5887e028/README.md)
   explicitly identifies Chris Cork and AGPL-3.0-only. The pinned
   [engine metadata](https://github.com/crispin81/RapidRetouch/blob/5e9d9c1d2770ff29d11a3879e5a90aad5887e028/engine/pyproject.toml)
   independently declares `AGPL-3.0-only`; its blob is
   `e36105b3784f86d13853d7f0b952854ae27ee303`.
   The [full licence](https://github.com/crispin81/RapidRetouch/blob/5e9d9c1d2770ff29d11a3879e5a90aad5887e028/LICENSE)
   was also inspected. The licence text alone is not the evidence for the
   “only” identifier; the explicit upstream declarations supply that evidence.

Existing local derivatives are `third_party/rapidretouch/under_eye.py`,
`eye_filters.py`, `eye_colour.py`, `facial_wrinkle_layer.py` and
`facial_wrinkle_geometry.py`. Their SPDX headers, `UNDER_EYE_NOTICE`, root
`NOTICE`, and archived full licence already record the pinned reuse. Preserve
them. A neck-specific derivative must retain AGPL-3.0-only, Chris Cork's
attribution, exact upstream paths/pin, modification notes and corresponding
source. An independently written integration module must not be used to
relicense the derivative. Existing combined-work/source-distribution obligations
continue; this design is not a new legal clearance or proprietary relicensing.

Inspected local SHA-256 values, before this design was authored:

| Relative to engine/src/lumaretouch_engine/ | SHA-256 |
| --- | --- |
| third_party/rapidretouch/under_eye.py | 1f9f953b70c759c94bcc605962c9de5be0ab0e0c2956c86f065b9d74620359da |
| third_party/rapidretouch/eye_filters.py | 301df54e56a1329a09756807e28cc8f32ed72e8919e9643f366b90fc8ba38964 |
| third_party/rapidretouch/eye_colour.py | b4793783066a05388ef47c5b8b9684a7820d942b5b40fbdc25b45e4851e70757 |
| third_party/rapidretouch/UNDER_EYE_NOTICE | 495466ac1c5105d95e53a4a7134ec9b54d90e2f915b266e2101c6611739958af |
| third_party/rapidretouch/LICENSE | 0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0 |
| facial_wrinkle_layer.py | e2e22f37b7e49d8e25fb875d4e351cfb1fd6cece9811bb0d37b2457af6260e76 |
| facial_wrinkle_geometry.py | ea9a4330493785c611f251266ebf8d583b7bda558a18aa974936f0d618f411f3 |

These local derivatives are not byte-identical upstream files. Git blob IDs and
local SHA-256 values have different purposes and must not be interchanged.

## 3. Existing boundaries to reuse, not bypass

- `facial_wrinkle_geometry.geometry` deliberately intersects the actual face
  oval. `FacialWrinkleLayer.bounds` derives a face ROI. Neither owns a neck.
  Keep existing facial and under-eye behavior byte-for-byte unchanged.
- `neck_shape_state` owns reviewed deformation geometry, a complete head/hair
  transport plateau and geometric transitions. A length/width review does not
  authorize neck texture edits, sampling or structural-shadow removal.
- `skin_colour_body_support` already binds an operation-specific descriptor to
  one FaceRef, an explicitly associated BodyRef, measured pose digest, actual
  body-skin observation, source dimensions and association revisions. Its
  manual region intersects the named `body_skin` plane, not merged face skin.
  Other retained faces are vetoes, and other people's reviewed body areas cause
  refusal rather than sorted-owner pixel theft.
- `skin_colour_body_host` stages source/support/amount privately and publishes
  through the existing people/history receipt owner only after a real rendered
  comparison is presented and confirmed. Extend its explicit family dispatch
  through an independent neck adapter, not by accepting arbitrary family names.
- `collarbone_layer` demonstrates a source-measured radiometric LocalEffect,
  outside the geometry kernel. Reuse that separation, not its anatomy or age/
  gender eligibility. Its ordinary preview input may be a smaller pipeline grid:
  copying its call signature alone does **not** establish full-source analysis.
- `creative_derived_source`, the canonical export resolver, and the existing
  derived repair/source proofs distinguish actual returned pixels from physical
  original provenance. A matching original pathname is not a derived input.

## 4. Proposed stable module interfaces

Names and serialized contracts below are proposed interfaces for coordinated
implementation, not already registered APIs.

### Portable intent

`neck_wrinkle_state.py` owns:

- `OP = 'lnx.neck_wrinkle.v1'`.
- `CONTROL_ID = 'control:PC-32464:19'`; do not invent a second handbook ID.
- `neutral() -> {'version': 1, 'amount': 0.0}`.
- `check(recipe)`, `active(recipe)` and `portable(recipe)`; reject unknown keys,
  booleans-as-numbers, nonfinite values and amount outside [0,1].

Amount is the only transferable parameter. Default zero is exactly neutral and
must not resolve support, require a model/native backend, or allocate an effect.
The slider scale is local product policy, not a copied PixCake numerical range.

### Independent neck support

`neck_wrinkle_support.py` owns `FAMILY='neck_wrinkle'`,
`KIND='neck_wrinkle_visibility'` and `check_neck_review(value, source=...)`.
The existing canonical people support bank stores its immutable descriptor.
There is no second person, project, undo or body-pose operation bank.

Extend the body-skin review shape only for this family with a `neck` field:

```text
review = {
  body_ref, points_sha256, recipe,
  visible: true, unoccluded: true, ownership_confirmed: true,
  neck: {
    version: 1,
    domain: 'source-normalized',
    line_half_width: finite positive fraction of the canonical short side,
    protect_recipe: independently reviewed manual brush stack,
    protections_reviewed: true,
    visible_neck_skin_reviewed: true
  }
}
```

`recipe` marks the actual visible neck skin and admissible nearby context.
`protect_recipe` marks jewelry, clothing/collars, hair, beard, tattoos/skin marks,
hands, other people, Adam's-apple/neck tendon edges, jaw/collarbone structural
shadows and any unwanted line. It is a separate veto, never an opacity decrease
that a later add stroke can undo. Empty protection is allowed only with an
explicit reviewed-none confirmation expressed by `protections_reviewed`; it is
not evidence that the scene contains no occluders. A dedicated UI must explain
that statement and display the final admitted region, not just the drawn brush.

The named body-skin observation and existing known-occluder field remain
mandatory. They are not instance segmentation or a jewelry detector. An old
neck-shape, collarbone, generic body-skin or face-wrinkle review cannot authorize
this descriptor. Pose/face observations establish identity and can disprove
ownership; neither can create a contour, crease trace, scale or positive mask.
Do not initialize the review with inferred chin/shoulder geometry.

### Measurement and application

The preferred numerical implementation is an explicitly **AGPL-3.0-only Rust
derivative** in `core/neck_wrinkle/`, translating the pinned line/depth method
while making full-grid kernels, owned sampling and bounds explicit. It must not
be called original GPL code merely because the language changes. Original
integration code stays separate. `neck_wrinkle_native.py` owns the ABI boundary;
`neck_wrinkle_measure.py` is the narrow checked adapter, with no Python numerical
fallback. Proposed entry point:

```text
measure(full_source_rgb_f32, admitted_weight_f32, hard_protect_bool,
        *, line_half_width_px, byte_budget, cancelled)
    -> immutable PreparedNeckField(window_yxhw, log_gain_f32, facts)
```

It accepts full canonical-grid pixels and masks only. It does not load files,
choose a person, invent a source proof, change graph state or run inference.
All arrays are finite, correctly shaped and owned; opaque SDR working-sRGB is
required. Alpha/HDR and inadequate context refuse, never flatten or clamp.

`neck_wrinkle_layer.prepare(ref, analysis, recipe, *, people_state, body_assets,
body_bank, full_source, byte_budget, cancelled=None)` resolves the distinct neck
review, validates ownership, requests the actual canonical/repaired full source
from an engine-owned resolver, rasterizes the reviewed vectors at those exact
dimensions, and returns a `LocalEffect` at stage `neck_wrinkle` with immutable
`log_gain` and the checked amount. `full_source` is a trusted internal resolver,
not a UI pathname, arbitrary array plus SHA, or public boolean claiming that a
proxy has been verified. Its exact adapter must reuse the current canonical
source owner rather than minting another authority.

`neck_wrinkle_composition.apply_np/apply_t` apply a source-owned scalar field to
actual current-stage linear RGB with one common per-pixel gain, constrained by
current headroom. Full-resolution export slices the already solved field using
the true expanded-tile origin. Display may downsample the completed full-source
result; no proxy-measured field is enlarged into an export. Any lower-resolution
interactive approximation must be separately labelled and may not authorize
final review, cache reuse, or full-size output. Prefer one full-source result
for initial preview/review instead of introducing such an approximation.

## 5. Bounded numerical adaptation

The first implementation should retain the upstream *method*, but not blindly
call the current `_wrinkle_lift`/`_relight` chain and claim stronger guarantees.

1. Measure L* from the immutable effective source stage, including verified
   repair replay, before portrait light/colour/smoothing and before common
   body/face geometry. No sequential feed-back from corrected neck pixels.
2. Use three source-grid Gaussian/Hessian scales derived from the user's
   observed fine-line half-width, not eye, face or shoulder dimensions. A
   proposed initial policy is sigma ratios (.5,.75,1) and maximum half-width
   1.4..12 canonical pixels, ensuring the smallest sigma is at least .7.
   These bounds require numerical/photo evaluation and are not vendor settings.
3. Adapt Hessian anisotropy and morphological closing depth from the pinned
   helpers, retaining smooth line weights, pore-scale depth smoothing, dark-line
   rejection and conservative broad-fold attenuation. Initial local policy may
   retain at least 60% of deep-fold proposal depth and cap lift at 6 L* units.
   These are caps on the measured proposal, not proof of retained physical depth.
   No broad frequency-band skin blur is substituted for line measurement.
4. Use finite explicit full-grid filter kernels. Gaussian radius is
   `ceil(3*sigma)`; morphology and maximum-filter radii must be explicit. Account
   for both stages of morphological closing and the two finite-difference
   gradient passes. A dependency-radius calculation accompanies the implementation.
   For the first conservative implementation, apply only where the entire
   composed sampling footprint lies in admitted owned skin, outside every
   protection and inside the source. Erode by the complete composed radius,
   not merely the largest individual radius. This can refuse narrow/occluded
   neck regions; that is preferable to sampling necklaces or inventing context.
   Merely multiplying the final result by a mask is insufficient.
5. Do not reuse unbounded/adaptively enlarged `masked_blur` for neck chroma.
   Initially omit chroma borrowing entirely. Convert measured positive L* lift
   into bounded scalar log-light gain and apply that gain to current linear RGB.
   A conservative proposed maximum is 1.25x. Current per-pixel headroom uses a
   common scalar, not independent RGB clipping. No donor skin is pasted back.
   This preserves current channel ratios under the gain but does not guarantee
   perceptual hue or pore-amplitude invariance after other ordered edits.
6. Protection, zero amount, zero detected signal and zero current headroom are
   exact no-ops. Keep untouched pixels out of colour-space round trips. No-lines
   with valid support is an honest `no_detected_wrinkle_lines` result, distinct
   from absent/invalid/too-small support. Never report visible correction when
   changed-pixel count is zero.
7. Compose each owned neck once. Refuse overlapping positive regions belonging
   to different people before publication; do not accept the default generic
   sorted-face winner rule. Neck and facial effects remain separate stages,
   with face/neck ownership guards preventing accidental double treatment.

Fine texture is protected by the method's scale/anisotropy decisions and by
avoiding broad image replacement, not guaranteed unchanged. Elongated pores,
thin shadows, necklace chains and hairs can resemble wrinkles. Manual exclusion
and real 100% before/after review remain necessary. Unknown occlusion or a
confidently wrong semantic observation is still a limitation.

## 6. Original/derived source, invalidation and transactional ownership

The canonical full-source packet must bind effective source content and extent,
orientation, working format, exact repair-stage identity and a pixel digest
stamped by its actual resolver. For returned creative images, the physical
original's digest/path remains provenance only. Never decode the original and
label it with the returned asset ID. A newly created layer cannot inherit the
former source's neck descriptor, analysis receipt or measured field.

An immutable measurement cache key includes actual source/repair pixel identity,
FaceRef and analysis evidence, BodyRef and body record/pose digest, both explicit
association revisions, semantic observation and actual input-plane digest,
review/protection content digest, canonical dimensions, scale and backend/version.
Amount-only changes can reuse the full-strength measurement. Repair, mask,
source, identity, association or scale changes cannot. Analysis-model output
resolution remains honestly reported even when its semantic plane is resampled;
resampling is not new full-resolution semantic inference.

Admission is aggregate and before allocation: resident full pixels, any repaired
buffer, analysis/support planes, raster scratch, every admitted neck ROI and
all detector/intermediate fields. Budget refusal must not lower resolution,
truncate people, lower scale or silently retain a prior result. ROI bounds come
from the reviewed source support plus explicit halo, not a facial crop. A 32 MP
ROI ceiling can match existing facial policy but is not a performance promise;
the actual byte budget may refuse a much smaller ROI. Cancel between finite
passes and publish no partial field or graph on cancellation/failure.

New support requires an actual source-bound comparison, exact presented preview
ID and existing graph/document/association/repair fences. A check box without a
rendered candidate is not a review receipt. Stale or uncertain publication uses
the established receipt query/reconciliation path, never blind replay. Neutral
reset, disable, detach and clear remain reachable when analysis/support is stale.

Recovery, if integrated, must be an exact `neck_wrinkle` operator target bound
also to the neck support/BodyRef context. Recovery attenuates only this operator's
light field before the common geometry map, never restores original RGB over
other effects. Existing face-only recovery owner fields alone do not establish
neck ownership. Until that extension is complete, explicitly fence neck recovery.

Projects/history store portable amount and immutable support references in the
existing owners, not cached rasters or another schema fork. Presets/batch may
copy amount only after every target independently supplies its own neck review,
source and person association. Default first-slice policy is to fence shared
cohorts/cross-image transfer and admit only reviewed current-face editing.
Derived-source command and support allowlists must be widened only after the
full source/review/export route exists, not to make an unadapted UI clickable.

## 7. Coordinated integration inventory

Future independent files: `neck_wrinkle_state.py`, `neck_wrinkle_support.py`,
`neck_wrinkle_native.py`, `neck_wrinkle_measure.py`, `neck_wrinkle_layer.py`,
`neck_wrinkle_composition.py`, and thin host/project/UI adapters as needed.

Shared edits require coordination with their owners: people operation/default
registry; strict support-kind/family allowlists; body-skin review/action dispatch;
actual full-source preview/export capture and input forwarding; ordered stage
registry before common deformation; derived admission; immutable history/project
validation; amount-only preset/transfer guards; UI/native receipt transport;
licence/source packaging; exact handbook traceability and diagnostics.

Do not insert this radiometric operation into the neck-shape inverse map or
expand the facial-wrinkle key set to bypass the independent support workflow.
Do not edit the existing RapidRetouch helpers globally: their consumers have
different numerical, cache and licence contracts. A future copied/translated
neck derivative must be clearly attributed even if written in another language.

## 8. Acceptance required before implementation or quality claims

All cases below are requirements, not tests that were run:

- Exact recipe validation; disabled/zero identical output; absent support,
  NaN/Inf, wrong shape, wrong source, stale repair and owner refusal.
- Round pores versus thin valleys; smooth ramp/flat source no false lift;
  isotropic spot, wrinkle crossing pores, narrow shadow and deep-fold limits.
- Alter every protected pixel adversarially: no measured correction outside
  the admitted dependency footprint may change. Check composition leakage and
  missing context at collars, jewelry, hair, hands, source edges and masks.
- Full-source solution equals full-source tile slicing at arbitrary tile origins;
  no tile-local solve, resized measurement or uint8 intermediate. RGB16 source
  precision survives. Display downsampling does not become a solver input.
- Original source and returned creative source have distinct actual inputs;
  original-path reuse, forged array hashes, source-switch history and stale
  candidate receipts refuse. Repair replay matches the captured source stage.
- Two people/touching neck regions, disabled foreign owners, association change,
  reanalysis, missing body skin and insufficient semantic support refuse safely.
- Common-gain headroom, neutral/current-stage behavior, other preceding effects,
  geometry ordering and any independently implemented recovery remain correct.
- New support confirm, cancel, duplicate click, uncertain receipt query,
  undo/redo, save/reopen, detach/reset and amount-only preset behavior.
- Peak memory and cancellation across several ROIs with no budget increase or
  partial publication; optional backend absence has no generic-blur fallback.
- Authorized real-portrait review at 100% and full-size export: fine horizontal
  lines, skin tones, noise, low-key/split lighting, age/expression variation,
  rotated/profile necks, jewelry, beard/stubble, coloured light, makeup, tattoos,
  high collars, hair/contact occlusion and multiple people. Unsupported views
  may refuse. Synthetic arrays cannot establish aesthetic acceptance.

Only source reading, read-only upstream retrieval and file hashing were used for
this research. No product imports/execution, inference, tests, build, typecheck,
model/code download/install, hardware probe, Git or GitHub write occurred.
The design document was written locally; no source implementation or shared
registry was changed. Handbook status must remain pending until a real bounded
implementation and its separately reported verification justify an update.

## 9. Parallel implementation ownership and handoff contracts

The following split can start after coordination releases implementation. No
worker independently edits shared dispatch/registry/history files.

### Numerical-core owner

Own only `core/neck_wrinkle/`, `engine/src/lumaretouch_engine/neck_wrinkle_native.py`,
`neck_wrinkle_measure.py`, isolated numerical fixtures and numerical documentation.
The core README and bundled notice must explicitly identify the AGPL derivative,
Chris Cork, exact upstream paths/pin, and new algorithmic differences. Copying or
translating the line/depth code requires the full upstream licence in the core
source distribution; do not invent an installed runtime or build it in this phase.

Stable Python-facing adapter contract:

```text
ABI = 1
available() -> bool
plan(source_shape_hw, line_half_width_px, candidate_window_yxhw)
    -> {window_yxhw, dependency_radius_px, required_work_bytes,
        retained_bytes, algorithm_version}
measure(source_rgb_f32, admitted_weight_f32, hard_protect_bool,
        *, line_half_width_px, byte_budget, cancelled)
    -> PreparedNeckField
apply(current_rgb_f32, log_gain_f32, *, amount)
    -> new_rgb_f32_or_original_if_noop
```

`PreparedNeckField` has readonly contiguous scalar float32 `log_gain` of shape
window H×W, integer `window_yxhw`, exact `source_shape_hw`, `algorithm_version`,
and JSON-safe `facts`. Required facts: supported/context-rejected/line/changed
pixel counts, maximum proposed lightness lift, maximum log gain, explicit sigma
and dependency radius, no-signal reason, and `runtime_quality_accepted: false`.
`supported_pixels` and `changed_pixels` are different quantities; don't equate
eligible skin with detected or actually changed wrinkles. The adapter exposes
memory planning and cancellation without loading source files or mutating owners.

The ABI must distinguish invalid input, missing context/scale, insufficient
budget, cancellation and numerical failure from successful zero-signal output.
It validates dimensions and checked arithmetic before dereferencing/allocation,
disallows overlapping input/output buffers, does not retain Python pointers,
does not publish partial output, and has no runtime compile/download path.
`available()` only detects an installed compatible library. No generic blur,
legacy Python helper or cached-preview fallback is acceptable. The numerical
owner may design the internal C ABI, but must keep this adapter contract stable
or report a proposed change before touching the support/UI consumer.

### Support/host/UI owner

Own only new `neck_wrinkle_state.py`, `neck_wrinkle_support.py`,
`neck_wrinkle_layer.py`, `neck_wrinkle_composition.py`, thin
`neck_wrinkle_host.py`/`neck_wrinkle_project.py` adapters, a dedicated UI directory
such as `ui/src/features/neckWrinkle/`, and isolated ownership/UI fixtures.
Use the core adapter above, not a duplicate numerical implementation.

The support worker supplies the existing immutable family record pattern plus
the exact neck review schema in section 4. Any required hook into
`skin_colour_body_support` is delivered as a coordinated integration proposal,
not a private alternate bank. The review UI collects a source-bound manual neck
region, independent protected regions, observed line scale, the existing exact
body/person association and explicit visible-neck/protection acknowledgments.
It displays missing evidence and context exclusion honestly. No generated neck
outline, arbitrary raw mask upload or source pathname enters the command.

Proposed four host actions, all under existing people-context envelopes:

- `neck_wrinkle_reference`: empty payload; return actual source-review image,
  exact context/source proof and available explicitly associated BodyRefs.
- `neck_wrinkle_preview`: `{review, amount}`; privately stage exact support,
  measure actual full source, and render before/after through the real pipeline.
- `neck_wrinkle_confirm`: `{preview_id, reviewed: true}`; require the exact
  presented candidate and unchanged capture, then use canonical publication.
- `neck_wrinkle_detach`: empty payload; remove only this pointer, respecting
  current active-intent rules and preserving immutable assets for history.

The UI receives only portable amount, review vectors and verified image/receipt
metadata. Native transport validates bounded JSON and known action/field sets.
Display labels say manual-assisted neck fine-line correction, not automatic AI.
All layout/type/runtime tests remain explicitly UNRUN until separately allowed.

### Parent/integration owner

The integration owner alone edits shared family/operation/stage allowlists,
canonical source-resolver capture, full-source preview/export forwarding,
derived-source admission, receipt/project/history validation, native dispatch,
panel registration, package staging/notices and handbook traceability.
It must verify all call paths use the same support bank and actual source
resolver, including parked candidates and restored histories. Do not publish
an enabled slider while its source/review/export path is still fenced.

The first combined source freeze may describe an authored bounded manual-assisted
slice, with runtime and photo acceptance still UNRUN. It cannot change the
handbook leaf to accepted on the strength of this design, source syntax, mocked
fixtures, or an upstream README listing neck lines.
