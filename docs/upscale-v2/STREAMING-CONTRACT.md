# Native-sized float reconstruction: authored reference, admission UNRUN

This is a LumaRetouch local policy, not a claim about a proprietary AI超清
algorithm or byte identity with RealESRGANer's integer-first helper.

## Pipeline and full-image identity

The caller freezes the exact current creative/source raster and separately
binds its document, asset, graph, revision and ownership token. This module
accepts only immutable little-endian linear sRGB D65 premultiplied RGBA-f32
bytes whose entire source has alpha=1, finite RGB in [0,1], matching dimensions
and SHA256. Minimum width/height is 2. The existing 100 MP / 1.6 GB single-asset
limits remain maximum type bounds, not processability promises.

Validation scans 1 MiB views with cancellation between chunks. It creates no
converted whole-image raster. The pure Python scan is an unmeasured reference,
not a responsiveness/performance claim. RGB16 sources must have been truly
decoded and color-managed by the existing full-source owner before this point.

Each tile copies RGB to a float32 NCHW buffer, converts linear RGB to encoded
sRGB with the standard piecewise transfer, and invokes the strict-loaded graph.
No divide by 255, uint8/uint16 conversion, BGR flip, ImageNet normalization,
negative/HDR clipping or alpha reconstruction occurs. Generated output is
finite-checked, dimension/device-checked and explicitly clamped to [0,1].
Statistics retain pre-clamp extrema and component counts.

The generated encoded-sRGB raster is conceptually filtered at native dimensions
with the exact global filter below. A second explicit generated-only clamp
handles negative-lobe filter overshoot. Its separate statistics are recorded.
Inverse sRGB transfer returns linear float32 RGB; result alpha is 1. The source
is never mutated. Returning a raw candidate is not blending regional settings
or performing the owning layer/history Apply.

## Global phase, boundaries and finite support

- Upstream topology is pinned separately from local reconstruction policy.
  x2 has input-unshuffle factor 2; every tile origin and input end is even on
  the frozen source's coordinate grid. x4 alignment is 1.
- Pre-pad is fixed at zero. x2 globally reflects only a missing last column/row
  to obtain even dimensions, using original coordinate width-2 / height-2.
  The source dimension floor of 2 makes this reflect operation defined.
  Artificial tile edges are not independently reflected or treated as true
  image edges; model padding there is isolated by the explicit neural halo.
- Generated coordinates are absolute: tile local (u,v) corresponds to global
  `(tile.x0*scale+u, tile.y0*scale+v)`. Only original width*scale and height*scale
  are eligible downsample samples. Global mod-padded output is cropped logically
  by these sample limits before reconstruction.
- Native sample i has scaled-image center `(i+0.5)*scale-0.5`. Lanczos support
  uses `sinc(t)*sinc(t/3)` for `abs(t)<3`, where t is distance divided by scale.
  This is antialias widening, not just a fixed six high-resolution-pixel kernel.
- Binary64 coefficients are normalized and then converted once to float32.
  Samples are ordered by ascending original integer index, including repeated
  edge-clamped samples. The implementation does horizontal then vertical
  float32 multiply/add accumulation; no per-tile target-size interpolation.
- Sample indices outside the whole *original* scaled image clamp to its edge.
  For each native core, all needed global filter taps are within an extra
  3 source pixels. Its model window has that filter margin plus the neural halo,
  aligned outward to the unshuffle grid. The implementation verifies that every
  tap is actually in the generated tile before sampling.

This finite-support argument establishes intended coordinate/support coverage,
not numerical runtime acceptance. It also does NOT establish that a chosen
neural halo captures a 23-RRDB receptive field or meets portrait/seam thresholds.
Full-frame/tiled comparisons with actual admitted weights, odd dimensions,
true edges, phase shifts, hair, text and fine structure remain mandatory.
No overlap-monotonicity or byte-exact model-equivalence guarantee is made.

## Working-set accounting without a full 4x output

The reference holds only one generated scaled tile at a time. Downsampling
uses a view of the required vertical support strip, a horizontal filtered
temporary, and one native core. Index-select, multiply, transfer and float
conversion intermediates are real allocations, not counted as free views.
There is no full scaled image or scaled weight canvas, and no independent
per-tile resizing that loses cross-core filter support.

The immutable full source stays resident. A native-size RGBA-f32 bytearray is
staged and later copied to immutable bytes. Their possible simultaneous payload
is 48*N bytes for N original pixels. For 24 MP that is 1,152,000,000 bytes,
before the caller's original encoded file, current assets/history, capture,
model/checkpoint, tile buffers, allocator cache, runtime and serialization.
This is a lower-bound accounting, not a peak-RAM promise.

For comparison only, a full 24 MP generated RGB-f32 image at x4 would be
4,608,000,000 bytes; x2 would be 1,152,000,000 bytes. The reference does not
allocate these buffers. The planner exposes these counterfactual sizes to make
that architectural difference visible instead of hiding it behind “tiled.”

Planner `maximum_input_tile_pixels` is an outward-aligned geometry upper bound;
`maximum_generated_tile_bytes` is that pixel bound times scale squared times
12. `model_parameter_bytes` counts one f32 tensor set only.
`device_payload_terms_at_tile_bound` adds one model, RGB input and scaled output
at the geometric tile bound. It excludes model activation/workspace/resample
buffers and is intentionally neither a complete peak estimate nor a budget
bound. A clipped edge tile may be smaller than the geometric bound.
On CPU those tensors consume host RAM instead, so the device number must not be
misread as the complete CPU total. Checkpoint deserialization and strict network
copy can temporarily retain additional tensor sets as well.

There is no approved resource profile or reservation implementation. Peak host
and device bytes are null; `memory_admitted=false`. Production must reserve
existing live host storage, all deterministic staging/copies and a reviewed
runtime-specific measured/conservative scratch envelope before processing.
It must reject inadequate budgets rather than raise existing asset/store caps,
reduce source precision, silently shrink the source, or switch device/dtype.
Thus the private reference is not a functioning production streaming executor.

## Cancellation, failure and receipts

Cancellation raises between full-source scan/hash chunks, tiles, device input,
model calls, every filter tap group, CPU transfer, native row writes, result
hash chunks and final immutable copy. The kernel and final full bytes copy are
not interruptible internally. Final copy cost is explicitly charged.
Any tile error/nonfinite output/OOM/cancellation exits without returning the
partially populated native raster. No failure tile is replaced with source,
black, Lanczos, an old preview or a false successful no-op.

The private result deliberately says unadmitted reference candidate. Raw model
statistics include halo and global mod-pad computations and may count duplicated
source locations across tiles; they are not unique final-image statistics.
Native post-filter statistics count disjoint output cores exactly once.
No measured peak allocation, model SHA, runtime attestation, source owner token,
semantic-mask receipt or UI success is fabricated. Production must add and
validate these facts in the parent-owned operation receipt before acceptance.
