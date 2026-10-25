# Portrait export source materialization v1

Status: AUTHORED / UNRUN. Source review is not runtime, memory-profile or
photographic acceptance evidence. No tests, imports, builds or inference were
executed while authoring this module.

## Source and licence

The helper and fixtures are original repository orchestration under
GPL-3.0-or-later, as stated by their SPDX headers and the repository `LICENSE`.
No upstream implementation was copied and no new numerical algorithm, model,
native ABI or package dependency was introduced. The existing `numpy>=2.1`
dependency supplies conversion and division. NumPy's core is BSD-3-Clause;
its bundled components' additional notices remain governed by the existing
`THIRD_PARTY_NOTICES`, which must not be reduced to the core licence alone.

Primary API references used for the allocation/numerical boundary:

- [NumPy ndarray.astype](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.astype.html),
  including its default `copy=True` behavior.
- [NumPy divide](https://numpy.org/doc/1.20/reference/generated/numpy.divide.html),
  for the existing division ufunc operation. The application retains its
  installed NumPy version and literal old expression, not upstream source code.

## Bounded phase and unchanged owners

The existing `people_engine_runtime.prepare_export` normalizes the real RGB8/16
source, or copies the canonical derived float32 source, with:

`np.array(source.astype(np.float32) / divisor, dtype=np.float32, copy=True)`

This can overlap two full float32 RGB arrays during cast/division or the final
copy. Its existing semantic admission conservatively reserves `36N` bytes plus
visible source and repair storage. The optional v1 phase instead owns one final
`12N` private RGB destination and at most two `12B` RGB work blocks, where
`B <= 65,536`. It retains a named 65,536-byte allowance for small objects and
ufunc bookkeeping. This is application working-set accounting, not process RSS.

The optional integration must preserve the legacy semantic `36N` reserve and
the separate portrait solver's `256N + 128 MiB` gate. This change removes real
allocation overlap; it is not permission to raise caps or claim larger exports
are supported. For a recognized backing owner, reserve at least the larger of
the old `source.nbytes + 36N` and the materialization plan's `peak_bytes`, plus
the existing independent repair reservation before semantic resampling.

The helper knows only the actual source backing, its private output and its
bounded scratch. Semantic arrays, retained snapshots, recovery fields, repair
pixels, body inputs, native solvers, joint geometry, preview tensors and other
jobs remain independently owned and budgeted. No portrait-wide bounded-memory
claim follows from this phase.

## API

- `inspect_export_source(source, divisor)` inspects ordinary ndarray metadata
  and terminal backing ownership without reading or copying pixels. It returns
  immutable `SourceMaterializationPlan` fields including version, shape,
  source-owner bytes, output bytes, block workspace and simultaneous peak.
- `can_materialize_export_source(source, divisor)` returns false only for
  `UnsupportedSourceLayout`. Invalid dtype, RGB shape or divisor still raises.
- `materialize_export_source(source, divisor, max_bytes=..., cancelled=None)`
  repeats inspection, refuses insufficient memory before its destination
  allocation, and returns one private readonly C-order float32 RGB array.

The runtime chooses the source kind. RGB8 requires integer divisor 255; RGB16
requires 65535; canonical float32 requires 1. This helper does not infer source
identity, decode another file or prove that an arbitrary float array is the
canonical composite.

Unknown backing layouts can remain on an explicit legacy branch only before
the optional phase starts. Never catch general `ValueError`, `MemoryError` or
`InterruptedError` and retry the old allocating path. A recognized layout with
an insufficient budget refuses; it does not evade admission via legacy code.

## Precision, ownership and publication

Every block uses the literal old `block.astype(np.float32) / divisor`
expression. It does not multiply by a reciprocal, change the divisor's scalar
type, fuse integer conversion with division, quantize to RGB8, clip or resize.
Original integer samples through 65535 are exactly representable in float32;
the same division expression retains the legacy rounding operation. Canonical
float32 uses the same divisor-one operation as before, including signed zero.
Bitwise parity still requires the authored tests to be executed.

Blocks split both rows and columns, so an image wider than 65,536 pixels does
not exceed the block bound. Finite/range checks inspect the normalized block
only. A later invalid block or cancellation discards the unpublished private
output, with no source, source flags, repair, document, history or pipeline
mutation. A final cancellation check occurs before readonly publication.
Finally cleanup clears private output and block references even when a caller
retains the raised exception and its traceback.

Source views charge the full terminal allocation, not only visible `nbytes`.
Inspection recognizes exact contiguous owning ndarrays and bytes/bytearrays,
with bounded ndarray/memoryview chains. It validates every recognized array's
address span, including negative strides, against the terminal allocation.
Byte-backed inspection creates a metadata-only buffer view, not pixel storage.
Unknown wrappers, memmaps and exotic owning strides refuse optional admission.
The source retains the backing throughout the operation. Other roots and
cross-owner deduplication are not part of this single-source helper.

Repair ownership is unchanged: geometry consumes the unrepaired source, while
effect algorithms may consume the separately verified repaired source.
Derived repair evidence must still hash the canonical input, committed output
and ordered repair-stack identity before preparation. Derived source binding,
document matching, actual dimensions and the ban on original-file support
inputs remain the host's existing checks. The helper makes no evidence.

## Explicit exclusions and follow-on work

Torch preview is not wired to this helper. Its source and repair CPU transfers,
creative proxy equality check, and `verify_pipeline`'s independent tensor-to-CPU
proof conversions need separate bounded ownership work.

`people_snapshot.at_dimensions` still creates all target-grid semantic planes
and validates them; `people_render_runtime.prepare` still performs full-source
validation, ROI/native solvers and its existing conservative admission. Recovery
rasterization happens before export preparation. This version changes none of
those phases or their native/source ownership contracts.

Required execution gates include exact RGB8 and all-code RGB16 parity, float32
signed-zero/subnormal parity, strided/view backing admission, wide rows, tiny
budgets, cancellation at every publication boundary, unknown-layout legacy
routing, original/derived repairs and actual active-portrait integration. Full
export and photographic QA remain separate release gates.
