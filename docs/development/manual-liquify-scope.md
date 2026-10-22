# Manual liquify implementation scope (2026-10-22)

Status: implementation and shared wiring written, **unrun and unaccepted**. No
application/build/typecheck/test/benchmark/model operation was run. Static source
inspection is not runtime or photographic evidence, and no proprietary algorithm
parity is claimed. Local verification and photographic acceptance remain pending.

Source requirements: official https://wiki.pixcakeai.com/guide/9422.html;
Linux handbook “手动液化”, and AI requirements ENGINEERING-liquify /
LNX-MANUAL-002 (vector replay/undo). Complete algorithm/license/wire/domain notes
are in [the worker contract](../../core/manual_liquify/README.md).

Implemented components:
- Rust replay: forward push, reconstruct, field smooth, rotation, pucker, bloat,
  official horizontal left push, freeze/thaw; size/affine axes, density, pressure,
  retained pen pressure/timing, rate, fixed edges, retained protection.
- Python strict state/source binding and original-resolution budget admission;
  cancellation/deadline-controlled Rust transport; existing Torch warp sampler;
  preview/output proof, source identity, history receipt helpers, export helpers.
- Native epoch-bound current-output proof and one-shot receipt helpers.
- UI single drawable actual-output surface, red protection overlay, continual held
  gestures, coalesced intermediate real renders, final visible-preview submission,
  one-gesture receipt, cancel/Escape/blur/pointer-loss handling, N, compare and zoom.

Connected integration contract:
1. `_manual_liquify` is included in document snapshots, restore/undo/signature/dirty state,
   project v7 validation and migration. Only vectors/source identity are saved.
2. `ManualLiquifyStage` is attached to PreviewPipeline and applied after background before
   geometry. Sync from engine state before each frame; missing data fails closed.
3. Preview/apply protocol handlers are registered. The preview owner ticks in server.run and
   cancels on document changes or shutdown. Apply is prepared before mutation fence,
   has a distinct undo group, and emits its receipt only after history bookkeeping.
4. Native hosts are wired to reset/ready/event/ended and mutation invalidation.
   UI owner is App-scoped so panel collapse cannot lose an uncertain receipt.
5. Source-bound recipe/path/stamp/field are included in ExportSpec and snapshots;
   verify before and after decode; replay original-size field once, add peak plus
   second interpolation support to tile halo, install slices, reject missing fields.
6. Keep manual intent out of presets and auto batch portability. Per-document export
   retains its own state; generic exports from a manual-edited source must not
   silently copy or silently omit the source-bound recipe.
7. Build/staging and CI declarations include the matching worker; redistributed
   worker sources, GEGL attribution, LGPL and GPL texts are bundled. None ran here.

Neither completion of this checklist nor static inspection establishes photographic
acceptance. The local tester still needs to exercise repeated gestures, cancellation,
undo/redo, switch/load/restart, cropped/rotated views, freeze/reconstruct/smooth,
RGB8/RGB16, tiled boundaries and full-resolution source mismatch behavior.

Static findings already resolved before wiring:
- Do not send the inverse field directly to the established forward-field sampler:
  its adapter deliberately uses strength=-1 to preserve visible tool direction.
- Intermediate image results must still be displayed while the next path candidate
  is queued; replacing every in-flight request on every pointer move would starve
  continuous feedback. The UI now keeps one running render and one latest pending
  candidate; explicit cancel interrupts the worker. Only the final candidate can
  be acknowledged for mutation.
- Source-locator proof is not reused as output proof. The manual preview owns its
  own epoch/session/revision and producer projection; the drawing surface never
  shows or permits painting on an unrelated immutable source capture.
- Freeze/thaw use saturating accumulation so fully protected/unprotected pixels
  can reach exact endpoints, unlike an asymptotic-only protection blend.
- Resource admission is explicit and not a destructive simplification: the work
  ceiling is 16 billion charged operations after considering repeated full-size
  gestures; image/point/dab/memory bounds and a 120 s worker deadline still apply.
  Neither success nor rejection implies measured interactive performance.

Shared lifecycle closure:
- Main proxy output, recovery actual-output review, history/device/document replay
  and full-resolution inspection include the same final manual stage. Source
  recovery/local-grade masks remain upstream and are not double-warped.
- Native readiness, engine epoch restart/end, mutation invalidation, one-shot
  output presentation proof and terminal receipts are connected.
- Empty recipes impose no manual pixel/work/memory limit on unrelated exports.
  Nonempty zero-displacement/freeze-only intent is still verified and replayed.
- v7 rejects a missing/null/incompatible manual record, including owned nested
  history states. v1-v6 migrate only missing manual intent; v5 independent groups
  and v6 recovery remain intact. Existing sparse project fixtures now explicitly
  carry empty manual intent; genuine legacy fixtures declare the older schema
  before adding documents. Assertions are preserved; no tests were run here.
- Continuous-preview source validation hashes at session admission and final
  commit. Intermediate candidates check the owned source binding, file stamp,
  document revision and projection before/after rendering instead of rereading
  a potentially large RAW file for every point. Full export still verifies SHA.
