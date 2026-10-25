# Neck fine-wrinkle current-photo review host

Status: **AUTHORED / UNRUN**. This slice implements source text and synthetic
fixtures, not runtime, numerical, device, image-quality or PixCake-parity
acceptance. The handbook leaf remains pending independent verification.
No product imports, tests, builds, type checks, inference, installations,
downloads, hardware probes, Git commands or GitHub writes were run for this
host slice. Verification was limited to source reading, Python AST parsing and
SHA-256 of authored files.

## Owned files and boundaries

- `neck_wrinkle_actions.py`: strict exact envelopes for this family only.
- `neck_wrinkle_review.py`: bounded PNG transport, genuine integer-pixel crops,
  full-raster identity and source-space native-admission diagnostics.
- `neck_wrinkle_host.py`: private source/reference/candidate fences; stages
  canonical support and passes a candidate to the existing people owner.
- `engine/tests/test_neck_wrinkle_host_unrun.py`: synthetic authored fixtures.
- This document.

This adapter owns no independent person/project/receipt/history bank, no source
loader or repair replayer, no model/neck/jewelry segmentation, no geometry
sampler and no numerical fallback. Other modules own numerical preparation,
source authentication, body/person support, render composition, and UI.

The operation is `lnx.neck_wrinkle.v1`; support kind is
`neck_wrinkle_visibility`; family is `neck_wrinkle`. No collarbone demographic
rule, facial-wrinkle review, body-colour review or neck-shape review authorizes
it. Current original or opaque SDR returned-source review only. Live and dormant
same-source project aliases refuse rather than silently spreading one image's
review. Private document ownership retains the existing virtual-copy rules.
No alias, preset, cohort, batch or cross-photo workflow is added.

## Integration ports

All actions live inside the existing document/revision/association-fenced people
envelope and existing request/receipt owner. `neck_wrinkle_actions` exports
`ACTIONS`, `READS`, `WRITES`, `check_action(action, payload, target)` and
`read_only(raw)`, `neutral_patch(raw)` and `is_neck_command(raw)`. The selected target must be exactly
`{scope: 'face', target_id, face_ref}`, with matching cursor and source.

`neck_wrinkle_host` exports:

- `reference(engine, state, target, payload, *, cancelled=None)`.
- `preview(engine, state, target, payload, *, cancelled=None)`.
- `crop(engine, state, target, payload, *, cancelled=None)`.
- `confirm(engine, state, target, payload, *, mark_started, cancelled=None)`.
- `detach(engine, state, target, payload)`.
- `report(engine, state, source, selected_id)`.
- `bound_receipt_payloads(existing_receipts)`.
- `require_transition(engine, before, candidate)`.
- `reviewed_transition(engine, before, candidate)` context manager.
- `verify_before_publish(engine, before, candidate)` and
  `discard_publication(engine)` for existing transaction/reset cleanup.

Read handlers return payloads only. Confirm/detach return `(candidate_graph,
result_payload)`; the caller must prepare and publish that graph through the
existing people owner and history transaction. Confirm's `mark_started` must
mark the existing request's mutation boundary. Append-only support is retained
before graph preparation in the existing body-review pattern. If graph
preparation refuses with an unchanged owner fence, unused immutable bytes can
remain but no graph or pixels were published. The existing outcome/uncertainty
logic, not this adapter, decides the receipt's terminal state.

`confirm` creates a private typed publication permit bound to the exact canonical
owner identity/fence, before/candidate graph hashes, support-bank hash, selected
FaceRef, source binding, numerical measurement key, document/snapshot, body-bank
and selected-analysis hashes. The parent wraps only its existing neck-confirm
publish call with `reviewed_transition(engine, before, candidate)`, calls
`require_transition` at `_people_prepare_graph`, and supplies
`verify_before_publish` as the existing transaction's final callback after
preparation and before commit. The context manager clears the permit/admission
in `finally`; resets or failed-request cleanup can call `discard_publication`.
This is a one-candidate transient authority, not a new ledger or loose boolean.

Unchanged neck intent, support and active ownership permit unrelated edits.
Outside exact reviewed confirmation, the transition guard allows only explicit
selected-current-face zero, optionally removing its own support pointer.
Changes to active FaceRef/evidence, confirmed links/person/cross-owner record,
association revision, support, or positive amount refuse. Existing history
restoration must retain its separate canonical restore owner, not manufacture
an unreviewed generic active patch. Protocol admission must additionally reject
any ordinary patch containing this operation unless `neutral_patch` matches the
exact one-leaf zero request, including same-value active and mixed patches.

The engine's `_neck_wrinkle_reference` and `_neck_wrinkle_preview` fields are
transient JSON-only review records. The separate publication permit contains only
metadata and the existing owner identity and lives only through publication. Reset/switch/rollback integration must
invalidate these alongside other per-document reviews. Existing receipt cleanup
must call `bound_receipt_payloads` for reference, preview **and crop** payloads.
At most two image-bearing outcomes are retained; released receipts retain their
original request/outcome identity with `payload_released`, not guessed success.
The UI must use the existing people request/receipt reconciliation, not issue an
independent replay ledger or retry an uncertain write.

## Frozen action contract

- `neck_wrinkle_reference`: `{}`.
- `neck_wrinkle_preview`: `{review, amount}`; amount is finite and positive up
  to 1, and `review` is the independent neck support schema. A genuine source
  crop under the current reference must have been issued first.
- `neck_wrinkle_crop`: `{reference_id, plane: 'source', rect}` or
  `{preview_id, plane: 'before' | 'after', rect}`. Never both IDs.
- `neck_wrinkle_confirm`: `{preview_id, reviewed: true, before_sha256,
  after_sha256, support_sha256, inspection: {rect, before_sha256,
  after_sha256}}`.
- `neck_wrinkle_detach`: `{}`.

`rect` is `[x, y, width, height]` in exact integer pixel edges, with positive
width/height at most 1024. Booleans, fractional or normalized coordinates,
out-of-domain rectangles, source/output-ID confusion, unknown fields, arbitrary
arrays, paths and caller-supplied source proofs refuse. Review JSON is limited
to 192 KiB; no silent vector simplification occurs.

## Source and rendering evidence

The source port is the parent-owned trusted adapter:

- `from_engine(engine, *, state=<base live PEOPLE GRAPH>, source)` creates an
  internal resolver, without live source/graph swapping.
- `resolve(resolver, *, face_ref, source, analysis, byte_budget,
  cancelled=None)` returns immutable `packet.rgb`, canonical `packet.analysis`,
  `packet.proof`, and aggregate `packet.resident_bytes`.
- `packet.proof` contains version 1, exact `source`, existing effective
  `source_proof`, host-owned actual repaired-pixel `input_sha256`, ordered repair
  stack `repair_sha256`, encoded-sRGB float32 encoding, source bit depth,
  EXIF-normalized orientation and immutable-source/verified-repair-base stage.

The host does not accept an arbitrary array plus hash or a UI assertion that a
thumbnail is full-resolution. Source pixels must have the canonical source
shape and be readonly float32 SDR RGB. Effective source and physical-original
provenance are distinct. Changes to either proof, source pixels, repair history,
selected face, graph, scalar edits, model observations, body association or
document identity invalidate the review.

`neck_wrinkle_layer.prepare_review` supplies the same actual native solve as
render preparation and returns `(effects, evidence)`. Evidence exposes full-grid
admitted weight and hard veto, the native ROI eligibility mask and source
window, measurement key and source proof. The host displays:

- Cyan: actual complete-context numerical eligibility, not merely paint or
  detected/changed lines.
- Magenta: actual hard sampling protections/exclusions.
- Orange: positive admitted input support rejected by complete-context rules.

A successful zero-line solve is not proof of visible correction. The transport
always reports `runtime_quality_accepted: false`.

Diagnostic fields and source packets are released before real mixed rendering.
The before/after images come from `full_candidate_render.render` at complete
output resolution, with staged canonical people graph/support context for the
after result. There is no live mutation, injected precomputed effect, local
patch-only preview, proxy-render overlay or enlarged proxy crop. Render proof
must contain `neck_wrinkle_measurements`, a bounded list of actual prepared
`{face_ref, measurement_key}` values derived by the canonical renderer. The
selected active after result must match the diagnostic's key. Empty measurements
are valid for a neutral before image.

The host records private complete float-raster hashes plus full-render proofs.
Every requested before/after crop rerenders the frozen complete candidate,
compares its full raster/proof, and only then slices the actual output pixels.
A float change hidden by RGB8 quantization still refuses. Output crops therefore
include all existing colour, geometry and retouch operations, rather than
pretending a source-space crop equals a crop of the result.

## Display and consent semantics

Every image is exactly `{mime: 'image/png', base64, width, height, sha256}`.
`sha256` hashes the PNG bytes, not its base64 string or the full float raster.
Whole-frame displays are at most 1152 per edge and 4 MiB per PNG; they fit the
UI's 1280-edge limit. Display-only BOX reduction partitions all source rows into
bounded stripes. It never supplies measurement, export or 1:1 crop pixels.
Unbounded complete float images are not cached per receipt.

Before/after result sizes are separately reported as `before_output_size` and
`after_output_size` and must agree. The support image covers the canonical
source domain; it is not an output-geometry overlay. Source proof and input /
repair hashes accompany all reference, preview and crop results. Reference
body choices are exact `{body_ref, points_sha256}` pairs, at most 64, with an
explicit refusal on overflow rather than silent truncation.

The three confirmation hashes must match the exact bounded whole-image PNGs.
The inspection acknowledgement must match both issued 1:1 output crop hashes
at the same rectangle. Requesting another rectangle replaces the private pair.
Only one rectangle and its two hashes are retained. One inspected rectangle is
**not whole-photo 100% coverage**, a claim of actual user attention, or image
quality acceptance; the UI must separately wait for decode/display and explicit
human review. Before publication the host rechecks canonical source, candidate,
actual numerical measurement key and support PNG.

Confirm result is `{kind: 'confirmed', family, operation_id, attached: true,
amount}`. Detach result is `{kind: 'detached', family, operation_id,
attached: false, amount: 0}`. Detach makes one candidate containing a local zero
amount plus removal of only this family's pointer. It never needs fresh
analysis, source-image decode, body resolution or native measurement. Immutable
support bytes and historical recipes remain available to the existing history
owner, and other families are untouched.

## Authored coverage and remaining acceptance

Fixtures cover strict envelopes and domains; source-crop gating; private staging;
all three PNG acknowledgements; matching output crop pairs; source/repair/model
and graph staleness; private-candidate tampering; actual-render measurement-key
mismatch; sub-PNG float changes; actual pixel crops; memory-free private records;
neutral detach without numerical dependencies; exact transient publication authority,
finally cleanup, direct activation/ownership refusal and harmless-edit preservation;
live-alias refusal; image-receipt
bounds; and cyan/magenta/orange diagnostic semantics. All are **UNRUN**.

Still required: actual full-source/repair integration, native/backend build,
source/project/history/undo/redo regression execution, UI decode/seen/receipt and
interruption checks, packaging/ABI checks, aggregate memory and cancellation
stress, and representative fine-line photographs with neck texture, jewelry,
clothing, hair, beard, tattoos, hands, multiple people, tendon/Adam's-apple edges,
broad folds and source/output geometry differences. No visual quality or
full-photo fine-texture preservation claim follows from source checks.
