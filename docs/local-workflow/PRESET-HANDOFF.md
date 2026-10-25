# Same-lease preset handoff

Status: source implementation and authored fixtures only. Product execution,
tests, native/UI integration, crash durability, numerical behavior and image
quality are **UNRUN**. No end-to-end acceptance is claimed.

## Ownership and progression

The genuine managed importer remains the authority for each stable document UUID,
source asset, original occurrence and durable import receipt. A transient editor
load ID is used only by the existing preset command's loaded-target fence; it
never replaces the stable document identity.

A supported exposure/white-balance preset pauses the same exclusive ingestion
lease. The user opens the exact imported target, reads both complete reviewed
images, and explicitly approves. Approval is not application. Only the core's
journaled `ApplyPreset` command can consume that exact approval and enter the
normal `preset` dispatcher, history bookkeeping and post-history receipt owner.
The admitted apply operation is retained before a fallible approval consumption,
so an expired approval cannot be reported under its earlier preflight identity.

The actual captured state, effective/original source proof, people context,
repair stack and complete render snapshot must equal the reviewed candidate
before an explicit save becomes available. The result remains pending until the
user saves the exact project and then returns to the original editor document.
The original row, recipe and revision are checked after return before the lease
selection is updated. The finishing operation explicitly clears only its own
retained handoff snapshot; old operation queries cannot borrow a newer handoff.

## Physical source evidence

Stored fingerprint dictionaries are not proof of current source bytes. The
handoff reads the regular managed file without following symbolic links and
compares its complete SHA-256 and byte count against the original managed-import
and document receipt. Its physical stat identity is retained as well. Both byte
substitution and same-content file replacement invalidate the handoff.

The proof is checked before loading, throughout review/approval, before normal
preset dispatch, after application, during the explicit save's precommit checks,
and before releasing the return. The rendered review's original-source digest
must also match the imported source digest. The source file is never written.

## Target-only codec save

The handoff retains the verified saved, hydrated project body. It does not use
`_project_build` to save, because that rebuild regenerates all version timestamps
and can discard inactive saved versions. The existing project codec and
`virtual_copy_project.save_row` update only the selected target's active recipe,
proxy budget, document revision and normal history/context.

Every non-target document record, including version timestamps, named versions,
undo/redo and metadata, remains exactly as saved. Existing immutable assets are
retained and only newly encoded target assets may be added. Source registrations,
project-level people data, task records, import receipts and saved selection are
not rewritten. A lossless encoding failure, hidden migration or unrelated change
refuses the save before manifest replacement. Ordinary save semantics omit
derived precompute tensors, not user intent or editable repair history.

`workflow_preset_save.persist` owns the existing codec preparation, immutable
blob durability, bounded pinned-directory CAS, atomic replacement, directory
fsync and exact readback. A successful publication uses the codec's actual
stamped body and hydrates sidecar blobs for live project use. Packed manifest
assets are never installed as if they were live hydrated content.

## Failure and restart boundaries

An invalid/stale step rejected before its effects is a definitive failed request,
not an excuse to poison the retained handoff. Repeating its exact request returns
its receipt. Any possible replacement or uncertain application stays fenced and
must be inspected through the retained original operation. New request IDs do
not authorize retry. An engine restart does not restore an in-memory approval or
replay a pending mutation. There is no automatic rollback overwrite, project
save, selection recovery or export continuation after an unknown outcome.

The authored `test_workflow_preset_handoff_unrun.py` covers source substitution,
symlink/replacement rejection, non-target codec preservation, hidden migration,
early apply correlation, stale-step rejection, complete applied-proof mismatch,
and unknown-save no-retry behavior. These are planned acceptance fixtures, not
executed evidence. Full engine load/apply/history/save/return and process-crash
acceptance still require a separately authorized runtime validation pass.
