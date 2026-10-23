# Creative image-layer core, ABI v1

Status: original source authored, static source review only. Build, Rust tests,
Python import/tests, native loading, visual output, performance and end-to-end
integration are **UNRUN**. Nothing here is a claim of product acceptance.

## Working image contract

- Real imported/decoded full-resolution image pixels, not a procedural stand-in,
  thumbnail, encoded image file, or UI preview.
- Tightly packed native-endian float32 H×W×4 RGBA, linear-sRGB D65, premultiplied.
- RGB may be negative or exceed one. All values must be finite. Alpha must be in
  [0,1], and RGB must be exactly zero when alpha is zero. RGB is not constrained
  to alpha because that would wrongly exclude extended-range premultiplied data.
- The project import store may enforce a stricter signed-HDR provenance bound
  (for example straight colour magnitude at most 65504). This working compositor
  deliberately does not clip such values or subsequent intermediate composites.
- Colour arithmetic is widened to f64 internally to avoid needless intermediate
  overflow; the source, destination, and committed result are float32. A result
  that cannot be represented as finite float32 is rejected rather than clamped.
- The native compositor does not perform ICC conversion, tone mapping, transfer
  conversion, quantization, unpremultiplication or export encoding. Explicitly
  named bridge entry points below keep import, strict export and display separate.

`lrt_creative_validate_rgba` validates the entire immutable imported source once.
`lrt_creative_validate_mask` validates the entire immutable source-local mask
once. The tile entry point then revalidates every accessed source tap, mask tap,
and backdrop pixel. It does not repeatedly scan untouched source pixels: callers
must not mutate a source after its successful whole-image validation. A zero
opacity or entirely off-canvas layer need not read the source raster.

## Resource and ownership contract

The constants are limits, not allocation targets:

| Quantity | Limit |
| --- | ---: |
| Source image pixels | 100,000,000 |
| Source RGBA bytes | 1,600,000,000 |
| Optional mask bytes | 400,000,000 |
| Destination tile pixels | 65,536 |
| Destination tile bytes | 1,048,576 |
| Rust staged output bytes per call | 1,048,576 |
| Exact integer canvas-origin magnitude | 2^50 |

Width and height must be positive; there is no additional arbitrary per-axis
cap. Products, span sizes, pointer alignment and address arithmetic are checked.
The caller must enforce its document-wide retained-asset, concurrency, group-depth
and aggregate-memory budgets. This core cannot see other live documents or jobs.

The caller owns valid aligned buffers of the declared lengths. Source, backdrop,
mask and matrix remain immutable during each call. Output is disjoint from all
inputs. The core rejects detected overlap, including partial overlap. Like every
raw-pointer C API, it cannot establish whether a non-null address actually points
to the claimed live allocation. Fabricated/dangling pointers violate the ABI.

The Python bridge uses bytes-backed immutable snapshots rather than relying on
NumPy's reversible writeability flag. A whole contiguous array backed by immutable
bytes is reused without an additional full-raster copy. Other array owners are
copied once. Cache the frozen result for the lifetime of a render snapshot rather
than freezing every tile. The backdrop is copied once per bounded tile so a
concurrent alias cannot change it while ctypes releases the GIL. NumPy and the
shared library are loaded lazily, not at module import.

## ABI entry points

See `creative_layers.h` for exact prototypes. All lengths count floats, not bytes.

- `lrt_creative_layers_abi()` returns 1.
- `lrt_creative_validate_rgba(input, length, width, height)` requires
  length = width × height × 4.
- `lrt_creative_validate_mask(input, length, width, height)` requires
  length = width × height.
- `lrt_creative_linearize_rgba(input, output, length)` converts one bounded chunk
  of straight encoded-sRGB RGBA into premultiplied linear RGBA. All four input
  channels must be finite in [0,1]. It uses the piecewise inverse sRGB transfer
  (threshold 0.04045), then multiplies RGB by unmodified alpha. The importer must
  normalize uint8/uint16 and perform ICC conversion into encoded sRGB first.
  Existing linear/HDR sources must not use this entry point. No 8-bit round-trip.
- `lrt_creative_linearize_extended_rgba(input, output, length)` is a separately
  named bridge for capturing edited signed extended-sRGB output. It uses the
  odd-sign inverse sRGB transfer, requires finite RGB and alpha in [0,1], rejects
  decoded straight RGB magnitude above 65504, and validates the stored rounded
  premultiplied value against 65504×alpha. It does not change SDR import semantics
  or silently clip excessive HDR. Input and output both have `length` float32s.
- `lrt_creative_encode_opaque_sdr_rgb(input, output, length)` bridges canonical
  linear RGBA into a legacy opaque-SDR RGB exporter. Every alpha must equal one
  and all RGB must be in [0,1]; otherwise it rejects the whole chunk. It applies
  the sRGB transfer but never implicitly clips, mattes, drops transparency or
  quantizes to eight bits. `length` counts RGBA input floats; output contains
  length/4×3 float32 RGB values. A caller needing HDR or alpha export must choose
  a genuinely supporting exporter, not silently route through display output.
- `lrt_creative_display_rgb8(input, output, length, matte)` is display-only:
  source-over onto an explicitly supplied three-float linear-sRGB [0,1] matte,
  followed by SDR clipping, sRGB encoding and RGB8 quantization. It accepts valid
  signed/HDR input but only modifies a presentation copy. `length` counts RGBA
  input floats; output contains length/4×3 uint8 RGB values. No implicit matte.
- `lrt_creative_composite_tile(source, source_length, source_width,
  source_height, backdrop, output, tile_length, tile_width, tile_height,
  inverse, canvas_x, canvas_y, opacity, mode, mask, mask_length)` produces one
  canvas tile. Source dimensions always describe the complete imported source.
  Backdrop and output lengths equal tile_width × tile_height × 4. A null mask
  requires mask_length = 0; otherwise mask_length = source_width × source_height.

Return values:

| Code | Meaning |
| --- | --- |
| 0 | Success; all output committed |
| 1 | Bad ABI/layout, length, overlap or resource budget |
| 2 | Invalid affine, origin, opacity or blend mode |
| 3 | Invalid pixel/mask values or alpha contract |
| 4 | Bounded staging allocation failed |
| 5 | Result not representable as canonical finite float32 RGBA |
| 6 | Compositor panic contained at the C boundary |

Every nonzero rendering/transfer result leaves **every output byte unchanged**.
No output is published until the complete tile succeeds. Do not compile the
compositor with panic-abort if relying on panic containment. Allocation failure
uses `try_reserve_exact`; the core contains no full-image intermediate allocation.

## Affine sampling and source halo

`inverse` is exactly six doubles `(a,b,c,d,e,f)`:

    source_x = a * canvas_x + b * canvas_y + c
    source_y = d * canvas_x + e * canvas_y + f

The matrix must be finite and invertible. Coordinates are pixel-center based:
destination pixel `(x,y)` is sampled at `(origin_x+x+0.5, origin_y+y+0.5)`;
source pixel `(i,j)` has center `(i+0.5,j+0.5)`. Identity is `(1,0,0,0,1,0)`.
A forward image translation by `(tx,ty)` uses inverse `(1,0,-tx,0,1,-ty)`.
Negative scale and rotation are supported, without a special reflection mode.

Bilinear interpolation reads the four neighboring source pixels. Beyond the
full image extent each tap is transparent black, never an edge-clamped colour.
Even at a destination tile edge, the source is still the full immutable image,
so interpolation reads the needed one-pixel source halo rather than clamping to
the destination tile. Render tiles use global canvas origins, so splitting them
does not change the sample coordinates or cross-tile edge behaviour. This ABI
does not accept arbitrary source windows; a future windowed source must declare
its valid region and required halo rather than silently treating missing data as
transparent.

Optional mask coverage is in the image's local source coordinates and multiplies
each premultiplied source texel, including alpha, before interpolation. Layer
opacity multiplies the resulting premultiplied sample, including alpha, once.
If alpha rounds to zero while nonzero RGB remains representable, the tile is
rejected rather than losing HDR energy or introducing hidden edge colour.

## Exactly five blend modes

Mode IDs are fixed: 0 normal, 1 multiply, 2 screen, 3 lighten, 4 darken. Any other
ID is rejected; no silently substituted or unimplemented mode is exposed.

The core uses source-over with algebraically premultiplied separable blend
expressions, avoiding division by tiny alpha. With source `(s,as)` and backdrop
`(b,ab)`, the output alpha is `as + ab*(1-as)`. Each colour channel is:

    normal:   s + b*(1-as)
    multiply: s*(1-ab) + b*(1-as) + s*b
    screen:   s + b - s*b
    lighten:  s*(1-ab) + b*(1-as) + max(b*as, s*ab)
    darken:   s*(1-ab) + b*(1-as) + min(b*as, s*ab)

These expressions are evaluated in the declared linear working space, not
encoded display sRGB. The signed/HDR extension intentionally does not apply
SDR rounding/clipping instructions. Thus screen can produce negative RGB for
large HDR operands; that is not silently tone-mapped. This is not a promise of
bit-identical browser CSS output in every colour-management environment.

## Isolated groups and integration ports

The caller recursively composites children into a transparent `(0,0,0,0)`
offscreen tile. It then composites that finished tile once onto the parent with
the group's opacity/blend mode and cropped canvas-space group mask. It must not
apply group opacity independently to children. An offscreen tile at canvas
`(tx,ty)` uses inverse `(1,0,-tx,0,1,-ty)` when treated as the group source. A
group must not blend its children against the outside parent backdrop.

The core does not infer a layer tree or implement pass-through groups. It exposes
the primitives needed for explicit isolated recursive offscreen composition.

Python ports:

    linearize_rgba(srgb_rgba, *, cancelled=...) -> float32 premultiplied RGBA
    linearize_extended_rgba(srgb_rgba, *, cancelled=...) -> signed/HDR canonical RGBA
    encode_opaque_sdr_rgb(rgba, *, cancelled=...) -> float32 encoded-sRGB RGB
    display_rgba(rgba, *, matte, cancelled=...) -> uint8 presentation RGB
    freeze_rgba(pixels, *, encoding='linear-srgb-d65', premultiplied=True,
                cancelled=...) -> FrozenRGBA
    freeze_mask(pixels, *, cancelled=...) -> FrozenMask
    composite_tile(backdrop, source, *, inverse_affine=(1,0,0,0,1,0),
                   canvas_origin=(0,0), opacity=1.0, blend_mode='normal',
                   mask=None, cancelled=...) -> new float32 RGBA tile

`FrozenRGBA` and `FrozenMask` expose width, height, nbytes and a fresh read-only
pixels view. The wrapper returns no partially completed image on rejection or
cancellation. Callers must still check render generation, document revision,
source scope and cancellation before committing a result to preview/export.
Missing or incompatible packaged native code is an explicit unavailable error,
never an automatic Python fallback or runtime compiler invocation.

## Provenance and local QA handoff

All source in this directory and the Python bridge is original Lumaretouch code;
no Krita implementation or third-party source was copied. Conceptual sources
verified on 2026-10-23:

- W3C, [Compositing and Blending Level 1](https://www.w3.org/TR/compositing-1/),
  sections 6, 8.2, 9.1.4, 10.1.1–10.1.3, 10.1.5–10.1.6: source-over, separable
  blend functions, and isolated-group starting backdrop.
- Krita, [Group Layers](https://docs.krita.org/en/reference_manual/layers_and_masks/group_layers.html):
  child results are combined before compositing the group with the outside image.
- W3C, [CSS Color 4, sRGB](https://www.w3.org/TR/css-color-4/#valdef-color-srgb):
  declared D65 colour space and piecewise encoded-to-linear transfer constants.

Only Qoder/the authorized local QA environment may run the following while the
current no-execution development gate remains in force:

    sh core/creative_layers/build_creative_layers.sh
    rustc --edition=2021 --test core/creative_layers/lib.rs -o /tmp/lrt-creative-tests
    /tmp/lrt-creative-tests

Authored Rust fixtures cover five mode goldens, independent partial-alpha
reference, signed/HDR preservation, canonical transparency, identity/rotation/
reflection, masked bilinear edge coverage, horizontal/vertical tile seams,
isolated group opacity, full import validation, overflow, late-invalid input,
overlap, malformed lengths, resource bounds, and import sRGB transfer.
Additional bridge fixtures cover strict float-RGB export, rejection of HDR and
alpha on the unsupported legacy exporter, explicitly matted/clipped display,
and separately bounded signed extended-sRGB capture with strict import unchanged.

Still required: local build/link, all authored tests, Python bridge tests with a
real packaged library, source alias mutation/bytes reuse, real RGBA PNG and
RGB/RGBA16 imports with ICC, visual halos and group-mask acceptance, cancellation
and stale-generation rejection, source immutability, memory/latency measurements,
preview/export parity and host-level integration. Authored fixtures are not
substitutes for those results.
