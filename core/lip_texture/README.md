# Original bounded lip-furrow attenuation

**AUTHORED / UNRUN.** This crate implements only conservative attenuation of
source-visible, narrow dark furrows on independently measured lip surfaces.
It is not a complete implementation of the commercial feature, and it is not a
medical, visibility, dry-flake, crack-reconstruction or semantic lip detector.

Feature identity: `LNX-REF-PC-32464-C-b6315c40ca` / 唇纹修整.
Portable intent: `lnx.lip_texture.v1`, exactly `{version:1, amount:0..1}`.

## Provenance and licensing

- The [official PixCake guide, 唇纹修整](https://www.pixcakeai.com/guide/32464)
  describes a broader feature addressing prominent lip texture, dry flakes/dead
  skin and small cracks. That establishes the feature gap, not a public algorithm
  or permission to copy commercial code, weights, assets or behavior.
- [Carsten Steger's author-hosted technical report, July 1996,
  *An Unbiased Detector of Curvilinear Structures*](https://mv.in.tum.de/_media/members/steger/publications/1996/fgbv-96-03-steger.pdf)
  explains why a line's surroundings and unequal lateral contrast matter.
  It is conceptual background only. This crate does **not** implement Steger's
  Gaussian-derivative, scale-space, subpixel location/width or bias-correction
  method, and no mature lip-retouching validation is inferred from that report.

All code and policy constants here are independently authored and licensed
GPL-3.0-or-later, consistent with the repository's root `LICENSE`. No external
source, publication content, model, image or dataset is vendored; there are no
third-party crates or new runtime dependencies. Public access to a paper is not
a software reuse license. This is not a patent-clearance/legal conclusion.

## Boundary and behavior

`engine/src/lumaretouch_engine/lip_texture_native.py` exposes:

    apply(source_rgb, coverage, amount, *, across, radius,
          cancelled=lambda: False)

Exact native float32, encoded working-sRGB-D65 SDR RGB HWC and coverage HW are
required. Source is the immutable original effective source on this grid, not a
previous result or lipstick intermediate. No alpha, HDR, implicit conversion or
RGB8 quantization is accepted. RGB16 low bits must survive the host conversion.

The host authenticates measured upper/lower lip surfaces, mouth axis, source,
person, revision and geometry. Every candidate needs a complete fully allowed
square radius `3*radius` and reliable bilinear footprints, so a sample cannot
jump over an oral-cavity seam or permission hole. Radius is measured current-grid
extent in `1..12`, not a saved setting. Thin surfaces intentionally refuse/no-op;
the host distinguishes absent complete footprints from a valid no-furrow result.

Five along-line sections, each with two flank distances on each side, are tested
at the measured mouth across axis and ±30°. Only compatible bilateral luminance
and normalized linear chromaticity with persistent narrow dark contrast qualify.
A common multiplicative linear-RGB gain lifts at most 35% of the measured
residual, jointly constrained by gamut. No average flank colour is pasted into
the image, no blur/inpaint/morphology is called, and no missing lip is invented.

The exact contract, original thresholds and limitations are in
[`docs/lip-texture/NUMERICAL-CONTRACT.md`](../../docs/lip-texture/NUMERICAL-CONTRACT.md).
Photographic quality, false positives, real-image usefulness, model inference,
performance and before/after parity remain **UNRUN / UNVALIDATED**.

## Build and source-distribution hooks

`packaging/build-lip-texture.sh` is the explicit offline/std-only build hook. It
accepts an optional output `.so` path and otherwise targets
`engine/src/lumaretouch_engine/bin/liblrt_lip_texture.so`. It builds into a sibling
temporary file and renames only after a successful compiler exit. It has not
been run. The runtime never compiles, installs or downloads anything.

The package stage must ship the library **and** corresponding source:
`lib.rs`, `tests.rs`, `lip_texture.h`, `Cargo.toml`, this `README.md`, the build
script, and the repository GPL `LICENSE`. The parent package staging hook owns
those shared paths. ABI declarations and error codes are in `lip_texture.h`.
No generated library, Cargo lockfile or compiled output is committed here.

## Verification status

`tests.rs` contains numerical, no-effect, contamination, ownership, cancellation,
resource and C ABI acceptance intentions. The Python `_unrun.py` fixtures cover
state, ownership and refusal boundaries plus an optional installed-core smoke
case. Protocol fakes are test-only, never production fallbacks.

No tests, builds, compiler/type checks, product imports, inference, downloads or
Git writes have been executed for this change. Static source review is not a
passing runtime check. Separate execution authorization and photographic review
are required before this can be described as verified or ready to ship.
