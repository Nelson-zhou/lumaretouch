# Preset organisation: LNX-REF-WF-32459-bf14f4d6c1

Status: implementation and registration source complete, NOT ACCEPTED. No product execution,
tests, compilation, type checking, build, model inference or downloads performed.
Local runtime verification belongs to Qoder. Fixture cases are explicitly UNRUN.

## Evidence and scope

Manual baseline: `baseline_probe/manual-text.txt`, 管理预设; the supplied requirement
mapping row has phase P1, status 研究 and no acceptance cases. Official page
https://www.pixcakeai.com/guide/32459 was read on 2026-10-23 (page updated
2026-05-23). It confirms category/preset drag ordering, cross-category moving,
right-click rename/delete, and filtering by preset type. It does NOT specify
category deletion, collision semantics, storage schema or undoability.

Category CRUD, soft deletion/restoration, validation, revision fences, durable
receipts and keyboard alternatives below are Linux-original safeguards, not
invented official behavior. The manual's save-preset name limit is 20 characters;
organisation rename adopts this limit. Existing longer recipe names remain visible.

## Persistence contract

The existing recipe files remain byte-for-byte untouched by organisation edits.
A sibling `.organisation.state` file holds only stable preset IDs, category IDs,
manual positions, optional display-name overrides, deletion flags, generation,
and a bounded 128-receipt journal. This extension avoids the legacy `*.json`
recipe enumerator. Categories/rows use stable IDs, never labels as keys.

Write temp file in the same directory, flush/fsync, atomic replace, fsync parent.
Receipt and metadata change are one replacement. A root-specific reentrant
thread lock plus Linux flock serialise cooperating readers/writers, including
legacy recipe saves and deletes. Expected revision hashes generation, metadata
and the complete validated raw recipe catalogue. Concurrent/stale edits reject;
uncertain write results are queried by original request ID, never auto-retried.
Uncooperative external filesystem writers cannot be fully serialised by flock.

`preset_store.raw_list_all` supplies unprojected recipes. `list_all` projects
active names and persisted order into deep copies; `find`, apply, batch and other
existing consumers retain all modules/assets and use the same IDs. Import/export
package references are not remapped. Organisation metadata is local and is not
an invented XMP or cloud-sharing format. Saving over a trashed ID or a differently
named metadata alias refuses rather than silently destroying organisation state.
Legacy `delete` now trashes metadata and retains the original recipe path.

Empty categories persist. Only empty custom categories can be trashed; any
active, trashed or offline recipe reference blocks category deletion. Missing
recipe IDs remain visible as offline references, never silently pruned. Restore
uses the original ID and category/order. System categories cannot be renamed or
trashed. Built-in presets can reorder within their category but cannot rename,
move to custom categories, or be deleted. Custom entries cannot enter builtin.

Names trim then normalize NFC; 1–20 Unicode code points, no Unicode control or
format characters. Active category names are unique by casefold. Preset rename,
move and restore reject casefold collisions within the destination category.
Grandfathered duplicate names from existing imports remain readable, not silently
renamed. Type filtering is a view only and uses actual recipe `kind` values;
reordering operates on unfiltered sibling positions and never discards hidden IDs.

Catalogue edits are not photograph edits: they do not create image undo records
or alter image recipes. Trash has explicit restore, not permanent purge. Reverting
an ordinary move/rename is another revision-fenced catalogue operation.

## UI and native contract

`PresetOrganisationPanel` is mounted in the real PresetPanel. It provides drag,
keyboard up/down buttons, destination selector, inline rename/create forms,
right-click/More actions, type filter, empty states and restore. Native confirmation
is used before trash. No optimistic catalogue mutation is shown as completed.
Native commands are `preset_organisation` and `preset_organisation_result`;
engine command/event are `preset_organisation` / `preset_organisation_result`.
A separate mailbox validates protocol/identity; epoch reset/end invalidates stale
receipts. The UI validates category references/order and refreshes from the engine
only after durable completion. Uncertainty blocks further edits until queried or
explicitly inspected; missing receipt is never taken as proof of non-execution.

## Registration integration map (applied; source inspected only)

- server.py: import PresetOrganisationHostMixin; add Engine base and HANDLED name;
  ready capability `preset_organisation_protocol: 1`. `_process_line` must call
  this command and return before any photo/capture/preview/history invalidation.
- main.rs: declare `mod preset_organisation_api`, register both native commands.
- capture_lifecycle.rs: reset_capture_hosts calls module `reset(epoch)`.
- engine.rs: call module `ended(epoch)`, route event via `receive(epoch, &v)`,
  advertise mailbox support via `ready(epoch, capability == 1)`.
- EngineHandle send/send_interactive: exempt this metadata-only command from both
  sample-library and semantic-colour capture invalidation paths.
- Shared source integration also covers preset_store.py, preset_controller.py,
  PresetPanel.tsx and usePresetWorkflow.ts. Registration hooks above are applied.
  Native compilation and runtime reachability remain UNRUN.

## Verification, rollback and limitations

See `fixtures/preset_organisation_acceptance.json` for 18 UNRUN workflows including
installed native entrypoint, crash/disk failures, keyboard access, stale revisions,
source corruption, asset hashes, import/export and cross-process interleavings.
Static parsing is not behavior evidence. No screenshots or runtime pass claimed.

Rollback code changes only after retaining the sidecar and user recipe files.
Old versions ignore the sidecar, so trashed presets become visible again with
original recipe names and filename order; this is recoverable, not data deletion.
Do not purge user data as a rollback step. No permanent-delete API is provided.
