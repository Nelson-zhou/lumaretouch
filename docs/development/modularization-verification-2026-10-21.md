# Modularization verification — 2026-10-21

Final refactor-only baseline: `2fd22da74bd2d29c26281ffd267a80a8c294ce20` on
`fix/interaction-regressions`. This does not certify later feature changes.
No installed application was overwritten; no main merge/release was performed.

| Scope | Commit | CI | Qoder local result |
|---|---|---|---|
| Diagnostic hooks, native edit-command boundary, inspection ownership, history policy | `31d42a57` | [39649285261](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39649285261) | Python 232 passed, rc0; UI 75 passed plus typecheck/build rc0 |
| Batch synchronization lifecycle and explicit editor/document ports | `afbcb3ce` | [39649987843](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39649987843) | Python 47 passed, zero skipped, rc0 |
| Project workflow state, action policy and workspace rendering | `4c37d354` | [39651347185](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39651347185) | UI 79 passed, zero skipped, typecheck/build rc0 |
| Live undo/redo lifecycle and rollback ports | `2fd22da7` | [39652400044](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39652400044) | Python 76 passed, one skipped, rc0 |

All listed CI non-GPU jobs succeeded. GPU jobs were skipped, not passed.
Local runs verified exact commit/tree and candidate module source paths, retained
actual command/exit-code/JUnit logs, and had clean worktrees before/after.

The one local skip was
`test_session.py::test_browse_slot_bins_only_the_browse_slot_and_reports_the_true_size`:
external large real-DNG fixture `LRT_BIG_DNG` was absent. Browse-slot binning and
true dimensions for that fixture remain unverified. No GUI, performance or
installation acceptance is inferred from these focused checks.

## What changed structurally

App coordination reduced from about 4,175 to 2,128 physical lines; native main
from about 2,165 to 2,011; Engine server from about 7,383 to 6,960. These are not
quality scores. Ownership and dependency direction, not line count, are the
acceptance criteria. New tests check narrow ports, dynamic emit compatibility,
legacy `Engine.__new__` embedding, rollback ordering and source registration.

## Remaining work

Document/session/project transactions and export orchestration still contain
legacy coupling. Diagnostic scenarios remain a large isolated suite. Existing
batch partial-failure/frame-selection and project cancellation/error UX quirks
are documented in `module-boundaries.md`, not silently fixed or concealed by
this refactor. Continue the full product requirements without placeholder or
scope-cut claims; deep real-device optimization remains a later phase.
