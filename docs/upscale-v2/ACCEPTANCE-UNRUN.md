# Required acceptance, none executed

Static AST/JSON parsing establishes syntax/readability only. It does not
establish importability, tensor support, checkpoint compatibility, numeric
correctness, resource safety, performance or product completion.

## Exact architecture and safe-loading fixtures

- Compare the complete 702 tensor names/shapes against the pinned upstream
  constructor for both candidate models. x2 conv_first.weight is (64,12,3,3);
  x4 is (64,3,3,3). Both have 23 blocks, each with three five-convolution dense
  blocks, plus six top-level convolutions. Biases remain present.
- Strictly load the actual admitted official checkpoint through a reviewed safe
  byte loader. The current private constructor does not implement that loader.
  Establish hash/length/file identity before deserialization, then explicitly
  use supported weights_only=True and never retry with pickle or class allowlists.
- With both params_ema and params present, select params_ema. Malformed EMA
  must fail, not fall back. Reject raw/net envelopes, wrong key sets, prefixed
  keys, x4-as-x2, wrong shapes/dtypes, subclasses, nonfinite/sparse/device tensors,
  noncanonical storages and unknown model IDs. No state key rewriting.
- Compare actual forward outputs against the pinned BasicSR graph on small
  admitted inputs. Include x2 channel/phase ordering and both upsampling stages.
  A shape-only random network is not checkpoint or photographic acceptance.
- Verify package imports and capability probing do not import Torch, NumPy,
  BasicSR or torchvision, open a model file, install/download, or change state.
  All public restoration attempts must currently fail before allocation.

## Source, numeric and tile fixtures

- Validate full immutable canonical input. Include exact source SHA mismatch,
  byte length/geometry mismatch, unsupported encoding, mutable/proxy bytes,
  NaN/Inf, alpha 0/partial, negative RGB/HDR values and such pixels outside
  proposed selected regions. Source may never be silently fixed or clipped.
- Test genuine RGB16 import including very dark values <=256 and high-frequency
  ramps through the existing source owner, not the BGR/integer upstream helper.
  No uint8 intermediate or max-value bit-depth guess is allowed.
- Compare transfer functions against independent f32 references at 0,
  0.0031308, 0.04045 and 1 and adjacent representable values; maintain RGB order.
  Preserve separate generated raw clamp and post-Lanczos overshoot statistics.
- Evaluate a small whole-image globally anchored Lanczos reference independently
  of the implementation. Verify every boundary, native sample center, coefficient
  normalization, support radius, repeated clamped sample and reduction order.
- For each actual network scale, compare whole-frame and tiled candidates on
  even/odd sizes, 2-pixel dimension floor, 17x19, 255x257, thin horizontal/vertical
  sources, and non-multiple final cores. Include edge impulses, ramps and checker
  patterns. x2 tile origins/ends must remain globally even.
- Assert the plan's lazy core rectangles cover each native pixel once, model
  extents align globally, all reconstruction taps have generated support, and
  the observed generated tile stays within the reported geometric bound.
- Establish neural halo criteria using real admitted weights and representative
  photographs. Do not assume the filter's 3-pixel margin replaces deep-network
  context. Quality thresholds must be chosen before reporting acceptance.

## Resources, cancellation and production ownership

- Trace allocations for source capture, retained host assets/history, checkpoint
  load/network copy, model activations/workspace, tile encode/clamp/gather/filter,
  CPU transfer, native staging, final immutable copy and result serialization.
  Include CPU and every explicitly supported CUDA/ROCm runtime/device variant.
- Prove no full scaled raster/weight plane or full encoded source is allocated.
  This alone does not prove peak memory fits. Record actual peak host/device
  usage and reviewed budget margins for the exact runtime, tile shape and dtype.
- Implement reservations and a bounded safe loader before activation. Refuse
  insufficient budgets before work. Unknown envelope is unavailable, not zero.
  Never raise asset/store caps, reduce source resolution/precision, silently
  switch backend, or call unmeasured arbitrary halos production-safe.
- Cancel at validation, hash, tile prepare, after model kernel, filter groups,
  host transfer, native row write, final hash and immutable copy. Report actual
  noninterruptible intervals. Inject OOM, wrong dimensions/device, nonfinite
  output and model exceptions; no partial successful candidate may return.
- Parent-owned acceptance must bind result/source/model/runtime/settings/region
  identities, freeze current source rather than original pathname, preserve zero
  effective coverage bytes, and atomically Apply under current document/token.
  Missing semantic regions cannot be substituted by face_skin/body_skin/others.
- Save/reopen/history/return/export/batch/UI are outside this source slice and
  must follow the independent implementation map; no ledger is marked complete.

## Photographic evaluation

Use authorized diverse portraits and full-resolution comparison. Inspect
invented texture or lettering, ringing, plastic skin, identity change, hair,
clothing, motion/defocus blur, compression and low light. Native-size neural
reconstruction is not proof of recovering true lost detail. Report limitations
and compare useful baselines without presenting deterministic sharpening as AI.
