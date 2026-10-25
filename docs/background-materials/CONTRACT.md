# Local background materials v1 contract (source authored, UNRUN)

This independent catalogue implements the local-management slice of preserved
`creative:165433`. Its first actual consumer is ID background control
`LNX-REF-PC-32475-C-7f1d9dd04c`. It is not an AI staging backend, a colour-sample
library migration, a stock subscription, or a sky-consumer implementation.

## Ownership and entry points

- New `background_material_*.py` files own catalogue/storage and its protocol.
- `background_material_command.dispatch(engine, request, cancelled=...)` handles
  transport-neutral requests. `controller(engine)` obtains the independent owner.
- `background_material_host.BackgroundMaterialHostMixin` exposes
  `_background_material_host()`, `cmd_background_material_library(message)` and
  `cmd_background_material_library_cancel(message)`.
- The reader may call `owner.observe_line(line)` and `owner.stop()`. Reader work
  only registers cancellation events. Actual catalogue/image work stays on the
  serialized engine-command owner.
- Shared outer guard/finally handling calls
  `background_material_host.dispatch_rejected(engine,message,error,started,emit)`.
  It replays an exact matching retained terminal; otherwise it retains a known
  not-applied rejection before command entry, or an unknown outcome after entry.
  It retires the ingress cancellation event without running the requested command.
- `background_material_selection.resolve_for_id_background(selection,
  cancelled=..., root=None)` returns an existing `IDBackgroundAsset`, not a path
  or preview. Shared ID integration alone adds `id_import_material` with
  `selection` and all existing document/recipe revision fields; it calls the
  resolver, existing `id_background_assets.pack`, and the existing single edit,
  history, project and export owner. Direct `id_import` remains available.
- New UI/native modules own browsing and transport. The parent owns shared
  server, registry, native registration and ID-panel integration.

## Transport envelope

Native invocation: `background_material_library({request})`.

Native request is exactly `{action, request_id, request?}`; actions are `request`,
`status`, `cancel`, `release`. Only `request` carries an inner `request` object.
Native state replies use `{request_id, phase: "pending"|"done"|"unavailable",
result?, cancel_requested?}`. A terminal may be released only after consumption.

Engine request is exactly `{cmd:"background_material_library", action:"request",
request_id, request}`. Cancellation control is exactly
`{cmd:"background_material_library_cancel", request_id}`.
Terminal event is `{event:"background_material_result", protocol:1,
request_id, action:"request", success, outcome_unknown, committed,
result? , error?, error_code?}`. `committed` is boolean or null. Unknown transport
outcomes are reconciled by the original request ID, never automatic resubmission.
Request IDs match `[A-Za-z0-9_-]{1,128}`. Request and terminal JSON budgets are
8 MiB. The host retains at most 128 terminals / 16 MiB; native retains admitted
terminals until explicit release. There is no cross-engine durable receipt claim.

## Inner requests (no unknown fields)

- `{method:"snapshot"}`
- `{method:"page", query, expected_revision}`
- `{method:"thumbnail", id, expected_revision}`
- `{method:"select", id, expected_revision}`
- `{method:"command", op, payload, expected_revision}`

Query is exactly `{group_id:null|string, text:string, trash:boolean,
sort:"manual"|"name_asc"|"name_desc"|"newest"|"oldest", offset:number,
limit:number}`. Text is at most 120 characters, offset is 0–20000, page limit is
1–48. Case-insensitive name search is local. `group_id:null` means all groups.

Command payloads:

- `group_create`: `{name}`
- `group_rename`: `{id,name}`
- `group_delete`: `{id}`; members move to fixed `ungrouped`, originals stay.
- `group_reorder`: `{ids}` containing every group exactly once.
- `import_paths`: `{paths,group_id}`; paths are explicit absolute local files or
  directories, group_id is an existing ID including `ungrouped`.
- `material_rename`: `{id,name}`
- `material_move`: `{ids,group_id}`
- `material_remove`: `{ids}`; recoverable metadata removal only.
- `material_restore`: `{ids}`
- `material_reorder`: `{ids}` containing every active material exactly once.

Identifiers are 32 lowercase hexadecimal characters except fixed group
`ungrouped`. Names are trimmed, nonempty and at most 120 characters, with no
control/surrogate characters. SHA-256 is 64 lowercase hexadecimal characters.
Revisions are integers 0–9007199254740991. Every mutation is revision-CAS.

## Results

Snapshot: `{version:1,library_id,revision,groups:[{id,name}],order_ids,
counts:{active,trash,total},storage:{bytes,budget_bytes},limits:{max_active,
max_records,max_groups,max_import,max_object_bytes,max_pixels},warnings:string[]}`.

Page: `{version:1,library_id,revision,query,total,items,next_offset}`. Each item is
`{id,name,group_id,sha256,bytes,width,height,bits,format,has_alpha,created_at,
deleted_at}`. Format is JPEG/PNG/TIFF/BMP; bits is 8 or 16. Times are epoch
milliseconds; deleted_at is null for active rows. `next_offset` is null at end.
No complete pixels or absolute managed paths are returned in pages.

Thumbnail: `{version:1,id,revision,thumbnail_sha256,data_url}`. The data URL is a
bounded display-only PNG, maximum 256-pixel edge and 256 KiB encoded PNG bytes.
It must never be passed to the image/render/export owner.

Selection: exactly `{version:1,library_id,material_id,catalog_revision,sha256}`.
Selection alone does not mutate the photo. The ID consumer rechecks active-row
membership and exact catalogue identity/revision before and after full decode.

Mutation: `{version:1,library_id,revision,changed,counts,outcomes?}`. `outcomes`
appears for imports; rows are `{index,name,status,material_id,message}` with status
`imported`, `duplicate`, `trashed_duplicate`, `error`, or `cancelled`.
An import may retain successful earlier files and report cancellation for later
ones. Other mutations are all-or-none before publication. Refresh after success
to get current groups/order/page, rather than guessing locally.

## Admission and persistence

Own-file JPEG/PNG/TIFF/BMP only, at most 10,000,000 bytes and 32,000,000 pixels,
matching the first ID consumer. Existing ID decoder owns real PNG16/TIFF16,
orientation, ICC conversion and alpha handling. No new numerical implementation.
Compressed original bytes are copied without modification into content-addressed
objects. Thumbnails are separate. Full float images are not stored in the library.

Catalogue location: `LRT_BACKGROUND_MATERIAL_DIR`, otherwise
`$XDG_DATA_HOME/LumaRetouch/background-materials`, falling back to
`~/.local/share/LumaRetouch/background-materials`. It never shares or migrates the
colour sample catalogue. Default storage budget is 16 GiB; optional
`LRT_BACKGROUND_MATERIAL_MAX_BYTES` must be a positive bounded integer.

Application policy limits: 1000 files per import, 2000 active materials, 20000
rows including trash, 200 groups, 32 MiB catalogue. These are implementation
choices, not alleged competitor limits. Catalogue writes use flock, complete
validation, atomic replacement, fsync and an explicitly retained previous
catalogue. Corruption or unsupported versions fail visibly; no silent reset.
Removal never unlinks original objects, and no automatic garbage collector is
provided. Missing/changed managed objects fail; source files are never modified.

All source, UI, runtime, image and packaging acceptance is UNRUN.
