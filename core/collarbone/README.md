# Collarbone: reviewed observed-source 2D contrast, AUTHORED / UNRUN

This original dependency-free Rust core is a bounded **partial** implementation
for `LNX-REF-PC-32465-C-abf0a5c8c9` (锁骨). It is not the referenced product's AI3D
implementation, anatomical detector, physical relighting model, reconstruction or
missing-collarbone synthesis. Official model/assets and proprietary calibration
were not supplied. A manually reviewed trace tells the operator where existing
source appearance may be enhanced; it does not establish what the anatomy is.

No build, import, test, inference, performance measurement or representative-photo
acceptance was executed during this source-only slice. All fixtures are UNRUN.
The coefficient values below are unvalidated original engineering choices, not
claimed vendor values or experimentally established photographic defaults.

## Inputs and host authority

- Exact float32 HWC RGB and float32 HW coverage. RGB is encoded working-sRGB-D65
  SDR, finite `[0,1]`; no alpha, implicit ICC conversion, RGB8, tensor, HDR or
  clipping acceptance. Current RGB and original effective-source RGB are distinct.
- The host authenticates source identity/revision, source transform, selected
  person, review eligibility, visible anatomy and exclusions. The C ABI cannot
  establish provenance or semantic ownership from arrays alone.
- Coverage must be this person's observed semantic body skin intersected with
  reviewed manual support and all exclusion/veto masks. It authorizes both the
  target and the near/far source observations. A narrow trace-only mask that omits
  the farther baseline is unsupported, not permission to sample clothing, another
  person, background or invented fill.
- One or two independent traces, each 3..8 points. Normalized point coordinates
  use the shared **pixel-edge** convention `(x*W-0.5,y*H-0.5)`, strictly inside
  normalized `(0,1)`. IDs are image/screen `left` or `right`, not inferred anatomy.
  Width is the enhancement band's **half-width** divided by `min(H,W)`.
- Half-width on the actual supplied source grid must be 4..256 pixels, without
  clamp/resampling. Every segment must be at least 2 pixels long, total length at
  least twice its half-width, no self/cross-curve intersections, and neighboring
  forward segments must have positive dot product. Unsupported geometry refuses;
  there is no trace repair, absent-side mirroring or reconstruction.
- Scalar amount is `[0,1]`. Neutral is exact zero, not a negative or relight mode.
  Canonical source eligibility/manual review is the host's responsibility even
  if source-grid numeric inputs happen to be accepted here.

## Original source measurement

The source is prepared independently of amount and independently of current-stage
RGB. The native field is a bounded **signed natural-log luminance gain**, never
an additive RGB patch and never a new positive ridge synthesized from geometry.

For each trace with half-width `w`:

1. Decode source sRGB to linear RGB; use Rec.709/sRGB luminance coefficients
   `(0.2126,0.7152,0.0722)`. Source evidence is `log(max(Y,1e-6))`. The floor only
   prevents log singularity; near-black reliability is zero, so it cannot create
   recovered detail.
2. Form a narrow real-source square average with integer radius
   `r=max(1,floor(w/4))`. Coverage-normalized sums include **only** nonzero owned
   source pixels. A valid mean requires its entire square in the real source
   window, nonzero center coverage, weight at least 1 and mean coverage at least
   0.20. Unsupported means remain NaN sentinels and are never rendered. This
   narrow mean avoids applying raw pore/noise-scale residuals directly; it does
   not prove every pore, JPEG artifact or noise frequency is suppressed.
3. Project each candidate output pixel onto the nearest reviewed polyline
   segment. Interpolate normalized neighboring vertex tangents to obtain its
   local normal. Distance-to-trace and distances along the trace from both
   endpoints give smoothstep permission tapers. Support is strictly inside the
   half-width band, with no extension beyond trace endpoints.
4. Bilinearly sample the narrow log means at the pixel and at symmetric locations
   `pixel ± 2*w*normal`. Every nonzero bilinear tap must have nonzero owned
   coverage and a valid narrow mean. All three complete filter footprints must
   lie in genuine source pixels. No reflection, replication, truncated windows,
   unsupported zero-as-observation, extrapolation or synthetic halo is used.
5. Observed signed residual is `center-(far_minus+far_plus)/2`. Positive source
   residual can brighten; negative source residual can darken. A flat source
   gives exact-zero admitted gain because the minimum-signal gate rejects tiny
   numerical residue. The trace does not by itself generate any light or shadow.
6. Source reliability is smoothstep from linear luminance 0.005 to 0.03,
   multiplied by the inverse smoothstep of encoded-channel maximum 0.94..0.995.
   Use the minimum of target-pixel reliability and the three coverage-normalized
   mean reliabilities. Reliability <=0.05 refuses the pixel.
7. Minimum-signal gate ramps absolute observed residual from 0.010 to 0.040.
   A conservative excessive-residual gate fades 0.35..0.70; a farther-side
   asymmetry gate fades absolute far-minus/far-plus difference 0.30..0.70. These
   heuristics can reject valid anatomy and cannot universally identify clothing,
   cast shadows or lighting ambiguity from one photograph.
8. Prepared field is coverage × band/end taper × reliability × signal gates ×
   `0.12*tanh(0.65*residual/0.12)`. Thus magnitude is at most 0.12 natural-log units,
   and its sign cannot oppose the observed residual. Overlapping trace bands do
   not add twice: nearest normalized trace distance owns the pixel; stable
   screen-side order breaks exact ties. This is conservative, not a seam-free
   guarantee for arbitrary overlapping traces.

No source detail is transplanted from another person or side. Near-black,
clipped/highlight, unsupported, ambiguous or insufficient-signal pixels remain
zero evidence. Genuine low contrast or true high-frequency detail may also be
refused. This is an appearance edit, not a measurement of bone geometry.

## Current-stage composition and tiles

`prepare(reference_rgb, coverage, curves, cancelled=...)` returns a
`PreparedCollarbone` containing an owned read-only float32 ROI field, its integer
full-source `(x,y)` origin, full-source `(H,W)` and JSON-safe diagnostic dict.
The host must invalidate it whenever source/review/person/transform identities
change; the object is not self-authenticating or a portable recipe.

`compose(current_rgb, prepared, amount, origin=(0,0), cancelled=...)` or
`compose_field(current_rgb, field, amount, field_origin=..., source_shape=...,
origin=..., cancelled=...)` applies already prepared evidence. Independent field
and current tile origins are validated against the same source grid. Regions
outside the field are exact zero. A crop of a prepared field is valid; deriving a
new field from an edited intermediate or a viewport/proxy is not.

For each current pixel, decode to linear RGB, set `d=amount*field`, and choose one
common scalar gain. Requested gain is `exp(d)`. Positive gain is constrained to
`min(exp(d),1+(1/max(linearRGB)-1)*(1-1e-12))`; negative gain needs no upper-gamut
reduction. All channels receive the same gain, then encode to sRGB. This preserves
linear-RGB channel ratios, not a claim of invariant perceptual hue under every
other pipeline effect. There is **no independent channel clipping**. Gain may be
fully blocked by an already saturated current channel. Exact amount/field zero,
all-black current and all-white current are bit copies, including signed zero.

Composition has no spatial dependencies. Preparing once and composing that field
in disjoint current-stage tiles uses the same arithmetic per pixel as full-grid
composition. Narrow-mean preparation itself depends on real source neighborhoods
and is never rerun independently on cropped output tiles. Repeated composition
onto a previous result compounds the edit and is forbidden by host replay rules.

## ROI, memory, cancellation and FFI

The wrapper finds the union of trace-band output bounds. It expands them by a
real halo of `ceil(2*w+max(1,floor(w/4))+2)` using the largest trace width, covering
any normal direction, narrow filter and bilinear corner. It clips only to actual
source bounds; border samples are refused, not filled. There is no caller-remap
of normalized source geometry. Disjoint far-apart traces can make a large union
ROI; resource admission may refuse it rather than silently use a proxy.

Limits: source dimensions 1..65,536, total source pixels at most 32,000,000, total
operator-accounted memory at most 4 GiB. These are refusal limits, **not** proof of
24 MP speed, whole-process memory safety, OOM immunity or acceptable UI latency.

- Preparation snapshots use 16 bytes/sample pixel (RGB+coverage).
- Rust peak filter scratch is 32 bytes/sample pixel: three f64 horizontal sums
  plus two f32 mean/reliability values. Curves run serially; prior filter scratch
  is dropped, never multiplied by curve count.
- Prepared output uses 4 bytes/field pixel. Small point/statistics buffers and
  bounded validation copies are covered by an 8 MiB allowance.
- Pure `memory_estimate(shape,curves)` returns `48*sample_pixels+4*field_pixels`
  plus 8 MiB, additional to caller-owned source/coverage. The absolute check also
  counts 16 bytes/full-source pixel already owned by that caller. If no curves
  are supplied, it conservatively charges a full-grid evidence/output window.
- Before allocation the wrapper also consults the existing fail-closed cgroup
  memory estimate. The host must account separately for any unallocated coverage
  raster, retained layers, current image, other operators and whole-job budget.
- Composition charges 12 bytes/current pixel snapshot, 12 bytes/output pixel,
  and 4 bytes/supplied field pixel snapshot plus allowance. Its absolute check
  additionally counts caller current/field arrays. A small tile does not incur
  full-source filter allocation or re-estimation.

Rust preparation is bounded O(sample pixels × curves + output pixels × reviewed
segments), with at most two curves and fourteen segments total. Validation,
allocation filling and numeric loops poll cancellation at least every 256 pixels
or each row/column. Python snapshots/verification poll in row chunks of <=4096
pixels. Allocation calls themselves cannot be interrupted. Callback exceptions
are captured and reraised only after Rust returns; callback must not reenter,
mutate buffers or unwind across FFI.

ABI v1 is in `collarbone.h`. All sizes count elements. The caller provides valid
aligned live allocations, immutable input and exclusive nonaliasing output.
Aliases are rejected before creating native mutable slices. Panic is contained,
not a defense against invalid foreign pointers, faults or process abort.
Statuses: 0 success, 1 ABI/shape/alias, 2 settings/geometry, 3 pixels/numerics,
4 cancelled, 5 resource refusal, 6 contained panic. Discard **all** outputs on any
nonzero status. Private partial writes are never success/publication authority.

Successful preparation can still have zero observed support. Diagnostic status
and counters distinguish no reviewed band, no owned coverage, real source-border
refusal, unsupported source samples, unreliable source and no observed signal.
`admitted_pixels` aliases `supported_pixels`, the exact count of nonzero field
pixels. Active host application must refuse a zero-admission result instead of
reporting a successful enhancement. Partial support is explicitly labeled.

## References, licensing and acceptance remaining

Conceptual primary references, researched separately and recorded in
`docs/collarbone/REQUIREMENT-AND-RESEARCH.md`:

- [darktable tone equalizer manual](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/tone-equalizer/):
  luminance-guided/log-domain editing and preservation of source detail.
- [Local Laplacian Filters author project](https://people.csail.mit.edu/sparis/publi/2011/siggraph/):
  conceptual context for controlling detail/halos. This core is **not** a Local
  Laplacian implementation and does not claim its quality guarantees.
- [Guided Image Filtering author project](https://people.csail.mit.edu/kaiming/eccv10/index.html):
  background for guide-aware/source-support reasoning, not a claim that the narrow
  source average here implements the published guided filter.

No vendor code, darktable implementation, paper prose, image, dataset or model is
copied/vendored. All code here is original GPL-3.0-or-later. A public description
is not a software redistribution license; no unverified-license archive was
fetched. The authored offline build script is `packaging/build-collarbone.sh`,
producing `bin/liblrt_collarbone.so`; it must not auto-run at runtime.

Before acceptance: compile Rust; execute ABI and numerical fixtures; test owner,
review and source invalidation; test full/tile/current-stage integration; inspect
trace joins/band boundaries, strong shadows, clothing, occlusion, noisy/JPEG and
low-light sources, highlight/near-black gates, varied skin tones and anatomy,
original/derived and PNG16 preview/export; measure real memory/latency; verify
cancellation and publication fences. Manual fallback remains visibly distinct
from unavailable AI3D. Passing static source checks cannot establish any of these.
