# Background-material native/UI boundary

Status: source authored, static review only. Runtime, compiler, typecheck, build,
unit, interaction, image, native picker, hardware and packaging acceptance are
UNRUN. No dependency, model, asset pack or sample photograph was downloaded.
The authoritative wire shapes are in `CONTRACT.md`.

## Scope and source ownership

This implements the local own-file management slice of `creative:165433`
([official requirement](https://www.pixcakeai.com/guide/165433)): user imports,
categories, name search, sorting, multiselect move, rename, recoverable removal,
restore and refresh. It is an independent catalogue, not the colour sample
library. It does not implement AI scene generation or redistribute proprietary
packs. The initial photo consumer is the existing ID background editor.

- `ui/src/backgroundMaterials/model.ts`: strict versioned result parsing and
  frozen stable selection identity; no host/native imports.
- `adapter.ts`: transport-neutral port, revision/query binding, read aborts and
  explicit unknown-write classification.
- `nativePort.ts`: four-request bounded native scheduling, one original send per
  ID, polling/cancel/release, retained unresolved IDs and retryable release-only
  cleanup. It never retries a mutation.
- `useBackgroundMaterialHost.ts`: App-lifetime pending owner, coherently refreshed
  header/page, cross-page explicit selections, captured caller, unknown-result
  review gate and stale-callback fences.
- `BackgroundMaterialHost.tsx` / `backgroundMaterials.css`: keyboard-accessible
  management/chooser region, native import controls, real metadata pages,
  IntersectionObserver-lazy display thumbnails, per-file import results and
  honest unavailable/error states.
- `ui/src-tauri/src/background_material_api.rs`: native command/control envelope,
  independent receipt mailbox, capability/epoch fence, native path picker.
- `model.unrun.test.ts` and Rust `unrun_fixtures`: authored, not executed.

No shared App, engine, registry or ID files are owned by these modules. Their
registration is performed separately by the integration owner.

## Exact UI integration

Import `useBackgroundMaterialHost`, `BackgroundMaterialHost`, and optionally
`BackgroundMaterialLaunch` from `./backgroundMaterials`.

Mount the hook once at App lifetime, outside the conditional retouch/ID panel:

```tsx
const materials = useBackgroundMaterialHost({
  enabled: liveEngine && backgroundMaterialLibraryProtocol === 1,
  targetKey: currentIdTargetKey,
});
// Always keep this owner mounted; the component manages its hidden state.
<BackgroundMaterialHost owner={materials} />
```

The key must be a captured current-photo/load AND ID recipe/edit context identity,
not just a filename. The owner does not fabricate canonical document revisions.
Opening/closing the catalogue must not change the key itself.

Management: `materials.show()`. Optional generic launcher:
`<BackgroundMaterialLaunch owner={materials} />`.

Selection from the existing ID tool:

```tsx
materials.show({
  targetKey: capturedIdTargetKey,
  onChoose: async selection => {
    // The consumer independently rechecks the captured document/recipe intent.
    // Send id_import_material through the existing ID background edit owner,
    // with {selection} and that owner's existing document/revision envelope.
  },
});
```

The callback receives exactly the frozen `MaterialSelection`:
`{version:1, library_id, material_id, catalog_revision, sha256}`. Unknown fields,
paths, data URLs and pixel arrays are rejected rather than stripped. Selection
alone does not apply a background or mutate a photo. The engine consumer must
resolve and revalidate the reference through its original-resolution image owner.

The callback is captured when the chooser opens and revoked on Close, newer
Show, target identity change, unsupported-engine transition or App cleanup.
After awaiting selection, the owner checks session, target, callback, enabled
state, abort, library identity, exact revision, material ID and SHA-256 before
calling it. It clears the capability before delivery to prevent a second click.
Any asynchronous work inside the callback remains the consumer's responsibility.

The optional `port` argument is for transport-neutral hosts/acceptance fixtures.
It must be stable for the App lifetime. Swapping a port/root mid-request is not
silently supported; a changed library identity fails visibly.

## Exact native integration

Register `background_material_api::background_material_library` and
`background_material_api::background_material_choose` with Tauri.

Lifecycle hooks:

- `reset(epoch)` when a new engine epoch is established.
- `ready(epoch, hello["background_material_library_protocol"] == 1)` only from
  the current engine's hello capability.
- `receive(epoch, &event)` for `event == "background_material_result"`.
- `ended(epoch)` after stdout drain on exit; any still-pending request becomes
  an explicit unknown terminal, not a failure/rollback assertion.
- `EngineHandle::cancel_background_material_library(id)` uses the existing
  complete-line cancellation writer with command
  `background_material_library_cancel`, never a second stdin owner.
- Use `background_material_api::read_only(&command)` as an early direct-queue
  exemption in both normal and interactive engine sends, before document,
  preview, capture or edit-intent invalidation. Here “read-only” means no photo
  mutation; catalogue metadata writes still follow the serialized engine owner.

Native invocation is `background_material_library({request})`, where request is
exactly `{action,request_id,request?}`. Status/cancel/release omit inner request.
Picker invocation is `background_material_choose({kind:"images"|"folder"})`.
No paths are guessed. Native picker returns local absolute paths only, with a
single-open guard; the engine validates files, folders, codecs and capacity.

The mailbox reserves bounded response memory before admission: 64 records,
16 MiB total, 8 MiB request/result ceilings. Thumbnail response budget is bounded
PNG base64 plus envelope; snapshots contain identities/counts, not all metadata.
IDs are retained as process-lifetime replay tombstones up to 65,536; exhaustion
refuses new requests instead of forgetting a previous mutation. Terminals are
never evicted to admit another request. Explicit release removes payload only.

Cancellation before admission records a negative-admission tombstone, preventing
a delayed invoke from starting after the UI timed out. Cancellation after
admission requests engine cancellation but keeps waiting for the actual terminal.
Unknown send/terminal outcomes never trigger a new ID with the same write. The
App keeps the pending write owner even while the visual panel is closed. A
fresh coherent header/page cannot unlock writes until every retained old write
has an actual terminal or verified pre-admission cancellation; the user must
then explicitly acknowledge the observed catalogue.

Known commits survive late abort and refresh failures. The latter produce
“operation confirmed; refresh incomplete”, keep per-file outcomes and disable
new writes until refresh. Release failures retain cleanup ownership without
turning a confirmed write into an error or repeating it.

## Runtime acceptance still required

1. Empty/new, populated, corrupt and unsupported-version catalogues; failed read
   must not display a fake empty success or silently replace data.
2. Real native file and folder picker; cancellation; duplicates; file limits;
   inaccessible, changed, symlink, malformed and unsupported inputs. Verify
   every input has an accurate result and originals remain byte-identical.
3. More than 48 active/trash rows: actual page traversal, query/order binding,
   complete counts, cross-page selections and full-target bulk moves/removals.
   No hidden full-catalogue metadata or pixel cache may accumulate.
4. Lazy thumbnail admission/release, scrolling, page changes and Close. Failures
   show metadata plus a reason; never a synthetic image or export fallback.
5. Group create/rename/reorder/delete, whole-order preservation, search and each
   sort. Deleting groups preserves members; removing materials remains recoverable.
6. Late replies across Close/reopen, new Show, photo switch, edit revision switch,
   disabled capability, App cleanup and React StrictMode cleanup/setup. An old
   choose callback must never apply to a new caller.
7. Lost enqueue/status/cancel/release responses; delayed admission; engine exit
   and restart; full mailbox; malformed or foreign-epoch receipts. No write retry,
   silent rollback assertion, receipt eviction or unbounded payload retention.
8. Partial import stopped between files, cancel after known commit, successful
   command followed by failed snapshot/page. Report truthfully and require fresh
   catalogue review without replaying the original command.
9. Strict selection reference across native/UI/ID consumer. Reject extra path or
   pixels, changed library/revision/hash, trash, missing originals and stale ID
   target. Preserve the existing edit/history/project/export owner.
10. Keyboard-only operation, screen reader labels/status/errors, focus restoration,
    large text, narrow layout, long Unicode names and confirmation dismissal.

These are acceptance obligations, not passed checks. Source/AST/hash review does
not establish native compilation, app launch, UI appearance or photo fidelity.
