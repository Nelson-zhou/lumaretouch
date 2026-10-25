# Capture strategy 3: bounded CG then SC finishing

Requirement LNX-REF-WF-165438-165adae6a7 remains partial. This is a working-set
change to existing colour grading and selective colour, not a new colour
algorithm. All tests, numerical parity, photo quality and runtime memory
acceptance remain UNRUN.

## Actual private path

The lens host selects explicit edited-capture strategy 3 when its existing v2
renderer capability is available. Earlier capture versions retain their prior
defaults. Geometry admission remains version1; finishing admission separately
opts into version1. A neutral finishing plan creates no request and takes the
unchanged original exporter branch.

For an admitted active finishing stage, the bridge constructs a frozen request
only after the final built-spec memory plan. It contains the sub-budget, exact
output extent, original-source context and canonical selected colour recipes.
It is a transient call argument, not a saved recipe field or generic callback.

`export_float` passes the optional request through the original-source resolver
to `_export_image_impl`. A creative source plus request is refused before
resolution. Request/spec validation runs at renderer entry, before any prepass
or delivery early return. Unsupported recursion families remain unadmitted and
do not inherit the request. Generic callers default to `None`.

Only the established CG/SC finishing site branches. Reference and semantic
stages still precede it, while editor/detail/fringe/grain/tone and all final
source checks remain after it. The actual existing stage instances and exact
recipes are handed to the bounded module. The final helper does not revalidate
the initial ExportSpec schema after legitimate preparation has added temporary
fields; instead it checks the frozen request, actual stage recipes and canvas.

The module completes a bounded whole-canvas validation before each active
stage, then calls unchanged stage/native methods on owning float32 blocks.
CG completes before SC. One private full-size float32 result is reused between
stages; source input is never modified. Native input/output buffers are disjoint.
The existing intermediate float32 rounding, domain refusals, native library
requirements and cancellation behavior remain meaningful. There is no clipping,
float64 cast, stage fusion, quantization or partial fallback.

## Budget and publication

The new phase includes actual possible source backing, one private result,
shared bounded scratch and fixed reserves. The sub-budget excludes already-live
integer decode, encoded original, ICC, snapshot/context/spec banks, last export
tile and other named reserves. It is not an extra full budget on top of those
owners. Output transfer and immutable freezing stay separate, with persistent
raw banks charged through the tail. Limits are not raised.

No request enters project persistence. Existing source/document fences, complete
candidate comparison, image ACK, new-copy return, history and uncertain-write
reconciliation remain the publishing boundary. Generic export without the
request executes its original two stage calls unchanged. No Rust mathematics,
native ABI, stage implementation or old recipe is replaced.

## Honest remaining limits

Active CG/SC with unsnapped arbitrary-angle geometry remains unadmitted because
its established float64 output is outside these stages' float32 contract. The
generic neutral-PhotoDetail float64 mismatch is not hidden by this optimization.
Current exclusions for active portrait/body/local/background/repair effects,
RAW/TIFF optimization and transparent/HDR photo return remain.

This lowers one declared working phase; decode, tile colour work, immutable
storage, canvas growth and available memory can still dominate or refuse a real
photo. No universal 24 MP throughput, RSS bound, numerical equivalence across
platforms, photographic acceptance or complete automated lens feature is claimed.
