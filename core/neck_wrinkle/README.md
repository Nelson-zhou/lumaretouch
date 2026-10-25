# Manual-assisted neck fine-wrinkle numeric core

AUTHORED / UNRUN for `control:PC-32464:19`. This is an **AGPL-3.0-only
RapidRetouch derivative**, original author Chris Cork, pinned to
`5e9d9c1d2770ff29d11a3879e5a90aad5887e028`. Translation to Rust is not an
independently licensed original GPL algorithm. Read `NOTICE` for exact source
paths, Git blob identities and changes, and `LICENSE` for the full copied licence.
Existing combined-work/corresponding-source obligations continue to apply.

The method adapts `eyes.py` `_line_strength`, `_wrinkle_lift`, `_lab_l_to_y` and
`_relight`, with the `colour.py` sRGB transfer. It does not copy skin.py's inferred
neck ownership or reduced working grid. No geometry, model or automatic neck
segmentation exists in this core. Three finite full-source-grid Hessian scales
and morphological closing estimate a bounded positive lightness proposal from
actual, independently admitted, reviewed neck pixels. There is no generic image
smoothing fallback or donor chroma borrowing.

`neck_wrinkle.h` defines the C ABI. `lib.rs` is a dependency-free cdylib/rlib. The
engine imports only a separately built matching `bin/liblrt_neck_wrinkle.so`.
There is no runtime compiler, installer, download, alternate Python detector or
cached preview substitution. No binary was built or installed in this slice.
`Cargo.toml` describes an optional future authorized offline build; it is not an
automatic build or readiness claim. `tests.rs` and the Python numerical fixture
file were authored but **never executed**.

See `../../docs/neck-wrinkle/NUMERICS.md` for the exact finite dependency proof,
resource formula, interfaces, statuses, output ownership and remaining acceptance.

Measurement input is opaque native float32 full-canonical-grid **encoded working
sRGB-D65 SDR**. Application input is current-stage **linear working RGB SDR**.
These are deliberately distinct. Alpha, HDR, NaN/Inf, context/scale problems and
budget failures refuse instead of flattening, clamping or reducing resolution.

Even a successful bounded synthetic measurement is not aesthetic acceptance.
Pores, hair, structural shadows and actual wrinkles can be confused. Independent
reviewed hard protections and a real 100% source-bound comparison remain required.
