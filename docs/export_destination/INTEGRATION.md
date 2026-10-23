# M09 export destination workflow: shared wiring authored, acceptance UNRUN

Shared integration base: 0cbffbabcbed16afa389ebf7382d5c249fb0f2f0 (project v23,
per-document/copy export queue). Implementation status is SOURCE-WIRED, NOT VERIFIED.
No application, engine, renderer, tests, compiler, typechecker, build, inference or
export has been executed. No Git mutation was performed. Do not mark M09 accepted.

## Exact source mapping

- LNX-REF-WF-32563-8139388436: 多目录导出.
- LNX-REF-WF-32483-30b6eae726: 导出设置与资源竞争.
- LNX-P0-EXPORT supports the existing original-protection/encoding requirements.

Official sources directly opened on 2026-10-23:
https://www.pixcakeai.com/guide/32563 (updated 2026-05-23), lines 123–136 describes
source-folder subfolders and retaining imported folder naming/hierarchy at a chosen
location. The imported leaf root, rather than a guessed common ancestor, names the tree.
https://www.pixcakeai.com/guide/32483 (updated 2026-06-18), lines 76–91 describes the
source/chosen location choices, project/source-folder naming, and hierarchy option.
The main guide and FAQ use different UI wording. We expose separate controls.
Stable root collision suffixes, copy-ID allocation, local receipts and no-clobber
publication are Linux safety design, not claims about undocumented PixCake behavior.

## Actual entrypoints and data flow

1. App.tsx library button -> native choose_import_folder -> session add ->
   export_destination_import.expand. Recursive folder imports retain the chosen root
   and internal relative path; symlink directories/files are not traversed. Overlapping
   roots in one request reject rather than silently changing hierarchy. Subsequent
   folder additions preserve prior imported roots; rescan retains directory imports.
2. server._new_row stores import_origin {schema_version:1,root,relative,kind}.
   virtual_copy_session assigns the explicit folder origin only to newly imported rows.
   virtual_copy_project saves/restores it; virtual_copy_storage validates it on project
   read and preserves it through copy/relocation. Existing v23 files stay readable:
   missing provenance is explicitly tagged legacy_parent, and the preview warns that
   their original import root was not recorded. Physical relocation never rewrites the
   logical import root or relative hierarchy. Source-folder exports use the current path.
3. App export settings mount ExportDestinationPanel. It shows source/chosen root,
   subfolder naming, hierarchy, creation permission, rename/skip/review collision choice,
   explicit cross-directory layout destination and per-file preview. Start requires a
   current preview. Option/selection/edit/workspace changes invalidate it; repeated
   preview/submit is guarded. Existing curve edit barrier is settled first.
4. exportDestinationApi -> real invoke -> export_destination_port Rust handlers ->
   Engine.cmd_export_destination -> cmd_export(action=preview). All existing export
   options and selected-document recipes are validated/frozen by the real export path.
   Preview returns before mkdir, task creation, worker start or rendering. Native
   requests are engine-epoch fenced, bounded and released; requested:true is not success.
5. export_destination_runtime.build creates a plan using the authoritative per-copy
   document entries, source fingerprints, workspace/document revision/recipe receipts,
   exact encoding/ICC/GPS/compression/watermark/layout settings and actual target filenames.
   Multiple roots with the same leaf remain distinct. Source/virtual-copy IDs are never
   replaced by a root name or source path as queue identity.
6. Native runExport carries destinationPolicy/destinationPlanId/intentRevision to the
   real export command. Start regenerates the plan and requires identical plan_id;
   changed files, settings, revisions or output occupancy require another preview.
   Ask/review collisions block start until the user chooses rename or skip in the same
   product settings. Replacement is deliberately not offered, even for export files.
7. The exact plan enters opts, _export_args and T.new_task.inputs before worker start.
   Both RGB16 branches and the RGB8 writer use runtime.primary_target and runtime.run.
   The context owns only the frozen destination plan; it does not fetch live edit state.
   export.resolve_target obeys planned skip/write disposition and refuses a raced-in
   existing target instead of renaming again. Retry compares retained and persisted plans,
   keeps the original target and preserves the existing recipe_persisted restart guard.
8. watermark_delivery uses separately reserved clean variants instead of synthesizing
   a new path from a renamed primary. It creates no destination folders outside the
   canonical publisher in a planned export. Partial committed outputs survive errors.
9. layout_delivery reserves all pages, PDF and manifest before queue start. Chosen-root
   mode uses the chosen directory; source mode with multiple directories requires an
   explicit layout_root, never an arbitrary first source directory. Planned layouts use
   fixed paths, no-clobber per-artifact publication and manifest-last ordering. Any skipped
   layout target skips the whole layout set; failed/skipped photo outputs cannot be
   replaced with old files. Partial page publication remains visible on failure.
10. export._atomic_write, shared by RGB8 and RGB16 codecs, now calls canonical
    export_destination_commit.commit_encoded_bytes. Each ancestor is opened by dirfd with
    O_DIRECTORY|O_NOFOLLOW; exclusive same-directory temp, fsync, atomic hardlink publication
    and parent fsync prevent overwriting raced-in files or originals. Missing directories
    are created only under the frozen creation choice. Existing legacy exports retain
    their caller-created directories but also use no-clobber final publication.
11. Per-item results retain plan ID, original renamed target and variant outputs; task
    ledger details persist partial outputs. ExportQueuePanel distinguishes skipped from
    completed and exposes the actual output path. No GPS/ICC/bit-depth option is altered
    by the destination layer. RGB16's existing unsupported EXIF/GPS guard remains intact.

## Canonical writer API and target-size coordination

commit_encoded_bytes(target, encoded, *, create_missing=False, cancelled=lambda:False)
returns {path, committed, cancelled}. Cancellation checks precede publication only.
CommitFailure exposes target, committed and outputs for uncertain post-publication
fsync/unlink failures. An already committed file must not be called cancelled or overwritten.
The target-size worker consumes this publisher; no competing final-write implementation
is needed. runtime.active(), resolve(path), create_missing() provide frozen-plan context.
Target-size shared integration must include its settings in destinationOptions and the
server settings hash, and consult runtime.resolve rather than perform legacy recheck.

## Local persistence and migration

Project remains v23 with an additive, independently versioned import_origin record.
Old files do not gain guessed common roots. Queue destination plans are schema
lrt.export-destination.v1 with content hash integrity, not a security signature. Plans
and paths stay in the local project/task/UI flow, not presets, telemetry or cloud upload.
Persisting a plan does not persist arbitrary tensor recipes and does not enable
post-restart execution. Existing recipe_persisted guard still requires a new export.

## Authored verification artifacts

- engine/tests/test_export_destination_policy.py: executable regression source, UNRUN.
- engine/tests/fixtures/export_destination/acceptance.json: scenario matrix, UNRUN.
- manifest.json: exact authored/new/changed paths and SHA256 hashes.
- shared-before.json: pre-edit shared source hashes, not a runtime or acceptance report.
- static-validation.json: source parser evidence only.

The older isolated DestinationController/host helpers remain reusable fixtures/adapters;
the active host is server.cmd_export_destination and runtime.build/run, not a mock capture.

## Remaining validation / known limits

Qoder must run the authored tests, Rust/TypeScript compilation, real UI flows and actual
RGB8/RGB16/ICC/GPS/watermark/layout exports, including original hashes and no-clobber races.
No runtime/visual/color quality, performance, or filesystem support claim is made.
Hardlink publication requires filesystem support; unsupported filesystems fail closed.
An fsync failure after publication reports a committed-but-unconfirmed file and requires
review; retries do not rename or overwrite it. Multi-artifact watermark/layout publication
is not an all-files atomic transaction; partial files and failures are explicitly retained.
Pinned descriptors prevent symlink traversal, but external renaming of an already-opened
directory can move its location. Existing output files are never replaced.
Directory preview is advisory about ACLs/free space; errors remain possible at commit.
Legacy import-root provenance cannot be recovered if it was never saved; the preview
warns rather than asserting the original hierarchy was known.
Rollback must revert the shared diffs plus manifest-listed new files together; removing
only new modules after shared wiring would break imports.
