# Immutable full-source portrait fitting boundary

Status: AUTHORED / UNRUN. Source inspection and Python AST parsing only. No
product import, test, image decode, native execution, inference, build, download
or runtime memory/performance measurement was performed for this module.

## Defect and separation

Ordinary preview previously fitted hair reference statistics from its analysis
proxy while complete candidate/export fitted the full source. Resizing a proxy
is not full-source evidence and changing its label does not repair that mismatch.
The reusable `portrait_fit_source` provider supplies only the authenticated,
complete, immutable pre-edit source. It performs no repair, hair operation, skin
matching, portrait deformation, mask inference, crop or display conversion.

The preview host creates a lazy closure with its captured effective binding.
It invokes this provider only at the fitting phase, after subtracting existing
source, repaired-frame and prepared-field residents from available working
memory. Derived complete candidate/export already has the real full canonical source
and fits that source directly. Original delivery uses the snapshot-only provider
when fitting, independently of its output decoder: in particular, established
RAW8 delivery remains unchanged but cannot be used as RAW16 fitting evidence. The host
is responsible for passing the same full-source domain to measurement and for
mapping composition coordinates explicitly. This module alone is not evidence
that preview/export parity or composition integration has passed acceptance.

## API and ownership

`capture(engine, *, expected_source, byte_budget, cancelled=lambda: False)`
returns a frozen `FullSource` with:

- `source` / `binding`: fresh `{sha256, width, height}` dictionaries.
- `pixels`: a fresh C-contiguous little-endian float32 RGB ndarray wrapper over
  owned immutable bytes; it cannot be made writable with `setflags`.
- `input_sha256`: SHA-256 of the exact C-order little-endian float32 RGB bytes.
- `owned_bytes`: exactly `12 * width * height` retained after capture returns.
- `source_bits`: 8 or 16 for original decoder precision, 32 for creative assets.
- `kind`: `original` or `creative`.
- `peak_bytes`: the conservative incremental pre-admission charge.
- `descriptor`: fresh JSON-compatible metadata, not a serialized authorization.

`expected_source` is a guard, never caller authority to invent a source SHA.
The host must obtain the result from `capture`; directly constructed dataclasses
or externally submitted descriptor/pixel pairs are not authenticated results.
`capture_original(path, *, expected_source, expected_stamp, byte_budget,
cancelled=lambda: False)` is the frozen-original-snapshot counterpart. It reads
no engine and uses exactly the same source precision, decode, ICC, freeze and
memory contract. It verifies actual file bytes against the supplied SHA and its
five-element file stamp before and after; the two caller values alone never
establish authority. Snapshot owners retain and recheck their own document and
recipe fences. This keeps RAW8 output delivery separate from RAW16 fitting.

No full-resolution cache is added to the engine. The host releases the result
immediately after fitting and retains only the measured reference and evidence.
Every property wrapper can be mutated structurally without changing another
wrapper or its immutable backing storage; descriptor mutation is also isolated.

## Source authentication and precision

The actual active row, existing load token and document fences must stay stable.
`creative_derived_source.verify` authenticates the expected effective binding
both before and after decoding. Original file stamps also bracket inspection,
decoding, normalization, hashing and final source authentication. Original
binding hashes are read from real file bytes by the existing source owner, not
accepted from a caller. The loaded row's original-source stamp remains required.

Originals reuse `load_full` with `device='cpu'`, exact pixel cap and the real
8/16-bit request selected through `full_source_working.source_bits`. RAW metadata
is admitted through `libraw.identify` before decoding and RAW uses the existing
16-bit LibRaw-only branch, never the 8-bit self-DNG/embedded-preview alternative.
Unknown RAW dimensions reject. Orientation is applied only by the established
decoder; exact oriented dimensions are checked afterwards. Draft, half-size,
preview, substituted dimensions and reduced precision all reject.

`working_rgb(decoded)` preserves the established ICC contract: RGB8 has already
been converted to working sRGB; genuine RGB16 PNG/TIFF embedded ICC is converted
once through the existing LittleCMS16 route. RAW16 is already developed as sRGB.
The provider divides integer RGB by 255 or 65535 into float32; it does not apply
an additional gamma transform, quantize to RGB8 or discard genuine low bits.

Derived sources authenticate the canonical immutable asset and use
`creative_document_base.export_source` to obtain encoded working-sRGB float32.
The original file path and display/analysis proxy are never opened or read for
this branch. Native canonical conversion rejects unsupported alpha/HDR. The
provider additionally rejects nonfinite/out-of-range pixels, preserving finite
SDR float32 bit patterns without clipping. Original actual alpha is checked
before an RGB decoder can discard it, while native PNG16/TIFF16 retain their
existing stricter channel/precision gates. Unsupported float/HDR source metadata
is rejected rather than relabelled as SDR. A bounded streaming metadata gate
rejects PNG8 HDR/cICP declarations even when the installed Pillow does not
expose them in `image.info`; it seeks over pixel payloads and is not a PNG codec.

## Memory admission and cancellation

Maximum source size is 32 million pixels, matching complete candidate admission.
The provider requires an explicit positive remaining `byte_budget`; it does not
silently invent a budget from host RAM or reduce dimensions to fit.

- Derived incremental peak: `128 * N + 64 MiB`.
- Original incremental peak: `128 * N + 64 MiB + 2 * original_file_size`.
- Retained immutable output after capture: `12 * N`.

The two compressed-file charges cover the existing PNG16 decoder's frozen
container and pixel-bearing snapshot. Source files above 4 GiB reject; existing
codecs may have stricter limits. Existing canonical asset bytes are already
resident and must be counted by the host, not allocated/counting them again as
new provider storage. Peak reserve covers decoding, ICC, integer normalization,
full f32 staging and the immutable byte copy. This is conservative admission,
not a hard native allocator cap or an OOM guarantee. No 24 MP performance or
memory-use claim is implied.

Cancellation checks bracket admission, inspection, decoding, conversion and
publication, with additional checks per 64-row conversion block and per MiB of
output hashing. Existing decoder/ICC calls are synchronous and cannot be
interrupted inside their kernels by this wrapper. Cancellation or any changed
identity discards the private result; no document/cache state is published.

## Authored contracts awaiting execution

`engine/tests/test_portrait_fit_source_unrun.py` covers actual file-hash guards,
full decoder arguments, snapshot/current parity, output-independent RAW16 fitting, RGB16 low-bit/ICC-boundary ownership, RAW16 admission,
proxy/preview/half-size rejection, changed file/document/derived content,
pre-decode memory rejection, compressed-byte charging, genuine immutable output,
derived original-path exclusion, native alpha/HDR propagation, finite SDR checks
and cancellation. Mocked decoder/native returns do not establish codec/native
correctness, perceptual quality, UI behavior, memory performance or end-to-end
preview/export parity. Those remain explicit later acceptance work.
