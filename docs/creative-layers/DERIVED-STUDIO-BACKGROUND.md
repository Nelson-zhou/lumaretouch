# Derived-source studio background: source-only integration

Baseline: `2ab9d1345c2ce47592e63c82e5626ce42e5d81aa`. This slice adapts existing studio cleanup, not sky replacement, ID replacement or proprietary AI. No runtime acceptance is claimed. Fixtures are authored and UNRUN; no product imports, build, typecheck, inference or tests were run.

## Handbook mapping and primary evidence

The supplied Linux handbook, background section (manual-text lines 568–575), and development-package mapping identify the following exact requirements. Prefix all suffixes below with `LNX-REF-PC-32474-C-`:

- `d637886dca`: solid-background intrusion removal.
- `c03981fad1`: solid-background blemish removal; `75549ae6f0` background and `f06957c177` floor scopes.
- `0eb173d7d8`: blemish enhancement brush; `8505883728` add and `77953fa019` subtract.
- `508ddebe87`: lighting uniformity; `07dabe5ea7` child brightness, -100..100, default 0.
- `b5e8d5499a`: solid-background colour-banding removal.
- `98057214a1`: background enhancement.
- `c68a287a5a`: recovery brush.

[Official background guide](https://www.pixcakeai.com/guide/32474), read 2026-10-23, reports update 2026-09-09. It limits the first four modes to solid backgrounds, separates floor/background blemishes, specifies add/subtract plus size/feather/flow/opacity and update-before-confirm, and describes recovery of those four individual effects. The existing implementation uses measured deterministic OpenCV float operators and Rust vector rasterization. Source rebinding does not demonstrate proprietary-model equivalence or complete official visual acceptance.

## Source and processing contract

- Immutable returned asset identity and dimensions own retained studio intent, including inactive recipes and history. The original pathname, digest and file stamp remain separate provenance. A different returned asset cannot inherit vectors merely because it shares a physical path or dimensions.
- Actual installed `src_f32` is checked against immutable pipeline evidence. Studio measurements intentionally use the pre-repair source, matching the existing original-photo algorithm. Their contributions are applied to current edited pixels after repair/light/smoothing/fabric, before automatic deformation. This slice does not reorder the algorithm or paste source pixels over other edits.
- Manual background/floor/protect/enhancement and recovery vectors retain their existing normalized domain and complete-resolution Rust replay. Semantic background requires actual current-source inference input, pinned model identity and measured background editing weights. Floor is never inferred from a person/background classifier.
- Review freezes source, recipe, model/coverage and actual pixels across asynchronous preparation, presentation and apply. Existing native review acknowledgment, final transaction, receipts and unified history remain the only edit owner. Static inspection of `studio_background_api.rs` and `studio_background_host.rs` confirms the existing protocol already admits these exact manual/semantic recipes and four recovery targets; no native guard was broadened. Exact terminal receipts remain replayable, while cancellation can release a stale review without blessing its pixels.
- Full export resolves canonical RGB float32, stamps those actual pixels, then checks them before semantic observation conversion and studio preparation. Only model observation is RGB8. Rendering keeps canonical floats and regenerates full-source semantic coverage rather than enlarging proxy masks. No HDR/alpha clipping workaround is introduced.
- Physical decode dimensions are not compared to a returned canvas. Original-file provenance is checked separately; full effect preparation and tile slices use the immutable derived dimensions. Snapshot provenance also supports the derived 100% inspection path without decoding the original as a substitute.

## Integration ports

`creative_derived_studio` owns durable validation, frozen context, actual preview proof and canonical export proof. `creative_studio_host` admits exact existing studio envelopes only. `studio_background_state`, `studio_background_preview` and `studio_background_runtime` retain existing reviewed intent and consumption. `export_snapshot`, `ExportSpec`, canonical export resolution and `studio_background_export` carry/check the ephemeral context. `creative_document_base` removes only the studio fence after verification. Project staging and server state restore validate every retained frame before mutation. Semantic-only studio intent triggers current-source analysis even when no faces were retained.

Studio `recover_intrusions`, `recover_blemishes`, `recover_uniformity` and `recover_banding` attenuate their corresponding contribution using the existing stage. They are not the distinct common `background_replace` recovery target. No new common recovery target is enabled.

## Explicit residuals

- Sky manual regions still need immutable source/asset/review/export binding; automatic OneFormer acquisition and resolver still read the physical source path.
- ID replacement still needs source-owned support/prompted-mask resolution, picker modes, immutable asset bundles and preview/export binding together. Its stage is not legacy full replacement.
- Legacy background replacement and its common recovery remain fenced. So do unadapted cross-image/preset/batch transfer, which require target-owned analysis and explicit identity review.
- Transparent or HDR returned sources are still explicitly refused by the portrait RGB path, not flattened or clipped.
- Retained semantic intent, including zero-strength recipes, requires matching current-source analysis before export or another reviewed edit. Missing/stale model evidence is explicit failure, not a manual/full-image fallback; reanalysis is required.
- Existing budgets, full-domain processing, Rust helper availability, model availability and native presentation are not runtime-verified here. Proof checks copy/hash actual proxy buffers; latency and memory require local measurement. Source wiring is not a claim that all official modes or all 32 AI tools are complete.
