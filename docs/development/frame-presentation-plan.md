# Frame-bound presentation correction (implementation candidate, not yet verified)

The current ordinary preview stretches a cropped/rotated output back into the
fixed proxy raster and displays that raster's aspect. A square crop of a 3:2
photo therefore appears 3:2, although export and full-source inspection have
correct geometry. The identified frozen colour capture has its own producer-bound
presentation dimensions; this does not fix the ordinary preview.

## Required boundary

Commit presentation metadata with pixels in the existing SHM slot's 36 reserved
bytes under the existing flock. Include version/tag, load identity, presentation
width/height, geometry identity and view kind. Mapping instance plus sequence
identifies the frame. Do not join a visible frame with the latest doc_state.
Audit every producer: session open, embedded preview, ordinary edit, original
comparison, device switch and synthetic/image-stream benchmarks. Session opening
currently assigns _load_id after publishing its first frame: allocate a pending
identity for the frame without advertising a successful load before render succeeds.

The native pull/peek paths must share a versioned frame-wire encoder, reading
metadata and pixels under the same lock. Raster dimensions remain texture sizes.
UI adopts presentation geometry together with the pixels actually drawn, including
same-size swaps. Skipped/zero-byte frames must not relabel existing visible pixels.
Dirty-row streams require a full-frame barrier when document/geometry changes.

## Comparison without removing functionality

Retain single, split, swipe and temporary original view. Each original/edited layer
has its own frame-bound aspect and contain rectangle. A common screen-space wipe
clips both independent layouts; neutral background fills uncovered regions. This
is whole-frame composition comparison, not source-coordinate registration when
crop/rotation differs. No stretching, silent crop, or permanent swipe disablement.
At endpoints, the divider can reveal the complete original or edited picture.
Temporary original capture frames must not replace the cached edited layer.

Source-aligned comparison is separate scope: it needs the producer's actual rounded
crop bounds, snapped angle/affine, pre-resize output dimensions and valid-content
region. Aspect ratio alone cannot prove registration. Earlier nonlinear retouch
warps cannot be inverted by the final crop affine.

Full-source inspection ROI/layout is unchanged. This correction does not claim to
fix existing brush/pick inverse-coordinate mapping through crop/rotation.

## Verification required

Square/portrait/landscape crops, rotation, same-size image switches, old visible
frames during edits, original capture racing edited frames, dirty/skip modes,
large integer identities, parser version/length failures, independent split/swipe
aspects, zoom/pan and first-frame initialization. Basic deterministic checks first;
real-machine visual/performance acceptance remains pending until performed.

## Candidate wiring

LPR1 slot metadata, LRF1 preview IPC, strict original-frame identity, independent
comparison containment and display-aspect adoption are now implemented as an
unverified candidate. New Viewer instances use uncounted full bootstrap reads;
partial uploads remain on an initialized texture. Existing full-source inspection
layout remains separate. See docs/protocols/preview-frame-v1.md for exact fields.
