# Reviewed eye-bag protection blend

**AUTHORED / UNRUN.** Original GPL-3.0-or-later Rust source with no external
crates, models, downloaded assets, new image decoder or copied solver. No build,
compiler, test runner, product imports, inference or image processing was run.

This is the narrow numeric blend for the proposed `lnx.eye_bags.v2` operation
and reference `LNX-REF-PC-32464-C-e5fac5fdcf`. It neither identifies aegyo-sal
nor removes bags by itself. The host must independently prepare a correction
from the exact repaired effective source and retain an independently reviewed,
source-owned protection mask. Existing eye-light visibility masks are not ridge
evidence. No automatic anatomy, official algorithm parity, default calibration,
photographic acceptance or final-render bit-equivalence is claimed.

## Numerical contract

The safe Rust entry and C ABI accept float32 encoded-working-sRGB SDR RGB for
the source and corrected source, float32 scalar protection coverage per pixel,
and a finite `preserve` scalar, all in `[0,1]`. The corrected input must contain
only this operation's bag edit, not aggregated independent eye controls.

For each pixel let `keep = preserve * protection`, evaluated in f64. The result
is `source + (corrected - source) * (1 - keep)`, evaluated in f64 and returned as
f32. This is an encoded-space opacity blend, not a linear-light relighting model.
No clamp, gamut repair, image resampling or color conversion occurs.

- `keep == 1` copies source channel bits exactly.
- Numerically equal source/corrected channels copy source bits exactly, including
  source signed zero. A blend that rounds to no numerical change does the same.
- `keep == 0` returns corrected channel bits where there is a nonzero correction.
- Fractional coverage blends, rather than promising exact protection.
- Every source/corrected/protection value is checked even for full protection,
  no-op or zero preservation. Nonfinite, HDR and out-of-range input is refused.
- Empty or invalid dimensions/lengths are refused, not inferred or truncated.

Exact retention is local to this source-domain operation. Other effects,
subsequent common geometry/interpolation and export encoding can change the
displayed/output pixels. The native boundary cannot validate source ownership,
mask provenance, anatomy, or whether every processed eye was independently
reviewed. Those remain mandatory host responsibilities.

## ABI, resources and publication

Library name: `liblrt_eye_bag_preserve.so`. ABI query:
`lrt_eye_bag_preserve_abi() == 1`. Entry:
`lrt_eye_bag_preserve_apply_v1`; the header gives the exact argument order.
All lengths count float elements, not bytes. Read-only inputs may overlap each
other. Output must be an exclusive live allocation overlapping no input. Caller
must keep buffers and callback/context alive and immutable until the call ends.

The bound is 32,000,000 pixels and 65,536 per dimension. Native private staging
needs at most 12 bytes/pixel. Total numeric buffers are 52 bytes/pixel: 12 source,
12 corrected, 4 protection, 12 output and 12 staging. The conservative core limit
is 3 GiB for these buffers. These are admission limits, not measured resource or
latency promises. The bridge additionally admits any snapshots/copies, and the
host accounts for mask rasterization, other effects and retained source arrays.

Status codes are 0 success, 1 ABI, 2 settings, 3 pixel/numeric, 4 cancellation,
5 resource and 6 contained Rust panic. Validation/calculation poll cancellation
at most every 256 pixels. Returned failure leaves output untouched. Publication
is one final non-interruptible copy after the last cancellation poll. The native
core retains no state. No runtime compilation or numerical fallback is provided.

`tests.rs` contains authored-only invariants. All runtime, FFI, build/package,
photographic, source/FaceRef, mask-editor, preview/export and history acceptance
remain UNRUN. This directory does not itself wire any product control.
