# Lens aperture core, ABI 1

Status: **AUTHORED / UNRUN**. This is an independently authored CPU reference
operation, header, isolated build recipe and numerical/ABI fixtures. No compiler,
build, local product execution, import, test, benchmark, inference, model download,
installation, Git write or GitHub write was performed for this module. Static
source review does not establish compilation, numerical correctness, photograph
quality, interactive speed or feature acceptance.

The exact product reference is `LNX-REF-WF-165438-165adae6a7`, 镜头虚化. Its full
workflow and remaining acceptance gates are tracked in
[`docs/lens-blur/RESEARCH-AND-GATES.md`](../../docs/lens-blur/RESEARCH-AND-GATES.md).
This module alone is NOT that completed feature.

## Independent module and replacement contract

- No external Rust crates, model, decoder, global mutable state, file I/O,
  networking, runtime compiler, thread pool or background job. A call borrows
  immutable inputs and privately stages at most one output tile.
- Public C symbols: `lrt_lens_aperture_abi` returns 1;
  `lrt_lens_aperture_kernel_mask_v1` returns 31 (bits 0 through 4);
  `lrt_lens_aperture_validate_v1`; `lrt_lens_aperture_render_tile_v1`.
  See `lens_aperture.h` for exact signatures. Float lengths count elements.
- `Settings` is passed by value: one uint32 aperture, then six float32 fields
  `max_radius_px, focus_near, focus_far, depth_falloff,
  occlusion_tolerance, rotation_radians`. Intended C layout is 28 bytes,
  float32 alignment, verified only by an authored UNRUN fixture so far.
- The host checks exact ABI and symbols before advertising native availability.
  Kernel bits mean implemented mathematics, NOT accepted image quality.
  Missing library/symbol/ABI, disabled module or rejected kernel must leave the
  saved recipe intact, mark it unavailable and fail active rendering explicitly.
  Do not quietly substitute Gaussian blur, copy source as successful rendering,
  delete a recipe, downgrade its kernel or report that a missing depth model ran.
- No live-library unloading or hot replacement is provided. Replace a verified
  artifact between process lifetimes. Retain v1 semantics when loading v1 saved
  intent; changes to radius, depth, aperture or visibility semantics require a
  new version plus explicit migration, not silent reinterpretation.
- A true zero-effect recipe may be bypassed by a host only when it can prove
  the saved operation is neutral without changing its source or intent. This is
  not evidence the module loaded. ABI calls still strictly validate all inputs
  they are specified to inspect, including on zero-effect paths.

## Source, colour, alpha and depth

The source is native-endian tightly packed float32 H×W×4 linear-sRGB D65
premultiplied RGBA. It contains actual full-resolution source pixels, not an
8-bit preview or a synthetic stand-in. Alpha is finite [0,1]. Each RGB component
is finite and its absolute value is at most `65504 * alpha`, measured in f64.
This admits signed extended-range/HDR working values; alpha zero requires
exact zero RGB. Negative zero is accepted. No ICC, transfer encoding,
unpremultiplication, tone mapping, highlight boost or quantization occurs.

Depth is native float32 H×W, finite [0,1], explicitly **near zero, far one**.
It is relative ordering, not metres, inverse metres, disparity, confidence or a
segmentation mask. A real adapter must explicitly convert its model's convention
and reject invalid/flat or untrustworthy output according to its own contract.
This core does not guess a model's convention, infer depth from RGB, discover
a subject or invent a focus point. The host resolves point/subject focus into
the explicit interval `[focus_near, focus_far]` before calling.

Optional refinement is float32 H×W in [-1,1], otherwise absent. Source, depth
and refinement must share exact image identity, source revision, geometry,
orientation, dimensions and pixel grid. The host binds and validates those
identities and owns brush rasterization. Dimensions alone do not authenticate
a depth field. Never interpolate a thumbnail and claim native model inference
at full resolution; record the actual inference and resampling provenance.

All channels are accumulated with nonnegative weights in f64. RGBA is averaged
together in premultiplied space, including transparent samples in the spatial
normalization. The exact-arithmetic result is a convex combination of valid
premultiplied inputs, so no invented colour, alpha or gamut excursion is needed.
After f32 conversion the envelope is checked again. Any finite/alpha/envelope
failure, including a rounding excursion at the exact HDR bound, returns 7
without publication. It is never silently clipped. SDR input stays within its
convex hull; HDR remains HDR. The caller chooses a separate supported exporter.

## Radius and five original aperture kernels

Let z be relative depth, f0/f1 the focus interval, t the positive depth falloff,
R the maximum radius in **source-grid pixels**, and q the signed refinement:

    d = max(f0-z, z-f1, 0)
    b = min(d/t, 1)
    b' = b + (1-b)*q       when q >= 0
    b' = b*(1+q)           when q < 0
    r = R*b'

R is [0,128], t is [0.000001,1], f0/f1 are [0,1] with f0≤f1. Rotation is
finite [-π,π]. Aperture uses inverse rotation of normalized coordinates (u,v).
These parameters do not represent focal length, f-number, sensor size or
calibrated circle-of-confusion physics.

Each source pixel emits through its own radius, rather than gathering every
receiver through only the receiver's radius. The kernels are genuinely distinct:

| ID | Original name | Transmission inside support | Analytic unit mass |
|---|---|---|---|
| 0 | Circular disk | 1 for u²+v²≤1 | π |
| 1 | Rim-weighted disk | 0.25+0.75(u²+v²), same disk | 0.625π |
| 2 | Regular pentagon | Intersection of 5 half-planes with inradius cos(π/5) | 5 sin(2π/5)/2 |
| 3 | Regular octagon | Intersection of 8 half-planes with inradius cos(π/8) | 8 sin(2π/8)/2 |
| 4 | Cat-eye intersection | Intersection of unit disks centred at (±0.35,0) | 2 acos(0.35)−0.7 sqrt(1−0.35²) |

Polygon normals have angles 2πk/n. Every kernel fits inside a radius-one circle.
The cat-eye is a fixed rotated disk intersection, not spatially varying optical
vignetting. Rim weighting is OUR artistic apodization, not the undisclosed
commercial “圆形II” algorithm. None of these shapes is a Gaussian renamed to
match a label. No proprietary numerical or visual parity is claimed.

For radius≤0.5 the entire aperture lies in the source pixel, represented by an
exact unit self tap. Otherwise each receiver pixel box uses a deterministic 4×4
midpoint grid, normalized by `unit_mass * r²`. This is bounded quadrature,
not exact polygon/circle integration. It can alias small moving highlights;
continuous radius does not promise flicker-free parameter motion.

## Explicit visibility and refinement mathematics

For emitter j and receiver i, with receiver alpha ai and tolerance τ:

    visibility(j,i) = 1-ai   if zj > zi+τ
    visibility(j,i) = 1      otherwise
    wji = visibility(j,i) * aperture_pixel_weight(j,i,rj)
    blurred_i = sum_j(wji * premultiplied_RGBA_j) / sum_j(wji)

This rule blocks a farther emitter from contaminating an opaque nearer receiver.
A partially covered receiver attenuates farther emitters by its uncovered
fraction. A closer defocused emitter may spread over a farther receiver. The
visibility test happens before colour normalization, not as a radius-only gate.
τ is [0,1], in relative-depth units. Increasing it permits more cross-depth
mixing; τ=1 effectively disables this occlusion restriction.

For q<0, the receiver additionally blends the blurred value with its original
premultiplied value using clear fraction −q. q=−1 returns the original four
float32 words exactly, even beside a nearer blurred emitter. Positive q changes
emission radius only. Focused pixels are not universally protected: a physically
nearer out-of-focus source is allowed to cover them by the above approximation.
An all-focused plane with no blur refinement is exact identity. R≤0.5 and a
sole self-contributor are exact copies without transfer round trips.

**Known limitation:** this is conservative single-depth 2.5D visibility, NOT
layered front-to-back aperture compositing, ray tracing or hidden-surface
reconstruction. It can leave a hard inner silhouette on a defocused foreground,
produce asymmetric edge spread, dark/light halos where depths are wrong, and
cannot recover background hidden behind hair, glass, transparent surfaces or
thin foreground structures. Receiver normalization changes global flux at
occlusion/image boundaries. Fractional alpha is not a replacement for multiple
depth layers. These are explicit photographic acceptance blockers, not solved
by the presence of a depth map or a set of synthetic fixtures.

## Tiles, resource limits and cancellation

The source and planes always describe the complete immutable image. `(x,y)` is
the integer source-grid top-left of the requested output tile; output is exactly
tile_width×tile_height×4. Tiles cannot extend outside the source. No implicit
image enlargement, coordinate transform, edge replication or reduced-resolution
fallback exists.

The conservative real-source halo is zero for R≤0.5, otherwise `ceil(R+0.5)`.
The half-pixel term covers receiver pixel-box support. Bounds clip only at true
image edges, never at tile edges. An arbitrary source crop is not a full source.
The complete expanded halo is validated before calculations. The entire source
must also be validated once with `validate_v1` and then kept immutable; rendering
does not repeatedly inspect pixels outside its halo.

| Budget | Maximum |
|---|---:|
| Source pixels | 100,000,000 |
| Borrowed RGBA | 1,600,000,000 bytes |
| Borrowed depth | 400,000,000 bytes |
| Optional borrowed refinement | 400,000,000 bytes |
| Output tile pixels | 65,536 |
| Caller output | 1,048,576 bytes |
| Private native staging payload | 1,048,576 bytes |
| Candidate neighbour visits per tile | 8,388,608 |
| Aperture midpoint evaluations per candidate | at most 16 |
| Maximum source-pixel radius | 128 |

Source and tile products, lengths, pointer spans/alignment, tile bounds and
address arithmetic are checked. Candidate admission uses the conservative bound
`tile_pixels * min(width,2*halo+1) * min(height,2*halo+1)`. A too-large tile
returns resource status; the host may divide it into smaller tiles with the
same settings and full source, not silently reduce radius or image resolution.
Worst-case work is O(tile_pixels·R²) with 4×4 quadrature; this is NOT an interactive
performance claim. Large full-resolution radii may be impractically slow.
The host must bound total job work/time, concurrent tiles, retained sources,
decoded arrays, depth-model memory and aggregate document memory separately.
Listed payload sizes do not include allocator metadata or upstream copies.

Cancellation is polled before work, every 256 validation/candidate visits,
before each output pixel and immediately before the final commit. Allocator,
callback and final ≤1 MiB copy latency are not real-time bounds. A callback must
not unwind, reenter or modify/free inputs. The host also checks request/source
generation after a successful tile to reject a result made stale after the last
poll. A successful tile is not permission to publish a partially completed job.

Every error or cancellation leaves the caller's entire output unchanged. Private
staging is dropped on return. Every C entry point that can fail catches Rust
unwind panics; invalid raw pointers, foreign faults and panic-abort are not
recoverable this way. Output must be disjoint from all inputs, including partial
overlap. Inputs may overlap one another only while they remain valid immutable
views. The caller owns all allocation/lifetime guarantees.

Status codes: 0 success; 1 ABI/layout/overlap; 2 settings; 3 pixels/depth/plane;
4 cancelled; 5 resource/allocation; 6 contained panic; 7 invalid rounded result.

## Execution gate

The build script and Cargo manifest are authored, not invoked. Under future
execution authorization, compile the exact final source, run the Rust fixtures,
validate the C/Python struct boundary and cancellation, then run real-image
quality and performance evaluation. Synthetic tests cannot close the workflow,
licensing, export, performance or depth-quality gates documented separately.
