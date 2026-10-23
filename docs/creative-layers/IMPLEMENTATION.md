# Creative image document foundation: source implemented, acceptance UNRUN

## Exact baseline and scope

Source: Linux open-source portrait retouch product handbook, extracted manual-text.txt lines 257–271 and 909–922; AI development package functional acceptance mapping; official workflow 127932. M11/M12 and the bounded M14 bridge only. No M13 candidate generation/re-generation and no claim that the 32 AI algorithms are implemented.

All IDs have prefix `LNX-REF-WF-127932-`:

| Suffix | Required semantics | Source implementation / residual |
| --- | --- | --- |
| 5989aa3ddc | Independent creative workflow | Controlled real image document, not decorative aside |
| c37e1cce2d | Select, rename, duplicate, delete, lock, hide layers | Stable IDs, inherited locks, unified recoverable history |
| 67dd01e14f | Empty/selected groups and add/remove masks | Isolated groups, real imported numeric masks; no fake mask button |
| 44a13c1440 | Blend and opacity | Exactly 正常/正片叠底/滤色/变亮/变暗: normal/multiply/screen/lighten/darken |
| 504f58d74a | Canvas dimensions/DPI when unselected | Metadata/extent changes do not resample original assets |
| b392a2decb | Alignment, position, scale, rotation, flip | Current image-layer affine transform, center rotation/flip |
| 22318776c0 | Generated removal/candidates | NOT implemented; M13 separate |
| 657ed77402 | Superresolution-related transform | Generic transform foundation only; no superresolution algorithm claim |
| a9c143a25d | Return as new image / update original | Real full-resolution bake, independent row or single history update; source-bound tool rebinding remains incomplete |
| c7783ea5fb | History recovers original after bake | Existing host snapshot owner, no second undo stack; original source bytes untouched |

Native project format remains v23. No proprietary `.tsq` compatibility claim.

## Integration boundaries

- `App.tsx` retains one creative hook; `CreativeWorkspace` replaces the decorative aside. Controls are authoritative, not optimistic. Image imports and masks are real assets. Native file drops route to the open creative document. Existing tool catalogue and canvas guides remain.
- `creative_layers_api.rs` supplies bounded Tauri request/status and receipt reconciliation. `engine.rs` routes authoritative events; main registers commands. Request identity is source UID + document ID + revision + ownership token + request ID. Unknown sends do not automatically retry.
- `server.py` registers creative_document, serializes commands, persists fields in normal snapshots, switches proxy geometry for baked baselines and uses the existing history owner. Read-only state polling does not revoke other capture owners.
- `creative_document_host.py` connects assets, state commands, full current-edit capture, native rendering, history, source rows and return. `creative_document_controller.py` owns request/ticket fences but never a second history stack.
- `creative_document_state.py` is the pure validated command graph. Immutable asset references survive duplication and historical deletion. Groups are isolated; non-neutral ungroup is refused rather than changing appearance.
- `creative_document_import.py` reuses existing ICC/true-PNG16 paths. Source bytes and ICC are retained. No preview bitmap is promoted to an export asset.
- `creative_document_render.py` orchestrates bounded tiles; original Rust `core/creative_layers` performs premultiplied linear-space float32 color/alpha blend and bilinear transform sampling. Full source halo is available across tile edges. Transparent exterior is distinct from clamped edge pixels.
- A validated non-null `_creative_base` is the authoritative bake marker: the original portrait/body graph is retained but dormant, not deleted or rebound. Native portrait synchronization and legacy slider mirroring stop before touching original-source analysis; export ignores that dormant original graph. Existing unified history restores `_creative_base=None` and its exact original graph together. All new source-bound mutations are refused until true derived-source binding exists.
- `creative_document_base.py`, export_snapshot/export_recipe/export/master16_policy resolve a baked base exactly once, retain float32 before final integer encoding and refuse unsupported alpha/HDR returns. Native project/recovery/package blob integration is documented in the storage module.

## Numeric and resource contract

Canonical RGBA is little-endian float32, premultiplied alpha, linear sRGB D65. Alpha is finite [0,1], zero-alpha color is zero, and unassociated signed/HDR channel magnitude is bounded by 65504. SDR source import converts ICC to working sRGB before native linearization, including true 16-bit PNG. Numeric mask coverage is linear [0,1], not color-managed. RGB16 export must not stage through uint8. Preview clipping/matte is display-only and never an implicit destructive return.

Five exact blends follow W3C compositing source-over equations, applied in the declared linear working space. Group isolation follows mature editor architecture, not a copied engine. References: https://www.w3.org/TR/compositing-1/ and https://docs.krita.org/en/reference_manual/layers_and_masks/group_layers.html . No Photocraft or other third-party engine code was copied. Original code uses the repository GPL-3.0-or-later license. Packaging includes its source, ABI, header and license.

Native tiles are bounded to 65,536 pixels. Source/canvas admission is at most 100 MP and memory-budget bounded; graph max 1,024 layers / depth 32. Engine budget is at most half estimated available RAM and at most 4 GB, not an unconditional 24 MP performance guarantee. No runtime compiler fallback. Missing packaged native library is an explicit capability failure. All numerical and visual performance claims await local tests.

## Remaining implementation map, not accepted functionality

1. M14 source-bound tools: create a genuine immutable derived-source identity for the baked composite, bind all face/body/segmentation/repair/local-mask/optics/reference-color owners to that content and reanalyse it. Never spoof the original SHA or merely refresh original-path faces. Current live guard and pre-inference export guard refuse such edits. Cross-document people/batch/semantic plans are conservatively fenced while a returned-base row is loaded, and target portrait candidate validation rejects that row; these planners still need derived-source-aware target admission. global tone/crop and layers remain available.
2. Alpha/HDR photo return: extend retouch baseline/pipeline and output codec contracts before enabling. Current independent layer documents retain these pixels exactly; return to the current opaque SDR photo pipeline fails without flattening/clipping.
3. High-bit/multipage formats: supported bounded single-page RGB/RGBA TIFF and PNG paths must be locally verified. Unsupported associated-alpha, multipage, or missing lossless codec paths fail explicitly.
4. Full-resolution 100% inspection transport still assumes original-file snapshots and does not admit canonical byte assets. Its start is explicitly refused for a returned base until content-bound asset transport and dimensions are integrated. Main export is separate.
5. Full viewport gestures, interactive paint-mask editing and advanced group transforms are not implied by numeric layer controls/imported masks.
6. Reopening an existing creative document resumes its retained layer graph. Later main-workspace adjustments do not silently rewrite its source layer. An explicit “new creative document from current edited pixels” transition, preserving the old graph in history, remains a follow-up.
7. M13 generation is separate. Imported/composited output provenance is never described as AI generation.

## Verification boundary

Only source inspection, Python AST parsing, JSON/hash/manifest inspection and whitespace checks are permitted here. No product imports, compiler, typecheck, native build, inference, tests or application execution have run. Fixtures in core/creative_layers/tests.rs, engine/tests/fixtures/creative_layers and ui/src/creativeLayers/client.test.ts are authored UNRUN. Qoder must verify packaging, ABI, numeric neutral/blends/halos/alpha, 16-bit gradients/ICC, 24 MP bounded save/recovery/package, all command/history/race flows and visual acceptance before any requirement is marked accepted.

## Persistence and ordinary-photo resource accounting

Canonical float32, original encoded image and ICC bytes are losslessly divided into <=7,000,000-byte hash chunks. The v23 JSON manifest references immutable owned sidecar blobs; it does not embed full RGBA per history step. Save fsyncs blobs before the atomic manifest replace. Project files must travel with their hidden creative asset directory, or use the portable package. The sidecar name derives from the project basename: use application Save As or portable packages rather than manually renaming only the JSON file. There is no automatic orphan deletion. Existing 256 MB project-manifest, 64 MB recovery-freeze manifest, 1,024,000,000-byte recovery-store and package caps are not raised.

Recovery captures a small frozen manifest plus immutable payloads, accounts exact unique raw bytes and manifest/receipt overhead, and restores mandatory blobs. Packages always carry creative blobs even if optional original dependencies are omitted, and validate hashes on extraction/readback. A bounded shared immutable-byte cache prevents repeated identical history frames from becoming separate full RGBA buffers on decode; exact-input validation caches do not modify canonical asset tables.

24 MP arithmetic only, not runtime acceptance: one RGBA-f32 raster is 384,000,000 bytes; original plus one different returned base is 768,000,000 bytes plus retained encoded source/ICC/other history. A 25 MB original yields approximately 793 MB, fitting a fresh recovery budget but not guaranteeing room when prior candidates/history remain. Import admission is 96 bytes/pixel plus twice encoded input, up to about 2.572 GB for the UI's 128 MiB file maximum. Source/render/return and available-RAM admission remain independent. Transient base64/project-validation copies still exist, and full-source preview hashing/rendering can be expensive. Qoder must measure peak memory, failure atomicity and responsiveness on real 24 MP files.
