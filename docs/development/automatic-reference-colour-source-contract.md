# Automatic reference colour: source contract

Status: **SOURCE AUTHORED / UNRUN**. No test, build, typecheck, inference, product
runtime, photographic-quality or durability acceptance is claimed. Local runtime
validation remains with Qoder. This is not arbitrary cross-scene style transfer.

## Exact admitted job

The existing finite directory scheduler captures one source-file list. Start must
explicitly disclose its scope, complete pinned preset, immutable stored reference
asset/render/source SHA-256 identities, managed-copy policy, output and stop/skip
policy. The separate intent declares `reference_scope:
stored_reference_per_target_fit` and `reference_source_policy: reject_same_source`.
This does not create or imply an image-view acknowledgment.

Only a nonzero, reference-colour-only preset is admitted. Reference + portrait,
reference + exposure/white-balance, and any other mixed-family preset are refused
as a whole; selected modules are not silently dropped. Existing unrelated target
edits remain target-owned and must pass the canonical full-render guards.

## Fit once, then verify only

`workflow_auto_reference.TargetReferencePlan` adapts the existing
`portrait_group_reference.inputs` and `reference_color_engine.prepare_target`
owners. Stored reference capture, original-scene support provenance, ORB/homography
correspondences and Rust channel-gain fitting remain their existing algorithms.
Each target has its own genuine first fit. The returned fit is frozen before
complete-candidate validation; later assessment/application reads pass that exact
frozen fit to the existing verifier and never fit again. A failed first fit cannot
be retried under the same assessment. No fitted source sliders, source masks or
person identity are copied between photographs.

This requires sufficient genuine scene-texture correspondence (typically related
views of the same scene), not semantic similarity or merely a similar histogram.
Insufficient correspondences, missing/corrupt reference resources, unsupported
source/render provenance, virtual/derived targets and resource-limit failures are
reported concretely; they do not fall back to a different algorithm or proxy.

## Reference aliases and failure outcomes

A target with the reference's source-byte hash is rejected before fitting. The
existing reference owner also rejects reference-document identity. Neither the
reference photograph nor a byte-identical imported alias is treated as a corrected
output or silently omitted as success.

With `stop`, a definite failure stops the job. With `skip`, an exact unchanged
recipe/history/people proof and successful prior-editor return are required before
the existing scheduler marks that file `Skipped`. That skipped file is **not
exported**. Label-filtered files are a separate, explicitly disclosed existing
policy: a nonmatching label bypasses preset application and may export unchanged.
Unknown load, application, history, save or return outcomes remain query-only and
are never automatically replayed or downgraded to safe skips.

## Existing ownership boundaries

The existing live batch owner re-verifies target/source/fit and performs strict
replay. Its normal live `_history_capture` / `_history_record` boundary is retained
with a non-coalescing finally record, including partial/lost outcomes; the loaded
row is checked before history writes. This is not a second history implementation.
Applied verification uses canonical document capture, not the ephemeral per-face
preset DTO, and checks full candidate/source/people/repair/export-snapshot identity.
The existing scoped project codec, durable CAS/save, verified editor return,
scheduler and export owners remain authoritative. No second queue is introduced.

## Authored acceptance fixtures — UNRUN

Engine fixtures cover exact intent, complete mixed-family refusal, one fit followed
by verify-only reuse, pre-fit source-alias rejection, correspondence failure without
refit, no-effect proofs, canonical history calls and unknown-outcome non-replay.
UI/core fixtures cover strict paired reference fields, metadata identity disclosure,
new Start consent after changes and missing/malformed reference metadata refusal.
These are authored contracts only, not evidence of execution or image quality.
