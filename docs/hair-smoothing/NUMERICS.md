# Original Rust numerical contract — AUTHORED / UNRUN

Core: `core/hair_smoothing/{contract,direction,measure,compose,lib}.rs`.
C ABI: `hair_smoothing.h`; version 1, independent checked plan/measure/compose.
Source and build are original GPL-3.0-or-later; no third-party neck kernel is used.
See the core README/header for exact constants and buffer/status contracts.

## Measurement

- Immutable full canonical HWC float32 **encoded working-sRGB** input; target and
  context are separate float32 [0,1] arrays; hard protection is exact 0/1.
- Convert source to log linear luminance. Central-difference gradients use their
  own center and ±1 taps. Finite local tensor sums, not signal integral-prefix
  subtraction, determine the signless tangent and coherence. Low energy supplies
  no direction. A strong-transition tensor gate can also suppress signal.
  `no_admitted_directional_signal` also covers coherent candidates suppressed by
  photometric gates; it is not a claim that the source has no visible direction.
- The complete conservative square dependency halo is admitted inside positive
  owned context and outside hard protection: `ceil(scale/2)+1+ceil(2*scale)+1`.
  This covers derivatives, tensors and both bilinear along-tangent samples,
  including conservative zero-weight taps. No border replication or invented
  out-of-ownership context is allowed.
- Four symmetric sample pairs along the tangent use robust range weighting;
  either side's strong transition, local direction variation, low coherence,
  deep dark, near-clipping or bright-region gate can veto a proposal. These are
  engineering safeguards, **not physical highlight/occlusion recognition**.
- The signed source log-luminance correction is bounded by `abs(gain)<=ln(1.10)`.
  Separate immutable exact eligibility survives alongside the gain. Eligibility
  is complete-context admission, not directional confidence or nonzero signal.

## Current-stage composition

Measurement never replaces the current image with source texture. At application
only CURRENT linear-RGB is multiplied by a common scalar exponential gain.
Positive gain shares the minimum SDR headroom across channels; no per-channel
clamp is used. This retains linear chromatic ratios subject to float rounding,
not a guarantee of perceptual hue invariance. Zero amount/field/current signal
preserves identity; no unnecessary colour-space roundtrip changes other pixels.

Canonical measurement is solved once per preparation. Interactive preview only
projects the frozen field and vetoes any sample with an ineligible interpolation
tap. Full candidate/export preparation must remain canonical; expanded tiles
slice existing gain and eligibility with the true `(y,x)` origin. No tile fitting,
proxy upscaling or replay inference occurs.

## Failure and budget

Checked dimension/length/address/alias/finite/range/scale/memory/cancel validation
precedes publication. Rust private outputs and checked allocation avoid partial
publication on rejection, cancellation or contained panic. Foreign pointers and
callbacks must satisfy the documented C caller obligations; invalid foreign
memory is not made safe by `catch_unwind`.

The measurement plan accounts `120N + 8(w+1)(h+1) + 16MiB`, with a 4GiB absolute
operation bound; host source/repair/semantic/raster/other-effect residents remain
additional. Canonical gain+eligibility retains `5N` bytes. The host conservatively
charges combined preparation and retained fields, and refuses rather than
reducing measurement resolution. Native composition uses bounded strips while
retaining atomic caller-visible publication.
