# Reviewed body extension integration

Source-authored / all runtime, numerical, UI, resource and photographic acceptance
**UNRUN**. The original requirement remains `control:PC-32465:19`, not a newly
counted algorithm. Automatic instance segmentation and automatic approval are not
implemented. Manual visible/unoccluded body ownership remains required.

## Independent version and actual computation

`lnx.skin_reference_body_match.v1` stores a separately reviewed body amount under
its owning FaceRef. It deliberately does not reinterpret or activate old
`lnx.skin_reference_match.v1` face recipes. A body may be corrected without
changing its owner's face. The explicitly selected same-photo reference can be
another person's measured face or the body's own face. All retained active face
and body reference matching must agree on the selected reference. Changing this
reference requires clearing or explicitly reviewing the affected intent; generic
transfers do not carry another person's reference or manual support.

No new photometric solver or proprietary AI is claimed. The existing original
Rust full-source robust brightness/log-chroma fit and bounded current-pixel
application are reused unchanged. `skin_reference_match_inputs` captures one
immutable native-precision source for both banks. Original PNG16/ICC16/RAW16 and
derived canonical opaque SDR float follow the existing source contracts. Output
bit depth does not become the fitting source. No proxy RGB fitting, independent
channel clipping, source-pixel copying, or alpha/HDR workaround is introduced.

The body runtime uses actual body_skin semantic evidence, explicit retained
BodyRef/person/face association, and new operation-specific source-normalized
manual add/subtract coverage. A different target owner's face_skin observation is
not required; the selected reference still needs its own actual face_skin and
measured anatomy. Reference/owner ovals, every retained face box and competing
owners' manual body reservations are vetoes, not manufactured segmentation.
Legacy body families now also respect the new family's foreign-owner reservation.
These rules do not claim that merged skin semantics can identify unseen or
unreviewed people automatically.

## Full render and transaction

Face matching and body matching are separate source stages before existing body
chroma/skin operations and the unchanged combined one-pass geometry. Preparation
checks common source/reference, complete target-bank ownership and positive
coverage overlap before publication. Applying either operation uses current
pixels, so existing edits are not replaced by original RGB.

Body catalog/preview/image/confirm/clear use the existing people owner, exact
all-people photograph envelope, immutable image pages and independent body tokens.
Each body review changes one explicit owner/body while preserving all retained
other targets. Actual complete mixed before/after images and an explicit image ACK
are required. Existing graph/support/history ownership remains singular; no new
private undo stack or automatic retry is added. Clear is a neutral-intent escape
path, not proof of fresh body visibility. Native/UI validators bind complete
retained-target report, source/document revisions, support bank and the selected
body's consent. Source and review display remain reduced RGB8, not native zoom.

Current-photograph original/derived paths are connected. Preset/batch/cohort and
shared-source aliases stay guarded. Automatic brightest-reference helper research
is independent; unless its public route is separately connected, it remains
unavailable, not an end-user capability. Existing face-only behavior is retained.

## Admission and limitations

Source and application geometry are phased, with actual padded anatomical ROIs
and actual independent body/reference fit windows charged separately. This avoids
charging every temporary as a worst-case full-frame native ROI, but is not a
measured memory or 24 MP guarantee. Existing shared full-render, face-count,
semantic-grid, mask-work, support-bank and native fit/tile limits remain enforced.
No final-resolution downsampling fallback is introduced. Source capture also
charges already resident analysis backing before decode/freeze; fit admission
then accounts for its own phases without subtracting that backing twice. The new
body-support kind is dispatched to its dedicated preparation, not generic recovery
rasterization. These are source-reviewed accounting and routing corrections, not
measured performance results.

Known uncertain writes keep the original request fence and query path. There is
no dedicated verified workspace-retirement protocol for this family. If no
terminal proof can be recovered, full application restart and opening the last
confirmed saved project may be needed; unsaved edits may be lost. Merely reopening
a photograph does not prove that an earlier write failed. Model execution,
hardware, tests, builds, typechecking and visual acceptance were not performed.
