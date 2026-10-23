# Original PNG16 retouch source integration

Source-only implementation against `3cc38d32f28ef71af954fae5b0f5065ea657d3d9`.
All codec, numerical, UI, export, performance and photographic acceptance is
**AUTHORED / UNRUN**. This is a shared precision correction, not another handbook
feature count or a declaration that the broader alpha/HDR pipeline is complete.

## Contract

The ordinary original-image path now has a genuine PNG16 decoder instead of
mistaking Pillow's RGB mode for proof of RGB8. The existing pinned
`imagecodecs==2026.10.10` libpng binding supplies native uint16 samples. No new
dependency, model, external implementation or binary was downloaded or installed.
The original encoded file remains untouched. This does not change the already
separate alpha-capable creative-layer and background-asset import contracts.

- Header detection is content-based, independent of suffix. Native sample depth
  is distinct from the deliberately RGB8 display proxy and delivery format.
- Full-resolution `load_full(..., want_bits=16)` retains source encoding and ICC.
  EXIF orientation is applied once without an RGB8 intermediate.
- The display/proxy path converts embedded RGB ICC through existing LittleCMS16
  before quantizing for display. Retained source ICC is provenance, not a reason
  to convert those already-working RGB8 pixels a second time.
- Source-owned candidate, spill locator, 100% inspection and current-edit creative
  capture use the same genuine source and working-sRGB boundary. No preview PNG,
  camera thumbnail or reduced-resolution proxy becomes an export source.
- Neutral master16 and edited16 use existing verified TIFF16 output. PNG16 input
  does not claim that the existing PNG output encoder can write RGB16.
- Ordinary RGB8 delivery from PNG16 keeps true16 samples through working-space
  floating-point editing and geometry, then quantizes once for delivery. Existing
  output ICC, watermark, size-target and delivery ownership remain downstream.
- Reference-colour/semantic-colour preflight and prompted-mask input use the
  effective working source. Lens correction does not misclassify `png16`
  provenance as camera RAW.

Existing per-consumer memory admission, immutable source checks, frozen recipes,
FaceRefs and mask ownership remain in force. No global cap is raised. A codec
failure cannot silently fall back to Pillow RGB8 or promote eight-bit data.
Before a full encoded snapshot, the new decoder additionally admits
`2 × source_bytes + 64 × pixels + 64 MiB` against 65% of the visible available
memory after a 256 MiB reserve. The existing 120 MP full-decode ceiling is not
increased; encoded PNG is bounded to 1 GiB, metadata to 16 MiB, EXIF to 1 MiB
and chunk count to 65,536. These are conservative source budgets, not measured
24 MP throughput, cancellation latency or an allocation/OOM guarantee.

## Unsupported and explicit boundaries

The ordinary retouch pipeline is RGB SDR. PNG16 nonopaque alpha, including a
one-code difference in uint16 alpha and exact native-depth tRNS matches, is
refused before information can be lost. All-opaque alpha is not flattened and
may be removed only after native verification. APNG/animation, unsupported colour
signalling and HDR are not interpreted as ordinary sRGB. Gray16 may expand to
equal RGB channels; an unsupported gray ICC profile is not relabelled RGB.
Unprofiled ordinary SDR uses an explicit sRGB assumption, not a claim to recover
missing colour metadata. RGB16 ICC conversion and SDR output are not lossless
wide-gamut or scene-linear HDR editing. Neutral unconverted uint16 preservation
and transformed output colour are separate contracts.

The sample/reference library retains its explicit PNG16 and RGB16-ICC selection
guards; this slice does not silently broaden that separate resource workflow.
Existing asset-import support is not removed. Source paint's 512-pixel locator
remains a locator, not 100% inspection. Per-target visual spill batch review and
photographic spill quality remain unfinished.

## Primary evidence and licensing

Read 2026-10-23, without copying third-party source:

- [W3C PNG Third Edition](https://www.w3.org/TR/png-3/): native sample layout,
  exact-depth transparency comparison and precedence of colour signalling.
- [Imagecodecs upstream PNG binding](https://github.com/cgohlke/imagecodecs/blob/master/imagecodecs/_png.pyx):
  the mature existing codec path, not a new decoder algorithm.
- [Imagecodecs BSD-3-Clause license](https://github.com/cgohlke/imagecodecs/blob/master/LICENSE).
  Existing runtime pin is unchanged; upstream reading is not a claim that its
  current branch was executed or matches an installed local binary.

New adapter code is original project code. Distribution still must retain the
existing imagecodecs/libpng and LittleCMS dependency notices. No licensing claim
is made for copying an unrelated engine or proprietary model.
The existing [codec license inventory](../development/tiff-codec-license-manifest.json)
records the pinned dependency's notice hashes; this slice does not replace that
inventory with an unverified new version or execute a license scanner.

## Verification ownership

Authored fixtures cover native low bits, alpha/tRNS, header/content/precision,
orientation, source/proxy ICC, master readback, candidate/source capture,
inspection selection, working-space consumers and final-only delivery
quantization. They were not imported or run. Static AST/JSON/hash/source review
does not establish codec availability, output appearance, UI behavior or speed.
Qoder/local validation remains necessary before functional acceptance.
