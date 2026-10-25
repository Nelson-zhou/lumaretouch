# Manual creative selection engine

Status: **AUTHORED / UNRUN**. Only static source inspection, AST parsing and hashes
are permitted for this change. No product import, tests, native build, renderer,
inference, install, download or runtime performance measurement has been run.

Reference: <https://www.pixcakeai.com/guide/158252>, ui:18 regular rectangle/ellipse
and ui:19 free lasso/brush selection. This is independently authored geometric
coverage, not automatic person/full-body/AI selection or vendor numerical parity.

## Replaceable boundary

- `creative_selection_recipe.py`: strict vector JSON and canonical digests.
- `creative_selection_native.py`: packaged `liblumaretouch_creative_selection.so`,
  ABI 1, `lr_selection_abi_version` and `lr_selection_evaluate_v1`. No compiler or
  fallback. The existing creative compositor ABI must also be available.
- `creative_selection_stage.py`: full-grid evaluation, source projection, private
  mask candidate and real before/after composite/coverage images.
- `creative_selection_jobs.py`: reader-thread Event signals only. The original
  serialized read must unwind before its cancellation is reported.
- `creative_selection_host.py`: proof, review, exact apply ACK, bounded receipts
  and the existing creative commit port. No alternate history or image pipeline.

Parent integration owns registry, shared mixins, App and native UI mailbox.
Exports are `handle(engine, request, emit)`, `read_only(request)`,
`guard_other(engine, name, request)`,
`dispatch_rejected(engine, request, message, started, emit)`, `capability()` and
`invalidate_after_reload(engine)` (only after an authoritative confirmed reload).
Reader ingress invokes `creative_selection_jobs.controller(engine).ingress(line)`;
shutdown invokes `.stop()`. Ingress strips the native transport-only
`_host_request_id` before binding a request hash and always returns false so the
serialized cancellation command receives its own outcome. Early source/request
cancellation tombstones are bounded and honored when queued work later arrives.
An early cancellation receipt remains pending until the original operation ends;
the host then updates and emits that exact cancellation request's terminal result.

## Wire protocol

Every request has `cmd: creative_selection`, `action`, `request_id`, `source_uid`.
Every result has `event: creative_selection_result`, matching action/request/source,
`status`, `success`, `outcome_unknown`. No unrelated existing route is hijacked.

1. `context`: also supplies `document_id`, `expected_revision`, `ownership_token`,
   `layer_id`. The image must be the actual selected leaf, and neither it nor any
   ancestor may be locked. It does not open or rebind a creative document.
2. A ready result provides `context: {proof, canvas_image, existing_mask_image}`.
   The last value is null without an existing mask. `canvas_image` traverses the
   actual complete current creative composite, including groups and other layers.
3. `preview`: also supplies exact `proof`, `recipe`, `mask_policy`. Only one private
   candidate is retained. A ready `review` contains `proof`, `preview_token`, exact
   accepted `recipe`, `recipe_sha256`, `mask_policy`, `output_mask_id`,
   `output_mask_sha256`, `before_mask`, `after_mask`, `before_composite`,
   `after_composite`, and opaque exact `ack`.
4. `apply`: also supplies exact `proof`, `preview_token`, `ack`, `reviewed: true`.
   The UI must validate/decode/display all four images and obtain explicit review.
   ACK binds all four PNG digests, full immutable mask digest, recipe, mask policy,
   ownership/document/source/layer/transform/mask proof and review nonce.
5. `cancel`: supplies `target_request_id` and optional `preview_token`. It signals
   only the named source/request read. Apply cannot be cancelled. A queued/read
   cancel is pending until actual unwind; a reviewed draft may be released without
   writing. A known applied/unknown mutation is reported as its real outcome.
6. `status`: supplies `target_request_id`. Returns a cached `original_result` or
   pending, never re-executes a write. Native retained-receipt queries may be used
   without a new engine status request. Missing receipts are not retry permission.

Proof keys: `document_id`, `source_uid`, `ownership_token`, `expected_revision`,
`layer_id`, `asset_id`, `source_sha256`, `document_sha256`, `transform_sha256`,
`existing_mask_id`, `existing_mask_sha256`, `canvas:{width,height}` and
`source:{width,height}`. Source/mask SHA values cover immutable canonical float32
bytes; content-addressed asset IDs also bind original/profile provenance. All
SHA values except existing asset IDs are bare lowercase 64-hex strings.

Image descriptors are `{mime:'image/png',width,height,sha256,base64}`. SHA covers
encoded PNG bytes. Images are whole-frame display samples of actual full-source
rendering, never full-resolution mask substitutes; display caps are 262144 pixels,
4096 edge and 4 MiB encoded PNG. Before-mask for a previously unmasked layer is
true all-one source coverage. The review's source-mask images use source aspect;
composite images use canvas aspect.

JSON digests use UTF-8, sorted keys, compact separators, `ensure_ascii=False`,
`allow_nan=False`. The UI binds returned recipe structurally to its immutable
request, not by assuming JavaScript and Python number serialization are identical.

## Geometry and existing masks

The exact recipe is `{version:1,coordinate_space:'canvas-pixel-edge-v1',canvas,
feather_radius,operations}`. Rectangle/ellipse operations contain normalized
`x0,y0,x1,y1` and explicit `combine`; lasso contains `points:[[x,y],...]` and
`combine`; brush contains points, diameter/hardness/opacity and add/subtract;
invert is only `{kind:'invert'}`. Shape combines are new/add/subtract/intersect.
Empty draft recipes cannot be applied accidentally; explicit invert of an empty
selection means full-canvas coverage. Draft undo/deselect is vector-only UI state.

The native core evaluates every canvas pixel in 256-edge tiles, including all
boundaries and feather halos, at full resolution. The existing state API is
`creative_document_state.affine(transform, source_width, source_height)`, not a
new matrix implementation. It retains centers for flips/rotation. Source texel
centers `(x+.5,y+.5)` map forward to canvas coordinates. The stage bilinearly reads
the full canvas coverage grid centered at `(n+.5,m+.5)`; missing taps and centers
outside canvas edge bounds have zero coverage. This produces a full-size source
mask with the original source width and height.

The unchanged compositor multiplies coverage into each source texel before its
four-tap bilinear image transform. A transformed source mask is not generally
identical to multiplying a separate post-transform canvas alpha, especially with
rotation/minification. No such equivalence is claimed. The actual unchanged
compositor renders both reviewed images so this representational limit is visible.

Mask policy is mandatory: create only with no mask; replace/union/intersect/
subtract only with an existing mask. Source-local coverage operations are replace,
max(existing,new), min(existing,new), and max(existing-new,0). No old mask is
silently discarded. Candidate validation retains every unrelated layer/property,
original source asset and source bytes. Imported masks with identical float data
but different original-file provenance may get a new canonical generated-mask ID.

## Mutation, history, persistence and uncertainty

Preview uses a temporary OverlayAssets view, not the live asset store. It retains
one mask and four bounded PNGs, never a raw RGBA snapshot per stroke. Apply checks
all current ownership, graph, source, transform, mask and ancestor-lock evidence
again, interns one immutable mask, and invokes the existing
`CreativeController.ports.commit_document(after,before,'creative:selection_mask')`.
This delegates to existing `CreativeHost.commit_document`, with one unified
history entry and canonical `_creative_document` / `_creative_asset_records`.
No remove-mask/add-mask pair and no second undo stack is introduced.

Existing creative project/history/recovery/portable-package byte codec carries
the same source-local float32 mask record without a schema addition or pixel loss.
Applied masks survive existing undo/redo and persistence; uncommitted vector
drafts/reviews are deliberately ephemeral. Original assets are unchanged.

Write receipts are never evicted (128-write admission bound); old display imagery
is discarded from retained write receipts. Large read receipts are bounded and
released. Same request ID with different content never replaces a receipt. If a
commit adapter raises or readback differs, the write is unknown and not retried.
Other mutation is fenced, while exact status/cancel and explicit project/recovery
reopen remain available. A confirmed workspace reload clears the live fence, not
its historical receipt. A post-commit preview/report failure stays applied with
`preview_error`; missing visuals cannot turn a committed edit into rejection.

## Budgets and unrun acceptance

Host vector caps: 256 operations, 65536 total points, finite coordinates within
±1048576, brush diameter 1/64..262144, feather integer 0..256. Canvas/source edge
cap is 131072 and existing canonical pixel cap 100M remains unchanged. Fullsize
memory admission includes full canvas coverage, local mask/codec overlap, native
64 MiB scratch, bounded projection scratch and display transport. Native tiles
also enforce 100M work units each and a 2B-unit complete-recipe cap. A refused
budget produces no approximation.
Full operations, projections and actual compositor tiles observe cancellation and
ownership changes. UI may use tighter vector limits.

`engine/tests/test_creative_selection_engine_unrun.py` contains authored strict
recipe, ABI-layout, affine/edge, cancellation, ownership/locks, exact ACK, history,
codec, replay/unknown-fence, missing-native and genuine-native coverage/review
fixtures. They are all UNRUN. Native/render numerical parity, image quality,
24MP/RSS timing, cancel latency, package load, real UI and full aggregate testing
remain acceptance gates, not accomplishments claimed by static review.
