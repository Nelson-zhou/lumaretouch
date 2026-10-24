# Original analytic face-decoration foundation

Status: **source-authored; all build, test, inference and portrait acceptance
stages UNRUN**. No claim of a runnable or accepted feature follows from these
files. Missing native binaries fail visibly; there is no Python renderer fallback.

## Requirement and provenance

- Exact reference item: `LNX-REF-PC-32471-C-dd14134407`.
- [Official reference guide](https://www.pixcakeai.com/guide/32471), parent live
  inspection of lines 248–250: five freckle materials, three mole materials and
  strength. This establishes the material count and control, not their artwork,
  coordinates, colours, numeric ranges or equivalence to this implementation.
- The eight immutable layouts, names and analytic pebble kernel are original
  Lumaretouch GPL-3.0-or-later work. No proprietary artwork, downloaded image,
  copied texture, existing blemish-removal routine or blur renderer is used.
- [MediaPipe landmark connectivity](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/web/vision/face_landmarker/face_landmarks_connections.ts)
  was read for the official existing landmark topology. The local algorithm uses
  measured points and existing repository contour constants, not a copied face
  template. MediaPipe's six-class portrait mask is not per-person segmentation.

## Stable portable contract

`lnx.face_decoration.v1` owns `{version:1, pattern:<id>, strength:0..1}`.
`strength=0` is exactly neutral, with no requirement to load a native library,
resolve a review, run inference or create a contribution. Portable recipes never
carry geometry, source IDs, semantic planes or source-owned review/recovery data.

Catalogue IDs: `freckle_dust`, `freckle_bridge`, `freckle_constellation`,
`freckle_sunburst`, `freckle_scatter`, `mole_left_cheek`, `mole_right_cheek`,
`mole_pair`. Left/right explicitly means source-image left/right, not anatomical
left/right. Catalogue bytes are pinned by SHA-256
`414200ac138b5f75986db42b95c12ac77b5142816bc6a00f391287090956cf56`.

## Geometry and visibility

The nose-tip origin and transverse half-cheek span are measured from an actual
478-landmark MediaPipe result. The vertical axis is perpendicular to that span,
oriented toward the measured chin. This is a conservative moderately frontal
affine placement frame, not a 3D perspective reconstruction. Severe yaw,
foreshortening, pitch, clipped contours and insufficient source resolution refuse.
It does not invent hidden cheeks, use an avatar mesh or infer missing landmarks.

The exact named face-skin semantic plane is intersected with independent
decoration-only human-reviewed visible skin. Actual known-occluder and foreign-face
exclusions remain mandatory. Face boundaries, both eye contours, brows, lips and
measured nasal-base capsules are excluded with full-pixel clearance; genuinely
reviewed bridge skin remains eligible. A single-mole material does not require
bilateral coverage. Unknown skin-coloured hands/glasses can escape automatic
semantics: review is necessary and no complete-occlusion claim is made.

## Numeric kernel and antialiasing

Each mark is an original 12-sector irregular pebble with a 0.38-radius pigment
plateau and linear opacity falloff. Its two rings form 36 nonoverlapping
triangles. The measured affine frame transforms vertices to source-pixel
coordinates. Each triangle is clipped to every intersected unit pixel square;
the affine opacity integral is triangle area times mean vertex opacity. Clipping
uses f64 geometry to avoid cancellation, then returns f32 integrated coverage.
There is no stochastic sampling, fixed supersampling grid, proxy-resolution
texture, per-tile solve, minimum pixel-sized dot or sample-missed tiny feature.
Subpixel marks retain integrated coverage as their position changes. The finite
mesh defines the material, so exact integration does not claim an exact ellipse.

Coverage is summed and bounded at one, then multiplied by support and strength.
Original fixed warm-brown pigment absorption `[0.40,0.57,0.68]` yields
`delta[c] = -source[c] * alpha * absorption[c]`. This preserves local source
variation, is proportional to source luminance, never creates a pale constant-RGB
overlay and does not remove existing spots. The finite SDR float32 source is
immutable. `source + delta` stays in SDR range by construction, without RGB8
quantization or silently clipping HDR input. Core ABI validation and work checks
finish before writing output. Host stores one frozen source-resolution local
contribution for the established people compositor and export crops.
The existing people source-vector compositor constrains that frozen contribution
against the actual current image using a single direction-preserving SDR gain
per pixel, rather than independently clipping colour channels after other stages.
The landmark conversion follows the repository's established normalized x*width,
y*height convention; pixel integration still uses unit source pixel footprints
with centres at half-integers. Source-normalized review brushes remain owned by
the canonical mask rasterizer and are not converted into landmark coordinates.

## Explicit budgets and verification boundary

- At most 4,000,000 source ROI pixels and 64 marks per call.
- At most 32,000,000 triangle/pixel bounding-box candidates; larger exact-raster
  work refuses instead of lowering quality. One 4-byte coverage raster is owned
  by Rust, plus at most 2,304 small triangle records. No per-pixel UV raster.
- Python preflights a conservative 256 bytes per ROI pixel plus 64 MiB, against
  cgroup/process memory estimates and RLIMIT_AS. This is not a measured peak.
- The ROI is the actual measured face oval plus four source pixels, not the
  larger lip ROI. Very large tightly cropped faces can still exceed the explicit
  cap and are refused. This source-only foundation does not claim every camera
  resolution or portrait framing is supported.
- Native calls are synchronous with bounded work; no per-call cancellation ABI
  is present. The host must discard stale receipts using its normal lifecycle.
- `packaging/build-face-decoration.sh` is explicit packaging, never invoked at
  runtime. It, Rust fixtures and Python contracts are all **UNRUN** here.
- Synthetic intended checks cover exact zero, source immutability, finite bounds,
  invalid-input atomicity, area conservation, subpixel translation and scale,
  eight distinct layouts, no-support leakage and strict recipe validation.
  Real portraits across skin tones, resolutions, rotations, occlusions, preview,
  full-resolution export, history and batch workflows remain acceptance work.
