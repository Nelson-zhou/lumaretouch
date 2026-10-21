# Frozen batch verification checkpoint — 2026-10-21

## Backend candidate

Remote `e56ef6ab8e1203392355ceb3722c712fe53f1871`, exact tree
`97fd7f2f97c51cb9bf9cad5df6169c111cd69aff`. Connector tree and fetched FETCH_HEAD
match the local committed tree. `origin/fix/interaction-regressions` is a stale
tracking ref in this checkout; verification used the actual fetched commit instead.

GitHub CI run `39680987829` completed successfully for all non-GPU jobs. Engine job
`119503093565`: **1045 passed, 422 skipped in 69.57s**. GPU jobs were skipped; CI is
not evidence of AMD/NVIDIA/Wayland or real-image visual acceptance.
https://github.com/Nelson-zhou/lumaretouch/actions/runs/39680987829

Qoder dedicated detached candidate `lumaretouch-backend-e56ef6ab`:
- Official curve helper build rc 0 at 21:46:44 UTC.
- Guarded same-process source assertions and pytest: **21:46:57–21:47:12 UTC**,
  rc 0, **52 passed, 0 failures/errors/skips**, JUnit duration 14.294 seconds.
- Counts: document_versions 4, document_version_wiring 2, batch_preflight 4,
  frozen_batch_controller 13, batch_sync_controller 9, batch_skin_scope 6,
  preset_batch 4, module_boundaries 3, import_device_order 7.
- Existing Python environment reused with candidate cwd/PYTHONPATH; package plus
  server, batch_sync, batch_preflight, batch_preflight_controller, document_versions
  and scope source paths were asserted in the guarded process.
- Source controller SHA256:
  `6225d7b9a242b28ac020250a56545c1b8aa49b514eff2327661d88b1d0a20384`.
- Curve helper SHA256:
  `15a7635b37d18773f40bcc986704f3a69fb415761707038935bf6cba5d9fbc8e`.
- `test-artifacts/`: pytest-backend.log, junit-backend.xml, pytest-backend.rc,
  pytest-backend-trace.txt, build-trace.txt, build-curve-compiler.log,
  run_backend_guarded.py. Only this directory was untracked. Baseline untouched.

## Preserved failure and correction

Prior remote `516b272227645dd8343408e07044b92a411675c9` local run at
21:38:18–21:38:33 UTC returned rc 1: **41 passed, 1 failed, 0 skipped**.
`test_batch_scope_and_policy_guards` required rejected `conflict_policy` and value
`overwrite` to appear in the diagnostic. The new generic message omitted both.
The production diagnostic was corrected; no assertion was weakened. `-x` stopped
before module_boundaries/import_device_order in that failed run. Failed logs and
JUnit remain preserved in its separate candidate worktree. The corrected run above
ran all nine files. Its CI success alone did not cover the locally exercised failure.

## Scope and remaining validation

Backend evidence covers immutable source snapshots, monotonic target fences,
reorder/remove/re-add, workspace invalidation, scoped undo, parked dirty tracking,
revision exhaustion admission, claim-before-write and unknown-outcome/idempotency.
It does not prove crash durability or exhaustive lifecycle/GUI behavior.

Native epoch-bound receipt ownership and the React review flow are included in the
next integrated candidate. Their tests/build/typecheck are **pending** at this
checkpoint. The installed desktop application has not been replaced. Full handbook
coverage and real-machine quality/performance acceptance remain open.
