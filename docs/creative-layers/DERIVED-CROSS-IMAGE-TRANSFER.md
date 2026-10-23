# Reviewed cross-image parameters on effective creative sources

Baseline `2f01b699085758d4be02595d99aa1aff9d8c3d32`. Source integration only. All added/updated fixtures are AUTHORED/UNRUN. No product import, execution, test, compiler, typecheck, inference, installation or download was performed.

## Requirements and scope

The supplied handbook sections 4–5 (manual text lines 1012–1027) require explicit user confirmation for cross-photo person association, immutable source versions, selected target/module scopes, per-target preflight, parameter-key replacement, expected-revision conflict handling, truthful per-target outcomes and protected group undo. Unselected parameters and source-owned masks/landmarks must remain intact. Association removal must not delete photographs or editing history. The text references official guides 47211 (people properties) and 32457 (presets); this slice uses the supplied text, not a claim to have freshly verified those live pages.

The existing frozen registry maps these workflows to `LNX-P0-BATCH` and `LNX-P0-PRESET`, `lnx.batch.v1.module_scope` and `lnx.preset.v1`. Exact portrait/batch acceptance references are `LNX-REF-WF-47211-94a68c31d0`, `LNX-PORTRAIT-005` (manual cross-photo confirmation), `LNX-PORTRAIT-004` (leaf inheritance), `LNX-REF-WF-32480-c75523501b`, and `LNX-BATCH-001` through `LNX-BATCH-004`. M14 return/history ownership continues `LNX-REF-WF-127932-a9c143a25d` and `LNX-REF-WF-127932-c7783ea5fb`. These are requirement references, not completed acceptance claims. The existing operation registry remains authoritative; this slice adds a narrower admission set, not new invented commercial algorithm semantics.

This is two coherent routes:

1. General transfer of explicitly supported global parameters, using the existing frozen batch/preset owners.
2. One-transfer-only, visually reviewed source-face → target-face correspondence using each endpoint's own document, source and analysis evidence. This is **not** a newly saved/shared person identity or a face-recognition algorithm.

## General batch and presets

`creative_derived_transfer` and `scope.check_derived_modules` admit actual stored/frozen module objects, not request labels. Supported modules are exposure, white balance, levels, curves, HSL, extended tone, photo detail, photo grain, colour grading, primary calibration, selective colour and colour editor with canonical `scope=all`. Unsupported modules reject even when their supplied values happen to be neutral. General transfer does not transport local masks, support assets, landmarks, face identity, model outputs or canonical source pixels.

Cross-image crop is deliberately not admitted here: the handbook requires normalized coordinates and target preview, while the general review currently presents parameters rather than a genuine target crop preview. Existing direct per-image crop remains available. Skin/blemish, local grades/masks, custom LUT, studio/ID/sky background, optics, reference/semantic colour and legacy portrait scopes are not enabled through this general route. Supported portrait parameters use the separate exact-face route below.

`batch_preflight` retains compact immutable source/target proof JSON within its existing total metadata budget. `batch_preflight_controller` binds current canonical content and original-file provenance for every selected eligible target whenever a source or selected target is derived. An original pathname alone cannot authorize a returned composite. Original-only workflows retain their existing contracts.

The frozen scalar parameter snapshot remains authoritative if the source photograph changes or is removed after review. The result still reports source-changed/source-missing honestly; this does not permit substituting a newer source recipe. Target identity, source/provenance and expected document revision remain strict. Unsupported/conflicting targets are reported under the existing recheck versus skip-and-report policy.

`batch_sync` and `batch_group_history` preserve target-owned unrelated state, verify candidate changes are limited to selected parameters, and retain proofs in the existing ledger. Proof-less legacy records cannot awaken on a derived current state or a dormant derived before/after frame. Active derived replay is strict. All targets are rechecked after expensive active replay, inside rollback boundaries and before parked writes. Source/analysis buffers are not embedded in these receipts.

`preset_controller` validates actual saved modules and `local_grade_preset_review` validates actual frozen modules before claiming a token. Derived reviews bind canonical source, original provenance, stable row/load identity, version and path. Missing or changed proof rejects without consuming the review. Completed receipts replay before fresh admission. Actual derived preset application requires strict replay so a suspended existing effect cannot be quietly omitted.

Actual current/dormant derived assets are admitted only through the existing opaque-SDR portrait boundary. No alpha flattening, signed/HDR clipping or claimed high-bit source compatibility is introduced. A frozen source's metadata does not require reopening that source merely to apply previously reviewed scalar parameters.

## Explicit cross-owner face review

`people_transfer_inventory` provides a read-only, bounded inventory through the existing native batch mailbox's `people_targets` action. It never detects faces, classifies a new graph owner, changes selection, changes associations or commits history. It reads retained faces and displays actual effective-source pixels: the canonical creative base for returned images, and the existing decoder for originals. Derived alpha/HDR sources reject before display matting can disguise unsupported input. Faces remain source-coordinate boxes, not landmarks copied from another photograph.

Inventory limits are explicit: 1–16 unique target documents, at most 128 retained faces per item, a 320-pixel-edge display-only PNG with bounded encoded bytes, and a 7 MiB total result under the existing native receipt cap. There is no silent truncation. Unopened/unanalysed or unavailable targets report why they cannot supply a valid choice. Inventory is not a model run or a full-quality preview.

Each endpoint proof contains its exact document ID/workspace/revision, graph owner scope, state and association revisions, graph content digest, effective-source identity/extent and original-file provenance. The explicit request names the source FaceRef and independently chosen target FaceRefs. Every requested document must have an exact map; faces are never chosen by list position, appearance, matching digest or a coincidentally inherited person ID.

`people_transfer_adapter`/`people_batch_transfer` freeze that map and only the selected scalar parameter leaves into the existing plan. Preflight and commit verify each endpoint's own proof and exact enabled/verified FaceRefs, then prepare the target using its own retained landmarks, masks, support banks and full effective-source exporter. The current source need not share the target's graph revision or content digest. Byte-identical virtual copies remain valid explicit targets because logical ownership is separately proven.

The older `confirmed_person_only` selector is now restricted to the same established graph owner. Equal person IDs across independent owners are not user authorization. Its established shared-graph behavior remains; explicit map review is the separate route for independent/derived owners. No persistent identity link is created or copied by either transfer operation.

`ConfirmedPeopleTransfer`, the inventory workflow, face preview components and transfer proof validators expose the choice. The user must select each face on its actual source view. Source and target previews with selected boxes are retained for the final frozen `BatchReview` confirmation. The interface labels this as a correspondence for this transfer only. Pending inventory can be queried using the same request ID, cancelled locally, and invalidated on source/context changes; it never automatically retries a mutation.

The existing native `batch_api`/`batch_host`, dispatch and engine routes accept only the exact read-only inventory envelope before capture invalidation. Server dispatch similarly returns before edit fences/history, and recovery tracking does not turn inventory into a mutation or taint event. No new native command registration, parallel transaction queue or undo owner was introduced.

## Publication, history and remaining boundaries

Portrait transfer still publishes through `people_batch_ledger.commit_scoped`: independent graph owners are staged and validated separately, then committed under the existing all-owner rollback and protected group history. Target actual source proofs are rechecked after active rendering before success. New reviewed face evidence is retained with ledger targets so later reanalysis cannot silently reuse the old correspondence during undo/redo. Existing document source-switch history continues to preserve both dormant source slices; it may refuse a stale undo rather than overwrite newer work.

`people_candidate_render` now calls the source-aware local-mask snapshot verifier for derived objects-grade targets rather than comparing their masks with the physical original. It still refuses incomplete target preparation or skipped existing edits. The target does not borrow the source's analysis or support assets.

Remaining work is explicit:

- Persistent cross-owner person associations, automatic similarity candidates and cross-owner person/group inheritance are not implemented by this one-transfer map.
- Shared legacy person/group edits from an original active photograph into a parked derived owner remain refused. The new reviewed-face ledger evidence is not synthesized for that unadapted route. Existing derived local face/all-people edits retain their separate document publication path.
- General support-bearing scope transfer and semantic/reference/optics planners remain guarded until each target has its own real analysis and review. General crop transfer needs genuine target visual review.
- Dedicated ID recovery, spill removal and original-shadow extraction remain outside this slice, as documented in `DERIVED-ID-BACKGROUND.md`.
- Transparent/signed/HDR returned portrait sources remain refused; no implicit conversion is used to claim support.
- Runtime/native GUI, model/device behavior, visual pairing usability, full-source export correctness, memory/cancellation behavior, project/package reload and local quality acceptance remain unverified.

Required local acceptance includes original→derived, derived→original and derived→derived targets; byte-identical independent copies; different canvas dimensions; independent graph revisions; missing/disabled/unverified faces; changed graph, source, original provenance, source/target removal, reanalysis and stale receipts; no mask/landmark/link copying; source changes after general scalar review versus stricter face review; parked writes and rollback races; protected undo/redo including dormant history; inventory cancellation/context switching; malformed native envelopes; and target full export versus 100% inspection. Fixture authorship/static parsing is not evidence these scenarios passed.

The new UI fixtures are not registered in `package.json`; local acceptance must select the repository's TypeScript/React-aware fixture setup explicitly. No automatic test discovery or successful compilation is claimed.
