# PhotoCraft preview idea adaptation (not enabled)

Status: original-design implementation, **default off and not production-enabled**.
There is no UI, environment-variable, recipe or IPC activation. The private engine
cache's `enabled` flag alone is insufficient: an audited live-upstream context
provider must also exist. None is installed. Complete invalidation coverage for
all runtime-only state and temporary previews has NOT been proven. This change
therefore claims no measured or user-visible speed improvement.

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

Implement and audit `_grading_prefix_audited_context` to return immutable bytes
covering ALL upstream live state, including unsaved/temporary overrides, tensor
and mask content changes, assets, source identity and relevant runtime readiness,
plus actual colour-space and signal-domain labels. Never substitute persisted
recipe/revision alone, object identity alone, or a generic assumed sRGB label.
The additional key covers load/document, revision, source tensor identity/version,
pipeline identity, baseline generation, dimensions, device and dtype. Unknown
context must return None and execute the original full render. Audit every
load/close/history/edit/temporary-preview/compare/context path, including calls
that do not enter the transport. Eligibility remains after normal runtime sync;
cache lookup remains after normal readiness checks. Do not weaken those guards.

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
