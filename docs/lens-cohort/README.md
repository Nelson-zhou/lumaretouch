# Exact-radius lens cohort implementation slice

Status: SOURCE AUTHORED / ALL EXECUTION AND ACCEPTANCE UNRUN, 2026-10-25.
This document describes actual new source in `core/lens_cohort`, not a claim
that a compiled renderer, 24MP deadline, photographic quality or integration
has passed. No product imports, compiler, tests, builds, inference, downloads,
installs, Git or GitHub writes were performed in this lane.

## Accepted input subset and identity

ABI 2 and mathematical identity `0x00020001` are separate from ABI1. The host
must bind this identity, full native f32 settings, source/refinement identities,
manual-depth acknowledgement and deterministic geometry into recipe/review
identity. Old v1 candidates cannot be silently migrated.

The whole source is borrowed, immutable, contiguous native f32 linear-sRGB D65
RGBA. The entire source is validated once: finite RGB in [0,1], alpha exactly1.
An optional equally immutable f32 refinement plane is validated in [-1,1].
Unsupported HDR, signed-negative RGB and partial alpha are rejected, never
flattened or clipped to fit. Valid signed-zero RGB is accepted. V1 retains its
wider input scope. Manual depth is one explicit native f32 value [0,1]; its
acknowledgement flag is a host gate, not proof of user intent or provenance.
The core never pretends this is inferred AI depth or supports varying depth.

Original radius limit128 and all five original 4×4 midpoint mathematical
apertures remain: disk, rim-weighted disk, rotated pentagon, rotated octagon,
rotated cat-eye intersection. There is no Gaussian substitute, radius/depth
quantization, image downsampling, hidden field interpolation or base subtraction.

## Actual algorithm

1. Compute actual source radii with the unchanged v1 f64 operation order after
   native f32 settings/refinement. r<=0.5 is an exact delta. Non-delta baseline
   and full-blur radii are deduplicated by their f64 bits. Other emitters are
   exact direct residuals. Every emitter belongs to one partition only.
2. Count global residual candidate rectangles clipped to true image bounds and
   exact per-core intersections before successful create. Reject excessive
   total or per-core work, rather than discard feather paint.
3. Cache each active cohort's sampled spatial kernel and signed-offset FFT
   spectrum. The kernel is K(destination-source), not reflected correlation.
   This matters for the odd pentagon. The original scalar FFT is independently
   authored radix2 f64 with no planner, dependency, SIMD or worker threads.
4. Use 254×254 maximum source-grid cores and a halo from the largest actual
   emitting radius. FFT dimensions are next powers of two of core+2halo, at
   most512×512. Read immutable global source coordinates, zero outside the real
   image, retain only the halo-safe core. Artificial tile edges never clip mass.
5. Three complex input pairs carry R+iG, B+iA and mass+i0. There are six 2D
   transforms per active cohort/core, plus one cached kernel transform. All five
   accumulated quantities are normalized by receiving mass, then the existing
   clear blend is applied. This is not physical radiometric flux conservation.
6. Delta emitters, including q=-1, contribute their original RGBA and unit mass.
   q=-1 receivers copy original bytes exactly. A global all-delta job also
   copies bytes. A tile with exactly empty non-delta cohort inputs and no
   residual support rectangle also has an exact identity certificate. A
   radius-zero receiver alone is not an identity shortcut.
7. A positive exact neighboring kernel contribution, together with positive
   self support, proves there is more than one contributor. Without that proof,
   the receiver is recomputed by exact bounded direct gather over every source
   candidate in its halo. Sole-self byte copying is then determined by actual
   contributor counting, never rounded FFT support/mass guesses.
8. Nonfinite or out-of-policy normalized results also use the same reserved
   direct repair. Residual and repair candidates share the unchanged250M global
   direct-pair ceiling; each core has an8,388,608-pair ceiling. Exhaustion rejects
   the core and invalidates the job. A sparse pattern can exhaust support-repair
   work even if its residual budget fits; that is an explicit remaining limit.

The new math ID declares an opaque-only numerical endpoint policy: normalized
RGB in [-1e-9,1+1e-9] may round to [0,1], and normalized alpha within1e-9 of1 is
stored exactly1. Beyond that range or nonfinite values require direct repair or
refusal. This threshold is a design policy, NOT a measured/certified FFT error
bound or permission to clip genuine HDR/nonopaque data. Inputs outside scope
were rejected first. Reordered sums and this policy distinguish the v2 math ID.

## Whole-job counters and memory

The C header is authoritative for exact fields and widths. Expected ordinary
C layouts: Settings44bytes, Budget72bytes, Plan232bytes; runtime ABI/layout
acceptance remains UNRUN. All counts use checked u64 arithmetic. The budget
must explicitly admit FFT butterflies (hard ceiling24billion), kernel quadrature,
classification visits, support probes, shared direct candidates, owned memory
and full sink bytes. No timing claim is derived from those counters.

- validation_pixels is N complete source/refinement validations.
- classification_pixels bounds three N scans (validation, residual-list build,
  delta rendering), three cohort input-fill grids/core, and twice residuals×cores
  for exact core admission and render filtering.
- fft_transform_count includes cached kernel transforms; fft_butterflies bounds
  each radix2 complex butterfly, including both dimensions. These are upper
  bounds when an exactly empty cohort tile skips its transforms.
- kernel_quadrature_evals conservatively reserves16 times kernel samples,
  residual+repair pairs and8 residual-neighbor witnesses. Cached cohort witness
  weights need no new quadrature. support_probe_upper_bound is separately8N.
- owned_plan_bytes includes spectra, spatial kernels, residual records, per-core
  pair counts and a1MiB metadata/allocator allowance.
- required_scratch_bytes includes owned_plan_bytes plus one complex FFT buffer,
  one column, five-f64 accumulation planes and four-f32 staged output planes.
  These are managed allocation payload/reserve calculations, not measured RSS,
  allocator fragmentation, cgroup/page-cache usage or total host memory.
- The immutable source/refinement, external caller output tile and external
  private full-result sink are separate. No full output is allocated in Rust.

For6000×4000, one radius128 cohort with no residuals:384cores,512×512 FFT,
2305transforms,5,438,177,280 complex butterflies,13,597,992bytes core
payload/reserve and1,032,256bytes external maximum output tile. Source and sink
are each384,000,000bytes; optional q adds96,000,000 borrowed bytes. This is a
static derivation, not a benchmark, RSS measurement or120-second capability.
The scalar original FFT may be too slow; measurements determine that gate.

## ABI lifecycle and atomic publication

Create receives already-reserved external sink budget, immutable input spans,
settings/budgets, a cancel callback and out_job/out_plan locations. It checks
spans/nonoverlap, validates the source once, admits work/memory, prepares bounded
plan/kernel caches, and writes the output handle/plan only on success.

render_next requires exact consecutive row-major tile indices. The host obtains
x=(index%tile_columns)*tile_width, y=(index/tile_columns)*tile_height and clips
width/height at true edges. Every tile is assembled and validated privately;
caller output changes only once at successful completion. Callback polls occur
at most every256 direct candidates/pixels and every FFT row/column (line<=512),
plus phase boundaries. Latency measurements remain UNRUN.

Host rules are mandatory: hold immutable bytes/leases until destroy; no concurrent
handle use, mutation, reentrancy or callback unwinding; reserve all host overlaps;
append each successful tile exactly once to a private sink; discard every prior
tile on any failure; publish only after finish confirms complete coverage.
finish itself does not publish, hash, commit, authenticate source identity or
manage document/history/export. destroy releases only core-owned storage.

Invalid pointers, foreign callback faults, external concurrent writes and process
aborts are outside what Rust panic containment can repair. Output atomicity is
not a claim of transactional application integration by this standalone core.

## Authored acceptance and remaining gates

`tests.rs` includes an independently authored direct 4×4 reference, all five
apertures/radius thresholds/rotations, true borders and fixed-core seams, odd
pentagon orientation, exact plateau+feather mass, full protection/neutral/sole
self bits, radius-zero receiver nonidentity, cancellation inside FFT and after
a successful earlier tile, scope/budget refusal, FFI overlap and an explicitly
ignored full24MP plan fixture. Additional fixtures render radius128, inspect both
seam directions and four-core corners, exercise distant nonself contributors,
verify the unaffected-tile certificate with zero repair reserve, and require
invalid ABI tile indices to poison retry/finish without output writes. EVERY
fixture is UNRUN. Compilation, ABI loading,
error tolerances, allocation behavior, no-partial-publication integration,
24MP throughput/RSS/cancellation and photographic inspection remain open.

Dense feathered fields, genuinely varying depth, HDR/partial alpha in this new
backend, edited/RAW source capture, immutable file-backed storage, project reopen,
undo and final streaming export are not implemented by this numerical lane.
The original renderer is untouched; the new subset does not erase those product
requirements. See `../lens-fullresolution/` for the larger acceptance plan.

## Provenance

All new source is original project work, GPL-3.0-or-later. The v1 aperture and
source-radius mathematics are deliberately reused from our original local
`core/lens_aperture/lib.rs`, whose inspected SHA256 is
`2f9f2114f2c2a17e614ca27e198c3b2bbe08e407ee39a8a2c68d9aed5de2b62c`.
That file was not modified. No GEGL, FFTW, RustFFT, NVIDIA or commercial source
was copied, downloaded or linked. Public technique references remain in the
full-resolution research notes, not bundled implementation dependencies.
