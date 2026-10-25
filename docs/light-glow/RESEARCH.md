# Next major handbook capability: light glow

Read-only source reconciliation: 2026-10-25. Research baseline supplied by the
coordinator: `c04fa7c028f9d3325ed72d8796e4ff384d5cc432`. This document is not a
runtime, performance, photographic-quality or licensing-clearance certificate.

## Exact available requirement and genuine absence

`docs/development/handbook-traceability.json` contains exact entry
**creative:211524**, source file **创意工具规格.json**, zero-based source index **29**.
The preserved `ui/src/spec/creative.json` contains matching tool id **211524** and
official source URL. Original granular/hash-suffixed requirement files were lost
with an earlier workspace and are not in this recovered checkout. No new
`LNX-REF-...` hash ID is invented. The behavior map deliberately stays under the
available original entry rather than claiming reconstructed original sub-IDs.

Before implementation, a source search of engine, core, UI, native and docs for
211524 / 黑柔 / 白柔 / 辉光 / 光散射 / glow / bloom found no light-glow processing,
service, route or native module. The only source-name hits were unrelated lipstick
patterns and Lindbloom references. The traceability entry's implementation list
was empty. The current lens-blur source/host/UI were independently inspected and
are already present, so lens blur was not re-proposed from stale status notes.

## Official semantics, not a reverse-engineered algorithm

[PixCake guide 211524](https://www.pixcakeai.com/guide/211524), read 2026-10-25,
updated 2026-09-17, describes selecting one or multiple photos; entering Creative
or the colour-panel shortcut; and choosing black mist, white mist or glow. Black
and white mist have 1/8, default 1/4 and 1/2 strengths; glow has default weak,
medium and strong presets. Presets initialize strength, radius, threshold,
exposure and scattering controls, which remain editable. Hue, saturation and
lightness tint the glow; a green diagnostic shows affected regions, and Apply
confirms the effect. The page describes AI illumination detection and a physical
mechanism but does not publish a model, equations, numeric slider limits or
preset values. Local values and deterministic selection cannot be called those
undisclosed vendor algorithms or full AI/optical parity.

## Mature primary sources and licence reconciliation

- [GEGL bloom documentation](https://gegl.org/operations/gegl-bloom.html) describes
  threshold, softness, radius, strength and exposure limiting. The
  [primary bloom source](https://raw.githubusercontent.com/GNOME/gegl/master/operations/common/bloom.c)
  carries LGPL-3.0-or-later, copyright 2020 Ell, and composes a luminance-derived
  selection, multiplication, Gaussian blur and add/screen output. It is a real
  mature highlight-halo reference, not evidence of learned detection. No GEGL
  source was copied, translated, linked or vendored for this independent module.
- [Darktable soften source](https://raw.githubusercontent.com/darktable-org/darktable/master/src/iop/soften.c)
  carries GPL-3.0-or-later. It identifies a linear-RGB display-referred creative
  Orton operation and actually uses repeated box filtering after colour changes,
  followed by a blend. This supports an implementable bounded CPU diffusion
  approach. Its exact implementation and coefficients were not ported.
- [Darktable diffuse documentation](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/diffuse/)
  explains more general multiscale anisotropic diffusion and bloom use, with a
  significant resource warning. That PDE solver is not needed for this bounded
  first deterministic artistic operator; claiming to implement it would be false.
- [OpenCV 4.12.0 licence](https://github.com/opencv/opencv/blob/4.12.0/LICENSE)
  is Apache-2.0. OpenCV could supply standard filtering primitives, but adding an
  external runtime solely for this module was not chosen. No OpenCV API, binary,
  dependency, implementation source or model is used here.

The master/development links are recorded research snapshots, not immutable
vendored revision attestations. This delivery is independently authored under
the repository's GPL-3.0-or-later original-core convention and has no third-party
source/model payload. Future actual source reuse must pin revision, preserve the
applicable licence and attribution, and receive its own distribution review.

## Why this lane

It is a complete independent family of visible creative controls, useful for
portrait/wedding atmospherics, rather than another small portrait parameter or a
transport-only refinement. A deterministic renderer can genuinely produce the
effect at the full source grid today without introducing an unavailable model.
The boundary remains explicit: this does not close advertised AI detection,
every source format/HDR path, multi-image integration, persistence, speed or
photographic acceptance merely because code now exists.
