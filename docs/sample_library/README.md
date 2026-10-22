# Local sample/reference-photo library

Status: source implementation with registered engine/native/App/RetouchPanel integration.
This is NOT runtime acceptance or completion of the whole AI colour family.
No product import/execution, compiler, build, typecheck, unit test, inference, model download,
or photographic acceptance was performed. Qoder owns runtime verification.

## Exact scope and evidence

Baseline: `baseline_probe/manual-text.txt:595–603` and
`AI开发资料包/功能需求验收映射.json`.

- `PC-32452-C-af312f51a2`, `LNX-REF-PC-32452-C-af312f51a2`: custom sample import.
- `PC-32452-C-9ac5aa4d79`, `LNX-REF-PC-32452-C-9ac5aa4d79`: import samples.
- `PC-32452-C-831245a683`, `LNX-REF-PC-32452-C-831245a683` and
  `PC-32452-C-faf6a4e2e8`, `LNX-REF-PC-32452-C-faf6a4e2e8`: create a sample from the current rendered result.
- `PC-32452-C-710056cf5d`, `LNX-REF-PC-32452-C-710056cf5d`: manually select a suitable local sample.

Primary sources verified 2026-10-22:

1. [PixCake official AI colour guide](https://www.pixcakeai.com/guide/32452), updated
   2026-09-17: local sample import/capture and management, grouping, multiselect move,
   drag sorting, rename/delete, 1000 per import and 2000 active samples. Only this local
   management sub-scope is implemented. The guide's official cloud library, semantic
   AI, model choices, precise parameter inversion, local dual masks, recommendations
   and style engine are separate, unimplemented requirements.
2. [digiKam album workflow](https://docs.digikam.org/en/left_sidebar/albums_view.html):
   folder/file import, multiple-photo moves, album organization and recoverable trash
   are established open-source UX practices. This implementation is original code,
   not a copy of digiKam source or artwork, and uses logical groups rather than moving
   the user's source folders.
3. [Pillow's upstream license](https://github.com/python-pillow/Pillow/blob/main/LICENSE):
   MIT-CMU. Pillow is already a repository dependency; no newly vendored dependency,
   model or sample photograph was introduced. Existing NumPy/TIFF/imagecodec packages
   and reference assets retain their repository notices. An application's or decoder's
   code license is never taken to license example photographs.

Default catalogue is empty. The user imports their own material. There is no network,
stock-photo scraping, commercial sample copying, uploaded-photo service or presumed
photo licence. No AI追色 or PC-32452-family completion claim is justified by this module.

## Source ownership

- `sample_library_state.py`: strict versioned schema and capacity/name/identity invariants.
- `sample_library_store.py`: cross-process flock, optimistic revision, atomic JSON/fsync,
  previous-catalogue recovery copy, immutable object checks and local byte accounting.
- `sample_library_images.py`: bounded folder walk, descriptor-checked original copy,
  metadata and display thumbnails, deferred original-resolution full decode.
- `sample_library_controller.py`: operations, per-file results, manual select, trash/restore.
- `sample_library_query.py`: bounded metadata pages, revision/query-pinned cursors, full counts and small mutation receipts.
- `sample_library_capture.py`: original-resolution render through existing full export
  owner with independently owned read-only output, source/version/state rechecks.
- `sample_library_command.py`: strict narrow engine-command port.
- `sample_library_host.py`: registered mixin, bounded terminal receipts and cancellation-only reader ingress.
- `command_reader.py`: genuine extraction of existing selectable stdin/backpressure ownership.
- `ui/src-tauri/src/sample_library_api.rs`: Rust protocol/receipt validation, bounded epoch-bound mailbox,
  explicit terminal release, native local file/folder picker and capture intent fencing.
- Existing native dispatcher/engine writer: atomic complete-line writes shared with a cancellation-only
  control lane, without bypassing the serialized edit queue for any actual operation.
- `ui/src/sampleLibrary/`: accessible manager, native adapter, App owner and reachable launcher.
  Existing App navigation is genuinely extracted to `WorkspaceTopbar.tsx` to respect the file cap.
- `engine/tests/test_sample_library.py`: authored fixtures, not executed.

Catalogue/storage orchestration stays with existing Python filesystem/codec owners.
It does not introduce a second colour implementation. Existing reference math/render
kernels remain Rust-backed where already implemented. The native protocol, safe picker, receipt lifecycle and queue/control writer are Rust.
No decorative Rust shim, extra colour operator or new native build dependency was introduced.

## Storage and preservation

`$LRT_SAMPLE_LIBRARY_DIR`, or `$XDG_DATA_HOME/LumaRetouch/sample-library` (fallback
`~/.local/share/LumaRetouch/sample-library`). Linux is the target; flock is intentional.

- Original compressed files are copied once, byte-for-byte, by SHA-256. No persistent
  float32 expansion occurs on import. Original names become editable display labels;
  filesystem paths never derive from those labels.
- JPEG/PNG/TIFF/WebP single-frame imports, maximum 256 MiB and 32 million pixels each;
  folders are capped at 10000 visited entries / depth 16 before import, with at most
  1000 image candidates. Symlinks are not followed. New samples are deduplicated by
  original bytes; duplicates in trash point to the recoverable row instead of duplication.
- 384-pixel JPEG thumbnails are explicitly 8-bit display-only, never calculation input.
  Source bit depth is recorded; PNG IHDR is checked because Pillow's RGB mode alone
  does not prove 8-bit input. Full selection refuses unsupported PNG16/transparency/
  unconverted ICC-bearing RGB16 rather than silently discarding precision or alpha.
- Selection expands one admitted full reference through the existing decoder and
  `reference_color_assets.save/load`, preserving stable source/render/asset identities.
  Imported-source support matches an unedited document's interior pixels (two-pixel
  boundary excluded). It is pipeline support, NOT proof of an untouched camera scene.
  External-import provenance remains explicit. Same-scene matcher admission still
  requires its geometric/photometric evidence; selecting a photo applies no effect.
- Full current-result capture uses `reference_color_engine.render(reference=True)`:
  original decode, current effects, actual geometry/crop and known source-support
  exclusions, without export-only upscaling/sharpening. It refuses unsupported render
  state or missing provenance instead of silently dropping effects. No screenshots,
  proxies or camera-preview substitutes are accepted.
- Admission measures library bytes plus the entire existing shared reference cache
  against a configurable policy, default 16 GiB (`LRT_SAMPLE_LIBRARY_MAX_BYTES`, a
  positive integer byte count), including trash, local orphans and unindexed/shared NPZ resources.
  Thus other projects' reference bytes count conservatively, but counting never grants
  deletion rights. Owned usage and shared-cache totals are reported separately. Full-reference
  admission reserves the actual float RGB/support canvas plus ZIP overhead, not merely
  its expected compressed size; the compressed-file acceptance limit is 256 MiB. Resource
  directory renames are fsynced before publishing catalogue references. CPU memory is
  independently admitted using the existing fail-closed available-memory estimator.
  Writers outside this library do not participate in its lock: admission is a checkpoint,
  not an application-wide cross-process quota reservation service. Actual filesystem free
  space is checked separately before copies/reference saves/catalogue writes, retaining
  a 32 MiB recovery margin. Both filesystems are reported if library/cache differ. A racing
  ENOSPC remains possible and does not justify retrying an uncertain atomic replacement.
- Removing a sample only tombstones its row. Restoring is explicit and subject to
  the 2000-active cap. Trash is never auto-evicted; 20000 retained rows / 200 groups /
  32 MiB catalogue are defensive limits, separate from the official active count.
- Originals, thumbnails and shared project/preset reference bundles are never reclaimed
  by removal. `reclaim_plan()` is a read-only orphan report and returns
  `safe_to_delete:false`; global reachability and permanent reclaim are not implemented.
  Thus deleting samples frees active slots but does not promise immediate disk recovery.
- Catalogues use atomic compare-and-swap revisions under a process lock. Unknown schema,
  corruption, symlink targets, conflicting revision, full disk and missing resources
  do not silently reset the library or replace the user's originals. A failed commit
  can leave unindexed immutable objects; they are preserved and included in accounting.
  Post-rename durability errors retain uncertain-outcome metadata and must not auto-retry.
  Read-only metadata uses an inode/size/mtime/ctime-validated cache under the same lock;
  visible thumbnail reads do not reparse/copy the entire catalogue for every card.

## Host integration contract

The engine advertises `sample_library_protocol:1` and dispatches `sample_library` on its
existing serialized command thread. Library metadata reads do not invalidate unrelated
editor previews, enter edit history, or dirty projects. Heavy library work refuses overlap
with known export/inspection/preview workers. Current-result capture also refuses unconfirmed
preview sessions rather than capturing different committed parameters under a preview label.

The Rust command `sample_library` accepts `{request:{action:'request',request_id,request}}`;
`status`, `cancel`, and `release` accept `{request:{action,request_id}}`. Acceptance is only
`phase:'pending'`; terminal `phase:'done'` contains the backend success/error envelope.
Known-not-applied and unknown outcomes are distinct. The 64-entry/16-MiB native mailbox
reserves bounded payload capacity, rejects overload without silent eviction, and keeps terminal
receipts until explicit release. The UI releases processed payloads, limits concurrency to six,
and never automatically replays writes after timeout, malformed receipt, or engine restart.
A bounded native process-lifetime seen-ID set prevents replay even after payload release.
Pre-admission cancellation tombstones fence delayed Tauri invocations that arrive after an
initial timeout/unavailable response; uncertain UI writes remain blocked until that fence
and the retained terminal status can be reconciled.
Thumbnails use separately bounded verified JPEG data URLs, not arbitrary filesystem URL access.

`sample_library_choose` uses the existing local dialog plugin, only absolute UTF-8 local paths,
up to 1000 selections and an 8-MiB request budget. No selected photos are uploaded. The original
file descriptor and content validation still happen inside the library owner, not in the picker.

Cancellation-only stdin controls share the native writer's complete-line mutex, bypassing the
acknowledged edit queue without bypassing serialized mutation. The reader only sets Events and
retains early cancellations that can overtake queued requests. Native edit/navigation intent
cancels pending current-result captures before entering that queue. Cancellation is checked
before decode, through existing export progress checkpoints, and immediately before catalogue
rename. An individual decoder/operator may finish its current non-interruptible step first.
Import cancellation retains already completed files and reports the rest individually.
A late cancellation is not proof of rollback. Shutdown and uncertain writes preserve resources;
refresh/reconciliation requires checking retained receipts, not resubmitting the operation.

- `{method:'snapshot'}` returns a bounded header: groups, revision, capacity, storage,
  truthful global/group active/trash counts and active `order_ids`; no full sample metadata.
- `{method:'page',query:{view,search,limit,cursor},expected_revision}` returns bounded
  `{revision,samples,total,offset,limit,next_cursor}`. Limit is 1–100; UI uses 48.
  Cursor pins revision plus normalized view/search/limit. Stale pages require an explicit
  header refresh, never mixing revisions or truncating a catalogue silently.
- `{method:'context'}` returns current canonical document ID/revision, available/label/key,
  and separate `load_id`. App `doc.document_id` is the viewport load identity, NOT the
  canonical document ID. The UI compares `load_id` to it and submits only canonical
  ID/revision for capture. Neither is replaced with unrelated viewport `doc_rev`.
- `{method:'thumbnail',id}` returns `{data_url}`.
- `{method:'command',op,payload,expected_revision}` returns small
  `{revision,affected_ids,capacity,counts,group_counts,outcomes?}` terminal receipts;
  the UI refreshes its header/current page after durable success, not the whole library.
  Import cancellation stops remaining files and commits completed successes; it is not
  rollback. Other mutations check cancellation immediately before atomic publication.
- `{method:'select',id,expected_revision}` returns the small receipt plus `{sample_id,reference,notice}`;
  selection can increment revision when materializing a missing immutable reference.
- `{method:'capture',name,group_id,expected_revision,expected_context:{document_id,revision}}`
  returns the small receipt plus `{sample_id,reference,duplicate,archived,capture}`. Evidence contains canonical document
  ID/revision/state key, rendered SHA, source kind and original-resolution status.
- `{method:'reclaim_plan'}` is read-only and must not be presented as deletion permission.

Operation payloads: group_create `{name}`, group_rename `{id,name}`, group_delete `{id}`,
group_reorder `{ids}`; import_paths `{paths,group_id}`; sample_rename `{id,name}`,
sample_move `{ids,group_id}`, sample_remove `{ids}`, sample_restore `{ids}`,
sample_reorder `{ids}`. Reorder requires the complete authoritative active ID sequence,
not just a filtered page. Selected off-page IDs are retained explicitly; visible-page
metadata is not the global selection or count. `ungrouped` is fixed. Deleting a custom group moves its active
and trash items into ungrouped without deleting their content.

The top bar exposes sample management even before opening a photo, and RetouchPanel exposes
local sample/reference controls instead of presenting presets/LUT as the entire PC-32452 family.
Unrelated preset/LUT controls remain available; remaining AI/cloud/operator gaps remain
visible. App's `sampleLibrary` owner exposes frozen `selectedReference`, `setSelectedReference`
and `clearSelectedReference`; it is a reference choice, NOT a successful colour-transfer result.
Late selection is fenced to its target load identity. Existing same-scene consumers may use
this immutable reference only through their normal review/admission. A future creative colour
operator must have its own verified semantics, masks, review and undo integration.

## Acceptance still to run (Qoder)

1. New empty library, reopen persistence, two app instances, stale writes, disk-full,
   atomic replace/fsync failure, main corruption and explicit backup recovery. Exercise configurable
   admission, shared unindexed bytes, real free-space exhaustion and separate filesystems.
2. One and multiple JPEG/PNG/TIFF/WebP, duplicate bytes/names, source replaced during
   read, unreadable/symlink/special file, corrupt/animated/huge image, deep directories,
   1000 versus 1001 entries and exactly 2000 active rows; per-file errors preserve successes.
3. RGB16 near-level precision and source hash retention; PNG16/alpha/ICC refusal on
   selection is explicit. Inspect memory/disk growth across 2000 compressed originals.
4. Group rename/delete, cross-group and cross-page multiselect move, drag order and keyboard/button
   equivalents, 2000-active/large-trash pagination, stale cursor/query rejection, full-order
   reordering, truthful counts, repeated clicks and loading errors.
5. Remove/restore before and after reference selection; reopen projects/presets using
   removed samples and verify immutable NPZ presence. No destructive GC occurs.
6. Frozen current effect with RGB8/16, crop, optics, manual and all-person geometry,
   known repaired/replaced footprints, source replacement, edit/navigation during capture,
   abort/close at each stage, late success versus uncertain failure and full-resolution pixels.
7. Native routing, protocol/receipts, packaged runtime resources, accessible keyboard/focus,
   engine restarts, lost acknowledgments, terminal release, mailbox/ID capacity, early cancellation,
   control writer failure, load-ID versus canonical-ID separation and full reference selection.
   No full-resolution reference viewer is supplied; the manager displays explicit thumbnails.
   These outcomes are not proven by AST.

The manifest records only authored source bytes. Neither its hashes nor AST parsing
constitutes compile, integration, image-quality or end-user acceptance.
