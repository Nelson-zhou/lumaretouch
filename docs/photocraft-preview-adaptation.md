# PhotoCraft preview idea adaptation (not enabled)

Status: original-design implementation, **default off and not production-enabled**.
There is no UI, environment-variable, recipe or IPC activation. A real production
context provider now exists for the deliberately narrow RGB8/exposure/HSL lane
described below. Local acceptance can set the private cache's `enabled` flag to
exercise it without fabricated contexts. The flag remains False by default.
Broad runtime-state coverage and runtime acceptance have NOT been established.
This change claims no measured or user-visible speed improvement.

## Pinned research and provenance

Read the primary source at PhotoCraft commit
`ff4738810134d7f7e68b49f2e4f231b686282ff3`:

- [adjust_preview.rs](https://github.com/storytold/photocraft/blob/ff4738810134d7f7e68b49f2e4f231b686282ff3/crates/ui-egui/src/adjust_preview.rs)
  Git blob `b0362f20564ceb9c38d668e0120848fdeb14958b`.
- [proxy.rs](https://github.com/storytold/photocraft/blob/ff4738810134d7f7e68b49f2e4f231b686282ff3/crates/ui-egui/src/proxy.rs)
  Git blob `a3a73c754261ec2f4d14835f5588ea3604daebf7`.
- [filter_preview_worker.rs](https://github.com/storytold/photocraft/blob/ff4738810134d7f7e68b49f2e4f231b686282ff3/crates/ui-egui/src/filter_preview_worker.rs)
  Git blob `0950e67939c7c9c26f4a3ec21f8f35aa0f46e8cb`.

Idea used: separate stable session work from changing slider settings and retain
only an eligible reusable base. No source text/code fragments, dependencies,
models, fonts, icons, branding, compositor or Rust engine were copied. There is
no new third-party vendored component. Lumaretouch's existing single-flight/latest
queue, request cancellation, readback and publication fencing remain authoritative;
PhotoCraft's different cancellation policy is deliberately not adopted.

## Boundaries

The canonical proxy sequence is split, not duplicated: prefix ends immediately
after semantic colour; suffix begins at colour grading and retains the existing
selective-colour, colour-editor inspection, detail, tone finishing and source-grain
callback order. Inspection taps run the full canonical path. Commit, cancel,
rollback, compare and ordinary renders do not request cache reuse. Export code is
unchanged. Active original-source colour-editor or grain rendering and any
nonempty sky-replacement state are excluded, without downgrading their quality.

One private NCHW float32 snapshot, at most 64 MiB, stays on its existing device.
Store uses a detached clone, hit returns a clone, suffix never gets retained
storage. Budget or snapshot-allocation failure uses the ordinary full pipeline.
A completed prefix is stored only after cancellation/context checks, repeated
under its generation lock. Exceptions never store partial work. No cache state is
serialized. Prefix builds, hits, retained bytes and suffix runs are inspectable
on the internal cache object; these are counts, not performance measurements.

Baseline generation is separate from the controller epoch: repeated grading
preview requests retain the baseline generation. Non-preview ingress, service
stop, source replacement and non-grading frame rendering invalidate it. This is
conservative (even some reads evict); it is not a claim that every possible
mutation is covered.

## Required before any enablement

The real `grading_prefix_context.narrow_context` provider admits only an RGB8
proxy with zero smoothing and no channel, optional exposure/WB and HSL, and every
other prefix consumer proven inactive by its actual runtime early-return inputs.
It does not inspect only persisted recipes and does not hash opaque runtime
objects. Unknown/missing attributes or nonfinite/non-plain scalar state miss.

The context includes exact finite exposure parameters, reference temperature,
prepared WB gains, all 24 HSL values and filter-validation arguments as canonical
JSON bytes. Source/load/document/revision/generation/dimensions/device/dtype are
in PrefixKey. Source tensor mutation is covered by its PyTorch version counter;
tensors without a version counter are ineligible. The colour-space/domain labels
name the existing encoded working-RGB proxy contract, not a new inferred ICC
conversion. Decoder ICC handling, original-source rendering and export are
unchanged. These labels are not permission to cache arbitrary external tensors.

### Static consumer audit for the narrow lane

- `vram._retouch_prefix`: strength exactly zero, channel None. `base()` chooses
  repaired pixels if present, so repair_base/repair_ops are excluded. No masks or
  smoothing products are consumed in this lane. Filter validation still executes
  before cache lookup.
- `vram._apply_light_cached`: field absent; no dodge/burn operand. Its numeric
  exposure and the legacy grade amount must remain finite scalar values.
- `FabricStage.apply`, `EffectRecoveryStage.apply`, `StudioBackgroundStage.apply`:
  amount/field, required/fields/suspensions and required/fields/suspension are
  checked directly. No recovery or studio field is admitted.
- `people_pipeline.active`, `people_engine_runtime.require_ready`: no prepared
  people graph and no suspension. Readiness is still checked on every retouch,
  including cache hits. `people_host._people_sync` returns without a graph for
  an unanalyzed source, so this lane is reachable without artificial fixtures.
- `facial_wrinkle_layer.refresh_source/apply_delta`, `under_eye_layer.refresh_source`,
  `lip_makeup_runtime.refresh_source`, `lip_makeup_layer.apply_delta`: source layers
  and deltas must be absent; enhancement amounts zero and lip recipe neutral.
  Nothing can be lazily rebuilt behind a supposedly neutral recipe.
- `vram.apply_deform/apply_enhance`: no unit/face-geometry fields or enhancement
  inputs; zero amount maps. Suspended face geometry is excluded conservatively.
- `vram.apply_exposure` reads only exposure_params, exposure_ref_k and prepared_wb;
  all are captured. `white_balance_recipe.prepare_state` returns the actual three
  gains (or None). `vram.apply_hsl` reads the captured 24 scalar bands.
- `PrimaryCalibrationStage.apply_t`, `ExtendedToneStage.apply_t`: inactive flags
  are required and tone override is absent. `LevelsStage.apply`, `vram.apply_curves`:
  no compiled active operands. LUT object/volume absent, grade parameters zero.
- `LocalGradeStage.apply`, `SkyReplacementStage._apply`: no local fields or
  suspension; sky must be exactly empty and not suspended. No sky fallback is
  made cacheable. `vram.apply_background`: no active/background tensors.
- `ManualLiquifyStage.apply`, `OpticsStage.apply`: no field/active optics and no
  suspension, preserving their pre-no-op error guards. Geometry is identity.
- `ReferenceColorStage.apply_t`, `SemanticColourStage.apply_t`: inactive flags;
  semantic suspension excluded. This ends the prefix consumer list.
- Other owned preview objects, inspection/prompted/semantic/live-grade owners
  and override slots exclude eligibility even while idle; active preview/publication flags and original-source editor/grain are
  independently excluded. Ineligible frame contexts evict retained snapshots.

Each post-prefix/store/hit recheck reruns these predicates and captures current
operator arguments, so direct live parameter changes do not require a history
revision to miss. External non-preview ingress invalidates generation; direct
non-grading renders/source replacement also invalidate it. Broader spatial,
portrait, masked, source-derived, external-asset and temporary-preview combinations
are intentionally unsupported, not assumed to share this audit.

Before enabling by default, Qoder must validate this lane against actual engine
transactions, threading/device behavior and pixel output. Expanding it requires
an explicit consumer-by-consumer context/invalidation audit, not removing rejects.
Do not weaken runtime sync, readiness, validation or publication guards.

## Validation handoff (UNRUN)

Only source/AST inspection was performed. No product imports, tests, builds,
compilers, typecheckers, inference, downloads or installs were run. Added tests
are authored but UNRUN. Qoder/local testing must cover:

1. CPU and supported GPU full-vs-cached pixel equivalence, including a suffix
   deliberately mutating input in place; one prefix build followed by N suffixes.
2. Cache miss on every upstream edit/override and on same-path reload/source
   replacement, document switches, history, comparison, close and cancellation.
3. Newer request arriving before prefix completion, during snapshot clone,
   during cache-hit clone, before suffix and before shm publication. Old frames
   and old snapshots must not survive context changes.
4. Active editor, grain, sky, scope/inspection and every competing preview:
   original path/guards/quality flags preserved, no cache reuse.
5. Over-budget/allocation failure, source dimensions/device/dtype changes, zero
   strength and masked strength; portable save/export/preset contains no cache.
6. Commit/cancel full render and history behavior unchanged, including rollback;
   existing controller/service fence regressions continue to pass.

Remaining transfers are unchanged: grading tensor CPU conversion, NumPy/Rust
processing and device return, VRAM readback, shared memory and Viewer WebGL upload.
This is neither end-to-end GPU residency nor PhotoCraft engine integration.
