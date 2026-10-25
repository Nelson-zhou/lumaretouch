# Proposed optional AI clarity backend contract

Design only. No implementation, compatible model pack, numerical test or
photographic acceptance is claimed. This document separates verified upstream
behavior from new LumaRetouch policy. Any new port names below are proposals.

## 1. Public operation and provenance

Proposed operation: ai_clarity, schema lrt.ai-clarity.v1,
mode restore_native_dimensions. Its result has the frozen source's exact width
and height; network scale and presentation/output size are separate fields.
No connection to export-only scale or sharpen is implied.

A request must bind all of:
- Source document ID, effective immutable canonical asset ID/hash, width/height,
  color/alpha encoding, complete edited-source recipe revision, creative document
  revision and ownership token. Original pathname/file hash is retained only as
  original provenance, not substituted for a returned composite's pixel identity.
- Reviewed model ID, code commit/installed distribution hashes, checkpoint
  SHA256/length, architecture, preprocessing version and backend device/dtype.
- Whole/face/body/background local strength settings and the versioned combination
  rule; source-bound coverage/protection assets and producer/review evidence.
- Pixel/byte/work budget, tile geometry/global alignment policy, result downsample
  kernel/version, cancellation token and unique request/job ID.

Result receipt: the exact frozen input and settings hashes; actual model/device/
dtype; actual tile count, dimensions and pad/crop policy; generated range/clipping
statistics; cancellation/completion state; original-size restored asset hash;
region/fusion version; actual allocated/spooled resources when measurable.
Never label a missing-model/fallback result AI. Missing backend preserves saved
intent and previously owned result bytes, not a fake successful no-op.

## 2. Source and canonical numeric boundary

Reuse creative assets: little-endian float32, linear sRGB D65, premultiplied RGBA.
Existing asset bounds permit finite alpha [0,1] and signed/HDR unassociated
channels up to magnitude 65504; **the model proposal does not inherit that range**.

Initial model admission is deliberately narrower:
1. Validate the entire frozen source before inference: finite channels, alpha
   exactly one everywhere and RGB within [0,1]. Reject partially transparent,
   fully transparent, negative or >1 input, including pixels outside selected
   regions. Do not flatten onto black/white, discard alpha, tone-map, clip source,
   or infer SDR status from a proxy. Keep the original/creative asset unchanged.
2. Full original RGB8/RGB16 decode must preserve true bit depth and ICC conversion
   using the existing full-source capture; no camera JPEG, load_rgb proxy, display
   buffer or uint8 analysis input may become the restoration source. For a
   returned image use its exact immutable canonical asset, never reopen the
   original pathname as a shortcut. For a current creative graph render the
   frozen current graph, not an earlier base layer.
3. Convert admitted linear RGB to display-encoded working sRGB in float32, using
   a versioned standard transfer function. For L in [0,1], E=12.92L at
   L<=0.0031308, otherwise E=1.055*L^(1/2.4)-0.055. No ICC metadata is guessed at
   this stage and no division by 255/65535 is applied to normalized float input.
4. Feed contiguous RGB NCHW [1,3,H,W] float32 [0,1] to the exact pinned architecture.
   Normalize neither by ImageNet statistics nor to [-1,1]. Model input transfer
   is distinct from the canonical source buffer and retained in its receipt.
5. After genuine inference, reject nonfinite output and unsupported dimensions.
   Record pre-clamp range and clipped component count. The upstream inference
   semantics clamp **generated output** to [0,1]; doing the same explicitly is
   not permission to clamp source. Keep generated data float32, not uint8/uint16.
6. To restore native dimensions, apply a fixed, globally aligned antialiased
   downsample to the generated encoded-sRGB float output, then inverse-transfer
   to canonical linear RGB. Record any generated-only overshoot clamp after a
   negative-lobe filter. Kernel, border policy, sample centers and arithmetic
   order must be fixed in the backend version before implementation acceptance.
   This float-preserving policy differs from the demo helper's integer-first
   post-resize; do not call the resulting pixels byte-identical to that helper.
7. Blend into the exact canonical source only using validated coverage; alpha
   remains exactly one. Pixels with effective coverage zero must copy source
   bytes, not round-trip through model transfer/resize. All strengths zero
   returns the exact source without pack import, allocation or inference.

Transparency/HDR support is a future, separate contract. Merely keeping source
alpha while processing unpremultiplied colors does not validate the model on
transparent edges; the upstream default can even run the model on alpha, which
changes geometry. Never advertise HDR restoration because the outer float type
can store HDR. Existing opaque-SDR return/export guards remain in effect.

## 3. What the official inference actually does

Sources are pinned in PROVENANCE.json, principally inference_realesrgan.py,
realesrgan/utils.py and BasicSR basicsr/archs/rrdbnet_arch.py.

- General x4plus: RRDBNet, 3 input/output channels, 64 features, 23 RRDB blocks,
  growth 32, scale=4. x2plus uses the same listed sizes but scale=2 and input
  pixel-unshuffle by 2; conv_first therefore takes 12 channels. Do not load x4
  weights into a scale=2 or scale=1 constructor.
- Official checkpoint selection prefers params_ema, otherwise params, with strict
  state loading. The demo's torch.load does not explicitly request weights_only.
  A future adapter must use a reviewed safe tensor-only loading route, explicit
  weights_only=True where supported, exact byte/shape/key admission and no
  untrusted class allowlisting or pickle fallback. Matching bytes alone do not
  make arbitrary checkpoint execution safe.
- RealESRGANer accepts a URL and may download automatically; the CLI downloads
  missing model files and can download GFPGAN when face enhancement is selected.
  Neither path is suitable as an unrestricted product entry point. The proposed
  pack is offline/local-only; opening a file, status probing and inference never
  fetch a model or run an installer. No face_enhance in this first backend.
- enhance() is an OpenCV image convenience interface, not the canonical float
  interface. It converts BGR to RGB, infers 16-bit scaling from max(image)>256,
  otherwise divides by 255, processes, clamps, converts back, rounds to integer
  output and only then applies INTER_LANCZOS4 for outscale. Passing normalized
  float32 into this method silently divides it by 255. A dark uint16 input whose
  maximum is <=256 is also not correctly represented by that value heuristic.
  Never route the product's float or true RGB16 buffers through it unchanged.
- Helper pre_pad default is 10, while the CLI passes default pre_pad=0. Padding
  is reflection on right/bottom; x2 requires mod-padding to divisibility by two.
  Both padding layers are cropped away at native network scale afterwards.
  Degenerate images that cannot satisfy reflect-padding must fail or use an
  explicitly tested separate contract, not accidentally switch padding modes.
- The helper defaults half=False, but the CLI passes half=not fp32 and thus
  normally selects fp16. The upstream FAQ explicitly calls for fp32 on CPU when
  half operators are unavailable. Initial LumaRetouch proposal is explicit fp32
  on a declared CPU/CUDA/ROCm device only after validation; no silent device or
  precision fallback and no claim that it works on all current variants.
- general-x4v3 uses SRVGGNetCompact with 32 convolutions, not RRDBNet. Its denoise
  setting interpolates two separate checkpoints. That needs two admitted hashes
  and is not a face/body/background mask or a universal x4plus strength slider.

Minimal optional dependency strategy: expose a narrow architecture/forward port,
not the upstream training package or full CLI. Direct use of the official class
may import BasicSR utilities, torchvision and other modules. Vendoring a small
licensed inference-only subset could reduce that surface but is a separate
implementation/review decision and must retain exact attribution, source pins,
modification notice and compatibility fixtures. No such subset exists here.

## 4. Region strengths are a missing semantic dependency

Official meanings are whole image, face, body and background, not face skin,
body skin, background and sharpen. Existing semantic_sources.py exposes six-class
portrait probabilities; its own documentation says portrait_parts is not a
complete person silhouette and others is not background. face_skin excludes
important facial details and body_skin excludes clothing. Neither may be quietly
renamed to satisfy the requirement. A face bounding box is also not a reviewed
semantic face mask.

Required implementation choice:
- Genuine source-bound segmentation/face-region evidence with explicit face,
  body and background definitions, or user-reviewed manually delineated regions
  visibly labelled manual. Unknown/uncertain pixels remain explicit, not silently
  assigned to background. Manual-only support is a declared partial scope, not
  completed automatic region behavior.
- Validate dimension/source/revision/model/transform provenance and all numeric
  masks. Region inference may use its declared proxy only if the mask resampling
  is documented and reviewed; restoration always uses full source detail.
- Freeze a local strength rule, since the vendor does not disclose one. A simple
  candidate is independent nonnegative [0,1] strengths with effective coverage
  max(g, f*face, b*body, k*background), capped by any explicit protection. This
  is a LumaRetouch proposal: global is a lower bound, so a smaller regional value
  does not weaken it. Its UI must explain that behavior or choose a different
  explicit rule before coding. No formula or numeric range is claimed official.
- Fuse one genuine restored result with the source using that coverage. Region
  controls do not require fake separate model invocations or separate neural
  face reconstruction. User review must catch invented facial/textural details.

No unknown mask becomes an all-ones/all-zero success. A valid empty region is
distinct from unavailable region evidence. Batch recalculates/reviews each
target's own regions; it never copies another photo's masks or restored pixels.

## 5. Tiling, resources and cancellation

Upstream tile_process uses tile_pad context and copies the central tile area to
a full-sized device output. It does not blend overlaps. Its default halo 10 is
a heuristic, not proof of exact whole-image equivalence for a deep RRDB network.
The existing local cross-fade implementation is a different algorithm; its
random tiny-network monotonic-overlap fixture proves neither upstream equivalence
nor enough context for real portrait details.

The official helper and current local code both allocate full scaled output on
the device. Consequently "tiled" does not mean peak memory depends only on tile:
24 MP × RGB-f32 = 288,000,000 bytes; a 2× RGB output is 1,152,000,000 bytes, and
a 4× RGB output is 4,608,000,000 bytes, before model/features/input/workspaces.
The local implementation adds a full output-sized scalar weight plane as well.
One canonical source RGBA-f32 is 384,000,000 bytes. These are lower-bound
arithmetic calculations, not measured allocator/VRAM results.

Proposed runtime must:
1. Admit exact source, staged result, coverage, model, feature/workspace and
   spool/serialization bytes before work. Respect existing 100 MP asset,
   1.6 GB single-asset, 2 GB asset-store and host available-memory budgets; none
   is a promise that any 100 MP image is processable. Do not raise them to make
   model output fit. Native-size restoration can still have oversized internals.
2. Use immutable full-source coordinates. For x2, align tile origins and padded
   extents to the global 2-pixel unshuffle grid and retain the same global
   right/bottom mod-padding. Avoid independently padding each tile as an image.
3. Either explicitly reject insufficient memory for full scaled output, or
   implement a real bounded GPU-output stream to CPU/spool with the complete
   context needed by the final global downsample. Independent per-tile resize
   is not equivalent. Storage and CPU copies count too.
4. Pin a validated tile/halo/downsample policy to the backend; insufficient
   context or lack of validation is a capability blocker. Compare against actual
   full-frame inference on admissible small inputs, including borders/odd sizes,
   phase shifts and region boundaries. No generic byte-exact claim and no
   unproved promise that increased overlap monotonically improves quality.
5. Poll cancellation between capture/hash/padding steps, model tiles, transfer,
   resampling and fusion. A running model kernel or weight load may not be
   interruptible; disclose that granularity. Cancel/OOM/runtime errors discard
   the staged result and leave the current graph/history untouched.
6. Fail the whole operation on a tile error. Upstream demo tile_process catches
   RuntimeError and prints it before continuing; do not inherit this behavior
   and risk stale/undefined tile output. Never fill failed tiles with black,
   source pixels, Lanczos or an old preview and report AI completion.

Until the exact offline pack, architecture, resource strategy, semantic masks,
numeric fixtures and photo quality are established, advertise unavailable with
specific reasons. Do not solve the blockers by relabelling deterministic output.
