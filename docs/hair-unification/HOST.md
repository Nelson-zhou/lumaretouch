# Hair unification host integration

Status: AUTHORED / UNRUN. Static source inspection only. No imports, product
execution, tests, builds, typechecks, inference, installation or downloads were
performed. These hooks are not runtime acceptance or vendor parity evidence.

## Independent contract

- Requirement `LNX-REF-PC-32472-C-fb2fe59a22`, PC32472 control 13.
- Operation `lnx.hair_unification.v1`; stage/local-asset kind `hair_unification`.
- Exact recipe `{ "version": 1, "amount": -1..1 }`. Negative selects manually
  painted tips; positive selects manually painted roots. Zero is exact identity
  without loading native code, retrieving evidence or rasterizing samples.
- Existing `lnx.hair_colour.v1` recipe and all original operations remain distinct.
- Real six-class hair evidence plus separately reviewed per-person support are
  indispensable. A face box, face count, copied mask or imaginary analysis never
  proves hair ownership. Samples themselves belong only to this operation.

`hair_unification_assets` is an append-only content-addressed vector bank. Each
record pins exact source hash/dimensions, FaceRef including analysis revision,
actual semantic evidence/model, original reviewed support asset digest and its
support-only review key. Recovery/tint changes do not invalidate unchanged support;
changing support requires new sample review. Historical original support bytes
remain retained for undo. Root/tip masks accept only source-normalized manually
painted brush/radial add/subtract objects. No sample can be inherited across targets.

## Numerical extent and stage

`runtime.prepare_bank(state, asset_sha256, source, plan, *, evidence, assets,
hair_assets, byte_budget, source_path, force_prompted=False, cancelled=...)`
returns `(tuple[LocalEffect], per_face_facts)` on the complete immutable effective
source. `assets` is the new bank; `hair_assets` is the original reviewed hair bank.
Source RGB is float32 encoded working-sRGB, not the repaired/current render stage.
Each record has source-local `weights` target coverage and frozen `Parameters`
containing signed amount and immutable measured native reference. No old RGB delta
or synthetic HWC2 chroma field is stored.

Targets are all other explicitly reviewed own-person hair. The entire nonzero
selected sample footprint, INCLUDING feathered edges, is protected exactly.
Roots/tips are manually assigned sample roles, not automatic anatomical regions.
A hard footprint boundary can remain visible; seamless boundaries are not claimed.
Overlapping root/tip samples or overlapping separately claimed people refuse.

The sole Rust composer applies the reference to ACTUAL current pixels immediately
after existing hair colour and before the existing one geometry warp. It preserves
linear luminance and detail rather than equalizing brightness. Dark/highlight
reliability gates can leave pixels unchanged; missing/clipped detail is not rebuilt.
Existing tint/gloss can coexist, but exact original-reference RGB matching is not
claimed. Native measurement is once per full source, never once per export tile.

`composition.apply_records_np(current, records, recovery=None, *, source_shape,
origin=(y,x))` and `apply_records_t(...)` share the Rust tile composer. Tensor
preview copies current pixels to CPU and back; there is no parallel unverified
shader implementation. Composition carries source tile coordinates and caps native
private tiles at 262144 pixels. No extra warp or interpolated preview RGB enters
export. Performance and peak memory remain unmeasured.

Native file: `bin/liblrt_hair_unification.so`. `LNX_DISABLE_HAIR_UNIFICATION=1`
disables this module independently. Missing/incompatible native capability refuses
active previews/renders. Capability is symbol/ABI loading only, not image success.
See ABI.md and NUMERICS.md for source math and reference-quality limits.

## Controller and exact acknowledgement

`HairUnificationHostMixin` provides `cmd_hair_unification` and
`finish_hair_unification`. Shared dispatch must enter the dedicated serialized
branch BEFORE generic document-fencing/history wrappers. This controller records
one ordinary canonical history entry itself around graph+bank publication.

Every request is exactly:

```
{cmd:"hair_unification", protocol:1, operation_id:"lnx.hair_unification.v1",
 request_id, action, people_context, payload}
```

`people_context` is the existing exact document ID/epoch/revision, graph revision,
association revision and selected face target envelope.

- `context`, payload `{}`: actual unmodified source PNG, original source extent,
  display PNG extent, exact face/support/evidence, current recipe and sample vectors.
- `preview`, payload `{recipe,root_sample,tip_sample,ownership_confirmed:true}`:
  requires fresh source context. Builds a PRIVATE staged graph+bank and renders the
  complete existing recipe twice through `portrait_review_render`, not a mask-only
  stand-in or an edited proxy. Returns source support/sample overlay, full before
  and after display PNGs, their binary-PNG SHA256 values, exact dimensions,
  `sample_asset_sha256`, `preview_id`, and `review_token`/`preview_sha256`.
- `presented`, payload `{preview_id,review_token,before_sha256,after_sha256,
  support_sha256}`: client must actually load and SHA256-check all three PNGs and
  explicitly confirm ownership. Server accepts only this exact full review ACK.
- `commit`, payload `{preview_id,review_token,confirmed:true}`: requires the exact
  prior presented ACK under that immutable review identity. Server rechecks source,
  graph, document/analysis/recipe/bank fences. A one-way claimed review cannot be
  reused to create a second transaction. Result's `asset_sha256` must equal preview
  `sample_asset_sha256`, not the photograph hash.
- `clear`, payload `{}`: sets only this operation's amount to zero; retained vectors
  remain for undo. It does not require new unification sample measurement or its
  native core, but still requires exact current ownership, an editable context,
  and the original/derived source and analysis dependencies of the full renderer.
  Missing baseline analysis is refused, not manufactured for a neutral reset.
- `status`, payload `{original_request_id}`: original saved terminal only. Native
  app uses its retained request mailbox; no blind resubmission after uncertainty.

Terminal event `hair_unification_result` echoes protocol, operation_id, request_id,
action, document_id, exact people_context and exact raw `request_payload`. It has
boolean success/outcome_unknown, object payload on success and nonempty error on
failure. Receipt digests are internal only; cross-language correlation compares
parsed original payload values, never a guessed canonical JSON hash.

`read_only`, `guard_other`, `dispatch_rejected`, `capability`, and
`invalidate_after_reload` are explicit server hooks. `execute` never emits a terminal;
`finish` emits it once, replaying the stored original if queried/retried exactly.
Pre-entry rejection uses `dispatch_rejected` instead of also calling finish.
An unresolved mutation blocks other edits until the original result is established
or an authoritative project reload succeeds. Clearing cannot race an uncertain write.

## Canonical persistence, history and admission

The existing virtual-copy context adds only this bank, with empty default for old
contexts. Project graph shape, operation recipes, history owner and source graph
remain unchanged. `full_candidate_render` staging may append immutable entries to
this bank but must not change any unrelated context fields or existing bank bytes.

Project interfaces:

- `validate(project_or_context, allowed=True)` validates banks and graph/history
  pointers recursively without calling virtual-copy validation recursively.
- `validate_graph`, `validate_leaf`, `save`, `load`, `store`, `needed(state,asset)`.
- `preview_kwargs(engine,state)` returns ONLY `hair_unification_assets` and ensures
  real evidence has been captured when active. `shared_preview` returns canonical
  shared `hair_evidence` and `hair_source_path` only when this operation needs them.
- `capture(engine,snapshot,pc,binding,source_path=...)` freezes this bank and fills
  canonical shared hair evidence/source/stamp even when old hair tint/gloss is zero.
- `capture_derived(engine,state,snapshot,pc,source)` uses measured actual composite
  evidence and forbids original-file prompted acquisition. No synthetic analysis.
- `kwargs(snapshot)` returns ONLY `hair_unification_assets`; existing hair kwargs
  own shared `hair_evidence` and `hair_source_path`. No duplicate keyword overwrite.
- `validate_derived` authenticates source/evidence and manual retained support.
- `require_scope` rejects only this operation's changed cross-photo/alias/dormant
  shared-source mutations, not unrelated old operations.
- `require_transition` additionally rejects any newly active amount/sample/enable
  change without the exact ephemeral `reviewed_transition` admission used solely
  by the controller. Generic scalar patch/preset/cohort/batch cannot bypass review.
  Existing unchanged active effects remain usable during unrelated edits.

Publication privately validates/prepares the entire candidate before calling the
existing graph owner. Bank entries are append-only; graph pointers make them live.
On a known rollback old bank is restored. On uncertain commit/rollback new bytes
are retained so no live/history pointer is lost. Existing history capture/record is
called once (noncoalesced), even if a partial mutation needs recovery. Undo/redo
remain existing graph restore operations, not a parallel per-feature history.

First slice is current photo only, original or proven immutable derived source.
Alias/cohort/batch propagation is explicitly unsupported, never silently broadened
by transferring sample assets. All retained neutral assets still require project
integrity validation even though neutral rendering itself needs no native evidence.

## Authored acceptance checks, not executed

`engine/tests/test_hair_unification_contract_unrun.py` covers scalar schema/sign,
no-native neutral identity, no semantic/full sample shortcuts, entire soft-edge
sample-footprint protection, exact ACK envelope, source/face/support content
binding, bank hash integrity and recipe/sample separation. Additional full app
acceptance still needed: render/pipeline parity, original and derived reopen,
RGB8/16, mixed operations/current Y, exact preview ACK, stale source/global edit,
undo/redo/history failures, native ABI and packaging, ownership overlap, original
export tiled/untiled parity, missing-core clear, cancellation and resource peaks.

### Read-image receipt retention bound

Encoded image strings retained by context, preview and status receipts share a
32 MiB byte ceiling. Old read payloads become correlated no-write tombstones,
preserving the exact request digest, ID, context and raw payload. Reusing that ID
never recaptures or rerenders. Mutation and presented-ACK receipts are not modified.
Read receipts omit unrelated `doc_state` image copies; mutation receipts retain their
exact authoritative state. Status copies also count toward the image ceiling.
A separate 1024-request identity ceiling refuses new work before execution instead
of evicting old identities; existing exact receipts remain replayable. Saving and
reopening the authoritative project resets this session-scoped store. Budget and
no-rerender regressions are authored but UNRUN.
