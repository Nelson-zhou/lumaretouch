# Prepared-original preset group review

Status: **source integration / UNRUN**. This is a bounded filmstrip batch step,
not unattended directory processing or proof of photographic quality/performance.

## Practical slice

Select one to eight parked original photos and a stored preset containing only
`lnx.skin.v1`, `lnx.exposure.v1`, and/or `lnx.white_balance.v1`. Every selected
target must already have its own genuine single-face MediaPipe analysis, explicit
skin scope, neutral recipe and no edit history. The current editor photo, virtual
copies, composites, ambiguous/manual/disabled faces, detection-limit hits, retained
overrides/associations, and unprepared targets are refused. An unsupported module
rejects the complete preset; an invalid target rejects the whole selection.

The UI prepares and displays each target's complete before/after render, then
offers **one explicit acceptance of that exact group**. All image pages and whole
PNGs are SHA-256 checked and both sides must actually load before acceptance.
Changing the selection/preset, closing the view or replacing the engine cannot
carry approval to another group. No source mask, face identity or analysis is
copied between photos. The eight-target/32 MiB evidence limits are implementation
resource bounds, not measured throughput or memory-performance guarantees.

## Existing owners remain authoritative

- Stored-preset catalogue resolution binds the exact complete recipe hash.
- `portrait_preset_batch` retains disposable image evidence and row identity only.
- `FrozenBatchController.store` owns plan expiry, claim and terminal receipts.
- Full-candidate render/snapshot primitives own per-target complete pixel evidence.
- `BatchSyncController.commit` owns candidate construction, revisions, each
  target's history, dirty state and the ordinary batch ledger. Private checks run
  after planning and immediately before parked writes. Normal batch JSON cannot
  supply that callback or use a group token to bypass group acceptance.
- Existing project save, batch history and export remain separate actions. A
  successful apply receipt does not mean saved, exported or visually accepted.

Current targets must be parked so this slice never rebinds the live people graph
mid-commit. All people/source/context/history/candidate evidence is rechecked
before publication. Claimed operations with uncertain results remain unknown;
they are not retried as new mutations.

## What this does not yet do

Fresh-target group preparation is now an **explicit separate mutation**, not a
side effect of read-only review. See [serial preparation](PRESET-GROUP-PREPARATION.md).
It requires a clean project and distinct physical sources, including the original
editor. It is not unattended directory processing: approval, saving and export
remain separate. Edited targets, virtual/composite documents, multiple faces and
restart/resume are not supported by this bounded path. The directory workflow's
per-photo handoff is unchanged; group preparation never steals its exclusive lease.

## Design reference

Reviewed official darktable [copy/paste documentation](https://darktable-org.github.io/dtdocs/en/module-reference/utility-modules/shared/copy-paste/)
on 2026-10-25: selected modules can be applied to a selected image set, while
history preservation and unsafe mask transfer deserve explicit treatment. This
implementation follows that practical selection/group-action pattern, not copied
code, and freezes stored recipe identity rather than using mutable donor state.

## Authored acceptance scenarios — all UNRUN

1. Two separately analysed neutral original targets: complete pages/whole-image
   digests and DOM loads gate one group acceptance; original editor stays selected.
2. An unprepared, edited, duplicate, current, virtual, composite or multi-face
   member rejects the complete group before any recipe write.
3. Page reorder/corruption, omitted target/side, stale token, changed preset,
   changed source/context/revision/history or replacement row cannot apply.
4. Generic `batch commit` with a group token cannot bypass the dedicated ACK.
5. Candidate or owner drift at the final batch barrier prevents parked writes.
6. Exact replay returns the canonical terminal result; mismatch/unknown cannot
   become a new write. Disconnect/restart never restores approval.
7. Ordinary batch/preset workflows retain prior behavior; group apply uses the
   same per-target undo/redo and subsequent normal project save/export.

No tests, builds, typechecks, inference, product execution, GUI/device checks or
image-quality/performance measurements were run for this slice.
