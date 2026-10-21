# Batch undo scope correction (basic verification passed)

The existing batch undo conflict check compares only synchronized module parameters,
but restoration previously replayed the entire old document snapshot. That could
erase later changes in unrelated modules despite passing the conflict check.

The correction applies the recorded before-parameters for the synchronized modules
into the current state, then replays/parks that merged state. Tests cover parked and
live targets plus the real shared exposure tuple: undoing synchronized EV must keep
later white-balance/tone edits. Root static review found no new nested-container
aliasing in the current scope writers. Basic CI/Qoder verification is recorded below; GUI acceptance remains pending.

Existing contracts remain: changed synchronized parameters are conflicts; skin and
blemish share strength, so they are not independently restorable. WB reference-K
is outside the transferable WB parameter scope and remains current. This restores
synchronized parameters, not a guarantee of historical visual WB under a changed
reference. Stable target identities and frozen preflight are separate unfinished
work, documented in frozen-batch-preflight-plan.md.

## Basic verification completed

Candidate45b427bade0e73e135a5f17599474f3992edcfd7,
tree29c27539d4af40c47227878abf5ad1418bc24882.
CI all non-GPU jobs passed; GPU jobs skipped:
https://github.com/Nelson-zhou/lumaretouch/actions/runs/39676662856
Qoder exact candidate worktree lumaretouch-backend-45b427ba:
22 passed,0failed/0errors/0skips,rc0,UTC21:15:33–21:15:48,JUnit14.395s.
Counts: batch-sync-controller9,skin-scope6,preset-batch4,module-boundaries3.
Matching curve compiler built successfully at21:14:25 UTC. Guarded launcher,
outer candidate PYTHONPATH, package paths and six module __file__ assertions passed.
Only test-artifacts untracked; no source edits or reruns. Evidence includes
run_backend_guarded.py,build-curve-compiler.log,build-trace.txt,pytest-backend.log,
pytest-backend-trace.txt,pytest-backend.rc,junit-backend.xml.
Product source batch_sync.py SHA256:
65810e308dea991218a12f3372191f4b543f74183a68f03455d70ac019a97e22.
No root product execution or GUI/GPU/performance/installed-app changes.
Frozen preflight remains separate unfinished work.
