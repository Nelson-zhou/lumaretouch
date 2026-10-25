# Donor-expression numerical core, ABI 1

Status: SOURCE AUTHORED, STATIC REVIEW ONLY, ALL FIXTURES UNRUN. This module is
not installed, loaded, compiled, benchmarked or proven visually. It is not a
complete implementation of LNX-REF-PC-32468-C-0e5f836ef1.

## Contract and module ownership

`expression_blend.h` is the exact C interface. Rust exposes the same stable ABI.
No dependencies, model execution, decoder, filesystem, network, threads, RNG,
identity classifier, donor search or mutable global state exist in this module.
The caller owns source resolution, colour conversion, authentic analysis, manual
review, scheduling/cancellation, immutable snapshots, layer history and export.

- `lrt_expression_blend_abi()` returns 1.
- `lrt_expression_blend_capabilities_v1()` returns 0x3f: bits 0 through 5 are manual
  donor alignment, editable fusion, multiband, colour offset, atomic output and
  cancellation. These are declarations, not runtime acceptance evidence.
- `lrt_expression_blend_max_side_v1()` returns 1024.
- `lrt_expression_blend_max_levels_v1()` returns 5.
- `lrt_expression_blend_v1(...)` processes one reviewed donor/target pair.

Dynamic untrusted plugin loading is not supported or implied. A packaged bridge
must probe the installed ABI and all required symbols before advertising the
capability. Missing, disabled or incompatible native code must leave a saved
active recipe intact but mark it unavailable, refuse render/export that would
silently omit it, and let the user restore the backend or explicitly disable the
layer. Never replace missing output with target pixels and call the edit done.
Explicit layer disable or a validated density-zero recipe is a distinct neutral
operation. No automatic recompilation, download or alternate algorithm fallback.
A future ABI/algorithm change needs a separate declared version and explicit
migration; maintaining ABI shape alone is not permission to change saved results.

## Pixels and coordinate systems

Both sources are exact, unresized rectangular face-context crops from their
source-owned canonical working rasters. Each width/height is 2..1024; each crop
contains at most 1,048,576 pixels. Reject larger crops, never downsample to fit.
Input and output RGBA are tightly packed native-endian float32 linear-sRGB D65.
All RGB components are finite in [0,1], every alpha is exactly 1. Transparent,
HDR, negative RGB, encoded-sRGB, foreign ICC and quantized display buffers are not
accepted by implication. There is no hidden colour conversion or tone mapping.
Full scans also validate unused pixels. Inputs must already satisfy this contract.

Landmarks each contain exactly 478 triples. x/y are finite [0,1], referring to
pixel centres in that exact crop: x_pixel=x*(width-1), y_pixel=y*(height-1).
z is finite in [-2,2] and retained for the input contract but not used by the
2D fit. The adapter must explicitly convert its measured coordinates, not assume
MediaPipe normalized-to-image coordinates have this endpoint convention. Mapping
full-source pixel coordinates to crop coordinates is (x_source-crop_x)/(crop_w-1)
and equivalent for y. All 478 points must fit the context crop; do not clamp.
No template/synthetic landmark backend can authorize a production operation.

The 1024 limit is a real full-resolution restriction, not a quality claim. Large
native faces currently fail before native execution. Future full-resolution
support needs a separate crop/tile provider retaining the same global stable
alignment, sufficient Gaussian pyramid halo, consistent sample phase and global
colour statistics. Tiles must be proven equal to a full-raster reference before
expanding this capability. Source-pixel brush vectors, exact crop rectangles and
algorithm-versioned recipes remain unchanged; do not reinterpret brush radii or
landmarks as proxy-space values. Increasing a build constant alone is not proof
of bounded memory, responsiveness or acceptable large-image rendering.

## Provenance and required reviews

`reviews` must equal 127, with all seven bits set and no unknown bits:

1. Human confirmed that selected target and donor show the same person.
2. Human confirmed the sources belong to the same photographic session.
3. Target landmarks came from its authentic measured detector output.
4. Donor landmarks came from its authentic measured detector output.
5. A human reviewed the two visible face poses as compatible for replacement.
6. Target is assessed unoccluded in the replacement region/anchors.
7. Donor is assessed unoccluded in the replacement region/anchors.

These are caller assertions, not proof produced by the core. Do not pre-check UI
boxes, infer identity from landmarks, use unknown occlusion as zero, fabricate
pose measurements, or reuse review receipts across changed sources/faces. Genuine
measured landmarks are permitted only for positioning, not identity recognition.

There is deliberately no yaw/pitch/roll input array. The existing real-landmark
producer does not retain measured pose angles, so callers must not invent them.
The core derives conservative **2D image-shape compatibility**, not metric 3D
pose: cheek line 234→454 must be at least 16 px, forehead10→chin152 at least24 px,
with positive orientation and absolute normalized axis dot product <=.45.
Screen cheek-line roll is within ±45 degrees, and pairwise difference <=15.
Nose4 projected along the cheek line is in [.30,.70], along forehead→chin in
[.35,.75], with pairwise fraction differences <=.08. Cheek-width/face-height is
[.45,1.5], with target/donor ratio deviation <=.20. Stable-anchor residual gates
below provide another independent compatibility check. These are conservative
original engineering bounds, not validated yaw/pitch estimates or PixCake controls.
A frontal-looking 2D projection does not prove unoccluded or identical pose; human
review must still refuse unknown/strongly turned/incompatible cases. A future
metric solver must be separately documented and qualified rather than relabelling
these 2D ratios as 3D degrees.

## Masks and settings

Lengths are float counts, never bytes. Each mask is one float32 channel at its
own source crop dimensions, finite [0,1].

- `target_allowed`: immutable reviewed target-face eligibility cap, excluding
  unrelated people and background. `donor_allowed` has the equivalent donor role.
  This may be the reviewed interior of actual measured face-oval geometry, including
  eyes and mouth. Geometry is not semantic skin/occlusion detection. Do not use a
  skin-only mask and pretend it supplies whole-expression eligibility.
- `target_protection`, `donor_protection`: hard veto masks. Any positive value,
  including the smallest positive normal, protects the pixel. Target protection
  preserves exact target values. A required positive-weight donor sample touching
  donor protection or zero donor eligibility refuses the operation.
- `fusion`: user-editable target-space mask, each value <= target_allowed. It may
  erase and restore only within the reviewed cap. It cannot override protection.
- `colour_reference`: separately reviewed target-space skin-only reference mask,
  each value <= target_allowed. It is not inferred from the fusion region. The
  native code additionally excludes padded target AND mapped-donor eye/lip boxes.
  At colour_strength=0, NULL with length0 explicitly means no reference; a supplied
  full-length mask is still validated. A null reference at nonzero strength refuses.
  Do not fabricate skin data to fill an unavailable source.
- `density`, `colour_strength`: finite [0,1]. Density is applied once as a final
  linear interpolation. No hidden minimum strength.
- `levels`: integer 1..5; every level before the final one must have both axes >=2.
  Level 1 is the degenerate single-band path, not an extra synthetic algorithm.

Positive donor eligibility at every contributing bilinear tap is required; its
minimum further caps fusion. Unsupported mappings are never edge-clamped into
another donor pixel, hole-filled or generated. Zero-weight bilinear taps are
irrelevant. Zero target fusion and positive target protection stay byte-exact,
including after pyramid-mask diffusion.

## Deterministic algorithm

1. Validate dimensions, all pixels/masks/landmarks, reviews, 2D compatibility and mask caps.
2. Fit a weighted least-squares similarity donor->target from contour indices
   127/356/234/454 (weight 1) and nasal 168/6/197/4 (weight 2). No eyelid, iris,
   eyebrow or mouth landmark enters this fit. The donor expression is transported
   as actual pixels, not deformed back to the target's eye/mouth geometry.
3. Refuse tiny/near-collinear anchor covariance, reflected cross-covariance,
   face width under 16 px, scale outside [.75,4/3], rotation over 15 degrees,
   weighted RMS above max(1.5px,.035*face_width), or worst anchor error above
   max(3px,.07*face_width). No affine shear, dense flow or per-landmark morph.
4. Inverse-map target pixel centres and bilinearly sample actual donor pixels.
   Unedited context is target RGB. Matching source anchors get exact identity
   transform coefficients rather than a nearly-identity numerical perturbation.
5. Optional mean RGB offset uses >=16 effective reviewed reference pixels.
   Mean channel discrepancy over .20 refuses. Requested per-channel offsets are
   limited to ±.06*strength and reduced to keep every edited donor RGB in SDR.
   The code does not clip input data, synthesize texture or remap expression.
6. Build float32 Gaussian pyramids with separable [1,4,6,4,1]/16 filtering,
   clamped-context boundaries and ceil-half decimation. Define Laplacian bands
   against the same bilinear expansion used for reconstruction. Blend donor and
   target bands using Gaussian coverage, then reconstruct.
7. Apply the original effective fusion again as a conservative support cap and
   apply density once. This intentional second support attenuation means a soft
   fusion edge is not identical to plain source-over alpha. It prevents mask
   diffusion from changing protected or erased pixels. In hard-mask interiors
   the cap is one. A shared per-pixel RGB-ray scale attenuates only a derived
   overshooting correction to remain in SDR, recording such pixels; no source
   clipping or independent channel clipping. Output alpha remains exactly one.
8. Publish staged target-sized RGBA, effective fusion coverage and the numerical receipt only after success
   and a final cancellation poll. No history/file/state mutation occurs here.

Pixels/pyramid storage are float32. Fixed-order reduction, fitting, interpolation
and reconstruction use f64 intermediate arithmetic for stability. No random
sampling or worker-order reductions occur. Bitwise cross-architecture/compiler
reproducibility is not promised without qualification. Neutral density, fully
erased/protected fusion, or identical aligned/colour-adjusted source values copy
the original target bits exactly after the relevant validation. Neutral calls
still validate ABI, data, review, 2D compatibility, alignment and target mask caps; donor tap
coverage and colour-reference sufficiency apply only when there is active work.

## Effective fusion output

`effective_fusion` contains target_width×target_height float32 values. It is
exactly min(user fusion, minimum contributing donor eligibility)×density, with
hard target protection forced to zero. Density-zero/fully erased calls return
zero coverage. Identical-colour calls may retain nonzero coverage even when
changed-pixel count is zero. This coverage describes the accepted replacement
support, not per-channel colour change, pyramid attenuation or the gamut limiter.
Use it for the actual mask overlay, never rasterize a second approximation in UI.
The RGBA output already contains the full fused target result: replace the exact
source-owned crop in the host's non-destructive candidate, leaving its exterior
unchanged. Do NOT use effective_fusion to alpha-blend this result over target
again; that would double-apply the mask/density and alter the reviewed candidate.

Hash the exact immutable numeric bytes and retain their shape, byte order,
coordinate convention and crop rectangle in the parent's result lease; PNG display
bytes are not the numeric mask digest. The core itself does not hash or serialize
host recipes. A host requiring portable hashes should explicitly canonicalize
float32 bytes to a documented endianness before hashing and bind that version.

## Numerical receipt

The 16 floats are:

0 a, 1 b, 2 tx, 3 ty for x'=a*x-b*y+tx, y'=b*x+a*y+ty;
4 scale, 5 rotation degrees, 6 weighted anchor RMS pixels, 7 max residual pixels;
8..10 actual linear RGB colour offsets; 11 changed target-pixel count;
12 gamut-limited correction-pixel count; 13 levels; 14 density; 15 colour strength.

This receipt is not an authenticated preview/apply token or source digest.
The parent must bind source IDs/revisions/full raster fingerprints, both FaceRefs,
exact crop rectangles, both original landmark digests and their coordinate
conversion version, all eligibility/protection/fusion/reference digests, exact effective-mask digest,
2D-admission version and human review evidence, settings, algorithm/ABI version and output fingerprint into
one job lease. Cancel, source mutation, selection change or unknown/stale response
invalidates the pending result. Apply must reuse the exact reviewed candidate or
prove an identical frozen render; do not recompute from mutable live inputs.

## Ownership, atomicity and resource limits

The caller owns live aligned initialized allocations of every declared extent
for the complete synchronous call. Inputs stay immutable; outputs are exclusively
writable, disjoint from all inputs and from each other. Read-only input aliases
are permitted. Null, alignment, length, multiplication/address overflow and
output overlap are rejected before raw slices. These checks cannot make arbitrary
pointers safe or verify array ownership. Callback must not unwind, reenter,
mutate or release buffers. Synchronous ABI completion is not OS-transactional
visibility to another thread: the caller must not inspect outputs during the call.

The two source crops require at most 32 MiB RGBA. The six mask arrays require at
most 24 MiB, output 16 MiB, plus 4 MiB effective-mask output and small landmark/receipt arrays. Internal
logical f32 buffers stay below 64 MiB at the declared dimensions/levels; allocator
bookkeeping is additional. All variable allocations use try_reserve_exact and
bounded lengths. The host must budget concurrent jobs, frozen source snapshots,
full documents, queues and retained candidates separately, preferably one active
job per document. No allocation or latency measurement has been performed.

Every nonzero return leaves ALL THREE outputs unchanged. Staging is dropped on error,
allocation failure or cancellation. Panic-unwind is caught at the C boundary;
panic-abort builds and foreign callback unwinds are outside that guarantee.
There is no fallible work/callback between beginning and ending output copy.

Codes: 0 success; 1 ABI/layout/scalar/levels; 2 invalid pixels/masks/landmarks or
unrepresentable numerical data; 3 required provenance/reviews missing; 4 incompatible 2D face geometry;
5 alignment; 6 mask/coverage; 7 colour reference/mismatch; 8 allocation/resource;
9 cancelled; 10 contained Rust panic. A failure never means success/no-op.
