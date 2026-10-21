# Required non-sRGB reference fixture

- Asset: `AdobeCompat-v2.icc`, 374 bytes, ICC V2 RGB profile (description A98C).
- Upstream: saucecontrol/Compact-ICC-Profiles, commit `bdd84663061bc4ae95ca70decff54f581e27f702`.
- Source: https://raw.githubusercontent.com/saucecontrol/Compact-ICC-Profiles/bdd84663061bc4ae95ca70decff54f581e27f702/profiles/AdobeCompat-v2.icc
- SHA-256: `60fb2adecacf82132db0b1c09b303316f3bbd9e2823e7ba096d01627d12d57c9`.
- License: CC0-1.0; upstream license retained verbatim as `CC0-1.0.txt`.
- License source: https://raw.githubusercontent.com/saucecontrol/Compact-ICC-Profiles/bdd84663061bc4ae95ca70decff54f581e27f702/license
- License SHA-256: `469d87b5fa48f8aaf69e25f4fcac3a309c97dbb7d561b917638abdb640e004d9`.
- Maintainer documentation: https://github.com/saucecontrol/Compact-ICC-Profiles/blob/bdd84663061bc4ae95ca70decff54f581e27f702/readme.md

This independently generated profile represents Adobe RGB (1998)-compatible
primaries/transfer behavior, not sRGB. It is not Adobe's proprietary profile and
does not imply Adobe endorsement. CC0 does not grant trademark or patent rights.

The fixture replaces an optional system-path dependency in ICC regression tests.
Its absence or checksum mismatch must fail rather than skip those tests. The tests
must still prove changed pixels and compare against an independent Pillow8 path;
embedding a different ICC without converting pixels is not sufficient. It is a
test fixture, not a claim that the product's wide-gamut output UI is complete.
