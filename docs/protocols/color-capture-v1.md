# LRCP v1 frozen proxy-frame wire (candidate)

Little endian, fixed 128-byte header plus exact width × height × 4 RGBA8 bytes.
Maximum payload: 128 MiB. No dirty rows, no omitted pixels, no partial-frame reuse.
This is a separate identified capture response, not a change to ordinary preview IPC.

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | ASCII LRCP |
| 4 | 2 | version = 1 |
| 6 | 2 | header size = 128 |
| 8 | 16 | producer epoch |
| 24 | 16 | SHM mapping instance |
| 40 | 16 | capture ID |
| 56 | 8 | exact frame sequence |
| 64 | 8 | producer generation |
| 72 | 8 | document load token |
| 80 | 8 | native arm ticket |
| 88 | 4 | raster width |
| 92 | 4 | raster height |
| 96 | 4 | presentation width |
| 100 | 4 | presentation height |
| 104 | 8 | payload byte count |
| 112 | 16 | reserved, must be zero |

All IDs are nonzero; u64 IDs remain canonical decimal strings / BigInt in UI.
Raster and presentation sizes are distinct: the fixed proxy backing may be resized
anisotropically after cropping, so display uses the producer-bound presentation
aspect while sample indices use raster coordinates. The display payload is RGBA8
sRGB, not the float sample source. Point readouts are separately requested from the
same still-valid producer generation's float32 working-sRGB pipeline.

The shared golden fixture `color-capture-v1.hex` is one pixel and deliberately uses
sequence 9007199254740993 (> JS safe integer). It is data, not a runtime generator.
