# Source-connected integration freeze

Integration base: 66393d4a88633690a8769c76206e06c2b9413490. Status SOURCE_CONNECTED_UNRUN. Every runtime/build/typecheck/visual/performance acceptance remains UNRUN.

## Actual pixel route

Existing stage order is preserved: geometry → reference → semantic → colour grading → selective colour → whole-canvas photo detail → NEW grain → final monochrome. Extended-tone exposure prepass remains unchanged and returns before grain/detail final processing. No colour or geometry stage was silently moved ahead of another.

Grain's coordinate domain is the original-sized developed editing raster immediately before crop/rotation, after any earlier optics/deformations. It is artistic grain anchored to that raster, NOT a sensor-noise model attached to facial landmarks or optical ray coordinates. photo_grain_geometry.mapping uses the existing geometry module's exact crop rounding, quarter-turn snap, output size, inverse rotation and valid-corner rules. It emits at most 65536 coordinate triples per call. Native mapped grain samples the persisted seed field at those source coordinates on the full-resolution final edited canvas. Outside-image rotation corners do not receive grain. Source dimensions and transformed canvas dimensions must match exactly; unknown/resized mappings fail.

Export keeps original-size geometry/colour/detail processing, grain and monochrome together. If export-only scale/sharpen are requested, photo_grain_export performs that complete source render first and then uses existing global Lanczos Plan/banded upscale and final unsharp. This is an explicit active-grain delivery policy; neutral paths retain legacy ordering. Crops whose scaled rounding produces a different canonical output shape are explicitly rejected with a corrective message, not silently shifted or resized. Output size is not a second grain-size unit.

Preview photo_grain_runtime uses verified original RGB16/RGB8 decoding, ICC conversion, canonical captured export recipe and full export renderer. It checks source stamps, original dimensions, budget, document/revision/cancellation and missing layers. Only the finished float canvas is area-downsampled to the fixed display canvas and packed. No fresh proxy-resolution noise is generated. Initial reopen, device switch, normal edit rendering and grain preview/commit share this route. Vram's optional source-output callback also supplies final float colour-scope/capture output; unbound export tile pipelines keep the normal neutral path. Inspection snapshot carries the exact seed recipe and its full-quality path invokes the same grain-enabled export renderer. Display overlays never enter export.

Rust stores no image/noise buffers. Python mapped bridge mutates only the renderer's private assembled float target and allocates one source-row copy plus bounded coordinate rows. The existing source/whole-canvas detail render still owns full image buffers. The runtime admits a conservative RAM reserve and max100MP source/canvas; no performance or zero-copy claim.

## Connected canonical ports

- server: neutral defaults, stored-state/history capture/restore, active report, export snapshot, service ingress/shutdown, controller-owned commit, final shared-memory publication fence, ready capability and source preview.
- project v21: v20 detail and v19 primary remain accepted; new grain validates recursively, is rejected in older schema, and only missing fields default to neutral.
- scope: lnx.photo_grain.v1, full recipe only; preset/batch apply the same strict recipe including seed. Existing host group transactions remain authoritative.
- export_recipe/export_snapshot/master16_policy/full_quality: no RGB16 neutral passthrough when grain active; no omitted grain in inspection.
- Tauri request/status/frame_status/abort registration and epoch-correlated receipt dispatch; existing exact presented-frame verification remains.
- RetouchPanel, native capability types, batch/preset labels and exact eight control paths connected. Controls reset preserves seed.
- packaging includes std-only original Rust library and license/contract; no runtime compilation or downloaded assets.
- Reader-side sibling services classify photo_grain_state as read-only, avoiding accidental invalidation on panel readback.

Remaining: compile, typecheck, tests, runtime/visual/performance validation by Qoder. Scaled crop rounding incompatibility is a disclosed supported-domain limit, not a completed all-geometry acceptance claim.
