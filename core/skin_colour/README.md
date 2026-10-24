# Face-skin temperature and tint pixel core

Status: **AUTHORED / UNRUN**. Original source, bridge, build hook and authored
fixtures only. No project imports, builds, tests, compiler/typechecker runs,
inference, benchmarks or downloads were used. Static source inspection does not
establish compiled correctness, performance, photographic quality or completion
of the broader skin-retouching feature. Local Qoder execution and visual review
remain required after separate authorization.

## Boundary and source ownership

`skin_colour_native.apply(rgb, coverage, temperature, tint, *, cancelled=...)`
returns owned contiguous float32 encoded working-sRGB RGB. Input is H×W×3
float32, unpremultiplied, finite SDR [0,1]; coverage is matching H×W float32 in
[0,1]. Reject alpha, HDR, wrong dtypes/shapes and all nonfinite values, including
neutral controls and unsupported pixels. No implicit clipping/conversion.

This is only a per-pixel colour operator. The host must authenticate photograph,
revision, face, geometry and transform, and supply real face-skin support with
semantic exclusions/protection. An oval/rectangle alone is not evidence of skin.
The kernel cannot verify array provenance or colour-space labels. It cannot
detect occlusion, eyes, lips, brows, hair, glasses, clothing or background.
Positive coverage is supplied permission to affect a pixel, not a calibrated
skin probability. Source/coverage may not mutate while the bridge copies them.
Native processing uses independent immutable snapshots, not aliases to callers.
Errors and cancellation never publish partial output through Python.

This is not skin whitening, body adjustment, automatic skin matching, smoothing,
texture synthesis, white balance, a segmentation model or an alias for those
controls. No neighbouring pixel is read. Always rerender from the original
source snapshot, not the prior result, to avoid accumulating edits.

## Original bounded correction

1. Validate all inputs before any output writes. Decode the standard sRGB
   transfer into f64 linear light and convert by its D65-primary matrix to XYZ.
2. Compute CIELAB relative to the same D65 white, x=0.3127 and y=0.3290. Preserve
   original L* and original XYZ Y. This deliberately is **not CSS lab()**, which
   uses D50 adaptation, and must not share its reference-white constants blindly.
3. Both controls require finite [-1,1]. Temperature shifts b* by 8×temperature:
   negative moves toward blue/cool, positive toward yellow/warm. Tint shifts a*
   by 6×tint: negative moves toward green, positive toward magenta. These scales
   are original bounded product choices, not Kelvin, Adobe values, perceptual
   calibration, recovered PixCake parameters or equivalent appearance claims.
4. Try the corrected Lab colour at original Y. If outside linear-sRGB gamut,
   scale both corrected a* and b* together toward zero, at fixed L*, with exactly
   24 bisection steps. Retain only strictly in-gamut candidates and initialize
   the feasible neutral anchor to [original Y; 3]. Never clip RGB channels, even
   for numerical repair. Black and white bypass correction as exact source
   copies, because they have no chromatic headroom at unchanged L*.
5. Blend corrected and original RGB in **linear light** using coverage, then
   encode to float32 sRGB. Original Y/L* and its fine texture are retained up to
   floating-point conversion; there is no averaging or spatial smoothing.
   Neutral controls and zero coverage take direct bit-copy branches, preserving
   signed zero. Output is checked finite and in gamut, and Python independently
   checks the exact neutral/outside-support invariant before returning it.

Common scaling preserves the requested numerical Lab hue angle, not a guarantee
of perfectly constant perceived hue. CIELAB is not perfectly uniform and its
gamut paths can be nonconvex; conservative chroma reduction can desaturate more
than desired near boundaries. The bounded search guarantees a feasible retained
candidate, not globally maximal chroma or CSS gamut-mapping conformance. Strong
saturation, near-black/highlight skin, coloured light and makeup require real
image review. No measured naturalness or calibrated ±8/±6 claims are made.

## FFI and resource contract

ABI function `lrt_skin_colour_abi()` returns 1. C entry point:

    int32_t lrt_skin_colour_apply_v1(
        const float *source, size_t source_len,
        const float *coverage, size_t coverage_len,
        size_t width, size_t height, float temperature, float tint,
        float *output, size_t output_len,
        int32_t (*cancel)(void *), void *context);

Lengths are float32 element counts, not bytes. No source/output overlap or
coverage/output overlap is permitted. Native checks dimensions, checked sizes,
alignment, address addition and overlap before constructing slices. Foreign
callers must still guarantee live allocations, ownership, immutability and
callback lifetime. Callback must not unwind, reenter or mutate these buffers.

Status: 0 success, 1 ABI/buffer/dimension error, 2 settings error, 3 invalid
pixels, 4 cancelled, 5 resource limit, 6 contained Rust panic. Every nonzero
status means discard **all** output. `catch_unwind` with unwind-enabled builds
contains Rust panics, not invalid foreign pointers, callback faults or aborts.
Python catches callback exceptions inside the callback, returns cancellation,
then re-raises the original exception outside C. It validates results before
publication and never returns a partial image.

Dimensions are 1..65536, at most 64 million pixels. Native worst-case admission
counts 25 gamut evaluations per pixel, at most 1.6 billion; seven float32 buffer
elements per pixel are checked against 2 GiB. Native allocates no heap/image
scratch. These are safety ceilings, not performance promises. Python includes
caller arrays, two independent snapshots and output at 44 B/pixel plus 8 MiB
allowance, under a 3 GiB limit. Its additional allocation estimate is 28 B/pixel
plus allowance and uses the existing fail-closed CPU/cgroup budget helper.
Concurrent system allocation can still fail; an estimate is not an OOM promise.

Native polls cancellation before validation, every 256 pixels in validation and
rendering, and after the last pixel. At most 6400 gamut evaluations lie between
render polls. Python copies and validates in blocks of at most 4096 pixels with
polls before each block and before publication. A single allocation or library
load cannot be interrupted inside that system call.

`available()` loads and checks actual symbols/ABI. Missing or unloadable native
code is explicit unavailability, including for neutral requests; there is no
Python approximation or runtime compilation. The separately authorized build
hook is `sh packaging/build-skin-colour.sh`; it uses rustc without dependencies
and atomically replaces only its completed output library.

## Primary research and licensing

Read on 2026-10-23. No external source code, model, image or dataset is copied or
added. Standard mathematical relations are independently expressed in original
Rust, under the repository's GPL-3.0-or-later convention and existing LICENSE.

- [CIE ISO/CIE 11664-4:2019 public description](https://cie.co.at/publications/colorimetry-part-4-cie-1976-lab-colour-space-1)
  identifies CIELAB lightness, chroma and hue coordinates and reverse conversion.
  Only its public description was read, not a purchased full standard; no CIE
  publication text is redistributed and no certification is claimed.
- [W3C CSS Color 4](https://www.w3.org/TR/css-color-4/), especially sRGB,
  colour-space conversion and 14.1.3–14.1.6, supports the mathematical background
  and explicitly documents chroma-reduction limitations. Its normative CSS
  gamut algorithms and sample implementations are **not** copied or implemented
  here. D65-relative Lab in this operator differs from CSS D50 Lab.
- [W3C document license](https://www.w3.org/copyright/document-license-2023/)
  and [software/document license](https://www.w3.org/copyright/software-license-2023/)
  were read. Document and marked code-component terms are distinct. This change
  adds links and original engineering prose, not redistributed specification
  prose or adapted W3C sample code.

## Unrun validation manifest

`tests.rs` authors 13 native cases: exact no-ops/signed zeros, black/white,
independent axis direction/scale, linear-light coverage, saturated/near-endpoint
gamut and L*, common chroma factor, texture/no-neighbour dependence, determinism,
invalid data/settings, dimensions/resources/lengths, staged cancellation,
invalid FFI pointers/aliasing and ABI/callback status.

`engine/tests/test_skin_colour_native_unrun.py` adds bridge fixtures and real-ABI
fixtures gated only on a prebuilt binary. Boundary stubs are **not** numerical
proof. All tests remain **UNRUN**; neither source checks nor fixture presence
count as pass results. Future acceptance must cover real skin diversity, lighting,
occlusions, exclusions, preview/export consistency and memory/cancellation costs.
