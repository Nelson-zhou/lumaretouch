# Renderer contract and algorithms

Status: DESIGN ONLY; all numerical, performance and photographic acceptance UNRUN.
The mathematics below is independently derived from the current local numerical
definition. It is not copied GEGL, NVIDIA, or commercial filter implementation.

## 1. Preserve the actual operation

Let P(s) be four-channel, linear-sRGB D65, premultiplied f32 RGBA. Preserve signed
RGB/HDR and the existing finite premultiplication envelope. Let z(s) be the
existing f32 near-zero/far-one relative depth and q(s) the f32 signed refinement.
Compute source radius r(s) using the existing f64 operation order and settings
converted through their existing f32 native layout. Do not key cohorts using
unrounded UI doubles instead of actual native values.

For integer destination p and emitter s, define the existing discrete kernel:

    r <= 0.5: K_r(p-s) = 1 exactly when p=s, otherwise 0.
    r > 0.5:  K_r(d) = sum over 16 midpoint samples of T((d+offset)/r)
                       / (16 * aperture_unit_mass * r*r).
    offsets = {-3/8, -1/8, 1/8, 3/8} on each axis.

T is exactly the selected existing disk, rim-weighted disk, rotated regular
pentagon, rotated regular octagon, or rotated cat-eye intersection. The rim is
T = 0.25 + 0.75*(u*u+v*v) inside the disk. No aperture-family substitution.

The existing pairwise visibility and output are:

    V(s,p) = 1                             if z(s) <= z(p)+tolerance
             1-alpha(p)                    otherwise.
    A(p) = sum_s V(s,p)*K_r(s)(p-s)*P(s)
    M(p) = sum_s V(s,p)*K_r(s)(p-s)
    clear(p) = max(-q(p), 0)
    result(p) = (1-clear(p))*A(p)/M(p) + clear(p)*P(p).

This normalization is receiving-mass normalization, not physical radiometric
flux conservation. It is a single-depth 2.5D visibility rule, not lens ray
tracing, multilayer transmittance, or recovery of hidden background. Transparent
emitters still contribute their kernel mass under the existing definition.
Do not reinterpret that mass as emitter alpha or silently change the rule.

`q(p) == -1` copies the exact original destination bytes. A radius-zero/delta
whole operation also copies bytes after input and backend validation. Preserve
the existing sole-self-contributor exact-copy rule through an exact support
proof or direct local evaluation, not an epsilon guess on FFT output.

## 2. Fast path: exact-value cohorts, not radius/depth bins

Partition every emitter into exactly one cohort or the residual set. A cohort
has exactly identical (z_f32_bits, r_f64_bits). Signed zero can be normalized
only after proving identical comparison/radius semantics; the initial version
can simply retain the bits. Membership is binary, not an approximating blend.
For a global constant depth certificate, grouping only r is sufficient.

For cohort g, with binary membership B_g:

    A_g = K_r(g) * (B_g * P)       [four convolutions]
    M_g = K_r(g) * B_g             [one convolution]
    V_g(p) = 1 or 1-alpha(p), using exact z_g > z(p)+tolerance.
    A = sum_g V_g*A_g + A_residual
    M = sum_g V_g*M_g + M_residual.

The result is algebraically the same finite sampled operator in real arithmetic.
Summation and transform rounding are not bit-identical to ABI 1.

- Constant manual depth makes V identically 1. Prove constant actual sampled
  f32 depth, not merely a provenance label. Preserve the current bilinear depth
  mapping and conversion; scan the resulting field or prove its exact bits.
- Full-clear plateaus produce r=0; full-blur plateaus produce r=max_radius.
  Unpainted pixels usually share a baseline radius. All these are genuine exact
  cohorts. The receiver clear blend still runs after source spreading.
- Process a delta cohort directly, without FFT.
- Feathered/partial paint remains exact. Frequently repeated exact radii may
  form more cohorts; other emitters remain residual. Do not round them into
  nearby cohorts. A small deterministic histogram/candidate pass followed by
  exact counting avoids allocating one hash entry per image pixel.
- Partition out residuals BEFORE convolution. Do not convolve a complete base
  and subtract a second large blur; this avoids avoidable signed mass
  cancellation. All mathematical mass additions remain nonnegative.
- A genuinely varying depth field with few exact (depth,radius) values may use
  the same formula, with per-cohort visibility. Continuously varying depth can
  have almost N cohorts; do not choose N FFT passes or claim constant-depth
  acceleration applies to it.

Choose cohort count and residual strategy using complete prospective work
bounds. Start with at most four non-delta cohorts as an implementation limit,
not a correctness limit: remaining emitters must be evaluated, or the exact
request must be refused before publication. The cost model must compare direct
gather, cohort convolution, and residual enumeration, not always choose FFT.

## 3. Bounded overlap-save convolution

For output core Bx by By, use actual halo h=ceil(r+0.5), never the receiving
pixel's radius. Choose Fx >= Bx+2h and Fy >= By+2h, normally power-of-two FFT
extents. Read the source rectangle core expanded by h; zero-pad only outside
the real image. Place the discrete kernel at signed offsets modulo the FFT
extent. Inverse-transform and retain only the core corresponding to the fully
available halo. Do not confuse convolution with correlation: the pentagon is
not centrosymmetric. Never reflect the aperture by assuming all kernels are
even. Normalize the inverse transform by Fx*Fy exactly once.

Keep source-space coordinates global across tiles. Artificial tile edges have
no clipping, reflection, replicated borders or independent mass renormalization.
Only true image bounds clip emitters. The mass plane accounts for this clipping.
For a single all-image cohort, a precomputed summed-area table of the SMALL
discrete aperture kernel gives clipped-image mass by four lookups; this is not
a box-blur approximation of the aperture.

RGBA channel pairs may be represented as R+iG and B+iA through a complex linear
convolution with a real spatial kernel. Two forward/inverse transform pairs
carry four channels. A membership mass pass needs another pair unless a proven
constant/all-image special case supplies exact mass. Audit this pairing against
separate-channel reference transforms before optimizing it.

Suggested initial geometry retains the existing 65,536-pixel output-tile limit:
at radius 128, h=129, Fx=Fy=512 and Bx=By=254. A 6000×4000 image needs 384 tiles.
The FFT input area processed per transform type is 100,663,296 points. Six 2D
complex transforms per tile/cohort mean 603,979,776 point-visits, or about
5.436 billion radix-2 complex butterflies, excluding kernel setup, masking,
transposes, I/O, fields, validation and residuals. The single all-image cohort
can omit the membership FFT and use four transforms instead. These are derived
counts, NOT measured milliseconds or a promise of the 120-second deadline.

Cache one bounded kernel spectrum at a time, or reserve every cached spectrum.
Use one worker initially; additional workers require aggregate scratch leases.
Query/plan exact FFT scratch before admission, including planner allocations.
Poll cancellation between bounded batches of 1D row/column transforms and
transpose blocks. Do not enter an uncancellable full-image FFT.

## 4. Residual interval splat: exact samples, not exact pixel area

All current support sets are convex. At each emitter s, destination integer y,
and one of four vertical subpixel offsets eta, intersect a horizontal line with
the radius-scaled, rotated aperture. This gives a horizontal interval [L,U].
For each horizontal offset xi, contributing destination integers satisfy:

    ceil(s.x + L - xi) <= x <= floor(s.x + U - xi).

Clip to real output bounds and the current output stripe, not to source-tile
bounds. Compute endpoints conservatively and check adjacent integer candidates
with the exact current transmission predicate so sqrt/rotation rounding cannot
drop a boundary sample. Empty/tangent intervals must be explicit.

For the flat disk/polygon/cat-eye kernels, add the same weighted five-vector
(premultiplied RGBA, mass) to the interval using start/end difference events,
then prefix-sum the row. This is O(sum_s (2h_s+1)*16 + output_pixels), not
O(sum_s h_s^2). Nearby horizontal offsets can merge equal endpoint events;
that is an optimization only after the unmerged reference is verified.

The rim weight is a degree-two polynomial in the receiving x for fixed y and
subpixel offsets. Maintain three difference coefficient planes per output
channel/mass, then evaluate the polynomial at each x. Use stripe-local x origins
to avoid unnecessary large-coordinate cancellation. Expanding the polynomial
changes floating operation order, so it belongs to the new math identity.
An exact test oracle must still use the existing rotated u/v predicate and
transmission, not assume finite-precision sin²+cos² equals exactly 1.

Shape intersections:

- Disk: circle/line quadratic roots.
- Pentagon/octagon: intersect the rotated half-plane inequalities with the
  scanline, including the existing enclosing unit-disk predicate.
- Cat-eye: intersect the two rotated disk/line root intervals, including the
  existing enclosing-disk predicate.
- Rim: disk support plus quadratic transmission coefficients.

An unmerged conservative radius-128 bound is 16×259 intervals, 8,288 endpoint
events per residual emitter, with five scalar fields, or fifteen for polynomial
coefficients. A dense 24MP field would therefore require about 99.5 BILLION
intervals before reconstruction. O(NR) is much better than O(NR²), but this is
not a viable blanket 24MP/120-second claim. Use interval splats for genuinely
sparse residuals; choose direct sparse splats when small radii make them cheaper.
Count event creation, coefficient arithmetic and reconstruction separately.

## 5. Genuinely varying depth

A plain difference-row splat is WRONG when visibility varies across receivers:
one emitter's interval can contain both blocked and visible pixels.

Initial exact path: region-based receiver gather with immutable halo input and
the existing V(s,p), under the unchanged total direct-tap budget. Source radius,
all five kernels and clear/blur corrections remain intact. This solves bounded
working memory, not general 24MP throughput. A refusal must identify work, not
masquerade as unsupported aperture or ask the user to lose their paint.

Possible second exact accelerator: for one output row/stripe, produce interval
start/end events carrying emitter depth and five-vector coefficients. Sweep x
while maintaining a balanced prefix-sum/Fenwick index over exact emitter-depth
keys. The current visibility is equivalent to:

    visible_sum = all_sum - alpha(p)*sum_of_emitters_with_z > z(p)+tolerance.

Apply this to numerator and mass, and to each polynomial coefficient for rim.
Depth keys must be exactly ordered f32 values, with threshold computed in the
existing f64 order. This preserves the pairwise rule without quantized layers.
It costs roughly O(E log D + N log D), with E interval events and D active exact
depth keys. Event sorting, storage, subtraction stability and prefix index
updates require their own bounds. Spill/sort is not free; a stripe cap alone
does not prove a global RAM bound. This is a research implementation milestone,
not an already usable wide-radius dense-depth solution.

For cancellation-prone `all - alpha*far` when visible mass is tiny, evaluate
the near-prefix and (1-alpha)*far contributions directly instead, rather than
subtracting two nearly equal large numbers. Still check accumulated error and
refuse/fall back if the output contract cannot be maintained.

## 6. Numeric version and reliability

Preserve `lnx.lens_blur.v1`, recipe version 1 and ABI 1 behavior. Do not silently
serve an FFT output through a saved v1 numeric identity. Introduce a separately
versioned renderer/operation recipe and negotiate it through host/UI/native
capabilities. It must identify aperture-sampling rule, field-sampling rule,
source-radius rule, visibility rule, accumulation/FFT implementation and version,
and deterministic plan/tile geometry. A v1-to-v2 migration requires an explicit
new review; old candidates are never reinterpreted. Candidate recipe hashes,
result identity and replay fences must bind this math identity.

Start with f64 transforms, coefficients and accumulators, one final f32 store.
Reject nonfinite values, nonpositive mass, invalid alpha or broken premultiplied
HDR bounds. Do not clip, unpremultiply/re-premultiply, or clamp a small negative
FFT alpha to conceal error. A bounded direct recomputation queue may repair
numerically suspect pixels using the same mathematical request, with its work
reserved before rendering. If that queue would exceed admission, discard the
candidate and report a numerical/work refusal.

Exact support-count metadata or direct local checking must establish the
sole-self-copy optimization. Do not round an FFT support count to an integer
without a proven error bound. A constant-image certificate can preserve exact
constant pixels where mathematically justified. It is not a replacement for
general HDR/alpha acceptance. The FFT library itself does not certify this
application's numerical error or optical quality.

## 7. Analytic pixel-area kernels are a distinct later semantic change

The interval algorithm above is exact for the specified midpoint samples in
real arithmetic; it is NOT exact integration over a destination pixel box.
For constant-radius cohorts, a better pixel-area kernel can be precomputed
cheaply relative to image work, but must receive a distinct sampling version:

- Polygon: clip the rotated aperture polygon against each destination pixel
  square, then integrate area.
- Disk: split circle/square intersections at analytic boundary breakpoints and
  integrate circular-segment antiderivatives.
- Rim: integrate area and x²+y² moments over the clipped disk.
- Cat-eye: integrate the intersection of both rotated circles and the pixel
  box, splitting at circle/circle and circle/box boundary changes.

These yield analytic-to-floating-roundoff geometric integrals, not exact real
arithmetic. Tangencies, very small radii, rotation, finite precision, aperture
mass and positivity need dedicated tests. Do not change only circular blur and
quietly leave the other four apertures on an unlabeled lower-quality path.
