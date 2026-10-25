# Creative selection coverage core

Status: **AUTHORED / UNRUN**. No compiler, tests, import, benchmark, image inference,
hardware probe or build script was run for this work. A written fixture is not an
acceptance result. See [ACCEPTANCE-UNRUN.md](ACCEPTANCE-UNRUN.md).

## Ownership and boundary

`core/creative_selection/` is an independent, original, dependency-free Rust
coverage evaluator. Its C ABI is replaceable independently of the editor, Python
host, creative-layer compositor and mask/history storage. It never reads images,
paths, model weights, display screenshots or existing mask assets, and never
mutates a document, layer, recipe or file. It returns real row-major float32
coverage, not a polygon preview, boolean bitmap, uint8 alpha proxy or placeholder.

The traceability anchors are `ui:18` (regular selection) and `ui:19` (free
selection) at the [official manual](https://www.pixcakeai.com/guide/158252), with
creative-layer context in `workflow:127932` at the
[creative workflow manual](https://www.pixcakeai.com/guide/127932). Those entries
remain subject to independent verification. This module does not complete the
entire creative workflow, rendering/return path, or native UI acceptance.

## Versioned numerical contract

- ABI version 1; full creative-canvas pixel-edge coordinates; X right, Y down.
- `source_width` and `source_height` name the authoritative canvas sample grid in
  this ABI. They do **not** name a zoomed preview or a transformed leaf's local
  raster. The host must bind the recipe to immutable source/document identities.
- Samples represent cells `[x,x+1) × [y,y+1)` and are located at centers
  `(x+0.5,y+0.5)` when subsequently sampled as a raster.
- Ordered rectangle, ellipse, lasso, brush and invert operations start from zero
  coverage. Deselect is an empty operation list. An empty recipe is not an
  implicit all-selected mask; that state needs explicit host policy.
- New, add, subtract, intersect are `B`, `max(A,B)`, `max(A-B,0)`, `min(A,B)`.
  Invert is `1-A` within the canvas. Final feather is then applied.
- Free/fixed ratio/fixed size are editor geometry-creation constraints. They
  lower to the same normalized bounding rectangle, without a second native
  shape mode or silently changing a stored bounding rectangle.
- The brush is a continuous round-capsule path. Diameter, hardness and opacity
  are separate; add/subtract are supported. Repeated points do not stamp opacity
  repeatedly. This is a documented selection brush, not a paint deposition model.
- Feather is an integer-radius, separable normalized finite **box** filter with
  zero extension outside the canvas. It is not claimed to match a proprietary
  feather kernel, a Gaussian, GIMP output or Cairo output.

See [NUMERICS.md](NUMERICS.md) for sampling and limitations and [ABI.md](ABI.md)
for concrete native layouts, bounds and sample-projection responsibilities.

## Bounded source-addressed evaluation

An invocation requests an integer tile wholly inside the canvas. The core expands
it by the exact feather support, clipped to canvas bounds, replays the complete
recipe on that patch and returns only the requested tile. Geometry and sampling
remain in global coordinates. Results of successful tile evaluations are designed
to be bit-identical to the same positions in a successful bounded whole-canvas
evaluation on the same build/platform. Neither a tile nor a preview becomes a
different geometric source grid.

Default per-call limits are 64 MiB of numeric working buffers, 1,048,576 output
pixels and 100,000,000 deterministic work units. Independent hard caps prevent
unbounded caller overrides. Large canvases are processed in source-addressed
tiles, never by allocating a full supersampled image. A 6000×4000 canvas can be
addressed, but this is **not** a measured 24 MP throughput or latency claim.

The intended host schedule uses 256- or 512-pixel tiles, a bounded cache, explicit
cancel polling and one complete immutable asset only after every required tile
succeeds. Preview display may downsample completed authoritative coverage; it
must never be promoted/upscaled into the final source mask. Extremely complex
recipes can return `LIMIT_ERROR`; the host must report that honestly, not replace
the result with zeros, a lower-quality raster, a proxy or a claimed success.

## Module files

- `lib.rs`: checked C entry and original numerical implementation.
- `creative_selection.h`: fixed public ABI with scalar/pointer layouts.
- `Cargo.toml`: standalone Rust crate, no third-party dependencies.
- `build_creative_selection.sh`: dedicated Linux cdylib build entry, **not run**.
- `tests.rs`: authored numerical, tiling, cancellation, bounds and ABI fixtures.

No shared build wiring, Git writes or third-party source imports are part of this
module. Runtime loading, selected-leaf validation, projection, asset hashing,
existing-mask merge policy, stale review checks and history are host concerns.
