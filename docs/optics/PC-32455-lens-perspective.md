# PC-32455: real lens correction and perspective, implementation handoff

Status: development implementation and shared source integration are written.
Compilation, type checking, product execution and acceptance have NOT run. No model, database,
package or binary was downloaded/installed. Do not mark any control accepted from
this document. Qoder owns local verification; this is development evidence only.

## Baseline and design decisions

Inputs are the user's manual text lines 604–611 and the provided acceptance map,
filtered to `镜头调整` and `透视矫正`. The live official guide confirms distinct
lens and perspective branches, RAW default lens correction, automatic smart /
horizontal / vertical, up to four guide lines with solving on the second release,
manual transforms and ratio-preserving crop locks:
https://www.pixcakeai.com/guide/32455 and the current desktop Wiki
https://wiki.pixcakeai.com/guide/9398.html . The latter identifies `AI透视矫正`
as the enable control for those three modes, not a separately specified fourth
algorithm. It does not require a neural model. Numerical slider limits and
default/reset/composition details are not published there. The ranges and
policies below are explicit LumaRetouch design choices, not claimed PixCake
values or a pixel-equivalence claim.

This is NOT crop/rotation relabeling. Lensfun calculates calibrated distortion and
TCA inverse coordinates and photometric gains; our Rust raster kernel actually
samples original upstream RGB with those coordinates. Manual radial distortion,
linear-light vignette and midpoint are independent operators. Perspective is a
real homography, not canned guessed offsets. Smart analysis is an OpenCV LSD
line detector followed by robust regularized least squares, heuristic evidence
scoring and fold/conditioning rejection. This implementation has no neural
network dependency; that is not a claim about PixCake's undisclosed internals.

## Automatic-perspective enable, reset and review policy

The existing version-1 `perspective.mode` is the sole retained enable state:
`smart`, `horizontal` and `vertical` are enabled; `off` and `guided` are not
automatic. No second hidden enable flag, model or recipe version is introduced.

- New/legacy neutral recipes start `off` with an identity matrix. A valid RAW
  default Lensfun correction is independent and is not disabled by this policy.
- Every enable from `off` or `guided` runs `smart` on the current real
  lens-corrected, pre-perspective pixels. No former mode/matrix is secretly
  restored. Mode buttons are available while automatic correction is on, or as
  explicit retry choices after a failed enable/solve so a failed smart solve
  cannot block a useful single-axis attempt. Failure does not turn on an
  unproved recipe. Selecting a mode performs a new image-evidence solve, never
  a fixed transform.
- Disabling automatic correction clears only its mode, matrix, analysis and
  guide records; lens edits and all seven manual perspective values remain.
- Manual values compose after the solved matrix, as before: solved perspective,
  manual horizontal/vertical projective terms and aspect, center rotation,
  uniform scale, then offsets. Crop-lock framing and final legacy crop remain
  downstream. Manual edits do not change the line-analysis input or its meaning.
- Automatic and guided solves are alternatives. Entering guides replaces the
  automatic solve; the first guide has no solved transform and the second
  release triggers the solve. Enabling automatic clears the guide records.
  Both transitions are disclosed and retain manual values. A dedicated clear
  guides action removes the guided solve without resetting manual values.
- `reset_perspective` replaces only the perspective section with neutral values:
  mode off, identity matrix, no guides/analysis, manual values zero except scale
  100, auxiliary grid off, crop lock on. It preserves the complete lens section,
  including its profile, enabled state, manual edits and crop lock. Source
  binding remains if the retained lens profile requires it. Existing `reset`
  is explicitly labeled as resetting **both** sections, including lens identity.
- Each operation stays in the producer-owned preview draft. Failures keep the
  previous valid draft. Apply consumes the exact reviewed result once and adds
  one undo step; cancel discards unapplied changes. Changing mode or resetting
  does not create a history step until Apply.
- Interactive optical review binds the exact preview ID, result image URI and
  decoded dimensions. All three images must load; the actual result element
  must intersect the viewport by at least 99%, be unclipped by its scroll
  ancestors, pass basic occlusion checks, and remain on a focused visible page
  over two animation frames. A delayed acknowledgement cannot approve a newer
  preview. Merely loading the result below the fold is not presentation proof.
  This does not assert that the user understood or accepted image quality.

The persisted field `analysis.confidence` remains for compatibility; the UI
labels its value a heuristic line-support score out of 100, not a probability.
Guided results display their user-supplied constraints rather than a fictitious
100% success probability. No solver, threshold, dependency or precision path was
changed by this enable/reset correction. Naturalness, strong keystone behavior
and perceptual quality remain unrun/unaccepted, not proved by these controls.
See `AI-PERSPECTIVE-SHARED-HOOKS.md` for the included small shared routing changes.

## Explicit operator order and coordinate contracts

The insertion point is NEW, named `post-manual-liquify-pre-crop-normalized`:

1. Preserve every existing upstream repair / smoothing / fabric / automatic
   deformation / enhancement / global color / local group / studio background /
   recovery operator in its existing code order. This list describes membership,
   not an instruction to reorder those operations.
2. Existing final manual liquify remains after those effects.
3. New optics stage: photometric Lensfun/manual vignette in source-linear RGB;
   composed inverse geometry for perspective, manual distortion, Lensfun
   distortion/TCA; one RGB resampling pass. Lensfun coordinates are float32;
   RGB arithmetic/interpolation is float64 and returns the input floating dtype.
4. Existing final crop/rotation, with export upscale/sharpen placement explicitly
   handled at the global stitch boundary. No old geometry state is renamed.

This deliberately does not claim a physically early camera-correction stage.
Moving optics before old effects would silently change old stored strokes,
regions, control points and recovered pixels. Old project recipes migrate to an
exactly neutral stage, and `apply` / `apply_np` return their original object without
allocation, interpolation, quantization or optional-library loading when neutral.

Source locators, recovery regions and local masks retain their original source
coordinate contracts. They are NOT changed to mean optical-output coordinates.
`OpticsStage.inverse_points` is a green-channel optical-output-to-pre-optics
point lookup for this stage's controls, rejecting blank canvas. It does not invert
upstream automatic/manual deformation and is not a nonlinear brush Jacobian.

When optics is active, manual liquify must use an explicitly labeled PRE-OPTICS
drawable before/after/protection canvas, plus an independently visible READ-ONLY
final optical review. Existing stored vectors remain unchanged. A new optics
signature and document revision must invalidate every manual preview/session
and output-presentation proof. Never show the post-optics result as if it were
the old affine-domain brush canvas. The v2 manual preview contract uses four PNGs, 12 MiB combined data plus 16 KiB metadata, canonical optics identity, and a visible final-review acknowledgement.

## Control-by-control development mapping

All IDs have prefix `PC-32455-C-`. Each row has source implementation and shared hooks,
not acceptance evidence; the linked baseline remains research evidence.

| Suffix | Control | Actual implementation |
|---|---|---|
| df80f90191 | lens adjustment | Separate lens state, producer preview, UI section |
| 8503f7df6c | RAW | Unique real camera/lens/calibration match only; metadata and dependency absence are visible, no guessed success |
| f652e5e464 | non-RAW | Automatic correction default off; manual controls remain available |
| 9fa03b233c | lens correction | Lensfun real per-channel mapping + linear gains; exact DB and algorithm version pinned |
| 7f0e3965e8 | distortion | Independent radial inverse remap, -100..100, not crop |
| e1dc351e67 | lens crop lock | Ratio-preserving global crop zoom with boundary/interior probes and full-map coverage rejection |
| 97e25fa700 | vignette | Linear-light edge gain, -100..100, maximum +/-2 EV |
| 34a1b1823c | midpoint | Radial onset, 0..100; default50, neutral unless vignette is nonzero |
| b75e31f8df | perspective | Separate retained homography/manual parameters and source binding |
| 171eace8b1 | automatic enable | Real parent switch for existing three image-evidence modes; exact baseline routing connected; no neural prerequisite |
| cb1d7f388c | smart | Conservative regularization compromises straightening and stretch; not ML |
| 7a3b74734c | horizontal auto | Fits horizontal-line evidence without vertical-projective degree |
| 744036c8c7 | vertical auto | Fits vertical-line evidence without horizontal-projective degree |
| a2317750e5 | guides | 0..4 editable lines; second pointer release triggers a real solve; endpoint edits/delete/axis choice; no 5th line |
| 2ae6b603af | vertical | Manual projective denominator term, -100..100 |
| 3600bc8b78 | horizontal | Manual projective denominator term, -100..100 |
| 8b5c326b67 | rotation | Actual pixel-aspect-aware within-canvas rotation, +/-45 degrees |
| e7242daf5b | aspect | Reciprocal horizontal/vertical scale, -100..100 |
| a930092c46 | scale | 25..400 percent, default100 |
| 372d7fd6b9 | horizontal offset | Real homography translation, -100..100 |
| f51e766b17 | vertical offset | Real homography translation, -100..100 |
| f6f6b349fd | auxiliary guides | UI result grid only; not baked into RGB |
| 65d14e4b47 | perspective crop lock | Same full-map ratio-preserving crop contract, independently switchable |

Guide input is its own real lens-corrected, uncropped, pre-perspective image. It
is not a CSS warp of the final image. Geometric lens changes require explicitly
turning off auto/guided perspective and re-analyzing/replacing lines, so old line
coordinates are never silently reinterpreted. Failed low-support detection
keeps the last valid draft and never commits a guessed transform. Preview edits
accumulate in a producer-owned draft. Apply publishes one confirmed transaction
and one undo step; closing discards the unapplied draft.

## Precision, full output, tiling and bounded resources

The Rust ABI accepts explicit pointer lengths, finite parameters and dimensions;
max image size is 64 million pixels, dimensions at most65,536. CPU row bands are
at most64 rows / 1,048,576 pixels. Each band uses GLOBAL output positions and can
sample anywhere in the complete upstream raster. An independently warped legacy
tile is incorrect, because geometry may pull pixels across any tile boundary.

Full8 and full16 output therefore assemble original-resolution upstream FLOAT
RGB first, run this one global optical stage, then continue upscale/sharpen/final
geometry/quantization. Full16 never goes through an8-bit tile path; the source is
not replaced with a resized proxy. Neutral export must keep the pre-existing path
exactly. Memory admission is based on the existing visible cgroup-budget helper,
full source/output/gain allocations and bounded temporary grids; missing budget
information fails closed. No fallback reduces bit depth or uses proxy remaps.

Linear gains are applied to source pixels before sampling. Without gain changes,
sampling preserves the existing encoded-RGB operator contract rather than silently
changing the full pipeline's color model. RGB16 source increments remain floating
until the final writer. Automatic analysis may use an explicitly bounded1400px
working image, but exports use the retained normalized solution with a newly
computed full-resolution inverse map, not an enlarged proxy displacement field.

## State, proof, preset and batch contracts

`optics_state` strictly validates all fields, source SHA256/dimensions, profile
identity, calibration branches, matrix, max4 guides and scalar bounds. Project
migration must recursively add neutral `_optics` to every old recipe/history
state, and latest schema must require it. Undo/redo/document switching must retain
this exact state and revalidate source identity and DB/algorithm versions.

The preview and apply protocols use separate session/preview/request identities,
engine generation, document revision and exact rendered-output presentation.
The native host cannot turn a source-capture/locator proof into optics permission.
An uncertain send is queried with its original request, never duplicated.

The connected `lnx.optics_manual.v1` preset/batch scope is explicitly labeled
**manual parameters only**. It copies distortion/vignette/midpoint, manual
perspective/rotation/aspect/scale/offsets and crop/grid settings. Each target keeps
its own camera profile, automatic solve and guides. Changing distortion beneath
a retained automatic/guided solve is rejected, requiring explicit reanalysis on
that target. Profile identities, solved matrices and guides never copy across
photographs. `optics_runtime.transfer` is a lower-level per-target preparation
helper, NOT an exposed automatic batch feature; no connected automatic batch
reanalysis claim is made.

## Shared integration hooks (written, unexecuted)

- `vram.PreviewPipeline`: neutral `optics` stage/reset; `render_stage='optics-input'`
  tap after manual liquify; then apply optics before existing geometry.
- `server`: `_optics` lifecycle/capture/restore/document report/recipe history;
  metadata extraction each source load; RAW default only on NEW imports, never
  on restored projects. Synchronize stage before real frame rendering. A missing retained profile suspends
  the optical stage and all frame consumers fail closed. A new import with absent
  or ambiguous profile stays neutral with visible manual fallback. The optical
  tool has an explicit reset-and-review recovery action, never silent omission. Register
  `optics_preview` read-only and `optics` guarded edit with controller prepare
  before history fence and finish after history receipt. Cancel other stale proofs.
- `project`: current schema v9 after studio v8; neutral recursive migration,
  latest strict validation, source-binding portability discipline.
- `export`: add optics snapshot/spec provenance and full-decode verification;
  force only ACTIVE optical output through original-resolution float stitched
  upstream raster; call `apply_export` globally before final upscale/sharpen/crop.
- Tauri `main/AppState`, engine ready/end/event dispatch, native mutation routing,
  capture lifecycle: register `optics_api`, `optics_host`, `optics_protocol=1`;
  exact receipts and stale proof invalidation parallel existing manual workflow.
- `App` / document type / color tools: `useOpticsWorkflow`, `OpticsPanel`, report
  from producer; editing context includes document revision and pending mutations.
- Manual preview v2: sync current optics strictly; temporarily neutralize only
  runtime `pipe.optics` for before/after/protection, retain candidate manual stage,
  restore real optics for separate `final_review`; restore both stages in finally.
  Add canonical optics signature to session metadata and candidate review. Extend
  Python/native/TS image validation and payload budget consistently. Wait for
  actual visible final review plus editable images to load before presentation ack.
  Do not mutate `_optics`, reuse old optical final as pre-optics baseline, or add
  history merely to render these two views.
- Package builder invokes `packaging/build-optics.sh` explicitly. Runtime never
  compiles, installs or downloads anything.

## Local verification still required (not executed here)

Qoder should verify real straight-edge and camera profiles, EXIF orientations,
missing/ambiguous metadata, source/DB changes, fail-closed evidence scoring, second-line
trigger/max4, crop bounds, every manual control, preview acknowledgement races,
one-step undo, project replay, two simultaneous documents, manual-only portable scopes and explicit per-target
automatic reanalysis, global tile seams, full8/full16, nonzero low-bit16 ramps, cancellation,
resource failure and exact neutral old behavior. Representative RAW+nonRAW images
are required before claiming optical quality. These are acceptance obligations,
not invented pass results or a regression-writing campaign.

## Automatic transfer and runtime follow-up

The previously recorded frozen automatic-transfer implementation gap is now wired
through both transaction controllers and real preset/batch review UI. See
[AUTOMATIC-TRANSFER-HOOKS.md](AUTOMATIC-TRANSFER-HOOKS.md) for full candidate binding,
per-target matching/solver, proof validation, errors and exact undo. No source
profile, guide or solved matrix is copied. This closes the source-wiring gap, not
Qoder's unrun behavioral/quality acceptance.

Normal packaging now produces and carries the actual optical runtime/database
bundle before staging, rather than only shipping optional requirements. See
[INSTALL.md](INSTALL.md) for the independent current official calibration pin,
official compatibility conversion, offline installation, licenses and platform
requirements. No dependency build/install/download was executed in this task.
