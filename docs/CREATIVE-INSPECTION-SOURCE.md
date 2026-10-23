# Returned-base full-source inspection boundary

Status: implementation and regression fixtures authored; no execution, compilation,
type checking, native inference, or numerical/UI acceptance was performed in this
work slice. This is not a completion claim for M14 or for derived-source analysis. See `creative-layers/DERIVED-SOURCE.md` for the
separate analysis binding added in the combined continuation.

## Source and provenance

The captured `creative_base` contains immutable canonical little-endian float32
premultiplied linear-sRGB RGBA bytes and its independently validated SHA-256 asset
identity. Its dimensions are the baked canvas dimensions. The original path and
file stamp remain separate provenance and must remain stable during this operation.
They never supply returned-base inspection pixels or people/mask observations.

The controller binds each request to the captured asset id. The isolated worker
validates the received asset bytes and id, verifies admitted baked dimensions, and
builds the recipe at those dimensions. The original-photo worker branch is retained
for documents without a returned base. Missing assets, changed ids, mismatched
dimensions, and unsupported source-bound edits fail closed.

## Ownership, render and publication

Snapshot accounting includes canonical, original and ICC bytes. Immutable bytes
are retained without mutable aliases; dictionaries are privately cloned. Bounded
spooling writes those bytes through explicit bundle byte-vector tags, not pickle,
JSON base64, file-path substitution, or a display proxy. Array and immutable-payload
accounting are separate. Existing 512 MiB snapshot/spool and worker address-space
admissions remain; over-budget assets are rejected without downscaling.

The full-quality branch invokes the shared export resolver exactly once, using an
empty carrier rather than fake original pixels. The resolver calls the packaged
Rust opaque-SDR float bridge and applies current edits at full baked resolution.
Crop/rotation apply once before ROI extraction. Alpha/HDR incompatibility remains
an explicit error, not a matte, clip, or original-pixel fallback. RGB16 conversion
is the final export/display step; canonical pixels are not modified.

LRIF remains an opaque RGBA8 display packet. Its decoded-precision field may now be
32 for the canonical float input, and source-file precision is unknown for this
derived source. Python, Rust, and TypeScript readers agree on that extension.

Existing command fences invalidate host inspection generations before creative
mutation, undo/redo, source changes and edits. Engine snapshot cancellation precedes
mutation; worker cancellation retains leases until process exit. Result publication
still checks epoch, ticket, canvas and ROI, including stale in-flight pulls.

## Unexecuted regression fixtures

`engine/tests/test_creative_inspection_source.py` covers immutable-byte budgets and
round-trip identity, mutable-byte refusal, baked geometry without original access,
single resolver use, truthful precision, early admission, cancellation, and an
explicit native-render/export equivalence fixture. Rust and TypeScript envelope
fixtures cover float-source precision. The native fixture skips explicitly when
the packaged library is absent. A permitted execution pass is still required.

The separate analysis binding in `creative-layers/DERIVED-SOURCE.md` accompanies
this inspection change. Source-bound effect tools, transparent/HDR photo return,
and whole-product manual acceptance remain incomplete.
