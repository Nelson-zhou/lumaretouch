# Original format: authenticated source facts (AUTHORED / UNRUN)

This is source-only implementation. No decoder, codec, native ABI, test, build,
benchmark, or application has been executed for this change. Static Python AST
parsing is syntax evidence only, not functional acceptance.

## Ownership and contract

`export_source_facts.freeze(row, entry, snapshot)` is a host-only adapter called
with an owned document and VCX's full source fingerprint. It does **not** choose
an output format. `export_format_native` passes the policy fields to the packaged
Rust resolver; no Python codec-decision fallback is supplied by this module.

Facts use `lrt.export-source-facts.v1` and exactly these keys:

- `container`: content-authoritative `jpeg/png/tiff/webp/unknown`.
- `source_kind`: `bitmap/raw/unknown`; non-null decoder `raw` metadata alone is
  not RAW evidence (`png16` and `tiff16` are bitmap decoder identities).
- `precision`: encoded sample depth, with unsupported/unknown precision refused.
- `single_frame`: no animation, MPO, extra TIFF image IFD, SubIFD, or first-frame
  truncation is admitted as a single supported original.
- `variant`: `encoded/creative/unknown`.
- `fingerprint`: exact full host fingerprint, including byte SHA-256 and path.
- `decoder_stamp`: inspector version, five-part source stat, encoded dimensions,
  EXIF orientation, container encoding, frame count and sample layout.
- `effective_asset`: exact encoded ancestor identity, or creative asset identity,
  dimensions and encoding plus the separately authenticated encoded ancestor.
- `schema` and `fact_id`: independently versioned strict schema and canonical
  SHA-256 over every other field. `validate` rejects extra/missing nested keys.

The original `managed_import.original_path` is never opened. It remains a logical
name; the retained exact-byte source is authenticated. Virtual copies have the
same facts when their physical/effective source is the same, while outer plans
retain separate document, recipe, copy and output identities.

Creative ancestors must match both the authenticated carrier SHA-256 and the
asset's retained unchanged `original` bytes. The effective RGBA asset's immutable
content identity is independently checked. Unknown ancestry explicitly refuses;
RAW ancestry still refuses through the policy. The carrier determines container
and encoded precision, not render pixels. Full rendering remains owned by the
existing creative-aware export pipeline, with its alpha/HDR refusal rules.

## Header-only inspection and bounds

Preview hashes/authenticates file identity and reads metadata, never pixels.
JPEG reads bounded pre-scan segments and detects MPF/MPO. PNG walks chunk framing
with seeks over compressed IDAT, detects APNG and HDR signalling, and reuses the
existing IHDR/EXIF helpers. WebP reads RIFF framing and VP8/VP8L/VP8X headers; it
rejects animation and inconsistent frame dimensions. Encoded payload validity,
opacity and real codec acceptance still require the full decoder before writing.
There is no claim that valid header facts imply valid compressed pixels. Duplicate
JPEG EXIF and late PNG colour/orientation metadata are explicitly refused rather
than assuming competing metadata readers choose the same orientation.

`raw.inspect_tiff` replaces the prior catch-all-false skeleton sniff with one
shared classic-TIFF/BigTIFF structural inspector. It returns bitmap/raw/unknown;
`has_raw_ifd` raises on an ambiguous or failed inspection instead of treating it
as a safe non-RAW bitmap. It bounds:

- 64 image IFDs including next-IFD and SubIFD links; repeated offsets/cycles fail.
- 4,096 tags per IFD and 16,384 total tags.
- 2 MiB total metadata reads and 16 MiB maximum declared individual tag value.
- 64 selected metadata values/children, exact table/value bounds and unsigned
  64-bit offset arithmetic. No pixel strip/tile or compressed payload is read.

Missing photometric metadata, duplicate tags, bad types, truncation, oversized
work, unsupported skeletons and ambiguous image topology are unknown/refused.
DNG version/CFA/LinearRaw identifies a RAW carrier. Native TIFF16 selection in
`decode.load_full` uses these authenticated content facts instead of `.tif`
filename selection, then delegates to the existing tifffile decoder. A known
bitmap TIFF also takes precedence over a misleading RAW filename suffix.

`verify_decoded(facts, decoded, snapshot)` does **not** sniff/re-resolve the source.
It compares the frozen facts to full decoder container, real uint8/uint16 dtype,
encoded source depth, source orientation, oriented dimensions and no-preview/no-half-size evidence.
The current frozen creative asset must still match its admitted identity. This
check precedes the existing writer, including the neutral RGB16 master path.

## Local acceptance required (all UNRUN)

`engine/tests/test_export_source_facts_unrun.py` authors synthetic bounded PNG,
JPEG and WebP headers; classic TIFF in both byte orders; malformed/cyclic IFDs;
a malformed BigTIFF excessive-count header (not a valid BigTIFF image); RAW-vs-
bitmap classification; renamed-container/copied-source selection; retained
creative-ancestor hash mismatch; schema tampering; and decoder
container/precision/orientation disagreement. The routing additions below are
also authored. Every one of these fixtures is UNRUN.

**Planned local/Qoder acceptance, not authored coverage or passing evidence:**
valid BigTIFF/strip/tile pixel fixtures; source drift before/during header freeze;
virtual-copy equivalence; a valid standalone WebP codec round-trip; duplicate
JPEG EXIF and late PNG metadata; missing/unavailable ancestor records; actual
JPEG/PNG8/TIFF8/WebP8 and genuine PNG16/TIFF16 codecs; valid/invalid compression;
opaque/nonopaque alpha; ICC/orientation; corrupt payload after valid headers;
real APNG/MPO/animated WebP/multi-IFD TIFF; native helper missing/ABI mismatch;
and source/path/recipe-preserving retry. No runtime or numerical pass is asserted.

### Vendor RAW routing compatibility correction (AUTHORED / UNRUN)

Known Olympus ORF magic `0x4f52`/`0x5352` and Panasonic RW2 magic `0x0055`
are TIFF-like **vendor RAW** headers, not unknown bitmap evidence. A bounded
8-byte `vendor_raw_family` recognizer preserves the existing LibRaw route in
`decode.is_raw`. The legacy `has_raw_ifd` self-DNG probe returns false for only
those recognized non-classic vendor containers so both preview and full 8/16-bit
RAW decoding proceed through existing LibRaw, not a new parser. The strict
`inspect_tiff` result remains unknown; Original-format admission still refuses
these sources. Malformed classic/BigTIFF is not rescued by a vendor suffix.

Known JPEG/WebP signatures likewise route to the existing bitmap decoder despite
a misleading `.dng`/`.nef` suffix; PNG retains the existing header-based route.
The signature is only decoder selection. Full codec validation still owns pixels
and can fail before publication. UNRUN fixtures cover vendor RAW full/proxy
routing, malformed TIFF refusal, and JPEG/WebP with misleading RAW suffixes.

### Metadata descriptor identity correction (AUTHORED / UNRUN)

Pathname equality before/after metadata probing is not sufficient: a temporary
replacement can be opened and then the old pathname restored. `freeze` now passes
the authenticated five-part stamp into `_headers`; the exact metadata descriptor
must match dev/ino/size/mtime/ctime before reading and again in `finally` after
reading. The extra TIFF descriptor receives the same binding through the optional
keyword-only `inspect_tiff(..., expected_stamp=...)`, and checks descriptor and
pathname stamps before/after. Legacy callers can omit the expected stamp but
retain their own before/after identity checks. No nested metadata open can borrow
another inode's source fingerprint.

Two deterministic descriptor-substitution fixtures are now **authored, UNRUN**:
one substitutes the outer bitmap metadata open while leaving the original path
unchanged; one substitutes only the nested TIFF inspector open. Real concurrent
rename/restore stress and full runtime acceptance remain planned local checks.
