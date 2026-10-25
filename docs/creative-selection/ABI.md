# Creative selection ABI v1

Status: **AUTHORED / UNRUN**. Canonical declarations are in
`core/creative_selection/creative_selection.h`; Rust mirrors them with `repr(C)`.
All examples/specifications below are authored, not native smoke-test evidence.

## Entry and buffers

The dedicated build script targets
`engine/src/lumaretouch_engine/bin/liblumaretouch_creative_selection.so` by
default; its optional first argument is a complete destination library pathname.
The exported symbols are:

```
uint32_t lr_selection_abi_version(void);  /* 1 */
int32_t lr_selection_evaluate_v1(
  const LrSelectionRecipeV1 *, const LrSelectionTileV1 *,
  const LrSelectionLimitsV1 *, LrSelectionCancelV1, void *,
  float *, uint64_t, LrSelectionStatsV1 *);
```

The output has exactly `tile.width*tile.height` float32 samples, row-major, no
stride/padding. `output_len` must equal that number. There is no length guessing,
ownership transfer, opaque allocation/free handle or process-global mutable state.
A successful return replaces output and optional stats. Every error leaves both
unchanged. Inputs are read-only. The caller must not publish the buffer while a
call is in flight.

Status codes: 0 success, 1 ABI/span/version error, 2 value/geometry error, 3 budget
or hard-limit error, 4 cancellation, 5 fallible allocation failure, 6 caught Rust
panic. A nonzero code is never a valid empty mask. Foreign callback exceptions,
invalid-address faults, process aborts and global allocator behavior cannot be
made safe merely by a status code or Rust panic catcher.

Every nonempty pointer span must be valid, aligned, live and non-overlapping with
every other ABI span for the duration of the call. Null array pointers are allowed
only for count zero. A null limits pointer selects defaults; a null stats pointer
omits stats; a null cancel function disables cancellation. A supplied cancellation
function returns nonzero to cancel, must not unwind, free storage, mutate input or
output spans, or reenter with aliased buffers. Independent calls are reentrant.
Pointer alignment/range/overlap checks do not prove that memory belongs to caller.

## Struct field order

`PointV1`: `x,y` f64; 16 bytes.

`OperationV1`: `kind,combine,point_offset,point_count` u32, followed by
`x0,y0,x1,y1,diameter,hardness,opacity` f64; 72 bytes.

`RecipeV1`: `abi_version,struct_size,source_width,source_height,operation_count,
point_count,feather_radius,reserved` u32, then pointers `operations,points`.
`struct_size` must equal the platform's C `sizeof`, not a JSON schema size.
Version is 1 and reserved is zero. On 64-bit targets this struct is 48 bytes;
host bindings must use native alignment rather than force packed layouts.

`TileV1`: `x,y,width,height` u32; 16 bytes, strictly positive extent entirely inside
the source canvas. `LimitsV1`: `max_working_bytes,max_output_pixels,max_work_units`
u64; 24 bytes. `StatsV1`: `working_bytes,work_units,output_pixels` u64; 24 bytes.
The cancel function takes one `void*` context and returns u32.

## Operation lowering

Kinds: rectangle 1, ellipse 2, lasso 3, brush 4, invert 5.
Combine: new 0, add 1, subtract 2, intersect 3.

- Rectangle/ellipse: normalized `x0<=x1,y0<=y1`. No points or brush values;
  unused point offset and all brush fields are exactly zero.
- Lasso: at least three points in the shared point array, with implicit closure.
  Box and brush fields are zero. Even-odd fill; duplicate points are legal.
- Brush: at least one point, only combine 1 or 2. Box fields are zero. Diameter
  `[1/64,262144]`, hardness/opacity `[0,1]`; all are finite. A single point is a dab;
  multiple points form a continuous stroke, not disconnected event stamps.
- Invert: combine zero, no points and all geometry fields zero. It complements
  the current field inside the canvas, in operation-list order.

All coordinates (including unused box values before zero validation) must be
finite with absolute value at most 1,048,576. Every point in the shared array is
validated, even if no operation references it. Referenced spans must fit exactly
inside the point array. An empty operation list is zero selection.

The JSON serialization belongs to the host/editor. Its versioned meaning must
include canvas/source identity, canvas dimensions, source-coordinate space,
operations and final feather radius. Flatten `[x,y]` points and lower rectangle
`x,y,width,height` into the above C shapes only after validating that host contract.
The C struct is not itself a portable persisted binary format.

## Resource bounds

Defaults per call:

- Working numeric buffers: 67,108,864 bytes (64 MiB).
- Output pixels: 1,048,576.
- Work units: 100,000,000.

Hard maximum overrides: 536,870,912 working bytes, 16,777,216 output pixels,
4,000,000,000 work units. Explicit zero limits are invalid, not unlimited/default.
Other hard limits: canvas edge 131,072; canvas area `2^32`; 4,096 operations;
262,144 points; final feather integer radius 0 through 256.

For tile width W, height H, clipped expanded patch width P, height Q, maximum
points in any operation N, and radius r, requested working bytes are:

```
4 * (P*Q + 5*P + W*H + (r > 0 ? W*Q : 0))
  + N * (sizeof(Edge) + sizeof(Segment) + sizeof(size_t) + sizeof(double))
```

Here Edge is two f64 points (32 bytes), Segment additionally stores f64 squared
length (40 bytes), and size_t is a native index. The coefficient for geometry is
88 bytes per point on a 64-bit target. Numeric buffers are independently owned;
input geometry is borrowed. Caller output and all application-level caches/assets
are outside this budget and need their own bound.

For example, a 512×512 interior tile at radius 32, before geometry storage,
requests `4*(576*576 + 5*576 + 512*512 + 512*576)` = 3,566,848 bytes.
This is an arithmetic capacity example, not a measured resident-memory or speed
result. A 24 MP image must be scheduled as bounded tiles, not silently accepted
as one default output buffer. A more complex path can still exceed work limits.

## Canvas-to-selected-layer sample contract

The native output is an authoritative canvas-grid field C, not the already
transformed selected layer's final mask. In the host's separate projection stage:

1. Freeze a valid selected raster leaf, its source dimensions/content identity,
   its full source-to-canvas affine S, canvas identity/dimensions, and revision.
   Root/group targets, singular/nonfinite matrices and stale references must not
   be guessed or retargeted.
2. For each leaf-local source sample center `(i+0.5,j+0.5)`, compute canvas edge
   coordinates `(X,Y)=S*(i+0.5,j+0.5,1)`. If outside the canvas domain, use zero.
3. Inside, evaluate bilinear raster sampling with `u=X-0.5,v=Y-0.5`. Fetch the four
   integer neighbor samples from **full-resolution** native canvas tiles, with
   zero for out-of-canvas neighbor indices. Never subtract half a pixel twice or
   treat pixel-edge coordinates as pixel-center array indices.
4. Write coverage to the immutable leaf-local source mask. The compositor applies
   that mask **before** the leaf affine. Existing-mask combine/replacement is a
   separate explicit host policy, not a reinterpretation of the recipe's first
   operation. Preserve the old mask/history until the full operation commits.

Identity and integer translations should reproduce matching source samples
exactly. General rotation, scale and shear use a two-stage raster sampling
approximation, not an analytic transformed-polygon area guarantee. Minification
quality and end-to-end transformed-layer equivalence need explicit acceptance
fixtures and tolerances. This v1 ABI does not evaluate an arbitrary affine grid
directly and must not be advertised as doing so. A future ABI may add that feature
without changing v1 semantics.

Projection must bound both source-mask staging and canvas-tile cache, forward
cancel requests, and bind preview/review/apply receipts to the same recipe,
source, target, transform, existing-mask identity and content revisions. A display
preview alone cannot authorize an upsampled final mask.
