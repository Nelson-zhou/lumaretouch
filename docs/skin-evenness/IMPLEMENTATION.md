# Face skin colour evenness: source implementation, not accepted AI parity

Baseline: `377e601de8941d55047843c421b8c93b903def54`.
Requirement: **LNX-REF-PC-32465-C-60b7c0e3d1**, `PC-32465|AI肤色统一（脸部）`.
Status: **PARTIAL; all numerical, runtime, UI and photographic acceptance UNRUN**.

## Exact scope and distinctness

The [official skin guide](https://www.pixcakeai.com/guide/32465) describes uneven facial colour, red cheeks and local colour patches. It supplies no algorithm or numeric range. This implementation offers an original deterministic, own-source chromatic correction, not a learned blemish classifier or proprietary-equivalent AI. Its anatomical evidence uses the existing actual face-skin observation and measured landmarks; that does not make its correction learned AI.

The prior official leaf routed to `skin.broad`, a photograph-level RGB frequency gain coupled to smoothing. That recipe and its rendering remain unchanged, with explicitly labelled legacy strength and broad-gain controls still available. Broad gain zero is not old smoothing-neutral; old strength zero disables that smoothing. The new `lnx.skin_evenness.v1` has an independent amount in [0,1], neutral zero. No old numeric value is migrated or automatically cleared.

Under-eye colour correction was not added again: existing dark-circle code already uses surrounding skin and low-frequency colour/tone. This operation is also not skin temperature/tint, whitening, gloss, texture sharpening or body colour matching.

## Source, solver and stage contracts

- A live canonical FaceRef, matching normalized 478-landmark digest, actual named face-skin class/observation and known-occluder evidence are required. Producer dimensions may differ from the current render grid while aspect and normalized source identity remain valid.
- Intersect measured face anatomy with source skin semantics; exclude eyes, brows, mouth, known occluders and every retained foreign face box on the same source, including disabled or unresolved neighbours. No body-mask extrapolation or borrowed analysis.
- Prepare once on the true source ROI containing all own-face support and a real 2r+1 halo, clipped only at image edges. Radius is measured on the current grid; unsupported scales refuse rather than secretly downsample.
- Original Rust computes own-face robust log-chroma reference and masked luminance-guided low-frequency chroma. Adequate reference and local context are required; missing reference/context is an error, not a successful neutral result. A valid already-even image may produce a genuine zero field.
- Retain a read-only HWC2 log(R/G), log(B/G) shift, bounded to vector length 0.09. It is not an RGB bitmap delta or reusable source mask.
- At the dedicated stage before existing skin-colour corrections, decode the ACTUAL upstream RGB, apply the field as diagonal linear gains, normalize to that pixel's current linear luminance, then use one gamut-feasible interpolation. No per-channel clipping or copied old-source brightness. Later colour/geometry stages can change this invariant; this is not a final-output physical claim.
- Native CPU applies each ROI with stable first-face ownership. Device preview/export merges the same two-channel fields into tile coordinates and applies the same pointwise algebra; float64 temporaries are bounded to row strips of at most 131072 pixels. No tile-local reference solve. Native/device precision and parity remain UNRUN.
- Original PNG16 working-source and immutable derived float paths enter the existing actual-source preparation and shared renderer. They do not reuse original-source analysis for a derived source. SDR opaque input only; broader alpha/HDR remains unsupported, not clipped.

## Integration and persistence

`skin_evenness_state` defines strict scalar intent; `people_algorithms` registers it. `skin_evenness_layer` owns measured support and immutable reference preparation. `LocalEffect.chroma_shift`, `people_render_runtime`, `people_effects`, `people_pipeline` and the existing vram stage carry the genuine field and count its retained memory. `skin_evenness_composition` performs current-stage application.

`skin_evenness_project` checks active, undo and redo leaves, including malformed neutral/no-face cases. Export fast-path admission cannot bypass malformed leaves. Existing canonical owner transactions, frozen preview/export snapshots and history receipts remain authoritative; no second undo owner was introduced.

`skin_evenness_scope` transfers only amount and rebuilds each actual target's independent source/reference/support with strict rendering before commit. Explicit reviewed cross-owner/derived maps and frozen receipts remain required. Generic derived preset installation remains refused; this does not broaden unsupported shared paths. Neither field, reference, floor/skin mask nor source colour is serialized in the preset.

Native capability gates the dedicated UI. The official leaf opens explicit strength and canonical before/after review, with pending/uncertain and owner/provenance fences. Existing legacy controls remain visibly separate. No dedicated manual recovery brush has been implemented for this new stage; supplying such a recovery record is refused rather than borrowing another operation's mask.

Packaging adds only the original Rust core/source/license alongside existing distribution. No runtime download, runtime compilation, Python effect fallback or additional weights are introduced.

## Primary technique and licence basis

- [He, Sun and Tang, Guided Image Filtering](https://people.csail.mit.edu/kaiming/publications/pami12guidedfilter.pdf): local linear luminance-guided filtering and chrominance guidance. The mask-normalized two-pass extension, admission policy and retouch reference here are original implementation choices, not an exact reproduction claim.
- [Barron, Convolutional Color Constancy, section 2](https://arxiv.org/html/1507.00410): log-chroma and diagonal gains. Its log(G/R), log(G/B) convention differs by sign from the equivalent coordinates used here. This implementation does not use its learned illumination estimator or claim illumination recovery.
- [OpenCV 4.10 guided-filter implementation](https://raw.githubusercontent.com/opencv/opencv_contrib/4.10.0/modules/ximgproc/src/guided_filter.cpp) was inspected as mature primary source. Its file header is BSD-3-Clause; repository licence is Apache-2.0. **No source was copied**, no reference implementation or model was downloaded. New original implementation follows this repository's GPL-3.0-or-later licence. Reading a paper does not grant a licence to its authors' separate code.

## Remaining limitations and acceptance

An own-face robust reference is a chosen statistical target, not recovered healthy skin or illumination truth. Coloured lighting, blush, freckles and natural pigmentation can resemble unwanted patches; there is no automatic makeup/material separation. Existing skin segmentation and landmark errors, unknown occlusion and low sample/context support can limit or refuse correction. Review is necessary, not a claim that detection is correct.

Body unification, multi-person brightest-reference matching, eyedropper target selection and neutral-grey lighting reconstruction are separate requirements and remain unimplemented by this slice. This adds no new count for those IDs. Full guide acceptance cannot be inferred from connected source or authored fixtures.

All tests are authored and UNRUN under the current no-execution rule. No build, import, compiler, typecheck, inference, performance run or photo evaluation was performed. Static source/AST/hash checks establish only the recorded source structure, not working-product acceptance.
