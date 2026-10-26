# Fixed Swin2SR CPU inference source — UNRUN

This is a new inference graph, **not RRDB with a new label**. It targets only
`caidas/swin2SR-classical-sr-x2-64` at
`cee1c923c6a37361c6e5650b65dcf4be821e5d52`.

## Primary evidence and license

- [Official pinned model card](https://huggingface.co/caidas/swin2SR-classical-sr-x2-64/blob/cee1c923c6a37361c6e5650b65dcf4be821e5d52/README.md)
  explicitly declares `license: apache-2.0`. Its observed raw 642-byte SHA256 is
  `9186aaf5bf94b0adb71532ad70368320e8134815fa026827c8f0e4920dc6886c`.
- [Official pinned config](https://huggingface.co/caidas/swin2SR-classical-sr-x2-64/blob/cee1c923c6a37361c6e5650b65dcf4be821e5d52/config.json):
  772 bytes, SHA256 `11179bdfd48394977f7fe6177b3a87d9c2c6fa2a67a4b3a7376229ca407f0376`.
  Fixed x2 / window8 / embed180 / six stages of six layers / six heads /
  MLP ratio2 / patch1 / GELU / epsilon1e-5 / `1conv` / `pixelshuffle` / img_range1.
- [HF inference source](https://github.com/huggingface/transformers/blob/9417c924af539be5f941c8a709a96b60dfe29eb3/src/transformers/models/swin2sr/modeling_swin2sr.py),
  blob `cd58b70650586582458ee03e2254df58b85c9ade`, Apache-2.0.
  Copyright and license accompany the adaptation as `swin2sr_NOTICE.txt` and
  `swin2sr_LICENSE.txt`.
- [HF conversion source](https://github.com/huggingface/transformers/blob/9417c924af539be5f941c8a709a96b60dfe29eb3/src/transformers/models/swin2sr/convert_swin2sr_original_to_pytorch.py),
  blob `6884bf0afc0cded4da5376e91e61696805343fd3`.
  This implementation does **not** run conversion or fetch remote Python.
- [Author source](https://github.com/mv-lab/swin2sr/tree/6f25d7689813f7dd12c5a212b638066fa71bc9e6)
  is Apache-2.0, but this graph follows the actual converted HF checkpoint,
  including its learned patch-projection weights rather than assuming identity.

## Exact checkpoint format and admission

The file is **`model.safetensors`**, not pickle or `pytorch_model.bin`.
Official LFS metadata pins 48,460,660 bytes and SHA256
`a515955815ab6dba3a9331d8c75db13a5166a5ffbcebf1a95ab676a5656ac4fb`.
Only bounded HTTP206 header research was performed; **the full model was not
downloaded, installed, deserialized, or executed during source development**.
The little-endian header is 94,368 bytes, plus its 8-byte length prefix. Their
combined SHA256 is
`6e72a861509a89f98ed23a506c791068c6638d58782dee73a72f892201c96888`.
The inspected header declares 724 F32 tensors totaling 48,366,284 payload bytes.
This is metadata/key evidence, not numeric-weight or inference validation.

`build_model(torch, checkpoint_bytes: bytes)` in `swin2sr_network.py` takes
already acquired immutable bytes, repeats full artifact hash admission, and
returns a frozen `torch.nn.Module` with `scale = 2`. It never reopens a path.
`swin2sr_loader.py` accepts only this exact hash/header, rejects duplicate JSON
keys, validates all expected names/shapes/types/offsets and contiguous complete
payload coverage, then uses owned bytearrays and `torch.frombuffer(...).clone()`
for little-endian F32 values. It rejects nonfinite values. No pickle,
`torch.load`, safetensors package, Transformers, dynamic import, downloaded code,
installation, network access, or untrusted config execution is involved.
`expected_shapes()` explicitly defines all HF keys; the graph uses these keys
directly, including distinct query/key/value (key has no bias), seven learned
1x1 patch projections, and the final pixelshuffle layers.

## Inference semantics and bounded tiling

- CPU float32, N=1, 3-channel **encoded RGB [0,1]**, `eval`, and inference/no-grad
  context only. Output is encoded RGB x2, **not clamped inside the graph**.
  Canonical linear RGB transfer and global output resampling remain caller-owned.
- Fixed RGB mean `(0.4488, 0.4371, 0.4040)` and image range1.
- Caller supplies dimensions >=16, multiples of8, at most1,048,576 input pixels
  per model window. Network does no hidden tile padding.
- Global right/bottom reflection padding is `(8 - dimension % 8) % 8`:
  **zero** extra pixels when aligned, not an extra full window. Apply once to
  the logical source, not separately at internal tile edges; tile origins must
  preserve global phase8. Crop padded output using the caller's global extent.
- HF v4.28 unaligned model input has a pre-padding dimension/unembed discrepancy;
  pre-aligned windows avoid it rather than silently adopting the bad reshape.
- Shifted layers use a4-pixel cyclic shift, relative cosine attention and
  continuous positional bias. The pinned HF code adds the shift mask twice;
  this adaptation deliberately preserves that (-200 total), not author-code
  single-mask behavior. Numerical equivalence still needs execution evidence.
- Conservative interior source-pixel dependency radius is **263**: 36 attention
  layers ×7, plus shallow convolution1 + six stage convolutions6 + body1 +
  pre-upsample1 + upsample convolution1 + ceil(final x2-grid convolution radius
  1 / 2)=1. Patch projections, norms and MLPs are pointwise. Phase8 halo264
  covers this bound; a profile may use272 as extra conservative margin.
  This protects retained **interior** cores, not true image borders. The finite
  -200 shift mask is not negative infinity: nonzero cyclic leakage can couple
  true global image borders to the opposite image edge. A border tile wraps to
  its own opposite edge instead, so no local halo proves whole-frame parity at
  those borders. **Initial exact-source profile must therefore use a single
  bounded full-frame window and reject larger images**, not silently approximate
  them with independent tiles. The integrated profile admits16..1024pixels per
  side and one full-frame model window; OS memory/time ceilings may still reject
  an admitted size, and no performance acceptance is claimed. Halo264/272 alone
  does not authorize exact tiled product availability. Full-frame vs tiled
  numeric parity, edge appearance, runtime and memory all remain UNRUN.
  Halo32 is insufficient even for the interior bound.

## Execution/acceptance ledger

Source and official metadata only. No model download, package install, model
load, inference, test, build, typecheck, image-quality evaluation, or performance
benchmark was run. Source compilation/import was not used for validation.
Static Python AST parsing may check syntax but is not a test pass.

Required later acceptance (all UNRUN):
1. Strict-loader wrong size/hash/header, duplicate key, shape/offset overlap,
   missing/extra tensor and nonfinite rejection fixtures; never pickle fallback.
2. Full admitted checkpoint construction and exact724 key use; no random tensors
   replacing missing learned weights; CPU/no-grad contracts and memory ceilings.
3. Against pinned HF inference: aligned16/64/128 inputs, shifted mask and learned
   patch projection parity, primary colors/ramp/checkerboard/portrait crops.
4. Whole-frame versus global phase8 tiled output, halo>=264, nonaligned source
   global reflection, corners, seams and final global crop/downsample.
5. Real wedding-image skin/fabric/hair detail, hallucination/artifact review,
   cancellation, timeout/resource failures and actual CPU/RSS/latency benchmarks.

Source integration, safe-artifact admission, successful build, real-device
quality, performance, and overall product completion are separate milestones.
