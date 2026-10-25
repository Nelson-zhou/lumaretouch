# Catalog-bound measured reference-choice host

Status: **AUTHORED / UNRUN**, 2026-10-25. Isolated host slice only. This slice
does not edit native-bridge, people-dispatcher or UI wiring and does not change
the current body-integration freeze. Shared integration is separately owned;
its actual state must be reported independently. No product import, collection/test execution,
build, typecheck, inference, installation/download, hardware probe or Git write
was performed for this slice. Static reading is not runtime acceptance.

## Purpose and ports

`skin_reference_choice_host.py` connects the existing measured
`skin_reference_choice.propose` helper to an already established, exact
face-family or body-family source catalog. The helper measures actual immutable
full-source pixels through the original native self-fit, never segmentation
confidence, an 8-bit display proxy, edited pixels or a replacement solver.

The only proposed people action is `skin_reference_choice`. Both `ACTIONS` and
`READS` contain only that name. `read_only` identifies malformed requests too so
future routing cannot accidentally send this read through generic recovery
writes. Full existing people-envelope validation must still run before calling
this host. No top-level command, graph owner, persistent bank or ledger is added.

Public functions:

```python
check_action(action, payload, target)
read_only(message) -> bool
propose(engine, state, target, payload, *, byte_budget=None,
        cancelled=lambda: False) -> dict
```

The target has exactly these fields:

```json
{"scope":"all_people","target_id":"<actual asset SHA-256>","face_ref":null}
```

The payload has exactly `family` and `source_review_sha256`, with the one optional
field `manual_reference`:

```json
{"family":"face","source_review_sha256":"<exact family catalog digest>"}
```

`family` is `face` or `body`. An explicit manual reference is either null or the
exact current `{asset_sha256,face_instance_id,analysis_revision}`. No amount,
target subset, caller pixels, scores, source bindings, consent/ownership flags,
budget, token or model switch is accepted on the wire. The host-only byte budget
is an allocation limit, not user authority. Omitted manual choice and explicit
null have the same selection semantics but are not normalized in the response.

## Strict response contract

The returned report has exactly the fields in `REPORT_FIELDS`:

- `kind: "skin_reference_choice"`, `version: 1`, `family`, and `operation_id`
  belonging to the selected face/body review family.
- `target`, `document_id`, `revision` (the catalog's document revision string),
  `source`, and `source_proof` copied from the exact verified catalog.
- `source_review_sha256`, `source_image_sha256`, `source_pixels_sha256`,
  `graph_sha256`, `analysis_sha256`, `body_bank_sha256`, and
  `document_snapshot_sha256`.
- `skin_reference_choice_request`: a deep, exact echo of the original payload,
  preserving omitted versus explicitly null `manual_reference`.
- `proposal`: the **unchanged** existing measurement helper output. Its exact
  top-level keys are pinned by `PROPOSAL_FIELDS`; candidate/measurement keys,
  current source/face evidence and selection consistency are checked too.
- `memory`: exactly `resident_input_bytes`, `total_byte_budget`,
  `verification_workspace_bytes`, `capture_byte_budget`,
  `measurement_byte_budget`, `estimated_peak_bytes`.
- `read_only_proposal: true`, `source_image_load_required: true`,
  `review_required: true`, `grants_consent: false`, `render_committed: false`,
  `portable: false`.
- `report_sha256`: canonical sorted compact JSON SHA-256 over every other report
  field, with non-finite numbers forbidden. The nested `proposal_sha256` retains
  its existing independent canonical-content contract.

The nested proposal's operation remains `lnx.skin_reference_match.v1` even when
the report's outer family is body. It measures candidate **faces**, not target
body brightness or ownership. Its `body_extension_enabled` stays false. The
outer body-family identity binds the applicable catalog and review destination;
it does not reinterpret the measurement as body consent.

`analysis_sha256` fingerprints the entire actual current-source analysis bank,
including rows unavailable at catalog creation. It is intentionally not the
catalog's fingerprint of only available face/body rows. `graph_sha256` includes
current graph revisions. Nested `proposal.state_revision` and
`proposal.association_revision` must match the live pending request.
`document_snapshot_sha256` fingerprints the catalog's full `before_key` (render,
context and graph snapshot), not merely original bytes. A hash is identity,
never independent authority that the UI is current or that a human viewed it.

Existing catalog receipts do not carry a document epoch. The eventual canonical
people transport must retain its request ID, document epoch/revision, state and
association fencing. The UI must compare the result with that pending request
and its current owner generation before showing/using it. No isolated host hash
replaces this outer transport responsibility.

## Exact source authority and change fences

1. Read only the selected family's existing `_skin_reference_match_reviews` or
   `_skin_reference_body_reviews` source entry. Do not create a catalog, use the
   other family's receipt, call `_store` (which prunes pending consent), or
   replace/renew a source receipt. Verify finite unexpired TTL, its full digest
   and the family's operation identity.
2. Invoke that family's own `_verify_source` before capture, after capture and
   after measurement. Its existing checks cover active graph owner, owner fence,
   exact row/path/load identity, unchanged source proof, document version, full
   repair/render/context snapshot, and the catalog's available analysis. Body
   catalogs also verify their independently retained body-bank digest.
3. Additionally fingerprint every supplied current-source analysis, the complete
   current document capture, and a checked body bank for **both** families.
   Recheck these at both later boundaries. Missing/unavailable rows cannot be
   silently added or changed during measurement merely because they were absent
   from the catalog's available-only fingerprint.
4. Use only `portrait_fit_source.capture`, which authenticates actual original
   or canonical creative bytes, exact dimensions/orientation/native precision,
   original stamps and source identity before/after decode. Compare captured
   source dimensions, kind/precision and original-pixel digest with the exact
   catalog source. Never deserialize or caller-construct the production source.
5. Pass the complete actual same-source analysis bank and current graph to the
   existing helper. It derives the candidate census from the graph, not from a
   UI subset. Validate the exact returned protocol and manually requested face.
6. Rehash/validate immutable original pixels, then reverify family source proof,
   complete document, analysis and body state before returning JSON. A replaced
   store/entry or expired catalog also invalidates the result. Cancellation,
   native absence, resource refusal and authentication errors propagate without
   partial success or a fallback method.

The canonical caller must serialize this read with document mutation. Source,
graph, repairs, support, associations, body bank, people cursor/target and review
consent are not written. The existing request receipt is a transport duty for
the later dispatcher, not another approval mechanism owned here.

## Memory admission before source decode

Source audit found that the family verifier itself allocates full per-face
snapshots. Admission solely before source decode was insufficient: even a
one-byte budget could enter that verifier, and later verifications could copy
semantic planes while the captured source remained resident. This host now
admits the verifier **before its first call**, not merely before pixel capture.
This correction has authored regressions but remains unexecuted.

The host subtracts actual retained buffers before calling capture: current and
parked document states, the current CPU source RGB, canonical creative content,
precompute/semantic arrays, all retained analysis banks, support/landmark/hair
buffers, and preview pipeline source/repair/effect fields. Arrays charge their
full backing storage even for tiny views. Already loaded tensor storage is read
without imports, transfers or numerical work; all devices are conservatively
charged. Traversal has depth/node bounds and does not inspect arbitrary foreign
model/session objects. Their process memory is still covered by the independent
fail-closed available-memory check. There is a 64 MiB host bookkeeping reserve.

Before calling any document capture or family verifier, the host reads existing
live `DOC_FIELDS` directly from the engine dictionary, without creating an
export snapshot. The independent verifier workspace reserve includes:

- Eight largest actual producer semantic planes per retained same-source face:
  four rederived planes plus four separately frozen planes. Shared inputs do not
  deduplicate these planned output copies.
- Sixteen additional largest planes for the initial shared bind, maximum
  reductions/float conversions and validation scratch, plus two 478-point
  float32 landmark arrays per face.
- Eight conservative copies of active document/context buffer and container
  footprints, including graph/support/body/hair stores, and another 64 MiB for
  bounded verifier bookkeeping. Immutable bytes may be overcharged here.

All counting is storage/shape/container inspection, not allocation of copies,
model execution or a warm-up snapshot. One-byte or insufficient per-face-copy
budgets refuse before entering `_verify_source`. Maximum resident and workspace
charges remain reserved across the operation. Each post-capture `_guard`
re-admits them with `FullSource.owned_bytes` still held before invoking its family
verifier; lowering headroom cannot initiate an unadmitted guard snapshot.

Capture receives only the remaining decode budget; its existing original-file
compressed snapshots, full native-precision conversion/freeze and inspection
peak admission runs before decoding. Memory is re-admitted after capture. The
unchanged helper independently charges full source, all supplied analysis and
snapshots, projection/anatomical/native scratch, and the largest full-source
ROI; its budget excludes both retained inputs and the reserved verifier workspace.
The report's estimated peak includes all three. Capture and measurement budgets
are the actual historical allowances passed to those functions, never relabeled
after a later guard. They may differ if headroom changes. Final resident/workspace
growth is compared with the actual measured admission and capture peak; a final
total that no longer fits refuses publication. Shared retained
analysis is deliberately conservatively charged twice. No existing pixel,
candidate or resource cap is raised by this fix.
No resolution reduction, smaller hidden candidate list or substitute solver is
permitted. These estimates are not an OOM guarantee or performance result.

## UI and integration limits

The source catalog being present does **not** prove its source image was fully
loaded in the UI or human-viewed. The matching family overlay's exact image
load/digest and natural dimensions remain a mandatory UI gate. The host never
emits a "human viewed" claim or source-image ACK.

A successful automatic proposal is only the brightest measured enabled retained
face under the declared statistic. `census_complete: false` remains visible:
the photograph may contain undetected people. A complete retained candidate set
can supply a suggestion, but the UI must require an explicit "choose suggestion"
or manual candidate action. It must not silently preselect or acknowledge it.
Near ties, missing retained measurements and detector-limit blockers are shown;
an explicit current measured face may still be chosen while blockers remain.

Choosing a reference never starts a preview/confirm automatically. The user
still independently selects target face(s) or an explicitly reviewed body,
confirms source/ownership, loads the family's exact complete before/after pair,
and explicitly applies it. Reference-face exclusion and body ownership/support
rules remain unchanged. No proposal or digest becomes portable, a fit cache,
support relation, consent token or render commit.

Native action validation/dispatch, canonical people read classification,
request-correlated final schema, and UI mounting remain outside this isolated
slice's ownership. No existing family/shared file or body freeze manifest is
edited by this slice; integration work is not proof of runtime acceptance.

## Authored fixtures and outstanding acceptance

`test_skin_reference_choice_host_unrun.py` authors both-family exact-source
receipt routing, JSON/echo/purity, null/manual intent, foreign/stale/expired
receipts, before/after graph/document/source/repair/body/support/analysis races,
previously unavailable analysis changes, original-pixel mismatch, backing-view
memory admission, strict report drift, cancellation and native refusal cases.
Budget-order regressions forbid first verifier/document-capture calls under a
tiny budget, charge shared producer planes per face, and lower headroom after
capture/measurement to ensure both later guard snapshots are refused before
their allocating verifier is entered.
They reuse the existing synthetic body-review fixture and explicit fake capture
and measurement ports. Those doubles do not prove Rust numerics, genuine file
authentication, GPU/CPU admission, actual image load, human review or UI safety.

All fixtures remain **UNRUN**. Runtime tests, native/full-source photographs,
precision/ICC/RAW/creative cases, complete UI interactions, memory pressure,
cancellation timing and transport integration need separate authorized
execution. No claim of passing tests, native compatibility or release readiness
is made.
