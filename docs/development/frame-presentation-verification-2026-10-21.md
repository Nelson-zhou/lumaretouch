# Frame presentation: basic verification

Original candidate33ee297de1529facae21fa204df111ebd8b450f4,
tree0bcf08743a8fef56ee5f2ba7b687621fc0e93b29.
Corrected test-only candidate62c331284358c05a712a1fc185a2ce4e04e1ddfa,
tree358efb0ad5d698fec2da125f778a4099806e9590.

## Preserved failure

Original UI test run:113 tests,112 passed,1 failed,0 skipped,rc1. The malformed
presentation-width fixture wrote0xffffffff, which is a valid nonzero u32, then
incorrectly expected rejection. Correction writes zero. Production validation was
not weakened. Original CI and Qoder evidence remain preserved. Build/Rust stages
were not run after Qoder's initial failure.
https://github.com/Nelson-zhou/lumaretouch/actions/runs/39675579342

## Corrected CI

https://github.com/Nelson-zhou/lumaretouch/actions/runs/39675865591
All non-GPU jobs passed; GPU jobs skipped, not passed.
- Engine1019 passed,422 skipped,70.04 seconds.
- Frontend113 passed,0 failed/skipped; typecheck/build passed.
- Presentation/preview-wire standalone Rust4 passed; native cargo checks and
  selected regression tests passed. Packaging passed.

## Qoder backend (production-identical original candidate)

Worktree lumaretouch-backend-33ee297e (directory suffix is a naming typo only).
Verified HEAD/tree match original candidate above. Matching tiny SHM harness and
color-scopes helper builds rc0, UTC21:07:02–03. Guarded pytest UTC21:07:27–30,
rc0, JUnit45 passed/0failed/0errors/0skipped,2.955 seconds:
presentation4,import-device-order7,capture-controller6,capture-pipeline4,
module-boundaries3,SHM13,cross-process-SHM8. Candidate package/module __file__
assertions and outer PYTHONPATH passed; actual native harness used, no interop skips.
Evidence: test-artifacts/build-trace.txt, build-shm-harness.log,
build-color-scopes.log, run_backend_guarded.py, pytest-backend.log,
pytest-backend-trace.txt, pytest-backend.rc, junit-backend.xml.
Harness SHA256 e6e46456fcafecbd311cc0b7f75f7272bdeb0588e98a6ed30c7aafe94200ac2c.
Only test-artifacts untracked; tracked candidate unchanged.

## Qoder corrected frontend

Worktree lumaretouch-ui-62c33128, matching HEAD/tree and clean tracked state.
- npm test UTC21:08:37,113 passed/0failed/0skipped,rc0,340.999943ms.
- npm build UTC21:08:50–54,rc0,81modules; no TypeScript errors.
- Preview-wire compile/run UTC21:09:11,rc0 each,4 passed.
- Capture-wire compile/run UTC21:09:30,rc0 each,2 passed.
Six rc files are zero. Evidence under .scratch/ui-regression/logs/:
stage1-npm-test.trace.log/.rc.txt; stage2-npm-build.trace.log/.rc.txt;
stage3-preview-wire-tests.trace.log and stage3-preview-wire-{compile,run}.rc.txt;
stage4-capture_wire.trace.log and stage4-capture-wire-{compile,run}.rc.txt.
Preview binary SHA25658dcadbd9d5e31aa102467291c37564c1a34d9af8ab6a10a897001ab554dfca7.
Corrected test SHA2563b97dcc8287bd94ef35d5c82f3d68e38f9de902817a1d4f2c0e6475a2cd4c03a.
Node/npm versions were not recorded. An evidence-read path typo was corrected;
there was no extra product test run. Original failed worktree/evidence remain intact.

## Limits

This confirms basic implementation/contracts, not real-machine physical display,
GPU performance or visual acceptance. No installed-app replacement or main merge.
Root did not run product code/tests. Crop/rotation inverse-to-source brush mapping
remains a separate issue; this change only aligns display-to-raster mapping.
