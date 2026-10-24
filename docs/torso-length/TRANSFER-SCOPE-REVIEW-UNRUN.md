# Torso scalar scope and full-target review: source-only contract

Baseline supplied for this work: `cce54da2`. These additions continue the same partial requirement, `LNX-REF-PC-32473-C-f1662d2dec`; they do not create a new numerical method or increment handbook coverage. The existing original Rust torso solver, source-space observations, runtime association checks, common inverse map and one-sample renderer remain authoritative.

Status: **AUTHORED / UNRUN**. Only source reading, text editing, static Python AST parsing and file hashing were performed. No product module was imported, and no tests, build, typecheck, native execution, image inference, model download or photographic review ran. Authored tests are future regression contracts, not passes. The synthetic pose, face and pixel fixtures are not observations of real anatomy or evidence of output quality.

## Scalar ownership

`torso_length_scope.check_params` delegates to the existing `torso_length_state.portable` validator. Its entire payload is `{version: 1, amount: number in [-1, 1]}`. It rejects wrapper recipes, bool-as-number, nonfinite values and extra support, identity or enable fields.

`target` and `params_of` require exactly one enabled body in the document bank. They refuse multiple enabled bodies rather than select the first match. Every retained body record, support asset and analysis-run key must belong to the same source. Disabled same-source bodies stay retained, including their exclusion responsibility in the existing renderer. The selected body must already have an enabled torso operation, reviewed operation-specific support, and an explicit body/person association. A neutral scalar is not permission to create an operation, enable a disabled body, copy support or invent consent.

`install` changes only the selected torso recipe through `body_pose_state.set_recipe`. No-op values leave the exact packed state untouched. Original target admission checks actual file digest and full dimensions. Derived admission uses the actual immutable composite identity and extent, never physical-original coordinates under a derived label.

`restore` likewise uses `set_recipe`, preserving current unrelated body operations and all immutable support assets. It checks the exact same source observation, BodyRef, association, review and support before restoring the prior scalar. `undo_key` hashes every body-bank dependency except the monotonic overall mutation revision, plus the effective derived source when applicable. Later unrelated body edits therefore conflict instead of being overwritten. Unrelated non-body edits can survive scoped restoration. Exact bank hashes in visual proofs still include the full mutation revision. `bank_sha256` exposes this full digest to the ledger owner.

## Review proof and rendering

`torso_length_transfer_review.prepare` obtains before/candidate identities from `full_candidate_render.identity`, validates the actual associated face using `torso_length_runtime.validate_face_review` against that returned canonical people graph, and renders both states with `full_candidate_render.render`. It never swaps a live row, invokes a body edit command, rebinds support, infers a face, or simulates apply/undo to make previews.

The expected private body-bank copy must equal applying only the selected scalar to the before bank. A candidate cannot smuggle support replacement, new operations, another body's scalar, association changes or extra revision advances through this review. Full state and people-context fingerprints cover all other retained edits. The current bounded product transfer route may impose stricter module-combination limits independently.

The compact record contains the original-shadow common review fields and these target-specific fields:

- `body_ref`: exact target asset, stable body instance and analysis revision.
- `associated_face`: exact `associated_face_ref`, normalized `associated_face_box`, and `associated_face_evidence_sha256`.
- `body_support_sha256` and `body_review_sha256`: the target's own existing independent support and review.
- `before_bank_sha256` and `candidate_bank_sha256`: complete canonical checked banks, including revision and every dependency.

The shared fields bind document/revision, effective-source plus physical-original proof, before/candidate full-state identity, before/candidate complete people-context identity, full source/output dimensions, exact scalar parameters and both image hashes. Private records contain no PNG/base64 pixels or body support coordinates. The associated-face box is identity evidence, not portable preset geometry.

Both actual rendered arrays must be complete, finite floating RGB at their exact source-derived output dimensions. Only afterward are they reduced for display, with maximum 256-pixel edge, 150,000 PNG bytes and 200,000 base64 characters. Integer proxies, reduced source renders, missing identities, incomplete dimensions and memory/native failures refuse rather than become alternative evidence. The exporter retains all existing original/derived native ownership gates; no fallback solver or second sampling pass is added.

`verify` checks the complete frozen record without re-rendering or rebasing. `rollback_record` describes the previously frozen before state for failed-publication verification; it does not accept a newly observed people graph. `history_identity` returns the existing five-field full identity only after current target/source/support/associated-face consent is validated, so group undo/redo cannot bless a stale face binding merely by fingerprinting it.

Ordered acknowledgments match each document, revision and exact before/after PNG SHA-256. They are bounded to eight distinct target documents; omitted, duplicated, reordered or generic approve-all inputs refuse. The preset and batch owners, not this module, own frozen tokens, publication, uncertain-outcome receipts and history.

## Future acceptance still required

The two new `_unrun.py` files describe scalar-only retention; ambiguous and multi-source refusals; disabled/missing operation, review or association rejection; sibling-preserving restoration; revision-aware dependency fences; original and derived target ownership; real current-face consent; full-frame and PNG schema checks; no body-operation smuggling; ordered acknowledgments; rollback identity and mid-render drift. Their renderer/identity doubles test adapter boundaries only if later executed.

Actual original and derived exports, native numerical invariants, broad photographic quality, UI interaction, runtime memory/cancellation behavior, transaction recovery and broader multi-body selection remain unverified. No test pass or completed requirement is claimed here.
