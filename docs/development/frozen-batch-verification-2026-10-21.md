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

## Integrated native/UI result

Corrected remote `c7594167c5df2311f505f96d2184b87aed6070ca`, tree
`2693d215d20b7e3ed343552038afacc2d656c9ab`, passed non-GPU CI run `39683725492`.
Engine job `119512389249`: **1045 passed, 422 skipped in 70.42s**. UI job
`119512388881`: **126 frontend tests**, TypeScript/Vite build, cargo check and
**5 batch_host Rust tests** passed, alongside the existing native regression groups.
GPU jobs remain skipped.
https://github.com/Nelson-zhou/lumaretouch/actions/runs/39683725492

Qoder dedicated `lumaretouch-ui-c7594167`:
- npm test at **22:06:20 UTC**: **126 passed, 0 failed/skipped/cancelled/todo**,
  including all 13 batchWorkflow cases; reporter 420.341523 ms, wall 0.559356125 s.
- npm run build **22:06:34–22:06:38 UTC**, rc 0, 0 TypeScript errors,
  Vite 6.4.4, 86 modules, dist 684 KiB reported; wall 4.416468390 s.
- Node v24.22.0 / npm 11.19.1. Existing dependencies were copied only after the
  package-lock SHA256 matched `89152a5d85f307d166834ab4d81b9b89f3e146f7874ccd07c17b899fe4e7b01e`.
- Exact candidate SHA/tree and zero tracked changes before/after verified.
- `.scratch/ui-regression/logs/stage{1-npm-test,2-npm-build}.{trace.log,rc.txt}`
  retains commands, actual times and results.
- App.tsx SHA256 `d07f644dfa2cc8984478cbee7d96eafd04a0af7b222b52bdfbbb31cbd135b1f3`.
- batchWorkflow.ts SHA256 `d90c9759c269abce0b035d066cf69abb331614e770b27aa74b7f53be29afcd31`.
- batchWorkflow.test.ts SHA256 `556234f0e02d3e224f4425dbe9af23d7882ae65af487ed7944a39ac08667a026`.
- BatchActions.tsx SHA256 `93f73c97c149dc5413cff528e022756813a84489b9e9888651fa2c1d14c2014f`.

Preserved frontend failure: `0f6c38782b545a30a1f511916c981f86a3ced721` passed
126 npm tests at 22:02:49 UTC (474.478653 ms reporter; 0.613913065 s wall), but
build returned rc 2 at 22:03:27 UTC. Moving the compact toolbar outside the fixed
filmstrip omitted one JSX fragment closure. CI job `119510655806` and Qoder both
reported TS17008/TS1381/TS17015/TS1382. Vite did not run and no dist was produced.
The missing closure was fixed; tests/guards were not weakened. Failed logs remain
in the separate `lumaretouch-ui-0f6c3878` worktree. Corrected checks used a new
worktree, not an overwritten failure record.

The recipe review/confirmation/target protection/correlated result loop has passed
basic verification. The installed desktop application has not been replaced. Real
GUI, 1000-image throughput, hardware quality/performance and full handbook coverage
remain open. Runtime review records are bounded and not crash-durable transactions.
