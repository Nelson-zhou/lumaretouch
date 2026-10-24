# Torso-length integration audit: AUTHORED / UNRUN

Baseline: `ad5fae4b5f67fd9ea0abb4690e7125b8b7558049`.
Requirement: `LNX-REF-PC-32473-C-f1662d2dec`.
Operation: `lnx.torso_length.v1`, version 1, signed scalar `amount` in the original local range `[-1, 1]`.
Audit date: 2026-10-24 UTC.

This is a source-only integration audit, not acceptance. The fixture file was parsed with Python's standard-library AST parser, without importing or collecting it. No product imports, tests, builds, compiler/typecheck, native process, model inference, downloads, package execution or Git writes were performed. Synthetic body/face evidence and model-identity strings are contract inputs only. They do not establish real detector output, image quality, learned-AI equivalence, performance or runtime availability.

## Actual ownership and render route

- `body_pose_operations.policies` registers the torso policy in the existing body bank. There is no second torso document, body identity, undo stack or pixel owner.
- `body_pose_geometry.TORSO_LENGTH_BODY_ORDER` extends the existing v6 prefix with torso at v7. `effective_order` chooses it only for active torso intent. Neutral and disabled torso preserve the former v1–v6 ordering.
- `body_pose_commands`, `body_pose_families`, `body_pose_host`, `torso_length_host` and the registered server command route to the canonical document binding, body graph, people graph, existing publication and history owners.
- `torso_length_runtime.bind_support_review` binds factual face identity to user-reviewed geometry. Preparation does not rebind or invent support. The support retains exact source, BodyRef, all-point digest, operation, FaceRef, associated face box and evidence digest. A FaceRef cannot substitute for a BodyRef.
- `torso_length_field.TorsoLengthField` prepares the native map at original source dimensions, then conjugates source/decoder scaling for preview evaluation. Head/face plateau, native displacement bound and actual off-grid inverse remain field-owned. Native failure has no alternative algorithm fallback.
- `body_pose_render.prepare` collects the torso field alongside all older body families and passes it through the existing arm/common adapter. `require_prepared` requires exact coverage of active, current operation inputs. `shoulder_shape_runtime.compose` applies body inverses, then face inverses at displaced coordinates, and admits the final composed Jacobian before the existing single source sampler.
- `people_engine_runtime.prepare_preview` consumes the actual immutable preview source. `prepare_export` consumes original RGB8/RGB16, or the independently admitted creative float32 SDR source, at original dimensions. A proxy-sized export, wrong source, wrong document owner, malformed snapshot order or insufficient memory refuses instead of silently enlarging a proxy correction.
- Derived preview uses the existing immutable-source and repair-evidence checks. The positive derived fixture uses a real `people_cross_owner` capsule because the existing derived gate rejects ordinary shared-person links. No graph, source-proof or repair gate is mocked.
- Export-buffer facts report the actual prepared geometry and output-byte hash, original geometry dimensions and one common portrait sample stage. They explicitly do not prove encoded-file/container publication or quality acceptance.

## Authored integration coverage

`engine/tests/test_torso_length_integration_unrun.py` keeps the real state, support, history, snapshot, render and sampler implementations. The only positive-test doubles are the actual `torso_length_native.prepare`, `.facts` and `.evaluate` seams. The compact smooth routing double is not a second product fallback and is not numerical evidence about the Rust kernel.

The authored fixtures cover:

1. Exact requirement/operation, signed scalar bounds, rejection of support/identity/adjacent waist-length values in portable intent.
2. Both amount signs through original RGB16 and derived float32 full-resolution preparation, actual common-map sampling, fixed source edges and truthful render-buffer outcomes.
3. Proxy preview and full-resolution export independently preparing original-coordinate native state, decoder-scale conjugation, actual tensor sampler and unchanged immutable input pixels.
4. Exact neutral with or without dormant support, missing native rejection for active intent, and zero/disable recovery without native loading or loss of stored support/intent.
5. Previous v1–v6 order identities, v7 only when active, immutable old operation prefix and no implicit duplicate body operation.
6. Missing support/review, changed pose digest, source extent, association revision, FaceRef revision, face box/evidence, manual face, foreign FaceRef-as-BodyRef, and copied foreign-body support rejection.
7. Disabled foreign faces, observed foreign bodies and unresolved foreign bodies continuing to protect their pixels. Boundary/ownership ambiguity is not silently assigned to the selected person.
8. Required review confirmations, source-edge clearance, memory admission, export precision/channel count, full-resolution dimensions, document/source ownership and frozen order fences.
9. Family reset, source-bound immutable supports, protected operation history, existing document-history decoration/restore, persisted body-bank round trip, stale people-graph replay rejection and re-preparation after undo.
10. Private parameter-transfer helper preserving the target's own support, pose and BodyRef, followed by actual target preparation. This is deliberately not claimed as a user-facing preset/batch flow.
11. Source-level server transport/readiness separation and Rust bridge support-schema, identity, epoch, replay-budget and correlated status-fence wiring. Rust's authored tests remain UNRUN.
12. A separate actual-native endpoint contract with no routing double: positive length moves shoulders/head upward, negative length downward, hips stay fixed, and actual shoulder-to-hip distance changes. Missing installed native code skips that acceptance test with an explicit UNRUN reason; a skip is not a pass. The core's own Rust numerical fixtures are separately authored and UNRUN.

These tests have not been collected or run. Assertions authored against source can still require correction after authorized execution. Real active face deformation combined with torso, other simultaneously active body families, complete server/Tauri publication/history transactions, desktop interactions, source-file decode proofs, final image containers, packaging, sustained memory peaks and photographic acceptance still require end-to-end execution. The positive integration fixtures intentionally do not fabricate a host publication receipt or replace an actual `PreparedPeople` object.

## Native transport and unavailable-core behavior

The registered transport remains protocol 1 even when the optional native torso library is missing. `server.py` separately advertises `torso_length_available` from the actual ABI/symbol availability check and an unavailable reason. Read-only view/status and zero/disable recovery must remain reachable; nonzero adjustments require the core. File presence alone is not numerical readiness.

The host's exact-zero recipe recovery may retain the reset with an explicitly original/unapplied publication when another active family still refuses. It does not clear that other family's intent, claim the stale edited frame was rendered, or relax refusal for a requested nonzero torso amount. The integration file includes the real neutral/disable preparation path and a source guard for this distinction; the separately owned support/host fixtures exercise the host transaction contract, also UNRUN.

`ui/src-tauri/src/torso_length_api.rs` validates exact signed recipes, the draft/manual support schema versus fully bound persisted support, all 25 upper-body anchors, source correspondence, separate inner/outer request IDs, native/document epochs and bounded replay tombstones. Read-only authoritative status can settle only its matching original recovery fence; it never dispatches the edit again. `engine.rs` avoids generic acknowledgement of an unvalidated torso result. Source presence and Rust fixtures are not proof of compiler or runtime correctness.

## Preset and batch continuation

The initial foundation intentionally left torso absent from `scope.MODULES`. The later continuation registers only a torso-exclusive scalar route with exact target-owned full before/after review. The private `torso_length_project.transfer_recipe` remains uncalled by that product route; it cannot represent different document-private people owners. The updated guard fixture checks explicit registration, torso-only scope and rejection of nonportable body identities instead of preserving the obsolete unknown-operation assertion.

See `TRANSFER-CONTRACT.md` and the new transfer fixtures for the bounded unique-enabled-body policy, mandatory per-target ownership/visual acknowledgment and existing ledger/history integration. No source bank, analysis or support is serialized as portable preset data. Every fixture remains UNRUN.

## Baseline non-regression inspection

Read-only byte comparisons against `ad5fae4b` confirmed these pre-existing numeric/sampling files unchanged during this audit:

- `engine/src/lumaretouch_engine/ops/deform.py`: SHA-256 `5e0800bffa8f87f9f8e4f6cf8caa1ea782bee20d099a2232c869e0e9d53247fd`.
- `engine/src/lumaretouch_engine/people_geometry.py`: SHA-256 `554e4ea056f8c675be3b1fb859a2ca3101ca437dc1db52967e4151524955580b`.
- `engine/src/lumaretouch_engine/shoulder_shape_runtime.py`: SHA-256 `96b29f51f764acfa84683545596706325a5eb5d57a56a8bd1a3e6ff19a0738c7`.
- `engine/src/lumaretouch_engine/people_pipeline.py`: SHA-256 `c2b13105062af9eaca632acc4f6dd5cc14dd959c3c57429e00a768a9a62d815d`.

For `body_pose_geometry.py`, the inspected diff adds only the v7 constant and the active torso branch in `effective_order`; old numeric composition/evaluation is unchanged. No existing test required a new-seven-family assertion adjustment, and no existing tests were modified by this integration task. Byte/source comparisons are not regression-test results.

## Remaining acceptance blockers

All runtime stages are UNRUN under the explicit source-only constraint. The actual native ABI, compiler support, inverse endpoint contract, final composition, original/derived preview/export parity, UI lifetime and cancellation, publication/undo/redo/receipt behavior, source-file proof, presets/batch, package install, image quality and memory/performance cannot be called passed or production-ready. The requirement remains partial; the distinct adjacent waist-length requirement is not implemented by this operation.
