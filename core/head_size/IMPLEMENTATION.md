# Complete head-and-hair size kernel

Status: AUTHORED / UNRUN. No compilation, test execution, native import, inference,
image rendering or photographic acceptance is asserted by these sources.

This is original GPL-3.0-or-later Rust with no crate dependencies. The private
waist-length ABI supplied local conventions for buffer admission, source-displacement
sign and bridge snapshots. No third-party algorithm source was copied. Public
OpenCV inverse-remapping and ITK iterative-inverse documentation informed the
coordinate convention and the explicit inverse-residual contract only.

The complete manually reviewed head including hair receives a uniform positive
shrink, rather than reusing a face-size/face-oval deformation. The kernel cannot
infer hair extent or attest to a human review from numeric landmark arrays.
Validated source/person/review ownership must precede native preparation.

See `../../docs/head-size/NUMERICAL-CONTRACT.md` for the complete ABI, proofs,
limits and remaining acceptance gates. `head_size.h` declares ABI 1. Both
`tests.rs` and the Python bridge fixtures are authored but UNRUN.

Production installation must explicitly build and package `liblrt_head_size.so`.
The Python bridge only loads that installed binary; it never compiles, downloads,
generates landmarks or falls back to a Python warp. The kernel never samples RGB.
