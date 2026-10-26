# Original-format export policy — source-only / UNRUN

Original is a **policy**, not a member of the encoder format registry. Given
authenticated document facts and installed writer capabilities, this small
dependency-free Rust helper selects an existing JPEG, PNG, TIFF or WebP writer
without changing supported encoded precision. It performs no filesystem access,
hashing, decoding, rendering, encoding, allocation, task creation or publication.
It does not copy original bytes or promise preservation of source compression,
metadata or pixel values after edits/colour conversion.

## Host contract

Only the authenticated host may construct the inputs. A UI format label,
filename suffix, library row `fmt`, or preview RGB8 buffer is not an authority.
The host binds physical file fingerprint/header facts and decoder source stamp,
effective asset, document/copy identity and recipe before calling this helper.
Creative-derived assets require an authenticated encoded ancestor plus a
separate binding to the effective creative pixels. The helper must never cause
the host to render that original carrier in place of the current creative asset.
RAW-derived sources retain source kind RAW and are refused.

The host freezes the result together with options and per-entry destination
paths, authenticates that exact frozen plan on admission, verifies full decode
against the bound facts before publication, and reuses decisions unchanged for
same-session retry. Header evidence does not guarantee a valid compressed pixel
payload. The existing decoder, renderer and atomic destination writer remain
the only owners of those operations.

## ABI 1

See `export_format.h`. `lrt_export_format_abi()` returns 1.
`lrt_export_format_resolve()` takes six `uint32_t` scalar arguments and returns
one `uint64_t` scalar. No pointers, array extents, callbacks or mutable memory
cross this boundary.

| Input | Values |
|---|---|
| container | 0 unknown, 1 JPEG, 2 PNG, 3 TIFF, 4 WebP |
| source_kind | 0 unknown, 1 encoded bitmap, 2 RAW |
| precision | Authenticated encoded bits per channel; successful values are 8 or 16 |
| single_frame | 1 authenticated single frame; 0 includes unknown cardinality |
| variant | 0 unknown, 1 encoded, 2 creative with independently bound encoded ancestor |
| capabilities | bit 0 jpg8, 1 png8, 2 png16, 3 tif8, 4 tif16, 5 webp8; other bits forbidden |

Numerical return bitfields do not depend on host byte order:

| Bits | Meaning |
|---|---|
| 0–7 | Status; zero means a complete decision |
| 8–15 | Codec ID: 1 jpg, 2 png, 3 tif, 4 webp |
| 16–23 | Output precision: 8 or 16 |
| 24–31 | Canonical extension ID; same mapping as codec |
| 32–35 | Applicable option bits: quality, TIFF compression, GPS, target size |
| 36–63 | Reserved, always zero |

Refusals return only the status, with all decision fields zero:

| Status | Stable host error code |
|---|---|
| 1 | `original_invalid_host_facts` |
| 2 | `original_source_kind_unknown` |
| 3 | `original_raw_unsupported` |
| 4 | `original_source_variant_unsupported` |
| 5 | `original_container_unsupported` |
| 6 | `original_single_frame_required` |
| 7 | `original_precision_unsupported` |
| 8 | `original_writer_unavailable` |

Malformed enum/boolean/capability values are refused first. RAW is then refused
before container/precision evaluation, so a TIFF-shaped camera file cannot be
mistaken for an ordinary RGB16 TIFF. Unknown kind, variant, container, unproven
single-frame status, unsupported precision and missing required codec are
subsequent refusal gates. There is no fallback writer or precision.

## Decision matrix

| Authenticated bitmap container | Precision | Codec / extension | Applicable options |
|---|---|---|---|
| JPEG | 8 | jpg | quality, GPS, target size |
| PNG | 8 | png | quality (existing PNG compression mapping), GPS |
| PNG | 16 | png | none of these four options |
| TIFF | 8 | tif | TIFF compression, GPS |
| TIFF | 16 | tif | TIFF compression |
| WebP | 8 | webp | quality, GPS |

All rows additionally require a known supported source variant, authenticated
single frame and the exact matching installed writer capability. Precision 16
is accepted only for true PNG16/TIFF16 bitmap sources. Precision 0, 1, 2, 4, 10,
12, 14, 24, 32 and all other unsupported values are refused, not converted to 8.
Options are *applicability*, not encoded output guarantees. The host retains
existing writer semantics and its metadata/ICC/alpha/HDR restrictions.
Any target-size request requires every selected entry to resolve to JPEG8;
GPS plus any 16-bit entry is refused as one batch, not silently stripped.
TIFF compression applies only to TIFF entries with existing 8-/16-bit defaults.
The UI must not supply a bit-depth override with Original.

## Adapter, packaging and verification

`export_format_native.resolve(facts, capabilities)` marshals typed host facts,
calls the installed ABI and decodes its result. It has no Python policy
implementation. `readiness()` loads the installed helper and checks ABI version;
absence, load failure or mismatch reports unavailable. No runtime compiler,
package installation or download is attempted.

`packaging/build-export-format.sh` is an authored build recipe. Staging invokes
it to place `liblrt_export_format.so` in the packaged engine `bin/`, and places
this source, C header, Cargo manifest, README, authored Rust fixtures, project
licence and integration note in `third_party/export_format/`.

`tests.rs` and `engine/tests/test_export_format_native_unrun.py` are authored,
**UNRUN** acceptance fixtures. No Rust compilation, Python product imports,
tests, typechecks, build, codec execution or runtime claim was made in this
source delivery. Static source/AST/whitespace inspection is not a runtime pass.
