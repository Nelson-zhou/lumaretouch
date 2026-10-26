# Hand-shape acceptance — AUTHORED, NOT RUN

This is a deferred local validation plan, not a pass report. Python AST parsing
only checks source syntax. Neither that nor authored fixtures establishes native
ABI safety, numerical correctness, UI behavior, photographic quality or speed.

## Already authored source fixtures

`engine/tests/test_hand_shape_source_unrun.py` covers standalone manual support
without FaceRef/BodyRef, independent palm/finger/joint controls, detached retained
records, mandatory exact boolean confirmations, actual opposite contours, tiny
axes, cropped support, protection refusal, duplicate regions, source bounds,
nonfinite controls, source-matched proposal provenance, model/runtime/hash pins,
21 ordered raw points, no invented visibility and actual category schema.

All proposal-shaped fixture values are **synthetic schema inputs**. They are not
inference outputs and cannot be used as authentic host-issued receipts. Schema
validation alone cannot distinguish a forged digest from a genuine inference.

## Required integration cases for Qoder

- Open an ordinary hand-only photograph with no detected face or 33-point body
  pose. Manual support must be available under its honest manual label.
- Confirm only visible selected anatomy, then separately vary palm, finger and
  joint controls. Missing support for an active control must refuse rather than
  fabricate regions or silently ignore intent. Zero controls must be neutral.
- Verify original local limits/sign/default labels are not attributed to the
  handbook. The handbook confirms hand width/fingers/joints, not numeric parity.
- Draw two independent opposite contours and the real visible longitudinal axis.
  Strong asymmetry, tiny/cropped ellipses and invalid roles must visibly refuse.
- Inspect the source support/transition overlay, then the entire before/after
  candidate, not just a cropped ideal result. Background within reviewed
  transition support may move; no background-zero-change promise is valid.
- Mark nails, jewelry, contact, other hands/persons or other protected regions.
  Intersecting support/preimages must refuse rather than clip a deformation at
  a hard mask edge or conceal contamination. Unknown occlusion is not visible.
- Change source, EXIF-normalized dimensions, repair stack, document or virtual
  copy after capture/proposal/preview. Old reference and proposal IDs must not
  authorize new support; stale before/after/candidate hashes must refuse.
- Ensure arbitrary client-supplied provenance is rejected. A proposal must be
  selected from the host's current retained producer result. Imported recipe
  validation preserves provenance but does not authenticate forged projects.
- Cancel or close during a pending proposal/preview; repeat clicks; navigate
  away/back; switch documents. No stale result may appear as current or publish.
- Confirm once and verify one canonical history entry; undo/redo should restore
  exact support/provenance/amounts and existing unrelated effects. Uncertain
  delivery must query the original receipt, never replay the mutation.
- Save/reopen a project including active/undo/redo records. Corrupt source hash,
  proposal model pin or support schema must be rejected before partial restore.
- Reject cross-photo preset/batch copying of anatomy and support. No automatic
  identity association or nearest-body/face matching is allowed.

## Native geometry and rendering cases

Run the separate Rust core's authored fixtures only when local tests are
permitted. Inspect off-grid composition and analytic determinants, compact
support identity, expanded preimage protection, multi-primitive overlap,
positive-Jacobian requirements, source edges, pointer lengths/aliasing,
nonfinite values and unchanged output on failure.

Preview and full-resolution export must reconstruct original source-coordinate
fields and join the existing common map, with RGB sampled once for this geometry
chain. Masks/recovery/support consumers must use that identical map. Do not add
a late hand-only warp over an already warped photograph or upscale a proxy field.
Check all-face/body interaction and explicit ambiguous overlap refusals, tile
halo completeness, band seams, original RGB8/RGB16 and supported float sources,
plus crop/rotation/manual-liquidify ordering. Compare full candidate and final
export under the same source/repair/frozen recipe identities.

Memory admission must include retained prior maps, candidate maps, evaluation
bands, model/input bytes and copies; measure native/runtime peaks separately.
Exercise large sources and budget refusals without an unbounded allocation,
partial publication or silent fallback. No performance claim is established yet.

## Optional model cases

The adapter must remain offline on import/status/missing model. Missing, truncated,
changed or symlinked model files and mismatched optional runtime versions should
be actionable unavailable states. No package/model installation should begin
from a proposal attempt. Genuine CPU IMAGE invocation must record consumed model
bytes, actual backend source hash/version and input RGB hash/dimensions.

Inspect raw out-of-frame points, multiple nearby hands, mirroring/handedness,
held objects, jewelry, gloves and hidden joints. Model-card reliability warnings
are not legal prohibitions and do not imply an automatic detector of such cases.
Only explicitly confirmed/corrected visible points and independently drawn
contours may authorize geometry. Limit reached must not claim a complete census.

Photographic naturalness, anatomical credibility, difficult-pose reliability,
latency and memory remain **unverified** until real local acceptance.
