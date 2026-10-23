# Colour grading: source-connected implementation, runtime/quality UNRUN

Scope: only PC-32455-C-f13fcb2a36 and its seven children. This is not completion of the whole colour feature family, not visual-quality acceptance, and not a vendor pixel-equivalence claim. No product/test/build/compiler/typecheck/import/inference was run by this worker. Fixture files are **UNRUN**.

## Baselines and primary research (read 2026-10-23)

- Supplied `manual-text.txt`, colour-adjustment section around lines 603–616; supplied `AI开发资料包/功能需求验收映射.json`, exact eight controls recorded in `requirements.json`. Full source SHA-256 values appear there.
- PixCake official https://www.pixcakeai.com/guide/32455, section 颜色分级, lines 362–370 in retrieved page: independent shadow/midtone/highlight/global colour wheels, radial saturation, blend transition smoothness, positive balance expands highlights, selected-range brightness. The vendor does not publish its numerical algorithm or parameter domains. Our domains below are product design choices, NOT disclosed PixCake values.
- Adobe official https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/image-tone-color.html describes independent tonal colour wheels and balancing their effects. https://blog.adobe.com/en/publish/2020/10/20/introducing-color-grading was visible in search but direct retrieval failed; not relied on for exact mathematics.
- darktable official https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/color-balance-rgb/ documents luminance-mask grading and scene-referred RGB. https://github.com/darktable-org/darktable/blob/master/LICENSE contains GPL version 3. It is a design reference only: no darktable source code, LUT, assets or constants specific to its implementation were copied.
- Existing repository LICENSE is GPL v3. New implementation is original source under repository-compatible GPL-3.0-or-later; no third-party runtime dependency is introduced by the Rust std-only library. Vendor prose, screenshots, algorithms and assets have not been imported into the product. Existing NumPy/React/Torch dependencies retain their existing notices. This is an engineering provenance record, not a legal opinion.

## Original v1 mathematics

All operator arithmetic is f32. For linear sRGB/D65 pixel p, Y = .2126 R + .7152 G + .0722 B. Mask coordinate t = clamp(max(Y,0)/(max(Y,0)+.18) + .003 balance, 0, 1). Positive balance moves a given tone towards the highlights. Mask half-width d = .04 + .36 blending/100. S = 1 - smoothstep(1/3-d,1/3+d,t), H = smoothstep(2/3-d,2/3+d,t), M = max(0,1-S-H), then normalize S,M,H to sum to one. Increasing blend broadens the transition, not a no-op slider. The .18 anchor is linear scene middle grey; no local adaptation or image histogram is used.

Each wheel maps hue to cos(h), cos(h-120°), cos(h+120°), subtracts the vector's weighted Y and normalizes by its maximum absolute component. Multiply this zero-luminance direction by saturation/200. This adds a graded tint; it does not change HSL hue buckets or semantic regions. Tint amplitude is max(Y,.02), allowing a restrained coloured lifted black. Local tint is S*shadow + M*midtone + H*highlight; global tint is separately added with unit weight. Thus global operation is independent of blend/balance whenever local wheels are neutral. Brightness uses gain = 2^(.02*(global_luminance + S*shadow_luminance + M*midtone_luminance + H*highlight_luminance)). Range brightness travels with its actual mask.

Hue 0–360° (360 canonicalizes to 0), saturation 0–100, brightness -100–100 (±2 stops per selected range), blend 0–100 default 50, balance -100–100 default 0. All four wheels default saturation=brightness=0. Hue/blend/balance alone with zero wheel strengths is exactly inactive. Neutral returns identical pixels without native dependency; the Rust neutral branch bit-copies signed zero and HDR floats.

## Precision and colour management

- Native chunk: 1–65,536 pixels, interleaved 3-channel f32, explicit mode 0 linear sRGB/D65 or 1 extended encoded sRGB/D65. All parameters finite; all channels finite. Linear input range ±65504, encoded input range ±128. Invalid recipe/pixels leave native output untouched. Caller must provide valid non-overlapping aligned buffers; no untrusted raw address is accepted over IPC.
- Signed extended sRGB decode/encode is in Rust. No HSL substitution, 8-bit LUT, ICC transform, white balance, geometry, inference or detail synthesis is hidden in this operator.
- Float output remains unclipped, including negative and >1 scene/highlight information; no gamut mapping or display transform is claimed. Non-neutral tint can produce negative channels, intentionally preserved until the existing terminal output transform.
- Host current colour-stage convention is encoded extended sRGB, so `apply_np` defaults to that explicitly named adapter domain. Callers with linear pixels must pass `encoding='linear-srgb-d65'`. Arbitrary camera/log/Display-P3/ICC RGB must first be converted by the actual colour-management path. A decoder lacking that contract is a blocker, not permission to relabel pixels.
- Integer RGB8/RGB16 adapters normalize directly to f32, never through uint8. Clipping/rounding occurs only when returning terminal SDR integer pixels. Internal active export must use f32 and quantize once, after all colour stages. Neutral integer input is exact identity.
- `apply_t` is an explicit Torch-to-CPU-Rust bridge preserving output f32. It is NOT a GPU implementation or a performance claim. Full image adapter budget is 100 megapixels; chunks permit cancellation. Actual 100MP memory/latency, GPU transfers, RGB16 gradient retention and HDR negative colour quality require local acceptance.

## Preview, persistence and safety

IPC contains only recipe scalars and bounded identities, ≤4096 serialized characters. It accepts preview/commit/cancel/status only. Recipe and unknown-field validation fail closed. One pending preview survives; new preview invalidates the old ticket. Owner-thread rendering is required; ingress cancellation sets an Event read between Rust chunks. Fenced preview results, revision and document checks prevent older intent committing. UI maintains one in-flight preview plus one replaceable pending recipe. Apply requires exact shared-memory sequence/slot and compositor-presented preview confirmation via the native bridge; history gets one non-coalesced entry only on change.

Cancel re-renders committed state; cancel during an unconfirmed commit is not treated as undo. A failed/uncertain commit blocks until query/reload, never blind retry. A bounded 64-receipt map deduplicates identical commit IDs and rejects ID-content reuse. Status lookup is valid after the commit revision advances. The shared dispatcher must preserve receipts/errors and invalidate on unrelated mutations.

Project v17/history store the complete versioned recipe, retaining v16 extended-tone, v15 CUBE and v14 hair decoding. Legacy omission is neutral; explicit malformed/null recipe is an error. Presets carry values only, no source image/masks/pointers; applying replaces, not accumulates. Batch preparation validates all target states first and copies independent recipes; shared batch owner remains responsible for atomic group history/rollback. Export uses the exact same stage and recipe.

## Not yet established

No compilation, tests, runtime route, UI rendering, GPU timing, large-image memory, quantitative smoothness, skin-tone visual review, export equality, project reopen, history, preset or batch E2E behavior is certified. Shared hooks were connected under the 2026-10-23 exclusive integration grant at base 40227cd94931e3651fb84a4572de0d412c65403d. See INTEGRATION.md. SOURCE_CONNECTED_UNRUN does not certify compiled or runtime behavior.
