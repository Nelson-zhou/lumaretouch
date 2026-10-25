# Reviewed workflow preset handoff

Baseline: c04fa7c028f9d3325ed72d8796e4ff384d5cc432.
Requirement: workflow:8YEKwsjJg7, extending the existing local directory workflow.
Status: partial source-connected; runtime, filesystem crash, UI and device
acceptance remain UNRUN. This is not a second new workflow algorithm.

The actual stored preset catalogue supplies names, IDs and exact content hashes.
Complete exposure/white-balance recipes and their mixtures with `lnx.skin.v1`
enter the source-connected route. Skin requires the explicit fresh-original
preparation below; recipe selection alone does not establish target readiness.
Any other selected module, XMP-specific review or unsupported retained portrait
review rejects the entire preset, never silently dropping those effects.

The original ingestion lease stays owned while discovery pauses. Each imported
photo is explicitly opened, fully rendered before/after, paged with immutable
image hashes, actually displayed and separately approved. The native workflow
core journals ApplyPreset before the ordinary preset dispatcher mutates state;
normal history capture/record/finish stays authoritative. Approval alone is not
an apply receipt. User save and verified return to the prior editor document are
separate actions before PresetApplied can permit the export phases to continue.

Stable document IDs and transient load IDs remain distinct. Actual managed-file
SHA/size/stat must match the durable import receipt. Source, complete candidate,
people and repair proofs are checked again through apply and explicit save.
The scoped save preserves other documents, inactive versions, source registrations
and unrelated project fields, then uses the existing codec and pinned-directory
content CAS. Hydrated live state comes from the exact stamped saved body.
See PRESET-SAVE.md for cooperative-lock/path-based immutable-sidecar assumptions;
this is not a hostile-writer transaction proof.

Per-operation handoff snapshots and retained original-step receipts remain
queryable without rerunning writes. Possible save/apply outcomes stay unknown;
engine replacement does not fabricate restored approval or automatically replay
work. No original project overwrite rollback is attempted. Restart reconciliation,
broader mixed portrait preset owners, initially empty editor selection and
unattended auto-approval are not implemented by this slice. Tether hardware remains
unverified and unchanged. No tests, builds, typechecks, product imports, hardware
interaction, inference, installation or downloads were performed.


## Explicit fresh-original skin preparation (source-connected, UNRUN)

The earlier scalar-only extension (`9e9d543`) and native shape alignment
(`56549ea`) did not establish an executable skin workflow. Checkpoint `bd0ed32`
disabled it after source tracing found a target people-owner transition missing
from review. This slice replaces that disabled scaffold with a bounded explicit
preparation path; **this is source integration, not runtime acceptance**.

1. Opening an imported target enters `awaiting_preparation`, not automatic
   inference. The user must choose `prepare_skin`: analyze this original and
   select only its own skin mask. Only the complete canonical fresh state (apart
   from loaded proxy dimensions), zero smoothing strength, no undo/redo entries,
   original non-copy source and no existing target people edits are admitted.
2. `SkinPreparation` dispatches the existing `cmd_precompute` with exactly
   `backend='mediapipe', channel='skin'`. It then calls the canonical
   `_people_sync(strict=True)` / `_people_bind` to establish that target's
   retained graph BEFORE review. The existing binder owns IDs, measured evidence,
   masks and mirroring. No donor face, automatic fallback or shadow graph exists.
3. Zero/multiple/manual/disabled faces, detection-limit hits, unknown detector
   bytes, stale retained landmarks/cursor/target, existing target edits and shared
   associations refuse. One detection is **not** claimed to prove a full census;
   the actual complete-image before/after review remains mandatory.
4. `workflow_preset_retained_skin.require_candidate` invokes the same
   `people_scope.plan_preset` used by normal application. Legacy skin strength is
   still its existing scalar operation, NOT translated to a different portrait
   algorithm. The planner must return the exact managed target, no graph patch,
   unchanged prepared graph and the reviewed complete candidate state.
5. A review-render failure with unchanged preparation retains that preparation;
   retry renders review only, not inference. Approval and journaled normal
   `PresetController` application remain separate. Normal undo returns to the
   explicitly prepared zero-strength state; preparation does not insert a second
   undo/history chain.
6. Before approval, cancel verifies the entire observed preparation/source/owner,
   then reuses `_people_history_apply` / `stage_document_restore` for the source
   slice and `_replay_state` for its original no-analysis neutral state. Runtime
   target banks are restored only under that exact unchanged proof. Document and
   graph fences remain monotonic. Any source/context/edit drift or uncertain
   recovery boundary stays Unknown; no blind rollback or replay is allowed.
7. Explicit save stages the target people context through canonical
   `virtual_copy_people.save_project` in a detached read-only snapshot view.
   Shared target graph/landmark/cursor deltas or a private target row are allowed;
   other documents, associations, sources and prior immutable evidence are not.
   See PRESET-PEOPLE-SAVE.md. Original import receipt origin and saved applied
   row-stamp authority are checked separately after return, and runtime
   `_precompute` is excluded from persisted recipe encoding just as in normal
   save. Derived analysis is not smuggled into project JSON.

A failed normal analysis command may mark the existing project recovery owner
**tainted**. This preparation does not clear or hide that flag: the handoff stays
Unknown for existing recovery reconciliation/reopen, rather than offering a
false clean retry. Successful analysis followed by a known refusal can restore
its exact state only when that recovery owner remains clean.

Remaining scope: no preparation of edited/previously analyzed/virtual-copy or
composite targets; no multi-face selection, unattended approval, restart-resume
inference, or broader portrait preset family. Only `lnx.skin.v1` plus exposure/WB
is admitted. `lnx.blemish.v1` and all other unsupported modules reject the whole
preset, including a mixed recipe. Unclassified unrelated imports or incompatible
saved portrait metadata may cause the bounded save to refuse rather than silently
rewrite other documents. Missing models and hardware/runtime support remain
actual runtime requirements, not claimed verified by source inspection.

Workflow precedent: darktable's official [selective history transfer guidance](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/lighttable/history-stack/)
separates selected parameter transfer from replacing complete history. No
external implementation or donor masks are copied.

All new preparation, retained-target, save, phase and receipt fixtures are
**authored UNRUN**. Python AST/whitespace checks are not execution, build results,
real-device image quality or performance acceptance. No product imports, tests,
builds, typechecks, inference, installation, uploads or pushes were performed.
