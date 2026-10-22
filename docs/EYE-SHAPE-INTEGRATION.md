# PC-32466 eye geometry v1: implementation and open acceptance gates

Status: source implementation, not photographic or runtime acceptance. No tests,
compilers, application execution, inference, model downloads or installation were
run by this implementation task. Existing tests are preserved. Newly authored
contracts must be executed by the authorized local verification owner.

## Requirements and factual source

Cross-checked the supplied product manual (face reshape and separate eye-enhance
sections) and AI development package `功能需求验收映射.json`. The immutable
baseline remains unchanged. Its eleven relevant entries remain research entries;
adding executable source is not a retrospective acceptance result.

Current official guide checked 2026-10-22:
https://wiki.pixcakeai.com/guide/9405.html, eye section lines 205–260.
It identifies ten controls and supports unlocking left/right for every one.
In particular eye height changes the upper/lower-lid separation, whereas eye
position moves the eye vertically. Positive tilt lifts the outer corner and
lowers the inner corner. None of these is PC-32470 eye enhancement.

Family: `PC-32466-C-9069cc8f2c`. All suffixes below use `PC-32466-C-`.

| Key | Label | Control suffix | Positive parameter geometry |
| --- | --- | --- | --- |
| size | 整体大小 | 350a901827 | Expand whole existing eye around its center |
| iris_size | 眼瞳大小 | a40648c2c9 | Enlarge existing visible iris inside the opening |
| height | 眼高 | c39023ab15 | Increase vertical aperture distance |
| width | 眼宽 | 02e379c464 | Increase horizontal eye span |
| spacing | 眼距 | 4aa3486419 | Move selected eye away from the head centerline |
| inner_corner | 内眼角 | 59bdc2ef4c | Extend the inner corner, localized falloff |
| outer_corner | 外眼角 | 6f1eb8b201 | Extend the outer corner, localized falloff |
| lower_lid | 眼睑下至 | b2458f8502 | Lower the lower-lid contour, retain upper lid |
| tilt | 倾斜 | 89afddb33a | Lift outer corner and lower inner corner |
| position | 位置 | 37e5823f58 | Translate eye upward along head-local axis |

These are projected 2D edits of existing pixels. They do not reconstruct depth,
create unseen sclera/iris/lashes, or make a closed eye truly open. Iris means the
visible iris region rather than an independently segmented pupil. Strong yaw,
closed/narrow openings, clipping, degeneration, poor contrast and known
occluders are conservative refusals. The pixel evidence is not a complete
occlusion, spectacles, reflection or anatomical segmentation model.

## Our policy, not commercial numeric specifications

Recipe version 1 contains exactly the ten bilateral objects, each with boolean
`linked` and finite `left`/`right` in [-1,1]. UI is [-100,100], neutral zero.
Left/right refer to the subject. Relinking only changes the flag; unequal values
persist until the next intentional linked adjustment. Reset/link operations are
whole-recipe intents, including while an earlier gesture is pending.

The original Rust ABI defines these maximum single-control coefficients: 12%
whole-eye scale; 15% iris-region scale; 20% vertical and 16% horizontal stretch;
7% of eye width for spacing; 8% width for either corner; 16% opening height for
lower lid; 0.12 head-local shear for tilt; 8% width upward translation. Combined
control displacement above 30% width is refused. These are conservative local
product choices, not values from the official guide. Geometry/photometric limits
are likewise local policy and require tuning only with honest photo acceptance.

## Topology, evidence and protection

Use the repository's verified MediaPipe 1.1.1 478-point topology: complete
16-point lid contours plus iris center and four-point iris ring for each side.
The original 8-point `big_eye` implementation is not reused as ten fake controls.

Head-local outward and up axes are constructed from the selected real mesh.
Per-side and per-control evidence requires original RGB, complete known-occluder
provenance, local usable pixel counts and contrast in the required opening/lid/
corner regions. Geometry may veto visibility but cannot establish it alone.
Iris resize requires the full iris ring to be observable and its moved ring to
remain inside the moved opening. Partially hidden iris is deliberately refused.

New geometry is calculated in Rust. Python owns orchestration, source-pixel
admission and the existing NumPy/TPS solver rather than introducing a numerical
library. Solve inverse-map controls at target=source+delta. Retain border,
brow, nose and lip anchors, compact support, duplicate/conflicting-anchor checks,
finite checks, conservative Jacobian sampling, and requested-control residual
checks. Protect the inactive opposite eye; never zero out the target eye itself.
Iris-only edits taper within the eye opening rather than changing its lid or
surrounding skin. Jacobian probes are admission heuristics, not mathematical
proof of global injectivity between probes.

## One geometry grid, one image sample

For existing automatic A, brow B, nose N and eye E pullbacks, use
`E(N(B(A(x))))`. Each field is evaluated at the actual off-grid output of the
preceding field. No naive sum of independently evaluated fields and no serial
RGB warps. Neutral eye delegates exactly to the prior geometry path.

Preview and full-size RGB8/RGB16 exports use the same resulting map for RGB,
source-bound local grades, recovery masks, sclera/iris/teeth supports and
under-eye deltas. Picker readiness includes the eye version in the final-grid
cache key. Export builds against original dimensions before tiling, measures the
actual total displacement component peak, and feeds it into the existing halo
allocator. Oversized halos and memory budgets refuse rather than truncate or
silently reduce source resolution. Existing optics/display-proof paths remain.

## Explicit old-project compatibility

Existing `deform.big_eye` values are neither reset nor translated. With a neutral
new recipe, old automatic deformation renders through its unchanged original
path. A nonzero legacy size is visibly reported in the new family. New overall
size refuses coexistence with legacy size on command, rendering, scoped transfer
and export paths; the other nine operations may coexist as distinct operations.

The visible button intentionally sets the existing legacy amount to zero using
its existing selected-person/scope command and undo history. It explicitly says
appearance changes and is reversible. Users compare that preview before choosing
a new size. This is not a lossless migration and does not estimate equivalent
new values. Existing face presets that attempt to reintroduce legacy size while
new size is active are refused and rolled back. No PC-32470 enhancement amount
or semantic mapping is changed.

## State, transport and packaging

`_eye_shape` plus selected-face identity participate in snapshots, undo/redo,
parking, reload, project validation and export snapshots. Derived fields and
visibility facts never enter portable recipes. The real versioned scope is
`lnx.eye_shape.v1`, registered only in `docs/p0/registry-extensions.json`.
Presets and batches transfer only parameters and recompute target anatomy,
source-pixel evidence and the full-resolution field, including frozen reviews.

UI uses the existing shared `browShape/latestIntent.ts` owner: one in-flight
request and latest full intent, explicit gesture IDs, document/face ownership,
acknowledged post-history recipe/revision and CAS base, no edit resends after an
uncertain result. Native `ReceiptHost` owns correlated bounded result mailboxes
and engine-epoch ownership. Read-only status queries do not invalidate picker
captures. A refusal supplies authoritative prior recipe/revision and structured
per-control facts; rollback failure is explicitly outcome-unknown. Panel collapse
does not destroy pending ownership. Slow continuous drag is one history step,
not a stream of timer-coalesced edits.

`packaging/build-eye-shape.sh` explicitly builds `liblrt_eye_shape.so`; staging
ships source, integration documentation and existing license notices. There is
no runtime compilation or silent Python algorithm fallback. Missing native core
is reported visibly and edits refuse; protocol availability is not evidence of
an installed or validated binary. No new model or unrelated colour code added.

## Required local verification, all still unrun here

1. Build/test Rust ABI, native host and UI; run engine and UI contracts plus
   retained regression suites. Check actual package contents and missing/invalid
   ABI failures. Source parsing is not a substitute for these gates.
2. For every control, both signs and each independent side, use real open-eye
   portraits, roll, mild yaw, glasses/reflection, occlusion, closed/low-resolution
   eyes, uneven illumination and iris partially hidden by lids. Confirm honest
   refusal rather than invented texture or a falsely successful no-op.
3. Check distinct size/iris/height/width/corner/lower-lid/tilt/position effects;
   protect opposite eye, nose, brow and lips on fine grids and real photos.
4. Compare old-project neutral output exactly; exercise intentional legacy clear,
   undo/redo, conflicting old face presets and restoration across projects.
5. Rapid drags over two seconds, numeric edits, queued unlock/relink/reset,
   collapsed panel, face/source changes, stale base, engine restart, lost reply,
   query-only reconciliation and rollback failure must not lose confirmed work.
6. Full-source RGB8/RGB16, multiple tile sizes and seams, actual displacement
   halo, mask/recovery/eye-tooth support alignment, under-eye effects, local grades,
   picker position, optics and display-proof parity need end-to-end checks.
7. Target-recomputed presets/batches, closed-eye/occluded targets, many faces,
   memory refusal, parked photos, source replacement and project redo histories.

None of these runtime or photographic gates is marked passed by this document.
