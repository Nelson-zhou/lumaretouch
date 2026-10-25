# Primary technique research and open acceptance gates

Research inspected 2026-10-25. These are primary project/author sources, not a
dependency installation, code import, source download, license audit of bundled
bytes, or legal clearance. No third-party implementation was copied into this
lane. Project code remains GPL-3.0-or-later.

## Technique and reuse decisions

### Region-driven evaluation

libvips documents demand-driven image regions and sequential versus random
access. Its design is useful precedent for bounded region pipelines, not proof
that current whole-array Lumaretouch operations can stream. Some access patterns
or input formats still need materialization. Its project states LGPL-2.1-or-later.
Prefer original small region/lease interfaces first; a future libvips codec
adapter needs exact version, dependency closure, color/alpha/precision and
decoder-allocation review.

- https://www.libvips.org/API/8.17/how-it-works.html
- https://www.libvips.org/API/current/developer-checklist.html
- https://www.libvips.org/

### FFT convolution

RustFFT is a mature pure-Rust SIMD-capable FFT implementation, with MIT or
Apache-2.0 license choice. Upstream release 6.4.1 is a concrete candidate, not
an approved/vendored dependency. A tag/release page is not a checked artifact
hash. Its API exposes scratch sizing and explicit-scratch transforms, useful
for admission. Pin the exact crate/source revision, retain the chosen license
and notices, audit transitive crates/features and supported compiler, and record
bytes/hashes before packaging. Do not use changing `master` metadata as the
license/MSRV evidence for an older pinned release. The README's older 'latest'
sentence is not an authoritative version decision.

- https://github.com/ejmahler/RustFFT
- https://github.com/ejmahler/RustFFT/releases
- https://github.com/ejmahler/RustFFT/blob/6.4.1/Cargo.toml
- https://docs.rs/rustfft/6.4.1/rustfft/trait.Fft.html

FFTW is an alternative mature C FFT library. The upstream FAQ says it is GPL;
this does not imply that a proprietary license is required for this GPL
application. Exact selected-version terms/build and packaging obligations still
need review. Prefer RustFFT or an original bounded reference FFT to avoid adding
another FFI/runtime dependency merely for the design. A hand-written reference
FFT is not automatically a performance substitute for a mature SIMD library.
The authors' convolution discussion also supports the distinction between
zero-padded linear and cyclic convolution.

- https://www.fftw.org/faq/section1.html
- https://www.fftw.org/~fftw/pruned.html
- https://fftw.org/fftw3_doc/One_002dDimensional-DFTs-of-Real-Data.html

### Existing lens operation and visibility limits

GNOME's original lens-blur change describes fixed/varying-radius circular blur;
its file carries LGPL-3.0-or-later. Current GEGL API documents the operation, but
this is not evidence of the five Lumaretouch kernels or the current pairwise
depth rule. Direct substitution would require a behavior/ABI/color audit and
cannot close the full feature requirement on the strength of its name. No GEGL
code was adapted here.

- https://mail.gnome.org/archives/commits-list/2020-June/msg00957.html
- https://www.gegl.org/operations/gegl-lens-blur.html
- https://developer.gimp.org/api/gegl/

NVIDIA's author-written survey distinguishes forward/gather image-space blur,
layered approximations and lens-sampled scene rendering. It is useful evidence
that single-depth postprocessing does not reconstruct hidden surfaces. Its
summed-area-table example is explicitly an approximate depth-of-field technique,
not proof that a box filter preserves arbitrary aperture geometry. Use the
papers as technique references only; no assumption about code reuse rights.

- https://developer.nvidia.com/gpugems/gpugems/part-iv-image-processing/chapter-23-depth-field-survey-techniques
- https://developer.nvidia.com/gpugems/gpugems3/part-vi-gpu-computing/chapter-39-parallel-prefix-sum-scan-cuda

### Tiled lossless float storage

OpenEXR's primary documentation supports scanline and tiled access and warns
that tile write ordering can cause buffering. Its upstream license is BSD-3-Clause.
FLOAT, lossless compression and bounded chunk ownership would be required for
canonical storage; HALF or lossy compression is not equivalent to f32 bytes.
OpenEXR is an optional storage alternative, not required for an original raw
canonical blob store. Exact dependency/codec bytes were not acquired or audited.

- https://openexr.com/en/latest/TechnicalIntroduction.html
- https://openexr.com/en/latest/ReadingAndWritingImageFiles.html
- https://github.com/AcademySoftwareFoundation/openexr/blob/main/LICENSE.md

## Acceptance matrix: every item UNRUN

### Mathematical/reference

1. Every aperture, rotation, radius 0/0.5/just-above/1/8/32/128; tiny images;
   dimensions not divisible by tile size; all four true edges and tile seams.
2. Compare accelerated results to direct f64 evaluation of the exact specified
   discrete kernel, separating kernel error, summation error and f32 storage.
   Establish tolerances from actual error analysis and HDR fixtures before
   approval. Do not invent a quality certificate from an arbitrary epsilon.
3. Impulse images prove aperture shape/orientation, especially non-even pentagon
   convolution versus correlation, cat-eye rotation, and rim weighting.
4. Membership partition sums exactly to one per emitter. Constant-depth,
   multiple exact-depth cohorts and residuals reproduce the correct pairwise
   visibility at threshold equality and immediately either side.
5. Full-clear destinations, delta-only operations and sole-self contributors
   preserve exact original bytes. Signed HDR and transparent/partial-alpha
   constant inputs remain valid without hidden clipping or false renormalization.
6. Sparse residual flat and polynomial interval passes match explicit 16-sample
   sums, including tangent/endpoint cases and very large source coordinates.
7. Receiver alpha 0/partial/1 with near/far emitters: no omitted occlusion factor,
   no opaque-background bleed falsely advertised as physical visibility.
8. Paint tile rasterization matches current full-grid f32 output byte-for-byte:
   stroke order, repeated points, overlapping segments, pressure-independent
   event rate, complete polyline points, feather and full-clear after full-blur.
9. Depth full-grid hashes match the existing centre mapping and f32 conversion.
   A uniform-depth certificate is based on actual values, not just provenance.

### Storage, lifecycle and protocol

10. Reader-backed and whole-byte assets produce identical canonical asset IDs,
    including original/ICC, on little/big-endian boundaries and odd dimensions.
11. Modified source file, wrong owner/revision, writable alias, damaged tile,
    truncated blob and inconsistent coverage each fail before publication.
12. Cancel/timeout during classification, field generation, FFT, residuals,
    hashing and display leaves no committed candidate/document/history change.
    Measure cancellation latency; a callback existing is not sufficient.
13. ENOSPC, quota exhaustion, allocation failure, corrupt temporary manifest,
    crash between file completion and manifest publication, and expired leases
    preserve the original and clean only owned uncommitted artifacts.
14. Review expiry does not collect output retained by an unknown apply or actual
    committed document. Existing one-shot submit/readback/receipt fencing remains
    authoritative, with the new numerical identity in exact hashes.
15. Save, close, reopen, undo/redo, duplicated documents and full final export
    retain canonical pixels/provenance after all temporary stage files expire.
16. Old v1 recipes still load under v1 semantics, with no automatic numerical
    migration. New capability and recipe disagreement rejects rather than falls
    back to a different aperture/renderer. No UI claim of AI depth is added.

### Full-resolution performance and usability

17. Real 6000×4000 canonical input, every aperture at useful radii, complete
    output dimensions and full content digest. Test unpainted, large hard-clear
    subject mask, blur plateaus, narrow/wide feather bands and adversarial strokes.
18. Measure classification/field/FFT/residual/I/O/hash/display phases separately,
    end-to-end time and p50/p95 where meaningful, peak RSS AND cgroup/page-cache
    charge, disk bytes and cancellation. Keep hardware/compiler/backend/plan
    versions with the result. Do not label a formula a benchmark.
19. Complete non-neutral current photo capture at 24MP, including the original
    edit stack, must pass independently. A preexisting canonical asset benchmark
    does not establish RAW/edited-source streaming.
20. Dense smooth varying depth plus feathered paint remains an explicit open
    major capability until its exact or explicitly versioned alternative meets
    agreed numerical and photographic quality and runtime gates. Do not replace
    it with a constant plane, quantized depth, or low-resolution final result.
21. Photographic inspection at 100%: point lights, hair, glasses, fine eyelashes,
    translucent edges, strong near/far contrast, smooth gradients, HDR lights,
    rotation and asymmetric aperture placement. Synthetic arithmetic is not a
    substitute for this inspection or comparison with product requirements.

## Release claim permitted today

Only: a source-inspected, primary-source-researched implementation design has
been authored. No 24MP working renderer, streaming asset pipeline, runtime
speed, compiled integration, optical accuracy, or photographic acceptance has
been established by this lane.
