# Original-shadow scalar transfer: explicit remaining source work

Read-only source audit, 2026-10-23. Not implemented or accepted by the direct
painting slice. Keep whole-ID nonneutral original-shadow refusal intact.

## Permitted proposed payload

Only `enabled`, `strength`, and `blend` may transfer. Every target retains its
own uniform-floor confirmation, lit-floor/retention vectors, subject support,
background asset and spill intent. Enabling (including enabled + zero strength)
requires an active independently reviewed target ID background and target samples.
Disabling and zero strength also require real target-specific before/after review.
A scalar disable retains samples; it is not the clear-and-reset operation.

## Coherent integration map

- New `engine/src/lumaretouch_engine/original_shadow_scope.py`: scalar validation,
  install, exact legacy/dormant restore and dependency-key ownership. Model the
  existing `spill_removal_scope.py` without copying source masks. Register in
  `scope.py` and `optics_auto_scope.py`. Whole-ID and shadow-scalar modules must
  not coexist in one transfer; simultaneous spill + shadow transfer needs an
  explicit combined review/budget design, not two unrelated acknowledgments.
- New target review adapter analogous to `spill_transfer_review.py`: isolated
  complete before/after render, immutable source, document revision, full
  candidate/people fingerprints, dimensions, exact scalar payload and ordered
  image-hash acknowledgments. Preserve mixed-person and stable-person fences.
- `batch_preflight.py`, `batch_preflight_controller.py`, `batch_sync.py`,
  `batch_group_history.py`, `workflow_ports.py`: target eligibility, private
  compact proofs, commit-time/post-publication checks, frozen rollback identity
  and scoped undo. Current generic batch history is session-only; cross-restart
  batch undo cannot be claimed without its own persistence implementation.
- `local_grade_preset_review.py`, `preset_controller.py`: save scalar-only
  snapshots, refuse direct unreviewed application, prepare a new target pair,
  verify installation and rollback. Presets never carry source floor samples.
- Native protocol plus `batch_api.rs`, `batch_host.rs`, `preset_api.rs`,
  `preset_host.rs` and module registration: bounded source-bound PNG receipts,
  hash acknowledgment, stale tokens and uncertain commit handling.
- `ui/src/batch/batchWorkflow.ts`, `BatchReview.tsx`, preset workflow/hook/panel:
  load and acknowledge each actual target pair, show ineligible targets and
  retain document-switch, stale-review and unknown-commit fences.

Existing nonzero active eligibility in `id_background_state.py` must still require
manual full-source subject geometry and exclude simultaneously designed shadows.
Never substitute source-photo support or copied review claims. All future
numerical, runtime, packaging and photographic acceptance remains UNRUN.
