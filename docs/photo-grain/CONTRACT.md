# Deterministic photo grain source implementation

Status: SOURCE_CONNECTED_UNRUN. Shared integration is source-connected; every runtime acceptance remains UNRUN.
No claim of PixCake algorithm parity, finished UI integration, tested output, GPU acceleration or performance. No model, texture, binary or package was downloaded. No product import, execution, tests, compiler, typecheck or build was run.

## Evidence and parameter decisions

Official PixCake https://www.pixcakeai.com/guide/32455, checked 2026-10-23, grain section lines 426–456 identifies overall strength, shadows, midtones, highlights, size, roughness and colour. It does not disclose numeric ranges or a seed algorithm. Local baseline is manual-text.txt lines 603–610 and AI开发资料包/功能需求验收映射.json, eight IDs in requirements.json. Lumaretouch's numeric ranges/defaults are original engineering decisions, not advertised official values.

Primary mature practice https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/grain/ distinguishes grain coarseness, strength and mid-tone bias. Its documentation says Lab L; our original implementation instead applies additive extended-encoded-sRGB noise (optional signed linear conversion). This is a design comparison, not copied code or identical film simulation.

## Algorithm

Version 1 uses integer coordinate hashing and smooth interpolated lattice fields. Persisted unsigned-32 seed is never regenerated on render, reset, undo, project restore, preset apply or batch. RGB channel keys are distinct. Roughness adds an independent half-size octave; size controls spatial correlation in original source pixels; colour blends common-channel noise into independent RGB noise. Smooth tonal weights partition unity and independently scale shadows, midtones and highlights before strength. No image-sized noise arrays exist.

The working/output float32 values preserve negative and >1 headroom, including linear mode via signed transfer functions. Inputs limited to finite +/-128 encoded or +/-65504 linear. Integer quantization/clipping belongs ONLY to terminal host output conversion, not this stage. This is artistic grain, not denoising and not an overlay.

## Source and output coordinates

Recipe size_unit is strictly source_pixels. A 2-source-pixel grain shrinks with a 1/4 output resize, rather than becoming a new 2-output-pixel grain. Native x,y are absolute integer coordinates in the full original source raster, pixel centers x+0.5,y+0.5. All tile/band origins must come from host source geometry. No viewport dimensions, zoom, device pixel ratio or proxy dimensions derive these coordinates.

Actual order preserves existing geometry → reference/semantic → grading → selective → whole-canvas detail, then adds grain before final monochrome. Grain uses inverse crop/rotation coordinates in the original-sized developed (post-optics/deformation) raster; it is not sensor noise tied to pre-warp scene content. See INTEGRATION.md for exact coordinate and full-source rendering contracts.

Preview uses verified original decode and the canonical full-source export chain, followed by area downsampling of the completed float image. Output resize/sharpen occur after the grained source edit in the active-grain delivery route. Crops whose scaled rounding would change canonical dimensions are rejected rather than misaligned. Active context-free/proxy apply_np and apply_t remain rejected; the integrated route is the mapped Rust row bridge, not either fallback.

## Memory and lifecycle

Rust has constant local state and no heap allocation. Native FFI processes at most 65536 pixels in one source row. The standalone stage allocates one caller-sized destination and one bounded row copy; the integrated mapped bridge works in-place on a private assembled float target with one bounded row copy plus coordinate triples. The generic source-band bridge permits 64-row bands; integrated preview/export share the existing source renderer and a conservative max100MP memory admission. Caller source and private sink storage remain host responsibilities. No multiple full noise buffers. A private sink should use an existing full-resolution render target or disk-backed storage; no publication until all source rows, canonical geometry and cancellation fence succeed.

Controller/service/nativePort/workflow follow existing grading typed transport patterns: one replaceable preview, document/revision identity, cancellation between chunks, exact-presented-frame commit fence, retained idempotent receipts, no resend on unknown outcomes, history transaction rollback/reload guard. Host owns history, preset, project, batch, export, publication and inspection hooks. Seed is portable recipe data; source identity/cached pixels/overlays are not preset data.
