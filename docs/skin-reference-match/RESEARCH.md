# Requirement, research and licence record

Reviewed primary sources on 2026-10-25. Source-only design; no external source,
asset, model, executable, Python package or example was downloaded/incorporated.

## Public feature requirement, not implementation permission

- [PixCake skin guide](https://www.pixcakeai.com/guide/32465), section
  **AI多人肤色统一**, updated 2026-05-26.
- [PixCake official wiki](https://wiki.pixcakeai.com/guide/9404.html), same feature,
  dated 2026-05-18.

Both describe a brightest-face reference, target face/body colour **and
brightness** correction, and exclusion of the reference face from the change.
The preserved external control key is `control:PC-32465:19`. The original hashed
LNX mapping is unavailable and is not guessed. Described behavior is a
requirements source, not proprietary source-code access or licence permission.

This first independent source scope instead requires an explicit user-selected
actual same-photo face reference and reviewed measured targets. Automatic
brightest ranking and instance/body segmentation remain unimplemented. It is
not a complete reproduction of the externally described AI feature.

## darktable color mapping

Primary references:

- [Official color mapping manual](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/color-mapping/).
- [Official colormapping.c source and licence header](https://github.com/darktable-org/darktable/blob/master/src/iop/colormapping.c).

The manual describes separate acquisition of source/target colour statistics,
cluster-based palette transfer and adjustable histogram matching. Its pipeline
is Lab/display-referred, not this crate's masked log-luminance/log-chroma model.
The official source header identifies GPL version 3 or later. This supports a
licence-compatible potential implementation route, but no code was copied here.

Design inference: separate source fitting and target application is useful, but
unrestricted palette/histogram transfer could alter intentional lighting and
contrast or mix unrelated body/face pixels. This implementation therefore uses
reviewed supports, robust centres only, bounded brightness/chroma translation,
no variance matching and no histogram equalization. The fixed histograms here
estimate medians; they do not redistribute the photograph's histogram. This is
not an implementation or performance comparison of darktable's module.

## POT optimal-transport colour example

Primary references:

- [Official POT example: OT for image color adaptation](https://pythonot.github.io/auto_examples/domain-adaptation/plot_otda_color_images.html).
- [Official POT licence](https://github.com/PythonOT/POT/blob/master/LICENSE).

The example independently samples two image colour populations and uses optimal
transport to adapt colour distributions. It cites Ferradans, Papadakis, Peyré and
Aujol's 2014 regularized discrete optimal-transport work. The example explicitly
identifies the MIT licence; the repository licence is also MIT. No POT code,
example assets, dependency or transport solver is incorporated.

Design inference: independently measured colour populations do not need pixel
correspondence, so unrelated-size source/target ROIs should not be resized into
fake paired observations. Full distribution transport is not needed for this
bounded partial scope and could change intended shading/contrast. This original
implementation uses neither an OT objective nor its solver and claims no OT or
proprietary-AI equivalence.

## Original implementation and remaining research

All new Rust, header, manifest and fixture source uses GPL-3.0-or-later, matching
the repository [licence](../../LICENSE). External materials informed conceptual
choices only. Existing project ABI/resource/transaction conventions informed the
interface; no external implementation is vendored and no additional third-party
code notice is required by this source-only lane.

The robust weighting, reliability thresholds, source evidence admission, separate
offset limits, streaming approximate medians, current-stage pointwise mapping
and common gamut interpolation are independently authored. Constants are design
choices requiring photographic validation, not published calibration values or
claims of recovered intrinsic reflectance. Needed future evidence includes mixed
lighting, varied skin colours without ethnic classification, cosmetics, body
shadows, occlusions, clipped sources, texture retention, memory/latency and
reference-face exclusion. All remain UNRUN.
