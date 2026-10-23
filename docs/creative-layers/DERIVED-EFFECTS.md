# M14 derived effects and explicit fresh-current document

Continuation: `DERIVED-EYE-LIGHT.md` adds the exact reviewed eye-light consumer
and effective-source reference pixels. The eight-operation list below describes
this earlier frozen slice, not the later cumulative admission set.

Status: source-only continuation of local
`b5d288a9ec0d80810236621f5f573b96a4f4856e`; runtime acceptance UNRUN.
This continues `LNX-REF-WF-127932-a9c143a25d` return and
`LNX-REF-WF-127932-c7783ea5fb` unified history. It is not completion of M14,
M13 generation or the 32 AI functions.

## Explicit fresh-current layer document

The creative workspace now exposes an explicit new-document action. It captures
current photo edits at full source resolution via the existing export resolver,
including the verified derived source when present. It does not substitute the
preview, silently reopen an old layer stack, or overwrite the source image.

The prior layer stack and immutable assets remain in the same recoverable host
undo history. The replacement has a fresh document identity and ownership token;
its source photo retains its independent identity, edits and canonical base until
an explicit return operation. The operation validates source/revision/ownership,
refuses while a return is pending, rechecks after capture, and caches its receipt.
Failures before publication retain the existing stack; uncertain publication is
not automatically retried. Native transport treats this as a fenced mutation.

Photo effects mirrored from the portrait graph are isolated before neutral
capture detection and rendering. This avoids treating an already owned graph as
another set of global effects or applying those effects twice.

Ports: `creative_document_refresh.fresh_current`,
`CreativeHost.handle(fresh_current)`, `creative_layers_api.rs`,
`useCreativeWorkspace.freshCurrent`, and `CreativeWorkspace`.

## Acceptance boundary

No product imports, test runs, compiler/build/type checking, inference or visual
acceptance occurred. Python AST and source/hash checks do not establish runtime
correctness. Authored fixtures cover recoverable fresh creation, stale owners,
pending return, source capture failure and idempotent receipts. The native
fixture checks that fresh capture cannot use a read-only envelope.

Existing source-format and resource limitations remain: no transparent/HDR photo
return by flattening/clipping; no proxy fallback for full capture; no unconditional
large-image performance claim. Original encoded bytes and original-file provenance
remain separate from the canonical derived pixel identity.

## Audited local portrait subset

The derived-source adapter admits only bounded local face/all-people envelopes
and validated scalar recipes for these existing operation IDs:

- `lnx.deform.v1`, `lnx.enhance.v1`, `lnx.facial_wrinkles.v1`
- `lnx.brow_shape.v1`, `lnx.nose_shape.v1`, `lnx.eye_shape.v1`
- `lnx.mouth_shape.v1`, `lnx.lip_makeup.v1`

These consumers receive the composite's pixels, measured landmarks and semantic
masks through the existing people pipeline. Live edits require exact captured
source/document/graph/target fences and real composite-bound MediaPipe analysis.
A command-name exemption alone is insufficient. Unsupported file-based effects,
recovery assets and shared person/group inputs remain refused, including when
loaded from a persisted graph rather than received through a command.

Legacy control mirrors are editing views, not an additional rendering owner.
Current-source graph validation precedes their reuse. Preview/export inputs must
not forward the original file as a substitute body or hair source for a composite.

The portrait registry also had a source-visible neutral-recipe inconsistency:
its deform default passed an empty map to a validator which rejects empty maps.
The authored correction uses explicit zero values for all supported deform keys.
This fixes the contract, but is not a claim of executed regression acceptance.

## Parked-target and batch foundation, still fenced

`creative_derived_source.row_asset/row_proof/verify_row` distinguish the immutable
composite hash and dimensions from physical-original provenance. The portrait
transfer preflight, commit and final checks now retain both proofs. Scoped batch
history records preserve that proof; legacy receipts without it may restore only
original-file targets, never a returned image sharing the original path.

Parked candidate validation supplies explicit document-private people context,
requires the exact candidate graph, uses baked dimensions and the existing float
export resolver, and never decodes original pixels for a returned source. Current
row lookup uses effective identity. Physical document-history relocation anchors
remain unchanged.

This is a planner foundation, not enabled cross-image transfer. Shared derived
person/group relationships remain incompatible with the audited local-only effect
contract, so the dispatcher continues refusing generic batch, semantic and shared
portrait operations in sessions containing returned images. Future work must
adapt each relevant shared asset/evidence consumer, then open only the proven
operation subset and verify transactional preview/export/history parity.

## Remaining implementation and runtime work

- Hair, body, advanced makeup/reference, semantic/local masks, repair/recovery,
  source patch and other unadapted effect paths remain explicitly fenced.
- Shared relationships and confirmed-person transfer to returned images remain
  fenced despite the new effective-source planner proof.
- Full runtime, numerical, visual and recovery/package acceptance is pending the
  authorized local test owner. In particular, compare preview and full-resolution
  output for every admitted portrait control, undo/redo across return/fresh layer
  creation, stale gestures, saved derived recipes, and rejection of original
  source analysis or legacy batch receipts.
- No additional algorithm implementation or third-party engine was copied. This
  slice reuses the existing admitted solvers and Rust float source/compositor;
  the primary practice references remain those in `DERIVED-SOURCE.md`.

## Integration map

| Boundary | Files |
| --- | --- |
| Exact command/source/operation admission | creative_derived_effects.py, creative_document_host.py |
| Source-only preview/export and graph validation | people_owned_inputs.py, people_engine_runtime.py, people_render_runtime.py, people_effects.py, people_export.py |
| Existing UI mirror and parked lookup | people_host.py |
| Neutral deformation registry | people_algorithms.py |
| Effective row proof and frozen transfer fences | creative_derived_source.py, people_batch_transfer.py, people_batch_ledger.py |
| Parked full-source candidate and scoped restoration | people_candidate_render.py, people_history_persistence.py |
| Fresh-current full-resolution capture | creative_document_refresh.py, creative_document_base.py |
| Native receipt and workspace action | creative_layers_api.rs, creativeLayers/nativePort.ts, useCreativeWorkspace.ts, CreativeWorkspace.tsx |

UNRUN fixture sources are under `engine/tests/fixtures/creative_layers/`:
`test_derived_effects_contract.py`, `test_derived_people_planner_contract.py`,
`test_fresh_current_document.py`, and the tightened malformed-envelope case in
`test_derived_source_contract.py`. Native fresh-capture admission also has an
UNRUN Rust fixture. No whole-product acceptance follows from their presence.
