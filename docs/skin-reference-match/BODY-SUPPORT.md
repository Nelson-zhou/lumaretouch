# Selected-reference body ownership support

Status: **AUTHORED / UNRUN**. Source-only design and contract fixtures. No tests,
product imports, inference, native raster execution, build, typecheck, photograph
review, numerical acceptance, performance or hardware measurement were run.

## Requirement and scope

The preserved public requirement `control:PC-32465:19` covers matching target
faces **and bodies** to one same-photo reference face, including colour and
brightness, while leaving the reference face unchanged. See
[the research/licence baseline](RESEARCH.md). This module adds operation-specific
reviewed body ownership. It is not automatic person-instance segmentation,
automatic brightest-face ranking, recovered reflectance, or complete proprietary
AI feature equivalence. Existing skin-reference fitting/application remains the
single numerical implementation; support code does not fit or correct RGB.

Body intent is separately versioned as `lnx.skin_reference_body_match.v1`. It is
an amount-only body lane within the same user-facing feature/requirement, **not
an extra colour algorithm**. Existing `lnx.skin_reference_match.v1` face intent
and its face-only consent retain their meaning. Selecting a body does not enable
its owner's face amount or create a face-only relation. A complete mixed review
must reconcile the one reference chosen by active face and body targets.

The selected reference can be the target body's owner face or a different
enabled, verified face in the same photograph. The body always belongs to the
exact target/owner FaceRef, never automatically to the selected reference's
person. No cross-photo reference, sampled colour, RGB, raster, landmark template
or fitted transform can be transferred by the support record.

## Ownership and immutable schema

The existing `people_support_assets` bank remains the sole asset owner. The
target FaceRef stores the descriptor:

```json
{"owner": "exact target FaceRef", "content_sha256": "record SHA-256", "kind": "skin_reference_match_body_visibility"}
```

The strings above describe typed values, not a literal serializable fixture.
The actual immutable record uses the existing envelope:

- `version: 1`, `face_ref`: exact target/owner FaceRef.
- `source`: canonical source SHA-256, width and height.
- `row.target`: `skin_reference_match_body_visibility`.
- `row.operation_id`: `lnx.skin_reference_body_match.v1`.
- `row.source_stage`: `immutable-source-before-repair-and-portrait-v1`.
- `row.reference_face_ref`, `reference_evidence` and
  `reference_face_skin_observation`: exact selected source reference identity.
- `row.face_evidence`: target owner's verified source/detector/semantic/478-point
  landmark evidence.
- `body_record_sha256`: digest of the entire retained measured BodyRef record,
  including source/model/input/pose evidence.
- `body_association_revision`, `people_association_revision`, `body_link` and
  `face_link`: exact manually confirmed source body/person/owner-face linkage.
- `observation`: actual named body-skin class's source/model/producer metadata.
- `review`: this operation's explicit manual coverage and confirmations.

Review has exactly these keys:

```text
operation_id = lnx.skin_reference_body_match.v1
body_ref = exact source-owned BodyRef
points_sha256 = current retained pose-points digest
recipe = existing version-1 source-normalized local-mask brush stack
visible = true
unoccluded = true
ownership_confirmed = true
reference_unchanged = true
```

Only add/subtract brush objects are allowed, with at least one enabled positive
add. Full-image, semantic, prompted, gradient, radial, intersect-only and
subtract-only aliases cannot establish reviewed ownership. `confirmed=True` at
retention represents this exact target/body/reference review; truthy integers,
another operation identifier, or another family's review do not substitute.
The host must stage the candidate privately and show real source coverage and
complete before/after output before publishing its independently fenced commit.

The current body bank must contain the exact enabled BodyRef on the same source
dimensions/orientation and a whole-source pose input. Its explicit body/person
association must name the current people-association revision. Exactly one
confirmed face for that person/source must be the **target owner**. No nearest
face, pose index, list order, anatomical box, source class or reference person
can establish this link. Body/face association changes, reanalysis, model/input
or pose evidence changes, and changed producer metadata make attached support
stale and require review again. Ordinary unrelated scalar edits do not rebind it.

Historical JSON can be checked without today's body/person graph. That permits
undo/reopen, not live use of obsolete consent. Detaching removes only the active
pointer and preserves immutable history. Private documents and virtual copies
resolve descriptors under their nearest canonical bank, never a sibling or
enclosing bank that happens to contain matching bytes.

## Public support API

All functions live in
`engine/src/lumaretouch_engine/skin_reference_body_support.py`.

```python
choices(state, body_bank, target_ref, target_analysis)
retain(state, assets, target_ref, reference_ref, body_bank,
       target_analysis, reference_analysis, review, *, confirmed=False)
resolve(state, assets, target_ref, body_bank,
        target_analysis=None, reference_analysis=None)
detach(state, target_ref)
validate_active(state, assets, active_refs, body_bank, analysis_bank=None)
check_record(record)
validate_project(project)

raster(state, assets, target_ref, body_bank,
       target_analysis, reference_analysis, shape, *, byte_budget, cancelled=None)
reference_geometry(state, assets, target_ref, body_bank,
       target_analysis, reference_analysis, shape, *, byte_budget, cancelled=None)
geometry(state, assets, target_ref, body_bank,
       target_analysis, reference_analysis, shape, *, byte_budget, cancelled=None)
```

- `choices` returns only manually associated target-owned body candidates, each
  with BodyRef, points digest, canonical source and association. It does not
  authorize the operation.
- `retain` returns new people state and immutable bank, leaving inputs, all
  scalar amounts, the reference face and body bank unchanged. Repeating the same
  retention is content-addressed/idempotent.
- `resolve` returns `(record, digest)` or `None` when no attachment exists. With
  both analysis arguments absent it authenticates current retained metadata
  only. Actual geometry/fit must supply both source-bound analysis rows.
- `validate_active` accepts the complete active body-owner set and returns its
  common selected reference or `None`. Duplicate/missing/stale relations fail.
  The parent mixed composition additionally reconciles active face references.
- `raster` returns `(readonly float32 HW body coverage, facts)`, or
  `(None, {"enabled": False})` for absence without requiring a body bank. A
  neutral reset must not invoke stale live resolution.
- `reference_geometry` returns actual readonly selected-face coverage and facts.
  It needs no face-only relation and does not import the older body/own-face
  solver's 64-hard-pixel sample gate. The existing skin-reference Rust fit alone
  owns photometric admission.
- `geometry` returns `(body_coverage, reference_coverage, facts)` with nested
  `target` and `reference` facts and independent `[y, x, height, width] source
  windows. `target.body_ref` names ownership; `reference.face_ref` names sampling.
  `support_sha256`, canonical `source`, `source_stage` and
  `reference_face_ref` remain explicit top-level facts.

## Actual geometry and conservative protection

Body coverage is the existing Rust manual brush raster at the requested whole
source grid, multiplied by the **actual named `body_skin` editing-weight plane**.
Merged skin, face skin, body boxes and pose silhouettes cannot substitute.
Known-occluder weight greater than 0.1 is vetoed. The target owner requires its
exact verified landmarks/body-skin/known-occluder evidence, but need not have a
face-skin sampling plane when a different reference face is selected.

Every retained same-photo face box is protected, including disabled/unresolved
faces. Boxes reserve whole pixel footprints plus a render-pixel guard; they do
not create positive ownership. The measured target-owner and selected-reference
ovals are additionally vetoed over their whole interior with a footprint guard,
even where face-skin has holes or a retained box is narrower than the anatomy.
The selected reference face mask uses genuine face-skin semantics intersected
with measured anatomy, known-occluder exclusion, all foreign face boxes and the
owner's whole oval when it differs from the reference.

Other owners' attached manual regions reserve ownership even when their faces
are disabled or their live associations are stale. Reservations include this
new kind and the existing independently reviewed skin-colour, skin-finish,
body-evenness, body/own-face and collarbone families. Any positive overlap with
the admitted target coverage fails. No scalar-order precedence silently assigns
ownership, and reservation is not permission to use another family's consent.
The same owner may deliberately compose independently reviewed families.

Unattached foreign bodies and unknown occluders cannot be automatically located
by this support module. Explicit human coverage/ownership review remains
essential; a whole-photo body-skin class is not an instance mask. This limitation
is not disguised as complete segmentation.

Vectors are rerasterized at source/export/application extents. Actual semantic
planes must match that grid; preserving producer metadata during resampling does
not claim new full-resolution inference. Canonical whole-source aspect and
decoder ALIGN=8 proxy rules remain in force. No cached proxy mask is enlarged.
Aggregate target/competitor manual work and conservative full-grid/face-ROI
memory admission precede manual raster allocation. These are budget guards, not
measured peak memory or latency results. Cancellation returns no partial field.

## Integration and acceptance boundary

The shared support registry must dispatch this kind to `check_record` and skip
it in generic facial recovery. Project/history validation must call the new
historical validator under the correct canonical bank. Runtime and host own the
separate amount recipe, original/effective source provenance, complete mixed
face/body transaction, reference agreement, native fit/application, source-edit
fences, receipt/undo/reopen and UI disclosure. This support module does not make
those integration paths accepted simply by existing.

Authored fixtures in `engine/tests/test_skin_reference_body_support_unrun.py`
cover independent body-only consent, own/foreign selected references, exact
owner FaceRef+BodyRef/person linkage, stale source/model/association evidence,
body-vs-face identity confusion, other-family refusal, manual-only schema,
all-face and measured-reference protection, disabled historical competitor
reservations, separate windows, no positive body/reference overlap, source-grid
rerasterization, cancellation/budget admission, immutable retention/detachment
and private-bank history isolation.

**Every numerical and image-quality acceptance item remains UNRUN**, including
actual Rust brush coverage, reliable reference/body sampling, dark/light/varied
skin colours without ethnic classification, mixed lighting and cosmetics,
clothing/hair/occlusion boundaries, multiple interleaved bodies, reference-face
unchanged pixels, target brightness/chroma behavior, texture retention, source
and application extents, memory/latency, native loading and user review flows.
