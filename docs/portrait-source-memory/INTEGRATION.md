# Portrait export source materialization v1

Source authored; numerical, runtime, RSS and photographic acceptance UNRUN.
This is an allocation strategy for existing portrait effects, not another
handbook algorithm and not completion of the large-photo portrait pipeline.

## Real entry and preserved behavior

The public `people_export.prepare` route opts into
`people_engine_runtime.prepare_export(source_materialization_version=1)`.
Direct callers retain version 0 by default. Unknown versions, including Boolean
values, fail before preparation. No saved recipe, project schema, UI control,
history owner or native numerical ABI changes.

The version 1 helper supports genuine original uint8/uint16 and derived float32
sources after the existing document, source and repair-evidence checks. It
materializes one private read-only float32 RGB output in bounded blocks. Each
block retains the existing `astype(float32) / divisor` expression, with divisors
255, 65535 or 1. It does not use a reciprocal approximation, an in-place update
to caller storage, a proxy image or a new colour conversion.

Known backing storage is inspected before allocating the output. A small view
does not imply a small retained allocation. Unsupported backing ownership takes
the historical route before any new output allocation; malformed inputs, budget
failure and execution failure do not fall back after partially doing the work.

The semantic resampling reservation is the greater of its historical
`source.nbytes + 36 * pixels` allowance and the bounded helper's actual-owner
plan, plus the existing repair allowance. This deliberately does not claim new
admission capacity by shrinking a conservative gate. Target-owned semantics are
still resized by the existing planner, all requested portrait algorithms still
run, body geometry still joins the common map, and the existing solver receives
its unchanged budget. Repair remains a separate effect input: this strategy
does not repair the geometry source or copy a donor's masks.

## Limits that remain open

- The existing 256-bytes-per-pixel plus 128 MiB portrait preparation gate and
  downstream whole-frame geometry/effect buffers are unchanged.
- Original decode/ICC, semantic resampling, derived proof validation, recovery
  rasterization and host snapshots are not made bounded by this helper.
- Preview's Torch CPU transfer and repair-evidence materialization are unchanged.
- The helper's cooperative cancellation API does not imply that the existing
  export caller now has a new user-cancel route. Publication and uncertain-write
  fences remain with their existing owners.
- Transparent/HDR photo sources remain refused by the existing portrait source
  contract; no clipping or downsampling is introduced.

The source change reduces one concrete conversion overlap. It does not prove a
24 MP workflow, process RSS ceiling, platform parity or full handbook acceptance.

## Primary practice and licensing

This is original project orchestration under GPL-3.0-or-later, using the already
declared NumPy dependency; no upstream implementation is copied. NumPy is
BSD-3-Clause and remains subject to the existing distribution notices.
The primary [ndarray.astype documentation](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.astype.html)
documents its default copy behavior; the [divide API](https://numpy.org/doc/stable/reference/generated/numpy.divide.html)
documents elementwise division. Those APIs explain the allocation opportunity,
not an executed proof of bitwise parity. The literal existing expression is
retained instead of introducing different Rust normalization mathematics.
