# Exact-content missing-source relocation

Status: source registered by static inspection; runtime acceptance pending; all runtime tests,
compilation, typechecking, builds, product imports and image inference UNRUN.
This document does not certify CORE-005, P0, Linux packaging, or visual quality.

## Requirement and official practice

- Handbook `manual-text.txt:1045`, LNX-CORE-005 / LNX-P0-PROJECT: missing files may be
  relocated; nonmatching source content must not reuse old cached identity.
- Official darktable collections documentation describes updating a moved folder's
  catalog location rather than re-importing or moving its files:
  https://docs.darktable.org/usermanual/3.6/en/module-reference/utility-modules/shared/collections/#updating-the-folder-path-of-moved-images
- Official darktable import workflow records locations without copying/moving:
  https://docs.darktable.org/usermanual/3.6/en/overview/workflow/import-rate-tag/
- SQLite's official atomic-commit discussion motivates distinguishing complete old
  and new states and durable synchronization. This implementation remains JSON,
  not SQLite, and does not claim SQLite's locking or crash guarantees:
  https://www.sqlite.org/atomiccommit.html

Verified by official-source search on 2026-10-23. Full-content verification,
explicit duplicate choices, limits and transaction receipts are original product
contracts, not a claim that darktable implements these exact safeguards.

## User flow

Open a saved, clean project. Choose up to 64 missing rows. Pick actual local files
or one directory through the existing Tauri dialog plugin. The bounded worker
hashes full files, displays old paths, exact SHA256, byte sizes and all matching
candidates. No candidate is preselected. User selects mappings, reviews the count,
checks explicit confirmation, and commits one atomic project replacement.
Unselected rows stay missing. The source files are opened read-only throughout.

Directory scans stop rather than silently declare a partial search complete:
10,000 entries, 16 levels, 120 seconds, 16 GiB total hashed bytes, 2 GiB/file,
32 matches/row and 256 total candidates. Symlinks at any path component, FIFOs,
devices and unsafe paths are rejected. Permission errors are visible (max 64).
Cancellation is cooperative at each directory item and 1 MiB read boundary;
blocking OS I/O and the final short atomic publication cannot promise immediate
cancellation. Full hashes are checked again at staging and immediately before
replace, with file dev/inode/size/mtime/ctime evidence.

Only historical `hash_level=full` SHA256 plus exact byte count proves identity.
Head-only/absent fingerprints are blocked, not upgraded from replacement bytes.
Exact encoded bytes also preserve source format, dimensions, ICC and orientation;
no decoder, pixel-only hash, filename or extension substitutes for this evidence.
Old records may not contain displayable dimensions/orientation; UI says so.
No new model/dependency/download is required.

## Preservation, transaction and recovery

Stage a deep copy, modifying only document.path and fingerprint.path. The project
receipt and updated_ns are separate from recipes; named versions, accepted assets, face/body IDs,
analysis/support provenance, historical source paths and task input snapshots are
not traversed or rewritten. Never merge two records sharing matching content.
Runtime rows are mutated in place. Current `_doc_path` and `_people_path` bindings
and verified local-mask/library file stamps follow the exact source. Runtime
relocation aliases let batch/people group restore resolve old paths by retained
document ID plus a fresh full content hash, without editing historical records.
Canonical runtime IDs stay the same and only
successful rows' monotonic revisions advance once. Undo/redo and live recipe
objects are untouched. Relocation is not a photo edit and does not create a false
undo frame. Reopening by project.open is deliberately not used for publication.

Require clean saved state; dirty state must be explicitly saved first. Snapshot
project digest, project file SHA, workspace, document IDs/revisions and candidate
fingerprints. Use temporary output in the same pinned directory, file fsync,
content-CAS, dir-fd-relative os.replace, directory fsync, then in-memory publish.
Before replace failure, retain old project and remove temp. After replace failure,
report unknown, retain evidence and fence mutations. Query original operation,
verify exact disk SHA plus operation marker, fsync and publish idempotently.
When reconciliation cannot establish a result, explicit project.open(force=true)
is allowed only after the worker stops. Only a successful workspace change clears
the old uncertainty fence; a failed open leaves it intact.
Never compensate by overwriting a possibly newer project with an old copy.

An advisory relocation lock serializes cooperating writers. The server dispatch
fence is REQUIRED. Arbitrary external writers do not honor advisory locks; CAS
narrows that race but cannot provide filesystem-wide transactions with independent
writers. Likewise an external process can change a source after verification;
normal source-change verification must remain on subsequent decode/reopen.

## Explicit inherited limits / acceptance blockers

- Existing project serialization does not store canonical DocumentVersions IDs;
  reopen creates new runtime identities. Same-session identity preservation is
  implemented; cross-reopen persistent identity is NOT claimed here.
- Existing ordinary project save rebuilds versions/assets. This feature bypasses
  that destructive rebuild to preserve the current persisted project exactly;
  it does not repair the unrelated ordinary-save behavior.
- Existing source decode/preview caches are not redesigned. Exact source bytes
  allow existing geometry/support reuse; changed content is never admitted.
- No rendered-image preview is fabricated. The preview is the concrete path and
  fingerprint mapping; file content equality is the validation, not visual guesswork.
- Native registration, dispatch gate, project panel and history restore ports are
  statically connected. Known active heavy/preview work blocks admission; owned
  preview ticks pause while relocating or uncertain. Read-only library queries and
  preset snapshot/receipt remain available. Qoder runtime coverage remains required.
- Shutdown requests cancel/join the relocation worker at safe boundaries before
  closing the engine. OS I/O may delay a safe stop; no instantaneous stop is claimed.
- Python pytest cases and the acceptance JSON are authored UNRUN, not passed.

## Registered shared files

server.py (ready/support metadata, project disk SHA tracking, command registration,
pre-dispatch gate, read-only exemptions, owned-tick exclusion, shutdown join),
main.rs (Tauri registration), engine.rs (correlated event route), native.ts
(project support type), ProjectWorkspace.tsx/useProjectWorkflow.ts (actual panel
and refresh), batch_group_history.py and people_host.py (verified path aliases).
The UI offers a separate, explicit warning/confirmation before force-reopening
the disk project for uncertain-result recovery; it never automatically discards
a session or repeats a commit.
