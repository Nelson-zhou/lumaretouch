# Eye-white purification: bounded original implementation

Baseline `83ea2ce34ecc2bb7a6872bbc40969f6c91d3ee12`. **Source-only; all runtime and photographic acceptance UNRUN.**

## Exact requirement, useful difference, and retained gaps

The supplied reference mapping identifies **LNX-REF-PC-32470-C-26ab900915 / 眼白净化**. Its legacy source URL is <https://www.pixcakeai.com/guide/32470>. The current official [eye-enhancement guide](https://www.pixcakeai.com/guide/202667), read on 2026-10-23, separately describes ordinary sclera brightness, red-vessel removal, purification of dull blemishes/colour casts, and flash-red-eye correction. That current cross-platform page corroborates the distinction; it does not replace the supplied legacy ID or disclose the proprietary algorithm. No official numeric range/default or model compatibility is inferred.

New scalar `/sclera_purify` belongs to existing canonical `lnx.enhance.v1`. It is not an alias or rescaled call to `sclera`, `veins`, `iris` or `red_eye`. Local [0,1] and neutral zero are implementation choices. The new original solver applies a bounded source-neighbour correction to small dark outliers and separately reduces chromatic casts at the same linear-light luminance. Existing brightness and vessel algorithms remain independently selectable and unchanged when purification is zero.

This is a limited implementation of the requirement, not full official feature acceptance. Broad dark areas, severe defects, arbitrary tissue/occlusion, strong casts, lost texture and unknown anatomical abnormalities are not reconstructed. It does not diagnose the photographed eye or estimate its true colour under the scene illuminant.

## Primary techniques and licensing

- [OpenCV's official smoothing tutorial](https://docs.opencv.org/4.11.0/d4/d13/tutorial_py_filtering.html) describes local median replacement for impulse noise and the difference from averaging. This motivates a robust local reference, not a claim that every dark eye pixel is noise.
- [GIMP's official desaturation documentation](https://docs.gimp.org/3.0/en/gimp-filter-desaturate.html) distinguishes linear-light luminance from nonlinear luma. The new solver explicitly linearizes encoded working-sRGB before its luminance calculation; it does not describe an encoded-HSV adjustment as physical luminance preservation.
- `core/sclera_purify/README.md` records exact additional primary numerical sources and licenses. This project implements its own algorithm and ABI. No external source, model, weights or runtime dependency was copied or downloaded. Existing unrelated RapidRetouch code retains its original notice.

## Source ownership and conservative geometry

`sclera_purify_apply.regions` processes each actual source-owned eye independently. It uses the existing 478-point landmark contract at width/height scale, not another subsystem's width-minus-one convention. An inward aperture with a hard safety inset excludes the eyelid border. Expanded **maximum** iris-rim radius excludes the iris and limbus. Both corners are excluded. Tiny, strongly foreshortened, nearly closed, empty or insufficiently supported regions refuse instead of widening a mask.

Source pixel gates suppress dark lashes/frames, highly chromatic leakage and near-white highlights. The soft edit support and stricter donor confidence are distinct: boundary/low-confidence targets cannot automatically become clean statistical references. Each full-source eye ROI includes its local neighborhood halo; the other eye, skin, iris, unsupported pixels, previously corrected pixels and preview interpolation are not donor fallback sources. Radius is source-scaled and bounded explicitly, not silently capped. Both unusable eyes cause failure; one usable eye may proceed with separate facts for the refused eye.

These are geometric and photometric **candidate** masks, not a semantic sclera model or reviewed occlusion segmentation. Glasses, lashes, makeup and coloured reflections can still be misclassified. Existing iris-makeup review does not prove sclera visibility and is not falsely reused as such. There is no new manual sclera mask or independent review receipt. The UI states this limit and asks for actual original/current comparison.

## Numerical and compositing contracts

The native bridge accepts finite float32 SDR encoded-working-sRGB RGB plus float coverage, amount and integer radius. It rejects alpha/HDR/out-of-range inputs instead of flattening or clipping. Original PNG16 decoding remains the shared actual float source; eye ROIs are not quantized through an RGB8 proxy for this correction. This does not claim arbitrary ICC16 bit-equivalence or HDR support.

Host admission accounts conservatively for additional full-face private composition buffers; the bridge separately admits native eye-ROI memory and neighborhood work. Neither is a measured performance guarantee or an unconditional megapixel-support claim.

The original Rust solver works on an immutable full-eye source. Reliable local neighbors supply its median-luminance reference; explicit directional/support tests restrict lifting to compact dark outliers, with bounded correction and no fabricated texture. Separate chroma reduction blends toward a same-luminance neutral. Gamut safety must be achieved by bounded shared adjustment, not independent channel clipping. Uniform neutral and unsupported samples stay unchanged. Exact coefficients, budget, donor and directional conditions are in the core README and authored fixtures, not claimed photo-calibrated thresholds.

UnderEyeLayer prepares both new red-eye and purification results independently from the untouched source and deliberately composes their deltas. Their geometry excludes each other; any actual overlapping changes refuse. Existing under-eye/vein/catchlight operations follow this combination. The complete source delta follows the established `eye_detail` stage: it is aligned with the common geometry and added after ordinary enhancement. This is not a new parallel history owner or a guarantee that separately selected effects commute.

## Integration and failure map

- `ops/enhance.py`: scalar registration, strict numeric validation, neutral defaults. Three original enhancement planes remain unchanged.
- `sclera_purify_apply.py`, `sclera_purify_native.py`, `core/sclera_purify`: separate source geometry and actual native solver. No Python numerical fallback or runtime build.
- `under_eye_layer.py`: named new-control lookup, preserved five-control legacy/OpenCV gates, actual per-control facts, frozen-source solve, repair-version invalidation, atomic publication.
- Existing canonical people effect preparation and source/FaceRef binding own the same `eye_detail` record; no copied source masks or added undo owner.
- Existing preview and full-source export solve before tile extraction. Native/export cancellation and failure discard private output; no new asynchronous canonical cancellation is claimed.
- `export_recipe.py`, server strict replay and `people_scope.py` refuse missing active support instead of saving skipped effects. Legacy command rollback also catches native allocation and OS/cancellation failures before publishing new state. Normal scalar preset and reviewed confirmed-person transfer regenerate target-local support. Generic legacy preset onto a derived source remains refused; direct canonical returned-source edits use actual effective analysis.
- Extracted UI control and sparse native transport preserve old caller signatures, omit absent optional parameters, and retain explicit-zero reset. Actual native ABI availability gates edits; absence never calls old brightness or vessel algorithms as a substitute.
- Packaging stages the new library, original source and license. Packaging itself was not run.

## Verification required, not completed

Authored Rust/Python/TypeScript fixtures remain **UNRUN**. No application imports, compiler/build, test runner, typecheck, inference, image processing run, model download, installation, latency or natural-photo QA occurred during authoring.

Required local acceptance: native ABI/build/package; real natural eyes across skin tones, light irises, glasses, reflections, makeup and occlusion; detailed false-positive assessment; small/signed-zero/neutral invariants; local median gate and radius behavior; original PNG16 precision/export; original and derived source identities; per-person overlap; source repair invalidation; combined filters and deformation; tile/full-source equivalence; project/history/recovery round trips; sparse IPC and zero reset with missing core; preset/batch target ownership, rollback, cancellation and memory admission. No product-wide or full eye-enhancement completion claim is made.
