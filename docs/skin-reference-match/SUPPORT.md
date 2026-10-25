# Selected same-photo face-reference support

Status: **AUTHORED / UNRUN**. This lane adds source-owned relation metadata,
conservative face-skin geometry, scalar state and unexecuted contract fixtures.
Only static source/AST/hash inspection is permitted here. No product import,
test collection/execution, build, typecheck, inference, download, installation,
benchmark or real-photo acceptance was performed.

## Deliberately partial scope

`lnx.skin_reference_match.v1` partially addresses `control:PC-32465:19` by matching
each reviewed target **face** to a user-selected different face in the **same
photograph**. The numerical core can match colour and brightness, but these
support helpers perform neither fitting nor pixel application. They do not rank
faces by brightness, copy donor RGB, infer identity, normalize skin toward a
universal ideal, or claim the complete proprietary AI multi-person feature.

Body support is **unsupported in this v1 relation**. A future body path needs
its own operation-specific visibility/ownership review and independently fitted
body region. Existing body-to-own-face, body skin-colour, skin-finish or other
consent must never be reused as permission here. Likewise this face relation
cannot authorize any body operation.

The immutable source stage is `immutable-source-before-repair-and-portrait-v1`.
It is the current original/effective-source generation BEFORE repairs and
portrait effects, not a previously corrected reference, repair result, rendered
preview or arbitrary library photo. The host authenticates actual source bytes
and owns complete review/source/repair-edit fences. This support module does
not weaken those fences or invent a repair-derived fitting dependency.

## Portable scalar state

`skin_reference_match_state.py` exposes:

- `OP = 'lnx.skin_reference_match.v1'`, `VERSION = 1`,
  `CONTROL_ID = 'control:PC-32465:19'`, `KEYS = ('amount',)`.
- `neutral()`, `check(value)`, `active(value)` and the lazy native capability
  query `capability()`.
- Exact schema `{version: 1, amount: finite number in [0,1]}`. `None` is neutral.
  Boolean numbers, unsupported versions, extra fields, references, body scopes,
  transforms, masks and embedded assets are refused.

Scalar amounts may use the existing recipe resolver. Reference selection and
support NEVER travel through recipes, inheritance, clipboard presets or a
person/group association. Every final nonzero target needs its own relation.

## One canonical bank, immutable relation

`skin_reference_match_support.py` uses the existing project-level
`people_support_assets` dictionary. `KIND = 'skin_reference_match_relation'` is
an operation-specific descriptor, not a second support bank or recipe owner.
The target face retains only `{owner: target FaceRef, content_sha256, kind}`.
The append-only content-addressed record uses the existing envelope:

- `version: 1`
- `face_ref`: exact target FaceRef
- `source`: canonical source SHA-256, width and height
- `row`:
  - `target: KIND`, `operation_id: OP`, `source_stage: SOURCE_STAGE`
  - exact `reference_face_ref`
  - exact `target_evidence`, `reference_evidence`
  - explicit `target_landmark_digest`, `reference_landmark_digest`, each equal
    to the corresponding retained evidence digest
  - exact `target_face_skin_observation`, `reference_face_skin_observation`
  - `review: {confirmed: true, scope: 'face-only', reference_unchanged: true}`

Both faces must be retained, enabled, distinct stable instances from the same
source, with verified MediaPipe anatomy/semantic provenance and identical
canonical source dimensions. Actual normalized 478x3 landmark bytes are checked
against each retained digest. Both named face-skin observations are required;
merged skin, body skin, a bounding rectangle or a template is never a fallback.
Producer observation dimensions stay separate from canonical source dimensions
and the current render grid. A geometry-grid resize does not claim new inference.

The record saves metadata only: no source RGB, donor pixels, landmark arrays,
raster coverage or fitted transform. The relation has its own explicit review;
other effects' reviews and inherited scalar amounts cannot manufacture one.

## Public support APIs

- `check_record(record) -> checked_copy`: strict historical JSON validation,
  independent of today's live graph. Undo bytes do not become invalid merely
  because the current face/reference was reanalysed or disabled.
- `retain(state, assets, target_ref, reference_ref, target_analysis,
  reference_analysis, *, confirmed=False) -> (state, assets)`: pure staging,
  requiring `confirmed is True` for this operation's review. Appends immutable
  metadata and attaches only the target descriptor. It does not change scalar
  overrides, reference-face state, source pixels or history publication.
- `resolve(state, assets, target_ref, target_analysis=None,
  reference_analysis=None) -> (record, key) | None`: absent relation is `None`;
  attached malformed, stale, disabled or foreign ownership refuses. Supplying
  analyses requires BOTH exact current rows. Without analyses this validates
  only retained metadata, never authorizes manufactured geometry.
- `detach(state, target_ref) -> state`: removes only the active pointer, even
  when current evidence is stale or the target is disabled; immutable bank
  bytes survive for history/reopen.
- `validate_active(state, assets, active_refs, analysis_bank=None)
  -> reference_ref | None`: checks the COMPLETE final active target list after
  recipe resolution. Every target needs its relation, all targets must select
  one identical reference, and the reference must not itself be an active
  target. Optional actual analyses are keyed by stable face-instance ID.
- `geometry(state, assets, target_ref, target_analysis, reference_analysis,
  shape, *, byte_budget, cancelled=None)
  -> (target_coverage, reference_coverage, facts)`: two owned readonly contiguous
  float32 whole-source HW masks, plus metadata including separate
  `facts['target']['source_window']` and `facts['reference']['source_window']`.
  Windows are `[y, x, height, width]` and can have different extents. No RGB is
  accepted or copied by this function.

An old inactive relation may remain attached without forcing a reference choice
for neutral processing. `validate_active` must receive all final resolved active
faces, not just currently selected UI rows. It refuses conflicting references
and cycles rather than selecting a winner by order, amount or brightness.

## Geometry and reliability ownership

The helper uses the actual `skin_colour_support.check_analysis_fields` and
`face_scope.selected_face_skin` APIs. Each independent face-skin class is
intersected with that face's retained measured anatomy. Eyes, lips and brows,
known occluders, source boundaries and outer pixel footprints are protected.
The counterpart's ENTIRE measured oval, including areas missing face-skin
confidence, is a veto. Every other retained same-source face box is a further
conservative veto, including disabled and unresolved faces. Rectangles never
supply ownership or replace anatomy/semantic evidence.

The reference-face guarantee concerns THIS operation. Other separately enabled
portrait operations may intentionally edit that face; the host must distinguish
those edits when verifying the reference is not changed by this operation.

The canonical whole-source shape validator accepts the exact original extent
or the decoder's ALIGN=8 whole-frame preview dimensions. Crops, enlargement and
unrelated aspect ratios are rejected. The host still must authenticate source
bytes; shape equality alone cannot do so. Full-resolution fit geometry must be
rebuilt at the actual full-source grid, not promoted from preview masks.

Whole-source budget admission precedes full-grid semantic validation, and the
largest face ROI is admitted before anatomical raster allocation. Processing is
bounded by the existing 64,000,000-pixel source-support ceiling. These accounting
bounds do not claim measured peak memory or latency. The host separately admits
source storage, both independent RGB/coverage ROIs, Rust fit scratch and apply
work. Cancellation returns no partial pair of supports.

There is no guided radius, halo, smoothing, per-tile fit or ROI correspondence.
A nonempty geometric mask, including soft or sparse support, is NOT a successful
photometric fit. In particular, the old skin-evenness/body-face 64-hard-pixel
admission gate is not used. The Rust skin-reference solver alone owns reliable
weight mass, effective sample size, robust fit and dispersion refusal. Empty
anatomical support refuses immediately; insufficient numerical evidence must
remain a native refusal rather than neutral-success fallback.

## Host integration obligations

The shared host must route this KIND through canonical `check_store` validation,
skip generic recovery raster/application, preserve source-owned relations in
history and invalidate copied/rebound references. It must never construct a
reference from inherited scalar recipes or resolve it by detector list position.

Before native fitting, validate all final active targets together and provide
actual full-source target/reference analyses from the authenticated immutable
source generation. Fit each target independently; do not pool different people.
Apply the frozen transform to current pixels only within reviewed target support,
with no target support in the entire selected reference face. Any failed target,
cancelled fit/tile, stale review or source inconsistency prevents publication of
a silently partial frame.

The host owns complete operation-specific preview and before/after confirmation.
A `confirmed=True` helper argument is not itself a review UI, an acceptance test,
or evidence that an unfenced source/repair edit was reviewed. No missing native
capability may fall back to another operation or a fixed tint.

## Authored fixtures, not results

`engine/tests/test_skin_reference_match_support_unrun.py` specifies strict scalar
state, immutable canonical records, independent consent, exact source/evidence
and observation checks, stale reference refusal, detach/history preservation,
reference switching, complete active-set agreement, actual anatomy and semantic
vetoes, disabled/unresolved foreign protection, whole-reference-oval exclusion,
independent readonly windows, sparse/soft support without copied photometric
heuristics, full-grid rebuild, budget admission and cancellation.

These fixtures have not been imported, collected or executed and may contain
authoring errors. Native ABI validation, host transaction/history acceptance,
reference-face pixel identity, full-resolution preview/export parity, measured
performance and licensed real-photo review remain separately unexecuted gates.
