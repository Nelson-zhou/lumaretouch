# Photo detail: source-authored, runtime UNRUN

Source-connected implementation against project v19 / base 48115f45, writing project v20. Shared hooks are authored; runtime correctness is NOT asserted. Nine independent controls, three groups. Not AI denoise, not a texture/clarity alias, no weights or model installs. No compile, test, typecheck, product imports, inference, packaging or visual evaluation ran.

## Evidence and direction

Handbook lines 603–610 and the supplied feature-to-acceptance map establish the color/detail family. Verified canonical official source 2026-10-23: https://www.pixcakeai.com/guide/32455, lines 403–424. The concatenated `/32455329` and `/32455456` paths did not resolve; these are not separate verified guide pages. Official sharpening amount enhances edges, radius controls extent, detail favors smaller structures. Luminance noise detail is explicitly stronger denoising at higher values, unlike Adobe. Chroma detail preserves finer color edges at higher values, with blotch tradeoff; smoothness reduces color noise more broadly, sacrificing detail. Official text does not disclose numeric ranges or define a numerical contrast direction. Our contrast control increases residual integration with surrounding luminance rather than changing global contrast. All ranges/defaults are original product decisions.

Mature primary references, consulted for concepts rather than copied implementation:
- https://helpx.adobe.com/content/dam/help/en/pdf/lightroom_cc_reference.pdf: amount/radius/detail separation and luma/chroma distinctions. Its luminance-detail direction is deliberately NOT copied.
- https://docs.darktable.org/usermanual/4.2/en/module-reference/processing-modules/denoise-profiled/: distinct luma/chroma treatment and profiled/NLM/wavelet tradeoffs. This implementation is NOT a camera-profiled denoiser or NLM.
- https://docs.darktable.org/usermanual/4.2/en/module-reference/processing-modules/diffuse/: scale visibility, edge and halo concerns. This is NOT a deconvolution/diffusion claim.

## Original math and boundary

f32 display-encoded RGB is split into weighted luminance and red/blue residual chroma. Chroma noise uses separable edge-guided smoothing and bounded residual suppression; smoothness changes spatial support and detail changes chroma residual threshold. Luma uses independently controlled edge-guided smoothing, higher detail broadens range tolerance, and contrast modulates residual integration. Sharpening uses Gaussian unsharp residual with detail-dependent fine-structure gating, not the extended-tone texture bands. Output remains float and unclipped until host output conversion.

The whole source frame must be evaluated after global color operators including grading/selective/CUBE and before final monochrome and output quantization, following the established optics/geometry/reference/semantic ordering. There are NO tile calls for this stage. A full-frame explicit proxy may use scale <1; radii are scaled from source pixels. Such previews are approximations, not exact native-resolution quality evidence. Native-size export and 100% inspection use scale=1; enlarged export passes its explicit output/source ratio (up to 8). Inspection ROI cropping occurs AFTER whole edited-canvas processing. Recipe crop/rotation stays at its existing pipeline boundary before reference/semantic/grading/selective/detail; no existing effect is reordered. No hidden resize exists. All active effects must run once, never twice via tile and assembled routes. Missing native fails visibly; neutral recipe bypasses native and is bit exact.

## Resource and cancellation policy

Maximum 100 MP; explicit conservative admission at 160 bytes/pixel +32 MiB, capped by min(8 GiB, half available RAM), prior to active-frame copies. Native temporary buffers use fallible reserve. Core uses bounded support at most 9 px at source scale (72 px at the admitted 8× scale) per separable pass, O(N*r), no global quadratic matrix or implicit downsample. Cancellation polls rows, every 128 filter pixels, every 4096 channel pixels, and before publication. The host transaction keeps native output private until complete. Estimated bound is not a measured peak; performance, cancellation latency and OOM behavior remain UNRUN.

## Transactions

Existing Engine document revision, history, rollback and publication fence are reused through explicit ports, not a second undo system. Requests correlate document/revision/request ID, retain receipts and reject ID reuse with changed payload. Unknown outcomes never trigger resend. UI keeps unresolved request identity across remount and offers query/cancel/readback/manual reconciliation. Shared dispatch must not automatically record another history entry. Batch/preset preparation is pure; existing host transaction owns actual all-or-none commit. No local masks are advertised.

## Release gate

Every requirement is SOURCE_CONNECTED_UNRUN. Shared hooks now exist in server/history/project v20/scope/export/inspection/native/UI/packaging; all numerical, visual, native ABI, UI, restart/rollback, export parity, batch undo and performance acceptance remains UNRUN until Qoder/local QA executes against the frozen hash set. Do not call this production-ready or equivalent to PixCake/Adobe/darktable quality.

## Source wiring completed (runtime UNRUN)

Preview: primary before extended tone unchanged; existing geometry/reference/semantic/grading/selective then photo detail then monochrome. Export applies detail once to assembled float32 output, after selective and before monochrome. Export tile stages stay neutral. RGB8 inspection uses the same geometry-aware export route for active detail, and RGB16 already uses the geometry-aware shared route. Recipe storage is in DOC_FIELDS and existing history capture/restore; batch/preset operations register in the existing scope engine. Native readiness checks ABI1 rather than file existence alone. Reader cancellation and publication fences cover detail and mutually superseding edits. Packaging explicitly compiles the Rust core, but packaging was not run.

The 100 MP limit applies to the actual processing canvas; a very large enlarged export can therefore be refused explicitly. Memory estimates and CPU separable-filter performance are not measured guarantees. Tool-routing coverage is not upgraded to visually accepted; exact requirement IDs live on the authored real controls and in the integration map.
