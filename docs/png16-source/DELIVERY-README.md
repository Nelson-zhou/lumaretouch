# PNG16 sample references and verified output

Source implementation against `4f8207ec2ce109f524fa1249f54b8d2a0915a593`.
All codec, numerical, application, replay, UI, export and quality validation is
**AUTHORED / UNRUN**. This closes additional source routes, not acceptance of a
new handbook feature or full alpha/HDR processing.

## Sample-library ownership

Genuine high-bit reference selection must decode the retained original, convert
source ICC to working sRGB before any display quantization, and save full-source
reference pixels rather than its JPEG thumbnail. Original bytes, content hashes,
sample IDs and immutable reference assets remain independent. No saved reference
is rewritten to disguise a changed decoder or make old recipes appear equivalent.

New sample imports can use the shared native PNG16 and RGB16 TIFF path. The
sample-library implementation records exact supported/unsupported reasons after
real source admission. Actual nonopaque PNG16 is refused by the opaque retouch
decoder at native precision; it is not tested through Pillow RGBA8. Gray ICC,
APNG, unsupported PNG colour signalling and HDR remain guarded. Supported thumbnail display
is deliberately RGB8 after colour conversion and is never a reference asset.
Unsupported high-bit sources show an explicitly labelled unavailable placeholder,
not an approximate RGB8 photograph. Native PNG16 metadata, including eXIf after
IDAT, comes from the genuine decoder rather than initially opened Pillow metadata.

Legacy unsupported catalogue rows require deliberate re-import/reinspection of
the same original bytes. Only eligible unresolved rows can refresh support and
thumbnail metadata under the catalogue's existing revision/hash ownership.
Existing references, identity, group, trash state and prior recipes are not
silently migrated. See the sample-library documentation for exact behavior.

## Real RGB16 PNG delivery

The format selector now admits PNG alongside TIFF for 16-bit output. Other
formats cannot silently inherit a 16-bit label. Destination preview, frozen
per-document filenames, watermark/clean variants, actual writer and receipt use
the selected container consistently. TIFF retains its lossless compression
options; PNG16 does not accept a TIFF-only compression setting.

`png16_export.write_verified_png16` receives already-target-encoded uint16 RGB.
The pinned imagecodecs/libpng encoder retains the native samples and uses fixed
lossless level 6. The adapter validates the returned RGB16 container and inserts
the bounded target iCCP profile before IDAT, without adding source EXIF or an
orientation transform. Existing LittleCMS16 and float edit paths own source and
output colour conversion. PNG16 delivery does not create a synthetic 16-bit master
from an RGB8 original; unsupported inputs still fail at the genuine decoder.

Publication uses existing frozen destination resolution and descriptor-relative
no-clobber atomic commit. Actual committed PNG pixels, profile and normalized
metadata are then read back through the genuine 16-bit decoder and compared.
Failure after commit retains the file for inspection and is reported as failure,
not a successful delivery or a reason to overwrite/retry blindly. The failure
message identifies the retained path; a structured unverified committed-output
receipt for queue/variant recovery is not yet implemented. A conflict
skip does not fabricate readback evidence. Diagnostic level counts do not demand
that a naturally flat photograph use every possible sample value.

The writer admits encode/snapshot/readback memory before encoding. The decoder
also performs its fresh admission before readback; races and native allocations
are not an OOM guarantee. No performance claim or global cap increase is made.

## Metadata, colour and unsupported cases

- Native 16-bit TIFF and PNG retain the existing ICC-only metadata policy. Source
  EXIF/GPS passthrough remains unfinished. The UI makes that limit visible, and
  the backend explicitly rejects a 16-bit request to retain GPS.
- Source orientation has already been applied to pixels. Output has no source
  orientation tag; the writer does not claim to know whether one originally
  existed. ICC bytes are verified independently from exact pixel readback.
- PNG16 output is opaque SDR RGB, not RGBA/HDR or arbitrary PNG3 colour encoding.
  Wide-gamut profile conversion is not scene-linear HDR or lossless gamut mapping.
- Sample materialization and preset/reference replay retain the existing
  source-owned review contracts. They do not become new style models or claim
  equivalence with proprietary colour grading.

## Evidence and local acceptance

The prior [source contract](README.md) records the W3C PNG specification,
imagecodecs upstream binding/license and existing pinned dependency inventory.
No third-party implementation, package or binary was copied or downloaded.

Authored fixtures cover source16/ICC16 sample references, native-opacity refusal,
legacy reinspection, original/reference identity, PNG16 sample/ICC readback,
metadata rejection, output conflict/destination rules, actual container naming,
watermark/clean variants and UI format reconciliation. Static inspection does not
prove them. Qoder must run the fixtures and inspect representative photographs,
project/preset replay and actual output files before functional acceptance.
