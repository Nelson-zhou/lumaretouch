# Selected same-photo face-reference runtime

Status: **AUTHORED / UNRUN**. This lane authored Python source and fixtures only.
No product import, test collection/execution, typecheck, native build, inference,
installation, download, benchmark or photographic acceptance was performed.
Static AST parsing and source hashes do not establish runtime correctness.

This is the partial selected-reference face-only implementation for
`control:PC-32465:19`, not the entire AI multi-person feature. It does not select
the brightest face, rank people, match bodies or infer person identities. Missing
real support, review, source provenance or original Rust capability refuses the
operation. There is no tint, RGB-delta, thumbnail-fit or other algorithm fallback.

## Entry points and integration boundary

`skin_reference_match_runtime.prepare_bank(state, asset_sha256, full_source,
analyses, *, assets, application_shape, byte_budget, cancelled=...)` returns
`(tuple[LocalEffect], facts_by_face_instance_id)` only after every target succeeds.

- `state` is the canonical anonymous people graph. The runtime resolves all
  enabled same-source faces through the existing sparse inheritance resolver,
  including all-people, groups, confirmed person links and explicit face leaves.
  It does not accept a caller-selected subset as the active target set.
- `analyses` is the source-bound face-instance-keyed analysis bank. Every active
  target AND the selected reference must have exact current analysis, even when
  the reference has zero amount. Actual `face_skin`, its original producer
  observation, normalized 478 landmarks and known-occluder support are required.
- `assets` is the existing canonical `people_support_assets` bank. Each active
  target needs its own operation-specific reviewed same-photo relation. All
  targets must agree on one distinct, enabled reference which is not itself
  active. Other retained faces, including disabled/unresolved faces, remain
  protective foreign claims through the support module.
- `full_source` must be a `portrait_fit_source.FullSource` returned by the
  canonical authenticated `capture` or `capture_original` route for this source,
  before repairs and all portrait effects. Bare arrays and caller verification
  booleans are not accepted. Exact canonical dimensions, immutable float32 byte
  storage, source/precision metadata, stored pixel digest and finite SDR range
  are checked. Construction of the public dataclass is NOT an authentication
  mechanism: the host must obtain it from capture and keep the document/source
  revision fence around preparation and publication.
- `application_shape` is a `(height,width)` tuple describing the whole current
  source canvas or the existing decoder's ALIGN=8 whole-photo proxy. It is not
  an ROI, an arbitrary warp or an instruction to resize source RGB.
- `byte_budget` is a conservative TOTAL working allowance for the supplied
  source/analysis arrays and this operation. The caller must subtract unrelated
  renderer allocations and concurrent work before granting it. Native wrapper
  byte budgets remain ADDITIONAL allowances after runtime reserves are removed.

`STAGE` is `skin_reference_match`. The compositor exports the existing hair-stage
compatible signatures:

- `apply_records_np(current, records, recovery=None, *, source_shape=None,
  origin=(0,0), byte_budget=None, cancelled=...)` returns `(pixels, stage_facts)`.
- `apply_records_t(pixels, records, recovery=None, *, source_shape,
  origin=(0,0), byte_budget=None, cancelled=...)` returns the tensor.

`source_shape` in these composition APIs means the declared whole APPLICATION
grid, not the canonical fitting grid. `origin` is `(y,x)` in that application
grid. Native apply receives no origin; the compositor intersects the retained
application window with the exact caller tile and supplies the corresponding
weights. Explicit optional composition byte budgets have the same total-work
meaning; otherwise a fail-closed live CPU admission estimate is used.

Registration, ordering, host review/commands, source capture/fences, preview and
export invocation, capability/UI presentation and packaging are separate shared
integration responsibilities. These four files do not claim those are connected.
There is no second history bank or geometry path. `Parameters.resident_bytes()`
returns a conservative 64 KiB per runtime record for all non-array fit, identity
and facts metadata; the host must charge the retained weight array separately.
This stage must be applied once
to current source-frame colour before the existing single geometric warp.

## One fit, independent populations, separate application permission

For each active target, semantic observations are projected to canonical source
shape with the existing `people_snapshot` bilinear interpolation contract. Only
`face_skin` and `excluded` are copied/projected. Their original observation
producer dimensions are retained; projection does not claim fresh full-resolution
segmentation. Normalized retained landmarks are not refitted or changed.

The support module rebuilds anatomy and foreign-face vetoes at canonical source
resolution. Its independent target and reference windows each contain their own
entire nonzero reviewed coverage. `N.fit(reference_rgb, reference_coverage,
target_rgb, target_coverage, ...)` receives strided views of authentic original
float32 pixels and these complete independent windows. Different sizes and
positions are intentional. Populations are never paired by pixel position,
pooled across targets, forced into matching rectangles, or remeasured per tile.

The runtime then separately projects the original semantic observation to the
application grid and reruns the support module there. It never enlarges a
finished canonical/proxy coverage mask, corrected RGB image, displacement or
source delta. Canonical fit ownership and application ownership are checked
independently. Any overlap refuses the complete private bank.

Only an immutable numerical fit and an immutable bytes-backed cropped application
weight plane survive preparation. Frozen `Parameters` bind the amount, source
hash and pixel digest, canonical/application dimensions, exact target/reference
FaceRefs, relation digest, independent fit windows, application window and weight
digest. They are in-process values, not portable consent. Recipes still contain
only version and amount. No fit or source image is inserted into the graph,
project asset bank, history, presets or public recipe state by this runtime.

## Current-pixel composition and exact protection

Every record is preflighted before the first native call: immutable weight digest,
exact target/window/grid, common source and reference, distinct targets, no
reference-as-target, no foreign recovery and no borrowed delta/shift/gain fields.
Overlapping support inside the current tile is refused before any application;
preparation has already checked the entire application grid.

The compositor passes the CURRENT stage pixels to the original `N.apply`, in
row strips of at most 1,048,576 pixels, reusing the same prepared fit. It never
subtracts source RGB or adds a precomputed source delta. Therefore upstream
repairs and portrait adjustments are not overwritten with fitting-source pixels.
Brightness and colour may both change; fixed-current-luminance is intentionally
not this operation's contract. The numerical and reliability rules remain solely
those of the original Rust core and native boundary.

Amount zero and absent local coverage call no native apply and preserve the
current object/pixels. Outside coverage, exact pure-black/white endpoints and
zero transforms must remain bit-identical, including negative zero. Current
input is never mutated. Successful earlier strips/targets remain private when
any later target fails, output is invalid, or cancellation occurs. The final
cancellation poll precedes returning the bank/image/tensor. This is in-process
publication atomicity, not process-crash or concurrent-caller-mutation safety.
Callers must keep the graph, support bank and analyses stable during preparation,
and current pixels/records stable during composition.

Torch uses the same CPU Rust boundary and private CPU transaction, followed by
copyback only after success. There is no independently implemented GPU shader,
PyTorch formula or body-to-own-face approximation.

## Conservative memory admission

Preparation charges supplied immutable source bytes, every supplied analysis
array's backing ndarray storage (aliases deliberately counted repeatedly), a
second analysis/validation allowance, 128 MiB of fixed graph/allocator headroom,
64 KiB per output record, both full/application ownership canvases, all retained application weights plus
freeze copies, 64 bytes per pixel on each full/application grid for semantic and
geometry work, and 288 bytes per largest canonical/application anatomical ROI for geometry
scratch plus independent fit snapshots. The support module's 64 MiB fixed
allowance and native fixed/scratch allowances are added. Geometry and native callers receive separately reduced remaining budgets.
No budget failure triggers a lower-resolution source fit.

Composition charges current backing storage, all retained weight storage,
private full output, overlap ownership, 32 MiB fixed headroom, the largest
possible native tile's snapshots/output/native stage and bounded assignment
scratch. Torch additionally reserves transfer, contiguous-copy and copyback
storage before entering the NumPy transaction. Validation/identity comparisons
are chunked. This is deliberately conservative admission, not a measured peak,
a memory reservation, or an OOM guarantee. Unrelated resident renderer buffers
remain the caller's accounting responsibility.

## Authored fixtures, all unexecuted

`engine/tests/test_skin_reference_match_runtime_unrun.py` describes canonical
inheritance and conflict refusal; neutral core-free identity; independent
canonical ROI fits; separate application geometry; neutral donor requirements;
reference agreement and active-donor refusal; disabled-face reservation;
immutable captured-source and parameter contracts; preallocation refusal;
current-pixel application; crop/full bit parity; exact neutral/outside coverage;
preflight overlap refusal; bounded strip/fit reuse and later-strip failure; later-target error/cancellation atomicity; graph/bank immutability after fit refusal; exact protected endpoint validation; source,
window, coverage, recovery and algorithm mismatch refusal; and cancellation
before fit. Protocol marker doubles demonstrate routing only, not numerical or
photographic correctness. Native real-core fixtures and broader integration,
quality, preview/export parity and memory/performance gates remain **UNRUN**.
