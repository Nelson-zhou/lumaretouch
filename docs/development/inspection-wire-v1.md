# Full-source inspection envelope v1 (not yet a runtime transport)

This envelope is separate from the proxy stream. It does not allocate/map SHM,
create worker processes, manage buffer release, or wire the Viewer. Those remain
required before the product can expose full-quality 100% inspection.

All integers are little-endian. Header is exactly 128 bytes, followed by tightly
packed opaque RGBA8 pixels. No compression or variable row stride in v1.

| Offset | Type | Meaning |
|---|---|---|
| 0 | 4 bytes | ASCII LRIF |
| 4 | u16 | protocol 1 |
| 6 | u16 | header length 128 |
| 8 | 16 bytes | nonzero host-issued engine epoch |
| 24 | 5 × u64 | request id, document, source generation, recipe, viewport |
| 64 | 2 × u32 | final edited canvas width, height |
| 72 | 4 × u32 | ROI x, y, width, height in final canvas pixels |
| 88 | u64 | exact payload bytes = ROI width × height × 4 |
| 96 | u32 | RGBA8 fourcc 0x41424752 |
| 100 | u16 | display profile 1 = sRGB |
| 102 | u16 | quality 1 = full_source_export |
| 104 | u16 | decoded precision 8 or 16 |
| 106 | u16 | source precision 1–32, or 0 = unknown |
| 108 | 20 bytes | reserved, all zero |

The epoch comes from the host, not the producer's self-assertion. Rust requires
it and the entire ticket/canvas/ROI to match the admitted request. A restarted
engine must get a new epoch even if its counters start again at one.

`parse_header` takes only the fixed header; callers must use this validation and
file-length verification BEFORE allocating/mapping a payload. `parse_packet`
borrows bytes without copying and rejects short/trailing data and nonopaque alpha.
Host request and memory budgets must be trusted scheduler outputs, not UI input.
A valid header alone does not prove source quality, resource ownership, or that
this request is still desired. Re-check generation with Gate at publication.

The Python encoder validates plain contiguous uint8 layout, identity, bounds,
precision, profile/quality and byte budget before scanning alpha in bounded chunks.
It creates only the header, not an extra full payload copy. Source semantics still
come from the shared full-quality renderer and its missing-layer guards.

The same literal `core/inspection/packet-v1.hex` is consumed by Rust and Python tests.
It includes request id 9007199254740993, intentionally above JavaScript's safe
integer limit. The standalone `inspectionFrame.ts` parser reads u64 via `getBigUint64`, then uses BigInt
or decimal strings for identities and a JSON round-trip test. Actual Viewer/ack/release wiring remains pending. Never round through Number or
serialize BigInt directly with JSON.stringify. u32 dimensions still need actual
canvas/texture device limits before allocation; u32 representability is not a
promise that a browser can display that size.

Lifecycle work still required: session-owned safe buffer names; no arbitrary
paths/symlinks; immutable one-result buffers or locks covering fstat/header/pixel
copy; no truncate while a reader holds the buffer; leases covering SHM + Rust +
IPC + JS + texture copies; release after the final consumer; cancellation and
engine-disconnect cleanup. Re-reading an unchanged header is not a substitute
for a lock and does not prevent concurrent pixel overwrite.

The JS parser rejects SharedArrayBuffer and resizable ArrayBuffer. Its pixels are
borrowed from the fixed input buffer, not immutable: the caller must not retain
a writing alias or transfer/detach the buffer during display. Publishing and ack
still need the session/desired-generation and ownership lifecycle checks.
