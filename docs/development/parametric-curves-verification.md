# Parametric curves: basic integration verification

Recorded 2026-10-22 UTC. This verifies the specified candidates, not physical
GUI, GPU, real-photo quality, performance or the entire product/manual.

## Integrated candidate

- Remote `3dd97a7d0c36a798126b1b834b807a301ef35a64`.
- Tree `07570b4eba3822d913bcb00a80485487c5d2ea6a`.
- [CI 39705155136](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39705155136):
  all non-GPU jobs succeeded. Engine 1056 passed / 426 skipped; frontend 141
  passed. Native compilation and curve API checks succeeded. GPU jobs skipped.
- Qoder backend selected nine files: **67 passed, zero failed/errors/skipped**,
  exit 0, UTC 01:34:54–01:35:03; JUnit 7.202 seconds.
  Parametric 14, point curves 8, luminance 9, curve state 5, curve protocol 2,
  frozen batch 13, neutral bypass 5, levels integration 8, module boundaries 3.
- Python 3.12.15 / NumPy 2.5.4 / Torch 2.10.0+rocm7.0, actual CPU path.
  Candidate package/server/curves/parametric module origins were asserted.
  The matching helper was built successfully and its runtime identity checked.
- Helper SHA256 `f38fad205e50e5d5febf861273cc490872da0ab0256901d365dcaf968ae4f603`.
- Qoder frontend: 141 passed, no failed/skipped; build exit 0, no TypeScript
  errors, 89 Vite modules. Tests 01:25:58–01:25:59; build 01:26:26–01:26:30.

## Final pointer/decoder correction

- Remote `356b64b1cde2edb193b5feb5169e4c109de422e5`.
- Tree `eb2476dd51c528d237b947062dfe80a8113e9736`.
- Changes: reject secondary pointer/busy gestures before focus, settle gestures
  on window deactivation, and check decoder byte bounds before snapshot copying.
- [CI 39706015324](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39706015324):
  completed successfully 01:34:19. Engine **1056 passed / 426 skipped** (66.83s),
  frontend **143 passed / zero failed**, native/build/packaging checks passed.
  GPU jobs remained skipped, not passed.
- Qoder frontend: **143 passed**, no failed/skipped/cancelled/todo; includes 15
  gesture cases. Tests 01:31:43–01:31:44, build 01:32:04–01:32:08, exit 0,
  no TypeScript errors, 89 modules. Dependency lock hashes matched before reuse.
- Qoder backend increment: only `test_parametric_curves.py`, **14 passed**,
  zero failed/errors/skipped, exit 0; UTC 01:46:03–01:46:05, JUnit 0.306s.
  This was not a second 67-case run. The full final engine CI is separate above.
- Matching helper build exit 0, 4,459,584 bytes; SHA256
  `58b1d5b60c35fbde3d5636476fb14d3bbda6a4a4bf38dc1c7547f00de5c96587`.
  Real helper/Torch CPU and candidate-origin assertions passed.
- Exact source trees were verified; candidate tracked files and the existing
  base checkout remained clean. Root did not run product/tests/builds locally.

## Retained local evidence and process qualifications

Project-container-relative evidence roots:
- `.scratch/parametric-3dd97a7d-backend/`
- `.scratch/parametric-3dd97a7d-frontend/`
- `.scratch/parametric-356b64b1-backend/`
- `.scratch/parametric-356b64b1-frontend/`

Backend retains `logs/step45-pytest.log`, trace/xtrace and RC files, helper build
logs, source hashes and JUnit XML under `artifacts/`. Final JUnit is
`junit-backend-356b64b1.xml`. Frontend retains stage1-npm-test and stage2-npm-build
trace/RC files. These local artifacts are not claimed to be repository attachments.

The 3dd launcher kept standard-library os/sys imports outside its main guard;
product imports, assertions and pytest execution were guarded. Record this
literal instruction deviation; no product bootstrap recursion occurred. Final
356 launcher has all ten imports directly inside the guard. Its helper path was
corrected before pytest execution but **after helper compilation**; a reported
“before any compilation” description was inaccurate. No product edits or failed
test reruns were made by Qoder. Tests ran once per candidate/specified selection.

## Remaining acceptance

Physical pointer/touch/keyboard/focus behavior, native GUI presentation, real RAW
and portrait/16-bit gradient quality, GPU parity on actual hardware, performance
and packaging/install acceptance remain open. Action eyedroppers and live/full-
resolution histograms are distinct unfinished functions. Do not count this
receipt as their completion. Initial core dense error evidence is recorded in
`parametric-curves-plan.md`; the observed maximum was 9.998432835001125e-7 over
168 profiles against the unchanged 2e-6 gate.
