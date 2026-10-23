# Reviewed persistent person associations across independent documents

Baseline `87ffb04583202d7384074d3fffc6b2840f319a3c`. Source integration only; all new fixtures are AUTHORED / UNRUN. No application imports, execution, tests, builds, typechecks, model inference or downloads were performed.

## Requirement boundary

The supplied handbook §§4–5 requires face overrides > confirmed person intent > group intent > all-people intent, explicit cross-photo confirmation, retained history after unlink, source/target/module/policy freezing, and protected group undo. Traceability: `LNX-PORTRAIT-004`, `LNX-PORTRAIT-005`, `LNX-BATCH-001`–`004`, workflow `47211` (`LNX-REF-WF-47211-94a68c31d0`) and workflow `32480` (`LNX-REF-WF-32480-c75523501b`). This slice implements a bounded manual association path, not automatic identity recognition or proprietary model equivalence.

The earlier one-transfer explicit face map remains available and still creates no persistent identity. This separate mode supports:

* Create an explicitly reviewed anonymous association with selected scalar intent.
* Patch selected scalar leaves from the reviewed source face into the common person intent, retaining unselected shared leaves.
* Unlink the entire association atomically. Explicit face edits, independently owned masks/support/analysis and existing history remain; inherited person intent is removed, so appearance may change.

There are 2–16 members including the source, exactly one selected face per document and one retained current document per independent portrait scope. A project-shared scope must contain only its current source asset; private scopes may retain dormant source slices. These are explicit safety boundaries, not truncated target lists. There is no automatic matching, membership expansion, group transfer, individual-member removal, or individual shared-leaf removal in this slice. Ordinary face edits remain local and take precedence over shared intent. Updating shared intent is an explicit all-member review, not automatic propagation of arbitrary slider changes.

## Durable owner-qualified representation

`people_cross_owner.py` extends anonymous person records with a versioned `cross_owner` capsule. The common content contains association ID, canonically ordered member document/scope/original-source/FaceRef identities, and selected scalar intent. Each replica also names its local document. A SHA-256 content generation excludes only that local owner field; it is not a monotonic authorization counter because protected undo may restore earlier accepted content.

Local graph validation requires the exact pinned face, one confirmed local link and person-level overrides exactly matching the capsule. The existing resolver supplies real person inheritance. Association creation does not copy source face overrides or masks into targets. Source values are seeded only from explicitly selected resolved leaves. Normal person setters, unsetters and relinking cannot mutate one replica independently.

The same immutable source hash in two virtual copies does not establish ownership. Actual host/row document identity is transported separately through preview preparation, full candidate rendering, frozen export snapshots and typed export specs. Neutral association recipes cannot bypass owner checks through passthrough export. Existing derived guards admit only internally consistent, independently owner-bound replica persons; ordinary shared links and groups remain guarded.

New virtual copies detach membership and materialize only inherited winning scalar appearance as copy-local face overrides, without replacing already explicit face overrides. This preserves the copied appearance but does not silently enroll a new document. The original association is unchanged.

## Visual consent, transactions and history

The existing read-only face inventory displays bounded previews from each actual effective source and its independently retained verified FaceRefs. Available entries expose accepted local capsules, not a promise that remote members remain available. The UI requires manual one-face choices, loaded source previews, complete current membership and compatible capsules before persistent actions. Source and target participants are both shown in the frozen review; source changes have a separate explicit outcome.

`people_cross_owner_workflow.py` uses the existing `FrozenBatchController` token store and receipt lifecycle. It binds exact source, graph, analysis and document proofs, fully prepares every candidate with that target's own effects and support, and rechecks after expensive preparation. Persistent operations require the atomic recheck policy. Partial skip-and-report is not supported. Commit receives only the frozen token.

Publication uses `people_batch_ledger.commit_scoped`, not a second registry, history stack or transaction queue. `people_cross_owner_ledger.py` checks whole-cohort consistency at the common publication boundary, including protected undo/redo. Every touched replica must have its matching actual document/source/FaceRef target; incomplete or divergent generations refuse before any graph publication. Existing sparse expected-value patches preserve unrelated later face edits and refuse conflicts. Capsule content naturally participates in the existing source-context digest, protecting source-switch undo from overwriting changed associations.

Project admission/save/load validates current owner-qualified replicas and active consensus, separately from internally valid historical generations. Missing or dormant members preserve the last accepted local projection and suspend shared mutations; they are not rebound to current faces. A linked face cannot be reanalysed while its exact FaceRef is pinned: explicit complete unlink is required first. Cohort edits and whole unlink require every member available, current and reviewed. No orphan-detach or missing-member recovery UI is implemented here.

## Integration map

* Schema, mutation and copy safety: `people_cross_owner.py`, `people_state.py`, `people_associations.py`, `virtual_copy_people.py`.
* Review and atomic publication: `people_transfer_inventory.py`, `people_cross_owner_workflow.py`, `people_batch_transfer.py`, `people_cross_owner_ledger.py`, `people_batch_ledger.py`.
* Project consensus: `people_cross_owner_project.py`, `project.py`, `people_host.py` save/stage/load hooks.
* Actual owner transport: `people_document_owner.py`, portrait host/input/runtime/export modules, `export_snapshot.py`, `export_recipe.py`, `export.py`, and explicit row-aware candidate/virtual-copy/reference/semantic/optics capture callers.
* UI: `ui/src/people/associationProof.ts`, `associationRequest.ts`, `AssociationEvidence.tsx`, inventory/transfer controls, and existing batch workflow/review.
* Native routing: existing batch command accepts the structured request and frozen-token commit. No new native command registration or `main.rs` changes. Unlink's empty module selection is admitted only for its explicit association request in the UI; backend validates the exact operation envelope.

## Remaining limitations and local acceptance

Automatic person candidates, shared group membership, multi-face-per-document cohorts, multi-document project scopes, membership expansion/removal, orphan recovery and individual shared-leaf unset remain unfinished. Unsupported target operations still fail existing full candidate/consumer checks rather than borrowing source analysis. Broader support-bearing transfer, derived semantic/reference/optics planner adaptation, ID recovery/spill/original-shadow work, transparent photo pipelines and signed/HDR returns remain explicit residuals. No HDR/alpha flattening or clipping was introduced.

Required local acceptance includes original↔derived and same-byte virtual-copy associations; differing dimensions and independent masks; explicit face precedence; all-member review including source; stale source/analysis/graph/document rejection; full preview/export agreement; neutral passthrough refusal; copy detachment; project/package/recovery reopening; source-switch dormant slices; unlink and protected whole-cohort undo/redo; later local edits retained; incomplete-member and budget refusals; and uncertain receipt replay without retransmission. Source fixtures specify cases only. None is claimed to have passed runtime acceptance.
