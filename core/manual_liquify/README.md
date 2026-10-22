# Manual liquify retained field worker

Implementation written but **not built, run, benchmarked, typechecked, tested, or
photographically accepted**. Local execution belongs to the user's local tester.

## Sources, actual adaptation and licensing

The control/behavior reference is PixCake's official manual:
https://wiki.pixcakeai.com/guide/9422.html (consulted 2026-10-22), together with
handbook “手动液化” and AI mapping ENGINEERING-liquify / LNX-MANUAL-002.
It specifies nine modes, size/density/pressure/rate, fixed edges, visible red
protection, shortcut N, and recommends automatic shaping before manual shaping.
It does not disclose proprietary kernels or exact parameter curves. In particular,
its left-push description means **horizontal left**, not Photoshop's perpendicular
motion convention. Our numerical curves/ranges are explicitly local contracts.

Compared mature implementations:

- GEGL `operations/common-cxx/warp.cc`:
  https://github.com/GNOME/gegl/blob/master/operations/common-cxx/warp.cc
  https://raw.githubusercontent.com/GNOME/gegl/master/operations/common-cxx/warp.cc
  Copyright 2011 Michael Muré; LGPL-3.0-or-later. `field.rs` is an actual Rust
  adaptation of its compact piecewise-quadratic falloff with hardness exponent,
  inverse-field composition, reconstruction attenuation, and weighted field-mean
  smoothing. These are not claims that GEGL is linked, or that only a name was
  borrowed. Preserve this attribution, `field.rs`'s SPDX/header and the bundled
  COPYING.LESSER on redistribution. The surrounding application is GPL-3.0-or-later
  (see repository LICENSE). No proprietary PixCake implementation was copied.
- Krita `libs/image/kis_liquify_transform_worker.cpp`:
  https://github.com/KDE/krita/blob/master/libs/image/kis_liquify_transform_worker.cpp
  https://raw.githubusercontent.com/KDE/krita/master/libs/image/kis_liquify_transform_worker.cpp
  Its transformed-point grid, Gaussian influence and original-point restoration
  were compared. No Krita source was incorporated: introducing another mesh
  interpolator, spatial container and transform infrastructure was unnecessary for
  this engine's existing tiled float-pixel warp path.
- The renderer deliberately reuses `ops.deform.prepare_warp_t` and
  `apply_prepared_warp_t` backed by Torch grid_sample rather than a new image
  sampler. Existing exact zero-displacement pass-through and float64 RGB16 grid
  generation/sampling remain intact. Manual fields are inverse offsets, so the
  adapter passes strength=-1 to that existing forward-displacement API.

## Retained operation and coordinate contract

JSON state: version 1, domain `post-effects-pre-crop-normalized`, source SHA-256
and full decoded W/H, ordered `strokes`. Nothing sampled from an image or a proxy
is saved. No face ID or semantic channel can make these gestures portable.

Every stroke retains id, mode, two normalized affine brush-radius basis columns,
points `[x,y,pen_pressure,time_ms]`, density/pressure/rate in [0,1], fixed_edges,
and rotation direction ±1. UI size is diameter as percent of displayed short axis.
Coordinates use normalized pixel edges, centers `(x+.5)/W`. The exact crop integer
rounding, snapped-quarter-turn, arbitrary rotation center and fixed-proxy resize
are inverted once at admission. Existing auto/manual deformation is NOT inverted:
the brush addresses the feature where the user currently sees it.

Pipeline: existing repair/smoothing/fabric → auto-deform → enhancement → exposure
→ levels → curves → HSL → LUT → legacy grade → independent local grades →
background/recovery → **manual liquify** → crop/rotation. Existing source-domain
masks are consumed at their own upstream stage then move with the final pixels.
Do not manually warp those masks again at their consumer. Reconstruction returns
to the fully processed pre-manual input, never to unedited source or pre-auto shape.
Changing upstream effects re-evaluates this same canvas-anchored intent; it does
not promise subject/face identity tracking.

Each dab reads immutable previous displacement D. New warp inverse offset v
composes as `D_new(p) = v(p) + D_old(p+v(p))`, bilinearly sampling the field. RGB
is sampled once after all field operations. Push derives inverse pointer motion;
left push is +first-basis inverse offset (visible left); pucker moves sampling
radially outward; bloat inward; rotate uses exact sine/cosine in brush coordinates.
Reconstruct attenuates D; smooth moves D toward a weighted local field mean, not
blurred RGB. Freeze/thaw saturating-add/subtract to destination protection and do
not change D. Frozen coverage attenuates later field updates, including reconstruct
and smooth. Full coverage preserves current D exactly; thaw never undoes D.

Dabs have at most 0.1 brush-radius movement or 16 ms between them. The first point
is one 16 ms dab. Timing is retained, so stationary holding works and replay does
not depend on the frequency of preview requests. A mouse uses pressure=1; actual
pen pressure multiplies the pressure control. Timed strength is
`1-exp(-6*rate*pressure*penPressure*dt/1000)`. Push uses actual motion multiplied
by rate/pressure/influence. This is LumaRetouch's disclosed behavior, not a match
to undisclosed proprietary curves. Freeze/thaw can reach exact 1/0 coverage by
accumulation; reconstruct locally attenuates toward identity. Reset removes all
manual warp/protection intent exactly. Fixed edges multiply field updates by
smoothstep over the outer 2% of the shorter canvas axis and exactly zero the
first/last rows/columns. It locks current edges rather than undoing old edits.
Sampling beyond image bounds without edge locking uses the established border
replication policy, not transparent pixels or unbounded reads.

## Wire, bounds and resource lifecycle

No Cargo dependency or model is added. `build-manual-liquify.sh` compiles the worker
from this checkout. Missing/stale worker is an error, not a Python or proxy fallback.
One request: little-endian u32 length, `LQL1`, W/H/stroke-count u32, then records:
mode u8, fixed u8, 8 f64 (density, pressure, rate, direction, axes columns), count
u32, followed by count × 4 f64 points. Response: `LQF1`, u64 byte count, H×W×3 f32
LE entries (inverse dx/dy in pixel units, frozen fraction). Python reads row bands,
not a second giant encoded response. Every length/finite/range check fails closed.

64 million pixels; dimensions ≤65536; 128 strokes; 2048 points/stroke; 8192 points
in total; ≤32768 interpolated dabs; ≤16 billion charged pixel operations; 1 MiB
request; 120 s replay deadline. Preflight uses conservative brush bounding boxes.
Memory admission counts both Python and Rust fields plus the largest temporary
patch and headroom. Actual memory/performance are unmeasured; this is not a latency
claim. No runtime compilation, software/model download or reduced-resolution
fallback happens. Cancel checks at ≤100 ms pipe waits kill the Rust process.
Only one replay runs at a time; new candidates replace queued work. Output rendering
and publication stay on the engine thread; no worker mutates the document.

Full export replays the entire retained field at original source resolution,
not per tile. Only field slices enter each bounded GPU tile. The measured global
manual displacement support is added to auto-deform/filter halos, including the
additional bilinear support. Then the same final stage runs before upscale,
sharpening and geometry. RGB16 grid construction and image sampling use float64,
then return to the existing float editing buffer before final 16-bit quantization.
