# Measured reference-choice native transport

Status: **AUTHORED / UNRUN**, 2026-10-25. Native source was authored and inspected
only. No product import, test collection/execution, compiler/build, typecheck,
model inference, install, download, Git operation, hardware probe or photograph
acceptance was performed by this slice. The fixtures are executable source for a
later authorized run, not evidence that this implementation passes.

## Same owner, no application authority

`ui/src-tauri/src/skin_reference_choice_people.rs` adds the single people action
`skin_reference_choice`, advertised by `skin_reference_choice_protocol: 1`.
There is no top-level command, new receipt store, graph mutation, renderer,
numerical solver, source-image generator, review token or portable effect.
All existing face/body preview, image, confirm and clear rules remain unchanged.

The request has the same eight captured fields as existing reviewed people
commands: `action`, `payload`, `document_id`, `document_epoch`,
`document_revision`, `state_revision`, `association_revision`, `target`.
The target is exactly the current `all_people` source SHA-256 with null
`face_ref`. The payload contains exactly `family: face|body`,
`source_review_sha256`, and optionally `manual_reference` as a same-source exact
FaceRef or null. Omitting that field is not rewritten as explicit null in either
echo. The usual request ID, optional transport command and engine epoch are
validated but are not added to the eight-field marker.

The result's outer `skin_reference_choice_request` is the exact eight-field
request. The host report's identically named inner field is the exact original
payload. `ReceiptHost` compares the outer marker with its immutable captured
request on success and failure. Neither action labels nor claimed source hashes
alone grant authority.

## Source-catalog binding in the existing receipt ledger

Before dispatch, `ReceiptHost` requires a retained successful catalog receipt
from the requested face/body family. The original receipt must already pass its
family's full validator, including exact PNG framing/hash, and match all six
context fields plus the requested source-review hash. Released catalogs, stale
document/graph/association generations and the other family cannot be borrowed.

The pending receipt retains only source/proof/image-hash/family/catalog-hash
metadata and the complete bounded face-ref/enabled list. It does not duplicate
PNG bytes or add another owner. These bytes count toward the existing ledger's
budget. Identical repeat catalogs are harmless; conflicting matches refuse.
Ordinary catalog eviction after dispatch cannot substitute a different source
for an outstanding suggestion.

A successful suggestion must contain exactly this retained face census, without
omission, duplication, substituted analysis revisions or changed enabled state.
Every disabled retained face is disclosed. Native transport does not assert
that the retained census contains every person in the photograph. The complete
document/repair snapshot and complete analysis bank remain authenticated by the
Python host's live before/after fences; native transport preserves their named
SHA-256 fields rather than pretending it can inspect those in-process objects.

## Bounded metadata validation

Requests are capped at 256 KiB and choice results at 1 MiB. Candidate count is at
most 64, never truncated. Object fields are exact and all scalar values are
bounded. Unknown/pending candidate statuses, unexpected consent, effect, token,
frame, document-state or additional numerical fields fail closed.

The outer report is selected-family bound. The nested proposal always names the
face measurement operation, even for a body-family destination. It requires the
immutable original-before-repair source stage, exact working-sRGB encoding,
original 8/16-bit or canonical creative 32-bit identity, original dimensions
within the existing 32 MP/65,536-dimension ceiling, and all declared review and
reference-exclusion flags. Body-extension, retained-fit, portability, consent
and committed-render claims remain false.

Measured rows require verified same-source MediaPipe evidence, exact landmark
and semantic-observation hashes, source-grid ROI, independent support digest,
and protective veto counts. Diagnostics must meet the existing native result's
scalar reliability bounds: at least 64 robust samples/weight/effective samples,
bounded dispersion/retention, and a reliable luminance centre. Each self-fit ROI
counts twice against the native 32 MP limit. Native transport validates metadata
consistency, not landmark geometry, masks, original RGB or the numerical fit.
The Python host and actual original core own those independent checks.

The displayed order is independently reconstructed from robust natural-log
linear-sRGB luminance, descending, with face ID used only for deterministic
display of equal numbers. Counts, segmentation confidence, demographic labels
and array order cannot become brightness scores or tie-breakers. Reported
linear luminance must agree with the exponential of the log centre.

Automatic selection requires every enabled retained face to be measured, at
least two enabled retained faces, no detector-limit hit, and the existing
greater-than-ln(1.02) separation. The top gap, near-tie list, ranked refs,
automatic selection and ordered blocker list must all agree. Unknown whole-photo
`census_complete: false` is mandatory and does not invalidate a legitimate
bounded automatic suggestion. A detector-limit hit does block it.

An exact measured enabled manual reference may coexist with automatic blockers.
It is returned as `manual-override-proposal`; blockers and any automatic result
remain unchanged. Disabled, unavailable, foreign or stale manual choices refuse,
never silently substitute another face. Neither manual nor automatic suggestions
are accepted as target selection, ownership consent, preview approval or apply.

Both content hashes are preserved as host-provided identity metadata. This
native layer does not reproduce Python JSON floating-point serialization to
recompute them, and a syntactically valid digest is not an independent source
authentication claim. Host validation and immutable request/catalog correlation
are required as well.

Memory metadata contains exactly `resident_input_bytes`,
`verification_workspace_bytes`, `total_byte_budget`, `capture_byte_budget`,
`measurement_byte_budget`, and `estimated_peak_bytes`. All are positive bounded
integers. The declared verification reserve is charged alongside resident
inputs before the measured-admission bound; their combined peak cannot exceed
the total budget. Capture and measurement budgets remain the truthful allowances
at their invocation times, not rewritten estimates of final free memory. They
need not be ordered relative to each other or final remaining space when live
availability/resident inputs changed; actual admitted work and the final peak
still must fit. This checks accounting consistency, not actual allocator or
device-memory behavior. Source measurement uses
`encoded-working-srgb-d65-sdr`; the separate captured storage descriptor's
`encoded-srgb-f32-v1` label must not replace this numerical ABI encoding.

## Read-only failures and late results

Failures require the original captured request and a bounded nonempty error.
They cannot carry payloads, doc-state publication, frame-emitted claims, created
objects or batch IDs. Transport-generated unknown results retain exact identity.
Unknown readonly receipts are evictable under the existing limits, not immortal
write barriers.

Only an exact retained choice read can reconcile a late terminal after an
unknown response: same live engine epoch, request/action/document binding,
complete valid result and captured family-source proof. Known terminal results
stay immutable. No confirmation or clear action gains replay authority. Released
read tombstones have an exact envelope and no payload; they cannot supply a
selectable proposal or become a replacement catalog.

## Native integration authored in this slice

- `people_api.rs`: module/action registration, request and result validation,
  capability gate, guarded source-bound begin, and receive admission.
- `engine.rs` and `native_dispatch.rs`: existing owned readonly dispatch path;
  no edit queue/history/capture invalidation for the suggestion.
- `receipt_host.rs`: strict eight-field binding, compact original catalog proof,
  bounded byte accounting, read eviction, exact late readonly reconciliation.
- `project_recovery_fence.rs` and `preset_alias_recovery_fence.rs`: the same
  validated readonly predicate; no weakening of mutation fences or generic
  action-name bypass.

No shared face/body validator or numerical file was edited. Pure existing
helpers are used as-is. This slice does not alter a prior freeze manifest.

## Parent integration checklist

1. Register only `skin_reference_choice` in the canonical Python people owner;
   validate the exact all-people context and payload, and route to the isolated
   host using the existing serialized readonly route. Classify malformed choice
   reads before generic write/recovery handling, then reject them normally.
2. Advertise exactly `skin_reference_choice_protocol: 1` only when that route is
   present. Preserve existing face/body capabilities and source-catalog stores.
3. Echo the full original eight-field marker on every terminal, including safe
   failure. A successful payload is the host report unchanged; do not normalize
   omitted manual choice or replace its document/repair/analysis/source hashes.
   No document publication or frame event accompanies this read.
4. The UI must retain the matching family catalog and completed source-image
   load, compare the result with its pending request and live owner generation,
   disclose unavailable/capped/tied/unknown-census limitations, and require an
   explicit choose-suggestion or manual-candidate action. Do not auto-apply,
   auto-preview, grant consent or alter the current selected reference silently.
5. Continue the original face/body target, source ownership and complete
   before/after image review flow separately. A suggestion digest cannot stand
   in for any of those checks. Body manual support and ownership remain distinct.
6. Include these source changes in a separately named next-slice capture only
   after cross-layer review. Preserve prior body/face captures as historical
   source evidence. Do not call source/hash inspection runtime acceptance.

## Authored UNRUN fixture coverage

Inline Rust fixtures specify exact request/optional-null echo, current-source
family boundaries, automatic suggestion with unknown whole-photo census,
read-only/consent/source/repair/precision/evidence/numeric/schema refusals,
deterministic rank, explicit tie/unavailable/detector-cap blockers, exact manual
override, safe failure/tombstone shape, native PNG framing for an original
catalog, same-ledger catalog requirement, complete candidate census, enabled
state, stale generation, wrong family, stale epoch, strict late-read identity,
and immutable settled terminal results.

The synthetic PNG and scalar metadata are protocol fixtures only. They neither
prove source measurement correctness nor validate original-file decoding,
display image loading, latency, memory pressure, cancellation timing, UI behavior
or real multi-person photo quality. All native and cross-layer fixtures remain
UNRUN pending explicit authorization for product execution.
