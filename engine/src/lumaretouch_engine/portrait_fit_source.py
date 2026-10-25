# SPDX-License-Identifier: GPL-3.0-or-later
"""Authenticated full immutable source for portrait reference fitting only.

The host supplies an expected binding, never authoritative pixels or a digest.
Original RGB8/RGB16 follows the existing export decoder/ICC boundary; canonical
creative sources follow its exact float bridge. No display proxy, repairs,
portrait transform, alpha matte, HDR clipping or persistent cache lives here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re

MAX_PIXELS = 32_000_000
MAX_SOURCE_BYTES = 4 * 1024**3
SCRATCH_BYTES = 64 * 1024**2
BYTES_PER_PIXEL = 128
ENCODING = 'encoded-srgb-f32-v1'


def _binding(value):
    if (type(value) is not dict or set(value) != {'sha256', 'width', 'height'}
            or type(value['sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', value['sha256']) is None
            or any(type(value[k]) is not int or value[k] < 1 for k in ('width', 'height'))
            or value['width'] * value['height'] > MAX_PIXELS):
        raise ValueError('Portrait fitting requires an exact full-source binding within 32 MP')
    return dict(value)


def memory_estimate(source, *, original_bytes=0):
    """Conservative incremental decode/conversion/freeze peak, not an OOM guarantee.

    The host must first subtract its already resident source, repairs and fields.
    Two compressed input snapshots cover the existing PNG16 codec. The retained
    canonical creative asset is already resident and is not charged twice here.
    """
    source = _binding(source)
    if type(original_bytes) is not int or not 0 <= original_bytes <= MAX_SOURCE_BYTES:
        raise ValueError('Portrait fitting original file exceeds its input byte budget')
    return source['width'] * source['height'] * BYTES_PER_PIXEL + 2 * original_bytes + SCRATCH_BYTES


@dataclass(frozen=True)
class FullSource:
    """Owned, immutable encoded float32 pixels; capture is the authority boundary.

    Instances are in-process results, not serialized approvals. The host must
    obtain one from capture rather than construct one from caller metadata.
    Every pixels property is a fresh read-only ndarray wrapper over bytes, so
    neither setflags(write=True) nor mutation of a descriptor leaks into storage.
    """
    source_sha256: str
    width: int
    height: int
    input_sha256: str
    source_bits: int
    kind: str
    peak_bytes: int
    _content: bytes = field(repr=False)

    @property
    def pixels(self):
        import numpy as np
        return np.frombuffer(self._content, dtype='<f4').reshape(self.height, self.width, 3)

    @property
    def source(self):
        return {'sha256': self.source_sha256, 'width': self.width, 'height': self.height}

    @property
    def binding(self):
        return self.source

    @property
    def owned_bytes(self):
        return len(self._content)

    @property
    def descriptor(self):
        return {'version': 1, 'source': self.source, 'encoding': ENCODING,
                'input_sha256': self.input_sha256, 'source_bits': self.source_bits,
                'kind': self.kind, 'owned_bytes': self.owned_bytes,
                'peak_bytes': self.peak_bytes}


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Full portrait fitting source capture cancelled')


def _active(engine):
    index = getattr(engine, '_doc_index', -1)
    rows = getattr(engine, '_docs', ())
    if type(index) is not int or not 0 <= index < len(rows) or type(rows[index]) is not dict:
        raise ValueError('Full portrait fitting needs an active owned document')
    row = rows[index]
    # Read existing fences without initializing/mutating document ownership.
    fence = row.get('_lrt_runtime_version') or {}
    return row, (index, getattr(engine, '_load_id', None), row.get('document_id'),
                 row.get('document_revision'), fence.get('id'), fence.get('revision'))


def _assert_active(engine, row, token):
    current, latest = _active(engine)
    if current is not row or latest != token:
        raise ValueError('Active portrait fitting document changed during capture')


def _admit(source, byte_budget, original_bytes=0):
    peak = memory_estimate(source, original_bytes=original_bytes)
    if peak > byte_budget:
        raise MemoryError('Full portrait fitting source exceeds remaining decode budget; no proxy fallback')
    return peak


def _require_sdr_png8(path, cancelled):
    """Bounded metadata gate for HDR chunks older Pillow versions may ignore.

    This does not decode PNG pixels or replace the existing PNG16 codec. Seek
    over payloads, retaining only the four cICP bytes. Reject HDR declarations
    even if Pillow omitted them from image.info instead of silently relabelling
    their samples as encoded SDR. The full decoder still owns pixel validation.
    """
    import os
    import zlib
    with open(path, 'rb') as stream:
        total = os.fstat(stream.fileno()).st_size
        if stream.read(8) != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Portrait fitting PNG signature changed')
        cicp = icc = False
        for _ in range(65536):
            _poll(cancelled)
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError('Portrait fitting PNG metadata is truncated')
            length, kind = int.from_bytes(header[:4], 'big'), header[4:]
            if length >= 2**31 or length + 4 > total - stream.tell():
                raise ValueError('Portrait fitting PNG metadata exceeds its container')
            if kind in (b'mDCV', b'cLLI'):
                raise ValueError('Portrait fitting cannot relabel PNG HDR metadata as SDR')
            if kind == b'cICP':
                if cicp or length != 4:
                    raise ValueError('Portrait fitting PNG cICP metadata is invalid')
                data, crc = stream.read(4), stream.read(4)
                if (data != b'\x01\x0d\x00\x01'
                        or zlib.crc32(data, zlib.crc32(kind)) & 0xffffffff != int.from_bytes(crc, 'big')):
                    raise ValueError('Portrait fitting requires supported SDR PNG cICP metadata')
                cicp = True
            else:
                icc = icc or kind == b'iCCP'
                stream.seek(length + 4, 1)
            if cicp and icc:
                raise ValueError('Portrait fitting cannot ignore PNG cICP/ICC colour precedence')
            if kind == b'IEND':
                if length != 0 or stream.tell() != total:
                    raise ValueError('Portrait fitting PNG end metadata is invalid')
                return
        raise ValueError('Portrait fitting PNG metadata exceeds its chunk budget')


def _inspect_original(path, source, cancelled):
    """Check dimensions and precision before alpha checks or full pixel decoding."""
    from .decode import is_raw, EXIF_ORIENTATION, SWAPPED_ORIENTATIONS
    from .full_source_working import source_bits, require_opaque_8bit
    from PIL import Image
    _poll(cancelled)
    if is_raw(path):
        from .ops import libraw
        dimensions = libraw.identify(path)
        # LibRaw identify reports pre-orientation output extent. Allow the
        # swapped axes here; Decoded's oriented dimensions are checked exactly.
        if (dimensions is None or type(dimensions.get('w')) is not int
                or type(dimensions.get('h')) is not int
                or sorted((dimensions['w'], dimensions['h'])) != sorted((source['width'], source['height']))):
            raise ValueError('Portrait fitting RAW full dimensions cannot be authenticated before decoding')
        return 16
    with Image.open(path) as image:
        orientation = image.getexif().get(EXIF_ORIENTATION, 1) or 1
        if type(orientation) is not int or orientation not in range(1, 9):
            raise ValueError('Portrait fitting source has invalid orientation')
        extent = (image.height, image.width) if orientation in SWAPPED_ORIENTATIONS else image.size
        if extent != (source['width'], source['height']):
            raise ValueError('Portrait fitting source dimensions changed before decoding')
        bits = source_bits(path, image)
        if bits > 16 or image.mode == 'F' or image.mode == 'I' and bits <= 8:
            raise ValueError('Portrait fitting cannot quantize or clip an unsupported float/HDR source')
        # PNG16's existing codec owns native alpha, cICP/ICC precedence and HDR
        # validation. Other inputs must not silently discard declared HDR data.
        if image.format != 'PNG' or bits <= 8:
            cicp = image.info.get('cicp', image.info.get('cICP'))
            if (cicp is not None and (type(cicp) not in (bytes, tuple, list)
                    or tuple(cicp) != (1, 13, 0, 1) or image.info.get('icc_profile'))
                    or any(image.info.get(key) is not None for key in ('mDCV', 'cLLI', 'mdcv', 'clli'))):
                raise ValueError('Portrait fitting requires a supported SDR source encoding')
        _poll(cancelled)
        if bits <= 8:
            if image.format == 'PNG':
                _require_sdr_png8(path, cancelled)
            require_opaque_8bit(image)
        elif image.format != 'PNG' and ('A' in image.getbands() or 'transparency' in image.info):
            raise ValueError('Portrait fitting cannot discard high-bit source alpha')
        return 16 if bits > 8 else 8


def _freeze(pixels, source, cancelled):
    """Normalize integers only; preserve creative encoded float32 bit patterns."""
    import numpy as np
    shape = (source['height'], source['width'], 3)
    if (type(pixels) is not np.ndarray or pixels.shape != shape
            or pixels.dtype not in (np.dtype('uint8'), np.dtype('uint16'), np.dtype('float32'))):
        raise ValueError('Portrait fitting needs exact full-source RGB8, RGB16 or encoded float32')
    result = np.empty(shape, dtype='<f4')
    divisor = np.float32(255 if pixels.dtype == np.uint8 else 65535 if pixels.dtype == np.uint16 else 1)
    for start in range(0, source['height'], 64):
        _poll(cancelled)
        block = pixels[start:start + 64]
        if not np.isfinite(block).all() or pixels.dtype == np.float32 and (np.any(block < 0) or np.any(block > 1)):
            raise ValueError('Portrait fitting source is not finite SDR; clipping is forbidden')
        if pixels.dtype == np.float32:
            result[start:start + 64] = block
        else:
            np.divide(block, divisor, out=result[start:start + 64], casting='unsafe')
    _poll(cancelled)
    content = result.tobytes(order='C')
    del result
    digest = hashlib.sha256()
    view = memoryview(content)
    for start in range(0, len(content), 1024 * 1024):
        _poll(cancelled)
        digest.update(view[start:start + 1024 * 1024])
    return content, digest.hexdigest()


def _verify_file(path, source, stamp):
    from . import local_mask_state as M
    if M.file_stamp(path) != stamp:
        raise ValueError('Portrait fitting original source stamp changed')
    if M.source_digest(path) != source['sha256']:
        raise ValueError('Portrait fitting original bytes do not match expected source')
    if M.file_stamp(path) != stamp:
        raise ValueError('Portrait fitting original changed during authentication')


def capture_original(path, *, expected_source, expected_stamp, byte_budget, cancelled=lambda: False):
    """Frozen-snapshot original fitting, independent of delivery output precision.

    In particular, an established RAW8 output decode does not become the fit
    source. This function uses the identical genuine RAW16/ICC path as preview
    capture. The supplied hash and stamp must match actual bytes, not each other
    alone. It reads no live engine, edits no snapshot and retains no source cache.
    """
    from . import local_mask_state as M
    from .decode import load_full
    from .full_source_working import working_rgb
    import numpy as np
    if type(byte_budget) is not int or byte_budget < 1:
        raise ValueError('Portrait fitting needs an explicit positive remaining byte budget')
    source = _binding(expected_source)
    if (type(expected_stamp) not in (tuple, list) or len(expected_stamp) != 5
            or any(type(item) is not int for item in expected_stamp)):
        raise ValueError('Portrait fitting needs its exact captured original file stamp')
    stamp = tuple(expected_stamp)
    _poll(cancelled)
    actual = M.file_stamp(path)
    if actual != stamp:
        raise ValueError('Portrait fitting original source stamp changed before capture')
    peak = _admit(source, byte_budget, actual[2])
    _verify_file(path, source, stamp)
    bits = _inspect_original(path, source, cancelled)
    if M.file_stamp(path) != stamp:
        raise ValueError('Portrait fitting original changed during source inspection')
    _poll(cancelled)
    decoded = load_full(path, max_px=source['width'] * source['height'], device='cpu', want_bits=bits)
    _poll(cancelled)
    if ((decoded.w, decoded.h) != (source['width'], source['height'])
            or (decoded.w, decoded.h) != (decoded.src_w, decoded.src_h)
            or decoded.draft_used or (decoded.raw or {}).get('used_preview')
            or (decoded.raw or {}).get('half_size')
            or bits == 16 and decoded.rgb.dtype != np.uint16
            or bits == 8 and decoded.rgb.dtype != np.uint8):
        raise ValueError('Portrait fitting refused reduced, substituted or lower-precision source pixels')
    pixels = working_rgb(decoded)
    content, digest = _freeze(pixels, source, cancelled)
    _poll(cancelled)
    _verify_file(path, source, stamp)
    _poll(cancelled)
    return FullSource(source['sha256'], source['width'], source['height'], digest,
                      bits, 'original', peak, content)


def capture(engine, *, expected_source, byte_budget, cancelled=lambda: False):
    """Capture actual full immutable source, with no mutation or proxy fallback.

    expected_source is a previously captured effective binding, not authority to
    supply its SHA. It is authenticated against the host and the actual source
    before and after decoding. Original before/after stamps and hashes, exact
    oriented dimensions and unchanged active ownership must all agree.
    """
    from . import creative_derived_source as SOURCE, local_mask_state as M
    from .creative_document_base import export_source, MAX_WORK_BYTES
    import numpy as np
    if type(byte_budget) is not int or byte_budget < 1:
        raise ValueError('Portrait fitting needs an explicit positive remaining byte budget')
    expected = _binding(expected_source)
    _poll(cancelled)
    row, token = _active(engine)
    base = SOURCE.record(engine)
    path = None if base is not None else row['path']
    stamp = None if path is None else M.file_stamp(path)
    # Admit even the alpha-inspection decoder only after charging exact pixels
    # and compressed snapshots. Source binding checks cannot allocate a raster.
    peak = _admit(expected, byte_budget, 0 if stamp is None else stamp[2])
    source = _binding(SOURCE.verify(expected, engine))
    _assert_active(engine, row, token)
    _poll(cancelled)
    if base is not None:
        pixels = export_source(base, cancelled=cancelled, max_bytes=min(byte_budget, MAX_WORK_BYTES))
        if type(pixels) is not np.ndarray or pixels.dtype != np.float32:
            raise ValueError('Creative portrait fitting requires exact encoded float32 export pixels')
        content, digest = _freeze(pixels, source, cancelled)
        result = FullSource(source['sha256'], source['width'], source['height'], digest,
                            32, 'creative', peak, content)
    else:
        result = capture_original(path, expected_source=source, expected_stamp=stamp,
                                  byte_budget=byte_budget, cancelled=cancelled)
    _poll(cancelled)
    if path is not None and (row.get('path') != path or M.file_stamp(path) != stamp):
        raise ValueError('Portrait fitting original changed during full decoding')
    SOURCE.verify(source, engine)
    _assert_active(engine, row, token)
    if path is not None and M.file_stamp(path) != stamp:
        raise ValueError('Portrait fitting original changed during final authentication')
    _poll(cancelled)
    return result
