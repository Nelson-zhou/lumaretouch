# Capture-only bounded colour finishing

Status: AUTHORED / SOURCE-REVIEWED / UNRUN. This is an allocation and scheduling
strategy around existing operators, not a new colour algorithm. No product
import, application, test, compiler, typecheck, inference, dependency/model
download or Git write was performed by this module's author. Numerical parity,
runtime routing, cancellation behaviour, photographic quality and memory/RSS
acceptance remain unverified. The parent owns shared export/admission integration.

## Public module contract

`engine/src/lumaretouch_engine/creative_capture_finishing.py` exports:

- `FINISHING_VERSION = 'edited-capture-colour-finishing-v1'`.
- `inspect_colour_finishing(pixels, grading_stage, selective_stage, *,
  block_pixels=65536, max_bytes=512000000, cancelled=None)` returns an immutable
  `ColourFinishingPlan`. Inspection validates metadata, exact stage types and
  recipe/active coherence; it does not scan pixels or load native libraries.
- `finish_colour_np_bounded(...)` accepts the same arguments and returns the
  original object when both stages are neutral, or a completed private float32
  RGB result when either is active. No caller storage is modified.

Only ordinary native-endian float32 HWC3 arrays, positive dimensions and at most
100 million pixels are admitted. Integer and float64 arrays are rejected rather
than normalized or silently rounded. Known ordinary ndarray, memoryview and
bytes/bytearray backing chains are inspected and charged by terminal allocation,
including unused backing bytes. Signed-stride bounds must fit that allocation.
Unknown/subclass/foreign/cyclic owners and unsafe unsupported wrappers fail
closed. Safe negative-stride, transposed, broadcast and read-only sources are not
made contiguous as a full image. Inspection is not provenance or colour-space
proof; the caller must establish genuine extended-sRGB D65 input.

The supplied stages must be the exact existing `ColourGradingStage` and
`SelectiveColourStage` classes with their ordinary instance fields. Their active
flags must agree with the validated recipes. Recipes are fingerprinted without
changing the existing float32 scalar-conversion boundary. Instance-level method
injection, subclasses, stale active flags and detected recipe drift reject.
Caller-owned input, stages and every external alias must stay stable throughout
the call. Rechecks do not provide protection against concurrent mutate-and-restore
races and do not replace the caller's ownership/fencing requirements.

## Existing arithmetic and order are reused

The reference path is `export.py` immediately after reference/semantic colour:
`colour_grading_stage.apply_np`, then `selective_colour_stage.apply_np`, before
colour editor/detail/grain/final monochrome and quantization. A separately
admitted private export context can select this strategy at that same boundary.
No persisted recipe is neutralized, reconstructed or reordered. Ordinary export
defaults must keep their existing path. Do not move active finishing after export
or ahead of geometry.

The existing `*_stage.py` methods validate a full input at lines 19–27. Their
`*_native.py` implementations scan the input and create full-sized contiguous
input/output storage at lines 31–41 before dispatching 65,536-pixel chunks at
lines 44–50. Calling those unchanged stage methods on bounded owning blocks
makes all of that scratch bounded without rewriting arithmetic or native loaders.

For each active stage, this module first scans the entire logical stage input in
bounded blocks for finite channels and magnitude at most 128. Only after that
preflight does it allocate the first private result or invoke that stage. Colour
grading completes across the whole canvas before selective colour is started.
If a completed CG result exceeds SC's input headroom, SC rejects before any SC
stage/native call. Neutral stages retain their original bypass semantics: they
do not impose finite/headroom checks. In particular, a neutral SC does not clip
or newly reject CG's output; existing downstream processing still applies.

One private float32 output raster is allocated. For the first active stage each
source block is copied to bounded owning float32 storage, passed to the original
stage, and its result copied into that raster. For the second active stage the
same private raster is read through bounded owning blocks and replaced only
after each stage call returns. This is not an overlapping/in-place native call.
CG's intermediate float32 write is preserved. No intermediate uint8, float64
conversion, changed transfer function, clipping or normalization is introduced.

`core/colour_grading/lib.rs` lines 60–64 and
`core/selective_colour/lib.rs` lines 47–51 evaluate each pixel independently.
The same packaged libraries, scalar conversion, extended-sRGB mode and sequence
are reused. This supports an authored exact-parity target against the existing
wrappers using the same binaries; it is not proof of executed parity, cross-build
bit identity, GPU acceleration or vendor pixel equivalence.

## Cancellation, ABI and failure ownership

Native grading lines 42–57 and selective colour lines 33–44 require aligned,
valid, non-overlapping input/output buffers and enforce the 65,536-pixel cap.
Existing wrappers continue to own those calls. Every new input block is a
separate aligned, C-contiguous owning allocation. Horizontal subdivision handles
widths above the cap; a single wide row is not an exemption.

Cancellation is polled before/after bounded validation, copies and calls, between
stages, and before return. Stage calls receive an explicit callback rather than
silently substituting the stage-local callback. Native calls remain cancellable
between their existing bounded calls, not through a data-racy flag. Exceptions
propagate; no partial destination is returned or published and no error selects
a fallback that omits an effect.

Owning input blocks matter beyond ABI safety: an exception inside the existing
stage/native Python frames can retain their argument. A view into the full
private output would therefore keep that whole partial output alive through its
backing allocation. The stage instead receives only a bounded owning block.
The validation helper and executor clear full-source/output references and views
in `finally`; old block results are released before allocating the next block.
This does not consume caller aliases or remove owners held by caller callbacks,
outer frames or source/document state. Caller writeability flags are untouched.

## Named working-set admission

Let M be output pixels, B=min(requested block pixels,M), and S the actual input
backing allocation. With at least one active stage, module admission is:

- S input backing bytes, not merely `pixels.nbytes`.
- 12M bytes for one private float32 output, regardless of one/two active stages.
- 64B bytes of conservative named block scratch: owning RGB input 12B, native RGB
  result 12B, float validation 12B, finite validation 3B, strided copy-back reserve
  12B and bounded array slack 13B. Some components do not actually coexist; this
  is deliberately conservative.
- 4 MiB array workspace plus 4 MiB metadata/recipe/object reserves.

When both stages are neutral, output allocation and block scratch are zero; the
same fixed allowances and actual source owner remain conservatively charged.
Plans expose their component values and declare `runtime_verified=False`.

The coordinator must subtract all simultaneously live original/ICC, integer
source, snapshot/spec/context, last export tile, host lease and native reserves
before supplying `max_bytes`. At the audited neutral-other-effects export
boundary, a small crop can retain the original stitched 12N backing, whereas a
quarter-turn copy owns 12M. The caller's prospective source reservation can
therefore use `max(12N,12M)`; it must not charge a small visible view as a small
owner. The last `got` tile is independent and stays separately charged. Actual
inspection enforces the observed source backing at execution. This does not
retroactively admit decode, geometry or snapshot allocations. Canonical RGB→RGBA
transfer, immutable freeze and interning are separate subsequent phases, not
simultaneous allocations hidden inside this adapter. None of these numbers is a
measured process-RSS or allocator guarantee.

## Integration limits

The parent-owned capture route must still enforce original-source format,
orientation, precision, provenance and current source/document fences; complete
recipe admission; no skipped edits; scale one and supported geometry. Active
finishing does not admit float64 arbitrary-angle geometry. Reject rather than
cast that result or run grading before geometry. Existing exclusions for active
detail/grain/extended tone, unsupported local/source-bound effects and unknown
fields remain in force. The neutral photo-detail structural validator and all
post-finishing export source checks remain part of the normal chain.

The module itself is not a source decoder, complete render pipeline, transaction
owner, publication fence, immutable asset creator or authorization to expand the
eligible capture family.

## Provenance and primary evidence

Inspected 2026-10-25:

- `core/colour_grading/lib.rs` header identifies original Lumaretouch tonal-mask
  grading under GPL-3.0-or-later; `core/selective_colour/lib.rs` header identifies
  original Lumaretouch RGB-family process-colour adjustment under the same
  license. Both numerical source files remain unchanged by this strategy.
- Root `LICENSE` contains GNU GPL version 3. `NOTICE` lines 163–172 separately
  identifies both existing cores as original GPL-3.0-or-later work and says no
  vendor code/assets are included. Their existing contracts distinguish external
  control-semantics references from copied implementations and vendor parity.
- `packaging/stage-engine.sh` lines 260–268 already builds the existing kernels
  offline and stages their exact source, root license and respective contracts.
  This strategy adds no dependency, kernel, model, asset or runtime compiler and
  does not replace existing notices. New orchestration source has an explicit
  GPL-3.0-or-later SPDX header. This is provenance, not a legal opinion.
- NumPy's official [ascontiguousarray documentation](https://numpy.org/doc/stable/reference/generated/numpy.ascontiguousarray.html)
  distinguishes a contiguous input returned unchanged from a noncontiguous input
  copied into new storage. Its [reshape documentation](https://numpy.org/doc/stable/reference/generated/numpy.reshape.html)
  states that reshaping is not always a view. Consequently this adapter never
  flattens or contiguizes a full strided input before blocking.
- Rust's official [from_raw_parts_mut safety contract](https://doc.rust-lang.org/std/slice/fn.from_raw_parts_mut.html)
  requires valid aligned storage within one allocation and exclusive access for
  the mutable slice's lifetime. No overlapping/native in-place extension is used.

These official practices were read, not copied as implementation. No additional
colour-algorithm or vendor research was needed for unchanged numerical reuse.

## Authored acceptance, not run

`engine/tests/test_creative_capture_finishing_unrun.py` separates real packaged
library parity from explicitly mocked stage/control-flow fixtures. Coverage is
authored for CG-only/SC-only/both, relative/absolute, all control families, tiny
controls, signed zero/negative/HDR, B−1/B/B+1, wide rows, singleton axes, safe
strides, neutral identity, bounded scans, owning inputs, stage-major order,
whole-stage rejection before calls, one output, actual backing budgets,
unsupported dtypes/owners, cancellation, recipe drift and retained exceptions.
Missing packaged native libraries explicitly skip numerical fixtures rather than
substitute formulas. Shared routing/source-fence/admission fixtures belong to the
parent integration slice. None of these fixtures has executed. Real full-source
export equality, source changes during execution, photograph acceptance,
large-image latency, cancellation responsiveness and measured RSS remain open.
