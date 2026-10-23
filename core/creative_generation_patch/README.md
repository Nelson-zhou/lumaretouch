# Creative generation patch numerical boundary (ABI 1)

Original GPL-3.0-or-later Rust implementation, no copied model/third-party code and no dependencies. This library does **not** generate images, identify passersby, infer masks, load weights or pretend that deterministic repair is generation. It prepares actual source data for an independently verified optional model and gates actual model output. Model/code/weights licenses and availability belong to the separate runtime pack. All fixtures and the build recipe are **AUTHORED / UNRUN**; no compilation, runtime, numerical, photographic quality or performance acceptance is claimed.

## Exact ABI

C `size_t` corresponds to Rust `usize`, `float` to `f32`, `int32_t` to return codes; callback is nullable `int32_t (*cancel)(void)`. Buffers are contiguous row-major interleaved arrays. Every length is a float count, not bytes. Symbols:

- `uint32_t lrt_creative_generation_patch_abi(void)` returns 1.
- `int32_t lrt_creative_generation_prepare_v1(const float *source, size_t source_len, size_t width, size_t height, const float *selection, size_t selection_len, const float *protection, size_t protection_len, size_t x, size_t y, size_t roi_width, size_t roi_height, float *rgb, size_t rgb_len, float *mask, size_t mask_len, float *eligible, size_t eligible_len, cancel_callback cancel)`.
- `int32_t lrt_creative_generation_fuse_v1(const float *generated, size_t generated_len, const float *eligible, size_t eligible_len, const float *fusion, size_t fusion_len, size_t roi_width, size_t roi_height, float density, float *rgba, size_t rgba_len, cancel_callback cancel)`.

Codes: 0 success, 1 invalid ABI/dimensions/pointers/alias/density, 2 invalid pixel/coverage/unsupported alpha or HDR, 3 cancelled, 4 resource limit, 5 no eligible selection in ROI. On **any** nonzero result discard **all** outputs, even if untouched or partially written. Outputs are not transactionally cleared on failure; only caller-owned unpublished buffers may be used. Publish only after return 0 and provenance verification. Cancellation is polled at entry, during validation, per preparation row, every 4096 fusion pixels and before success; it cannot preempt the synchronous callback itself.

## Prepare contract

Source is full-canvas linear-sRGB D65 **premultiplied RGBA float32**. This slice requires alpha exactly 1 everywhere and finite RGB in [0,1]; consequently premultiplied equals straight RGB. Reject rather than flatten/clip any alpha/HDR source, including outside ROI. Selection and protection are separate full-source-grid float arrays in [0,1], not display/proxy-space masks. Their lengths must both equal width×height. Inputs remain unmodified.

ROI uses integer source-canvas x/y, positive width/height ≤768, contained wholly in the canvas. It is not resized. The top-left ROI maps pixel-for-pixel to a fixed 768×768 patch. Remaining RGB uses nearest ROI-edge replication, not external pixels, scaling or arbitrary black padding. Masks outside ROI are exactly zero.

Outputs:

- `rgb`: 768×768×3 encoded-sRGB float32 HWC [0,1], using the standard piecewise sRGB transfer function with f64 intermediates. It never passes through 8-bit PIL or integer RGB. This avoids intentional RGB16 quantization, but float transfer/model arithmetic is not a bit-exact or lossless promise.
- `mask`: 768×768 float binary, 1=repaint, 0=retain. Eligible iff selection>0 AND protection==0. The runtime must use its independently verified model mask convention.
- `eligible`: 768×768 soft coverage, original selection where eligible, otherwise exactly zero. Any positive protection, including fractional feather values, completely excludes editing. Selection/protection remain independent source assets, not overwritten by this derived array.

Runtime converts HWC to model NCHW Tensor and [0,1] to [-1,1] without PIL8. Real generation must occur in the model runtime. Two candidates require two actual generation results; this kernel never fabricates them. The ROI limit is a truthful bounded first path, not claimed full-image or large-selection generation. Selection outside ROI does not authorize modifications outside it; UI must disclose the effective ROI.

## Fusion contract

`generated` is the actual model's 768×768×3 HWC encoded-sRGB float32 output. Every channel, even in unused padding, must be finite [0,1]; no silent clipping. `eligible` must be the frozen prepare output belonging to the exact source identity, ROI, selection/protection recipe, model job and candidate. `fusion` is separately reviewed editable soft coverage on that same 768 grid, with 0≤fusion≤eligible everywhere. This conservative envelope permits erase/restore only within the original soft selection, never painting into ungenerated or protected extent. Padding eligibility/fusion must be zero. Density is finite [0,1].

Output is 768×768×4 linear-sRGB premultiplied float RGBA, alpha=fusion×density. RGB is decoded actual generated RGB multiplied by alpha. Zero alpha produces exact positive-zero RGBA, including excluded/protected/padded pixels and density=0. Existing creative-layer compositor must translate the patch by source ROI x/y and composite over the immutable source with ordinary source-over. This module neither substitutes the base nor merges model output outside the gated extent. Effective full-size project output and return-to-retouch remain integration responsibilities.

## Memory, ownership and provenance

Prepare supports at most 32,000,000 source pixels, dimensions ≤65,536, and at most 1 GiB of referenced buffers (6 source floats/pixel plus 5 patch floats/pixel). A 24MP source fits this numerical boundary, but this is not an end-to-end memory/performance claim. Fuse has fixed 9×768² floats referenced, approximately 20.25 MiB. No heap allocation occurs on the production paths. Stack slices/reference arrays are bounded.

Null, unaligned, arithmetic-overflowing and overlapping writable ranges are rejected before slices are created. Read-only inputs may alias each other. Pointer arithmetic cannot prove memory accessibility: the C caller must guarantee valid allocated extents, lifetimes, immutable inputs and exclusive outputs. Callback must not unwind, reenter these operations or mutate referenced memory. Do not pass dangling pointers.

This is a numerical boundary, not an authorization boundary. The caller must hash-bind source/ROI/selection/protection/frozen eligibility, model and candidate identities, preserve original assets, and enforce ownership before invoking fusion. A forged caller eligibility array is not detectable here. Hashes, atomic publication, history, persistence, cancellation fencing and model availability are implemented elsewhere. Unsupported alpha/HDR, larger ROI, model semantic failures and model quality remain explicit limitations.

Effective selection outside the supplied ROI is rejected, even if all values are
otherwise valid. The context crop cannot silently omit an intended removal. Source
mask origin/review is a controller responsibility, not proven by array dimensions.
