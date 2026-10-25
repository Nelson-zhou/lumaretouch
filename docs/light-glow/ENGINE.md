# Light glow engine adapter

Status: **AUTHORED / UNRUN**. Only source reading and Python AST syntax parsing
were performed. No product import, test, native call, build, inference, install,
image download, type check or performance acceptance was performed. This document
is integration guidance, not evidence of executed photographic quality.

## Preserved reference and honest implementation scope

`ui/src/spec/creative.json`, creative:211524, preserves the official reference:
https://www.pixcakeai.com/guide/211524 (read 2026-10-25). The reference documents
black mist / white mist / glow modes, three presets per mode, editable strength,
radius, threshold, exposure, scattering and tint, plus a green affected-area view.
Its slider ranges are undisclosed. The local scalar ranges and presets are our
versioned calibration, not vendor parameter values. The implemented kernel is
original deterministic local finite-support diffusion, not AI lit-surface
segmentation, a neural model, physically proven refraction or vendor parity.

This adapter deliberately handles one currently owned photograph. Multi-photo
recipe application, original-image replacement, HDR and transparent photo return
are not exposed. The existing photo return pipeline accepts only opaque SDR;
unsupported canonical sources are rejected, never clipped or flattened. Native
RGBA math separately preserves premultiplied alpha, but this is not a claim that
that broader source domain is enabled in the photo workflow.

## Files and stable entry points

- `light_glow_native.py`: recipe admission; `native()`, `capability()`,
  `plans(width, height, settings, max_work_bytes=..., cancelled=...)` and
  `render(content, width, height, recipe, max_bytes=..., cancelled=...)`.
- `light_glow_source.py`: `capture_current(engine, budget=..., cancelled=...)`
  returns immutable `Source` and `Fence`; `require(source)` checks owned capture.
- `light_glow_stage.py`: `context(source, session_id, capability)`,
  `admit_source(source, budget)`, `prepare(command, source, budget=...,
  cancelled=...)`, `write_command(command)`, immutable `Candidate`.
- `light_glow_jobs.py`: `controller(engine).ingress(line)` and `.stop()`. Reuses
  the existing bounded event/identity coordinator, not the lens command route.
- `light_glow_host.py`: `handle(engine, request, emit)`, `read_only(request)`,
  `guard_other(engine, name, request)`, `invalidate(engine)` and
  `dispatch_rejected(request, message, started, emit, engine=engine)`.

No shared server, registry, Cargo root, build script, native dispatcher or UI
registration was edited by this adapter work. Those integration hooks must be
connected separately, keeping the feature unavailable until genuinely packaged.

## Required integration hooks

1. Package the separately built `core/light_glow` artifact as
   `engine/src/lumaretouch_engine/bin/liblrt_light_glow.so`. ABI is 1, math
   identity is `0x00010001` / 65537. Require the existing creative-layer native
   library too. A filename alone is never capability evidence: query ABI, math,
   all three struct sizes and both plan/render symbols. Do not auto-build.
2. Add the dedicated `light_glow` serialized engine command to dispatch
   `light_glow_host.handle`. The response event is `light_glow_result`.
3. Add `light_glow_jobs.controller(engine).ingress(line)` to reader ingress before
   serialized dispatch, and `.stop()` to engine shutdown. This ingress may set
   read/session cancellation events, never run image code or settle writes.
4. Classify only `current`, `preview`, `receipt` as read-only via the supplied
   function; preserve normal global admission guards. Add `guard_other` before
   unrelated mutation, and use `dispatch_rejected` for outer guard failures with
   the true `started` flag. Do not allow an uncertain copy write to be cancelled,
   replayed, hidden by teardown or bypassed by another tool.
5. Query `light_glow_native.capability()` for native/UI capability reporting.
   It returns the complete v1 capability object. It is safe to report missing
   module status; availability does not imply performance acceptance.
6. Add native request/status/cancel mailboxes independently from lens routes.
   Keep read outcomes and exact write receipts at engine lifetime, not panel
   lifetime. UI `LightGlowPort` is defined in `ui/src/lightGlow/model.ts`.
   A timed-out request must query its original outcome, never resend it as new.

## Wire v1

All request IDs, session tokens and owner identifiers obey
`[A-Za-z0-9_-]{1,128}`. Document revisions are unsigned 64-bit decimal strings.
Engine command envelopes have an exact shape:

- Current: `{cmd:'light_glow', action:'current', request_id}`.
- Preview: same keys plus `command`, action `preview`.
- Submit: same keys plus the exact apply/cancel `command`, action `submit`.
- Receipt: same keys plus the original exact apply/cancel `command`, action
  `receipt`. Its outer request ID may differ; inner original request ID must not.

Current success emits exactly `{event:'light_glow_result', request_id,
status:'ready', context}`. Failure/cancellation emits `status:'rejected'` or
`'cancelled'` and `message`. Unavailable capability rejects current acquisition.
Preview success emits `status:'ready', review`; submit/query success emits
`status:'ready', receipt`. The native mailbox can represent its own pending or
unknown read state while an operation is still running.

Inner preview, apply, cancel, context, review, capability and receipt fields match
`ui/src/lightGlow/model.ts`. Apply binds the issued candidate token, owner/session,
recipe hash, result source hash, full-resolution coverage hash, and SHA-256 of
all three actual presented PNGs. It also requires `reviewed:true` and
`return_mode:'new_image'`. No implicit original replacement is implemented.

Cancellation ingress supports either:

- `{cmd:'light_glow_cancel_read', request_id, request:<exact original current or preview envelope>}`;
- `{cmd:'light_glow_cancel_read', request_id, command_sha256}` using the digest
  issued/computed by this Python adapter, not cross-language JSON assumptions.

The digest is SHA-256 of `lrt-light-glow-host-command-v1\0` followed by Python's
ASCII canonical JSON. Prefer echoing the exact original envelope from native.
Session cancel is a normal serialized write command; its reader ingress signals
only the matching session. A successful cancellation receipt is emitted only
after preceding source work has actually unwound.

## Current edited source and evidence

`capture_current_asset` is called with a private job-local `AssetStore`,
`neutral_import_version=1`, `edited_capture_version=3` and
`allow_legacy_import_budget_fallback=False`. Existing full-quality export owns
active recipe, repaired pixels, geometry and all compatibility gates. The
version-3 strategy selects only its supported family; unsupported edits retain
the existing complete capture dispatch or reject. It is not a promise that every
24MP or RAW workflow fits the available memory budget.

The adapter reuses the existing exact file/document/people `_Fence` and augments
it with the real `creative_derived_repairs.stack_digest` for ordered active and
redo repair intent. Source evidence retains original SHA-256, people graph hash,
repair stack hash, document revision, load ID and a fresh capture token. It does
not rename original analysis as current-source analysis or claim a new model run.
A cheap hot fence polls object/revision/owner/file-stamp changes; cold fences
rehash original content, people graph and ordered repair evidence at operation
boundaries and immediately before the atomic new-copy transaction.

Shared `lens_blur_stage` helpers are reused **only** for immutable canonical
asset records, owner validation, bounded job admission and display-only PNG
projection. No lens render/depth path, photographic solver, alternate pixel math
or lens command is used. `Source` privately holds that immutable canonical source
plus glow-specific evidence; dictionaries returned to transport are copies.

## Numeric and memory ownership

`light_glow_native` matches `core/light_glow/ABI.md`. Settings are 56 bytes,
Geometry 32 and Plan 72. Plan `channels=9` describes internal scratch channels,
not the four RGBA input channels. The core owns halo/region calculation; the host
passes precisely the returned region from the original immutable full source.
Every output tile is at most 256×256. No already-written tile is read as input.

The host charges source/provenance retention, full-grid RGBA result, full-grid
coverage, canonical immutable freezes, bounded native region/scratch/private
transactional output, separate external tile outputs, display buffers, JSON and
receipt reserve. The core independently enforces its 512 MiB native working cap.
Allocation refusal does not cause image downsampling, narrower radii or another
filter. The final candidate always has the original captured full-grid extent.

Coverage is the native maximum absolute float32 premultiplied RGB change per
pixel. The bridge verifies it against returned pixels and source tile, and also
verifies finite unit range and unchanged alpha. Strength zero still requires the
installed core and must be bit-exact. The immutable coverage hash is SHA-256 of
little-endian float32 full-grid bytes. It is diagnostic and is never composited
a second time onto the completed output.

Before/after PNGs and coverage use the identical whole-frame source-centre display
grid, max edge 1280 and max one million display pixels. Final pixels are not
resampled. Coverage PNG is RGBA `(0,255,0,round(255*actual_coverage))`; zero coverage
is transparent. Its alpha is not a binary selection or an invented subject mask.

## New-copy transaction and uncertainty

Only `CreativeHost.commit_return` publishes the result, with `mode:'new_image'`.
The adapter creates a canonical one-base creative document from the reviewed
full-resolution asset; no second undo/history implementation or file overwrite
exists. It registers an unknown receipt **before** entering the transaction.
The receipt is made applied only after positive readback of a distinct new
canonical document, matching source family/path, full asset, creative document
contents and unchanged original revision. Failure after entry remains unknown.
Receipt queries may establish that positive proof but never execute the write.

Bounds are finite and non-evicting for write proof: 128 writes, 256 read identities,
64 sessions and 64 candidate tokens per session. Source and candidate lease expiry
releases transient data only. Uncertain writes retain their authoritative proof.
Service state must survive panel close; a restart with no receipt returns unknown,
not a fabricated rejection or permission to resend.

## Authored acceptance fixtures, all UNRUN

The `engine/tests/test_light_glow_*_unrun.py` files cover exact recipe/ABI inputs,
capability failure, native region/coverage/alpha/neutral/cancellation behavior,
private source capture and canonical return guards, immutable review and replay
semantics. Real-native cases require the separately built exact artifacts. Mock
or structural fixtures are not evidence of real numeric, visual or end-to-end
acceptance. Still required: actual native tests, Python tests, existing full source
regressions, UI/engine protocol tests, displayed image verification, undo/new-copy
flows, cancellation under load, original integrity, tile seam parity, memory/RSS
measurement and representative photographic review.
