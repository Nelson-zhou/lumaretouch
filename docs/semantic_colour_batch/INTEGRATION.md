# Global semantic-colour batch/preset integration contract

Status: source-integrated global batch and portable-preset workflow. Runtime,
packaging, performance and photographic acceptance remain UNRUN.

## Implemented computation and ownership

`semantic_colour_batch_fit` analyzes the reference once in a real bounded worker.
Its content-digest-checked cache contains the exact reference binding, actual model/runtime receipt,
full-precision spatial RGB/class/weight samples and coverage, never target results.
Every target independently freezes its full edited canvas, analyzes that rendered
canvas and calls the same original Rust fit. Cached reference identity/runtime
must match each target. The explicit portable manual offsets are added to each
new target baseline, with strict per-target errors rather than clipping/drop.
Requested missing classes are failures, even when that group is disabled.

`BatchFitJob` owns a separate offline process group, bounded input NPY headers,
240-second CPU/wall budget per image, cancellation and 24 MiB private result cap.
No model/runtime is needed for existing applied recipe replay. The cache is not a
trained colour network. Optimization diagnostics are marked initial-fit-before-
manual-offset only; preview is the actual point operator on full-precision spatial
samples. None of this establishes photographic quality.

`SemanticColourBatch` uses the existing FrozenBatchController.store and immutable
FrozenTarget/FrozenPlan records. It does not create a second transaction queue.
Private proposal files are capped at 512 MiB globally per owner and 24 MiB each;
plan metadata contains only content-addressed descriptors. Receipts contain small
summaries. Before/after previews are lazy, one selected target at a time. Existing
store expiry/eviction releases private artifacts. One review admits up to 128
explicit targets; excess is rejected, not silently dropped. Resource-budget failures
are explicit target blocks, with skip-and-report or all-or-none recheck policy.

`semantic_colour_batch_ledger` writes exactly the three AI-owned fields and uses
BatchSyncController.ledger, existing document revisions and history. Live target
render validates before parked writes. Undo/redo checks only the owned contribution,
preserves unrelated later edits, and restores retained masks without inference.
Later geometry changes preserve visible suspension, never stale-coordinate replay.

## Registered host and UI path

App passes the separate `semantic_colour_workflow_protocol:1` capability to
`ColourTransferTools`, which mounts the workflow within the single-photo panel.
The exact handbook batch/preset leaf routes to the mounted workflow instead of
a disabled placeholder or generic text-preset panel. The workflow shares that
panel's native owner, canonical document context and
unknown-mutation fence. A pending single-photo capture/review must be closed
before workflow preparation. Workflow activity disables single-photo writes.

The existing Tauri `semantic_colour` mailbox validates each exact action shape,
retains bounded session progress, and sends reader-side Event cancellation out of
band. Preparation waits are target-count-scaled, not the single-photo 60-second
wait. Requests remain 2 MiB, each receipt at most 8 MiB and retained mailbox data
16 MiB. Status never retransmits the original mutation. The engine routes to
`semantic_colour_workflow` on its command thread. No second native command,
transaction store, document identity or history stack is introduced.

Scope `lnx.semantic_colour.v1` is registered as portable intent with the explicit
`semantic_colour` dedicated transport and target-recompute review contract.
Generic batch preflight/commit and generic text-preset save/apply refuse this
module with an actionable reason. They cannot copy source gains/masks or omit
reference pixels. The existing preset panel labels and excludes that special
transport; the dedicated `.lrtcolour` import/export controls are source-mounted.

Batch apply requires a frozen token plus explicit review. Source/current photo
is excluded in ordinary batch mode. Checked preset imports privately prepare the
current target, still performing a fresh render, semantic analysis and fit.
Publication and group restore use the existing batch ledger. Active-image writes
record ordinary history once; parked targets retain ordinary undo snapshots.
Generic batch undo/redo dispatches tagged semantic entries to the same owned-
field restore. Current project v14 carries the already-introduced semantic v12
fields/resources without changing the container or body/people stage ordering.

## Actions and resource lifecycle

- `batch_prepare`, `batch_preview`, `batch_apply`, `batch_restore`: real per-target
  preparation, one lazy checked preview, frozen publication and owned undo/redo.
- `preset_export_prepare`, `preset_export_write`, `preset_export_status`,
  `preset_export_release`: explicit full-photo inclusion, private immutable staged
  archive, atomic no-clobber publication by default, exact file readback, release.
- `preset_import`, `preset_prepare`, `preset_forget`: bounded checked archive
  ownership, current-target recomputation/review, release without applying.
- `workflow_cancel`, `workflow_release`, `workflow_inspect`: session cancellation,
  private-resource cleanup and explicit read-only write-outcome inspection.

Shutdown and workspace replacement close staged imports/exports/proposals.
Superseding a review releases its old FrozenBatch token and artifact descriptors.
Ordinary lifecycle ticks prune expired plans; they do not run semantic inference
or whole-batch inspection. A completed export retains its exact staged identity
until acknowledgement/release, allowing lost replies to be reconciled before
another destination write. A late-settled receipt can be explicitly recovered in
the mounted UI. After engine/workspace replacement, file inspection can compare
the retained original small receipt's exact SHA/size without recreating its lost
temporary artifact or retrying a write. No silent overwrite or original mutation
retry occurs.

A post-publication failure remains `outcome_unknown` at the outer native receipt,
not a nested failure disguised as success. Explicit `workflow_inspect` compares
all retained attempt targets against owned before/after identities, reports
before/after/both/different/missing/invalid and recent ledger summaries, and runs
no ML or render. Its result does not establish current geometry or image quality.
Automatic state refresh cannot clear an unknown batch-write fence. The UI requires
explicit inspection and user acknowledgement before further mutations; the old
claimed token is never replayed. Engine loss/workspace replacement cannot invent
missing old transaction evidence.

`packaging/stage-engine.sh` already stages the entire engine source tree. This
slice also stages its integration/portability/evidence documents alongside the
existing native source attribution. No software/model download or build was run.

## Acceptance still required

All native fixture execution, Python tests, UI typecheck/build, real-model inference,
independent photographic target results, cancellation races, project reopen/export,
RGB8/16/full-resolution agreement, memory/performance, portable-file reconciliation,
and history/conflict behavior remain Qoder acceptance work. Local dual-image mode
and any source-bound user marks remain nonportable. Six-class categories are not
person instances; sky/lips/instance adapters are not claimed by this integration.
