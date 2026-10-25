# Numerical contract, version 1

Status: **AUTHORED / UNRUN**. The following specifies the code and pending tests,
not measured accuracy or runtime evidence.

## Coverage construction

All coordinates are finite f64 in authoritative canvas pixel-edge space. Output
samples are float32 in `[0,1]`. There is no mask quantization to 8 bits and no RGB,
semantic segmentation, alpha-image inference or displayed-proxy input.

### Rectangle

For cell `(x,y)`, intersect the horizontal interval `[x,x+1)` with `[x0,x1)` and
the vertical interval `[y,y+1)` with `[y0,y1)`. Multiply the two overlap lengths
in f64 and round to f32. This is analytic pixel-area coverage for an axis-aligned
rectangle, including fractional edges. Zero width/height means empty coverage.
The caller normalizes left/right/top/bottom; reversed bounds are rejected.

### Ellipse

The bounding rectangle defines center and radii. For each pixel row, eight
globally anchored vertical midpoint samples `y+(k+0.5)/8` produce analytic
horizontal ellipse chords. Exact horizontal overlap lengths are averaged in
fixed order. This avoids a 2D supersampled canvas and gives fractional coverage.
It is **eight-point vertical quadrature**, not analytic ellipse/pixel intersection.
Very thin ellipses narrower than the sample spacing vertically can be missed.
That limitation must not be described as exact subpixel geometry.

### Lasso

The last point connects to the first automatically. Horizontal edges do not
participate in crossing tests. All nonhorizontal edges are sorted by minimum Y;
an active edge list is advanced at the same eight canonical subrows as the
ellipse. An edge is active for `minY <= sampleY < maxY`. Crossings use f64 and are
computed directly from original endpoints, not by accumulating per-row slopes.
Sorted pairs fill the even-odd interior, including self-intersecting paths. Each
pair contributes analytic horizontal cell overlap divided by eight. Repeated
vertices and duplicate final closure are allowed. There must be at least three
points, but a collinear/zero-area path legitimately gives empty coverage.

There is no per-pixel loop over all polygon vertices. For E edges and S sampled
scanlines the setup is `O(E log E)`; each scanline processes its active edges,
sorts crossings and visits only filled horizontal spans. Ordered set combination
still visits the patch once per operation. This does not imply constant time for
pathological self-intersecting/high-active-edge polygons.

### Selection brush

A stroke is the union of continuous round capsules between consecutive points.
A single point is a disk. The scalar distance to each segment is evaluated only
within its capsule's horizontal extent. Those extents come from endpoint-circle
chords and the connecting oriented rectangle, not the entire diagonal bounding
box. Segments have a sorted-Y active list; there is no mandatory one-dab-per-input
event gap. Each pixel uses sixteen canonical midpoint samples (4×4).

Let `r = diameter/2`, `h = hardness*r`, and `d` be distance to a segment. The sample
weight is 1 at `d <= h`, 0 at `d >= r`, and `t*t*(3-2*t)` in between, where
`t = (r-d)/(r-h)`. Multiply by opacity. The maximum over stroke segments is taken
**before** averaging samples, avoiding per-segment opacity buildup and join seams
from averaging individual segment masks. Hardness 1 takes a hard circular edge;
opacity is still independent. Different stroke operations use the same documented
set-combination algebra as the other selections. Add is a coverage maximum, not
Porter-Duff source-over, and subtract is saturated difference, not multiplication.

The fixed sample grid is an approximation: tiny brushes or tiny features may miss
every sample. The legal native minimum diameter is 1/64 pixel to preserve a broad
wire contract, not a promise of visibility at that size. The editor should give
users useful full-resolution brush sizes rather than imply arbitrary analytic
brush accuracy. Pressure, tilt and paint-rate accumulation are not in v1.

## Ordered set algebra and inversion

The initial field is 0. Each shape constructs B without modifying A; new returns
B, add returns `max(A,B)`, subtract returns `max(A-B,0)`, and intersect returns
`min(A,B)`. Small summation overshoot is clamped to `[0,1]`. An invert operation
returns `1-A` inside the canvas and has no geometry or combine mode. Empty then
invert is full canvas. Invert is evaluated before the final recipe-level feather;
moving invert past feather can change boundary values and is not permitted.

Coverage algebra is not a geometric Boolean operation on infinitely precise
shapes: antialias integration and min/max do not generally commute. The recipe
semantics intentionally specify mask algebra after per-shape rasterization.

## Finite feather and exact tile independence

For integer radius r, the one-dimensional kernel has weight `1/(2r+1)` on offsets
`[-r,+r]`, zero elsewhere. Run horizontal then vertical, rounding each horizontal
mean to float32 before the vertical pass. Outside-canvas samples are zero;
denominators are never shortened at image edges. Radius 0 is identity. The exact
required geometric halo is r in X and Y, not an undocumented infinite Gaussian
tail. A full-canvas selection therefore softens at the canvas edge when r > 0.

Ordinary floating sliding sums can depend on where a tile starts. To avoid that,
`CoverageSum` represents the **exact sum of binary32 inputs** as three u64 limbs
in units of `2^-149`. The normalized float32 mantissa is shifted by exponent minus
one; subnormals are stored directly. A window has at most 513 samples in `[0,1]`,
so fewer than 160 bits suffice. Carry/borrow arithmetic is integer exact. The three
limbs are converted to f64 in a fixed high-to-low expression and divided by the
fixed kernel width, then rounded to f32. This is exact accumulation of existing
float samples, **not quantization of the masks to an integer coverage scale**.
No stronger claim of correctly rounded arbitrary real-valued convolution is made.

The same global shape samples, same ordered operations, exact window sums and
same two rounding steps are used for whole and tiled output. Hence boundaries do
not depend on tile shape/order. This designed bit-identity guarantee is scoped to
the same executable/platform; it does not promise identical libm results across
architectures or future ABI versions. Tests for radii 0/1/4/16/256 and irregular
tiles are authored but **not run**.

Feather costs linear passes plus window initialization, not `O(r*tile_pixels)`
convolution: approximately `O(patch_pixels + tile_width*patch_height + output_pixels
+ r*(patch_height + tile_width))`. Geometry replay dominates complex recipes.

## Limits, cancellation and known nonclaims

Scratch buffers are planned and bounded before allocation. Allocation uses
fallible `try_reserve_exact`; scalar span arithmetic is checked at the C entry.
The working-byte report counts requested numeric buffer capacities, not allocator
metadata, Rust runtime, the caller's arrays/output or all-process resident memory.
Work units charge covered pixels, active geometry, sorting estimates and filter
passes; they are a deterministic rejection budget, not CPU cycles or milliseconds.

Cancellation is polled at entry, operation/row boundaries, during long pixel
loops, and around sorting. Sorts and allocation/initialization are not preemptible;
there is no hard real-time cancellation latency promise. Output and stats are
committed only after successful evaluation and a final cancel poll. The host must
likewise delay document/history publication until every tile succeeds.

Full-resolution speed, 24 MP latency, memory usage measured by an operating
system, visual agreement with a reference product, GPU behavior, rotation
projection accuracy and minification-quality resampling remain unverified.
