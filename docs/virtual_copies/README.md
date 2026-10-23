# Virtual copies and linked trash/restore

Implementation status: authored; runtime acceptance **UNRUN**. No tests, builds,
compilers, product imports, image inference or application launches were used in
this development pass. Static Python AST/JSON/source inspection is not acceptance.

## Exact baseline

- LNX-REF-WF-3YX3UbkTVp-89e052113b — 虚拟副本
- LNX-REF-WF-3YX3UbkTVp-10e78f2d5f — 虚拟副本创建
- LNX-REF-WF-3YX3UbkTVp-acad6e50de — 副本删除恢复

All are P1 in the supplied AI requirements mapping, source
https://www.pixcakeai.com/guide/3YX3UbkTVp. Supplied handbook sections 244–256 and
920–921 establish gallery/retouch right-click, Ctrl/Cmd+apostrophe, batch creation,
current edits and metadata inheritance, adjacent same-source numbered groups,
root-delete cascade, and copy-restore restoring the root. The live PixCake page
was not retrievable during this pass; these semantics are from supplied material.
The commercial source's billing rule is not a local charging implementation.
There is no invented vendor copy-count limit. No duplicated source raster does
not mean zero metadata, undo, retained evidence, or memory overhead.

Mature primary references checked during research:
- https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/photos.html
- https://docs.darktable.org/usermanual/5.6/en/module-reference/utility-modules/darkroom/duplicate-manager/

## Data contract

Project v23 separates persistent document_id, source_asset_id, root_document_id,
copy_number and recipe_version_id. Runtime revision is monotonic and separate
from undo. Session/load tokens remain ephemeral presentation fences and are not
substituted for canonical document IDs. The source_assets table owns full-file
content evidence and a replaceable location, never source pixels. Byte-identical
independent imports are not merged. Same-path rows are legal only as explicitly
linked source-family members. Ambiguous path-only calls fail rather than choosing
a sibling's recipe.

Legacy v1–v22 IDs are deterministic UUID5(project identity, original path, kind).
Reopening an unsaved legacy project yields the same IDs; saving upgrades to v23.
The v22 identity migration does not reinterpret nested recipe provenance. Earlier
schema migrations retain their existing feature-specific rules. Source relocation
updates every family member and the source table after full SHA verification,
preserving historical path/full-hash aliases, graph evidence and recipe records.

A new virtual copy deep-copies current committed edits/metadata and receives new
canonical document/recipe identities, empty independent undo/redo and its own
people graph context. Originals retain the existing explicitly linked cross-photo
people graph. Face/source hashes and accepted support provenance are not renamed.
Per-document graph contexts isolate same-source copy edits and retained supports.
New independent imports with byte-identical content also receive private graph
contexts. Existing legacy byte-identical original rows intentionally keep their
historical shared associations/coupling; migration does not silently rewire them.

Trash original: all linked copies also enter trash. Trash copy: only that copy.
Restore copy: root + selected copy. Restore root: root only. Source files are
never moved, overwritten or deleted by these actions. Actions are idempotent
within a workspace; receipts are retained in the project when explicitly saved.
A lost unsaved operation after engine restart is unknown, not automatically replayed.

Exports freeze document-specific recipes/people contexts. Task item identity is a namespaced hash of the
canonical document ID, separate from source path; numbered copies use stable
copy-number/document-ID-hash filename suffixes with UTF-8 byte budgeting. Retries reuse the original task keys
and frozen recipes; restored tasks do not silently substitute current recipes.

## Qoder acceptance, all UNRUN

1. Open each legacy schema fixture, save/reopen v23, compare all image/editor/
   face/body/mask/recovery/preset/LUT records and accepted asset hashes. Verify
   stable document/recipe identity and active version; unsaved repeated legacy
   reopen must also be stable. Reject duplicate IDs, orphan copies, contradictory
   source fingerprints and unsupported schemas without replacing live state.
2. Import RAW/JPEG/TIFF with full effects, tags, stars, flags, manual strokes,
   object masks, layers, retained face/body analyses and undo. Create single,
   batch and copy-of-copy from gallery context, retouch context and shortcut.
   Confirm monotonic numbering, original-adjacent groups, no source file created,
   and unchanged original file SHA/mtime. New-copy undo starts empty.
3. Change every copied editor class and person/group override independently;
   inspect original, copy A, copy B and unrelated source after each change. Undo/
   redo, switch views, compare, full-size inspection, restart and re-open. Retain
   original explicit cross-photo links; test confirmed scalar batch transfer
   into two same-source copies and protected batch undo/redo.
4. Keep a pending preview/capture or background export, then attempt copy/trash.
   Ensure clear refusal or defined token invalidation, never tentative recipe
   capture, late preview publication, wrong-copy edits or stale full-view pixels.
5. Trash root and verify every sibling, then restore just one copy: root and that
   copy only return. Repeated requests, repeated clicks, stale revisions,
   selection changes, cancel review, lost reply and workspace restart must not
   create extra copies or alter unreviewed family members. Trash the displayed
   image and ensure editing/capture/viewport state is invalidated.
6. Save with arbitrary current copy; reopen that copy with its independent tags,
   recipe, history and people context. Scan unrelated directories with an unsaved
   copy family: no orphan or silent path deduplication is allowed.
7. Move source file; relink one family member through full-hash preview. Every
   member updates atomically. Save/restart and verify aliases continue to protect
   retained history. Wrong bytes, changed candidates, symlinks, external project
   edits, cancellation and uncertain post-replace fsync must remain protected.
8. Select original plus multiple differently edited same-source copies, export
   JPEG/PNG/WebP/TIFF8/TIFF16 with watermark/layout, and compare each expected
   recipe. Check stable distinct names, per-copy success badges, retry only failed
   IDs, readback receipts and zero source modification. Exercise missing files,
   source-content drift, conflict policies and partial export failures.
9. Regress library multi-axis filters/sorts/selection, presets and organisation,
   ordinary batch sync, reference/semantic colour, source relocation, old
   no-copy project behavior, IPC restart, image loading and all existing suites.

No desktop visuals, timing, pixel correctness, full-suite compatibility, native
compilation or performance claim has been verified. Qoder must report actual
command outputs and screenshots before any acceptance status changes to passed.
