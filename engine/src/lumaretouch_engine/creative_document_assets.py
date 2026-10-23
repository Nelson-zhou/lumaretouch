"""Immutable creative assets. No path-only assets, decoding, ICC guessing or model output.

The authorized decoder must convert original integer/float data using its ICC
profile to linear-sRGB D65 before this boundary. RGB16 is never routed through
8-bit Pillow. Bytes here are canonical little-endian float32, premultiplied RGBA.
"""
from __future__ import annotations
import hashlib
import json
import math
import struct
from copy import deepcopy

MAX_PIXELS = 100_000_000
MAX_ASSET_BYTES = 1_600_000_000
MAX_STORE_BYTES = 2_000_000_000
MAX_ORIGINAL_BYTES = 512_000_000
MAX_ICC_BYTES = 4_194_304
HDR_LIMIT = 65504.0


def dimension(value):
    if type(value) is not int or not 1 <= value <= MAX_PIXELS:
        raise ValueError('Invalid creative asset dimension')
    return value


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def _identity(record):
    header = {k: v for k, v in record.items() if k not in ('id', 'content', 'original', 'icc')}
    canonical = json.dumps(header, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    h = hashlib.sha256(b'lumaretouch-creative-asset-v1\0' + canonical)
    for key in ('content', 'original', 'icc'):
        data = record[key]
        h.update(struct.pack('<Q', len(data)))
        h.update(data)
    return 'sha256:' + h.hexdigest()


def validate_asset(record):
    keys = {'id','kind','width','height','encoding','alpha','source_hash','icc_hash','content','original','icc'}
    if type(record) is not dict or set(record) != keys:
        raise ValueError('Malformed creative asset')
    w, h = dimension(record['width']), dimension(record['height'])
    channels = 4 if record['kind'] == 'rgba' else 1 if record['kind'] == 'mask' else 0
    if not channels or w * h > MAX_PIXELS:
        raise ValueError('Creative asset exceeds pixel budget or has unknown kind')
    expected = w * h * channels * 4
    data, original, icc = record['content'], record['original'], record['icc']
    if any(type(x) is not bytes for x in (data, original, icc)):
        raise ValueError('Creative assets must contain immutable bytes')
    if len(data) != expected or expected > MAX_ASSET_BYTES or len(original) > MAX_ORIGINAL_BYTES or len(icc) > MAX_ICC_BYTES:
        raise ValueError('Creative asset byte budget/length mismatch')
    encoding = 'linear-srgb-d65' if channels == 4 else 'coverage-linear'
    alpha = 'premultiplied' if channels == 4 else 'coverage'
    if record['encoding'] != encoding or record['alpha'] != alpha:
        raise ValueError('Unsupported creative colour/alpha contract')
    if record['source_hash'] != digest(original) or record['icc_hash'] != digest(icc):
        raise ValueError('Creative source/profile digest mismatch')
    # Bounded vector validation avoids millions of Python scalar unpack calls;
    # all actual colour transfer/sampling/compositing remains native Rust.
    import numpy as np
    values = np.frombuffer(data,dtype='<f4').reshape(-1,channels)
    for offset in range(0,len(values),65536):
        chunk = values[offset:offset+65536]
        if not np.isfinite(chunk).all(): raise ValueError('Nonfinite creative pixel')
        if channels == 4:
            alpha_values = chunk[:,3]
            if not ((alpha_values>=0)&(alpha_values<=1)).all():
                raise ValueError('Invalid creative alpha')
            if not (np.abs(chunk[:,:3]) <= HDR_LIMIT*alpha_values[:,None]).all():
                raise ValueError('Creative premultiplied HDR bound exceeded')
        elif not ((chunk>=0)&(chunk<=1)).all():
            raise ValueError('Invalid creative mask coverage')
    if record['id'] != _identity(record):
        raise ValueError('Creative asset content digest mismatch')
    return record


def make_asset(kind, width, height, content, *, original=b'', icc=b''):
    record = {'kind':kind, 'width':width, 'height':height,
              'encoding':'linear-srgb-d65' if kind == 'rgba' else 'coverage-linear',
              'alpha':'premultiplied' if kind == 'rgba' else 'coverage',
              'source_hash':digest(original), 'icc_hash':digest(icc),
              'content':content, 'original':original, 'icc':icc}
    record['id'] = _identity(record)
    return validate_asset(record)


class AssetStore:
    """Private immutable byte records; snapshots refer to hashes, not live arrays.

    No implicit eviction: history may reference deleted layers. Host may collect
    assets only after scanning all documents, undo/redo and pending return jobs.
    """
    def __init__(self, max_bytes=MAX_STORE_BYTES):
        if type(max_bytes) is not int or not 0 < max_bytes <= MAX_STORE_BYTES:
            raise ValueError('Invalid creative asset budget')
        self._records = {}
        self._bytes = 0
        self.max_bytes = max_bytes

    def intern(self, record):
        identity = record.get('id') if type(record) is dict else None
        if identity in self._records and record == self._records[identity]:
            return identity
        record = validate_asset(record)
        identity = record['id']
        if identity in self._records:
            return identity
        size = sum(len(record[k]) for k in ('content','original','icc'))
        if self._bytes + size > self.max_bytes:
            raise ValueError('Creative asset store budget exceeded')
        self._records[identity] = deepcopy(record)
        self._bytes += size
        return identity

    def get(self, identity, kind=None):
        if type(identity) is not str or identity not in self._records:
            raise ValueError('Missing creative content-addressed asset')
        record = self._records[identity]
        if kind is not None and record['kind'] != kind:
            raise ValueError('Creative asset kind mismatch')
        return deepcopy(record)  # bytes remain immutable, no full pixel copy

    def records(self, identities):
        return {identity:self.get(identity) for identity in sorted(set(identities))}
