# Native Python boundary and remaining host obligations

Status: **AUTHORED / UNRUN**. This lane adds source and unexecuted fixtures only.
No product import, test collection/execution, typecheck, native build, inference,
installation, download, benchmark, photographic evaluation or package delivery
was performed. Static AST/source inspection is not numerical acceptance.

This document extends the original [core contract](CORE.md),
[numerics](NUMERICS.md), [unrun acceptance](ACCEPTANCE-UNRUN.md), and authoritative
[C header](../../core/skin_reference_match/skin_reference_match.h). It supersedes
only the earlier statement that no Python bridge source exists. No installed
binary or integrated feature is implied.

## Public boundary

Source: `engine/src/lumaretouch_engine/skin_reference_match_native.py`.

- `native()` requires the packaged `bin/liblrt_skin_reference_match.so`, ABI1,
  and both original `fit_v1` and `apply_v1` symbols. Missing file, symbols, loader
  failure or ABI mismatch gives an explicit unavailable error. There is no
  automatic build, search for unrelated libraries, download or Python effect
  fallback. `available()` checks only this ABI capability, not ownership, real
  evidence, photographic quality, complete packaging or user-visible wiring.
- `fit(reference_rgb, reference_coverage, target_rgb, target_coverage,
  *, limits=(ln(2), .35), byte_budget=None, cancelled=...)` returns `MeasuredFit`.
  It snapshots both independently sized real source populations. Both must
  include every reviewed source sample in their own ROI; there is no matching
  grid, correspondence, resampling, thumbnail fit or tile-by-tile remeasurement.
- `apply(current_rgb, coverage=None, measured_fit=None, amount=0,
  *, byte_budget=None, cancelled=...)` applies one current-pixel tile of at most
  1,048,576 pixels. Neither current tile dimensions nor position are derived from
  the reference ROI. The host proves registration and tile permission.
- `apply_tiled(..., tile_rows=None, ...)` takes a full current frame and uses
  contiguous full-width row strips, each within the original tile ceiling.
  `tile_rows` optionally selects a positive strip height within that ceiling.
  It fits nothing: the same immutable fit is reused for every strip. A full
  private frame is returned only after every tile and final cancellation check
  succeeds. This helper has a separate conservative 32-million-pixel frame cap.
- `memory_estimate(reference_shape, target_shape)` and
  `application_memory_estimate(shape, *, tiled=False, tile_rows=None,
  neutral=False)` return conservative **additional** byte requirements. They are
  pure shape/ceiling checks, without native loading, pixel allocation or a live
  memory query. Shapes use `(height,width)`.

Both fit and apply consume native-endian float32 encoded working-sRGB-D65 SDR,
RGB in HWC3 and coverage in HW, entirely finite and in [0,1]. Negative zero is
valid. Strided windows are accepted but copied without geometry changes. No
float64/uint8/endian coercion, clamp or implicit colour conversion is performed.
The host's upstream colour-management contract must establish the encoding.

The binding exactly declares `uint32_t` ABI version, `int32_t` status and
cancellation return, `size_t` dimensions and **element** lengths, `float*` RGB
and coverage, and `double*` limits/transform/diagnostics. It does not substitute
the hair or body-to-own-face native ABI, their data layouts or their algorithms.

## Fit result and integrity

`MeasuredFit` is a frozen dataclass with immutable scalar tuples:

- `reference_shape`, `target_shape`: independent source `(height,width)` grids.
- `limits`: two admitted f64 correction limits.
- `transform`: exactly `[1,dLogY,dLogRG,dLogBG]`, four f64 values.
- `diagnostics`: exactly the header's 24 f64 values, with source counts/weights,
  effective samples, centres, initial MADs, raw shifts, flags and retained mass.

No writable NumPy/native view of these arrays is exposed. Returned fit arrays
begin as NaN sentinels and are accepted only after native success and structural,
finite, support, dispersion, retained-weight, raw-shift and correction-bound
checks. Count/weight upper guards allow conservative floating-point accumulation
roundoff instead of assuming exact real arithmetic. This is boundary validation,
not a second robust estimator or a proof of
mathematical correctness. Apply revalidates the supplied `MeasuredFit`.

The class is a public numerical value, **not** an unforgeable provenance token.
Constructing a bounded fit, or matching its dimensions, does not establish that
the source is a particular photo, that the user chose the reference, or that the
covered pixels belong to the reviewed target. Runtime ownership bindings belong
to the host and must not be replaced by these checks.

## Neutral, exact pixels and failures

Amount zero is a real identity bypass: current shape/type/range/finiteness still
validate, then an independent owned contiguous bit-exact copy is returned. It
does not load the native library or demand evidence. Optional coverage or a
`MeasuredFit`, when supplied, still validates. Neither an invalid current frame
nor invalid supplied evidence is hidden by the neutral setting. Positive amount
requires both reviewed coverage and a valid measured fit, and never silently
falls back to neutral output if native support or evidence is missing.

Fit is not an amount-controlled bypass: even both limits zero require actual
reliable reference **and** target evidence. The numerical result is measured
once from immutable source, not rebuilt from edited current output.

Active apply validates finite in-range output and verifies exact bit identity at
zero coverage, all-zero transforms and pure current black/white endpoints. This
includes preserving negative-zero bits. Brightness is intentionally permitted
to change elsewhere; the body-to-own-face fixed-current-luminance invariant does
not apply to this separate operation. The Rust core's full reliability/gamut
behavior remains the sole numerical implementation.

Native statuses remain explicit failures: 1 ABI/layout/overlap, 2 settings,
3 pixels/numerics, 4 cancellation, 5 resources/allocation, 6 caught native panic,
7 insufficient reference, 8 insufficient target, 9 dispersion/retention,
10 invalid transform. Resources raise `MemoryError`, cancellation raises
`InterruptedError`, contained panic raises `RuntimeError`; other native refusals
raise `ValueError`. Corrupt successful outputs are rejected with `RuntimeError`.
Unknown nonzero status is also failure, never success.

Cancellation is polled before admission/copies/native calls, between bounded
snapshot/validation chunks, between strips and before return. Native callbacks
are held alive through each call; Python exceptions, including `BaseException`,
are contained inside the callback and reraised after native return. Later
cancellation discards private successful results. The native final copy is not
interruptible, and these guarantees do not imply process-crash atomicity.

## Memory and input ownership

Let N be the combined reference+target source pixels for fit, or full current
frame pixels for apply. Let T be the largest native application row strip.
Numbers below are source-derived admission estimates, not measured process peaks.

- Fit caller RGB/coverage: 16N bytes. Independent private snapshots: another
  16N. Native fixed scratch: 262,144 bytes. Additional validation/allocator and
  tiny fit-buffer allowance: 8 MiB. The additional estimator therefore returns
  `16N + 262144 + 8MiB`; host working admission checks the full `32N + fixed`.
- Active apply caller RGB/coverage: 16N. Private immutable snapshots: another
  16N. Full independent output: 12N. Native transactional RGB staging: 12T.
  Native fixed allowance: 4096 bytes, plus host 8 MiB. Additional estimate is
  `28N + 12T + 4096 + 8MiB`; total is `44N + 12T + fixed`. For one tile, T=N,
  so additional is 40N and total 56N before fixed allowances.
- Neutral additional estimate is `16N + 8MiB`: the current snapshot becomes the
  returned result and any supplied coverage is separately validated. Coverage
  bytes remain conservatively charged even when coverage is absent.

The wrapper's hard working ceiling is 2 GiB. It independently preserves the
core's combined fit ceiling of 32 million pixels and `16N + 262144 <=2GiB`,
and the native per-tile `40T +4096 <=64MiB` and 1,048,576-pixel limits. Every
dimension is 1..65536. It never evades admission by shrinking source resolution.

An optional `byte_budget` is an integer **additional-memory allowance**, not a
total process allowance. The estimate must fit both it and the existing
fail-closed CPU available-memory probe. The host must subtract its own cache,
owner arrays, masks, concurrent fits/tiles and renderer reserves before granting
this allowance. A live estimate cannot reserve memory, reveal hidden application
allocations or guarantee no OOM. Admission failure does not return fake output.

All input copies are owned, contiguous and read-only before the native call.
Snapshots are copied and checked in chunks of at most 4096 pixels. Validation
temporaries are bounded, not full-frame boolean or float64 arrays. Tiled apply
borrows contiguous row-strip views of full private snapshots/output, so there
are no unaccounted duplicate tile buffers. A caller must keep its own arrays
immutable throughout snapshotting; copies are not locks against concurrent
caller mutation. A cancellation callback must not reenter the binding or modify
buffers. The native core is trusted to honor its const-pointer contract.

## Host integration still required

Before an active operation, a future host must prove same photo/source revision,
working colour space, explicitly selected actual reference face, independently
reviewed target face or body owner, complete real-source support, source-grid
registration, and effective exclusion of the entire selected reference face.
No bounding rectangle, fit tuple, segmentation label alone or matching array
shape proves these facts. Targets from different people or face/body regions
must not be pooled into a single fitted population.

The host owns fit invalidation on source/reference/support/review changes and
keeps fits fixed throughout a render. Amount changes may reuse an authenticated
fit. No evidence, transform or diagnosis in this module becomes portable recipe
state merely because it is serializable.

`apply_tiled` provides a transaction for **one** fit over one current frame. A
host composing multiple targets must additionally keep the full sequence private
and publish only after all targets succeed. Overlapping supports and order,
reference-face exclusion, stale-source/review rejection, cache identity,
preview/export parity, UI disable/reason behavior, undo/redo, and packaging are
separate integration responsibilities. This source alone grants no pipeline,
catalogue, project-schema or public control completion.

## Authored but unexecuted fixtures

`engine/tests/test_skin_reference_match_native_unrun.py` describes exact ABI
types/symbol refusal, distinct strided source grids, immutable result tuples,
private pointer snapshots, strict current/source/coverage/setting validation,
core-free bit-exact neutral, missing evidence, conservative pure estimators,
preallocation admission, all native statuses, callback exceptions, cancellation,
actual current-pixel inputs, reuse across strips, later-strip failure and corrupt
native output rejection. Identity protocol doubles prove no numerical result.

Separate fixtures requesting the real core describe independent-source fitting,
full versus strip output bit parity, protected/current endpoint identity,
nonzero current correction, source immutability, all-zero-transform identity and
zero-limit evidence refusal. They skip explicitly when the original build is
unavailable. **Every fixture remains UNRUN.** The original Rust fixtures and
photographic/performance gates remain required, not replaced by Python source
review or a passing syntax parser.
