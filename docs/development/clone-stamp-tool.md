# Genuine clone-stamp brush (PC-32482)

Status: implementation work, not verified acceptance or an installed release.
No product execution, local tests, builds, or type checks were run for this slice,
following the user's development-first/no-regression instruction.

## Frozen requirement, without invented claims

The product handbook's 手动修复 section lists 污点修复、修补、仿制图章.
Its confirmed clone interaction is Alt/Option source selection followed by painting;
it explicitly leaves parameter ranges and cross-layer sampling unknown.
The AI development pack names `PC-32482-C-ec6361e1f3` /
`LNX-REF-PC-32482-C-ec6361e1f3`; related case MANUAL-003 requires stable source/target
mapping after zoom and reopening, visible coverage, and undo. This related case is
not a completed clone-specific acceptance result.

Size, hardness and opacity are explicit product controls chosen here, not asserted
as undocumented upstream ranges. The tool remains separate from spot healing and
source-patch reconstruction. Source patch retains its original behavior.

## Mature-practice comparison

Primary references read while implementing:
- GIMP Clone: https://docs.gimp.org/3.0/en/gimp-tool-clone.html
- Krita Clone Brush Engine:
  https://docs.krita.org/en/reference_manual/brushes/brush_engines/clone_engine.html

Both distinguish source selection from painting. GIMP documents None alignment,
which resets the source origin for each stroke; Krita exposes source reset before
a new stroke and explicitly distinguishes healing from cloning. This tool chooses
that per-stroke reset behavior, with a moving donor offset within each gesture.
It does not implement GIMP's complete alignment/pattern modes or Krita's complete
brush engine, and does not claim parity with either application.

Each gesture samples an immutable preceding repair stage. Its maximum brush
coverage is blended once at the chosen opacity, so overlapping dabs within one
stroke do not accidentally feed the new destination back into its own source.
Later gestures see earlier committed repairs. Clone preserves sampled color and
texture; no target-lighting reconstruction, generative fill, or heal alias is used.

## Data and interaction contract

The visible sampling view is the existing private repair-input capture, including
earlier repairs and current crop/rotation but excluding smoothing, deformation
and grading. The UI labels this difference. It does not infer source coordinates
from the final deformed display or submit displayed RGB bytes as edited pixels.

The Rust `clone_stamp` command accepts only source, normalized vector points,
normalized size, hardness, opacity, and capture/request identities. Rust validates
bounds and redeems the native capture proof before ordinary edit invalidation.
The engine validates the same recipe before its mutation fence. Receipt ownership
reuses the bounded repair receipt infrastructure; a missing or uncertain receipt
can only be queried, never auto-resubmitted.

The normalized recipe is stored as `RepairOp.kind = clone_stamp`, with translated
source and brush basis in the original repair coordinates. Exact inverse
crop/rotation mapping converts the visible circular footprint to the appropriate
source-space ellipse. Replay rerasterizes those vectors at the requested
resolution, samples the preceding float32 tensor, and changes only the target ROI.
Proxy mask assets remain coverage metadata, not baked clone image data. Project
v3, undo/redo, switching documents, and full-quality export use the existing
mixed repair stack and canonical parameter validation. Old heal/source_patch
records keep their interpretation.

Native identity, capture copying, queue ownership and command admission stay in
Rust. Float32 replay lives beside the existing tensor/ROI engine rather than
copying full GPU images through a new Rust/Python bridge.

## Acceptance still required

Implementation is not evidence that MANUAL-003 has passed. The consolidated
verification phase must cover target/source mapping at crop, arbitrary rotation,
quarter-turn, zoom and reopened project; multiple overlapping strokes;
source-boundary/padding behavior; hardness/opacity extremes; pointer cancellation,
Escape, tool changes and lost focus; one-step undo/redo; unknown-receipt recovery;
CPU/GPU memory and performance; and genuine full-quality photographic export.
No new runtime/model dependency is introduced by the clone operation.

Current admission bounds are 1–1024 vector points, a 120-megapixel input, a
16-million-pixel stroke bounding ROI, and 256 million cumulative segment-raster
pixel visits. Full-source dimensions are preflighted without image allocation
before committing a proxy gesture. Extremely long diagonal or broad strokes may
therefore be explicitly rejected with a request to split the stroke; they are not
silently truncated or saved as a recipe already known to fail full-size replay.
Distance/coverage and float sampling intermediates use 128×2048 tiles.
UI brush size is 0.1–40% of the captured image short side (default 4%); hardness
0–100% (default 70%); opacity 0–100% (default 100%). Native protocol accepts size
up to 100%, while the UI intentionally offers the narrower practical range.
