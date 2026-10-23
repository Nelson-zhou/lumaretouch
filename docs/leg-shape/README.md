# PC32473 leg line shaping: integrated source, NOT runtime acceptance

## Exact requirements and evidence

- `LNX-REF-PC-32473-C-6519e4b67b`: 瘦腿, simultaneous thigh/calf editing.
- `LNX-REF-PC-32473-C-2cebb24a12`: 瘦腿/大腿, hip-to-knee line shaping.
- `LNX-REF-PC-32473-C-c63c7afe15`: 瘦腿/小腿, knee-to-ankle line shaping.

Compared with `baseline_probe/manual-text.txt:561–567`,
`baseline_probe/AI开发资料包/功能需求验收映射.json:5205–5249`, and the
PC-32473 entry in `ui/src/spec/refine.json:3658–3683`. The latter explicitly keeps
leg numeric limits, defaults, steps and left/right unlock unknown. `PORTRAIT-008`
is a related module case, not evidence these three controls are implemented or
accepted. The three exact requirement IDs now route to real native/body controls;
source implementation status is separate from local runtime/quality acceptance.

The [official full-body guide](https://wiki.pixcakeai.com/guide/9412.html), read
2026-10-22, distinguishes widening toward the slider's left from narrowing toward
its right, and splits leg line adjustments at the knee. It separately describes
length controls. This tranche changes visible transverse lines only. It does not
implement lengthening, height, waist, hip enlargement, head/body ratio or anatomy
hidden by clothing/occlusion.

Numeric UI -100…100, stored -1…1, zero neutral, synchronous anatomical sides,
maximum inverse gain 0.25, confidence thresholds and support budgets below are
original LumaRetouch implementation policies. They are NOT disclosed PixCake
settings. No left/right lock/unlock was borrowed from shoulder controls.

## Portable intent and explicit source review

The only portable recipe is `{version:1, thigh:number, calf:number}`. Overall is
an atomic set of both amounts, never a third amount added to either deformation.
Unequal thigh/calf values stay unequal until the user actually edits Overall;
opening the panel or looking at its mixed state changes nothing. All defaults
are neutral, with no automatic editing on import or analysis.

This is one operation, `lnx.leg_shape.v1`, inside the shared v2 BodyRef bank.
It does not create a second body bank, face identity, detector-index identity or
inferred person association. Each leg operation has its own enabled state,
recipe, immutable support pointer and review. A shoulder review cannot authorize
legs. All 33 actual measured outputs, source digest/dimensions/orientation,
analysis revision and model provenance remain in the shared measured record.

The [official MediaPipe task guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)
identifies hips 23/24, knees 25/26 and ankles 27/28 within its 33-point output.
These are approximate locations, not measured limb widths. The implementation
uses those actual six joint observations and refuses confidence below 0.8,
cropped required joints, strong foreshortening, sharply bent/crossed legs and
ambiguous source ownership. Manual review never promotes low-confidence points.
It does not reconstruct a hidden skeleton, infer demographics or synthesize pixels.

For each of four visible segments the user measures both visible contour sides
at 25%, 50% and 75% of the actual axis, and explicitly reviews a falloff half-width.
The integrated editor shows a proven unretouched whole-source PNG thumbnail,
waits for its declared actual display dimensions to load, draws true observed
joints through the decoded-to-original pixel-centre correspondence, and permits
direct point selection or original pixel-width entry. It does not claim the
thumbnail contains full-resolution source pixels. Empty measurements stay
empty: no default width is invented from skeleton centres. Pixel widths are stored
as fractions of the original short side, not transferable anatomy coordinates.
The user separately confirms joint visibility, separable legs, lack of strong
foreshortening, body ownership and the neighbouring background inside support.

The contour support envelope is content-addressed and binds operation ID, source,
BodyRef, full pose-point digest and analysis revision. Editing support creates a
new immutable asset; the prior asset is retained for history. The current review
pins that exact asset digest. Reanalysis clears active review/support references
without deleting prior local assets or losing portable amount intent.

A visible trouser outline can be reviewed as a visible material contour. It is
not evidence of the anatomical leg width underneath. A skirt covering the leg
lines, overlapping material, crossed legs or unclear separate ownership is not
made editable by inventing hidden anatomy. This first implementation deliberately
requires the complete six-joint/two-leg review even for a thigh-only or calf-only
amount. Partial-leg review is not claimed. Real-photo supported coverage and
usability must be assessed by qoder, not inferred from these gates.

## Original Rust numeric implementation

`core/leg_shape/lib.rs` is original GPL-3.0-or-later Rust, with an explicit C ABI.
There is no Python numerical fallback, runtime compiler or image sampler.
`leg_shape_native` loads only the distributor-packaged `liblrt_leg_shape.so` and
refuses absent/mismatched native code. `packaging/build-leg-shape.sh` is an authored,
UNRUN distributor build recipe, not automatic installation.

For each segment, let t be the axial coordinate from proximal to distal joint,
v the signed transverse coordinate, R its explicitly reviewed support radius,
and n its unit normal. The inverse source point is:

`p = q + n * (0.25 * amount) * v * 64*t^3*(1-t)^3 * (1-(v/R)^2)^3`

for `0 < t < 1` and `abs(v) < R`, and `p=q` otherwise. The displacement returned
to the existing common sampler is `q-p`, not the source coordinate. Positive
amount samples outward to narrow the visible output; negative amount widens it.
The compact C2 factors reach zero at both endpoints and lateral boundaries. All
six reviewed joint locations remain fixed; no axial length amount exists.

The four internal maps are evaluated at actual off-grid coordinates in frozen
left thigh, right thigh, left calf, right calf order. They are NOT evaluated on a
grid and added independently. Each inverse has an analytical determinant; the
product and the final common image-grid map must also satisfy folding gates.
No request is silently clamped or accepted by lowering the requested amount.
Static determinant bounds do not prove a flattering/natural photographic result.

Additional original safety policies: segment projection at least 32 render pixels
and 5% of image short side; reviewed contour half-width 2 pixels to 40% of segment
length; falloff radius 1.4–2.5 times the widest reviewed half-width and at most 50%
of segment length; approximate z-change no more than 70% of projected length;
thigh/calf axis dot product at least 0.35; length ratio 0.4–2.5. Entire falloff
support must be in-frame. Opposite-leg supports cannot meet, and other actual
joints cannot lie inside a segment's moving support. These conservative rejection
rules can reject apparently usable images; they are not vendor behavior claims.

`LegField` exposes real `evaluate(points)`, `resident_bytes()`, `shape`, measured
`record`, `operation_id`, BodyRef, conservative support disks, displacement bound,
and `input_binding_sha256` over exact current record/recipe/review/support/ownership.
Neutral returns exact identity without allocating/loading native math. Proxy and
original geometry are rebuilt independently; a tiny proxy can be refused rather
than pretending it is verified. Active output requires the exact existing pinned
pose model, not an arbitrary body-record producer.

## Shared geometry, image and recovery transport

`body_pose_render.prepare` calls `leg_shape_adapter`, passing actual leg evaluators
into `shoulder_shape_adapter.prepare_common`. Enabled nonzero leg intent uses
`FrozenBodyOrder(2, ('lnx.shoulder_shape.v1','lnx.leg_shape.v1'))`. With no active
leg, the exact prior v1 shoulder-only order remains. Merely installing a policy,
selecting a body, inserting neutral leg intent or reviewing neutral supports does
not change rendered-canvas geometry identity or invalidate existing colour masks.
Snapshots preserve and verify their meaningful order; old v1 is not relabelled.
Canonical whole-bank digests remain stricter concurrency/cache fences, not the
persisted rendered-canvas geometry identity.

Shared `body_pose_geometry` groups every operation of a BodyRef into ONE
BodyGeometry. It checks exact current field input bindings and complete active
operation coverage, rejects duplicate operations, and evaluates later subfields
at preceding inverse coordinates. Distinct body collision checks include the
conservative prefix-displacement support expansion. The existing body-then-face
inverse chain then reaches the original source coordinates. No duplicate BodyRef
entries, summed sampled arrays, second RGB warp or module-local image resampling
is introduced. Unknown/missing enabled consumers refuse instead of disappearing
from preview/export.

The host replaces the common people geometry and uses its existing shared sampler
once for RGB8/RGB16, semantic/support/recovery masks, recovery deltas and other
local deltas. Full-resolution export reconstructs native leg/shoulder/face fields
at original dimensions from the exact source snapshot; it never enlarges a proxy
correction. Common memory budgets and final per-cell/band-seam Jacobian checks
remain mandatory. There is no claim that neighbouring background is unaffected:
background pixels inside compact support can bend together with visible contours.

## Host, project, history and UI ports

- `leg_shape_host.LegHostAdapter`: real candidate mutation/prepare/publish path,
  strict source/BodyRef/document epoch/revision fences, whole canonical body and
  people graph digests, one request ID/content digest, no eviction into replay,
  and query-only reconciliation after uncertain publication. Required `receipt_get`
  and `receipt_put` ports bind the body host's bounded process-lifetime ledger.
  A claim is stored before publication. Native and document epochs fence a restart;
  this is not a durable cross-process receipt ledger. The existing serialized edit
  transaction and authoritative publication ledger remain the sole live owner. Review/support changes can be
  saved as unapplied intent if other geometry remains unsafe; show the explicitly
  original/unapplied view, never a stale successful edit.
- `HostPorts.prepare` returns actual `PreparedPeople`, retaining face evaluators,
  hair colour/effects, recovery inputs and source-owned support. The canonical
  `_body_publish` stores the same `_body_pose_bank`, fences the document, publishes
  through the existing sampler and records the existing history owner. Its actual
  `last_outcome` pins output pixel/map hashes, dtype/dimensions, frame/revision and
  one common sampling stage. The leg adapter verifies that actual outcome, not a
  second DTO/publication path. A mismatched actual outcome stays unresolved and
  cannot be upgraded by generic lost-notification reconciliation. Preparation alone
  is never reported rendered.
- The v14 project retains the v2 body bank, immutable content-addressed supports
  and existing v13/v12/v11 migration fences. Generic body history decorates the
  existing undo/redo entries, preserving other operations and assets. Leg gestures
  coalesce there, not in a second stack. The operation-local patch guard also
  verifies the canonical people graph and rejects unrelated mutations.
- Cross-photo `transfer_recipe` requires the exact source and target bank hashes,
  current canonical people graph, one explicitly confirmed face for the same
  anonymous person in each photo, and the target's own current leg review/support.
  It copies only thigh/calf amounts. The host must prepare the actual target before
  publishing. No source coordinates, supports, review, masks or model outputs travel.
- `ui/src/legShape` provides the interactive panel, source contour editor, native
  invocation adapter and app-lifetime one-inflight/latest-unsent controller.
  Selection/photo/analysis changes cancel unsent intents; uncertainty is queried,
  not replayed. Model acquisition, real analysis and body-person association reuse
  the existing body workflow via the supplied callback, not a duplicate producer.

### Reachable integration and source correspondence

The native `leg_shape` command/status mailbox routes to engine `leg_shape`, which
uses the canonical body transport with exact outer and inner request identities.
App/RetouchPanel readiness and the exact three requirement IDs open the real leg
workspace. Optional model acquisition, real33 analysis and explicit body/person
association reuse the existing shoulder/body workflow. No arm or other limb policy
is registered. The staged engine explicitly builds and packages the Rust leg ABI.

The review image is honestly a bounded PNG thumbnail of immutable unretouched
whole-source decoder RGB, not a full-resolution original. The host verifies source
stamp/digest and original dimensions, admits full size or decoder ALIGN=8 whole
frame, then declares original, decoded and display dimensions with normalized
full-frame correspondence. The editor verifies the receipt and loaded PNG size,
then maps normalized source coordinates/widths to original pixel centres. Cropped,
retouched, stale-source and fabricated full-resolution receipts are refused. Small
features still need user review; thumbnail availability is not image-quality proof.

Preview preparation uses `people_owned_inputs.preview` with the candidate body
bank, preserving current hair assets/evidence/source path, faces and recovery.
Hair remains before the shared geometric sampler; existing reference/semantic
colour remain late. Original RGB8/16 export keeps all six decode path/stamp gates,
source digest/dimensions, frozen operation order and original-resolution recompute.

## Reused model and licensing

No new model is introduced. Reuse the shoulder tranche's exact MediaPipe Tasks
Pose Landmarker Full float16 revision 1 task bundle, documented with provenance
in `docs/shoulder-shape/README.md` and enforced by `body_pose_manifest.py`:

- URL: https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
- Expected bytes: 9,398,198.
- Expected SHA-256: `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`.

This expected hash is community-published provenance, not a Google-signed checksum
and not proof of a local verified acquisition. The shoulder documentation records
the exact community source revisions. Never substitute `/latest/`, another hash
or a newly self-trusted download. No model bytes were downloaded or executed here.

The exact model's Apache-2.0 release is confirmed by the Google collaborator in
[MediaPipe issue 6306](https://github.com/google-ai-edge/mediapipe/issues/6306)
(June 10, 2026), re-read for this tranche. This is separate from the runtime code
license. Keep the existing `body_pose_licenses/APACHE-2.0.txt` and `NOTICE.txt` and
reviewed runtime/transitive-license packaging. No GHUM/SMPL mesh, proprietary
asset, extra weight, new installer or software dependency is bundled. Existing
host offline enforcement remains required; no claim is made about future SDK
telemetry simply because the model is Apache-licensed.

## Acceptance status and reproducibility

All new Python, TypeScript and Rust tests and all fixture cases are AUTHORED,
UNRUN. Static source/AST/data/hash inspection is the only performed validation.
No product module import/execution, test run, Rust compile, UI typecheck/build,
inference, model download, package install, image quality review, external Codex
run, Git mutation, commit, push or CI run occurred in this worker.

`engine/tests/fixtures/leg_shape/acceptance-cases.json` maps dedicated cases to the
three exact requirement IDs. It includes signed controls, no double application,
real-observation/support provenance, refusals, source/mask alignment, 8/16-bit
export, single sampling, cross-operation composition, history/transfer and UI
race/uncertainty coverage. Synthetic unit fixtures are explicitly not real
photographs or successful detector evidence. Qoder must run the authored tests,
perform real local inference/pixel/UI cases on licensed/user-approved inputs,
record actual byte/model/version/source/output hashes and screenshots, and judge
naturalness/background damage independently. No case is marked passed here.

Qoder's local acceptance starts with the packaged Rust leg/shoulder cores, the
Python contract tests, the four `ui/src/legShape/*.test.ts` files through the
repository's Node type-stripping test runner, then the 35 dedicated real UI/export
cases. These commands and cases have not been executed by this worker. Source
parsing is not a TypeScript typecheck, Rust compilation, native ABI test or quality
acceptance.

`manifest.json` freezes exact owned and shared integration file bytes. It excludes
itself to avoid a recursive hash and does not certify build or photographic quality.
