# LRI1 buffer-instance prerequisite — 2026-10-21

Candidate `39af909ea657e7e03c8231e808cee036de641afc`, tree
`4241f9e28b6d96e7614afd0fed5f6cfda441f0a4` on `fix/interaction-regressions`.

- [CI 39666003475](https://github.com/Nelson-zhou/lumaretouch/actions/runs/39666003475):
  all non-GPU jobs succeeded. Actual native SHM interop harness built in the engine
  job. Engine **1006 passed, 421 skipped in 61.67s**; GPU jobs skipped, not passed.
- Qoder: small Cargo interop harness built rc0 at **19:58:47–19:58:48 UTC**;
  standalone identity Rust tests **2 passed**, compile/run rc0 at **19:58:59–19:59:00**.
- First local Python invocation: **13 passed, 1 failed**, rc1, **19:59:29–19:59:39**.
  The spawned writer exited 1; parent entered.wait(10) failed. Preserve this result.
- Read-only diagnosis found the custom run_phase1.py invoked pytest.main at module
  top level without a main guard. Captured output showed its preamble and another
  test-session start. Child traceback was not retained; exact original failure
  causality is therefore not claimed proven.
- Root explicitly authorized one new, guarded launcher on the same unchanged
  candidate, retaining original script/log/JUnit/rc. Product imports, provenance
  checks and pytest invocation moved under main(); harmless stdlib imports remained
  at module scope. Capture also changed to -s, so this was not a one-variable proof.
- New phase 1: **24 passed, zero skipped**, rc0, **20:07:11–20:07:12 UTC**,
  JUnit **1.439s**. Phase 2 protocol -k shm: **1 passed, 153 deselected**, rc0,
  **20:07:38–20:07:40**, JUnit **1.782s**. Deselected tests were not rerun or counted
  as passes. No additional retries or product-code changes were made.
- Candidate HEAD/tree and clean source status recorded inside the new traces.
  Phase 1 records source/harness hashes; phase 2 records HEAD/tree/status/time but
  no separate hash set. Do not invent that missing evidence.

This establishes the bounded buffer-instance prerequisite and cross-language lock
checks, not photo/recipe/display identity, point sampling, GUI interaction, GPU
parity or installation acceptance. The original failure is retained, not erased
or rewritten as a successful run.

Reference for guarded multiprocessing entrypoints:
https://docs.python.org/3/library/multiprocessing.html#safe-importing-of-main-module
