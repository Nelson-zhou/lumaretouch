# Levels candidate verification — 2026-10-21

Feature commit `cf5fc6cb2d4441584146cb25742007c40bf30277`, tree
`c42bd1dc33d086a0e16f823924e8a685f1bd00d3`; UI type-only correction
`fb559b3df494faba777b96f9bf475a75e78d189c`, tree
`95177c237ebc26d839fbb844fecae86b83e5f000`.
Branch: `fix/interaction-regressions`. No main merge, release or installed-app overwrite.

## Evidence

- [Corrected CI run 39660104880](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39660104880):
  UI/typecheck/build/native checks, packaging and engine jobs succeeded.
  Engine log: **993 passed, 421 skipped in 61.69s**. Skips are not passes.
  NVIDIA/CUDA and AMD/ROCm jobs were skipped, not executed.
- Qoder backend at feature SHA: **72 passed, zero failures/errors/skips**, rc0,
  JUnit 15.610 seconds, 19:17:19–19:17:36 UTC. Ten files: levels math/controller/
  integration, curves math/protocol/state, history, module boundaries,
  scope-registry agreement and preset-batch. Candidate helper build rc0.
  Actual outer PYTHONPATH and same-process server/ops.levels source assertions
  confirmed this worktree, not the older editable-install source.
- Qoder frontend at corrected SHA: **90 passed**, zero failures/skips, rc0;
  build/typecheck rc0 (completed 19:19:45 UTC). Standalone Rust Levels **5 passed**
  and Curves **10 passed**, compilation/execution rc0 (completed 19:20:05 UTC).
- Exact HEAD/tree and clean before/after/final worktrees verified for both.

## Failures retained, not hidden

Initial UI build at feature SHA failed rc2 with TS2345: crypto.randomUUID's
inferred template-literal type was narrower than stored gesture IDs. Vite had
not run. Initial npm tests passed 90; Rust tests were not run after the failure.
Correction explicitly annotates gestureId:string; no math/processing change.

The original backend handoff named a nonexistent test_scope.py. Qoder stopped
before pytest rather than guessing. Root inspected the repository and selected
existing test_scope_registry_agreement.py plus test_preset_batch.py; the original
missing-file record remains. No product-test failure was retried unchanged.

## Scope and remaining acceptance

Verified paths include recipe validation, exact neutral behavior, CPU/reference
parity, project/preset/batch/history persistence, RGB8/RGB16 output, actual bounded
inspection worker, failed-switch token invalidation, stale-ID rejection and UI
receipt ordering policy. Automated checks do not prove real-photo aesthetic
quality, actual GUI dragging/cancellation on every desktop, real RAW timing,
GPU parity or release installation. Those remain pending under the user's
functional-coverage-first priority.

Histogram, readouts/eyedroppers and parametric curves remain separate missing
functionality. Do not mark the entire professional-color family complete.
