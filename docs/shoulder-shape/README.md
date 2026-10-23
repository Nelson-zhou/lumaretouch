# PC32473 shoulder shaping: source-integrated, not runtime accepted

This source tranche connects two genuine automatic-shoulder controls to the
engine, existing common portrait renderer, project/history/export, optional
model acquisition, native routing and App. Manual liquify is not substituted.
No model bytes have been downloaded and no product code has been run here.

- `LNX-REF-PC-32473-C-1b5aae1f25`: 直角肩, visible shoulder-line shaping.
- `LNX-REF-PC-32473-C-57c31b17e1`: 肩膀宽度, narrowing and widening.
- Related module case: `PORTRAIT-008`. This does not imply either sub-control has
  passed that case; the baseline has no completed dedicated acceptance cases.
- Baseline handbook: `baseline_probe/manual-text.txt`, lines 561–567.
- Baseline mapping: `baseline_probe/AI开发资料包/功能需求验收映射.json`, around
  lines 5070–5100. Original mapping source: https://www.pixcakeai.com/guide/32473.
- Reverified official behavior source, 2026-10-22:
  https://wiki.pixcakeai.com/guide/9412.html, sections 直角肩 and 肩膀宽度.

Both controls have anatomical left/right values and independent link switches.
Width is signed: negative narrows and positive widens. Shoulder-line strength is
nonnegative. Relinking preserves unequal existing values; only the next edit
synchronizes the two sides. Local UI ranges are shoulder-line 0–100 and width
-100–100, zero neutral. These ranges, the 6%/8% displacement scales and all safety
thresholds are LumaRetouch implementation policy, NOT official disclosed values.

## Genuine body analysis and provenance

`body_pose_runtime.analyse` calls the actual MediaPipe Tasks PoseLandmarker in
IMAGE mode with verified model bytes passed via `model_asset_buffer`. All 33
actual normalized points retain x/y/z, visibility and presence. Missing scores,
wrong point counts, nonfinite outputs or missing packages refuse. There is no
synthetic fallback, face-box skeleton, fabricated visibility, segmentation-mask
anatomy reconstruction, image generation or texture creation.

Each observation pins source file SHA-256, original source width/height,
`exif_normalized_once`, actual analysis RGB8 byte SHA-256 and dimensions, actual
model-byte SHA-256, backend/version, backend Python source hash, point digest and
a stable random `BodyRef {asset_sha256, body_instance_id, analysis_revision}`.
The backend source hash identifies that file, not the entire runtime distribution.
RGB8 is an analysis-only view. Rendering retains the original RGB8/RGB16 source.

New observations receive new IDs. They never match a face, old body or person by
list position, nearest location or appearance. Explicit reanalysis names the old
BodyRef, keeps the recipe, advances its revision and invalidates prior visibility
review and association. Actual observations, user review and anonymous-person
association are separate state. `face_instance_id` is never populated with a body
ID. A combined face/body edit requires a current, explicit body→anonymous-person
link and that person’s one confirmed face in the photo. Body-only editing can
remain unassociated; it is not silently treated as face editing.

## Model licensing, exact pin, and remaining acquisition boundary

Chosen model is the exact official Full float16 revision 1 task bundle:
https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task

Expected bytes: 9,398,198. Expected SHA-256:
`5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`.
This is an attributable, independently corroborated COMMUNITY-PUBLISHED pin,
not a Google-published/signed checksum and not a locally verified acquisition.
The two exact-version publisher-source records were read as text, not executed:

1. https://github.com/khalid999devs/react-native-pose-detection/blob/c1ff344dd16937f404409326df7242ea92e445b9/packages/core/plugin/src/manifest.ts
2. https://github.com/BotchetDig/workout-gate/blob/c13a65ab1a01e76f33985f754e18b6e254675582/install.sh

The revision-versus-latest explanation is:
https://github.com/khalid999devs/react-native-pose-detection/blob/c1ff344dd16937f404409326df7242ea92e445b9/docs/adr/0004-pin-model-revision-not-latest.md.
The `/latest/` bundle can have different ZIP timestamp bytes. There is no fallback
to latest, mirror, alternate digest or on-the-fly trust of downloaded bytes.

The code license is Apache-2.0:
https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/pose_landmarker.py.
The separate model license is supported by the official model card page 2:
https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf,
and a Google collaborator’s 2026-06-10 response expressly covering the exact
Full float16/1 bundle: https://github.com/google-ai-edge/mediapipe/issues/6306.
These do NOT license additional GHUM/SMPL meshes, weights or topology assets. None
are included or loaded. Local Apache license/attribution text accompanies the
optional asset adapter. The existing reviewed MediaPipe runtime packaging path
and its transitive-license review remain authoritative; this adapter installs no
software and changes no requirements file.

`body_pose_acquisition` reuses the existing optional installer’s bounded byte
verification and cancellation helpers. The adapter performs no network operation during import, status or inference;
the host’s existing offline engine enforcement remains mandatory for third-party
runtime execution. Only a separately invoked optional-acquisition process can download the
exact URL into a staged directory, verify exact size/SHA, copy notices and publish
an atomic installation receipt. It rejects redirects and changed bytes and keeps
existing installations untouched. The native body-pose helper reuses the existing
optional-runtime subprocess pattern with progress/status/cancel, outside the engine
command thread. It never runs pip or falls back to a different system runtime. No model download, software install, inference or local asset verification
has occurred in this tranche. Verified asset bytes still do not imply runtime or
photographic-quality acceptance.

## Visible support and actual safety boundaries

The official model card describes single-person/full-body use and warns about
multi-person images, head visibility, subject scale, pose orientation, light,
motion and occlusion. It can predict hidden points or average positions. Those
outputs are retained as observations but cannot authorize deformation. Depth is
approximate and only a rejection clue, not metric anatomy or a reconstructed mesh.
Current Tasks supports `num_poses`; this is not proof of reliable multi-person
shaping. The UI exposes this distinction rather than labelling all multi-person
photos automatically accepted or blanket unsupported.

A supported edit requires actual visible head, shoulders, elbows and hip anchors
(indices 0,7,8,11,12,13,14,23,24), confidence at least 0.8, in-frame coordinates and
explicit source-point ownership review. Review cannot override low confidence.
Extreme torso/shoulder angle, depth asymmetry, arms raised into shoulders, tiny
support, cropped support, another detected body, any retained face intersecting
shoulder support, or inconsistent ownership refuses with a reason. Disabled bodies
still protect their visible support. The user can preserve a request while making
explicit corrections; no hidden anatomy is supplied as a substitute.

## Original Rust inverse field and common sampling

`core/shoulder_shape/lib.rs` is original Rust math. A visible shoulder moves up
along the observed torso axis for shoulder-line shaping, and outward/inward along
the transverse axis for width. This is a meaningful local 2D shoulder-line change,
not a promise to reconstruct a 3D clavicle/neck or a claim of clinical anatomy.

The two shoulder-centered radial support disks are disjoint. Their radii are
bounded by shoulder width and distances to actual fixed head/elbow/hip anchors.
A compact C2 kernel smoothly reaches zero on the fixed boundary and is exactly
zero outside it. Existing shoulder and nearby background pixels move together;
there is no multiplication by a person mask and no false “background unchanged”
claim. Neutral recipes return exact zero without loading the native library.

The forward displacement derivative is conservatively bounded below 0.65.
Inverse points are solved at their real off-grid coordinates with residual and
analytic determinant checks; unsafe movement is refused, never silently scaled.
The final face/body map also passes finite-difference Jacobian gates across every
pixel cell and processing-band seam. This numerical gate is not a claim of
photographic acceptance or a replacement for visual checks.

Common order is explicitly `body-then-face-inverse-v1`: x → B(x) → Face(B(x)).
The face chain itself remains M(E(N(B(A(x))))). Independent displacements are NOT
added at the same coordinates. `shoulder_shape_adapter.prepare_common` REPLACES
the prepared people map using original face evaluators. It never warps a rendered
image or samples an old face delta to approximate an evaluator. Existing
`CombinedGeometry` sampling is reused once for RGB, source masks, recovery deltas
and authentic-scene support. Separate body-owner metadata never pretends to be a
face ID. Full-resolution export must rebuild at original dimensions and preserves
RGB8/RGB16; proxy edits are never enlarged into final corrections.

## Lifecycle, UI and integration ports

- `body_pose_state`: retained observations, recipes, source-specific detection caps,
  visible reviews, separate stable BodyRef and explicit person associations.
- `shoulder_shape_state`: strict portable two-control recipes only.
- `shoulder_shape_project`: content-addressed project payload; exact source export
  snapshot; protected touched-body history; confirmed-person transfer of recipe
  values only. Target body geometry/review is recomputed, not copied.
- `shoulder_shape_field/runtime/adapter`: actual native evaluator, bounded memory,
  collision and final-map gates, common-map replacement and original export port.
- `shoulder_shape_host`: document/epoch/revision/body/association fences, base
  recipe checks, exact-request digest, no duplicate mutation after uncertainty,
  actual prepare/publish callbacks, and terminal receipt lookup. Corrections can
  retain unresolved intent with an explicitly unapplied original view instead of
  deadlocking or pretending a stale edited preview succeeded. Host must use its
  real edit lock, transaction/history and actual published-view receipts.
- `ui/src/shoulderShape`: real controls, observed-point overlay, explicit body
  selection/review/person link, independent sliders/link toggles, model acquisition
  and analysis callbacks, one-inflight/latest-intent controller, cancellation of
  unsent intent on target changes, and query-only reconciliation after uncertainty.
  App/RetouchPanel and a bounded native request mailbox now mount these source
  controls. The overlay uses a canonical unretouched source PNG, never the edited
  viewport. Load IDs and stable document UUIDs are explicitly distinct.
- Outcome receipts require actual rendered pixels, output pixel digest/type,
  published-frame ID, render revision/dimensions and one sampling pass. “Prepared”
  and “rendered” are distinct; neither sets quality acceptance true.

### Shared source integration and preserved ownership

- Body bank v2 keeps one stable BodyRef and operation-specific recipe, enabled
  state, visibility review and immutable support pointer. Shoulder anchor review
  cannot authorize future legs. Only the real shoulder consumer is registered;
  unknown enabled future operations remain visible and block export until an
  explicit correction/disable. No leg field or mesh is invented.
- Every prepared subfield carries an exact digest of current observation, recipe,
  review/support and association. Same-body subfields use an explicitly frozen
  order and off-grid evaluation before the face stage, not duplicate body rows
  or summed independently sampled displacement maps.
- `body_pose_host`/`body_pose_commands` bind to actual `DocumentVersions`, source
  stamps, people ownership, existing history and SHM publication. First analysis
  stores all real candidates without selecting or associating any. Later runs
  require explicit old-body/new-candidate replacement. Reanalysis keeps recipe
  intent, advances identity and clears all operation reviews/support pointers and
  person association. Analysis revision allocation survives undo.
- `_body_pose_bank` is a separately owned document field. Project v13 prevents
  older readers from silently ignoring body edits. All v12 semantic-colour and
  v11 semantic-sky validation/migration remain. Existing undo/redo holds sparse
  body patches alongside people patches, keeps monotonic fences and persists
  even the first body-only analysis undo entry. No second history manager exists.
- `PreparedPeople` retains its actual FaceGeometry tuple, including an empty tuple
  for body-only photos. `_people_sync` no longer clears valid body geometry just
  because no face/face precompute exists. Preview/export replace one common map;
  source masks, recovery and authentic-scene support use the same sampler.
- `export_snapshot` freezes the target document's complete body bank and actual
  source frame, never a selected-body cursor. Original RGB8/RGB16 export solves
  at full original dimensions. Cross-photo reuse of source reviews is refused;
  `transfer_recipe` copies only explicit confirmed-person operation values into
  a separately reviewed target, which must be prepared again before publication.
- Semantic rendered-canvas geometry identity includes actual nonneutral body
  values, not ordinary colour or relink-only intent. Neutral body state does not
  change prior v12 geometry keys. Geometry changes retain but suspend stale
  semantic supports instead of placing them at obsolete coordinates.
- Native packing invokes `build-shoulder-shape.sh` explicitly and ships original
  Rust source, GPL project license, Apache model notices and provenance. There is
  no startup compilation or automatic model/runtime installation.
- Actual preview outcomes hash the published RGB buffer and exact composed map,
  name its SHM frame and document revision, and keep quality acceptance false.
  Export outcomes hash the actual final render buffer and full-size geometry;
  they explicitly do not claim encoded-file/profile/container publication, which
  remains the existing export owner's responsibility. Uncertain late failures
  retain request identity; a verified authoritative outcome can be queried without
  repeating mutation. Native and engine retained ledgers have explicit budgets.

## Source-boundary safeguards

- The shared whole-source shape check follows the existing decoder's `ALIGN=8`
  downward rounding, rather than rejecting ordinary camera-image proxies. Shape
  is not provenance: the host still supplies immutable unretouched source pixels.
- Original-resolution consumers bind the exact source digest and a pre-decode
  file stamp, then check that stamp after decode and before/after rendering.
  Parked targets pass their own path, not the currently selected document.
- Publication records history in the existing controller even after partial
  mutation. Its after-state capture uses the transaction's pre-bound source
  identity, so a removed source cannot erase retained intent's undo entry.
  Failed rendering suspends the map, invalidates its cache, and only reports an
  unapplied original when that fallback frame was actually published.
- A status lookup is not a mutation receipt: unavailable current source/view or
  a failed query never proves rollback. Authoritative inner receipts survive
  document switches. Explicitly cleared/restored live histories are distinguished
  from unavailable project rows, preventing both resurrection and silent loss.

## Verification status and qoder gates

Only source inspection, Python/TypeScript AST inspection, JSON data/schema review,
whitespace and SHA-256 file manifests are permitted here. No product imports,
tests, builds, compiler/typechecks, inference, model/software downloads or installs
were run. Source fixtures and Rust/Python/TS unit tests are authored, not passed.
No product runtime, performance, geometry-quality or photographic quality was
accepted. Source integration is complete only after the final static freeze;
all runtime and photographic acceptance below remains unrun.

The dedicated authored matrix is
`engine/tests/fixtures/shoulder_shape/acceptance-cases.json`. Qoder should execute
all listed cases, including genuine separated multi-person supported examples,
unacceptable occlusions/crops, independent sides, linked asymmetry, history,
source/model/association changes, cross-photo target recomputation, uncertain
transport, actual original RGB16 export and patterned-background naturalness.
Use consented/license-authorized real photos, preserve originals, show source and
actual output side by side, and report refusal rates plus blinded visual findings.
Synthetic point and state fixtures are NOT image-accuracy or quality evidence.
