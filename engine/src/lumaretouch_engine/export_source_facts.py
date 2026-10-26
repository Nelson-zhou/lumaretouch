"""Authenticated, metadata-only facts for Original-format export admission.

This module does not decide an output codec: the packaged Rust policy owns that
choice. Header inspection does not prove compressed payload validity. The real
full decoder must agree with these frozen facts before the existing writer runs.
No library-row format, filename suffix, or client-supplied fact is authoritative.
"""
from copy import deepcopy
import hashlib
import json
import os
import re
import stat
import struct

SCHEMA = 'lrt.export-source-facts.v1'
INSPECTOR = 'lrt.original-header.v1'
MAX_HEADERS = 4096
MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_EXIF_BYTES = 1024 * 1024
_HEX = re.compile(r'[0-9a-f]{64}\Z')
_FACT_KEYS = {'schema', 'container', 'source_kind', 'precision', 'single_frame',
              'variant', 'fingerprint', 'decoder_stamp', 'effective_asset', 'fact_id'}
_FINGERPRINT_KEYS = {'path', 'bytes', 'sha256', 'head_sha256', 'hash_level', 'mtime_ns', 'readonly'}
_STAMP_KEYS = {'inspector', 'file_stamp', 'width', 'height', 'orientation',
               'encoding', 'frames', 'source_variant'}


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _stamp(path):
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('original_source_not_regular')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _Headers:
    def __init__(self, stream, size):
        self.stream, self.size = stream, size
        self.used = 0

    def read(self, offset, length):
        if (offset < 0 or length < 0 or offset > self.size or length > self.size - offset):
            raise ValueError('original_header_bounds')
        self.used += length
        if self.used > MAX_METADATA_BYTES:
            raise ValueError('original_header_work_limit')
        self.stream.seek(offset)
        data = self.stream.read(length)
        if len(data) != length:
            raise ValueError('original_header_truncated')
        return data


def _orientation(exif):
    if exif.startswith(b'Exif\0\0'):
        exif = exif[6:]
    if len(exif) > MAX_EXIF_BYTES:
        raise ValueError('original_exif_limit')
    # Reuse the existing bounded metadata decoder; never call Image.load().
    from .png16_source import _exif_metadata
    return _exif_metadata(exif)[1]


def _base(container, width, height, precision, *, orientation=1, frames=1,
          source_variant='rgb', encoding='unsigned-integer', variant='encoded', source_kind='bitmap'):
    if width * height > 120_000_000:
        variant = 'unknown'
    return {'container': container, 'source_kind': source_kind,
            'precision': precision, 'single_frame': frames == 1, 'variant': variant,
            'decoder_stamp': {'inspector': INSPECTOR, 'file_stamp': [],
                              'width': width, 'height': height, 'orientation': orientation,
                              'encoding': encoding, 'frames': frames,
                              'source_variant': source_variant}}


def _jpeg(reader):
    if reader.read(0, 2) != b'\xff\xd8':
        raise ValueError('original_jpeg_header')
    offset, frame, orientation, frames, exif_seen = 2, None, 1, 1, False
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    for _ in range(MAX_HEADERS):
        prefix = reader.read(offset, 2)
        padding = 0
        while prefix == b'\xff\xff':
            padding += 1
            if padding > MAX_HEADERS:
                raise ValueError('original_jpeg_marker_padding_limit')
            offset += 1
            prefix = reader.read(offset, 2)
        if prefix[0] != 255 or prefix[1] in (0, 0xD8, 0xD9) or 0xD0 <= prefix[1] <= 0xD7:
            raise ValueError('original_jpeg_marker')
        marker = prefix[1]
        length = int.from_bytes(reader.read(offset + 2, 2), 'big')
        if length < 2:
            raise ValueError('original_jpeg_segment')
        payload = reader.read(offset + 4, length - 2)
        offset += length + 2
        if marker in sof:
            if frame is not None or len(payload) < 6:
                raise ValueError('original_jpeg_frame')
            precision, height, width, channels = struct.unpack('>BHHB', payload[:6])
            if not width or not height or len(payload) != 6 + channels * 3:
                raise ValueError('original_jpeg_dimensions')
            supported = marker in (0xC0, 0xC1, 0xC2) and channels in (1, 3)
            frame = _base('jpeg', width, height, precision,
                          source_variant='grey' if channels == 1 else 'rgb' if channels == 3 else 'unsupported',
                          encoding='jpeg-dct', variant='encoded' if supported else 'unknown')
        elif marker == 0xE1 and payload.startswith(b'Exif\0\0'):
            if exif_seen:
                raise ValueError('original_jpeg_duplicate_exif')
            exif_seen = True
            orientation = _orientation(payload)
        elif marker == 0xE2 and payload.startswith(b'MPF\0'):
            frames = 2  # MPO/multi-picture is not an ordinary one-image JPEG.
        elif marker == 0xDA:
            if frame is None:
                raise ValueError('original_jpeg_missing_frame')
            frame['single_frame'] = frames == 1
            frame['decoder_stamp'].update(orientation=orientation, frames=frames)
            return frame
    raise ValueError('original_jpeg_header_limit')


def _png(reader):
    from .png16_source import _header
    header = _header(reader.read(0, 33))
    if header is None:
        raise ValueError('original_png_header')
    offset, orientation, frames, hdr, idat, ended = 33, 1, 1, False, False, False
    seen = set()
    for _ in range(MAX_HEADERS):
        if offset == reader.size:
            break
        chunk = reader.read(offset, 8)
        length, kind = int.from_bytes(chunk[:4], 'big'), chunk[4:]
        end = offset + length + 12
        if length >= 2**31 or end > reader.size or any(not (65 <= b <= 90 or 97 <= b <= 122) for b in kind):
            raise ValueError('original_png_chunk')
        if kind == b'IHDR' or kind[2] & 32 or (not kind[0] & 32 and kind not in (b'PLTE', b'IDAT', b'IEND')):
            raise ValueError('original_png_unknown_or_duplicate_header')
        if kind == b'PLTE' and (kind in seen or idat):
            raise ValueError('original_png_palette_order')
        if kind in (b'acTL', b'fcTL', b'fdAT'):
            frames = 2
        if kind in (b'cICP', b'mDCV', b'cLLI'):
            hdr = True  # No implicit HDR interpretation/tone-map.
        if idat and kind in (b'eXIf', b'iCCP', b'sRGB', b'gAMA', b'cHRM'):
            raise ValueError('original_png_late_colour_or_orientation')
        if kind == b'eXIf':
            if kind in seen or length > MAX_EXIF_BYTES:
                raise ValueError('original_png_exif')
            orientation = _orientation(reader.read(offset + 8, length))
        if kind == b'IDAT':
            idat = True
        if kind == b'IEND':
            if length or not idat or end != reader.size:
                raise ValueError('original_png_end')
            ended = True
            break
        # Only framing and selected metadata are read. Payload CRC and decoder
        # correctness belong to full decoding, not this advisory header proof.
        seen.add(kind)
        offset = end
    if not ended:
        raise ValueError('original_png_chunk_limit_or_missing_end')
    variant = 'grey' if header.color_type in (0, 4) else 'palette' if header.color_type == 3 else 'rgb'
    if header.color_type in (4, 6):
        variant += '-alpha'
    return _base('png', header.width, header.height, header.bits, orientation=orientation,
                 frames=frames, source_variant=variant, encoding='png', variant='unknown' if hdr else 'encoded')


def _webp(reader):
    head = reader.read(0, 12)
    if head[:4] != b'RIFF' or head[8:] != b'WEBP' or int.from_bytes(head[4:8], 'little') + 8 != reader.size:
        raise ValueError('original_webp_riff')
    offset, width, height, canvas, frames, orientation, payloads = 12, 0, 0, None, 1, 1, 0
    alpha, extended, seen = False, False, set()
    for _ in range(MAX_HEADERS):
        if offset == reader.size:
            break
        chunk = reader.read(offset, 8)
        kind, length = chunk[:4], int.from_bytes(chunk[4:], 'little')
        end = offset + 8 + length + (length & 1)
        if end > reader.size:
            raise ValueError('original_webp_chunk')
        if kind in (b'VP8X', b'EXIF', b'ICCP', b'XMP ', b'ALPH') and kind in seen:
            raise ValueError('original_webp_duplicate_metadata')
        seen.add(kind)
        if kind == b'VP8X':
            if extended or length != 10 or offset != 12:
                raise ValueError('original_webp_extended_header')
            extended = True
            data = reader.read(offset + 8, 10)
            if data[0] & 0xC1 or data[1:4] != b'\0\0\0':
                raise ValueError('original_webp_reserved_bits')
            frames = 2 if data[0] & 2 else frames
            alpha |= bool(data[0] & 16)
            canvas = (1 + int.from_bytes(data[4:7], 'little'), 1 + int.from_bytes(data[7:10], 'little'))
        elif kind == b'VP8 ':
            if length < 10:
                raise ValueError('original_webp_vp8_header')
            data = reader.read(offset + 8, 10)
            if data[0] & 1 or data[3:6] != b'\x9d\x01\x2a':
                raise ValueError('original_webp_vp8_signature')
            width, height = (int.from_bytes(data[6:8], 'little') & 0x3fff,
                             int.from_bytes(data[8:10], 'little') & 0x3fff)
            payloads += 1
        elif kind == b'VP8L':
            if length < 5:
                raise ValueError('original_webp_lossless_header')
            data = reader.read(offset + 8, 5)
            value = int.from_bytes(data[1:], 'little')
            if data[0] != 0x2f or value >> 29:
                raise ValueError('original_webp_lossless_signature')
            width, height = 1 + (value & 0x3fff), 1 + ((value >> 14) & 0x3fff)
            alpha |= bool(value & (1 << 28))
            payloads += 1
        elif kind in (b'ANIM', b'ANMF'):
            frames = 2
        elif kind == b'ALPH':
            alpha = True
        elif kind == b'EXIF':
            if length > MAX_EXIF_BYTES:
                raise ValueError('original_webp_exif_limit')
            orientation = _orientation(reader.read(offset + 8, length))
        offset = end
    if offset != reader.size:
        raise ValueError('original_webp_chunk_limit')
    if frames == 1 and (payloads != 1 or not width or not height or (canvas and canvas != (width, height))):
        raise ValueError('original_webp_dimensions')
    if frames != 1:
        width, height = canvas or (width, height)
    return _base('webp', width, height, 8, orientation=orientation, frames=frames,
                 source_variant='rgb-alpha' if alpha else 'rgb', encoding='webp')


def _headers(path, *, expected_stamp=None):
    def descriptor_stamp(stream):
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('original_header_not_regular')
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if expected_stamp is not None and (not isinstance(expected_stamp, (list, tuple))
            or len(expected_stamp) != 5 or any(type(value) is not int for value in expected_stamp)):
        raise ValueError('original_header_expected_stamp')
    with open(path, 'rb') as stream:
        opened = descriptor_stamp(stream)
        expected = opened if expected_stamp is None else tuple(expected_stamp)
        if opened != expected:
            raise ValueError('original_header_descriptor_identity')
        reader = _Headers(stream, opened[2])
        try:
            head = reader.read(0, min(16, reader.size))
            if head[:2] in (b'II', b'MM'):
                from .raw import inspect_tiff
                result = inspect_tiff(path, expected_stamp=expected)
                if result['source_kind'] == 'unknown':
                    raise ValueError('original_tiff_unknown: ' + str(result.get('reason')))
                photo, channels = result['photometric'], result['samples']
                rgb = photo == 2 and channels == 3
                sample_layout = ('rgb' if rgb else 'rgb-alpha' if photo == 2 and channels == 4
                                 else 'grey' if photo in (0, 1) and channels == 1
                                 else 'grey-alpha' if photo in (0, 1) and channels == 2
                                 else 'palette' if photo == 3 and channels == 1
                                 else 'ycbcr' if photo == 6 and channels == 3 else 'unsupported')
                supported = (result['precision'] == 8 or (result['precision'] == 16 and rgb))
                supported &= (result['planar'] in (1, 2) and sample_layout != 'unsupported'
                              and result['compression'] in (1, 5, 7, 8, 32946, 32773))
                frame = _base('tiff', result['width'], result['height'], result['precision'],
                    orientation=result['orientation'], frames=result['ifd_count'],
                    source_variant=sample_layout,
                    variant='encoded' if supported else 'unknown', source_kind=result['source_kind'])
                frame['single_frame'] = result['single_frame']
                return frame
            if head.startswith(b'\x89PNG\r\n\x1a\n'):
                return _png(reader)
            if head.startswith(b'\xff\xd8'):
                return _jpeg(reader)
            if head.startswith(b'RIFF') and head[8:12] == b'WEBP':
                return _webp(reader)
        finally:
            # Check the very descriptor whose header bytes were consumed. A
            # transient pathname substitution/restoration must not bind a
            # different inode's metadata to the old file's fingerprint.
            if descriptor_stamp(stream) != expected:
                raise ValueError('original_header_descriptor_changed')
    # RAW and unsupported containers both remain ineligible. A filename suffix
    # cannot turn their encoded bytes into an authenticated bitmap container.
    return _base('unknown', 0, 0, 0, frames=0, source_variant='unsupported',
                 encoding='unknown', variant='unknown', source_kind='unknown')


def _effective(snapshot, fingerprint):
    record = snapshot.get('creative_base')
    if record is None:
        return {'kind': 'encoded', 'sha256': fingerprint['sha256']}
    from .creative_document_assets import _identity, MAX_ASSET_BYTES, MAX_ORIGINAL_BYTES, MAX_ICC_BYTES
    expected_keys = {'id', 'kind', 'width', 'height', 'encoding', 'alpha', 'source_hash',
                     'icc_hash', 'content', 'original', 'icc'}
    if (type(record) is not dict or set(record) != expected_keys or record['kind'] != 'rgba'
            or record['encoding'] != 'linear-srgb-d65' or record['alpha'] != 'premultiplied'
            or any(type(record[key]) is not bytes for key in ('content', 'original', 'icc'))
            or any(type(record[key]) is not int or record[key] < 1 for key in ('width', 'height'))
            or len(record['content']) != record['width'] * record['height'] * 16
            or len(record['content']) > MAX_ASSET_BYTES or len(record['original']) > MAX_ORIGINAL_BYTES
            or len(record['icc']) > MAX_ICC_BYTES):
        raise ValueError('original_effective_asset_invalid')
    ancestor = 'sha256:' + fingerprint['sha256']
    if (record['source_hash'] != ancestor or hashlib.sha256(record['original']).hexdigest() != fingerprint['sha256']
            or len(record['original']) != fingerprint['bytes']):
        raise ValueError('original_ancestor_unauthenticated')
    if record['icc_hash'] != 'sha256:' + hashlib.sha256(record['icc']).hexdigest() or _identity(record) != record['id']:
        raise ValueError('original_effective_asset_identity')
    return {'kind': 'creative', 'id': record['id'], 'width': record['width'], 'height': record['height'],
            'encoding': record['encoding'], 'alpha': record['alpha'], 'ancestor_sha256': fingerprint['sha256']}


def freeze(row, entry, snapshot):
    """Authenticate the physical carrier and separately bind effective pixels.

    VCX supplies owned document rows and its full fingerprint; paths from managed
    imports are the retained exact-byte copy, not managed_import.original_path.
    The latter is only a logical naming hint and is deliberately never opened.
    """
    if (not row.get('document_id') or row.get('document_id') != entry.get('document_id')
            or not row.get('source_asset_id') or row.get('source_asset_id') != entry.get('source_asset_id')
            or row.get('path') != entry.get('path') or type(snapshot) is not dict):
        raise ValueError('original_requires_authenticated_document')
    fingerprint = deepcopy(entry.get('fingerprint'))
    _validate_fingerprint(fingerprint)
    path = entry['path']
    if os.path.abspath(path) != fingerprint['path']:
        raise ValueError('original_fingerprint_path')
    # Reuse the immutable source owner; hash equality binds header metadata to
    # the exact byte identity, not merely a same-sized/renamed file. Hashing is
    # not pixel decoding. Stat guards cover the ensuing metadata-only reads.
    from .virtual_copy_source import fingerprint_for
    actual, before = fingerprint_for({'path': path, 'fingerprint': fingerprint})
    if actual != fingerprint:
        raise ValueError('original_source_changed_since_freeze')
    facts = _headers(path, expected_stamp=before)
    if _stamp(path) != before:
        raise ValueError('original_source_changed_during_header')
    facts['decoder_stamp']['file_stamp'] = list(before)
    effective = _effective(snapshot, fingerprint)
    if effective['kind'] == 'creative' and facts['variant'] == 'encoded':
        facts['variant'] = 'creative'
    facts.update(schema=SCHEMA, fingerprint=fingerprint, effective_asset=effective)
    facts['fact_id'] = _digest(facts)
    return validate(facts)


def _validate_fingerprint(value):
    if (type(value) is not dict or set(value) != _FINGERPRINT_KEYS or value['hash_level'] != 'full'
            or type(value['path']) is not str or not os.path.isabs(value['path']) or '\0' in value['path']
            or type(value['bytes']) is not int or value['bytes'] < 1
            or type(value['mtime_ns']) is not int or type(value['readonly']) is not bool
            or any(type(value[key]) is not str or not _HEX.fullmatch(value[key]) for key in ('sha256', 'head_sha256'))):
        raise ValueError('original_requires_full_source_fingerprint')


def validate(facts):
    """Strict nested schema/hash validation; no filesystem or policy resolution."""
    if (type(facts) is not dict or set(facts) != _FACT_KEYS or facts['schema'] != SCHEMA
            or facts['container'] not in ('jpeg', 'png', 'tiff', 'webp', 'unknown')
            or facts['source_kind'] not in ('bitmap', 'raw', 'unknown')
            or type(facts['precision']) is not int or not 0 <= facts['precision'] <= 64
            or type(facts['single_frame']) is not bool or facts['variant'] not in ('encoded', 'creative', 'unknown')):
        raise ValueError('original_source_facts_schema')
    _validate_fingerprint(facts['fingerprint'])
    stamp = facts['decoder_stamp']
    if (type(stamp) is not dict or set(stamp) != _STAMP_KEYS or stamp['inspector'] != INSPECTOR
            or type(stamp['file_stamp']) is not list or len(stamp['file_stamp']) != 5
            or any(type(value) is not int or value < 0 for value in stamp['file_stamp'])
            or any(type(stamp[key]) is not int or not 0 <= stamp[key] < 2**32 for key in ('width', 'height'))
            or type(stamp['orientation']) is not int or stamp['orientation'] not in range(1, 9)
            or type(stamp['frames']) is not int or not 0 <= stamp['frames'] <= 64
            or stamp['encoding'] not in ('unsigned-integer', 'jpeg-dct', 'png', 'webp', 'unknown')
            or stamp['source_variant'] not in ('rgb', 'grey', 'palette', 'rgb-alpha', 'grey-alpha', 'ycbcr', 'unsupported')
            or facts['single_frame'] != (stamp['frames'] == 1)
            or stamp['file_stamp'][2] != facts['fingerprint']['bytes']
            or stamp['file_stamp'][3] != facts['fingerprint']['mtime_ns']):
        raise ValueError('original_decoder_stamp_schema')
    asset = facts['effective_asset']
    if type(asset) is not dict:
        raise ValueError('original_effective_asset_schema')
    if asset.get('kind') == 'encoded':
        if set(asset) != {'kind', 'sha256'} or asset['sha256'] != facts['fingerprint']['sha256'] or facts['variant'] == 'creative':
            raise ValueError('original_encoded_binding_schema')
    elif asset.get('kind') == 'creative':
        if (set(asset) != {'kind', 'id', 'width', 'height', 'encoding', 'alpha', 'ancestor_sha256'}
                or type(asset['id']) is not str or not asset['id'].startswith('sha256:') or not _HEX.fullmatch(asset['id'][7:])
                or any(type(asset[key]) is not int or not 0 < asset[key] <= 100_000_000 for key in ('width', 'height'))
                or asset['width'] * asset['height'] > 100_000_000
                or asset['encoding'] != 'linear-srgb-d65' or asset['alpha'] != 'premultiplied'
                or asset['ancestor_sha256'] != facts['fingerprint']['sha256'] or facts['variant'] == 'encoded'):
            raise ValueError('original_creative_binding_schema')
    else:
        raise ValueError('original_effective_asset_kind')
    if facts['fact_id'] != _digest({key: value for key, value in facts.items() if key != 'fact_id'}):
        raise ValueError('original_source_facts_integrity')
    return facts


def verify_decoded(facts, decoded, snapshot):
    """Check full-decoder evidence against the frozen plan, never re-resolve it."""
    facts = validate(facts)
    if _effective(snapshot, facts['fingerprint']) != facts['effective_asset']:
        raise ValueError('original_effective_asset_changed')
    aliases = {'JPEG': 'jpeg', 'JPG': 'jpeg', 'PNG': 'png', 'TIFF': 'tiff', 'TIF': 'tiff', 'WEBP': 'webp'}
    raw = decoded.raw or {}
    if (facts['source_kind'] != 'bitmap' or not facts['single_frame'] or facts['variant'] == 'unknown'
            or aliases.get(str(decoded.fmt).upper()) != facts['container']
            or raw.get('source') in ('self_dng', 'libraw', 'libraw_preview')
            or raw.get('used_preview') or raw.get('half_size') or decoded.draft_used):
        raise ValueError('original_decoded_source_disagrees')
    precision = facts['precision']
    dtype = decoded.rgb.dtype
    if (type(decoded.src_bits) is not int or decoded.src_bits != precision or precision not in (8, 16)
            or dtype.kind != 'u' or dtype.itemsize * 8 != precision or not dtype.isnative
            or decoded.rgb.ndim != 3 or decoded.rgb.shape[2] != 3):
        raise ValueError('original_decoded_precision_disagrees')
    if precision == 16 and raw.get('source') != {'png': 'png16', 'tiff': 'tiff16'}.get(facts['container']):
        raise ValueError('original_native_decoder_disagrees')
    if precision == 8 and raw.get('source') is not None:
        raise ValueError('original_rgb8_decoder_disagrees')
    stamp = facts['decoder_stamp']
    if getattr(decoded, 'source_orientation', None) != stamp['orientation']:
        raise ValueError('original_decoded_orientation_disagrees')
    width, height = stamp['width'], stamp['height']
    if stamp['orientation'] in (5, 6, 7, 8):
        width, height = height, width
    if (decoded.w, decoded.h) != (width, height) or (decoded.src_w, decoded.src_h) != (width, height):
        raise ValueError('original_decoded_dimensions_disagree')


def capabilities():
    """Loaded codec capability evidence only; no test encode/decode or fallback."""
    result = {name: False for name in ('jpg8', 'png8', 'png16', 'tif8', 'tif16', 'webp8')}
    try:
        from PIL import Image, features
        Image.init()
        for name, fmt, codec in (('jpg8', 'JPEG', 'jpg'), ('png8', 'PNG', 'zlib'),
                                 ('tif8', 'TIFF', 'libtiff'), ('webp8', 'WEBP', 'webp')):
            result[name] = bool(fmt in Image.SAVE and fmt in Image.OPEN and features.check(codec))
    except (ImportError, OSError, AttributeError, RuntimeError):
        pass
    try:
        import imagecodecs
        result['png16'] = bool(imagecodecs.PNG.available and callable(imagecodecs.png_encode) and callable(imagecodecs.png_decode))
    except (ImportError, OSError, AttributeError, RuntimeError):
        pass
    try:
        import tifffile
        import imagecodecs
        result['tif16'] = bool(callable(tifffile.imwrite) and callable(tifffile.TiffFile)
                              and imagecodecs.DEFLATE.available and imagecodecs.LZW.available)
    except (ImportError, OSError, AttributeError, RuntimeError):
        pass
    return result
