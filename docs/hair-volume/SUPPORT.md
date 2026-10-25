# Current-source hair geometry support

Status: AUTHORED / UNRUN, 2026-10-25. This is an actionable manual-assisted
current-photo design, not a claim that semantic hair output identifies an owner,
crown boundary, ear, hairline or hairstyle. No current photo has been rendered
or accepted in this static-only pass.

## Actual model/evidence contract

Reuse only `hair_colour_analysis` and `hair_colour_evidence` actual producer
contracts. The existing local `selfie_multiclass_256x256.tflite` is 16,371,837
bytes with SHA-256
`c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`.
Both were independently read/hashed in the working tree on 2026-10-25, without
loading/executing the model. The producer is
`mediapipe-six-class-confidence-gated-hair`, domain `source-normalized`.

The retained weight, dimensions, source binding, model hash and weight digest
are checked by the existing evidence contract. Its lossless bank identity is
retained in each geometry review. No model is downloaded, installed, run,
relabelled as a new inference, or rebound from original pixels to a derived
composite. `hair_colour_evidence.current` can retrieve retained evidence; for a
derived source the existing verified actual-composite precompute contract must
be used. Frozen replay does not require weights to be installed.

Only measured confidence at explicitly marked paired samples is read:
interior hair ≥0.20; exterior hair ≤0.05. These are original support admission
thresholds. Low hair confidence alone does NOT establish the background class:
the existing evidence only retains hair confidence. The operator must inspect
the whole moving transition and confirm it is clear of faces, exposed anatomy,
clothes, objects and other people. Model evidence corroborates observed hair,
not manual instance ownership. The scalar displacement is NEVER multiplied by
the dense confidence image. Changing evidence invalidates the exact review.

## Portable scalar intent

```json
{"version":1,"crown":{"version":1,"amount":0.0},
 "sides":{"version":1,"linked":true,"left":0.0,"right":0.0}}
```

Independent crown and sides versions permit maintenance without turning sub-
controls into inflated algorithm counts. A linked recipe must have equal side
amounts; the engine refuses mismatches rather than choosing a winner. Only this
scalar intent is transferable. Destination photos/people must obtain new source-
owned contours, protection, model evidence and independent operation review.

## Manual input schema

`regions={crown:patch|null,left:patch|null,right:patch|null}`. Only a nonneutral
requested region requires a patch; untouched regions can remain null. Each patch:

```json
{"x":[0.25,0.35,0.65,0.75],"y":[0.05,0.15,0.25,0.35],
 "contour":[[0.35,0.18],[0.50,0.18],[0.65,0.18]],
 "hair_samples":[[0.35,0.23],[0.50,0.23],[0.65,0.23]],
 "background_samples":[[0.35,0.08],[0.50,0.08],[0.65,0.08]]}
```

These values are SYNTHETIC schema examples, not automatically generated real
anatomy. The three equal-length point lists each contain 3–33 manually observed
points. Crown contour order is increasing x; each side order is increasing y.
Contour endpoints span at least half the plateau tangential interval. Contour
and hair samples are inside the closed plateau. Background samples are inside
the entire reviewed transition. Paired sample tangent coordinates agree exactly;
normal offsets are at least one original source pixel using `(width−1,height−1)`.
Hair is below a crown point, right of an image-left point, left of image-right;
background is on the opposite side. No face landmark is promoted to a crown or
ear observation. `x/y` breakpoints are normalized explicit source positions,
not guessed from a face/pose box.

Protection input:

```json
{"ears":[],"neck":[],"other_people":[],
 "visible_anatomy_reviewed":true,"whole_source_reviewed":true}
```

Each rectangle is `[x0,y0,x1,y1]` in the same source domain. Mark all exposed
ears (0–2) and neck (0–1) and all relevant other people (up to 64). Empty anatomy
lists mean no corresponding anatomy is exposed in the reviewed source, NOT an
inferred hidden-anatomy position. The model/landmarker cannot certify that
review. The current canonical face and every retained foreign face are also
protected regardless of enabled/manual/unresolved status. Additional observed
body/obstacle rectangles from the source owner may be supplied via runtime
`protected_regions`; preparation and consumption bind their exact digest.

All protected boxes must be disjoint from every complete active transition plus
the full displacement reach. Boundary contact counts as overlap. Different
owners' transitions cannot touch. Refusal does not punch a hole in the field,
silently delete an obstacle or attenuate requested strength. Current retained
face geometry/evidence changes invalidate `source_faces_sha256` and require a
new review; a detector's results are not treated as an exhaustive person census.

## Immutable support envelope and host integration

`KIND='hair_volume'`. Standard support store record:

```text
{version:1,face_ref,source,row:{target:'hair_volume',operation_id:'lnx.hair_volume.v1',
 semantic_model_sha256,semantic_evidence_sha256,source_faces_sha256,
 regions,protection,review}}
```

The review is `explicit_source_hair_geometry_review`, pins this operation and a
digest of the complete record excluding the review itself, and requires explicit
confirmation. Colour, head-size, root/tip or other existing review is never
silently reused. The canonical graph stores only `{owner,kind,content_sha256}`.
The store is append-only; clear detaches the active descriptor but retains bytes
for undo. Required APIs are `check_record`, `reviewed`, `retain`, `resolve`,
`detach`, `check_store`, `validate_project`. The shared store owner dispatches
this target to its validator and skips it in unrelated facial recovery rastering.

`reviewed(state,ref,source,regions,protection,hair_evidence,confirmed=True)` binds
manual inputs to actual retained evidence. `retain` stores the immutable review;
`resolve` verifies exact current FaceRef/analysis/ownership. `validate_project`
can verify the separate evidence bank, including archived support. Preview,
commit, history, source changes and export stay in the canonical host transaction
path; a support preview is not authorization to publish or to reuse consent.

## Supported scope and refusal UX

Supported target: a currently observed, sufficiently resolved exposed crown
band and/or independently visible side-hair strips with unambiguous owner,
measured hair interior, visible silhouette and room for a clear transition.
Neither front-facing pose nor short hair is mandatory. Long hair may use a
visible separated lateral segment whose lower boundary/tips remain fixed, if
the entire selected transition stays clear of shoulders/clothes/contacts.

Refuse or ask for narrower/redrawn support when crown is cropped, a side is
hidden, hands/hat/objects obscure the contour, the transition contacts exposed
ears/face/neck/clothing/another person, loose hair is interwoven between owners,
long hair contacts the shoulder in the selected strip, evidence disagrees, or
there is insufficient fade margin. Do not invent the missing half, use a pose
ear point as a crown, or fall back to full-head scaling. Reject only the affected
unsupported requested geometry transaction, not the entire feature for every
photo. The user can leave a hidden region neutral and adjust supported regions.

This is 2D controlled contour movement, not increased hair density, new strands,
anatomical skull measurements, occlusion recovery or guaranteed pixel-perfect
matting. Acceptance must include the displayed source/after pixels and semantic
protection facts, not only a changed parameter JSON.
