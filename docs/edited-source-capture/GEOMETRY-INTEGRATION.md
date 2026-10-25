# Explicit capture strategy 2: bounded arbitrary-angle geometry

Requirement LNX-REF-WF-165438-165adae6a7 remains partial. This extends the
existing full-source lens path, not a new lens algorithm or automated depth.
All runtime, numerical, photographic and memory acceptance is UNRUN.

## Why geometry is deferred only in this cohort

The existing `ops.geometry.rotate_np` returns float64 for an unsnapped angle.
The generic exporter subsequently calls PhotoDetail even when neutral, and its
input validator rejects float64 before reaching its neutral identity return.
Active colour-grading/selective-colour finishing also rejects this dtype.
Simply swapping in a bounded rotation callback would therefore leave the
ordinary arbitrary-angle capture path disconnected. Casting to float32 would
silently add a new rounding boundary; this slice does not do that.

Explicit `edited_capture_version=2` selects geometry admission version 1.
Only unsnapped angles with every post-geometry effect proven neutral defer
geometry: the unchanged original full-source exporter runs with `geometry=None`
and `provenance=False`, then the bridge applies the bounded old-sampler geometry.
All surviving post-geometry stages are identities or source validation. Primary
calibration and the supported tile colour chain retain their position before
geometry. Active colour grading or selective colour with an unsnapped angle is
not admitted. Existing unsupported reference/semantic/detail/tone/grain/editor/
fringe families are not newly enabled.

Snapped angles and identity continue through the original exporter geometry.
Capture versions 0 and 1 retain their earlier defaults and dispatch. Generic
file export, GPU preview, saved crop recipes and the old sampler are untouched.
This establishes an explicit new capture route using the old sampler semantics,
not a claim of successful runtime parity with the previously rejecting generic
flow. The earlier generic float64-finishing mismatch remains a separate issue.

## Ownership and publication

Admission prices the output's real rotated dimensions, a full float64 output,
actual retained RGB backing and bounded coordinate/gather/interpolation scratch.
Integer decode, persistent/frozen state, spec, encoded original, ICC and named
native allowances remain charged. The geometry sub-budget subtracts those
non-geometry owners before calling the isolated module. It is not a fresh 2 GB
allowance on top of the current renderer. No cap is raised or output resized.

The geometry module preserves crop rounding, strict half-degree snap, singleton
footprint, boundary-zero policy and existing bilinear operation order. It does
not create a full float64 source or whole-canvas coordinate/weight arrays.
Transfer still uses the existing Rust extended-sRGB ABI and a separately
admitted immutable freeze. Geometry output is private until cancellation and
unchanged source/document fences succeed; candidate review and new-copy history
remain the existing lens transaction. Failed or canceled work is not published.

## Remaining acceptance

- Authored parity fixtures must be run against the actual original sampler,
  including exact boundary/snap angles, singleton axes, signed zero, extended
  values, cropped/strided buffers and block boundaries.
- Real decoder/colour/geometry/transfer combinations, source races, cancellation,
  immutable candidate comparison and new-copy reopen require runtime acceptance.
- Full-resolution photographic quality, 24 MP throughput and peak process RSS
  are unmeasured. Rotation can substantially expand canvas/storage and still
  exceed admitted budgets. No arbitrary mixed-portrait/RAW/TIFF/alpha/HDR claim.
- Generic export's float64 finishing mismatch and active finishing compatibility
  are not repaired by an implicit cast or silently dropped effects.

The bounded module is independently replaceable through its versioned API and
the explicit capture strategy. This is not hot runtime plugin loading. It reuses
the project's existing sampler rather than copying a vendor implementation.
