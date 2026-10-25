# Selected-reference body review

Status: AUTHORED / UNRUN. This is the separately stored body lane of
`control:PC-32465:19`, not a new numerical algorithm or runtime/image acceptance.
No tests, collection, product imports, builds, type checks, inference, model
acquisition, hardware checks, Git writes or real-photo comparisons were run.

## Ownership and scope

- `lnx.skin_reference_body_match.v1` stores only `version` and `amount`. Each
  explicit scalar override belongs to the target owner's exact FaceRef. No
  person/group/all-people inheritance, donor value or portable BodyRef exists.
- `skin_reference_match_body_visibility` is an operation-owned immutable support
  relation in the existing canonical `people_support_assets` bank. It records
  the target BodyRef/person/face association, source/model/evidence identities,
  manually reviewed source-normalized brush vectors and selected reference face.
- The selected reference may be another same-photo face or the target owner's
  own face. Body-only intent creates no face correction or face-only relation.
  All actual face pixels remain protected by the separate support implementation.
- A review changes one selected owner/body at a time, preserving every other
  face/body target, amount and support attachment. All active face and body
  lanes must agree on one selected reference. Clearing bodies never clears faces.
- The minimal route is current-photo only. It does not authorize another source,
  source-identical live/dormant alias, virtual-copy sibling, batch or cohort.
  There is no automatic donor selection or inferred body ownership in this lane.

## Wire contract

All actions use the existing `people` envelope and exact target:
`{scope: "all_people", target_id: <effective source sha256>, face_ref: null}`.
They retain the existing document/epoch/revision/state/association/request fences.

- `skin_reference_body_catalog`: empty payload. Returns the immutable full-source
  display PNG and digest, source proof, document identity, a source-review digest,
  every retained face with donor availability, and genuine eligible owner/body
  choices with BodyRef, measured points digest, source and confirmed association.
  A target owner's body eligibility does not require its own face-skin sampling
  plane if a different eligible reference face supplies that plane.
- `skin_reference_body_preview`: exact fields `version`, `reference_face_ref`,
  `target_face_ref`, `review`, `amount`, `source_review_sha256`,
  `ownership_confirmed`. Amount must be positive; neutral uses clear.
- `review`: exact fields `operation_id`, `body_ref`, `points_sha256`, `recipe`,
  `visible`, `unoccluded`, `ownership_confirmed`, `reference_unchanged`. All four
  confirmation flags must be literal true, and operation_id must be this body
  lane. The brush editor alone does not grant these confirmations.
- Preview returns one frozen `review` containing the selected FaceRefs/BodyRef,
  exact `body_review`, amount, source/catalog proof, body-bank digest,
  `before_current` and `candidate_current` complete body target/amount/support
  reports, candidate revision, canonical support-bank digests, selected support
  hash, complete mixed-image `visual`, independent token and review digest.
- `skin_reference_body_image`: `token`, `side`, `sha256`, `review_sha256`. Returns
  the exact before/after PNG bytes for the frozen full mixed render. Every image
  read rechecks source, graph, document, full recipe, body bank and analyses.
- `skin_reference_body_confirm`: `token` and `ack`, whose exact fields are
  `review_sha256`, `before_sha256`, `after_sha256`. Both exact image sides must
  actually have been served and remain available; a metadata-only ACK is not
  sufficient. UI independently checks actual PNG bytes/load before enabling ACK.
- `skin_reference_body_clear`: empty payload. Removes only current-photo body
  overrides and body support pointers, including dormant/disabled targets.
  Immutable historical support bytes and all other operations remain intact.

The catalog's scope is `current-photo-body-only`. `current` report fields are
`version`, `operation_id`, `bank_sha256`, `reference_face_ref`,
`target_face_refs`, `amounts`; each amount row carries `face_ref`, `amount`,
`support_sha256`. The common donor can be nonnull with no body targets when face
matching already constrains the donor. This report describes retained intent,
not proof that current body evidence is renderable, so stale pose evidence does
not hide the clear action.

Confirmation proof fields are `kind`, `token`, `review_sha256`,
`reference_face_ref`, `target_face_ref`, `body_ref`, `amount`,
`candidate_state_revision`, `support_sha256`, `candidate_bank_sha256`, `review`,
`ack`. The `review` is the unchanged full frozen preview, allowing native/UI
receipts to verify complete retained target reports rather than only one target.
Clear proof fields are `kind`, `candidate_state_revision`, `cleared_face_refs`.

## Source, transaction and history

The catalog reuses only the immutable source-display helper and PNG transport
primitive. Original and derived effective-source binding/proof are retained;
source pixels are captured before repair and portrait effects. Before/after
images are rendered through the existing complete mixed candidate exporter,
including other authorized corrections and geometry, without swapping live
source, graph, support bank or history during preview.

The body lane owns independent source entries, pending tokens, served-image
receipts and a bounded operation-specific admission. It never reuses another
operation's consent, preview or publication bypass. Admission pins owner/fence,
exact before/candidate graphs, canonical support bank, body bank and review hash.
Publication uses the existing canonical people owner, receipts and document
history. Confirmation is single-claim; post-publication checks verify exact
owner, document revision, source and candidate context. Unused append-only
support metadata may survive a failed preparation, never as a successful edit.

Project validation closes pointer/hash/owner/evidence metadata under the nearest
canonical support bank, including private virtual-copy contexts and sparse
history patches. Scoped people history authenticates its own retained `_body_pose_bank`
snapshot rather than today's live links. Disabled, removed or reanalysed bodies
may keep nonzero unapplied intent: old relation bytes and BodyRef/points identity
remain durable metadata, never silently rebound or treated as render permission.
Historical stale status is transient and never changes saved recipes. Active live candidates additionally resolve exact body,
owner/reference and semantic evidence. Generic activation, amount changes,
retargeting and association/anatomical changes require this lane's own review.
Neutral clear does not require its stale body evidence or native numerical core;
unrelated existing-operation guards still apply.

## Authored acceptance matrix

`engine/tests/test_skin_reference_body_review_unrun.py` includes authored cases
for explicit donor/body choices; body-only and own-face donor; body owner without
face-skin plane; retained unrelated targets/amounts; mixed face/body donor
consistency; foreign/borrowed/partial consent; exact actual-image ACK; stale
source, repair, body, model, link, support, graph and analysis fences; independent
session tokens; no-alias refusal; generic activation/reassociation rejection;
neutral clear with disabled/stale/unavailable body evidence; historical body
snapshot closure and stale-unapplied save/reopen without rebinding; nearest private support-bank isolation; no migration of old
neutral graphs; and canonical single-claim publication.

These fixtures use explicitly synthetic measured records and fake display
bytes at mocked source/render boundaries. They are not true PNGs, inference or
photographic quality evidence. Tests, runtime acceptance, export fidelity,
UI accessibility/interrupted-flow checks, numerical reliability and hardware
coverage all remain UNRUN.
