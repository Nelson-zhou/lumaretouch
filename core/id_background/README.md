# ID-background numerical core (source-only, UNRUN)

Original std-only Rust code under this repository's licence. No model, copied
proprietary presets, external assets, or dependencies. ABI 1 is built as cdylib
`liblrt_id_background.so` and placed in `engine/src/lumaretouch_engine/bin/` by
packaging; it is not compiled or downloaded at runtime.

This layer consumes already authenticated, user-reviewed float source alpha.
It does not establish contact relationships, generate hair mattes, remove color
spill, extract old shadows, perform 3D lighting, or turn a proxy into source
quality. All planes cover the entire render domain. Export prepares once at
source dimensions and crops prepared fields for tiles, avoiding tile seams.

Foreground weight is `1 - (1 - edge_alpha) * background_opacity`. Replacement
background and its designed shadow are mixed with CURRENT pipeline RGB using
that weight. Subject RGB is not faded by background opacity. The source image
is not baked into these fields, so previous processing survives compositing.

Edge: signed square separable min/max morphology, rounded render-pixel radius.
Soft shadow: shifted alpha. Hard shadow: shifted alpha thresholded at 0.5.
Silhouette: shifted alpha vertically compressed to 35% about the bottom canvas
edge (explicit designed 2D projection, not estimated floor/contact geometry).
Blur: finite-support separable box convolution with zero-padding and rounded
radius; not Gaussian. Gradient fades toward source top, following translation.
Angle increases clockwise in image coordinates; zero points right. Shadow RGB8
is decoded to linear sRGB; normal, multiply, and W3C soft-light expressions are
evaluated in that fixed space. The projection is evaluated in an explicit blur-radius halo outside the
canvas before filtering, allowing off-canvas support to blur back into the
visible image. Only the final filtered result is cropped to the canvas. See https://www.w3.org/TR/compositing-1/#blendingsoftlight for the
blend formula specification; no implementation code was imported.

Bound: 32MP source, max dimension 65536, 64MP expanded shadow support.
Blur supports up to 256 source pixels. Each halo dimension adds twice the
render-scaled blur radius. Total conservative footprint is 52*source_pixels +
8*halo_pixels bytes, capped at 2GiB, including optional contiguous input copies,
output fields, edge plane and both halo scratch planes. The Python
memory_estimate helper provides this budget. Callers must additionally admit
their other pipeline allocations. Allocation
failures and cancellation fail closed. Cancellation polls every row/column.
Parameters, RGB [0,1], alpha [0,1], and finite values are checked before output.
Pointer non-overlap and lengths are the trusted FFI caller's responsibility.

Rust unit fixtures are authored but UNRUN. No compiler, build, test, product
import, execution, inference, install, or model download was performed.
