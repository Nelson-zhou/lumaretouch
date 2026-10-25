# Current-photo portrait crop host, protocol 1

Status: **AUTHORED / UNRUN**. Source-only work, including the fixtures. No product import, collection, native execution, model inference, test, build, typecheck, installation, download, or photographic acceptance was performed. A packaged planner with the expected ABI is a prerequisite, not a test result.

## Scope and source of semantics

This is the current-photo path for controls `control:PC-32478:9`, `:15`, `:16`, and `:17`, not another copy/transfer alias. The public reference is <https://www.pixcakeai.com/guide/32478>. The local rules explicitly mean crown-to-chin height / output height, crown top margin / output height, and face-center horizontal position / output width. Aspect ratio is output width / output height. No vendor slider ranges, defaults, hidden algorithm, or ID-photo compliance is claimed.

The native scalar planner is separately replaceable/versioned. It produces a pixel-snapped `lnx.crop.v1` rectangle. `ops.geometry` remains the unchanged sampler. Missing native capability, canonical commit integration, genuine detector/model files, sufficient memory, complete source ownership, or exact render proof means unavailable/refused, never a Python geometry fallback or proxy-only render.

## Geometry prerequisite and non-destructive capture

The canonical sampler crops **before** rotating. Version 1 therefore refuses **every nonzero stored rotation**, including values which the existing renderer happens to snap to zero or a quarter turn. It does not silently zero rotation, reinterpret a displayed rotated rectangle, promise post-rotation headroom, or discard unrelated edits. Extending this requires a proved inverse mapping to crop-before-rotate geometry and achieved metrics in the actual output frame, or a separately approved change of canonical semantics.

On the serialized edit thread:

1. Capture the exact current state and document/graph/source fence, independently hash the original file, and reserve/copy private render inputs. Arrays are privately owned and readonly.
2. Change **only a private copy's `_crop_rect`** to the full normalized rectangle. Preserve the original current state and exact stored rotation. Keep repairs, portrait/body shape, optics, manual liquify, source binding, masks, color, finishing and all other recipes.
3. Render that uncropped state with `full_candidate_render.render`. Require full `source_size == output_size` and the expected canonical destination grid. This shares the existing full renderer/export path and rejects omitted effects or proxy fallback.
4. Hash the complete float raster, then make a whole-frame display projection. The projection can be SDR-clipped and reduced for display/inference only; it never replaces canonical source pixels. Hash its actual RGB bytes and PNG transport separately.
5. Run the explicitly requested genuine MediaPipe backend on **that newly generated display proxy**. Reject synthetic/manual/truncated/duplicate/invalid evidence. Retain actual loaded detector and semantic-model hashes, all landmark digests, full-source and proxy dimensions, and analysis digest. This is fresh **proxy-domain** inference, not a claim of full-resolution model inference.
6. Release the complete temporary raster before backend inference. Keep the immutable display, compact evidence and owned recipe snapshot. Generate the actual current-crop before image through the same full renderer (or reuse the full source only if the stored rectangle already equals full frame).

The existing original-file analysis is never reused across portrait, optics, body or manual geometry. `face_id` is scoped to the new landmark digest in this capture, not a person identity or original photo FaceRef. Detected chin and bounding-box midpoint are only proposals. FaceMesh landmark 10 is **not a crown**, and there is no crown proposal. The user must mark/confirm the real crown, chin and center on the actual immutable image. Coordinates are continuous source-edge pixels, x right/y down; image dimensions map the displayed whole frame to `[0,W] × [0,H]`.

Memory admission includes held snapshots, full rendered planes, display, model proxy and transport reserves. The complete renderer and model also retain their own bounds. These conservative bounds are not measured peak-RSS evidence. Admission may reject large sources rather than secretly downsample the crop output.

## Public wire contract

All normal commands have `cmd: "portrait_crop"`, an ASCII bounded `request_id`, and `action`. Unknown fields are rejected. Every result has `event: "portrait_crop_result"`, `version: 1`, `request_id`, `action`, `command_sha256`, `original_request` (the immutable parsed command before solver coercion), and `phase`.

The server's command digest is SHA-256 of sorted compact UTF-8 JSON. UI/native code must first compare the entire original-request echo structurally and then pin the returned digest. Do not pretend JavaScript and Python floating-number JSON spelling is identical. The host sends `working` with that digest before current-source or preview work begins.

- `capability`: common fields only. Returns `phase: "capability"`, a `capability` object containing availability/reason, supported rotation `[0]`, genuine proxy analysis declaration and packaged planner details.
- `current`: common fields only. Returns `current_ready` with `current: {session_id,capture_sha256,binding,source,before}`.
- `preview`: add `session_id,capture_sha256,face_id,anchors,rules,anchor_review`. `anchors` is `{version:1,crown:[x,y],chin:[x,y],face_center:[x,y]}`. `rules` is `{version:1,aspect_ratio,headroom_fraction,head_fraction,horizontal_position}`. `anchor_review` is `{image_sha256,crown_confirmed:true,chin_confirmed:true,center_confirmed:true}`. The image hash must identify the captured source photograph. Returns `ready`, `preview: {preview_token,capture_sha256,candidate_sha256,preview_request_id,plan,before,after}`.
- `apply`: add `session_id,capture_sha256,preview_request_id,preview_token,candidate_sha256,before_image_sha256,after_image_sha256,review:"full_before_after_confirmed"`. Exact matches to the retained full-image candidate are required. It returns `committed`, `result:{status:"applied"|"no_change",document_id,revision}`, original request identity, preview/candidate identity and `recovered`.
- `cancel`: add `session_id`; release a known session without changing the source or edits. It cannot cancel an unresolved write.
- `status`: add `target_request_id`; returns `phase:"status", receipt:<the original complete receipt>`. The wrapper echoes its own status request and the nested receipt echoes the original request. An absent record is `unknown`, never permission to retry. Status wrappers are not recursively retained with image data.

Source fields: `width,height,orientation:"exif_normalized_once",mapping:"source_edge_pixels",source_sha256,analysis_sha256,model_sha256,semantic_model_sha256,proxy_sha256,proxy_size,inference,image,faces`. Each face supplies `face_id,landmarks_sha256,bbox,chin_proposal,center_proposal` in source-edge pixels. `source_sha256 == binding.uncropped_sha256` names the full float raster, not original file bytes.

Binding fields: `document_id,revision,document_epoch,load_id,original_sha256,source_proof,state_sha256,non_crop_sha256,people_sha256,repair_sha256,uncropped_sha256`. The complete state hash includes every edit and retained repair field; the separate repair hash is diagnostic, not an exclusion list.

Every photographic image is `{mime:"image/png",width,height,sha256,base64,source_width,source_height,mapping:"normalized_full_frame"}`. The source view is the complete uncropped edited image. Before is the complete current output. After is the complete candidate output, never a CSS-clipped source image or schematic. UI must decode and verify bytes/dimensions before enabling anchor/review confirmation. The candidate before image is the same captured before image.

`rejected`/`cancelled` carries `no_write:true`. `unknown` after apply carries `outcome_unknown:true`, the original request identity and no false `no_write`. Duplicate exact requests replay receipts, not operations. Reusing an ID with a different payload is refused. The engine-lifetime bounded ledger never evicts mutation outcomes; old read imagery may be explicitly released without rerendering. A source lease expires after ten minutes and a candidate after three; unresolved writes do not expire.

Reader cancellation is the separate exact packet `{cmd:"portrait_crop_cancel",request_id,command_sha256}` for `current`/`preview` only. It sets an event through `portrait_crop_controller.controller(engine).ingress(line)`. Only the original read's actual unwind reports cancelled. Apply is never registered as a cancellable job. Late cancellation is not evidence that completed work was undone.

## Canonical owner integration

`portrait_crop_host.service(engine, emit).handle(request)` is the serialized command port; `.maintain()` performs lazy lease reclamation. The reader uses `.ingress(line)` and calls `.stop()` at shutdown. `capability(engine)` is independently queryable.

The parent binds exactly one commit port:

`engine._commit_portrait_crop_candidate(*, before_state, candidate_state, proof, request_id)`

It must verify and publish through the **existing canonical history owner**, preserve every non-crop state member and exact rotation, change only the existing crop rectangle, retain one undo/redo step (or a true neutral no-op), and leave original bytes/source identity unchanged. `portrait_crop_project.verify_commit` provides source/edit/render/geometry proof validation immediately before admission. No second history stack, derived image source, creative-return copy, project recipe alias or renderer belongs here. The compact proof contains no display pixels and cannot authorize replay or reconstruct a UI confirmation after reopening.

Optional read-only recovery port:

`engine._portrait_crop_candidate_status(request_id)`

This must return a verified terminal canonical result or `None`, never repeat the mutation. The host marks uncertainty before entering the commit boundary. On transport failure or inconsistent post-commit proof it blocks further writes and queries the original request only. A recovered result establishes the historical outcome, not that the user has not subsequently edited or switched photos. If no authoritative original outcome exists, uncertainty remains visible.

## Acceptance still required

UNRUN fixtures cover strict envelopes, immutable request echo, exact-zero rotation support, non-crop retention, cancellation unwind, selected source/candidate/ACK mismatch, one-time canonical-port invocation, duplicate/colliding requests, stale capture refusal, unknown-write handling and status reconciliation. They use explicit synthetic contract doubles and are not photographic evidence.

Before enabling release claims, run authorized native scalar parity and sampler-edge fixtures; genuine original/derived-source capture and fresh proxy analysis; pre-existing crop/rotation cases; portrait/body/optics/manual deformation, repair replay and finishing retention; multi-face selection; manual crown/chin/center review; complete before/after image verification; stale/cancel races; one canonical undo/redo step; project reopen/export parity; failure/rollback/recovery; real images and bounded-memory measurements. Do not relabel an unavailable/unbuilt capability as delivered runtime functionality.
