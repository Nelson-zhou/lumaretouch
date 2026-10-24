# Original face decorations: source-connected, acceptance UNRUN

Requirement: `LNX-REF-PC-32471-C-dd14134407`. One distinct operation,
`lnx.face_decoration.v1`, with five original freckle layouts and three original
mole-style layouts. These are not eight algorithms or copied commercial assets.
See `REQUIREMENT-AND-RESEARCH.md` for exact original mapping and primary sources.

## Actual numerical operation

The immutable catalogue defines small irregular marks in a measured face-local
affine frame. Rust splits each original 12-sector mark into 36 triangles with
piecewise-linear pigment opacity, clips each triangle against the source pixel
square and integrates its opacity by area. This avoids missing a subpixel mark
with a fixed supersampling grid. f64 clipping arithmetic feeds float32 coverage
and immutable working-sRGB source contributions. This is exact integration of
the chosen piecewise-linear material, not a physically exact ellipse or pigment.

Coverage sums with a bound of one. Strength and independently reviewed skin
coverage scale a fixed warm-brown multiplicative contribution. It darkens the
observed source proportionally, preserving source variation instead of painting
an opaque constant RGB spot. No noise seed, proxy stamp or per-tile random solve
exists. Other source effects still use their original numeric kernels; the new
stage uses the existing bounded source-vector composition rather than silently
clamping channels when combined with other edits. Exact zero needs neither
native availability nor active support.

Own measured geometry allows reviewed nose-bridge skin, unlike the existing
bilateral blush geometry. Eyes, brows, lips, nasal base and face boundary remain
protected. The engine requires the authenticated `face_skin` plane, not merged
body skin, and explicitly excludes every other retained face box, including
disabled/unresolved faces. Unknown skin-coloured occluders remain a manual-review
limit. No 3D wrap, automatic visibility or hidden-surface reconstruction is claimed.

## Integration map

* `core/face_decoration/`: separate original Rust C ABI, source/coverage validation,
  work bounds and UNRUN numerical fixtures. Existing cores are unchanged.
* `face_decoration_state/catalogue/geometry/native/layer.py`: strict portable
  versioned recipe, pinned original marks, measured placement, native availability,
  preflight and frozen source-window `LocalEffect`.
* `face_decoration_support.py`: immutable decoration-only normalized source
  paint, exact FaceRef/source/dimensions/landmark ownership, canonical support bank.
  Semantic-confidence thresholding is separate from painted feather/eraser
  coverage, so partial human coverage is not discarded as low-confidence skin.
* `face_decoration_host.py` plus canonical people commands: current raw effective
  source reference, immutable image hash and correlated reference request;
  explicit visible/unoccluded/ownership consent. Ordinary people transactions
  own pointer publication, rollback, history and receipts.
* `people_render_runtime/effects/pipeline.py`, full candidate and export inputs:
  actual original or supported derived source, repaired float source for the
  contribution, source-owned support and one canonical geometry/render order.
  The raw source review is not falsely described as a repaired-result preview.
* `face_decoration_scope/project.py`: scalar-only intent and exact target owner
  proof, target-local support and material recalculation; no donor coordinates,
  images, masks or recovery vectors. Shared-source changes without complete
  affected-document authority are refused, not silently applied to siblings.
* `ui/src/faceDecoration/`: eight labelled schematic selectors, scoped parameter
  writes and neutral reset; real hash/decode-checked raw source canvas, separate
  brush strokes, add/subtract, clear, keyboard point-painting and explicit consent.
  Source changes invalidate drafts. Schematic selectors are not photo results.
* `ui/src-tauri/src/face_decoration_protocol.rs`: bounded exact source-reference
  and review proof through existing people receipts, not another history owner.
* `packaging/build-face-decoration.sh` and `stage-engine.sh`: explicit build and
  source/licence staging only. Neither was run and no runtime compilation exists.

## Honest boundaries

* Moderately frontal measured visible faces only. Very small, strongly posed,
  clipped or ambiguous faces refuse instead of inventing anatomy or artwork.
* Four million source ROI pixels, 64 marks and 32 million triangle/pixel candidate
  checks are hard kernel bounds. The measured oval ROI is tight, not an enlarged
  lip window. Python conservatively preflights 256 bytes/ROI pixel plus 64 MiB,
  with existing cgroup/process admission; this is not a measured peak guarantee.
* Existing portrait-wide memory and source-format budgets remain. Opaque SDR
  float32 paths do not imply alpha or HDR support. PNG16 master precision is not
  converted to RGB8 by this operator.
* Source review is the complete normalized frame at at most 1280 pixels per
  dimension, RGB8 display, at most 5 MiB PNG. It is transported once in the report;
  the receipt carries its proof, not a duplicate image. Existing overall response
  limits remain unchanged. Cached people receipts retain one decoration reference
  image; expired read-only receipts preserve their known outcome but cannot
  authorize review. Enlarging the reference does not reveal native pixels.
* Painting uses the existing source-normalized vector schema/coverage precision,
  not a stored proxy bitmap. It remains manual visibility confirmation, not a
  neural per-person skin/occlusion detector.
* Native numerical work is bounded but synchronous; this slice adds no interrupt
  ABI or claim that a user cancellation immediately stops an in-flight solve.
* Original moles/freckles are not removed. No vendor material, automatic makeup
  removal, perfect skin-tone realism or full official acceptance is claimed.
* All runtime, installation, numerical, photo, undo/reopen and export acceptance
  is UNRUN. `ACCEPTANCE-UNRUN.md` is a test plan, not evidence of passes.

## Actual transfer and recovery routes

The subsequent [complete preset and ordinary batch review](TRANSFER-CONTRACT.md)
adds exact full mixed-image acknowledgment to the bounded routes below. It adds
no new renderer/material or automatic visibility claim. The foundation-only
generic preflight limitation is superseded for one-photo exact presets and
ordinary explicit face-map batches. The later [multiowner slice](MULTIOWNER-CONTRACT.md) adds persistent cohorts and direct scalar aliases with complete affected-image review.

Ordinary original-photo preset capture/save/replay is registered with the
existing preset library and scope installer. Active replay requires the current
exact enabled FaceRef/owner and that target's own authentic face-skin analysis,
decoration support and native core. The ordinary whole-image derived preset
route remains refused by its existing operation allowlist; the dedicated
reviewed one-photo adapter is now a separate narrow admission. Derived direct
people edits and explicit confirmed face-map transfers use the actual supported
derived-source renderer instead; this is not a claim that every preset path is
now available on derived sources.

Ordinary explicit face-map batches now use paged photographic before/after
acknowledgment and the existing frozen scalar ledger. Only pattern/strength
travel, with each target's own evidence. Generic whole-state batches and
unreviewed persistent associations with active decoration remain refused; the dedicated complete-image cohort route is documented separately. Metadata preflight is not photographic review.

Direct scalar aliases now have complete affected-document review. Alias support/recovery pointer changes, mixed presets and dormant override changes remain refused pending their own exact support/state transactions. Independent virtual-copy owners remain
independent. Existing eye-bag or face-style alias review cannot authorize new
decoration state. Unsupported aliases must remain visible refusals rather than
silently changing hidden siblings.

The actual effect-recovery target is registered through the canonical source
capture, recovery vector and render path. It reduces only this added decoration
contribution, before common geometry, leaving other effects intact. It does not
remove a person's original freckles/moles. Existing recovery uncertainty and
shared-owner guards apply; there is no second recovery/history store.
