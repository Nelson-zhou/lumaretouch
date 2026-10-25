# Lower-copy canonical JPEG/PNG import v1

Status: SOURCE AUTHORED / STATIC REVIEW ONLY / ALL RUNTIME ACCEPTANCE UNRUN.
This isolated module does not alter the legacy importer or document/history
state. No product import/execution, tests, build, compiler, typecheck, inference,
dependency/model download, install, Git write, or main-branch write was run.

## Scope and contracts

`creative_document_import_bounded.py` exposes version 1 `inspect_import`,
`import_bytes`, and `import_file`. The import functions return the existing
content-addressed asset ID after the entire immutable asset is validated and
interned. Existing canonical identity, original bytes, ICC bytes, little-endian
float32 linear-sRGB D65 and premultiplied alpha remain unchanged. File reads
freeze one regular-file snapshot and reject a changed stat/length/identity.

`ImportBudgetExceeded(ValueError)` is raised ONLY by the final admitted-plan
comparison, after supported format/precision/ICC-container/EXIF/XMP/alpha
metadata checks and before any pixel decoder/native transfer. This is the sole
fallback-eligible resource refusal. Initial source/header/file-snapshot reserve
failures, invalid budget arguments and unsupported/malformed metadata remain
ordinary refusal, not permission to retry a looser legacy decoder. A host may
catch this distinct exception only when its original exact full-import route is
actually available; this module never performs an implicit fallback itself.
Pixel-stream correctness and actual ICC transform validity still belong to the
decoder/colour library, not to the header-only plan.

This is a real lower-copy implementation, not a smaller coefficient on the
legacy `96N` admission. It has no full normalized RGB, coverage, encoded RGBA,
or second full linear ndarray. It still needs a full integer decoder raster
and an existing-format immutable canonical bytes asset. It is NOT end-to-end
tiled storage or an arbitrary edited-photo export solution.

The unchanged global source ceiling is 100,000,000 pixels; encoded original
bytes remain limited to 512,000,000 and ICC to 4,194,304. The new path has a
2,000,000,000-byte maximum application work budget. The default is 512,000,000,
not an implicit increase. The host must separately charge existing assets,
previews, models, concurrent work, global available memory and retained-payload
limits. A 24MP source/candidate pair with large retained provenance may still
fail the lens host's separate retained-payload limit.

## Lifetime and admission ledger

Let N be full source pixels, S original encoded bytes, I ICC bytes, D the integer
decoder raster (1/3/4 bytes per JPEG pixel; PNG at most 8), and B the smaller of
65,536 and N. Orientation changes dimensions/views, not N. JPEG supports actual
L/RGB/CMYK modes, so its D is respectively N/3N/4N. The maximum phases below are
compared, not incorrectly added as if every historical allocation stays live.

Shared overhead O = 64 MiB metadata allowance + 64 MiB safety allowance + I.
Block workspace T = 96B accounts for integer/crop/ICC serialization, straight
float32 RGBA (16B), its immutable native input snapshot (16B), and the existing
Rust transfer's temporary Vec (16B). It is a bounded BLOCK allowance, not 96N.

- Header: 2S + O. Marker/chunk extents, counts, total metadata, image size and
  frame/mode/precision are checked before full pixel decode.
- Decode: 2S + D + JPEG Pillow core allowance 4N + T + codec reserve + O.
  The Pillow core term is zero for PNG. PNG owns one critical-chunk compressed
  snapshot while imagecodecs creates the integer raster. JPEG owns one BytesIO
  snapshot and Pillow core while copying integer samples via bounded crops;
  it never uses whole-frame Pillow `tobytes`/NumPy conversion, which may retain
  both serialization pieces and their joined bytes.
- Native transfer: S + D + 16N private sink + T + ICC reserve + O. The decoder
  compressed snapshot and Pillow core are already out of scope. EXIF is a view;
  each bounded block uses the existing integer ICC helper and f32 normalization.
  Only the existing Rust ABI performs inverse sRGB transfer/premultiplication.
- Freeze: S + 32N + O. The integer decoder raster, all views and all block owners
  are gone BEFORE `bytes(private_bytearray)`. Both 16N owners coexist during
  that unavoidable immutable ownership copy. This is explicitly NOT zero-copy.
- Validate/intern: S + 16N + 4 MiB vector-validation scratch + O. Existing asset
  validation/hash and store operations retain immutable byte references; the
  earlier bytearray has already been released. Existing store contents are a
  host responsibility, not concealed inside this operation's budget.

Codec reserve is separately inspectable: PNG charges 8H row pointers + 64W
row/decoder allowance + 32 MiB native workspace. JPEG charges the padded complete
component DCT coefficient grid (64 signed 16-bit coefficients per block), even
for sequential input, plus 64W times component count times maximum vertical
sampling factor, and 32 MiB native workspace. The grid follows declared MCU
sampling, including progressive JPEG; it is not assumed to be a tiny scanline
buffer. Nonordinary sampling/hierarchical/arithmetic/dynamic-height JPEG fails
explicitly. ICC reserves another 64 MiB native transform allowance, 4I profile
buffer allowance and 64 KiB target-profile allowance while ICC is active.

The source-dependent formula is code, not a measured allocator result. Public
imagecodecs/Pillow/LittleCMS entrypoints do not expose an enforced allocation
quota. Their internal pools, ICC tag interpretation/LUT construction, allocator
fragmentation and freed-but-retained pages mean these conservative reserves do
NOT establish a hard process RSS bound. `runtime_verified` is explicitly false.
Package/build-specific allocation instrumentation and process/cgroup measurement
remain required. A platform-native allocation cap or isolated worker is a future
hard-RSS design, not something this module pretends to provide.

For arithmetic illustration only, N = 24,000,000, S = 24,000,000 and no ICC gives
the freeze phase 926,217,728 bytes. This is below the existing 2GB host case,
whereas 96N alone is 2,304,000,000. No 24MP image was decoded or timed to establish
that arithmetic, and it proves neither RSS nor successful photo acceptance.

## Colour, alpha, EXIF and precision

- JPEG uses the same Pillow decoder and preserves L/RGB/CMYK through the same
  `_to_working_srgb` conversion. Relative colorimetric intent and black-point
  compensation remain its existing settings. JPEG is opaque, not implicitly
  flattened RGBA. EXIF orientations 1 through 8 are applied once by views.
- PNG uses genuine imagecodecs/libpng integer samples, including RGB/RGBA16 and
  gray/gray-alpha16. Palette and tRNS chunks remain in the decoder snapshot;
  the exact alpha-bearing channel count is checked. A decoder that drops alpha
  fails instead of silently making the source opaque. No RGB8 staging for PNG16.
- PNG orientation also preserves Pillow-supported `Raw profile type exif` and
  `XML:com.adobe.xmp` in tEXt/zTXt/iTXt, plus raw-byte tEXt keyword `exif`.
  Semantic text is extracted before stripping decoder-only ancillary chunks,
  including text after IDAT. One relevant text value is limited to 1 MiB decoded
  bytes, with a 4 MiB aggregate for orientation metadata. Compressed values must
  be a complete single zlib stream within that bound; unrelated compressed text
  is still never inflated. These allocations remain inside the existing named
  metadata/safety allowances, not an uncharged second decoder raster.
- Orientation interpretation reuses base `Image.Image.getexif` on an object with
  NO pixel core. It never calls `PngImageFile.getexif`, whose implementation can
  invoke full image loading. Existing strict EXIF validation is retained; base
  Pillow precedence/fallback handles EXIF with no orientation plus XMP. Matching
  distinct carriers are accepted. Repeated semantic keywords, eXIf plus raw
  `exif` text, conflicting carrier values, duplicate XMP orientation declarations
  or XMP forms the existing Pillow matcher cannot interpret are explicit
  refusals, not silently selected first/last/default orientations. Raw profile
  text remains hexadecimal EXIF, not a new image or colour representation.
  Repeated optional Exif prefixes are normalized by a linear offset scan to one
  prefix in the private metadata view before EVERY Pillow EXIF read, avoiding
  Pillow's repeated-slice behavior. Immutable original source bytes never change.
- Metadata ordering also preserves the existing importer canvas: when eXIf or
  raw tEXt `exif` is present before IDAT, legacy Pillow getexif does not load later
  text. Preflight compares that early-visible orientation against the full scan.
  If, for example, early EXIF lacks orientation but late XMP says 6, this path
  explicitly refuses the incompatible ordering BEFORE the fallback-eligible
  budget check. It does not silently rotate the current source. Matching late
  metadata is allowed; XMP/raw EXIF without early `exif` remains supported.
- Bounded RGB blocks reuse `_colour_manage`, including LittleCMS16 with the same
  intent, black-point and NOOPTIMIZE behavior. Gray samples without ICC expand
  only within a block. The existing strict PNG16 colour-precedence validator
  rejects unsupported gray ICC, HDR/cICP conflicts or non-sRGB gamma/chromaticity
  without an effective supported profile. This new path intentionally does not
  inherit the older creative PNG helper's permissive ignoring of those tags.
- APNG/MPO/multipage content, malformed orientation, oversized metadata, bad CRC,
  duplicate colour/transparency metadata and unsupported colour declarations
  fail closed. No frame is selected implicitly. TIFF and RAW remain explicitly
  unsupported here, with no fallback/downsample or legacy mutation.
- All nonpixel ancillary bytes remain in immutable original provenance, even
  when unused compressed text is omitted from the PNG decoder-only snapshot.
- Integer-to-f32 casting and division preserve the legacy normalization order.
  Alpha is coverage, not gamma encoded. Existing native Rust produces canonical
  premultiplied float32. Canonical little-endian serialization is explicit.
  Same-decoder/native float-bit parity is expected, but NOT verified here.

ICC helpers currently construct a transform for each bounded block. This avoids
new colour math and full-image colour buffers, but may cost throughput. A reusable
transform session must retain the identical profile/intent/flags and add its own
verified memory ownership if optimized later. No speed claim is made now.

## Acceptance still required

`test_creative_import_bounded_unrun.py` contains authored header/budget/cancel
contracts and actual native parity cases for 8/16-bit PNG, sub-8-bit palette,
tRNS, gray/gray-alpha, alpha low bits, all EXIF orientations, RGB ICC, JPEG
L/RGB/CMYK/progressive, bounded native calls and cancellation before publication.
The orientation regression cases additionally cover XMP/raw-EXIF tEXt/zTXt/iTXt,
all eight orientations, text before/after IDAT, raw-byte tEXt EXIF, metadata-only
preflight without PNG loading, EXIF-without-orientation XMP fallback, consistent
and conflicting carriers, duplicate declarations, truncated/extra zlib streams,
inflated-byte limits and fallback-eligible exception boundaries.
Repeated-prefix cases also inspect the actual metadata passed to every base
Pillow getexif call, with numerical parity separately authored and UNRUN.
Early-EXIF-without-orientation plus after-IDAT XMP has explicit refusal and
legacy-canvas fixtures, including refusal before a fallback-eligible budget error.
Every test is UNRUN. Missing packaged native/codec prerequisites cause an explicit
skip, not a mock numerical acceptance. Non-sRGB profiles, CMYK/L ICC fixtures,
Adam7, malformed/hostile metadata, long thin images, corrupted/progressive JPEG,
source mutation, allocation failures, repeated imports, 24MP time/RSS and cross-
platform bit parity still require real fixture and integration acceptance.

The host must deliberately opt into this module; neutral/current-canonical
capture integration is a separate owner. The non-neutral edited-source 96N path,
RAW processing, final export and end-to-end tiled persistence remain separate
prerequisites. This module does not mark any lens/photo workflow complete.

## Source/spec traceability

The source contracts examined were `creative_document_import.py`,
`creative_layer_native.py`, `core/creative_layers/lib.rs`,
`creative_document_assets.py`, `png16_source.py`, `id_background_assets.py`,
`decode.py` and `color16.py`. The repository's specification provenance caveat
remains in `docs/acceptance/原件一致性与缺失资料清单.md`; this work does not claim a new
independent verification of the missing standalone Word manual or all package
requirements. No unsupported requirement is marked complete.

Primary references read for this design, not downloaded as project code:

- PNG Third Edition: https://www.w3.org/TR/png-3/
- Pillow image storage/serialization: https://pillow.readthedocs.io/en/stable/reference/Image.html
- imagecodecs PNG implementation: https://github.com/cgohlke/imagecodecs/blob/master/imagecodecs/_png.pyx
- libjpeg-turbo coefficient ownership: https://github.com/libjpeg-turbo/libjpeg-turbo/blob/main/src/jdcoefct.c

Those upstream pages explain API/storage behavior, not the exact installed build.
The project pins imagecodecs 2026.10.10 but permits Pillow >=11; package-specific
runtime evidence must identify the actual tested versions and native libraries.
The metadata correction also inspected local Pillow `Image.getexif`,
`PngImagePlugin.PngImageFile.getexif`, and its tEXt/zTXt/iTXt handlers as source
text only. In particular, header `getexif()` is not assumed to be pixel-decode-free.
