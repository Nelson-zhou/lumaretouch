# Bounded edited-source capture sink

Status: AUTHORED / UNRUN. This source was reimplemented against the verified
existing creative-layer ABI after the earlier uncommitted workspace was lost.
It is not a claim that the lost files' exact bytes were restored. Syntax-only
AST inspection is not native parity, real-photo acceptance, full-24MP capture,
executed cancellation, throughput or measured process-RSS evidence.

## API and ownership

`inspect_rgb_sink(rgb, *, max_bytes, cancelled)` returns an
`EditedCaptureMemoryPlan` without native loading or pixel conversion.
`capture_rgb_sink(rgb, *, max_bytes, cancelled)` returns
`EditedCaptureSink(width, height, sink, plan)`. The sole mutable `sink` bytearray
contains little-endian float32 linear-sRGB-D65 premultiplied RGBA, with alpha
exactly one. No partial sink is returned on native rejection or cancellation.

Input must be a genuine native-endian float32 or float64 H×W×3 plain ndarray
containing the existing editor's full-resolution extended encoded-sRGB result.
The caller establishes provenance, colour space, complete effects, source and
document revision consistency. Inspection alone cannot certify these facts or
finite pixels. This is not a decoder, renderer, preview fallback or display port.

The caller must keep the source and its shape/storage stable during conversion,
including every external alias. This function does not consume the source. It
does not freeze content, intern assets, publish history/document state or write
files. The returned mutable sink is not suitable for persistent asset storage.

To use the source-free immutable-freeze budget, the caller must release every
RGB view, backing owner, exporter-retained alias and associated render owner
before `bytes(result.sink)`. Deleting just one variable is not proof that all
aliases are gone. That required immutable ownership copy temporarily coexists
with the mutable sink. Release the result/sink before asset validation/interning.
If source release cannot be established, charge still-live source storage during
freezing. Original bytes and ICC are retained caller-owned provenance, untouched
by this module. Final cancellation/revision/publication checks remain upstream.

## Existing transfer semantics remain authoritative

Each bounded block assigns RGB into a float32 straight-RGBA allocation and adds
alpha one. This exactly preserves the previous full-frame RGBA assignment
boundary. float64 is supported because existing arbitrary-rotation geometry can
return it. Its values round through the same float32 assignment, not a new
float64 transfer or an unbounded full-image cast.

The only transfer implementation is packaged ABI v1
`lrt_creative_linearize_extended_rgba`. It receives an immutable bytes-backed
block while ctypes releases the GIL. Rust retains the odd-sign extended inverse
sRGB transfer, float64 arithmetic, float32 storage, signed-zero behavior and
rejection of nonfinite or excessive HDR values. Decoded straight RGB magnitude
above 65504 is rejected, never clipped. Alpha is exactly one, so the canonical
premultiplied result preserves those signed/HDR values under the existing bound.

There is no NumPy transfer formula, clipping, 8-bit intermediate, tone mapping,
quantization, runtime native build or fallback. This port is not identity for
already-linear input. Existing neutral canonical-asset capture must bypass it,
preserving its no-transfer-roundtrip behavior.

## Explicit conversion budget and separate freeze phase

`max_bytes` is an integer from 1 through 4,000,000,000; its default is 512,000,000.
The canonical cap remains 100,000,000 pixels and each ABI block remains at most
65,536 pixels. Let N be the visible pixel count, B=min(N,65536), and S the charged
reachable RGB storage. The conversion plan counts:

- S source backing bytes: ordinarily 12N for standalone float32 or 24N for float64.
- 16N bytes for the single mutable canonical sink.
- 16B bytes for the bounded straight float32 RGBA assignment.
- 16B bytes for its immutable native input snapshot.
- 16B bytes for the existing Rust ABI's staged output Vec.
- 4 MiB named NumPy assignment/buffering allowance.
- 4 MiB named Python/ctypes/metadata/allocator allowance.

`plan.peak_bytes = S + 16N + 48B + 8 MiB`. A full-sized ndarray view shares the
one sink allocation; it is not another RGBA/linear plane. Full-width row blocks
are used when one row fits the block cap. Wider images use one row at a time
with bounded horizontal chunks. Previous staging owners are released before the
next block is allocated. Destination byte-order conversion is in place per block.

`source_bytes` reports visible samples. `source_storage_bytes` charges known
larger backing storage for ordinary cropped, reversed or transposed views.
Plain ndarray/memoryview chains and terminal buffer-protocol owners are inspected
without a pixel copy. Unknown chains, unsafe stride-trick wrappers and ndarray
subclasses reject rather than hide uncertain accounting. The plan cannot discover
unrelated allocations retained by arbitrary external aliases.

`plan.freeze_bytes_after_source_release = 32N + 4 MiB` describes a SEPARATE caller
phase. This module neither performs nor admits that phase. The owning transaction
must admit it before starting, adding any still-live source storage when release
is not proven. Both phases need caller accounting for originals, ICC, retained
assets, decode/render workspaces, models, concurrency and available memory.
A cheaper conversion sink does not establish that full edited rendering fits.

The named reserves are application admission allowances, not measured allocator
guarantees or a hard process-RSS ceiling. No full-24MP run is claimed.

## Failure and cancellation behavior

Cancellation is checked before inspection, allocation and each native call, after
each block, and before returning. The native call itself is bounded but not
interruptible internally. Earlier blocks may already have written the private
sink when a later block fails; that storage is never returned or published.
`CreativeLayerNativeRejected` preserves native status-code failures.

Private sink/block locals are cleared on conversion exit so this function's own
failure frame does not intentionally retain those allocations. This cannot
release caller aliases or objects retained by external exception instrumentation.
There is no caller-supplied destination or callback receiving partial pixels.

## Authored verification fixtures

`engine/tests/test_creative_edited_capture_sink_unrun.py` contains admission and
real-existing-ABI fixtures covering exact budget boundaries, retained backing
storage, dtype/shape/pixel/block caps, pre-native cancellation/refusal, separate
freeze admission, signed zero and the transfer knee, negative/above-one values,
low-bit precision, float64 rounding, strided/immutable input, wide/tall bounded
allocations, final-block nonfinite/HDR failures, cancellation after each native
block including the final one, source aliases and immutable-copy independence.

Real parity tests call the actual packaged ABI and explicitly skip if missing.
The error-routing stub implements no replacement pixel arithmetic. Tiny synthetic
fixtures do not establish real-photo parity or memory acceptance. Tests, product
imports, native loading, builds, typechecks, inference and downloads remain
UNRUN; static syntax/hash checks do not change that status.
