# SPDX-License-Identifier: Apache-2.0
"""Narrow data-only F32 safetensors reader; no pickle/import/remote-code loader."""
import hashlib
import json
import math
import struct
import sys

from .swin2sr_manifest import (
    CHECKPOINT_SHA256, CHECKPOINT_SIZE_BYTES, HEADER_BYTES,
    HEADER_PREFIX_SHA256, PARAMETER_PAYLOAD_BYTES, expected_shapes,
)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate safetensors JSON key')
        result[key] = value
    return result


def load_state(torch, checkpoint_bytes):
    """Validate entire immutable artifact before allocating any model tensor."""
    if type(checkpoint_bytes) is not bytes or len(checkpoint_bytes) != CHECKPOINT_SIZE_BYTES:
        raise ValueError('wrong Swin2SR artifact type/size')
    if hashlib.sha256(checkpoint_bytes).hexdigest() != CHECKPOINT_SHA256:
        raise ValueError('wrong Swin2SR artifact digest')
    if sys.byteorder != 'little':
        raise ValueError('Swin2SR reader requires little-endian CPU')
    header_size = struct.unpack('<Q', checkpoint_bytes[:8])[0]
    if header_size != HEADER_BYTES:
        raise ValueError('wrong Swin2SR header length')
    prefix = checkpoint_bytes[:8 + header_size]
    if hashlib.sha256(prefix).hexdigest() != HEADER_PREFIX_SHA256:
        raise ValueError('wrong Swin2SR header digest')
    header = json.loads(prefix[8:], object_pairs_hook=_unique_object)
    if header.pop('__metadata__', None) != {'format': 'pt'}:
        raise ValueError('wrong tensor metadata')
    expected = expected_shapes()
    if set(header) != set(expected):
        raise ValueError('wrong tensor key set')
    intervals = []
    for name, shape in expected.items():
        entry = header[name]
        if type(entry) is not dict or set(entry) != {'dtype', 'shape', 'data_offsets'}:
            raise ValueError('invalid tensor entry')
        if entry['dtype'] != 'F32' or entry['shape'] != list(shape):
            raise ValueError('wrong tensor dtype/shape: ' + name)
        offsets = entry['data_offsets']
        if (type(offsets) is not list or len(offsets) != 2
                or any(type(x) is not int for x in offsets)):
            raise ValueError('invalid tensor offsets')
        start, end = offsets
        if not (0 <= start < end <= PARAMETER_PAYLOAD_BYTES) or end-start != math.prod(shape)*4:
            raise ValueError('invalid tensor extent')
        intervals.append((start, end, name))
    cursor = 0
    for start, end, _ in sorted(intervals):
        if start != cursor:
            raise ValueError('overlap or gap in tensor data')
        cursor = end
    if cursor != PARAMETER_PAYLOAD_BYTES or 8+header_size+cursor != len(checkpoint_bytes):
        raise ValueError('trailing or missing tensor bytes')
    state = {}
    for start, end, name in intervals:
        # Mutable owned bytearray avoids a writable view of immutable bytes.
        value = torch.frombuffer(bytearray(checkpoint_bytes[8+header_size+start:8+header_size+end]),
                                 dtype=torch.float32).clone().reshape(expected[name])
        if not bool(torch.isfinite(value).all().item()):
            raise ValueError('nonfinite tensor: ' + name)
        state[name] = value
    return state
