# Flash red-eye correction: source implementation, acceptance UNRUN

Baseline: `6e5d18af5a0f3cff53794752da4f0cc87b2d76aa`.

## Requirement and non-duplication

`LNX-REF-PC-32470-C-ee00f0a195` is the supplied handbook's dedicated **祛红眼** control. The local mapping is `AI开发资料包/功能需求验收映射.json` (PC-32470), and `baseline_probe/manual-text.txt` eye-enhancement section. The official URL is <https://www.pixcakeai.com/guide/32470>; this research read failed through the web tool, so exact semantics come from supplied reference material, not a claim to have read the live page.

Existing sclera brightness, iris brightness, blood-vessel cleanup and catchlight enhancement remain separate and unchanged when this new scalar is zero. New canonical leaf: `/red_eye` in `lnx.enhance.v1`. Local neutral zero and range [0,1] are engineering choices, not disclosed official numeric defaults. This is not eye-white purification (`26ab900915`), eye replacement, iris recolouring, pupil reconstruction, or the whole eye-enhancement package.

## Primary method and licence boundary

GIMP's current [Red Eye Removal documentation](https://docs.gimp.org/3.0/en/gimp-filter-red-eye-removal.html) explicitly recommends selecting affected eye regions and describes replacement of excess red using the other channels. This supports a bounded colour correction, not a detector or proof of flash causation. GNOME GEGL's primary red-eye operation is GPL-3.0-or-later; exact source reference and method differences are in `core/red_eye/README.md`.

The new Rust implementation is original GPL-3.0-or-later code. No GEGL source or proprietary model/weights are copied. Existing RapidRetouch under-eye/vein/catchlight code keeps its own AGPL notice; the new red-eye-only route does not invoke it or require OpenCV.

## Actual source and numerical contracts

- The existing selected FaceRef, detector evidence, source asset identity and repaired source stack own the analysis. No source photograph's mask or landmarks are transferred to another photograph.
- `red_eye_apply.support` uses the actual 478-point geometry at the current source dimensions. It constructs an inward eye aperture and central iris candidate disk, with exact zero outside 0.65 measured iris radius. This is **not a measured pupil mask or semantic segmentation**. Tiny/strongly foreshortened geometry and empty support refuse rather than invent a pupil.
- The Rust solver tests actual red dominance against both green and blue, reduces only eligible red excess, and preserves G/B, neutral pixels and zero coverage. No replacement texture, synthetic eye detail or reconstruction. Coefficients are locally chosen and uncalibrated on natural photos.
- Input is encoded-working-sRGB SDR float32, three colour channels. Invalid/nonfinite/out-of-range pixels refuse; no HDR/alpha flattening or clipping workaround. Existing original PNG16 decode remains float source, without reducing the eye pixels through RGB8. Float32 correction precision is not mathematically bit-exact arbitrary RGB16/ICC equivalence.
- The whole source-owned eye ROI is solved once before export tiling. Masks are regenerated from full-source geometry, not enlarged from a proxy. Zero-delta locations retain their original values; existing post-geometry addition/compositing contracts still apply when combined with other effects.
- The original asset is immutable. The correction is a nondestructive source-derived delta. Combined red-eye and existing eye-detail controls deliberately compose red-eye first, then existing corrections. The delta is aligned with the same canonical deformation grid and added in the established eye-detail stage. This does not promise commutativity with iris enhancement or other corrections.

## Integration map

- `ops/enhance.py`: scalar validation/defaults; the three `SUBS` planes are unchanged. No alias to `iris` or `veins`.
- `red_eye_apply.py` + `red_eye_native.py` + `core/red_eye`: geometry/evidence, strict native bridge and actual correction.
- `under_eye_layer.py`: source ownership, repair invalidation, distinct per-control facts, valid no-red no-op vs invalid-support refusal. Legacy five-control logic remains independent; no extra runtime solver fallback.
- Existing `people_effects.py`/`people_pipeline.py`: `eye_detail` record, target ownership and common geometry. Canonical `has_enhance` does not call a zero eye-detail delta applied merely because its record exists.
- `vram.py`/`export.py`: source preparation, full-source solver, preview/export attachment. Legacy/export cancellation uses the existing callback; canonical synchronous preparation has no new asynchronous job-cancellation promise.
- `export_recipe.py` and server strict replay: missing active red-eye target support is a hard refusal, not a skipped export or silently saved preset.
- `enhance_scope.py`/`people_scope.py` + existing generic confirmed-person batch: scalar-only inheritance, target reanalysis, strict transaction/history. Generic legacy preset application onto a derived image remains refused; direct canonical derived-source controls and reviewed target-person transfer use actual effective-source evidence.
- Native optional field `redEye` is omitted when absent; explicit zero resets only this leaf. Existing old command wrappers remain intact. UI capability gating reflects actual native library loading and exposes a separate reset and ambiguity warning.
- Packaging stages the new native library and its original source/license. No library was built during this work.

## Remaining limits and required acceptance

Source-connected only. All authored Rust/Python/TypeScript fixtures are **UNRUN**. No build, import, runtime test, inference, natural-photo comparison, installation or performance measurement was performed.

An inward iris disk is only a conservative search region. Natural red/brown irises, coloured contacts or coloured reflections can be mistaken for flash redness. Geometry cannot establish causation. Large, displaced or irregular pupils, occlusions, small faces and weak/desaturated reflections may be incomplete or refused. UI warns users to inspect the original/current comparison. There is no new dedicated pupil review, manual red-eye mask or recovery brush, and no claim to restore the original eye colour.

Required local acceptance includes: native ABI build and packaging, sparse IPC/undo/redo/project roundtrip, original and returned-derived identities, real source PNG16 export, canonical multi-person overlap, off-axis/closed/occluded eyes and coloured contacts, combined effects, full-resolution/tiled equivalence, target-only batch/preset ownership, no-op reporting, cancellation/resource failure rollback, and natural photographic quality. Broader eye-white purification, AI reconstruction and alpha/HDR pipeline support remain unfinished.
