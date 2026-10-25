# Exact workflow preset save and dispatcher boundary

Status: source implementation and authored fixtures only. Product imports,
execution, tests, builds, typechecks, image/inference checks, process-kill tests,
filesystem durability tests, native bridge and end-to-end acceptance are all
**UNRUN**. Static source/AST/hash inspection is not runtime acceptance.

## Ownership and explicit user action

`workflow_preset_save.persist(project, path, expected_sha256, recheck)` is the
existing project codec's save adapter for one retained workflow preset handoff.
It is not a new project format, preset implementation, history implementation,
automatic-save policy, import transaction or source-relocation transaction.

The handoff owns the exact user-approved target, the genuine post-history preset
receipt, and comparison of the actual applied state with the reviewed state.
It prepares a scoped project retaining unrelated documents, source registrations
and existing assets. The save adapter does not infer those proofs from a JSON
flag or a matching filename. The caller must hold the existing serialized
project-mutation boundary throughout validation, persistence and publication.

The caller supplies a callable retained-owner check. It runs before sidecar
writes and again immediately before final disk CAS. A callback rejection does
not authorize a new target, a rebased saved-project hash or an automatic retry.
The explicit save is separate from image-review approval and separate from the
normal preset application. Export remains owned by the parent workflow.

## Existing codec and immutable creative bytes

The adapter uses `project._prepare_save` once. That existing codec owns complete
project validation, schema migration, writer metadata, `updated_ns`, JSON
encoding, bounds and external creative-blob packing. The prepared bytes are the
only proposed manifest bytes; the save adapter neither reencodes the recipe nor
invents an import or relocation receipt. Existing metadata remains codec-owned.

`creative_document_storage.write_blobs` receives the prepared manifest and its
exact blob inventory, reserving its normal reserve plus the manifest length.
That existing store owns the deterministic sidecar path, store lock, byte and
capacity bounds, hash/length checks, immutable hash-named blobs, staging and
durability ordering. Original bytes, float32 pixels and ICC bytes are not
quantized or recompressed by this adapter.

Existing blobs are verified, not overwritten. Corrupt hash-named bytes fail the
save rather than being silently repaired. Old generations and inactive-history
blobs are not deleted to make room. A refused or interrupted save may leave new
unreferenced immutable blobs; those are not permission to delete history or
roll back another writer's manifest. This adapter does not perform collection.

## Exact disk CAS and pinned manifest directory

The expected SHA-256 is the hash of the exact prior saved manifest bytes, not
the canonical hash of a parsed JSON object. Even semantically identical JSON
with different whitespace is a different disk generation.

The parent directory is opened component by component without following
symlinks. The retained directory descriptor owns the transaction lock, all
manifest reads, the unique manifest staging file, final replacement and staging
cleanup. The lock is the existing `<project>.relocation.lock`, opened without
following a symlink and required to be a regular file. Its exclusive advisory
flock is nonblocking; contention fails instead of implicitly retrying.

Every manifest CAS/readback uses a bounded descriptor-relative regular-file
read with `O_NOFOLLOW | O_NONBLOCK`. It refuses a symlink, FIFO, device,
oversize file, short/growing read, changed descriptor identity or changed named
leaf. Device, inode, size, modification time and change time are compared
across the read and against the current leaf in that same pinned directory.
The read is capped at the existing project limit plus one detection byte.

Separate pathname checks compare the currently reachable parent with the
pinned parent's device/inode. A newly substituted pathname therefore cannot
provide a decoy CAS while the subsequent replacement targets another pinned
directory. These pathname checks do not replace descriptor-relative reads.

The intended order is:

1. Validate/prepare the complete candidate with the existing codec.
2. Pin the parent, acquire the existing project transaction lock, confirm parent
   identity, read the exact prior manifest through that descriptor and recheck
   parent identity.
3. Revalidate the retained owner; write/verify immutable sidecars; recheck the
   parent; write, flush and fsync a unique descriptor-relative manifest stage.
4. Revalidate the retained owner again; check parent identity; repeat exact
   descriptor-relative disk CAS; check parent identity again.
5. Mark replacement as attempted, replace only within the pinned directory,
   fsync that directory, and recheck its pathname identity.
6. Read the committed manifest through the same pinned directory. Require both
   exact prepared bytes and expected SHA-256, then check parent identity again.

This is a cooperating-writer protocol, not a kernel conditional-rename
primitive. The host mutation gate and advisory lock are required. A program
ignoring both can still write between the last CAS and replacement. Byte CAS
cannot detect a change-and-restore that leaves identical bytes, nor prevent a
future write after the final readback. No stronger hostile-writer guarantee is
claimed.

The existing creative sidecar writer remains pathname-based, rather than
receiving the pinned manifest descriptor. Persistent parent substitutions are
checked before manifest commit, but a transient directory swap-and-restore
during sidecar operations is outside the proven boundary. The adapter must not
be represented as a complete adversarial-filesystem sidecar transaction.
Untrusted concurrent namespace mutation requires separate descriptor-relative
storage work and acceptance, not a broader claim about this adapter.

## Definite refusal versus unknown replacement

Before any replacement attempt, an error is raised. This means this adapter did
not attempt to replace the manifest; it does not mean no lock, unused blob or
other filesystem staging work ever occurred. The current external writer's
manifest is never overwritten as a rollback. Temporary manifest cleanup is
best-effort within the originally pinned directory.

Immediately before calling `os.replace`, the adapter records that replacement
has been attempted. If that call raises, whether before or after the operating
system changed the name, the result is conservative:

```json
{
  "status": "unknown",
  "expected_sha256": "sha256-of-the-exact-proposed-manifest",
  "error": "original failure",
  "requires_readback": true
}
```

Directory-sync failure, parent substitution, failed/mismatched post-replace
readback or descriptor-cleanup failure also returns Unknown. A failed descriptor
close is never retried, because the descriptor may already have been closed and
reused. Neither an exception nor a matching old file
permits a blind retry. The caller retains the original operation identity and
save outcome, blocks continuation as appropriate, and reconciles that operation
through its owner. This module has no retry, rollback or receipt-reconstruction
API.

Successful return contains `status`, verified manifest `sha256`, exact byte
count, codec-owned `updated_ns` and prepared externalized `project`. The caller
still owns complete sidecar hydration, in-memory publication, saved binding,
dirty-state updates and verified return to the previous editor document. A
failure after disk commit but before that publication is not an unsaved,
freely retryable operation.

## Normal dispatcher and nested recovery ownership

`workflow_preset_dispatch.dispatch(engine, payload, recheck)` admits only a
retained internal `load_image` or `preset` payload. A context-local private scope
matches the exact engine, command name and detached payload. Serialized JSON
does not grant that scope, and an unrelated command or nested workflow dispatch
is rejected. The retained owner is checked before entry.

The adapter calls the existing `engine._process_line` with the normal dispatch
table. It does not invoke `PresetController.apply`, replay the review candidate,
manually record history, manufacture success, or call command handlers
directly. Only the workflow and ingestion lease admission guards recognize the
exact private scope. Existing recovery, managed-import, package, creative,
relocation and ordinary command guards continue to run.

For a normal preset apply, `_process_line` owns the ordinary edit fence and
history capture/record path. History recording still occurs in its existing
`finally` boundary, including after an incomplete mutation. The genuine
`PresetController.finish` runs afterward and owns the corresponding
post-history receipt. An adapter return by itself is not successful apply
evidence: `_process_line` can catch a command error, so the handoff must inspect
the retained original preset receipt and actual reviewed result.

A workflow command already has an outer recovery boundary. Its nested normal
dispatch installs and finishes its own boundary. The adapter restores the
exact previous boundary and resets private admission in `finally`, including
on serialization or dispatcher failure. Restoration does not erase an inner
runtime taint, bless an incomplete history mutation, synthesize a recovery
checkpoint or replace normal recovery finish semantics. The outer
`workflow_owner` operation keeps its existing dedicated recovery treatment.

## Authored acceptance fixtures

`engine/tests/test_workflow_preset_save_unrun.py` specifies exact prepared-byte
save/readback, pre-write validation failure, owner rejection, initial/final
byte-CAS conflict, immutable sidecar retention and corruption, cooperative lock
contention, symlink/FIFO/oversize rejection, changed leaf identity, directory
substitution, uncertain replacement on both sides of the real replace call,
sync/readback/descriptor-cleanup failure, private dispatch scoping, nested-dispatch rejection,
outer recovery restoration and source-level normal-history/receipt ordering.

The prepared manifest and dispatcher probes deliberately isolate these
boundaries. They do not replace real project-codec round trips, source/image
quality checks, application history acceptance, interruption/restart recovery,
actual power-loss durability or the end-to-end import/review/apply/save/return/
export workflow. The fixtures are authored but **UNRUN**.
