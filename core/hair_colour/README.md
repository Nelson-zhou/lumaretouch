# Hair colour and measured gloss, ABI 1

Status: original source implementation and source-only fixtures. Compilation,
Rust tests, C/Python ABI integration, photographic quality, memory/throughput,
preview/export parity and visual acceptance are **UNRUN**. Qoder owns local
execution and acceptance. This core has no external crates, new learned weights,
downloads, generated assets or runtime compilation.

The commercial guide https://www.pixcakeai.com/guide/32472 is a reference for
feature names only. This is not its implementation, formula, palette, quality
claim or a reverse-engineered commercial effect. Every palette coefficient,
effect strength and threshold below is an original project choice.

## C ABI and caller responsibilities

```c
uint32_t lrt_hair_colour_abi(void); /* 1 */
int32_t lrt_hair_colour_apply(
    const float *rgb, const float *support,
    size_t width, size_t height, uint32_t style,
    float strength, float gloss, float *delta, float *highlights);
```

- Process the **entire immutable source once**, not independently per output tile
  or per viewport. Any cache must include the complete source/version, support,
  dimensions and controls. Reusing original measured evidence across control
  edits is mathematically possible; this ABI computes it on every call.
- `rgb`: contiguous interleaved RGB, `3*width*height` float32 samples in [0,1],
  display-referred encoded sRGB, not BGR, scene-linear RGB or arbitrary ICC RGB.
  Upstream colour management must establish this encoding. Nonfinite, negative
  and extended/HDR inputs are rejected, including pixels with zero support.
- `support`: mandatory contiguous one-channel float32 in [0,1], source-aligned,
  representing real hair intersected with the reviewed selected-person source
  mask. The caller must establish provenance, geometry and selected-person
  identity. This core cannot detect a bad/stale mask or recover missing semantic
  segmentation. Null is an error, never an unmasked fallback. An all-zero mask
  is valid and produces exactly zero delta and highlight fields.
- Both controls are finite [0,1]. No `none` style is required in this ABI;
  neutral colour is `strength=0`. Gloss can operate independently. The caller
  may bypass this core for a completely neutral recipe.
- `delta`: `3*N` float32 **encoded-sRGB additive differences**, not replacement
  RGB. The caller adds them exactly once to the same source. Do not apply this
  result repeatedly to a mutable prior result, blur it or rescale it as a mask.
- `highlights`: `N` float32 measured evidence in [0,1], multiplied by support,
  independent of style and both control amounts. It is not output RGB, a gloss
  gain, a physical specular probability or permission to extend the hair mask.
- `width`/`height` must be nonzero, with checked product at most 64,000,000
  pixels. Every buffer must be live, aligned, sufficiently large and stable for
  the whole call. Outputs must not overlap either input or each other. The ABI
  checks nulls, address alignment, address/length overflow and numeric span
  overlaps; **it cannot prove arbitrary pointer validity or allocation size**.
  Do not call in-place or mutate inputs concurrently.
- RGB8 callers convert to float32 by division by 255. RGB16 callers divide the
  full original uint16 samples by 65535. Keep the source precision through the
  whole effect and quantize only at an explicitly requested final RGB8/RGB16
  output boundary. There is no uint8/uint16 intermediate, palette LUT,
  quantization or dithering inside this core.

Status codes: 0 success; 1 invalid shape, pointers/spans, controls, style, RGB or
support; 3 nonfinite/out-of-range computed result; 4 scratch allocation failed;
99 caught Rust unwind. All inputs are validated, all buffers allocated and all
results computed before either caller output is modified. Recoverable failures
leave **both** outputs unchanged. Pointer faults, concurrent memory violations,
process termination and allocator/OS aborts are outside this guarantee. The
packaging script retains unwinding; consumers choosing panic=abort cannot
recover Rust panics through status 99.

## Original palette order

These numbers are encoded-sRGB colour intents, not replacement RGB, target
lightness, physical dye measurements or commercial presets. Only their decoded
chromaticity is used; selection never substitutes a flat swatch for source hair.

| ID | Label | Original RGB intent |
|---|---|---|
| 0 | 蜜茶棕 | .52, .31, .16 |
| 1 | 栗棕 | .40, .22, .13 |
| 2 | 落日橘 | .80, .27, .08 |
| 3 | 冷茶棕 | .31, .28, .22 |
| 4 | 苦亚麻 | .42, .40, .27 |
| 5 | 自然黑 | .075, .072, .068 |
| 6 | 玫瑰紫 | .47, .18, .37 |
| 7 | 蓝黑 | .10, .14, .24 |
| 8 | 鸢尾蓝紫 | .31, .20, .56 |
| 9 | 树莓粉棕 | .55, .26, .34 |
| 10 | 枫叶红 | .65, .14, .10 |
| 11 | 苔绿 | .29, .36, .20 |
| 12 | 薄藤粉 | .65, .46, .59 |

## Colour mathematics and texture limits

Point math uses f64; public samples/deltas and highlight fields are float32.
Decode and encode use the sRGB piecewise transfer curve (.04045/.0031308,
12.92, 1.055, .055 and exponent 2.4). Linear luminance is
`Y = .2126 R + .7152 G + .0722 B`. Let `S(a,b,x)` denote clamped cubic smoothstep
`t*t*(3-2*t)` for `t = clamp((x-a)/(b-a),0,1)`.

1. Protect unrecoverable regions with
   `q(Y) = S(.001,.012,Y) * (1-S(.90,.995,Y))`.
2. Decode the selected original palette `P` and normalize its chroma as
   `Cp = P/luma(P) - 1`. Colour amount is `t = .82*strength*q(Y)`.
3. Every style except natural black uses `Y' = Y`. Natural black alone uses
   `Y' = Y - .40*strength*max(Y-.001,0)*(1-S(.92,.995,Y))`.
   This never increases luminance, is identity below .001 and at/above .995,
   and is monotone. Where the positive part is active, the derivative of the
   subtracted term is at most .40, so the luminance derivative is at least .60.
4. With `r=Y'/Y` for positive Y, otherwise zero, form
   `C = (1-t)*(RGBlinear-Y)*r + t*Y'*Cp`.
5. Find the largest `k` in [0,1] such that all channels of `Y' + k*C` are
   in [0,1]. Contract along that chroma ray, not by separately clipping each
   channel. This retains the chosen luminance, up to floating-point precision.
6. Apply the measured gloss term below. Mix source and proposal using support
   **in linear light**, then encode and subtract the original encoded source.
   Feathered mask edges therefore also preserve linear luminance when gloss
   and natural-black deepening are off. Final roundoff guards bound RGB and
   verify the caller's float32 `source + delta` lies in [0,1].

With both amounts zero, delta is exactly positive zero. Every zero-support
pixel has exactly zero delta and highlight weight. There is no RGB spatial
filter, texture smoothing, generative fill, new strand, geometric warp, relight
or recovery of clipped data. Source luminance detail and shading are retained
for ordinary colour selections, but source chroma changes and gamut contraction
are intentional. These are numerical properties, not photographic guarantees.
Dark hair stays dark: the pink/lavender/ash labels cannot bleach black hair,
recover unseen detail or promise a light swatch match. Natural black only
deepens existing luminance through the documented monotone point transform.

## Measured existing-highlight gloss

Gloss is derived from the **original source**, not from the newly tinted RGB.
There is no learned highlight mask or global exposure boost.

- Local radius is `round(min(width,height)*.0025)`, bounded to 1–12 source
  pixels. Broad radius is `round(min(width,height)*.018)`, bounded to 3–96.
  Windows truncate at source-image edges. Compute each mean as
  `sum(support*Y)/sum(support)` with separable rolling f64 sums. Unrelated
  zero-support background is excluded. Neighbourhood support of at most
  1e-12 falls back to the source Y, hence contributes no positive contrast.
- Let the two means be `L` and `B`. The original evidence is
  `h = S(.0015,.045,Y-L) * S(.003,.12,Y-B)`
  `    * S(1.08,1.75,Y/(B+.01)) * S(.035,.28,Y) * q(Y)`.
  The positive local and broad contrast gates, high relative luminance gate,
  absolute visibility gate and clipping guard must all pass. A uniform patch
  or an isolated supported flat hair region has no gloss, even with a feathered
  mask. Deeply clipped blacks and fully clipped whites also have none.
- Gloss amount is `a=.16*gloss*h`. Move the colour proposal toward neutral white
  by `proposal += a*(1-proposal)`, then perform the linear-light support blend.
  The returned diagnostic is `support*h`, independent of slider amounts.

This enhances source evidence already present; it does not infer physical light
sources. Bright texture, noise, an incorrect hair mask or colour patterns can
still resemble a highlight. Large locally flat light patches intentionally get
no added gloss in their flat interiors. No threshold implies a quality score.
Source-scale windows make independently processed tiles/preview crops
incorrect; preview and export must use full-source evidence and coordinates.

## Resource and acceptance limits

Filtering is O(N), independent of window area, with one reusable full-source
two-f64 accumulator buffer. Peak scratch is approximately 40 bytes per pixel
(two staged outputs, luminance, one mean field and accumulator pair), excluding
input/caller output allocations and allocator overhead: about 2.56 GB at the
64M-pixel limit. That is a hard geometry cap, not a promise that every machine
can allocate it. Allocation failures are reported without output writes. The
three filter temporaries are released before the pointwise colour pass. There
is no unbounded iteration or per-tile statistic, but no cancellation callback
in ABI 1; callers should manage stale work/versioning outside it.

Inline `#[cfg(test)]` fixtures are source only and **not run**. They cover exact
neutral/mask-zero output, flat/no-gloss hair, real highlight-only changes,
background exclusion, amount-independent diagnostics, all 13 styles, linear
luminance preservation including soft masks, monotone natural black, clipping,
invalid inputs with atomic outputs, null support, dimension overflow/limits and
output overlap. They do not substitute for compilation or photographs.

Local acceptance must compile using the packaging script, run these fixtures,
then exercise the caller's true full-resolution RGB8/RGB16 path, source-mask
provenance and selected-person isolation, soft hair edges/skin/background,
black/white/clipped hair, dyed hair and curls, fine highlights/noisy images,
flat hair, both independent sliders, all labels, reset/undo/preset roundtrips,
stale async jobs and preview/export parity. Check CPU time and peak memory
before claiming 64M-photo practicality. No such acceptance has occurred here.
