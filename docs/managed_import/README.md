# Explicit reference / managed copy import

Status: SOURCE_REGISTERED_STATIC_ONLY_RUNTIME_UNRUN. This is not acceptance or a shipping-readiness claim. No product import, runtime test, compiler, typecheck, build, model inference, install or download was executed for this change.

## Requirement and mature practice

- Linux guidance manual, source text line 1045: originals are read-only; copy mode uses temporary files and hash verification before registration; reference mode detects movement/external change; equal content must not silently merge independent business copies. Source relocation preserves the full-content identity.
- AI development mapping: LNX-P0-IMPORT / lnx.import.v1:choose_files and choose_folder; CORE-002 and CORE-003 are planned acceptance cases, not completed cases. missingcoreM08 is the development gap being addressed.
- Official darktable manual distinguishes add-to-library (references existing files) and copy-and-import (copy, then register): https://docs.darktable.org/usermanual/4.0/en/module-reference/utility-modules/lighttable/import/ and https://docs.darktable.org/usermanual/development/en/overview/workflow/import-review/ . These support the interaction split, not a claim of implementation equivalence.
- Python official os API documents directory-descriptor-relative operations, O_NOFOLLOW, link, fsync: https://docs.python.org/3.11/library/os.html . The implementation is Linux-specific. Hardlink publication is exclusive and fails closed when unsupported; it does not fall back to overwriting rename.

## Connected behavior

Project workspace exposes files/folder pickers, reference default and a separate managed-root picker. Reference dispatches the existing session add implementation. Copy requires a clean saved project and no active heavyweight preview/export/thumbnail/pick, relocation or portable-package job.

Copy selection is bounded at 512 image files, 10,000 traversed entries, depth 16, 16 GiB input, 2 GiB per file and 300 seconds before project publication; final independent hash recheck is additionally bounded by the existing 120-second source verifier. 64 MiB free-space reserve is checked before copying and per file. Extension eligibility uses the existing session whitelist; this does not certify that corrupted files decode or that vendor RAW formats are validated.

All path components are opened without following symlinks. Source files are opened read-only and never moved, deleted, chmodded, or overwritten. Copy data streams through 1 MiB buffers to exclusive .partial files in the chosen root; full SHA-256 and the project-compatible 4 KiB head digest are reread from the staging descriptor. Source stat identity is checked before/after copying and against its current path. The staged copy becomes mode 0444 and is exclusively hardlinked to an operation/source-derived UUID filename, then fsynced. This is application-level immutability, not protection against an owner or administrator deliberately changing permissions/content.

A separate project transaction checks current project bytes (CAS), validates the candidate, rechecks every copied file by full hash, writes/fsyncs a temporary project, and atomically replaces the project. Runtime documents are published only after durable project publication. Any uncertainty after replace remains unknown and fences edits until readback or explicit force-open. Content-identical selected files remain distinct source/document identities. A duplicate operation returns its retained receipt rather than adding documents again. Receipts are bounded at 256 and admission fails instead of silently forgetting old operations.

Logical original path, original file stat identity, content SHA, import-root-relative hierarchy and managed root are retained. Normal save/open hooks preserve these and operation receipts; relocation can change the physical path without changing logical origins. Export naming uses the original basename for managed copies, with the existing virtual-copy/document collision suffixes; hierarchy export uses the existing import_origin record. Managed UUID filenames do not leak into ordinary export names.

## Failure and recovery boundaries

Cancel stops at a bounded copy/hash boundary; an already-entered atomic project commit may finish. Unmount never retries a write. UI keeps the unresolved operation UUID in session storage and offers query of the same operation. Native receipts are engine-epoch correlated; pending progress is not success. Restarted engines consult receipts in the opened project. A crash before project commit has no successful document registration: completed unregistered copies may remain and are never automatically deleted or represented as imported. Partial byte transfer is NOT resumed across process restart; only durable outcome readback is supported. Unknown pre-commit operations remain unknown rather than creating duplicate documents. Known failure/cancel messages list completed copies when available. No automatic cleanup of published copies is performed.

Mutual gates cover managed import, source relocation and portable package snapshots/commit; ordinary mutation dispatch and background preview/snapshot ticks are fenced during import. Native start uses the existing serialized queue. Readback/cancel do not invalidate image capture leases. Shutdown and run-finally join the worker before engine teardown.

## Required Qoder acceptance (UNRUN)

Run engine/tests/managed_import_cases.py explicitly (filename deliberately says cases, not a claim that default discovery executed it). Its opaque bytes exercise filesystem behavior only, not image decoding. Add real supported-format fixtures for UI/decode acceptance.

Required integration matrix: reference regression; deep hierarchy and original export names; duplicate equal-content independent files; virtual copies; normal save/reopen; relocation; package and recovery interaction; disk-full before/during staging; permission denial; symlink ancestor and link swap; same-destination collision; source mutation during hash; cancel at copy/hash/precommit/atomic-commit boundaries; close/reopen panel; repeated click; transport failure before/after send; engine crash before/after project replace; directory fsync failure; persisted same-operation query; full receipt capacity; project external modification; process shutdown; source/managed-file hashes unchanged after every failure. Verify UI responsiveness and byte progress on Linux filesystem families supporting hardlinks, and refusal on unsupported ones.
