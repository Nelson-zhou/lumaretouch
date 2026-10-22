# PC-32466 eyebrow geometry v1

Status: source implementation and static inspection only. No product execution,
Rust compilation, build, typecheck, inference, download or photographic test was
performed in this task. This is not photographic acceptance or pixel-parity proof.

## Verified evidence and licensing

- Frozen handbook `baseline_probe/manual-text.txt` lines 514–517 and
  `baseline_probe/AI开发资料包/功能需求验收映射.json`: seven eyebrow geometry
  controls, distinct from eyebrow colouring/makeup assets.
- Original official URL https://www.pixcakeai.com/guide/32466 was inaccessible
  to the research tool. Official replacement guide
  https://wiki.pixcakeai.com/guide/9405.html (read 2026-10-22, eyebrow section)
  verifies thickness, spacing, tilt, shape, position, inner/outer length and
  bilateral unlocking. It does not establish our numeric limits.
- Fixed optional dependency is `engine/requirements-mediapipe.txt`:
  `mediapipe==1.1.1`. Topology verified directly against official source
  https://github.com/google-ai-edge/mediapipe/blob/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py
  `FaceLandmarksConnections` lines 171–221. MediaPipe LEFT means subject left;
  the chain ordering here is inner to outer. The official open-source topology
  is the community implementation evidence, not an invented index list.
- MediaPipe upstream: Copyright 2023 The MediaPipe Authors, Apache License 2.0,
  https://www.apache.org/licenses/LICENSE-2.0 . No upstream solver implementation
  is copied. Packaging includes the archived upstream license with these factual
  topology references. Original Rust geometry and integration are GPL-3.0-or-later
  under the repository license. Existing third-party obligations remain in force.

## Control map and our numeric policy

Each independent control is signed [-1,1], displayed [-100,100], neutral zero.
This is our product policy, not a quoted official range.

| Control | Exact ID suffix (prefix PC-32466-C-) | Positive direction / full amount |
|---|---|---|
| family | a25ee7adaa | Seven independent bilateral parameters |
| thickness | 3a0e5b3aa6 | +50% upper/lower distance from the measured centreline |
| spacing | aef1ac96b6 | Move inward 12% own brow width along head-local lateral |
| tilt | 75f4aab5d9 | Rotate outer end down 12 degrees around own brow centre |
| arch | 5cd2097ba1 | Raise interior by 12% width, exact zero at both endpoints |
| position | 3b36aa8899 | Raise 12% width along head-local up |
| inner_length | b7ff3a0ac6 | Extend inner end 18% width, cubic falloff on inner half only |
| outer_length | 29f403bf68 | Extend outer end 18% width, cubic falloff on outer half only |

Negative values reverse these effects. Combined control requests exceeding 40%
of the brow width reject, rather than clipping silently. Relinking preserves
unequal values. Only the next explicit adjustment sets both sides. Exact recipe
whole-recipe base guards reject stale edits, avoiding delayed right-side edits undoing left-side
values. Ordinary edit receipts/history own the transaction; slider motion does
not prove an effect was applied.

## Geometry, refusal and protection

Only the actual selected MediaPipe 478x3 mesh is accepted. No synthetic, template,
missing or out-of-image fallback. Source pixels plus model-provenance-backed
hair/clothes/background vetoes must support a visible dark eyebrow in each third.
Missing evidence is a side-specific refusal of the transaction (unlock to edit
only a reliable side), not proof that a predicted mesh
contains visible hair. This conservative heuristic can reject blonde/low-contrast
brows; it is NOT complete eyebrow/glasses/occlusion segmentation. Eyelids, iris,
nose bridge and forehead are real zero-displacement anatomical anchors. Eye
interiors and the bridge additionally have hard-zero/feathered protection. Compact
support bounds distant forehead/background movement. TPS control collisions with
conflicting displacements reject before calling the existing deduplicator.

New Rust math produces forward control requests D. The existing TPS solver is
reused at target locations Q=P+D with displacement D, so the brow pullback
B(Q)=Q-D=P hits source points. It reuses existing scale normalization, regularized
solve and evaluation. Compact support uses the same smoothstep definition as
ops/deform.py but at actual off-grid coordinates. Fold-risk probes reject sampled
Jacobian determinants below 0.15; finite probes are not a proof of global
injectivity. Full-grid and real-photo checks remain required.

## One geometric image sampling stage

Order is SOURCE eyebrow geometry, then existing automatic deformation. Original
source landmarks are therefore the correct brow coordinate frame. Existing auto
amounts, controls, dedupe, TPS, compact support and accumulated float32 delta are
unchanged.

A(x)=x-D_auto(x), B(y)=y-D_brow(y).

C(x)=B(A(x)); D_total(x)=D_auto(x)+D_brow(x-D_auto(x)).

This is exact composition of the defined pullbacks, NOT addition of incompatible
forward fields or two image resamplings. Only the existing CPU/Torch sampler sees
the total grid. The existing automatic map is not falsely described as a globally
exact inverse of its forward controls. With brow neutral the exact original auto
delta object and original three-part cache key are retained. With both neutral,
no sampler runs and the original image object is returned.

Source-domain local masks, sky masks and post-geometric eye/under-eye consumers
follow the same total grid. Under-eye delta is sampled as a source-bound field,
not by resampling RGB a second time. Photometric lip/wrinkle stages remain before
geometry and are carried by the one image sample. Full resolution export builds
brow controls from original RGB8/RGB16 and source-normalized landmarks, composes
all displacement before measuring the real total component maximum for tile halo,
and adopts the combined grid even if all old auto amounts are zero. Tile crops
never rebuild anatomy. Requested unavailable sides cause an explicit export error,
not a silently missing effect. No hair, gap filling, assets or generated texture.

## Lifecycle and ownership

- `_brow_shape` is portable intent; `_brow_shape_owner` is the current source mesh
  fingerprint and is saved in document/history/project, never in preset params.
- Switching faces suspends an existing foreign-owner edit rather than silently
  painting another person. Returning to the matching face restores it; resetting
  permits a deliberate new edit on the newly selected face.
- Preview grid invalidates on brow version, automatic geometry and amount changes.
  Source analysis cache keys include selected identity, recipe, source and semantic
  model provenance. Strict command errors roll back recipe and cached field.
- Missing legacy project field means neutral; present null/malformed state and
  active state without ownership reject, including nested undo/redo records.
- `brow_shape_scope` transports parameters only and validates the target's actual
  analysis, then establishes its own owner and recomputes its field during replay.
- Native Rust ABI is explicitly packaged. Missing binary fails visibly. No runtime
  compilation, installation, downloaded model or silent alternate implementation.

## Qoder local acceptance (not run)

Build the native library/package using the ordinary approved local workflow, then
verify each control independently and combined, each subject side, tilted heads,
neutral byte identity, unequal relink/unlock, rapid stale commands, reset,
undo/redo, save/reopen, source face switches and pending-command document switches.
Check compact support, true endpoint moves, eye/iris/bridge preservation, folds,
RGB8/RGB16 original exports, several tile sizes and halo borders. Compare a source
marker transported by the total grid against aligned source masks. Check two
faces, hair/glasses occlusion, missing brows, blonde brows and cropped/side faces.
Test parameter-only preset/batch transfer to different aspect ratios and faces;
no source geometry/identity/mask may cross targets. Missing Rust/semantic support,
refused side, memory admission and export errors must be visible and atomic.

## Transfer admission and local verification handoff

`brow_shape_scope.validate_target` decodes the target's own original RGB16 working
source, verifies dimensions and file stability, recomputes support and geometric
admission, and refuses unavailable sides before any parked target is written.
Frozen batch preflight and commit both run this admission. Preset application does
likewise and requests strict live replay. For a candidate also containing automatic
optics, its existing whole-source candidate render already uses the same full-size
brow export path; the frozen complete-candidate/source proof is reused rather than
decoding/rendering a second time. No field, source photograph, face fingerprint or
source mask is present in the portable parameters. The installed owner fingerprint
is derived from the target's own selected face. The preset bound is 32 modules for
the now-17-entry registry, retaining unique known IDs and existing byte limits.

Added, NOT executed: `engine/tests/test_brow_shape_contract.py`,
`ui/src/browShape/model.test.ts`, and Rust `#[cfg(test)]` contract cases.
They cover bilateral relinking, malformed state, ownership, exact neutral object
reuse, nonconstant composed pullbacks, band consistency, topology and endpoint
falloff. Static Python AST / TypeScript syntax-tree parsing is not a typecheck,
solver execution, native build or photographic validation.

## Corrected continuous-input transaction contract

The original direct Slider→invoke path was unsafe: native ordinary commands are
FIFO, not keyed interactive coalescing; `requested:true` only acknowledges queue
admission. Several range events could use one old recipe as CAS base. The corrected
path has a module-lifetime generic `latestIntent` owner, one in-flight request and
one latest full optimistic recipe. Every input event still contributes to live
previews; it is not release-only. Updater functions operate on the latest intent,
so queued opposite-side edits, unlocking, non-destructive relinking and reset are
not reconstructed from stale React props. Engine CAS/application is now whole
recipe; `control` identifies the interaction, not a partial state merge.

Each operation is bound to document, actual selected-face fingerprint, request ID
and gesture ID. A post-history terminal receipt contains actual recipe, published
frame evidence and monotonic report revision. Only that receipt advances the next
CAS base. Delayed older frame reports cannot overwrite a newer confirmed recipe.
Native status is a bounded, epoch-bound ReceiptHost lookup of the ORIGINAL request
ID. Timeout, failed delivery or missing result keeps the operation uncertain;
querying is allowed, mutation resubmission is not. Source/person changes discard
unsent intent, not the outstanding receipt. Panel collapse does not destroy its
owner. A restarted engine produces unavailable old receipts, not assumed success.

Pointer/keyboard gestures have explicit IDs; history coalesces a continuous drag
independent of render latency, and returning to the exact original state removes
its no-op history entry. Link/reset are separate explicit gestures. While dragging,
slider position reflects desired intent and the working label distinguishes it
from confirmed effect. Added workflow tests are source only, not executed. This
correction does not establish runtime responsiveness or photographic acceptance.
