# Identified colour capture: basic verification

Candidate: 7257f1621e8357e7a88cc242b5f39dd1dde03faf
Tree: cfa969ffc3edd3627cbbe0c69bdfb871eba46b62
Branch: fix/interaction-regressions. No main merge or installed-app replacement.

## CI

https://github.com/Nelson-zhou/lumaretouch/actions/runs/39672654783
All non-GPU jobs succeeded. GPU jobs were skipped, not passed.
- CPU engine: 1015 passed, 422 skipped in 62.00 seconds.
- Frontend: 105 tests passed; typecheck/build succeeded.
- Capture wire: 2 standalone Rust tests passed.
- Native cargo check and selected tests passed, including CaptureHost's 5 tests.
- Packaging/staging checks passed.

## Qoder local basic checks

Frontend dedicated candidate worktree: lumaretouch-ui-7257f162.
Evidence under .scratch/ui-regression/{logs,rust}/.
- npm test: 105 passed, no failed/skipped; rc0, recorded UTC20:45:21.
- npm run build: rc0, UTC20:45:34–20:45:38.
- capture_wire standalone compile/run: rc0 each, 2 passed, UTC20:45:56.
- frame_identity standalone compile/run: rc0 each, 2 passed, UTC20:46:12.
Rust source hashes were recorded before/after and unchanged. Individual npm test
source hashes and node/npm versions were not recorded; do not infer them.

Backend dedicated candidate worktree: lumaretouch-backend-7257f162.
Evidence under test-artifacts/: helper build logs/trace, guarded launcher,
pytest-backend.log/.rc, pytest-backend-trace.txt and junit-backend.xml.
- Matching color-scopes/curve helpers built rc0, UTC20:45:59–20:46:00.
- Guarded pytest launcher rc0, UTC20:46:41–20:46:43.
- 23 passed, no failures/errors/skips: capture controller6, capture pipeline4,
  scopes controller4, scopes sampling/bridge equivalent6, module boundaries3.
- test_color_scopes.py imports both sampling/bridge modules and was used because
  separate test_color_scopes_sampling.py/test_color_scopes_bridge.py do not exist.
- Same-process candidate module-path assertions passed; five module hashes recorded.
- GPU visibility disabled for this process only. No SHM tests in selected scope,
  so no additional SHM harness was built.

Qoder sessions:
https://qoder.com/agents/session/qs_01m5e738aj2m6kqgcrwqfybc1d
https://qoder.com/agents/session/qs_01m5fqn216cqt0g02mbdrr8h03
Both ended idle. Root performed static review/edit/git operations only, not product
execution. Failed runs from earlier candidates remain preserved in their evidence.

## Limits

This validates contracts/basic code paths, not physical GUI presentation or final
portrait quality. Real-machine GUI/performance/visual testing remains pending.
Read-only proxy RGB/Lab/neighbourhood sampling is not an action eyedropper,
full-source sampler or comparison sampler. Ordinary live crop-aspect bug remains
open and is not fixed by the frozen capture's separate presentation geometry.
