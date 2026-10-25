# Light glow, ABI 1 / math 0x00010001

Status: **AUTHORED / UNRUN / NOT FEATURE ACCEPTED**.

The exact available handbook record is `creative:211524`, source index 29,
光影——发光. This is an original deterministic CPU operator, not AI illuminated-face
detection, measured optical simulation or PixCake algorithm equivalence. It is a
real finite-support renderer, not an unavailable-model scaffold or renamed
global exposure slider. [Requirement and references](../../docs/light-glow/RESEARCH.md).

The module owns only `core/light_glow/**` and its research/numerical documents.
It does not alter existing numerical cores, registries, host history, assets,
native loading or UI. Parent-owned adapters must connect those separately.

- Dependency-free Rust `cdylib`/`rlib`, GPL-3.0-or-later, using the repository's
  original-core convention. No file access, network, model, decoder, dynamic
  compilation, mutable global, background task or private undo stack.
- Full-source-addressed rectangular tiles with a complete declared halo.
  All processing is at the original grid. A bounded tile is not a reduced final
  image; there is no substitute thumbnail or interpolation of a finished effect.
- Explicit **linear-sRGB D65 SDR premultiplied float32 RGBA** input. Finite
  `0 <= RGB <= alpha <= 1`. Reject negative/HDR values even at zero strength.
  Do not use the existing signed-HDR creative asset contract as proof of SDR.
- Three distinct artistic responses: black-mist selected-radiance redistribution,
  white-mist veiling plus detail diffusion, and digital additive glow with an
  explicit bounded SDR shoulder. All preserve alpha; no light grows outside the
  existing alpha support. Opaque photographic hosts may reject alpha themselves.
- Threshold, strength, integer source-pixel radius, bounded exposure response,
  wavelength-dependent diffusion reach, and glow-only HSL controls.
- Exact zero-strength bypass, actual pixel-difference coverage, cancellation,
  pre-allocation budget checks, and output publication only after private success.

See [ABI.md](ABI.md), [NUMERICS.md](NUMERICS.md), the [C header](light_glow.h), and
[integration obligations](../../docs/light-glow/INTEGRATION.md).

No build, test, type check, executable import, benchmark, application launch,
inference, install or download was performed for this source delivery. Authored
fixtures do not establish that code compiles, passes, is interactive or looks
photographically acceptable. [Unrun gates](../../docs/light-glow/ACCEPTANCE-UNRUN.md).
