# Target-owned original-shadow scalar transfer

Source implementation scope, 2026-10-23. All runtime, numerical, photographic,
packaging and interaction acceptance is **UNRUN**. The original-shadow family
remains partial; this does not implement AI shadow extraction.

## Ownership boundary

`lnx.original_shadow.v1` contains exactly `enabled`, `strength`, and `blend`.
It never contains floor samples, retention vectors, subject masks, source pixels,
background assets or uniform-floor acknowledgments. Every target must own these
independently. Enabling, including enabled with zero strength, requires eligible
active ID background, confirmed target samples and manual full-source subject
support. Existing nonzero original-shadow versus designed-shadow exclusions stay.

A scalar disable is not sample clear/reset. Target samples and applicability
confirmation survive disable and history restore. Whole-ID portability keeps its
nonneutral original-shadow refusal. Shadow scalar transfer cannot be combined
with whole-ID or spill scalar transfer in this slice: their overlapping ID state
and combined visual review budget are not silently treated as independent.

## Review, commit and history

Each eligible target requires an isolated complete-source before/after render,
including disabling, zero strength and apparently neutral scalar values. The
256px review PNGs are display-only, at most 150000 bytes each, and never become
source or mask evidence. At most eight targets enter one visual review; larger
sets are refused, not silently truncated. Each pair has explicit visual review
and ordered hash acknowledgment.

The proof binds document/revision, actual original or creative-return immutable
source, full candidate and people identities, dimensions and exact scalar values.
Targets retain their own floor/subject evidence; no shared original path or source
face analysis can stand in for it. Changed source, target edits or stale review
invalidates commit. Publication and rollback check frozen expected identities.

Presets may save scalar intent without samples. Applying requires a new review
against that target's current eligible evidence. Batch commit uses frozen per-row
proofs and scoped undo; existing batch ledger remains session-only. No claim of
cross-restart batch undo follows from this implementation.

## Route map

- `original_shadow_scope.py`: portable scalars, target eligibility, dependency
  keys and exact scoped restoration; registered through `scope.py`.
- `original_shadow_transfer_review.py`: target-owned preparation, proof checking,
  display images and acknowledgments, independent of direct-panel tokens.
- `batch_preflight*`, `batch_sync.py`, `batch_group_history.py`: frozen target
  records, reviewed commit, receipt reconciliation and scoped history.
- `local_grade_preset_review.py`, `preset_controller.py`, `workflow_ports.py`:
  preset capture and new per-target review, refusing direct unreviewed apply.
- Native transfer protocol and batch/preset admission: strict bounded schema,
  source/image proofs, correlation, acknowledgment and uncertain outcome fences.
- Batch and preset UI: explicit actual target pairs, blocked-target reasons,
  source/target identity, stale review and unknown-commit handling.

## Remaining limits

Manual uniform diffuse-floor estimation cannot reliably distinguish same-colour
stains, texture or changed illumination. Dark, reflective and nonuniform floors,
colored lighting and general AI extraction remain unsupported. The existing
full-source RGB16/float source path and geometric mask coverage precision apply;
this does not add broad alpha/HDR support or justify clipping it. Mixed-person
presets retain the existing stable-person/candidate-graph restrictions.

Required UNRUN acceptance includes original/derived mixed target sets, missing
or changed target samples, dormant enable/disable history, full source mutation,
neutral and zero strength, blend differences, malformed/missing/reordered image
acknowledgments, stale token, document switch, commit publication failure, exact
rollback and same-target undo, plus full-resolution render/export parity.
