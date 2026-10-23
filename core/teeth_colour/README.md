# Independent teeth brightness and yellow removal

Status: **AUTHORED / UNRUN**. Original source, packaging hook and fixtures only.
No compiler, import, build, test, inference, benchmark or visual acceptance has
been run for this change. The presence of this source is not a finished-feature
claim. Real portrait evaluation, host integration and ABI execution remain gates.

## Scope and ownership

This is a non-generative colour operator, not an AI model, segmentation system,
tooth repair, dental recommendation, mouth replacement or geometry adjustment.
The caller supplies existing, real teeth support for one identified source/face.
The kernel does not infer support from skin colour, a mouth rectangle, landmarks
alone or brightness. It never dilates that support or synthesizes missing teeth.

The host must bind coverage to the exact source identity, selected face, source
revision, transform and raster dimensions before calling. Passing arbitrary
arrays is not evidence of that provenance. Coverage must already incorporate
the allowed support, feathering, protection and local correction density.
Pixels with coverage zero are preserved bit-for-bit. Do not treat the hue gate
as a replacement for a correct mask: orange/yellow objects inside wrong coverage
can still change. Yellow-only does not desaturate red/pink, blue or green hues;
brightness can brighten any covered colour, so its anatomical exclusion depends
on the genuine teeth coverage supplied by the host.

## Method and primary references

- [Adobe's teeth-whitening guide](https://www.adobe.com/uk/creativecloud/photography/discover/how-to-whiten-teeth.html)
  describes a teeth selection converted to an adjustment mask, selective yellow
  saturation reduction and soft mask edges.
- [GIMP's Hue-Saturation documentation](https://docs.gimp.org/2.10/en/gimp-tool-hue-saturation.html)
  distinguishes selected colour ranges from channels and from a master
  adjustment, including overlap between adjacent ranges.

These references motivate a masked, colour-selective workflow only. All code,
the hue gate, gain curve, limits and constants here are original implementation
choices, not copied Adobe/GIMP code, numerical equivalence, research findings or
validated naturalness settings. Sources were read on 2026-10-23.

RGB is **encoded working-sRGB**, float32 H×W×3, finite SDR [0,1]. There is no
transfer conversion inside this operator. Linear RGB, premultiplied RGB, RGBA,
negative values, HDR and other working spaces must not be silently passed as
this format. The host owns colour conversion and alpha policy.

Two independent finite amounts are in [0,1]:

1. Brightness increases HSV value through a common RGB scale, preserving hue
   and saturation rather than mixing the pixel with white. With original value
   V, gain g = 0.35 × brightness × V and headroom h = max(0, 0.965 − V), the
   lift is g × h / (g + h), or zero when either factor is zero. Thus the new
   value cannot exceed max(original V, 0.965). The soft shoulder preserves value
   ordering instead of flattening highlights at a hard clip. Original values
   above 0.965 are not darkened. Original black stays black.
2. Yellow removal lowers only original-HSV saturation. A smooth cubic hue gate
   is 1 from 45° through 75°, transitions over 25°–45° and 75°–95°, and is exactly
   zero elsewhere. The reduction amount is yellow × gate. RGB moves toward
   its original maximum by this fraction, which retains HSV value and hue
   while reducing saturation. A common brightness scale is then applied.

The coverage blends this adjusted pixel with its own original pixel in encoded
RGB. There is no blur, erosion, spatial resampling, colour sampling from adjacent
teeth or global desaturation. Hue/value calculations use f64 intermediates and
return float32; no float16 or integer quantization is used. Two neutral amounts,
zero coverage and unaffected yellow-only hues follow exact-copy branches. Every
input is validated, even when neutral or outside coverage. This means malformed
SDR input is rejected rather than silently passed through or clipped.

The same values are deterministic for a fixed source/coverage/settings. It is
not an iterative operation: preview/export should always start from the same
owned source snapshot rather than accumulating changes on previous results.

## Python integration

`teeth_colour_native.apply(rgb, weight, brightness, yellow, cancelled=...)`
returns an independent, contiguous, writable float32 array with the same RGB
shape. It accepts exact NumPy ndarrays, not dtype conversions or implicit Torch
device copies. NumPy and Torch hosts must call this one bridge; a Torch host
explicitly stages float32 CPU arrays, calls it, and restores the desired device.
Do not implement a second host-side colour formula or silently fall back when
the native library is absent.

Before native reads, the bridge makes independently owned, read-only snapshots
of source and weight, including strided input. The caller must not concurrently
mutate either input during snapshot copying. The return value aliases neither
input; failures never expose a partial output. `available()` loads and validates
the actual ABI and required symbols. There is no runtime build or download.

Admission is limited to 64,000,000 pixels, nonzero dimensions no larger than
65,536, a conservative 3 GiB static working-set cap, and a readable CPU memory
budget for additional allocations. The estimate is 44 bytes/pixel including
caller inputs, snapshots and output, plus 8 MiB scratch allowance. Additional
allocation admission uses 28 bytes/pixel plus that allowance. An estimate is
not an allocation guarantee; allocation failure still propagates. No proxy,
resizing, partial-frame export or precision downgrade is used to evade limits.
An unavailable or ambiguous memory-budget source fails closed.

Cancellation is checked before admission, around snapshot allocations/copies,
at native validation/render intervals of at most 4,096 pixels, and before return.
Python copies are bounded by a 4,096-pixel row group or one maximum-width row.
An individual allocator operation cannot be interrupted. Callback exceptions
are captured in Python, stop the C operation and are then re-raised, rather than
unwinding across a C ABI boundary.

## C ABI 1

`lrt_teeth_colour_abi()` returns 1. `lrt_teeth_colour_apply_v1` accepts these
arguments in order:

1. source float32 pointer, source element count;
2. coverage float32 pointer, coverage element count;
3. width, height (`size_t`);
4. brightness, yellow (`float`);
5. output float32 pointer, output element count;
6. optional `int (*cancel)(void*)`, opaque callback context.

RGB/output lengths must be 3×width×height; coverage length must be width×height.
Lengths count elements, not bytes. Output must not overlap either input. Read-only
input overlap is safe, although the Python bridge creates separate snapshots.
Null, unaligned, overflowing, wrongly sized and output-aliasing ranges are rejected
before slice creation. Pointer checks cannot prove that memory exists or is owned:
the native caller still guarantees live allocations, immutable inputs, exclusive
output access and a callback that does not unwind, reenter or mutate the buffers.

Return codes: 0 success, 1 ABI/pointer/length/dimension/alias failure, 2 invalid
settings, 3 invalid SDR pixels/coverage, 4 cancellation, 5 resource limit,
6 contained Rust panic. Native code allocates no image buffer. Input validation
precedes all output writes; cancellation during rendering can leave partial output.
**Discard all output on every nonzero status**, including cancellation after the
last pixel. The Python bridge enforces this publication rule.

## Packaging and acceptance still required

`packaging/build-teeth-colour.sh` is an authored, unrun explicit release build
hook. It uses the system Rust compiler without external crates and installs a
completed `.so` by replacement only after successful compilation. The Python
loader expects `engine/src/lumaretouch_engine/bin/liblrt_teeth_colour.so`.

Rust fixtures cover independent controls, exact neutrality/coverage exclusion,
non-yellow preservation, hue falloff, feathering, highlight ordering, SDR guards,
resource limits, C pointer rejection and cancellation. Python fixtures cover
immutable snapshots, strict API input, budget refusal, bridge error publication,
callback exceptions and optional real-ABI parity. All are **UNRUN**. Real-native
fixtures explicitly skip when no built library exists; a skip is not acceptance.

Before release, separately authorize and run the build and fixtures, then check
real source-owned masks on varied teeth, gums, lips, reflections and lighting;
preview/export parity; NumPy/Torch host parity; cancellation under real load;
memory use; and source/face/revision rebinding. These tests do not establish
medical suitability, automatic segmentation quality or production readiness.
