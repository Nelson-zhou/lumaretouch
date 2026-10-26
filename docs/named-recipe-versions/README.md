# User-named recipe versions — source implementation, runtime UNRUN

## Reachability and meaning

The mounted Retouch history panel has a **命名配方版本** section when the engine
advertises `named_recipe_versions_protocol: 1`. Read the catalog, enter a name,
create a checkpoint, rename a checkpoint, or select a checkpoint to restore it.
Save the project after these operations. Names are explicit user labels; the
system document revision, retained history ordinal, virtual-copy identity and
whole-project recovery snapshot are not substituted for a named version.

A selected checkpoint is recalled into the existing mutable working recipe.
The immutable named row **never becomes** `_project_version_id` or
`active_version`. Later edits/save/autosave cannot overwrite its recipe or
snapshot. Rename changes the label only. There is no delete/prune action.
Selection is a new canonical history edit (normal no-change history behavior
applies), not a revision rewind. Undo/redo does not delete named versions.

## Canonical storage and safe recall

- Named rows live in the existing project document `versions` list. `recipe`
  stays an ordinary complete recipe; `named_recipe_snapshot` is a versioned,
  document/source-bound metadata record containing a canonical encoded history
  frame. Arrays/assets use `PJ.encode` and the existing project asset table.
- Normal project build/recovery already retain inactive rows and all canonical
  assets. `PJ._migrate` owns a deep copy of the full tree; existing recursive
  validators see both recipe and frame. Named reads validate the exact metadata
  tag; recall validates the ordinary active-recipe codec on a staged project,
  decodes the frame, checks complete field and recipe agreement, then uses the
  canonical `_history_restore_frame` and `HistoryController.record`.
- Current people/support banks are serialized by the existing `_people_save`,
  **inside** the admitted mutation fence. That serializer refreshes ownership
  bookkeeping; failures are unknown, not false prewrite rejections. The exact
  document revision advances once. No hand-written parallel graph serializer.
- `PJ._prepare_save` checks canonical manifest/blob budgets before publishing a
  new checkpoint project. Precompute tensors are not checkpoint-owned; accepted
  user assets and existing canonical portrait support stores remain retained.
- `project_package_dependencies.inventory` recursively traverses the whole
  project for external sky bindings; its summary and archive include the full
  asset table. `creative_document_storage._references` recursively sees nested
  metadata and `pack` retains every referenced active/inactive creative blob.
  Virtual-copy creation copies live state/history ownership, not another
  document's named catalog; selection always binds `document_id`, not path.

## Explicit protected refusals

Recall refuses a different proxy size, effective creative source, people-history
presence, changed association fence, changed effective shared-person/group
context, or a same-source shared portrait alias. The source-context digest is
checked **after staging the local portrait restore**, so ordinary local changes
can be recalled while unrelated inherited shared changes cannot be silently
kept, globally rolled back or unlinked. This is not a full shared-version restore.
Old untagged project versions are preserved, not silently promoted into complete
named-history checkpoints.

At most 128 named entries, names at most 160 UTF-8 bytes. The escaped catalog and
full prospective applied receipt (using the server's ASCII-escaping JSON codec,
exact original request and maximum reached counters) must fit the existing 32KiB
native raw-receipt parser **before** mutation. Read envelopes are checked too;
error text is byte-budgeted without truncating request/proof identity. Existing
project manifest/creative-blob limits also apply. No versions are evicted to fit.

## One transaction/receipt owner

Explicit `named_state`, `named_create`, `named_rename`, `named_select` variants
extend the existing `history_navigation` namespace, native mailbox and UI owner.
They retain exact request/workspace/document/load/revision/history-digest plus
catalog-digest binding. Old `navigate` validation/ordinal semantics are unchanged.

Named phase envelopes are exact. Applied rename must include the requested
ID/name; applied select must retain the requested catalog digest and ID. Unknown
or rejected outcomes cannot carry a stale current view/catalog. Mutation
exceptions retain the existing engine/native/UI fences; querying does not resend.
Only the existing strict duplicate-key-rejecting raw open proof and later idle
observation/new engine can authorize explicit abandonment. Panel close or UI
remount cannot abandon the shared pending request.

## Authored verification (not executed)

Fixtures: `engine/tests/test_named_recipe_versions_unrun.py`,
`ui/src/namedRecipeVersions/model.unrun.test.ts`, and the named fixture module in
`ui/src-tauri/src/history_navigation_protocol.rs`. Python source AST parsing only
was performed. No test, build, typecheck, app execution, inference or install.

Required future runtime cases: create A → edit → create B → select A → undo/redo;
rename → manual save/open; recovery snapshot/open; package round trip with accepted
assets and external references; independent same-source virtual copies; metadata
limits/escaped Unicode; source/proxy mismatch; shared-context drift and absent
portrait proof; error before/after serializer, restore and frame publication;
timeout/process loss/panel close/remount; old retained-step navigation regression.
Runtime/quality/performance acceptance remains **UNRUN**.
