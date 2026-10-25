# First implementable module and parallel source lane

Status: RECOMMENDED IMPLEMENTATION BOUNDARY / not implemented / ALL ACCEPTANCE UNRUN.

## Concrete first slice

Author a separate `core/lens_cohort` module with an original bounded
radix-2 f64 FFT, the same five mathematical 4×4 midpoint aperture kernels,
exact radius cohorts, and bounded direct feather residuals. No new runtime
dependency is necessary for this first reference implementation. Do not edit
`core/lens_aperture` or reinterpret its ABI/saved v1 semantics.

The first accepted input subset is explicit:

- already-existing immutable canonical full-resolution RGBA bytes;
- exactly opaque alpha=1 and RGB within [0,1], matching the current host's
  opaque-SDR return scope, with no clipping to manufacture that scope;
- an explicitly acknowledged constant manual depth, resolved to the actual
  native f32 depth value through the existing source/field contract;
- any of the five current apertures, their full rotation/radius ranges, and
  complete ordered clear/blur strokes, provided exact residual work is admitted.

This does NOT make ordinary 24MP neutral JPEG/PNG/TIFF import work: the existing
importer still has a 96N preflight. It does NOT make 24MP RAW or non-neutral
edited-source capture work. Those are parallel source-lane prerequisites.
It does NOT imply that broad feather paint or varying depth already fits.
Alpha/HDR support in the original renderer is preserved, not removed or silently
flattened. The new backend advertises its narrower initial scope honestly.

## Exact cohort and residual classification

Normalize settings exactly once through f32, then compute the baseline radius
using the existing f64 source-radius order at q=0 and the certified f32 depth.
At every emitter, compute actual r from actual f32 q with that same operation
order. Classify by the resulting f64 bits, not a radius rounded to an integer:

1. r<=0.5 belongs to the exact delta class, regardless of q.
2. r exactly equals the baseline radius: baseline cohort.
3. r exactly equals max_radius converted from native f32: full-blur cohort.
4. Otherwise: direct residual.

Merge identical baseline/max cohorts; delta never needs an FFT. q=-1 is a
receiver exact-copy instruction AND an emitter whose radius is delta. Do not
discard it from the emitter mass. q=0/r=0 at a receiver is not proof its result
is original: blurred neighbors can still contribute. A global all-delta proof
does justify exact byte-copy output after validation.

A third non-delta cohort may be added only as an exact repeated radius with
bounded classification/counting; it is not required to ship the first module.
Every emitter belongs exactly once. Residual emitters are EXCLUDED from cohort
masks before convolution. There is no approximate radius binning or subtractive
base-blur correction.

## First numerical API boundary

Use safe Rust functions first; expose a small, separately versioned C ABI only
after its owner fixes exact layouts and lifetime rules. The numerical owner is
implementing `core/lens_cohort`; it is the sole authority for the actual header,
symbols and struct layouts. The accepted lifecycle shape is an opaque Job
created after preflight, bounded tile-next calls, finish and destroy. The design
below describes responsibilities, not a second competing ABI:

    inspect_plan(immutable_source, optional_immutable_q, extent,
                 constant_depth_f32, settings, explicit_budgets, cancel)
      -> ValidatedPlan { math_identity, cohort_radii, geometry,
                         work_counts, required_scratch_bytes }
    render_core(immutable_source, optional_immutable_q, validated_plan,
                output_rect, private_output_tile, caller_scratch, cancel)
      -> success or typed failure; output unchanged on failure

Source and q are immutable owned bytes-backed read views, NOT arbitrary mutable
arrays whose snapshots were removed merely to save memory. The host owns their
leases during every native call and binds source/recipe hashes. Native pointer
span, alias, layout, dimensions and finite/range checks remain mandatory. No
file I/O, document publication, Python inner-pixel callback or inferred depth
belongs in this core. A plan is bound to its source/q/settings identity; changed
inputs require reinspection. Native input lifetimes must remain valid across
GIL release, and cancellation callbacks must not mutate/reenter/free them.

The initial tile path can reread/classify its bounded halo directly from those
immutable arrays. This avoids a full per-pixel radius array or per-image hash
map. The preflight scans source/q once to validate and compute global exact
work. Later repeated halo reads/classifications are counted in plan work.

## Exact residual admission before rendering

For each residual emitter, let h=ceil(r+0.5). Its conservative destination box
is [sx-h,sx+h] × [sy-h,sy+h], clipped to the real image. Count its integer area
with checked u64 arithmetic. Sum those areas for the full request; this is a
direct emitter/destination candidate count, NOT N times the maximum radius.
The implementation may tighten the bound from exact support, but cannot claim
that a heuristic estimate is an upper bound.

The planned render evaluates this box partitioned by disjoint output cores.
Each actual source/destination pair is evaluated once; no pair is lost at a tile
edge. Per-core candidate bounds can be accumulated by intersecting each emitter
box with affected output-core rectangles. Reserve that small core-count table.
This proves both total and per-call direct work before any output is produced.

Keep separate checked counters for:

- source/q validation and repeated halo-classification pixels;
- FFT grid extents, transform count, radix-2 complex butterfly count, transpose
  and mask/accumulation work, kernel sample generation;
- residual direct candidate pairs and at most 16 quadrature samples per pair;
- any direct numeric/support-proof repair queue, sharing the direct-work budget;
- field rasterization work and canonical/hash/display work at the host layer.

Retain the existing 250M job direct-candidate ceiling and existing 64M actual
refinement-pixel ceiling. Do not allocate a second 250M budget for repair.
Keep individual direct batches/calls bounded; the existing 8,388,608-candidate
tile limit is a suitable conservative first bound. Reject or choose a smaller
plan BEFORE rendering if per-core work cannot fit. FFT work gets its own
explicit finite budget in the new plan; it is not falsely counted as free or
as a smaller number of old taps. Default production FFT/time limits require
measurement. The host's overall 120-second deadline remains authoritative.

An interior radius-128 residual emitter has a conservative 259²=67,081-pair
box. A 250M direct budget therefore fits at most 3,726 such emitters before any
repair work. This is a meaningful limitation: a large soft brush may have many
more residual pixels. It must be reported, not rounded into plateau radii or
called a complete 24MP painting solution. The interval residual design in
RENDERER-CONTRACT.md is the next exact optimization for this gate.

## Opaque convolution optimization and hazards

For the proven opaque input subset, mathematical output alpha is exactly 1.
Convolve R+iG and B+iMembership for each cohort. This carries RGB numerator and
the cohort mass in two complex convolutions, four transforms total. Direct
residuals add RGB and mass; the delta class adds its original RGB and unit mass
at the same destination. Store alpha=1 exactly only because the validated
opaque/visibility contract proves it, not as an alpha fixup. Full-clear
destinations copy all original f32 bytes, including valid signed zero.

The membership imaginary channel is independent from B, not source alpha.
Check paired-channel output against independent real-channel reference tests.
Kernel placement must be K(destination-source): a rotated odd pentagon exposes
the common convolution/correlation error. Place negative kernel offsets modulo
FFT dimensions and retain the true halo-safe core. Inverse scale occurs once.

Use f64 scratch and arithmetic, then validate before final f32 storage. A tiny
negative or >1 RGB from FFT error must not be clipped. Recompute suspect pixels
directly if reserved work allows it; otherwise refuse/discard the candidate.
Sole-self-contributor exact copy needs an exact local support proof/direct check.
Never infer it from a near-integer floating FFT count or near-equal output RGB.

At radius128, a 512² FFT with 254² cores keeps each output core below 65,536
pixels. One 24MP image needs 384 cores. Two packed channel pairs yield
402,653,184 transformed grid-point visits and about 3.624 billion radix-2
complex butterflies per non-delta cohort, excluding other work. This is only a
derived upper work description; original scalar Rust FFT may or may not meet
the deadline. Keep mature audited RustFFT reuse as a later backend option if
measurements show the original implementation insufficient.

## Bounded sink and transitional whole-byte output

The core writes only caller-owned private tiles. A NEW host adapter may target
a private canonical tile sink from the storage lane. As a transition, it may
target one private full-resolution output allocation, then freeze it to bytes,
ONLY when actual simultaneous memory and retained-payload accounting fit.

For N pixels, account at least:

    retained source and provenance
    + 16N mutable/private output
    + 16N immutable output during freeze, if conversion copies
    + q field and its conversion overlap, if present
    + admitted native scratch and plan
    + display/JSON/validation reserves
    + all preexisting host/editor memory and allocator allowance.

At 24MP the source is 384MB and each output copy another 384MB. This can be
materially below the old 128N stage allowance, but must be proved using the
actual dataflow and available memory, not simply by lowering a coefficient.
Existing source/candidate retained accounting charges provenance in both
records: with 100MB original, source+candidate is about 968MB before displays,
depth and ledger, not 868MB. Existing 1GB retained and 2GB working caps stay.
Do not assume physical byte sharing changes current logical admission.

Full resolution is retained even in this transitional whole-byte path. It is
not end-to-end streaming and must not be documented as such. Original import,
non-neutral edited capture, RAW and native asset/history/export region consumers
remain assigned to the parallel source/storage integration lane.

## Ownership that can be parallelized immediately

1. Numerical lane: new core directory only; contract, kernel, original FFT,
   plan counts, cohort/direct render, UNRUN fixtures. Preserve all v1 files.
2. Source/storage lane: new region reader/sink/lease interfaces and bounded
   import design; identify exact shared importer/capture/AssetStore changes for
   their integration owner. Do not pretend existing consumers stream.
   The initial importer owner is separately authoring
   `creative_document_import_bounded.py` for bounded original JPEG/PNG transfer;
   source authorship alone is not evidence that import is integrated or accepted.
3. Field lane: new exact tiled stroke rasterization with local work accounting;
   compare authored fixtures to existing byte definition, execute only when
   authorized. Full paint semantics must survive.
4. Integration owner: new v2 math/recipe/capability identity, separate bridge and
   stage, existing owner/review/commit fencing. No auto migration or v1 hash reuse.

First completion claim is limited to authored/validated scope. General 24MP
lens capability requires actual import/capture, painted fields, sink/publication,
throughput and photographic acceptance. Dense varying-depth performance remains
a mandatory later core milestone, not removed from the product requirement.
