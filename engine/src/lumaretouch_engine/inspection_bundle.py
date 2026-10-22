"""Private, bounded snapshot handoff to an independently limited CPU process.

Only fixed record tags and numeric array bytes cross this boundary. Never pickle.
The owner supplies a new private directory and keeps inputs alive until spooling
finishes or is cancelled. Byte-sized ticks bound copies, not disk latency.
"""
from dataclasses import fields
import json
import math
import os
import stat
import numpy as np

MAX_MANIFEST = 2 * 1024 * 1024
MAX_NODES = 65536  # Bounded vector mask paths: at most 8192 retained points.
MAX_DEPTH = 128
MAX_TEXT = 1024 * 1024


def _records():
    from .vram import RepairOp, LightOp
    from .face import FacePrecompute
    from .ops.lut import CubeLut
    return {v.__name__: v for v in (RepairOp, LightOp, FacePrecompute, CubeLut)}


def _integer(v, low, high):
    if type(v) is not int or not low <= v <= high:
        raise ValueError('Invalid bounded bundle integer')
    return v


def _dtype(code):
    allowed = {'|u1', '|i1'}
    for endian in '<>':
        allowed.update(endian + kind + str(size) for kind in 'ui' for size in (2, 4, 8))
        allowed.update(endian + 'f' + str(size) for size in (2, 4, 8, 16))
    if type(code) is not str or code not in allowed:
        raise ValueError('Bundle dtype is not an explicit numeric type')
    try:
        return np.dtype(code)
    except TypeError as exc:
        raise ValueError('Bundle dtype unsupported on this platform') from exc


class BundleWriter:
    """Write fixed files with exclusive creation. Caller owns directory cleanup."""
    def __init__(self, directory, owned):
        self._file = None
        self._arrays = []
        self._index = self._offset = self.written_bytes = 0
        self._manifest_offset = 0
        self._writing_manifest = False
        self.done = self.cancelled = False
        self._directory = directory
        records = _records()
        count = 0
        text_bytes = 0
        descriptors = []
        total = 0

        def encode(v, depth=0):
            nonlocal count, total, text_bytes
            count += 1
            if count > MAX_NODES or depth > MAX_DEPTH:
                raise ValueError('Bundle structure exceeds budget')
            typ = type(v)
            if v is None or typ is bool:
                return v
            if typ is int:
                return _integer(v, -(2**64), 2**64 - 1)
            if typ is float:
                if not math.isfinite(v):
                    raise ValueError('Nonfinite bundle scalar')
                return v
            if typ is str:
                text_bytes += len(v.encode('utf-8'))
                if text_bytes > MAX_TEXT:
                    raise ValueError('Bundle text exceeds budget')
                return v
            if typ is np.ndarray:
                if not v.flags.c_contiguous or v.flags.writeable or v.dtype.metadata is not None:
                    raise ValueError('Bundle needs privately owned readonly contiguous arrays')
                _dtype(v.dtype.str)
                if v.ndim > 32:
                    raise ValueError('Too many array dimensions')
                i = len(self._arrays)
                descriptors.append(dict(dtype=v.dtype.str, shape=list(v.shape), offset=total, nbytes=int(v.nbytes)))
                total += int(v.nbytes)
                self._arrays.append(v)
                return ['array', i]
            if typ is dict:
                if any(type(k) is not str for k in v):
                    raise ValueError('Bundle dict keys must be strings')
                return ['dict', [[encode(k, depth+1), encode(x, depth+1)] for k, x in v.items()]]
            if typ in (list, tuple):
                return ['list' if typ is list else 'tuple', [encode(x, depth+1) for x in v]]
            if typ in records.values():
                names = [f.name for f in fields(v)]
                if set(vars(v)) != set(names):
                    raise ValueError('Unknown record fields')
                return ['record', typ.__name__, [[encode(name, depth+1), encode(getattr(v, name), depth+1)] for name in names]]
            raise ValueError('Unsupported bundle value')

        tree = encode(owned.value)
        _integer(total, 0, 512 * 1024 * 1024)
        if total != owned.asset_bytes or len(self._arrays) != owned.array_count:
            raise ValueError('Owned snapshot accounting changed')
        self.asset_bytes = total
        self._manifest = json.dumps(dict(version=1, asset_bytes=total, arrays=descriptors, tree=tree),
                                   ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(self._manifest) > MAX_MANIFEST:
            raise ValueError('Bundle manifest exceeds budget')
        self._file = open(os.path.join(directory, 'arrays.bin'), 'xb', buffering=0)

    def advance(self, max_bytes):
        _integer(max_bytes, 1, 2**31)
        if self.cancelled:
            raise ValueError('Bundle was cancelled')
        if self.done:
            return True
        allowance = max_bytes
        try:
            while allowance and self._index < len(self._arrays):
                a = self._arrays[self._index]
                remaining = int(a.nbytes) - self._offset
                if not remaining:
                    self._index += 1
                    self._offset = 0
                    continue
                size = min(remaining, allowance)
                view = memoryview(a.reshape(-1)).cast('B')[self._offset:self._offset+size]
                written = self._file.write(view)
                if not written:
                    raise OSError('Snapshot spool made no progress')
                self._offset += written
                self.written_bytes += written
                allowance -= written
            if self._index == len(self._arrays) and not self._writing_manifest:
                self._file.close()
                self._file = open(os.path.join(self._directory, 'manifest.part'), 'xb', buffering=0)
                self._writing_manifest = True
            if self._writing_manifest and allowance:
                view = memoryview(self._manifest)[self._manifest_offset:self._manifest_offset+allowance]
                n = self._file.write(view)
                if not n:
                    raise OSError('Manifest spool made no progress')
                self._manifest_offset += n
            if self._writing_manifest and self._manifest_offset == len(self._manifest):
                self._file.close()
                self._file = None
                # Only a complete manifest is the commit marker.
                os.rename(os.path.join(self._directory, 'manifest.part'),
                          os.path.join(self._directory, 'manifest.json'))
                self._arrays.clear()
                self._manifest = b''
                self.done = True
            return self.done
        except BaseException:
            self.cancel()
            raise

    def cancel(self):
        if self._file is not None:
            self._file.close()
            self._file = None
        self._arrays.clear()
        self._manifest = b''
        self.cancelled = True


def _open_regular(directory, name, maximum):
    fd = os.open(os.path.join(directory, name), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError('Bundle file type/size exceeds budget')
        return os.fdopen(fd, 'rb', buffering=0), info.st_size
    except BaseException:
        os.close(fd)
        raise


def read_bundle(directory, *, max_asset_bytes):
    """Validate all metadata and offsets before allocating any array payload."""
    _integer(max_asset_bytes, 0, 512 * 1024 * 1024)
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('Duplicate manifest key')
            out[k] = v
        return out
    def integer(text):
        if len(text) > 21:
            raise ValueError('Oversized manifest integer')
        return _integer(int(text), -(2**64), 2**64-1)
    def bad_constant(_):
        raise ValueError('Nonfinite JSON constant')
    source, size = _open_regular(directory, 'manifest.json', MAX_MANIFEST)
    with source:
        data = source.read(MAX_MANIFEST + 1)
    if len(data) != size:
        raise ValueError('Manifest size changed while reading')
    try:
        manifest = json.loads(data, object_pairs_hook=pairs, parse_int=integer, parse_constant=bad_constant)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('Invalid manifest encoding/nesting') from exc
    if type(manifest) is not dict or set(manifest) != {'version', 'asset_bytes', 'arrays', 'tree'} or type(manifest['version']) is not int or manifest['version'] != 1:
        raise ValueError('Unknown bundle manifest')
    total = _integer(manifest['asset_bytes'], 0, max_asset_bytes)
    descriptors = manifest['arrays']
    if type(descriptors) is not list or len(descriptors) > MAX_NODES:
        raise ValueError('Invalid bundle array table')
    validated = []
    cursor = 0
    for d in descriptors:
        if type(d) is not dict or set(d) != {'dtype', 'shape', 'offset', 'nbytes'}:
            raise ValueError('Invalid array descriptor')
        dtype = _dtype(d['dtype'])
        shape = d['shape']
        if type(shape) is not list or len(shape) > 32:
            raise ValueError('Invalid array shape')
        product = 1
        for dim in shape:
            product *= _integer(dim, 0, 2**31-1)
            if product > max_asset_bytes:
                raise ValueError('Array shape exceeds budget')
        nbytes = product * dtype.itemsize
        if _integer(d['offset'], 0, total) != cursor or _integer(d['nbytes'], 0, total) != nbytes:
            raise ValueError('Noncanonical array offsets/lengths')
        cursor += nbytes
        if cursor > total:
            raise ValueError('Array table exceeds payload')
        validated.append((dtype, tuple(shape), nbytes))
    if cursor != total:
        raise ValueError('Array accounting mismatch')
    records = _records()
    count = text_bytes = 0
    references = []

    def decode(v, arrays=None, depth=0):
        nonlocal count, text_bytes
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError('Bundle tree exceeds budget')
        typ = type(v)
        if v is None or typ is bool:
            return v
        if typ is int:
            return _integer(v, -(2**64), 2**64-1)
        if typ is float:
            if not math.isfinite(v):
                raise ValueError('Nonfinite bundle scalar')
            return v
        if typ is str:
            text_bytes += len(v.encode('utf-8'))
            if text_bytes > MAX_TEXT:
                raise ValueError('Bundle text exceeds budget')
            return v
        if typ is not list or not v or type(v[0]) is not str:
            raise ValueError('Invalid bundle node')
        tag = v[0]
        if tag == 'array' and len(v) == 2:
            i = _integer(v[1], 0, len(validated)-1)
            references.append(i)
            return None if arrays is None else arrays[i]
        if tag in ('list', 'tuple') and len(v) == 2 and type(v[1]) is list:
            out = [decode(x, arrays, depth+1) for x in v[1]]
            return out if tag == 'list' else tuple(out)
        if tag == 'dict' and len(v) == 2:
            entries = v[1]; record = None
        elif tag == 'record' and len(v) == 3 and type(v[1]) is str and v[1] in records:
            entries = v[2]; record = records[v[1]]
        else:
            raise ValueError('Unknown bundle node tag')
        if type(entries) is not list:
            raise ValueError('Invalid bundle entries')
        out = {}
        for entry in entries:
            if type(entry) is not list or len(entry) != 2 or type(entry[0]) is not str or entry[0] in out:
                raise ValueError('Invalid or duplicate bundle field')
            key = decode(entry[0], arrays, depth+1)
            out[key] = decode(entry[1], arrays, depth+1)
        if record:
            if set(out) != {f.name for f in fields(record)}:
                raise ValueError('Unknown or missing record fields')
            return out if arrays is None else record(**out)
        return out

    if type(manifest['tree']) is not list or manifest['tree'][:1] != ['dict']:
        raise ValueError('Bundle root must be dict')
    decode(manifest['tree'])
    if references != list(range(len(validated))):
        raise ValueError('Arrays must each appear exactly once in canonical order')
    source, size = _open_regular(directory, 'arrays.bin', total)
    arrays = []
    with source:
        if size != total:
            raise ValueError('Array payload length mismatch')
        for dtype, shape, nbytes in validated:
            a = np.empty(shape, dtype=dtype)
            if nbytes:
                view = memoryview(a.reshape(-1)).cast('B')
                offset = 0
                while offset < nbytes:
                    read = source.readinto(view[offset:offset+min(1024*1024, nbytes-offset)])
                    if not read:
                        raise ValueError('Truncated array payload')
                    offset += read
            a.setflags(write=False)
            arrays.append(a)
        if source.read(1):
            raise ValueError('Unexpected array trailing bytes')
    count = text_bytes = 0
    references.clear()
    return decode(manifest['tree'], arrays)
