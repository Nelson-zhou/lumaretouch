# Reviewed crop transfer on actual edited targets

Baseline `9718b562caddb28a5d4410c20307c96df0a12043`. Source integration only. Fixtures are AUTHORED / UNRUN. No product imports, execution, tests, compiler, typecheck, inference, downloads or installations were performed.

## Requirements and scope

The supplied handbook §5, manual text lines 1022–1027, requires normalized coordinates plus target preview for transferable crop; otherwise crop must be excluded. References: `LNX-P0-CROP`, `lnx.crop.v1`, `P0-CROP-NEUTRAL`, `P0-CROP-BOUNDARY`, and feature-map `LNX-REF-PC-32478-C-184506303b` (guide 32478). Existing Linux P0 geometry supports −180..180 degrees; the official manual summary describes tilt −45..45. This preserves existing Linux behavior, not proprietary equivalence or completion of AI head-space, head-ratio or face placement.

Both original and derived batch targets and crop presets now require genuine target preview. Tokenless crop batch commits and raw crop preset apply are refused with a review requirement. Direct per-image crop is unchanged. The transfer allowlist admits crop parameters only in conjunction with the existing transaction owners' review checks.

## Actual pixels, source ownership and geometry

`full_candidate_render` extracts the existing strict portrait candidate exporter. Portrait validation supplies its staged graph; crop supplies the target candidate recipe and retained target graph/context. It does not swap live documents, borrow source masks or invent analysis. Unclassified imports must first be opened to establish document ownership; established empty portrait graphs stay empty.

Originals use genuine full-resolution RGB8/RGB16 decoding, not drafts, camera previews or half-size substitutes. Returned images use immutable canonical creative pixels; original bytes remain provenance only. Existing local masks, recovery, deformation, studio/sky/ID backgrounds and body support checks run before `build_export_spec`; skipped effects reject the target.

The existing `export_float` path renders the fully edited candidate using canonical `ops.geometry`: crop first, then clockwise rotation. Full-source rounding, quarter-turn snapping, expanded output canvas and arbitrary-angle boundary behavior remain those of full export. Only after full rendering does `crop_transfer_review` reduce and encode a display PNG. No CSS simulation or proxy crop is claimed as full-source evidence.

Source/output dimensions and memory are bounded. Oversized targets report blocked rather than silently reducing render resolution. Derived opaque SDR remains the supported photo domain; alpha/signed/HDR returns are refused before display conversion. Display PNG quantization does not alter original RGB16 or canonical float assets. This thumbnail is not a 100% quality proof or saved output image.

## Review, commit and history

Public `crop_transfer` evidence carries document/revision, effective-source/original-provenance proof, complete candidate digest, independent people context/graph digest, exact crop parameters, full source/output dimensions, and PNG bytes/dimensions/digest. Frozen private evidence omits PNG bytes. No raw floats or base64 preview are embedded in history.

Every eligible crop target has a preview, not merely the first few. Limits: 16 targets, display edge 320, encoded base64 at most 400,000 characters per preview. Existing metadata and receipt caps remain unchanged. Over-budget requests fail explicitly without truncating targets; high-entropy display PNGs may be reduced further without changing the full render.

Batch and preset UI compare evidence with frozen target fences and crop parameters. Confirmation waits for every relevant PNG hash and natural image dimensions to verify. Readiness is keyed to exact token/proof/PNG envelope. Preset document/review changes invalidate stale preflight responses, while uncertain mutations remain queryable without retransmission.

Existing workflow ports provide prepare/verify callbacks. Batch freezes compact proof, rechecks actual candidates before commit and retains source-bound protected history. Presets verify before token consumption and replay. After the transaction's own revision advance, post-render checks use only the captured expected new revision in an ephemeral proof; the durable frozen proof is not rewritten. Checks stay inside existing rollback boundaries. Group undo preserves unrelated later edits instead of restoring an old whole-image recipe.

Integration: renderer/proof in `full_candidate_render.py`, `crop_transfer_review.py`, `people_candidate_render.py`; batch in `batch_preflight.py`, `batch_preflight_controller.py`, `batch_sync.py`; presets in `local_grade_preset_review.py`, `preset_controller.py`, `preset_transaction.py`; ports/admission in `workflow_ports.py`, `scope.py`; UI in `ui/src/cropTransfer`, batch/preset workflows and App's review invalidation key. Existing native `preset_host.rs` now accepts crop-only preflight only with bound crop evidence, rather than rejecting it for lacking a local-mask/optics module. Read-only preset completion no longer requests a redundant session-state refresh that would invalidate its own visual review. No new native command registration or undo owner.

## Residuals and required local acceptance

Persistent cross-owner person associations, automatic identity candidates and inherited person/group edits remain unfinished. General support-bearing transfer and derived semantic/reference/optics planners remain guarded. ID recovery, spill removal and original-shadow extraction remain unfinished. Broader transparent/HDR photo-pipeline support is not implemented here.

Local acceptance still must cover original↔derived and derived↔derived targets; RGB16 and differing extents; identity/tiny/edge crops and arbitrary rotations; all target effects retained; stale source/graph/recipe/revision and post-render replacement; budget refusal without proxy fallback; every-target image readiness and repeated/context-switched review; raw apply refusal; protected undo/redo, save/reopen and package recovery; full export against 100% inspection. No such scenario is claimed passed. UI fixtures require explicit selection of the repository's TypeScript/React-aware runner; no automatic registration or compilation is claimed.
