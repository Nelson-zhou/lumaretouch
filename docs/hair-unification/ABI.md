# Hair-unification C ABI v1

Status: AUTHORED / UNRUN. The authoritative declaration is
`core/hair_unification/hair_unification.h`; ctypes declarations must match its
argument order and native C layout exactly. Symbols are exported from the planned
`engine/src/lumaretouch_engine/bin/liblrt_hair_unification.so`. No binary is supplied
and no loader/build result is claimed.

## Types and symbols

`lrt_hair_unification_abi()` returns u32 1. Lengths are u64 counts of float elements,
not bytes. Raster widths/heights and tile x/y are u32. Amount is f32 in [-1,1].
Masks and RGB use tightly packed, native-endian, aligned f32 buffers; no strides.
The cancellation type is `uint32_t callback(void *context)`; nonzero cancels.
A null callback disables cancellation.

LimitsV1 is four u64 fields, in this order:
`max_source_pixels, max_tile_pixels, max_work_units, max_working_bytes`.
Null limits uses {64000000,262144,1000000000,8388608}. Every supplied field must be
positive and may only reduce the hard ceiling, not increase it. Intended C size is
32 bytes.

ReferenceV1 has these exact ordered fields, intended C size 104 bytes:

1. u32 abi_version, struct_size.
2. i32 direction; u32 reserved (must be zero).
3. u32 source_width, source_height.
4. u64 selected_pixels, reliable_pixels.
5. f64 selected_weight, reliable_weight, effective_samples.
6. f64 retained_fraction, dispersion.
7. f64 chroma_ratio[3], in R,G,B order.

Do not pack these structs. Use `ctypes.Structure` with c_uint32/c_int32/c_uint64/
c_double, `sizeof`, and `c_double * 3`. Direction -1 = tips, +1 = roots. A neutral
record has direction 0, no samples and zero q; it is not a valid active reference.
Reference version, size, reserved bits, bounds, quality metrics, finite q and
luminance-neutral q are rechecked before active composition. Numeric validation
cannot authenticate provenance; the host must only use its own fresh measurement.

`measure_v1` argument order: source_rgb, source_rgb_len, hair, hair_len, roots,
roots_len, tips, tips_len, source_width, source_height, signed_amount, limits,
reference_out, cancel, cancel_context. Active RGB length is 3WH; each mask length
is WH. Source and every mask are validated. It measures the sign-selected mask;
no field pixels or native RGB output are allocated.

`compose_v1` argument order: current_rgb, current_rgb_len, hair, hair_len, tile_x,
tile_y, tile_width, tile_height, signed_amount, reference, limits, output_rgb,
output_rgb_len, cancel, cancel_context. Here "hair" means effective TARGET coverage,
with the selected sample region fully excluded. Input/output RGB lengths are 3wh;
coverage length is wh. Active tile must fit the measured reference's source raster.
CURRENT pixels can differ from measurement pixels due to earlier pipeline effects.

`compose_grid_v1` is a separate additive symbol with this exact argument order:
current_rgb, current_rgb_len, hair, hair_len, grid_width, grid_height, tile_x,
tile_y, tile_width, tile_height, signed_amount, reference, limits, output_rgb,
output_rgb_len, cancel, cancel_context. Grid width/height are u32 and are inserted
immediately before the original four tile coordinates. Tile lengths still refer
only to the tightly packed tile, not the complete grid. There are no struct changes,
no version reinterpretation and no change to the old `compose_v1` entry.

The grid is the complete CURRENT processing raster; tile coordinates are relative
to it. Active reference metadata remains the genuine full-source measurement,
including its full dimensions and original sample statistics. The new entry checks:

- Nonzero grid dimensions and grid pixel count <= max_source_pixels.
- Nonzero tile dimensions, existing max_tile_pixels, checked coordinate addition,
  and tile containment within the declared grid.
- Grid width/height individually <= reference source width/height, without upscaling.
- Exact full-source grid is accepted without alignment requirements. Otherwise,
  BOTH grid dimensions must be multiples of 8, matching `decode.proxy_size`.
- A single common downward-aligned scale must exist. Using checked u64 arithmetic,
  BOTH inequalities are STRICT: grid_width*source_height < (grid_height+8)*source_width
  and grid_height*source_width < (grid_width+8)*source_height. Equality fails because
  the upper scale-interval endpoint is open. This matches the existing canonical
  dimensional guard in `body_pose_evidence.whole_source_shape`, not a one-pixel rule.
- All original reference, sign, pixel, mask, alias, cancellation and scratch checks.

The host owns exact source/projection provenance and color/mask fidelity. Passing
the aspect test alone does not establish that a crop, rotated raster or unrelated
image came from the reference source. The core performs no resizing or remeasurement.
The host must authenticate the exact `decode.proxy_size` output for its actual
budget, not merely choose any dimensions passing the interval. That decoder aligns
both axes downward to 8, floors them at 8, and can decrement them again in its tiny
budget fallback. An originally tiny axis that would enlarge, or any floor/fallback
result outside the strict common interval, is explicitly refused by this core.
Reference dimensions, q and sample statistics must NEVER be rewritten or rescaled
to accommodate a preview. Export may declare the exact full-source grid. A missing
new symbol is an explicit compatibility blocker for preview-grid composition, not
permission to reinterpret the old entry or spoof reference metadata.

## Neutral path

The host must bypass evidence and native loading for either signed floating zero.
Native zero compose still validates finite amount, nonzero shape, tile-coordinate
addition, limits, exact current/output lengths, alignment and disjoint current/output
spans. It does not inspect RGB values, reference or hair. It copies all current bits,
including NaN payloads and negative zero. Null reference/hair are allowed regardless
of unused hair length; input/output in-place overlap is still rejected. It polls
cancellation before commit. No source-bound check is possible without a reference.

The explicit-grid neutral entry additionally checks its nonzero grid and grid-pixel
budget and requires tile containment within that grid. It still never reads hair
or reference, so no source projection or source-dimension check is possible on zero.
This extra structural validation belongs only to the new symbol; old neutral
semantics remain unchanged.

Native zero measure validates source shape, limits, reference output alignment and
its non-overlap with limits, then writes neutral metadata. It does not read source
or masks; their pointers/lengths can be null/zero. Such a record cannot authorize an
active operation. Neither zero route implies evidence has been reviewed.

## Safety, budgets and transactional publication

Callers must provide real readable/writable spans of the declared lengths. Null,
alignment, checked byte extents and arithmetic overflow are checked before slice
construction, but the ABI cannot prove that an arbitrary pointer is mapped. All
accessed input spans are immutable for the complete call. Read-only inputs may
alias each other; output must not overlap any accessed input, reference or limits
span. Exact in-place RGB operation is not supported. The callback/context must
remain live, must not throw/unwind, and must not mutate or free any ABI buffer.

Measurement uses constant-size stack histograms and a conservative 32768-byte
working allowance, not an image-sized allocation. It charges one logical work
unit per source pixel per pass, plus each visited median histogram bin, at most
3WH+2048. Work units are deterministic loop accounting, not CPU cycle estimates.
Composition stages 3wh f32 values and checks `12wh+4096` working bytes before
allocation. At the default 262144-pixel limit, staging is about 3 MiB. Other
caller-owned arrays and the caller's output allocation are outside native scratch
accounting; the host must enforce its complete process/request budget separately.

Callbacks are polled initially, at most every 4096 charged loop units, and before
commit. Cancellation latency is not a wall-clock guarantee. Zero compose charges
wh logical units then performs one bounded bitcopy. The final commit itself is not
polled, to prevent partial publication. After it starts, a success may complete even
if cancellation arrives concurrently; the host must discard stale sequence results.

Nonzero status never changes output bytes, including reference_out. Compose builds
its candidate in private bounded storage before publication. Allocation uses
try_reserve_exact. Rust panics are caught at each processing ABI boundary when
built with panic=unwind; aborts, OOM aborts outside recoverable allocation, invalid
foreign pointers, data races and foreign callback unwinding are not recoverable.

## Status codes

- 0: success.
- 1: bad ABI shape, pointer span, alias, tile bounds, reference schema/sign, or
  active explicit-grid projection/upscaling policy.
- 2: invalid amount, nonfinite/out-of-range RGB or mask, sample outside hair, bad q.
- 3: invalid/exceeded limits, dimensions too large, work or scratch budget exceeded.
- 4: cancellation observed before publication.
- 5: staging allocation failure.
- 6: contained Rust panic (only with unwinding enabled).
- 7: selected-reference quality/support insufficient or inconsistent.
- 8: overlapping root and tip marks, spatially ambiguous manual evidence.
- 9: nonfinite/out-of-gamut internal numeric result or impossible histogram state.

No status means "AI unavailable" because this operator performs no learned inference.
No fallback to source-color overwrite, additive-delta clipping, palette tint or
invented sample selection is permitted on an error.

## Added explicit-grid acceptance fixtures: UNRUN

The original 14 numerical fixtures remain. Six additional source-only fixtures
cover full-grid equivalence to the old entry, preview use without mutating reference
metadata, canonical ALIGN=8 interval acceptance/upscale and distortion refusal, neutral grid
bounds with arbitrary float bits, transactional grid/cancellation/alias errors,
and preview row-tile versus whole-preview equality. All 20 fixtures remain UNRUN;
no Rust build, parsing, native call, test or runtime result is asserted.
The shape guard fixture explicitly accepts 6000x4000 -> 3464x2304, rejects gross
aspect distortion and an open-interval equality, accepts an unaligned exact full
grid, and refuses tiny-axis upscaling. Preview ABI fixtures retain a genuine
128x64 measured reference while composing the pipeline-aligned 88x40 grid.
