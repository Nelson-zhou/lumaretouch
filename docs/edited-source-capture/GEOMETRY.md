# Bounded edited-source NumPy geometry v1

Status: AUTHORED / UNRUN. This change is source-only. No product module import,
numerical fixture, test suite, build, type check, inference, benchmark, real-photo
trial or process-memory measurement has been performed. AST syntax and source
hash inspection are not runtime acceptance.

## Scope and compatibility boundary

`engine/src/lumaretouch_engine/creative_capture_geometry.py` is a separately
versioned allocation strategy, identified by
`edited-capture-numpy-geometry-v1`. It does not modify the ordinary renderer in
`ops/geometry.py`, install a different interpolator, alter saved crop intent,
downsample input, clip RGB, normalize signed zero, or introduce fast-math.
Integration must explicitly select this path; the module does not select itself
or assert that other export effects are eligible.

The source contract is an exact plain NumPy HWC3 array with native-endian float32
or float64 dtype and positive dimensions. Input and output each have a
100,000,000-pixel ceiling. Known plain ndarray, memoryview, bytes and bytearray
backing-owner chains are supported. Unknown buffer wrappers, ndarray subclasses,
structured/object/metadata-bearing backing dtypes, unprovable non-owning roots,
noncontiguous owning roots, cycles/excessive chains, and views outside the known
allocation are refused before output allocation. Negative, zero and nonstandard
strides are supported when their full byte span lies inside a known owner.

Common export crop descriptors are accepted as four plain numeric scalars in a
list/tuple, or a one-dimensional four-element numeric ndarray. Nested/custom
descriptor objects are intentionally outside this bounded contract. The legacy
validator remains the authority for normalized range and angle validity.
Inspection does not certify finite pixels, color encoding, provenance, the
absence of external aliases, or the eligibility of an export pipeline.

## Exact arithmetic, not an approximation

The existing `check`, `is_identity`, `_cut`, `_snapped_quarter_turn`, `out_size`
and `_sample_bilinear_np` remain the semantic source:

- Full neutral geometry returns the original input object, including its dtype,
  readonly flag and strides. The original EPS identity test is retained.
- Crop endpoints use the existing round-to-pixel `_cut` rule.
- Quarter-turn snapping uses the strict original half-degree test on both sides
  of each quarter turn. Exactly half a degree still uses interpolation.
- Crop and snapped paths retain input dtype and lossless channel bytes. Where
  the legacy path returns a source alias, this implementation also returns a
  source alias. Otherwise it allocates one C-contiguous output rather than a
  contiguous intermediate crop followed by a second output.
- Arbitrary-angle output is native float64 RGB, even for float32 input. It is
  not silently cast back to float32 to satisfy a later consumer.

Legacy rotation first promotes the entire cropped source to float64. Therefore
performing `p10 - p00` in float32 and promoting afterward is incorrect, including
for large opposite-sign values. `_Float64Gathers` supplies the exact operations
the existing sampler uses: `.shape` and advanced-index reads. Each read first
gathers a bounded block, then promotes those values to float64 **before** any
subtraction, multiplication or addition. Float64 input gathers need no dtype
conversion. The existing sampler evaluates the original four-corner arithmetic;
there is no duplicate bilinear implementation in the new module.

The sampler also retains its existing distinct boundary rules: normal images
require the floor coordinate to have a complete 2-by-2 neighborhood; a singleton
axis uses inclusive half-pixel membership and clamps within that cell. The
adapter passes the actual cropped shape, not the original image shape.

Each output block generates its global integer `mgrid` coordinates, then casts
to float64. It evaluates the original `dx`, `dy`, `sx`, `sy` expression order
using the global output center and cropped source center. Tiles do not reset
coordinates, approximate an affine recurrence, use float32 coordinates, change
trigonometric expressions, or merge multiply/add operations. The old sampler
receives only coordinate arrays with at most 65,536 elements.

## Inspection and execution APIs

`inspect_crop_rotate_np(array, rect, rotation_degrees, *, block_pixels=65536,
max_bytes=None, cancelled=None)` returns an immutable `GeometryCapturePlan`.
It inspects layout/ownership and uses view-only slicing/quarter-turn operations;
it does not sample pixels or materialize a raster. If a maximum is supplied,
inspection rejects an over-budget plan immediately.

`crop_rotate_np_bounded(array, rect, rotation_degrees, *, max_bytes=512000000,
cancelled=None, block_pixels=65536)` re-inspects and admits the real source before
output allocation. `max_bytes` must be an integer from 1 to 4,000,000,000;
`block_pixels` must be an integer from 1 to 65,536. Boolean values are not valid
integer budgets. The default block bound is fixed and cannot be expanded by
passing a larger value.

Important plan fields:

- `version`, `path`, `crop_bounds`, `rotation_degrees`, `output_shape`,
  `output_dtype`, `quarter_turns` describe the exact planned operation.
- `source_bytes` is visible logical extent; `source_owner_id` and
  `source_storage_bytes` identify/charge the full terminal data-buffer owner.
  For example, a small crop of a large raster charges the large raster, and a
  broadcast view charges its actual small backing owner rather than pretending
  its logical repeated extent is a new allocation.
- `output_bytes` is logical output size. `output_storage_bytes` is retained
  backing storage after return. `output_allocation_bytes` is zero for a source
  alias and is the complete output allocation otherwise.
- `scratch_components`, `block_workspace_bytes`, `additional_work_bytes` and
  `peak_bytes` make geometry's declared working set inspectable. The plan holds
  no source reference and is not a persistent cache or an ownership lease.
- `runtime_verified` is false. `bounds_kind` explicitly describes an application
  working-set estimate with conservative native reserves, not a process-RSS cap.

All source/descriptor data and external aliases must remain stable for the
call. Callers must preserve the root's lifetime if comparing `source_owner_id`
with another census. The execution function does not accept a caller-constructed
plan as authority and never consumes/releases the caller's external aliases.

## Memory accounting

Let S be actual retained source storage, M the output pixel count, and
B = min(requested bounded block size, M). Arbitrary geometry requires:

`S + 24*M + 640*B + 4 MiB array reserve + 4 MiB metadata reserve`.

The shared immutable `ARBITRARY_SCRATCH_PER_PIXEL` declaration names the
source-audited conservative allowances, in bytes per block pixel:

| Scratch owner/category | Bytes/pixel |
| --- | ---: |
| Integer grids and float64 affine temporaries | 128 |
| Sampler indices, weights, and singleton clamps | 160 |
| Validity masks and boolean expression temporaries | 16 |
| Four simultaneous float64 RGB gathers | 96 |
| One gather/cast input transient | 24 |
| Bilinear and final where intermediates | 192 |
| Strided output assignment allowance | 24 |
| Total | 640 |

The ledger deliberately overcounts expression temporaries rather than claiming
an allocator measurement. The fixed reserves cover array/iterator/runtime and
Python metadata allowances; interpreter/import state and unrelated caller
allocations are not certified. Native allocator slop and real platform behavior
still require later measurement.

A copied crop/quarter-turn charges one output at source item size plus a
bounded assignment allowance of twice the block's RGB bytes and the same fixed
reserves. A source-alias output is not charged twice. No full cropped raster,
full float64 input conversion, full-canvas coordinate grid, or list of completed
blocks is created. Output block references are cleared before the next block.

The caller must separately admit the original encoded image, decoded integer
source, still-live export tiles, snapshot/analysis owners, other native work,
host/document roots, conversion sink, and later immutable freeze. It must not
interpret this module's `peak_bytes` as whole-pipeline admission. In particular,
an arbitrary output's 24 bytes/pixel differs from a snapped float32 output's
12 bytes/pixel, and its later source-to-sink overlap must charge the real dtype.

## Cancellation and failures

Cancellation is checked before layout work, after inspection, before allocation,
after allocation, around every block, and before returning a completed result.
No partial output is returned. On exit, local output/block/view references are
cleared; the gather adapter drops its source reference. This cannot release
external aliases or certify cleanup of another library's failure traceback.
Invalid geometry, unsupported ownership, output limits and budget errors do not
fall back to clipping, proxies or another arithmetic implementation.

## Authored evidence, still unrun

`engine/tests/test_creative_capture_geometry_unrun.py` compares against the
actual `ops.geometry.crop_rotate_np(..., uint8=False)`, not a substitute oracle.
Fixtures cover arbitrary angles, strict snap boundaries, rounded crop bounds,
singleton and crop-induced singleton shapes, negative/transposed/Fortran/channel
and broadcast strides, readonly neutral identity, signed zero, negative/HDR
values, and float32 extremes whose subtraction would overflow before promotion.
They demand exact output shape/dtype and C-order byte equality for finite cases.

Additional authored cases inspect global float64 block coordinates, verify
bounded sampler calls/no full source cast, inspect known full backing owners,
reject unknown owners, exercise exact/one-byte-short budgets, shape-only output
limits, and cancellation before allocation and after a real first sampler block.
These tests are not claimed to have passed. Runtime parity, memory profiling,
real-image validation and full export integration remain acceptance gates.

The legacy geometry file at the delegated baseline had SHA-256
`d8926644d923b5589eb112ac1ec3bb3a96c908789c9f53968aaecb8f618b4985`;
that file is not part of this module's edits.

## NumPy semantics consulted

The implementation was authored against the project's existing sampler, not
copied from an external implementation. Official NumPy documentation supports
the storage reasoning: [basic indexing produces views and advanced indexing
produces copies](https://numpy.org/doc/stable/user/basics.copies.html);
[`ndarray.base` records a backing object](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.base.html);
[`ndarray.nbytes` counts array element storage, not all object
overhead](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.nbytes.html).
Those facts motivate following the complete known owner chain and reserving
metadata separately rather than charging only a cropped view's `nbytes`.
