"""Version 1 lower-copy JPEG/PNG import. AUTHORED; runtime acceptance UNRUN.

Only integer decoding and bounded ICC/normalization precede the existing native
RGBA transfer. One private canonical bytearray is frozen once, after integer
decoder owners are released. This is application working-set admission with
explicit conservative codec/ICC reserves, NOT a hard process-RSS guarantee.
TIFF/RAW and edited-photo capture retain their separate existing contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import re
import stat
import struct
import sys
import zlib

from .creative_document_assets import MAX_ICC_BYTES, MAX_ORIGINAL_BYTES, MAX_PIXELS

IMPORT_VERSION = 1
MAX_WORK_BYTES = 2_000_000_000
BLOCK_PIXELS = 65_536
MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_ORIENTATION_TEXT_BYTES = 1024 * 1024
MAX_ORIENTATION_METADATA_BYTES = 4 * 1024 * 1024
MAX_CHUNKS = 65_536
# These are named admission allowances, not measured allocator bounds. Metadata
# includes parser objects, bounded inflated ICC/EXIF, and temporary profile bytes.
METADATA_RESERVE = 64 * 1024 * 1024
SAFETY_RESERVE = 64 * 1024 * 1024
ICC_WORKSPACE_RESERVE = 64 * 1024 * 1024
VALIDATION_SCRATCH = 4 * 1024 * 1024
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_COLOUR_CHUNKS = {b'iCCP', b'sRGB', b'gAMA', b'cHRM', b'cICP', b'mDCV', b'cLLI'}
_ORIENTATION_KEYS = {b'exif', b'Raw profile type exif', b'XML:com.adobe.xmp', b'xmp'}


class ImportBudgetExceeded(ValueError):
    """Validated source semantics, but final pre-decode working-set plan refuses.

    Only _plan raises this fallback-eligible exception. Initial read/metadata
    reservation refusals, invalid budgets, and malformed/unsupported sources
    remain ordinary ValueError: they do not certify a safe legacy retry.
    """


@dataclass(frozen=True, slots=True)
class ImportMemoryPlan:
    """Inspectable simultaneous-live phases; never a runtime/RSS certificate."""
    format: str
    width: int
    height: int
    bits: int
    original_bytes: int
    icc_bytes: int
    decoded_sample_bytes: int
    codec_workspace_reserve: int
    icc_workspace_reserve: int
    block_workspace_bytes: int
    phases: tuple[tuple[str, int], ...]
    max_bytes: int
    version: int = IMPORT_VERSION
    bounds_kind: str = 'application-working-set-with-conservative-native-reserves'
    runtime_verified: bool = False

    @property
    def peak_bytes(self) -> int:
        return max(value for _, value in self.phases)


@dataclass(frozen=True, slots=True)
class _Source:
    format: str
    width: int
    height: int
    bits: int
    channels: int
    orientation: int
    icc: bytes
    mode: str
    codec_workspace: int
    png_parts: tuple[tuple[int, int], ...] = ()


def _cancel(cancelled):
    if cancelled():
        raise InterruptedError('Bounded creative import cancelled')


def _budget(max_bytes):
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_WORK_BYTES:
        raise ValueError('Invalid bounded creative import budget; maximum is 2,000,000,000 bytes')


def _extent(width, height):
    if (type(width) is not int or type(height) is not int or width < 1 or height < 1
            or width * height > MAX_PIXELS):
        raise ValueError('Bounded creative source exceeds the unchanged 100,000,000-pixel limit')


def _request(original, max_bytes, cancelled):
    _budget(max_bytes)
    if type(original) is not bytes or not 0 < len(original) <= MAX_ORIGINAL_BYTES:
        raise ValueError('Bounded creative import requires immutable original bytes within the source cap')
    _cancel(cancelled)
    # Header parsing itself has a budget, before Pillow/EXIF/ICC parsing begins.
    if 2 * len(original) + METADATA_RESERVE + SAFETY_RESERVE > max_bytes:
        raise ValueError('Bounded creative header/source snapshot exceeds working-set budget')


def _png_orientation_text(kind, payload):
    """Interpret only semantic text; unrelated compressed text stays compressed."""
    separator = next((index for index in range(min(80, len(payload))) if payload[index] == 0), -1)
    key = bytes(payload[:separator]) if separator >= 0 else bytes(payload[:80])
    if key not in _ORIENTATION_KEYS:
        return None
    if separator < 0:
        raise ValueError('PNG orientation text is missing its keyword separator')
    value = bytes(payload[separator + 1:])
    compressed = False
    if kind == b'zTXt':
        if not value or value[0] != 0:
            raise ValueError('PNG orientation zTXt has an unsupported compression method')
        value, compressed = value[1:], True
    elif kind == b'iTXt':
        if len(value) < 2 or value[0] not in (0, 1) or value[1] != 0:
            raise ValueError('PNG orientation iTXt has an invalid compression flag/method')
        compressed = value[0] == 1
        fields = value[2:].split(b'\0', 2)
        if len(fields) != 3:
            raise ValueError('PNG orientation iTXt is missing language/translated-key fields')
        language, translated, value = fields
        if len(language) + len(translated) > MAX_ORIENTATION_TEXT_BYTES:
            raise ValueError('PNG orientation iTXt headers exceed the metadata budget')
        try:
            language.decode('utf-8', 'strict')
            translated.decode('utf-8', 'strict')
        except UnicodeError as exc:
            raise ValueError('PNG orientation iTXt headers have invalid UTF-8') from exc
    if compressed:
        try:
            inflater = zlib.decompressobj()
            value = inflater.decompress(value, MAX_ORIENTATION_TEXT_BYTES + 1)
        except zlib.error as exc:
            raise ValueError('PNG orientation text has invalid compressed data') from exc
        if (len(value) > MAX_ORIENTATION_TEXT_BYTES or inflater.unconsumed_tail
                or not inflater.eof or inflater.unused_data):
            raise ValueError('PNG orientation text exceeds its 1 MiB inflated limit or has an incomplete/extra stream')
    if len(value) > MAX_ORIENTATION_TEXT_BYTES:
        raise ValueError('PNG orientation text exceeds its 1 MiB decoded limit')
    # Match PngImagePlugin: only tEXt keyword "exif" is raw bytes. Other
    # EXIF encodings under that keyword are unsupported, not silently ignored.
    if key == b'exif':
        if kind != b'tEXt':
            raise ValueError('PNG exif text requires the supported raw-byte tEXt form')
        result = value
    else:
        try:
            result = value.decode('utf-8' if kind == b'iTXt' else 'latin-1', 'strict')
        except UnicodeError as exc:
            raise ValueError('PNG orientation text has invalid character encoding') from exc
    return key.decode('latin-1'), result, len(value)


def _png_orientation(exif_payload, text_info):
    """Reuse base Pillow getexif on metadata only, NEVER PngImageFile.getexif.

    The latter can call load() and allocate a full Pillow PNG raster. A base
    Image.Image has no pixel core; only its bounded info dictionary is inspected.
    """
    from PIL import Image
    from .png16_source import _exif_metadata
    info = dict(text_info)
    if exif_payload is not None:
        if 'exif' in info:
            raise ValueError('Duplicate PNG EXIF carriers: eXIf and raw exif text')
        info['exif'] = b'Exif\0\0' + exif_payload

    def read_orientation(values):
        image = Image.Image()
        image.info = values
        try:
            orientation = Image.Image.getexif(image).get(274)
        except (OSError, SyntaxError, ValueError, TypeError, OverflowError, struct.error) as exc:
            raise ValueError('Invalid or unsupported PNG orientation metadata') from exc
        if orientation is not None and (type(orientation) is not int or orientation not in range(1, 9)):
            raise ValueError('PNG orientation metadata is outside 1 through 8')
        return orientation

    declared = []
    for key, value in info.items():
        if key in ('exif', 'Raw profile type exif'):
            try:
                blob = value if key == 'exif' else bytes.fromhex(''.join(value.split('\n')[3:]))
            except (ValueError, TypeError) as exc:
                raise ValueError('Invalid PNG raw EXIF profile text') from exc
            # Existing PNG16 EXIF validation, with the same optional Exif prefix
            # accepted by Pillow's loader. Strip by offset, not quadratic copies.
            offset = 0
            while blob.startswith(b'Exif\0\0', offset):
                offset += 6
            tiff = blob[offset:]
            _exif_metadata(tiff)
            # Normalize this PRIVATE metadata view before every Pillow read.
            # Merely validating stripped bytes would still let Exif.load strip
            # the original many-prefix blob quadratically. Provenance bytes are
            # untouched; one prefix has exactly the same TIFF/EXIF semantics.
            normalized = b'Exif\0\0' + tiff
            value = (normalized if key == 'exif' else
                     f'\nexif\n{len(normalized)}\n{normalized.hex()}\n')
            info[key] = value
        else:
            # Base Pillow deliberately recognizes only these two XMP forms.
            # Detect duplicate or unsupported declarations rather than silently
            # letting a first regex match or default orientation choose a canvas.
            values = []
            for match in re.finditer(r'(?<!/)tiff:Orientation\b', value):
                tail = value[match.end():match.end() + 64]
                item = re.match(r'(?:="([1-8])"|>([1-8])</tiff:Orientation>)', tail)
                if item is None:
                    raise ValueError('Unsupported or malformed PNG XMP orientation declaration')
                values.append(int(item[1] or item[2]))
            if len(values) > 1:
                raise ValueError('Duplicate or conflicting PNG XMP orientation declarations')
            if 'tiff:Orientation' in value and not values:
                raise ValueError('Unsupported PNG XMP orientation form')
            if key == 'xmp' and values:
                raise ValueError('PNG XMP orientation requires the supported XML:com.adobe.xmp keyword')
        item = read_orientation({key: value})
        if item is not None:
            declared.append(item)
    orientation = read_orientation(info)
    if any(item != orientation for item in declared):
        raise ValueError('Conflicting PNG EXIF/raw-profile/XMP orientation metadata')
    return orientation or 1


def _png_source(original, cancelled):
    # Reuse the existing strict PNG16 colour-precedence and EXIF contracts. The
    # pixel decoder below remains the already pinned imagecodecs/libpng, not a
    # new PNG pixel/filter/interlace implementation.
    from .png16_source import _header, _colour_metadata
    header = _header(original[:33])
    if header is None:
        raise ValueError('Invalid bounded PNG header')
    _extent(header.width, header.height)
    view = memoryview(original)
    parts = [(0, 33)]
    metadata = {}
    text_info = {}
    early_text_info = {}
    early_exif = None
    orientation_bytes = 0
    seen = set()
    offset, count, metadata_bytes, palette_entries = 33, 1, 0, 0
    idat_seen = idat_closed = ended = transparency = False
    singletons = {b'PLTE', b'tRNS', b'eXIf'} | _COLOUR_CHUNKS
    while offset < len(original):
        _cancel(cancelled)
        count += 1
        if count > MAX_CHUNKS or len(original) - offset < 12:
            raise ValueError('PNG chunk count exceeds budget or chunk header is truncated')
        length = int.from_bytes(view[offset:offset + 4], 'big')
        kind = bytes(view[offset + 4:offset + 8])
        end = offset + 12 + length
        if (length >= 2**31 or end > len(original)
                or any(not (65 <= value <= 90 or 97 <= value <= 122) for value in kind)):
            raise ValueError('Invalid PNG chunk type or length')
        payload = view[offset + 8:end - 4]
        if zlib.crc32(payload, zlib.crc32(kind)) & 0xffffffff != int.from_bytes(view[end - 4:end], 'big'):
            raise ValueError('Invalid PNG chunk CRC')
        if kind in (b'acTL', b'fcTL', b'fdAT'):
            raise ValueError('Animated PNG needs explicit frame selection; bounded import will not discard frames')
        if kind == b'IHDR' or kind[2] & 32 or (not kind[0] & 32 and kind not in (b'PLTE', b'IDAT', b'IEND')):
            raise ValueError('Duplicate PNG header, invalid reserved bit, or unknown critical chunk')
        if kind != b'IDAT':
            metadata_bytes += length + 12
            if metadata_bytes > MAX_METADATA_BYTES:
                raise ValueError('PNG metadata exceeds the 16 MiB parser budget')
            if idat_seen:
                idat_closed = True
        elif idat_closed:
            raise ValueError('PNG IDAT chunks must be consecutive')
        if kind in singletons:
            if kind in seen:
                raise ValueError('Duplicate PNG colour, EXIF, palette, or alpha metadata')
            seen.add(kind)
        if kind in _COLOUR_CHUNKS:
            if idat_seen or b'PLTE' in seen:
                raise ValueError('PNG colour metadata must precede palette and image data')
            metadata[kind] = bytes(payload)
        elif kind == b'eXIf':
            if length > 1024 * 1024:
                raise ValueError('PNG EXIF exceeds the existing 1 MiB limit')
            metadata[kind] = bytes(payload)
            orientation_bytes += length
            if not idat_seen:
                early_exif = metadata[kind]
        elif kind in (b'tEXt', b'zTXt', b'iTXt'):
            text = _png_orientation_text(kind, payload)
            if text is not None:
                key, value, text_bytes = text
                if key in text_info:
                    raise ValueError('Duplicate PNG orientation text keyword')
                text_info[key] = value
                orientation_bytes += text_bytes
                if not idat_seen:
                    early_text_info[key] = value
        elif kind == b'PLTE':
            if idat_seen or header.color_type in (0, 4) or not 0 < length <= 768 or length % 3:
                raise ValueError('Invalid PNG palette layout or position')
            palette_entries = length // 3
            if header.color_type == 3 and palette_entries > 2**header.bits:
                raise ValueError('PNG palette has more entries than its source bit depth')
            parts.append((offset, end))
        elif kind == b'tRNS':
            if idat_seen or header.color_type not in (0, 2, 3):
                raise ValueError('Invalid PNG transparency layout or position')
            if header.color_type == 3:
                if not 0 < length <= palette_entries:
                    raise ValueError('PNG palette transparency requires a matching preceding palette')
            elif length != (2 if header.color_type == 0 else 6):
                raise ValueError('PNG transparent colour has an invalid sample length')
            elif any(int.from_bytes(payload[index:index + 2], 'big') >= 2**header.bits
                     for index in range(0, length, 2)):
                raise ValueError('PNG transparent colour exceeds source sample precision')
            transparency = True
            parts.append((offset, end))
        elif kind == b'IDAT':
            if header.color_type == 3 and not palette_entries:
                raise ValueError('Indexed PNG requires a palette before image data')
            idat_seen = True
            parts.append((offset, end))
        elif kind == b'IEND':
            if length or not idat_seen or end != len(original):
                raise ValueError('Invalid PNG end, missing pixels, or trailing image/data')
            parts.append((offset, end))
            ended = True
        if orientation_bytes > MAX_ORIENTATION_METADATA_BYTES:
            raise ValueError('PNG decoded orientation metadata exceeds the 4 MiB aggregate limit')
        offset = end
    if not ended:
        raise ValueError('PNG has no complete IEND')
    icc, _ = _colour_metadata(metadata, header.color_type)
    icc = icc or b''
    if type(icc) is not bytes or len(icc) > MAX_ICC_BYTES:
        raise ValueError('Creative PNG ICC exceeds the unchanged 4 MiB limit')
    orientation = _png_orientation(metadata.get(b'eXIf'), text_info)
    if early_exif is not None or 'exif' in early_text_info:
        # Legacy PngImageFile.getexif skips load() when an "exif" info key is
        # already visible before IDAT. Late XMP can otherwise change the canvas
        # here while legacy/current capture sees only the early metadata. Refuse
        # that ordering disagreement, including before a budget-fallback signal.
        early_orientation = _png_orientation(early_exif, early_text_info)
        if early_orientation != orientation:
            raise ValueError('PNG late orientation metadata differs from the existing importer canvas')
    channels = (1 if header.color_type in (0, 4) else 3)
    channels += int(header.color_type in (4, 6) or transparency)
    # Explicit row-pointer/row-buffer allowance plus libpng/zlib reserve. The
    # public decoder has no allocator callback/cap, so this is not an RSS proof.
    workspace = 8 * header.height + 64 * header.width + 32 * 1024 * 1024
    return _Source('PNG', header.width, header.height, header.bits, channels,
                   orientation, icc, 'PNG', workspace, tuple(parts))


def _jpeg_frame(original, cancelled):
    """Bound the marker container, including metadata between progressive scans."""
    view = memoryview(original)
    offset, count, metadata_bytes = 2, 0, 0
    frame = None
    icc_parts = {}
    icc_count = icc_bytes = 0
    entropy = ended = scanned = False
    while offset < len(original):
        _cancel(cancelled)
        if entropy:
            offset = original.find(b'\xff', offset)
            if offset < 0:
                break
        elif original[offset] != 0xff:
            raise ValueError('JPEG marker framing is invalid')
        while offset < len(original) and original[offset] == 0xff:
            offset += 1
        if offset == len(original):
            break
        marker = original[offset]
        offset += 1
        if entropy and (marker == 0 or 0xd0 <= marker <= 0xd7):
            continue
        entropy = False
        count += 1
        if count > MAX_CHUNKS:
            raise ValueError('JPEG marker count exceeds the parser budget')
        if marker == 0xd9:
            if frame is None or not scanned or offset != len(original):
                raise ValueError('JPEG has no frame or contains trailing images/data')
            ended = True
            break
        if marker in (0, 1, 0xd8) or 0xd0 <= marker <= 0xd7 or offset + 2 > len(original):
            raise ValueError('Unsupported or truncated JPEG marker')
        length = int.from_bytes(view[offset:offset + 2], 'big')
        end = offset + length
        if length < 2 or end > len(original):
            raise ValueError('JPEG segment is truncated')
        payload = view[offset + 2:end]
        metadata_bytes += length + 2
        if metadata_bytes > MAX_METADATA_BYTES:
            raise ValueError('JPEG marker metadata exceeds the 16 MiB parser budget')
        if marker == 0xe2 and payload[:4] == b'MPF\x00':
            raise ValueError('MPO/multiple JPEG images require explicit image selection')
        if marker == 0xe2 and payload[:12] == b'ICC_PROFILE\x00':
            if len(payload) < 14:
                raise ValueError('Truncated JPEG ICC sequence header')
            sequence, total = payload[12], payload[13]
            if (not 1 <= sequence <= total or sequence in icc_parts
                    or (icc_count and total != icc_count)):
                raise ValueError('Invalid or duplicate JPEG ICC sequence')
            icc_count = total
            icc_bytes += len(payload) - 14
            if icc_bytes > MAX_ICC_BYTES:
                raise ValueError('JPEG ICC exceeds the unchanged 4 MiB limit')
            icc_parts[sequence] = payload[14:]
        if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
            if marker not in (0xc0, 0xc1, 0xc2) or frame is not None or len(payload) < 6:
                raise ValueError('Bounded JPEG supports one sequential/progressive 8-bit DCT frame')
            bits = payload[0]
            height, width = struct.unpack('>HH', payload[1:5])
            components = payload[5]
            if bits != 8 or components not in (1, 3, 4) or len(payload) != 6 + 3 * components:
                raise ValueError('Unsupported JPEG precision or component layout')
            _extent(width, height)
            factors = [(payload[7 + 3 * index] >> 4, payload[7 + 3 * index] & 15)
                       for index in range(components)]
            if (any(not 1 <= horizontal <= 4 or not 1 <= vertical <= 4 for horizontal, vertical in factors)
                    or sum(horizontal * vertical for horizontal, vertical in factors) > 10):
                raise ValueError('JPEG sampling factors exceed the bounded decoder contract')
            max_h = max(horizontal for horizontal, _ in factors)
            max_v = max(vertical for _, vertical in factors)
            mcus = ((width + 8 * max_h - 1) // (8 * max_h)) * ((height + 8 * max_v - 1) // (8 * max_v))
            # Progressive libjpeg may retain a padded 8x8 i16 coefficient grid
            # for every component. Charge it for sequential JPEG too.
            coefficients = mcus * sum(horizontal * vertical for horizontal, vertical in factors) * 64 * 2
            workspace = coefficients + 64 * width * components * max_v + 32 * 1024 * 1024
            frame = width, height, components, workspace
        if marker == 0xda:
            if frame is None:
                raise ValueError('JPEG scan precedes its frame')
            entropy = True
            scanned = True
        elif marker in (0xc8, 0xcc, 0xdc, 0xde, 0xdf):
            raise ValueError('Hierarchical/arithmetic/dynamic-height JPEG is not supported by bounded import')
        offset = end
    if not ended:
        raise ValueError('JPEG is missing a complete end marker')
    if len(icc_parts) != icc_count:
        raise ValueError('JPEG ICC sequence is incomplete; profile will not be silently ignored')
    expected_icc = b''.join(icc_parts[index] for index in range(1, icc_count + 1))
    if icc_count and not expected_icc:
        raise ValueError('JPEG ICC profile is empty')
    return frame, expected_icc


def _jpeg_source(original, cancelled):
    from PIL import Image
    (width, height, channels, workspace), expected_icc = _jpeg_frame(original, cancelled)
    with BytesIO(original) as stream, Image.open(stream, formats=('JPEG',)) as header:
        if (header.format != 'JPEG' or getattr(header, 'n_frames', 1) != 1
                or header.size != (width, height) or header.mode not in ('L', 'RGB', 'CMYK')):
            raise ValueError('JPEG header, original mode, or frame count differs from bounded preflight')
        if len(header.getbands()) != channels:
            raise ValueError('JPEG decoded component mode differs from its frame')
        icc = header.info.get('icc_profile') or b''
        if type(icc) is not bytes or len(icc) > MAX_ICC_BYTES or icc != expected_icc:
            raise ValueError('Invalid creative JPEG ICC profile')
        orientation = header.getexif().get(274, 1)
        if type(orientation) is not int or orientation not in range(1, 9):
            raise ValueError('Invalid JPEG EXIF orientation')
        mode = header.mode
    return _Source('JPEG', width, height, 8, channels, orientation, icc, mode, workspace)


def _plan(source, original_bytes, max_bytes):
    pixels = source.width * source.height
    width, height = ((source.height, source.width) if source.orientation >= 5
                     else (source.width, source.height))
    samples = pixels * source.channels * (2 if source.bits == 16 else 1)
    block = min(BLOCK_PIXELS, pixels)
    # 16B straight + 16B immutable native input + 16B Rust Vec staging,
    # <=24B integer/Pillow ICC owners, <=24B crop/normalization/serialization
    # scratch. No full-frame float workspace is hidden in this term.
    block_workspace = block * 96
    icc_workspace = (ICC_WORKSPACE_RESERVE + 4 * len(source.icc) + 64 * 1024
                     if source.icc else 0)
    overhead = METADATA_RESERVE + SAFETY_RESERVE + len(source.icc)
    phases = (
        ('header', 2 * original_bytes + overhead),
        # PNG: original + critical-chunk snapshot + integer raster. JPEG:
        # original + BytesIO snapshot + <=4B Pillow core + integer raster.
        ('decode', 2 * original_bytes + samples + (4 * pixels if source.format == 'JPEG' else 0)
         + source.codec_workspace + block_workspace + overhead),
        ('native-transfer', original_bytes + samples + 16 * pixels
         + block_workspace + icc_workspace + overhead),
        # Decoder/image/array and every bounded block are out of scope BEFORE
        # bytes(bytearray). The private mutable and final immutable 16N coexist.
        ('freeze', original_bytes + 32 * pixels + overhead),
        ('validate-and-intern', original_bytes + 16 * pixels + VALIDATION_SCRATCH + overhead),
    )
    plan = ImportMemoryPlan(source.format, width, height, source.bits, original_bytes,
                            len(source.icc), samples, source.codec_workspace, icc_workspace,
                            block_workspace, phases, max_bytes)
    if plan.peak_bytes > max_bytes:
        phase, required = max(phases, key=lambda item: item[1])
        raise ImportBudgetExceeded(f'Bounded creative {phase} requires declared working set {required} bytes; budget is {max_bytes}')
    return plan


def _prepare(original, max_bytes, cancelled):
    _request(original, max_bytes, cancelled)
    if original.startswith(PNG_SIGNATURE):
        source = _png_source(original, cancelled)
    elif original.startswith(b'\xff\xd8'):
        source = _jpeg_source(original, cancelled)
    else:
        raise ValueError('Bounded import v1 supports JPEG/PNG only; TIFF/RAW need their existing explicit path')
    return source, _plan(source, len(original), max_bytes)


def inspect_import(original, *, max_bytes=512_000_000, cancelled=lambda: False):
    """Validate source headers/metadata and return a plan without pixel decode."""
    return _prepare(original, max_bytes, cancelled)[1]


def _decode_png(original, source, cancelled):
    import imagecodecs
    import numpy as np
    _cancel(cancelled)
    view = memoryview(original)
    # No unused compressed text/ICC/EXIF chunk reaches libpng. This snapshot is
    # a decoder input only; canonical provenance remains the unchanged original.
    pixel_snapshot = b''.join(view[start:end] for start, end in source.png_parts)
    pixels = imagecodecs.png_decode(pixel_snapshot)
    expected = (source.height, source.width)
    if source.channels != 1:
        expected += (source.channels,)
    if (not isinstance(pixels, np.ndarray) or pixels.shape != expected
            or pixels.dtype != np.dtype(np.uint16 if source.bits == 16 else np.uint8)
            or not pixels.dtype.isnative):
        raise ValueError('PNG native decoder changed dimensions, precision, or required alpha layout')
    _cancel(cancelled)
    return pixels[:, :, None] if source.channels == 1 else pixels


def _decode_jpeg(original, source, cancelled):
    import numpy as np
    from PIL import Image
    _cancel(cancelled)
    with BytesIO(original) as stream, Image.open(stream, formats=('JPEG',)) as image:
        if image.mode != source.mode or image.size != (source.width, source.height):
            raise ValueError('JPEG decoder disagrees with its validated source header')
        image.load()
        _cancel(cancelled)
        pixels = np.empty((source.height, source.width, source.channels), dtype=np.uint8)
        # Avoid Image.tobytes()/np.asarray(image) on the full frame: Pillow may
        # assemble all encoded chunks and their joined bytes simultaneously.
        rows = max(1, BLOCK_PIXELS // source.width)
        for y in range(0, source.height, rows):
            bottom = min(source.height, y + rows)
            for x in range(0, source.width, BLOCK_PIXELS):
                _cancel(cancelled)
                right = min(source.width, x + BLOCK_PIXELS)
                with image.crop((x, y, right, bottom)) as part:
                    block = np.asarray(part, dtype=np.uint8)
                    if source.channels == 1:
                        block = block[:, :, None]
                    pixels[y:bottom, x:right] = block
                    del block
    return pixels


def _working_rgb(block, source):
    """Only bounded integer ICC conversion; existing intent/flags remain intact."""
    import numpy as np
    if source.format == 'PNG':
        from .id_background_assets import _colour_manage
        rgb = block[:, :, :1] if source.channels <= 2 else block[:, :, :3]
        if rgb.shape[2] == 1:
            rgb = np.repeat(rgb, 3, axis=2)
        return _colour_manage(rgb, source.icc or None)
    from PIL import Image
    from .decode import _to_working_srgb
    raw = block[:, :, 0] if source.mode == 'L' else block
    # Preserve CMYK/L through source ICC conversion, rather than prematurely
    # converting JPEG to RGB and applying a profile to the wrong colour model.
    with Image.fromarray(raw, mode=source.mode) as image:
        converted = _to_working_srgb(image, source.icc or None)
        try:
            return np.asarray(converted, dtype=np.uint8)
        finally:
            if converted is not image:
                converted.close()


def _canonical_sink(pixels, source, plan, cancelled):
    import numpy as np
    from .creative_document_import import _orient
    from .creative_layer_native import native, P, CreativeLayerNativeRejected
    _cancel(cancelled)
    lib = native()
    oriented = _orient(pixels, source.orientation)
    if oriented.shape[:2] != (plan.height, plan.width):
        raise ValueError('Oriented source dimensions do not match bounded plan')
    sink = bytearray(plan.width * plan.height * 16)
    destination = np.frombuffer(sink, dtype='=f4').reshape(plan.height, plan.width, 4)
    maximum = np.float32(65535.0 if source.bits == 16 else 255.0)
    rows = max(1, BLOCK_PIXELS // plan.width)
    for y in range(0, plan.height, rows):
        bottom = min(plan.height, y + rows)
        for x in range(0, plan.width, BLOCK_PIXELS):
            _cancel(cancelled)
            right = min(plan.width, x + BLOCK_PIXELS)
            block = np.ascontiguousarray(oriented[y:bottom, x:right])
            rgb = _working_rgb(block, source)
            if rgb.shape != (*block.shape[:2], 3) or rgb.dtype != block.dtype:
                raise ValueError('Bounded ICC conversion changed integer precision or dimensions')
            rgba = np.empty((*block.shape[:2], 4), dtype=np.float32)
            # Same uint->f32 then f32 divide as legacy import, without full
            # normalized RGB/coverage arrays. No transfer-function pixel math.
            rgba[:, :, :3] = rgb
            rgba[:, :, :3] /= maximum
            if source.format == 'PNG' and source.channels in (2, 4):
                rgba[:, :, 3] = block[:, :, -1]
                rgba[:, :, 3] /= maximum
            else:
                rgba[:, :, 3] = 1.0
            immutable = np.frombuffer(rgba.tobytes(order='C'), dtype='=f4')
            target = destination[y:bottom, x:right]
            if not target.flags.c_contiguous or immutable.size // 4 > BLOCK_PIXELS:
                raise ValueError('Bounded native import block must be contiguous and within ABI cap')
            _cancel(cancelled)
            code = lib.lrt_creative_linearize_rgba(
                immutable.ctypes.data_as(P), target.ctypes.data_as(P), immutable.size)
            if code:
                raise CreativeLayerNativeRejected(code, 'Bounded creative import')
            if sys.byteorder != 'little':
                target.byteswap(inplace=True)
            # Do not retain the previous block while allocating the next one.
            del block, rgb, rgba, immutable, target
    _cancel(cancelled)
    return sink


def import_bytes(original, assets, *, max_bytes=512_000_000, cancelled=lambda: False):
    """Intern one complete immutable asset, never a partial document/history edit.

    max_bytes admits this operation's explicit live owners plus named native
    reserves. The host must separately charge existing assets, previews, models,
    concurrent jobs and available-memory limits. No process-RSS guarantee.
    """
    from .creative_document_assets import make_asset
    source, plan = _prepare(original, max_bytes, cancelled)
    pixels = (_decode_png(original, source, cancelled) if source.format == 'PNG'
              else _decode_jpeg(original, source, cancelled))
    sink = _canonical_sink(pixels, source, plan, cancelled)
    del pixels  # includes its underlying owner, after all conversion views end
    _cancel(cancelled)
    content = bytes(sink)  # REQUIRED immutable ownership copy: charge both 16N
    del sink
    _cancel(cancelled)
    record = make_asset('rgba', plan.width, plan.height, content,
                        original=original, icc=source.icc)
    _cancel(cancelled)
    return assets.intern(record)


def import_file(path, assets, *, max_bytes=512_000_000, cancelled=lambda: False):
    """Snapshot one selected regular file once; reject concurrent replacement."""
    _budget(max_bytes)
    _cancel(cancelled)
    source = Path(path)
    with source.open('rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_ORIGINAL_BYTES:
            raise ValueError('Bounded creative source must be a nonempty regular file within the source cap')
        if 2 * before.st_size + METADATA_RESERVE + SAFETY_RESERVE > max_bytes:
            raise ValueError('Bounded creative file snapshot exceeds working-set budget')
        original = handle.read(before.st_size + 1)
        after = os.fstat(handle.fileno())
    stamp = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if (len(original) != before.st_size or stamp(before) != stamp(after)
            or stamp(after) != stamp(source.stat())):
        raise ValueError('Creative source changed while its immutable bytes were read')
    return import_bytes(original, assets, max_bytes=max_bytes, cancelled=cancelled)
