# Creative layer UI integration map

Status: source authored and read-only source review only. **UNRUN**: no app execution,
runtime imports, compiler/typecheck, test, build, inference, download, installation,
or git write was performed. This is a source-integrated UI foundation, not evidence of an
end-to-end working product or completion against the two product source documents.
`App.tsx` mounts the owner hook and extracted workspace, replacing only the decorative
layer/history aside and preserving the existing creative tool catalogue. Native
registration is a thin `main.rs` addition; receipts live in `creative_layers_api.rs`.
The optional source identity/capability fields are declared in `native.ts`.

## Entry points and ownership

- `index.ts` exports `CreativeLayersPanel`, the transport types and `CreativeLayerClient`.
- `model.ts` validates transport snapshots and provides layer ordering/ancestry helpers.
- `client.ts` serializes commands and validates receipts without maintaining a second
  document, pixels, asset registry or undo/redo stack.
- `useCreativeWorkspace.ts` remains mounted in App, retaining unresolved requests across
  view changes. `nativePort.ts` sends explicit envelopes and queries original receipts.
- `CreativeWorkspace.tsx` owns the extracted layout/catalogue. App routes actual Tauri
  desktop drops and Ctrl/Cmd-Z to creative import/history while this workspace is active.
- `CreativeLayersPanel.tsx` displays only host-confirmed snapshots. Inputs explicitly
  describe uncommitted form drafts. A new owner/revision/selection remounts the property
  forms, discarding stale drafts instead of applying them to another document/layer.
- The host owns the validated layer document, immutable asset lifetime, operation
  receipts, selection, unified history and return transactions. Rust owns pixel work.

## Required panel props

Supply `snapshot`, `ownershipToken`, `ports` and optional `preview`, `history`, `busy`,
`unavailableReason`. The document schema is exactly version 1:

`schema, document_id, source_uid, source_asset, revision, canvas, selected_id, layers`.

The host must publish immutable snapshots. Revisions must be monotonically increasing
within an ownership token. Undo/redo that restore an older revision, and reloads that
restart revision numbering, require a new ownership token. The native adapter maps
the resulting authority token to `next_ownership_token` for confirmed history/return
receipts. Both empty snapshots and missing tokens disable editing.
Malformed snapshots are rejected, not normalized into plausible documents.
When history restores a pre-creative snapshot, the host publishes an explicit
`authority: null`. The UI clears the old document/preview and suppresses automatic
opening for that source scope. The user can return to the main canvas/history or
explicitly reopen a creative document from the restored photo. It does not silently
recapture pixels, invent an undo entry, or reuse the closed document's envelope.

## Host adapter boundary

Every port receives `request_id, document_id, source_uid, ownership_token,
expected_revision`. The adapter must enforce these again at the actual mutation or
return boundary, not only when the asynchronous operation starts. This matters for
file decoding, context switches, global history, external edits and delayed rendering.
An old selection must never become an implicit command target: target actions from
this panel always carry an explicit `layer_id`.

The host receipt is the same identity envelope, plus one of:

- `status: applied | no_change`, with a confirmed nonnegative integer `revision`.
- `status: rejected`, with `message`, ONLY if no mutation occurred.
- `status: unknown`, with `message`, for an uncertain outcome.

Extra backend receipt fields are allowed. Adapt a backend `error` into `message`
explicitly if necessary. Successful transport delivery alone is not an applied receipt.
On exceptions or identity mismatches the client does not retry. `reconcile` must query
the original request ID, never submit another operation. A pending receipt can be
queried even while the original port promise remains unresolved. A returned successful
receipt keeps the controls locked until the host publishes that revision or a newer
revision. Late replies from another owner cannot change current client state.

The host must retain pending operations across panel unmounts/context switches. This
view does not cancel an operation, delete an asset, undo work or dispose host history
merely because it unmounts. Do not create a second native mutation for retries.

## Port/control map

| UI control | Port/action | Important boundary |
| --- | --- | --- |
| Layer selection / edit canvas | `command`: `select {layer_id}` | Null selection exposes canvas properties only. |
| Name / duplicate / delete | `rename`, `duplicate`, `delete` | Delete is disabled without recoverable host history AND an undo port. |
| Visibility / lock | `visibility`, `lock` | Ancestor lock disables edits. Own lock can be cleared unless ancestor locked. |
| Empty group / group selection | `group {name, layer_ids}` | Empty list or explicit selected layer. Real children remain separate. |
| Ungroup / reparent / reorder | `ungroup`, `move {layer_id,parent_id,index}` | Sibling index is bottom-to-top. Descendant/locked destinations are excluded. Host revalidates graph. |
| Opacity / modes | `opacity`, `blend` | Opacity converts UI percent to 0–1. Modes are exactly normal/multiply/screen/lighten/darken. |
| Image transform / alignment | `transform`, `align` | Independent x/y, scale_x/scale_y, rotation, flip_x/flip_y. Alignment is to canvas. Group transforms are explicitly unavailable. |
| Canvas width/height/DPI | `canvas` | Only exposed when selected_id is null; limits mirror engine resource safety, not claimed manual ranges. |
| File dialog / file drop | `importImage` / native `importPaths` | One real file at a time. DOM files use bytes_base64; actual Tauri drop events use exclusive absolute path. Host validates/decode/intern/commit. 128 MiB transport cap. No FileReader/canvas/fabricated asset. |
| Attach / replace raster mask | `attachMask` | Raw File plus explicit layer_id. Host validates coverage, dimensions, coordinates and ownership before add_mask. |
| Remove mask | `removeMask` | Explicit layer_id; adapt to remove_mask command and host history. |
| Undo / redo | `undo`, `redo` | Use unified host history. Publish restored snapshot under a new ownership token if revision decreases. |
| New-image return | `returnNew` | Explicit current render_id and source identity. Missing adapter disables control. |
| Original-image update | `updateOriginal` | Separate explicit adapter. Must use host transactional recovery/history rules. Never implemented as a local snapshot rename. |
| Outcome query | `reconcile` | Query original request; no blind retry or inference from revision alone. |

All unsupported ports are visibly unavailable. Supplying a port is a capability claim:
do not provide a success-returning no-op adapter to enable a button. Set host `busy`
while other edits/history/transactions are in progress. A stale revision or native
validation error must produce a rejected/unknown receipt as appropriate.

Native state/result packets must include explicit `capabilities` booleans for command,
import_image, attach_mask, remove_mask, history, return_new and update_original. Missing
or malformed capabilities do not enable any endpoint. Read-only state packets must not
increment the main document revision merely for reading, avoiding refresh feedback.
The Rust bridge retains epoch-bound mutation receipts but never caches imported file
bytes. Pre-send native validation rejection is marked explicitly as not sent; uncertain
transport failures remain pending and are never treated as safe-to-repeat rejections.

## Preview/return contract

`preview` is `{document_id, source_uid, ownership_token, revision, render_id, url}`.
The URL must point at the real rendered result for that exact revision. Use an immutable
URL or correct cache invalidation per render. Host owns URL lifetime and revocation.
The UI never draws placeholder pixels, fabricates masks, composites using CSS, or shows
an older source image as if it were a current render. A matching image must load before
the return buttons enable; a browser load event is not a substitute for host pixel
correctness checks. Missing/stale/failed previews have a truthful text status.

Return adapters must still verify the supplied render_id and revision at commit time.
Preview availability alone does not authorize an unimplemented or unsafe original-file
overwrite; the host must keep source image identity, history and recovery coherent.

## Qoder verification handoff (all UNRUN)

`client.test.ts` contains authored metadata/receipt fixtures only. The blob string in a
fixture is not a preview image and is never used by the panel or claimed as rendered
pixels. The test file is not added to shared package scripts here.

1. Typecheck and run focused fixtures under the repository's supported local toolchain.
   Verify source-file import extensions are handled by the current Node/TS test setup.
2. Mount with no ports, missing ownership and malformed snapshots. Confirm disabled
   controls and no fabricated layers, mask pixels, successful messages or previews.
3. With real native ports, exercise select, rename, duplicate, hide/show, own/ancestor
   locks, empty group, group selected, ungroup, nested moves and sibling order.
4. Delete an image and group only with recoverable host history; undo must restore the
   full tree and real referenced image/mask assets. Check redo and resource lifetime.
   Undo past the first creative document into an older photo-only snapshot: the old
   document and preview must close, polling/view switching must not recreate it, and
   explicit reopening/main-canvas redo must remain available. Simulate history restore,
   rollback, stack-write and publication failures; they must not become `no_change`.
5. Verify all five blend modes and opacity against Rust output, not UI labels. Verify
   transforms, rotation/flips and six canvas alignments against real rendered pixels.
6. Import actual supported images (including the host's supported high-bit-depth TIFF
   path); import real raster masks and remove/replace them. Reject invalid files without
   leaking assets, losing history or representing imported IDs as decoded pixels.
7. Check canvas controls only with no layer selected. Change dimensions and DPI; verify
   clipping/metadata policy and safety rejections in the host, not only form constraints.
8. Delay decoding/rendering/receipts; double-click; switch document/source/ownership;
   publish a newer revision; regress revision; unmount/remount; lose transport. Confirm
   no duplicate commit, wrong-target mutation, implicit retry, stale-frame return or
   replacement of a newer snapshot by an old receipt.
9. Test both return modes separately with real rendered output, source binding and host
   history. A successful command or callback is not an end-to-end return acceptance.
10. Verify keyboard focus, file chooser/drop, narrow layout, preview failure and all
    disabled explanations in the actual app. No visual or accessibility pass is claimed.
