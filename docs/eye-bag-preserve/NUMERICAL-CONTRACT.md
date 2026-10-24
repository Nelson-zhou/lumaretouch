# Eye-bag protection numerical boundary, AUTHORED / UNRUN

The original new Rust library is a protection compositor, not a new eye-bag
detector, an anatomical model, or a replacement implementation of the existing
RapidRetouch solver. Its ABI is independent of the versioned portable recipe.

- Recipe: `lnx.eye_bags.v2`, version 2, `amount` and `preserve` in [0,1].
  Neutral amount is zero; preservation defaults to one. Preservation alone
  does not activate a render or require a valid live support/solver.
- Native ABI: `lrt_eye_bag_preserve_abi() == 1`,
  `lrt_eye_bag_preserve_apply_v1`. Inputs are immutable float32 HWC encoded
  working-sRGB source/corrected RGB and float32 coverage. This is an opaque SDR
  contract, not premultiplied alpha, linear-light compositing or HDR.
- The legacy solver supplies the correction from real current source pixels.
  Only independently reviewed eyes and the admitted target-owned skin/geometry
  support can receive that correction. Source vectors are rebuilt for the true
  render grid, not enlarged from a preview bitmap.
- Let source be S, separately corrected RGB be C, mask weight be M and
  preservation be P. The isolated compositor calculates
  `S + (C - S) * (1 - P*M)` with a float64 intermediate and float32 output.
  It copies source bits rather than performing arithmetic at full protection
  or numerical zero delta. With zero protection it copies changed corrected
  channel bits. This does not claim a physical material decomposition.
- Every input sample must be finite and within [0,1], including samples hidden
  by full protection. No clamping fallback is present in this new native code.
- The ABI validates dimensions, lengths, alignment and non-overlapping output
  spans before constructing slices. The caller must still supply genuine live
  allocations; range checks cannot establish foreign pointer validity.
- Output is staged privately and copied only on success. Cancellation is polled
  during validation and computation and immediately before the final copy.
  The final copy is intentionally non-interruptible, not a partial publication.
  This describes the native/bridge API, not end-to-end UI cancellation: the
  current canonical people preparation does not supply a cancellation callback,
  the existing local-mask worker retains its timeout, and legacy OpenCV calls
  cannot be interrupted within an eye solve. Fully interruptible treatment is
  not implemented or claimed by this slice.
- Native bounds are 32 million pixels, 65,536 per dimension, and checked memory
  accounting. Native scratch is 12 bytes/pixel; its stated 52-byte/pixel total
  includes its input/output buffers but not the Python solver, support raster,
  render graph, images, decoder or UI. Host admission must account for those
  separately. These source bounds are not measured performance or 24MP acceptance.
- In the common mixed graph, a later delta can exceed headroom left by earlier
  edits. The existing `people_source_vector` feasibility method attenuates one
  scalar per pixel to fit SDR headroom without individual channel clipping.
  Consequently isolated strength is not a promise of identical final appearance
  under arbitrary other edits. Active invalid/HDR upstream samples refuse.

The protection concerns this new operation before the common geometry warp.
Existing geometry interpolation, other effects and color/output transforms can
alter a displayed pixel even when its source region is protected from this
operation. Neither display PNG review nor authored fixtures prove native-pixel
export parity; those evaluations remain UNRUN.
