# Reference-assisted garment stain: current-photo contract

Authored source / UNRUN. This is not automatic sweat detection, a generic fabric
wrinkle alias, or a claim that every stain/pattern is repairable. Requirement IDs
are `control:PC-32477:5`, `:6`, and `:14`–`:17` in the retained original specification
`ui/src/spec/refine.json`. Native UI/command integration is owned separately.

The UI sends these **payloads inside the existing document/request/revision
transaction envelope**. This module does not define a parallel receipt owner.

- `reference {}` returns `protocol:1`, `family:"fabric_sweat"`, `reference_id`,
  `fence`, `source:{sha256,width,height}`, `source_image`, `current_amount`, and
  `capability:{available,reason}`.
- `preview {reference_id,amount,radius_px,review}` returns the same protocol/family,
  `preview_id`, `fence`, `before`, `after`, `mask`, `facts`, `candidate_sha256`.
- `confirm {preview_id,reviewed:true,before_sha256,after_sha256,mask_sha256,
  candidate_sha256}` returns an internal publication intent. Only canonical
  transaction success with updated document state is a successful UI edit.
- `clear {}` creates a neutral publication intent; it does not dispatch itself.

`fence` and each digest are 64 lowercase hex SHA-256 strings. Reference and preview
IDs are UUID hex strings, private and ephemeral. `Image` is exactly
`{mime:"image/png",base64,width,height,sha256}` with PNG-byte hash, display edge
at most 768 and PNG bytes at most 2 MiB (combined payload at most 7 MiB). These display rasters never feed numerical
measurement. Before/after are complete normal-pipeline renders, not isolated
operator-only mockups. The outer owner must bind results to its original request.

`review` has exactly:

- `version:1`, `domain:"source-normalized"`;
- `garment`, `target`, `reference`, `protect`: existing local-mask v1 stacks
  `{version:1,domain:"source-normalized",objects:[...]}`;
- `same_garment_confirmed:true`, `clean_reference_confirmed:true`.

Every object is an existing manual brush with `id,name,enabled,operation,kind,
opacity,feather,points,axes`. Add/subtract are allowed. Protection is exclusively
enabled opaque add strokes with zero feather; remove a stroke to revise it.
Normalised points/axes are in the **unrotated canonical source**, not fitted/cropped
preview coordinates. All four roles together obey 8192 points and 256 KiB.
Garment confines target and reference by intersection. Protection hard-excludes
both target and donor observations. Remaining target/reference overlap is an
error, not silently resolved. Garment ownership is an explicit user judgement,
not inferred from a face box or inverted skin mask.

`amount` is finite [0,1], preview requires >0. `radius_px` is integer 2..128 real
source pixels. This is a numerical low-frequency radius, not brush radius.
Any brush/amount/radius/source change invalidates the prior confirmation.

Persisted recipe is `None` or exactly `{version:1,source,input_sha256,
repair_sha256,amount,radius_px,review}`. It belongs to the canonical document's
`_fabric_sweat` state, never a new history bank. Source/repair mismatch suspends
nonzero use. No cross-photo transfer, presets, batch or aliases are introduced.
