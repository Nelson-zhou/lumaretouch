# Targeted color action math

Bounded dependency-free Rust scalar action math, integrated into the existing
packaged curve compiler through `color-action-v1`. No application code is copied
from GIMP or darktable. No image pixels are passed from JavaScript to this ABI.
The producer sends at most 121 stage-float RGB + coverage samples and an existing
validated recipe. It returns existing level endpoints, PCHIP control points or
8-band hue parameters, not a separate raster effect.

- Levels black/white update individual RGB endpoints after the retained master
  channel. Gamma, opposite endpoint, output range and master remain unchanged.
- Curve RGB master uses max(R,G,B), individual channels their actual node input,
  and luminance the existing linear-sRGB Y convention. Existing PCHIP compilation
  handles node insertion/spacing and preserves the 64-point limit.
- HSL readout is true HSL of the sample; the existing renderer remains explicitly
  HSV-based with 8 unnormalized smoothstep bands. Hue drag uses the same basis
  and a bounded minimum-norm adjustment, never changes S/V parameters.
- Out-of-range, nonfinite, rotation padding, invalid opposite levels endpoints,
  and nonzero hue changes on low-chroma HSL targets reject before a mutation fence.

`picker_test.rs` supplies narrow scalar specifications, authored but not run
locally under the development-only instruction. Runtime, photographic and GPU
acceptance are not claimed. Full integration and references are documented in
`docs/development/targeted-color-pickers.md`.
