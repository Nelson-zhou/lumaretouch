# Saved export task recovery — bounded L2 source slice

Status: implemented source paths, **not runtime acceptance**. L2 remains partial.
No tests, product imports, application execution, build, typecheck, installation,
network, image rendering or inference were performed for this slice.

## Durable scope and explicit action

This restores tasks present in a manually saved project or an existing project
recovery snapshot. It does not introduce a queue, an output-side journal, periodic
export checkpointing, or a promise to recover unsaved tasks after arbitrary crashes.
The existing recovery runtime still refuses capture while background export work
is alive; the existing manual save permits a genuinely paused export boundary.
Opening a project restores interrupted tasks as paused, without starting a worker.
The existing exact task control UI receives `resume` through allowed-action metadata;
resume starts the existing worker only after all proof checks pass again. Terminal
failed/cancelled tasks retain the existing explicit retry action.

## Frozen input persistence

`export_task_recovery.serialize` is shared by manual project build and recovery
capture. The original full argument tuple remains in `_task_args`; each retry uses
a separate pending subset rather than replacing that immutable selection.
The existing project encoder/decoder and content-addressed project `assets` retain
snapshots, source facts and embedded arrays/bytes. No new recipe/asset store exists.
A bounded tagged tuple-path map preserves tuple/list identity, including fields of
already approved codec dataclasses (RepairOp, LightOp, FacePrecompute, CubeLut).
No pickle, arbitrary module import, user-named constructor or permissive fallback
is used. A full existing exact fingerprint must match after codec round trip;
unknown values, dropped assets and changed container types block recovery.
Before hashing/decoding untrusted envelopes, node/depth/text/scalar limits apply;
all asset references (including duplicates) charge bounded encoded and decoded/copy
bytes. Dtype/dimensions and PNG IHDR geometry/bit-depth/color are checked before
PNG decompression. Specialized non-admitted project record tags are rejected.
The envelope binds task/project identity, original owner, immutable arguments,
input intent, saved item receipts and creation dependency evidence by digest.
Digests establish internal consistency/content identity, not signatures against an
adversary able to rewrite an entire project and all of its hashes.

## Ownership

Creation freezes project/workspace/session provenance independently of control
metadata. Saving cannot assign current ownership to an old task. Foreign or legacy
tasks remain readable blocked rows. An explicit successful project-open boundary
may establish a fresh control token/workspace/session for the restored ledger;
read/list never rebinds. Recipe execution is admitted only after same-project and
source/document identity checks. The current recipe/version is never substituted,
and a changed current recipe does not change retained inputs. Old native control
references remain stale. Owned workflow leases are not inferred from serialized
roots: this slice explicitly blocks their recovery.

## Exact supported replay boundary

Admission currently requires all of:
- A frozen authenticated destination plan, exactly one output per selected document.
- The original CPU device and matching checked engine source/package/build/platform/CPU/runtime-setting provenance.
- Full source fingerprints and unchanged document/source identities and paths.
- Global grade/exposure/white-balance/HSL/curves/levels/crop/sharpen edits whose
  remaining feature families pass the shared complete neutral-policy gate.
- Exact snapshot/assets/tuple integrity and all recorded completed output proofs.

The model/feature gate is conservative, not a generic model-inventory claim.
This is a conservative compatible-environment check, not a guarantee of pixel-identical
results across hardware or independently rebuilt dependencies with identical metadata.
No massive dependency binary/weight scanning or cross-machine equivalence is claimed.
Model-dependent recipes, people/body graphs, GPU recovery, active non-admitted feature families,
custom ICC, watermark/clean derivatives, layout aggregates, external unowned
sources and workflow-owned destination leases are retained but blocked.
Portable-package/source relocation is also blocked; no frozen plan or source-bound
recipe is silently retargeted. Those contracts need separate source/runtime proof.

## Commit reconciliation

The existing no-clobber output committer is unchanged. Destination decoration now
also authenticates ordinary explicit-format output receipts against writer-reported
encoded bytes, exact nofollow stat/content identity and frozen destination plan ID.
Original receipts and JPEG quality-mapping facts are preserved.
Restoration and each explicit action rehash saved completed outputs. Verified
succeeded entries are omitted from the worker pending subset. A missing/replaced
completed file, unproved existing target, failed durability receipt, or output
committed without a complete saved successful item remains blocked. Existing
files are never overwritten, renamed, removed or silently adopted. A snapshot
predating a commit cannot prove the intervening commit merely because a file exists.
No claim of partial derivative reconciliation is made by this initial slice.

## Owned path manifest

- `engine/src/lumaretouch_engine/export_task_recovery.py` (new)
- `engine/src/lumaretouch_engine/server.py` (task capture/restore/control/retry only)
- `engine/src/lumaretouch_engine/export_task_controls.py`
- `engine/src/lumaretouch_engine/tasks.py`
- `engine/src/lumaretouch_engine/project_recovery_capture.py`
- `engine/src/lumaretouch_engine/export_destination_runtime.py`
- `docs/export-task-recovery/source-review.md`
- `docs/export-task-recovery/unrun-scenarios.json`

Static Python AST and JSON parsing are syntax checks only. Independent source
review and the explicitly unrun scenarios below are still required before any
behavioral acceptance claim.
