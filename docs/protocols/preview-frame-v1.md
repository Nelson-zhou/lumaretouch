# LPR1 slot presentation and LRF1 preview transport

SHM locking protocol remains v2; LRI1 mapping identity remains unchanged.
The 36 reserved bytes of each committed slot contain optional LPR1:
4-byte tag, document u64, presentation width/height u32, geometry-recipe key u64,
kind u32 (1 edited, 2 original, 3 embedded preview, 4 synthetic), zero flags u32.
Only synthetic permits document0. Known malformed metadata is rejected. Legacy
or unknown extensions remain unidentified and use raster aspect, never current
UI document geometry. Metadata and pixels are written/read under one flock.

Presentation dimensions describe intended full-output aspect, not the dimensions
of the fixed proxy raster. The geometry key is a conservative recipe identity,
not a canonical affine or proof of pixel registration. Full-source vs proxy crop
rounding can differ, especially for tiny crops; do not invert this descriptor to
source coordinates. Embedded preview uses its own oriented pixel dimensions.

LRF1 IPC header is128 bytes, followed by exactly payload bytes:
- 0 magic LRF1;4 version u16=1;6 header bytes u16=128.
- 8 sequence u64;16 emit time u64;24 pull time u64.
- 32 raster width u32;36 raster height u32;40 payload bytes u32;44 first row u32.
- 48 mapping instance16 bytes (zero if unavailable).
- 64 slot presentation36 bytes (zero if unavailable).
- 100 reserved28 zero bytes.
All integers little endian. Payload is zero or whole RGBA rows within the raster.
Sequence/load/geometry identities remain decimal strings in the UI identity path.
The legacy40-byte parser is display-only; it cannot authorize identified comparison.

pull_frame and peek_frame use the same encoder. A geometry/document change forces
full rows in the normal pull path. Each new Viewer obtains an uncounted full bootstrap
snapshot; the bootstrap respects LRT_SKIP_PIXELS and does not submit benchmark ACKs.
Partial uploads stay on the initialized texture instead of ping-ponging into old
content. Explicit comparison/diagnostic peek still bypasses benchmark pixel skipping.

Viewer commits composition pixels and their CSS aspect together. Comparison uses
separate contain rectangles for whole original/edited frames; the wipe clips both
at a common divider. Different geometry is labeled composition comparison, not
registered pixels. No comparison mode is removed.

Full-source inspection retains its own ROI geometry. Display-to-raster brush/pick
mapping follows presentation aspect, but inverse crop/rotation-to-source editing
coordinates remain a separate existing issue, not claimed fixed here.
