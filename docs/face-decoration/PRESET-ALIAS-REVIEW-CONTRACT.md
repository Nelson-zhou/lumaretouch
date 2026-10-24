# Complete mixed decoration preset alias review

Status: authored source and fixtures only. Runtime, tests, native compilation, UI type checking, full rendering, photographic and numeric acceptance are UNRUN. Baseline: `279b7f28d2ba281e1f514dccba89ced06f59282a`.

## Ownership and planning

The existing mixed preset planner constructs the actual shared portrait candidate graph and the current document's complete selected recipe. An exact decoration alias planning mode selects the already explicit retained FaceRef among enabled faces without deleting or replacing any other face. Selected and every before/candidate active decoration face are included in visibility coverage. Graph patches remain selected-face scalar overrides only; observations, associations, local support, paint and source identity cannot change.

Private alias planning returns `PresetAliasReviewPlan`, a detached typed subtype. Generic `execute_plan`, `restore_plan`, single-photo replay and single-photo post-apply verification reject it. Only the distinct complete alias transaction, exact typed `PresetAliasAuthority`, immutable pages and all-member acknowledgement can publish. The private planning flag is not write authority.

All ordinary compatible mixed modules continue through the existing planner and source admission. Distinct specialized review-owner conflicts fail the whole request; no selected module is silently dropped or converted. Retained active decoration requires the same complete visual review even when the decoration operation was not selected.

## Versioned review

Single-photo review version 1 remains unchanged. Complete mixed alias review version 2 has exactly the version-1 fields plus:

- `members`: two through sixteen ordered `{path, role, visual}` members. The active member is first and has role `active`; all later members have role `sibling`.
- `before_bank_sha256`: canonical digest of the complete frozen immutable support bank.
- `review_sha256`: canonical digest of the complete version-2 wrapper before this field is added.

Each member owns its source proof, revision and full before/after image pair. Effective source identity, source dimensions, candidate graph and coverage are shared. Original provenance is deliberately not required to match: two documents may retain the same immutable composite while having different original sources. Each proof is independently validated and checked again against its own bytes/provenance.

The current member receives the exact planned full document state, including selected color, crop and other ordinary modules. Every sibling renders the same shared portrait candidate against its own complete unchanged recipe, repair and crop. Sibling before/candidate state digests and output sizes must match. No active member state is copied to a sibling.

The existing retained-history closure checks reject omitted, unavailable, pending, trashed or dormant source-switchable affected documents rather than silently skipping them. Complete snapshot keys, exact graph-owner fence, selected FaceRef, workspace, load identity, member revisions, source proofs, repair inputs, coverage and the immutable bank are frozen and rechecked at every image/read/publication gate.

## Images, acknowledgement and publication

Version-2 `face_decoration_visual` requests add the exact `member_document_id` and `member_revision`, while retaining the active loaded document identity and revision. Every member's before and after page must have been served. UI decoding is separately required before constructing the exact ACK:

`{review_sha256, preset_sha256, applies_sha256, members: [{document_id, revision, before_sha256, after_sha256, coverage_sha256}]}`

Membership and order must match the frozen wrapper. Scalar decoration aliases, support-paint aliases and old single-photo acknowledgements cannot authorize this request. The complete wrapper hash also binds the bank digest. Claimed immutable image bytes remain available solely for the final no-write verification, not another publication.

The publication callback validates the ACK, exact selected modules, every served image and retained immutable bytes immediately before the sole composite batch ledger transaction. A potentially started mutation consumes the review even if compensation restores old content. A successful no-op portrait graph still retains the complete alias closure when nonportrait current state changes.

## Authored verification

The new UNRUN fixture specifies version separation, exact bank and member fields, every image-side serving requirement, explicit selected-plus-all-active coverage, sibling-owned crop/repair, same derived asset with distinct originals, stale bank/source/state/coverage/membership/owner/workspace refusal, retained-active decoration without selecting its operation, graph-no-op closure and generic replay rejection. The prior v1 replay fixture explicitly isolates the single-photo route.

Only standard-library static AST parsing of the owned Python sources and fixtures was performed. No product import or execution, test collection, test run, build, native call, type checking, model inference, dependency download, local Git write or publication was performed by this work unit. Algorithm counts and numeric controls are unchanged.
