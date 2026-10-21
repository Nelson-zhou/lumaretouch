# Colour scopes candidate verification — 2026-10-21

Candidate `3f22cee3efd94d8e64ffe2ad181ef9d1c9a0acf5`, tree
`f33a395ad0d79b2b9cecca98d97b3d17dd38dc6d`, branch `fix/interaction-regressions`.
No installation overwrite, main merge or release.

## Results and provenance

- [CI 39662969628](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39662969628):
  all non-GPU jobs succeeded. Engine **1001 passed, 423 skipped in 64.77s**.
  GPU jobs skipped; none of these skips counts as passed GPU or visual acceptance.
- Qoder backend: **40 passed**, zero failures/errors/skips, rc0, JUnit **5.286s**,
  original UTC **19:37:53–19:37:59**. Both matching helpers built rc0.
  Same-process imports of server/sampling/controller/bridge point to the candidate.
  HEAD/tree and tracked source unchanged. Worktree was NOT completely clean:
  authorized build output `engine/src/lumaretouch_engine/bin/color-scopes` was
  untracked because its ignore rule was missing. A follow-up adds that ignore;
  this does not retroactively make the original status clean.
- Qoder frontend: **94 tests passed**, zero failures/skips; typecheck/build rc0.
  Standalone Rust colour-scopes **7 tests passed**, compiler and execution rc0.
  Trace 100 binds candidate UI cwd, npm command and 94-test summary; trace 102
  binds candidate Rust source and candidate-specific output binary; trace 103
  runs that binary and contains the 7-test summary. rc files 100–103 are all zero.
  Corrected actual UTC: npm **19:37:42–19:37:42**, build **19:37:56–19:38:00**,
  Rust compile/run **19:38:15**. Candidate HEAD/tree matched and source was unchanged.

## Reporting error retained

The initial frontend summary incorrectly reused earlier-round UTC fields without
reading the actual trace. Those times are invalid and are not evidence. Original
logs were not rewritten; read-only inspection recovered the actual times above.
No tests were rerun to manufacture a replacement history.

Source/binary hashes were originally calculated outside the bash-x wrapper and
returned in the session, not persisted in the trace. A later read-only recompute
matched those session values. Do not claim that the original trace contains hash
lines or that a later recompute proves more than it does.

## Scope

This verifies the bounded Rust statistics, binary transport limits, CPU sampling
and tap invariance, explicit read-only inspection coexistence, controller rejection,
UI identity policy, compilation and packaging. It does not establish GUI pointer
interaction, live refresh latency, full-source histograms or point/area eyedropper
functionality. The panel truthfully presents explicitly refreshed proxy samples
and aggregate means; those other requirements remain open.
