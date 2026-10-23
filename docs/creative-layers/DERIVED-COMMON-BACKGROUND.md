# Reviewed common background on an immutable returned source

Status: source-authored, UNRUN. Baseline 038d91eabfe198dddf69966f22409eab4d8f3f7c.
No product imports, execution, tests, compiler, typecheck, inference, model download,
or numerical/visual acceptance occurred. This is not completion of M14 or 32 AI tools.

## Requirement reconciliation

The existing handbook/map evidence is retained in COMMON-BACKGROUND-SOURCE.md and
ID-BACKGROUND-RECOVERY.md. PC-32475 common replacement and its spill/original-shadow
families are not equivalent to a deterministic color key. In particular spill
removal/manual spill brush (`e999ab085a`, `4bc238dfa1`) and original-shadow family
(`442ced0175`, `ab010073e3`, `48553e2d03`, `c959928d7a`, `b1b766d4ce`,
`9e1c732ff8`, `0513155f3d`) remain unfinished. The separate supplied-map recovery
item `LNX-REF-PC-32481-C-0f284fcda5` belongs to dedicated ID replacement, not this
common stage. No item is counted twice. Existing official-source/code-contract
references from the preceding slices remain the evidence; no new model-compatibility
or license claim is made here.

## Source and pixel contracts

Version 2 `legacy-color-key-effective-v2` binds the actual immutable returned
source SHA256 and canonical dimensions. Original encoded-file SHA256 is separate
provenance, never substituted for returned-source identity. Acquisition consumes
the verified canonical float32 preview source, freezes its border-median reference
and reference grid, and stores tolerance/softness/color as recipe intent. It does
not borrow original analysis/masks or claim full-size border analysis.

Full-resolution export and inspection evaluate the same frozen key against actual
canonical float32 source pixels, in bounded strips under existing pixel/memory
budgets. Internal content proof ties preparation to canonical export_source output.
The full matte is not an enlarged proxy bitmap. New v2 preview matte is float32;
original v1 retains its previous proxy quantization/appearance. Immutable pixels
remain external owned assets through existing project/package/recovery mechanisms;
no raw full image is embedded in history.

Returned source admission remains opaque SDR float32 RGB only. Alpha/HDR sources
are refused, not flattened or clipped. This admission does not license clipping
upstream edits: v2 common composition shares the exact existing ID low-level
linear-field float math, preserving alpha=1 edited pixels and extended edited
values. ID stage order, packed-field alignment, asset decoding, and separate
recovery target are unchanged. Original v1/legacy compositor behavior is deliberately
unchanged. No Rust/Torch numerical equivalence is inferred from extraction.

## Review, mutation and history

A distinct common_background protocol, native preview host and receipt owner carry
set/clear. No studio controller is reused. Actual synchronized production proxy
before/after images are produced without replacing source RGB or borrowing a stale
recovery stage. The UI must load both images at the reported dimensions, paint,
and obtain native and engine presentation acknowledgments. Recipe document/revision,
load/session/preview IDs, source, fields, composition mode and geometry remain bound.

Only the exact presented candidate can be consumed once. Native enqueue redeems
proof while holding the engine/proof ownership locks, with epoch binding and
bounded preview-ID tombstones. Cancellation revokes admission immediately. Unknown
results retain their original receipt and never auto-resubmit. Read-only engine
polling does not revoke the review. The modal blocks global compare/undo shortcuts
and remains visible across family filtering; closed pending work retains query UI.

Controller owns one existing history transaction, not dispatcher plus controller.
Precommit failure restores state, ledger and dirty flag; failed rollback requires
reload. Postcommit frame-publication failure is not reported as a clean rejection.
Monotonic invalidation fences are not decremented. Project serialization retains
versioned key intent and original provenance, including inactive keys needed by
dormant recovery. No-change follows the existing semantic history signature.

## Recovery and integration map

`background_replace` remains distinct from `id_background`. Its vectors bind the
actual common consumer's source/key/color, prepared matte/background bytes,
composition mode, geometry and activity. Review requires an active consumer for
new strokes; disabling/clearing retains checked source intent for dormant rows.
Export prepares full-source fields and verifies the consumer at prepass/final
boundaries. No unrelated recovery target is used as a bypass.

- creative_derived_common_background / common_background_source: v1/v2 recipe,
  canonical admission, provenance, full-source preparation and export ownership.
- common_background_preview_source: disposable fields, replay and content proofs.
- common_background_review / effect_recovery_preview: strict shared synchronization,
  actual current render, bounded presented candidate and restoration.
- common_background_controller / creative_common_background_host: exact source
  transport, one history owner, receipt replay, cancellation and derived guard.
- common_background_recovery / effect_recovery_* / creative_derived_*recovery:
  vector evidence, preview/commit gate and export preparation/verification.
- creative_document_base/project, id_background_project, project_recovery_runtime,
  preview_lifecycle, studio_tools_dispatch, server: existing lifecycle integration.
- ops/matting, id_background_stage, vram, export: shared float primitive with an
  explicit v2 mode; original/ID stage semantics otherwise retained.
- native common_background_api/host, AppState/dispatch/lifecycle: isolated review
  and terminal receipt transport, not an unrelated command alias.
- ui/src/commonBackground, RetouchPanel, App, useOriginalCompareKeys, native:
  persistent actual-image review, one-shot apply and competing-editor barriers.

## Explicit remaining limitations and next validation

Subsequent bounded transport recovery is documented in COMMON-BACKGROUND-READBACK.md.
Same-engine verified terminal readback addresses lost acknowledgments, not the
genuine failed-rollback/checkpoint-reload limitation below.

1. Unknown/requires_reload retains its receipt and locks edits; a dedicated verified
   host reload/reconciliation escape is not implemented. Restarting cannot turn an
   unknown outcome into success. This is a real recovery UX limitation.
2. Existing custom SHA-gated neural backend is not official BiRefNet compatibility;
   full-resolution derived neural transport/hair segmentation remain blocked.
   Existing diagnostic legacy original routes are not upgraded by this slice.
3. Common image-background assets/pickers, spill removal, original-shadow/contact
   segmentation, general alpha/HDR pipeline and common shared transfer remain
   unfinished. Existing ID high-bit assets are not narrowed or removed.
4. Existing global proxy-size loader clears undo/redo for legacy pixel layers.
   Current key intent survives; arbitrary old bitmap history migration does not.
5. Full model quality, real image review, rendered small-screen accessibility,
   performance, native compilation, numerical equivalence, rollback faults,
   original/derived RGB16 export, save/package/reopen and undo/redo need local
   validation. Fixtures are authored UNRUN and are not evidence of passing tests.
