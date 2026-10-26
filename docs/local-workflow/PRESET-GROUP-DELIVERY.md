# Exact successful group: explicit save and export handoff

Source integration only. Builds, type checks, tests, inference, real-device output,
photographic quality, durability and performance acceptance are **UNRUN**.

## Product flow and references

The existing bounded original-photo group review/apply flow now retains its
successful canonical batch receipt. The user can explicitly **save this group**
and/or open the **existing export settings** for this group. Filmstrip changes
never change the handed-off targets. No apply, navigation or setting change
starts a save or export automatically.

Design reference: darktable's official [export workflow](https://darktable-org.github.io/dtdocs/en/overview/workflow/export/)
and [export module](https://darktable-org.github.io/dtdocs/en/module-reference/utility-modules/shared/export/):
selected targets, explicit destination/profile configuration, conflict decisions,
and a background export job. This implementation reuses Lumaretouch's existing
owners; it does not copy darktable code or introduce another queue.

## Authority and identities

The successful group result includes ordered `delivery_targets` (document ID and
post-apply revision) and `workspace_generation`. Private session evidence binds
these to original row objects, canonical batch ID, source proof, full candidate
recipe/people context and undo/redo history. Before save/preview/start the existing
batch ledger must still exist, be un-undone and contain exactly those target
states. Any changed source, version, people context, row, project or workspace
rejects delivery. This is not restart/rebase/retry authority.

`portrait_preset_delivery_protocol=1` gates five narrow actions over the existing
batch mailbox: save, export preview, export start, original-task status and
original-task cancel. Every request/reply binds original token and batch ID, plus
plan/intent or task identity as applicable. Session dispatch receipts prevent
repeating uncertain writes; canonical batch history, project CAS, and export
jobs remain their existing owners. There is no replacement history/job ledger.

## Saving is not exporting

`portrait_preset_group_save` stages only exact saved original target rows through
existing per-row recipe/history codecs and detached canonical people serialization.
It preserves unrelated saved rows, source registrations, metadata and authored
support banks. It rejects unrelated shared portrait graph changes rather than
publishing them. Existing pinned-directory project CAS owns replacement/readback;
possible replacement failures remain Unknown. The global dirty flag is never
cleared by this scoped save, so unrelated dirty recipes remain unsaved.

A saved original project/baseline is required. Unsupported or externally changed
projects fail without silently invoking ordinary whole-project save. Unknown save
blocks new export handoff; querying its original receipt is not permission to
repeat replacement. Reopening/recovering is an explicit existing project-owner
operation, not an automatic action in this feature.

## Export ownership and honesty

The existing destination/profile/format/quality/size/watermark UI is reused. The
canonical destination planner freezes the exact target versions, source stamps,
paths, options, conflict choices and intent revision. The start action uses only
that stored plan and settings. Existing no-clobber output commit stays in charge;
changed or occupied frozen paths do not silently overwrite or choose new names.

`GroupExport` calls the canonical `cmd_export`, identifies its one newly created
original task, then reads canonical item states and output receipts from that
same task. It does not infer completion from queue admission, a last-error field,
a previous same-document export, or elapsed time. Status may be queried even if
live edits subsequently drift: the immutable original export snapshot is the
authority. A verified task status can reconcile the exact lost/unknown original
start receipt through the existing mailbox; it never dispatches another export.

Cancellation addresses only that exact task through `cmd_task`, at its normal
item boundary. Already completed outputs remain completed; pending, failed,
skipped, partial and cancelled outcomes remain visible. No automatic retry,
output deletion, overwrite or cleanup is introduced. An all-skipped canonical
successful job is reported partial, not all-images-written.

Task receipts are real lifecycle evidence, **not** independent file rehash,
visual inspection, print/color acceptance or performance acceptance. The API
always reports `output_completion_verified:false` to make that distinction
explicit. An unconfirmed task identity remains Unknown, never “not started”.

## Deliberate limits

- Same existing 1–8 distinct original-photo group scope; current editor excluded.
- No new modules, multi-face, edited/derived source or unattended approval support.
- Individual-photo delivery only: layout/PDF aggregation is explicitly rejected;
  normal independent layout export remains unchanged.
- One original export per group handoff; no new task after partial/cancel/unknown.
- Session proof capacity 64 groups, admitted before group application; bounded
  mutation receipts. Read-only status polling does not consume mutation capacity.
- A whole shared people-context change can invalidate a group even when its
  sliders did not change. This conservative limit avoids saving/exporting stale
  portrait evidence.
- Saving does not mark all project edits clean; exporting does not imply saving.

Authored UNRUN fixtures cover save preservation, source drift, output plan/task
identity, unknown admissions, no-start rejection, skips/partial/cancel and UI
interruption/reconciliation. Source AST/diff checks are not runtime validation.
