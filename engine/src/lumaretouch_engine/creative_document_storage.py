"""Lossless, bounded creative byte transport, separate from the JSON manifest.

Canonical float32/source/ICC bytes are chunked, never recompressed or quantized.
Only the final project-manifest replace commits a save. Hash-named immutable
blobs are fsynced first and retained across all generations: this module never
collects or evicts blobs, including after an interrupted save.
"""
from __future__ import annotations

import base64
import copy
from collections import OrderedDict
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import threading

from .creative_document_assets import MAX_STORE_BYTES

CHUNK_BYTES = 7_000_000
RESERVE_BYTES = 64_000_000
MARKER = '__creative_bytes__'
_ROW_KEYS = {'kind', 'shape', 'dtype', 'bytes', 'b64'}
_EXTERNAL_KEYS = {'kind', 'shape', 'dtype', 'bytes', 'blob'}


class _DecodedBytes:
    """Shared immutable bytes across separate recipe/history decode calls.

    This is only a bounded accelerator, never an authority for validity or an
    owner of user history. Eviction drops a cache reference, not saved state.
    """
    def __init__(self):
        self.values = OrderedDict()
        self.bytes = 0
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            raw = self.values.get(key)
            if raw is not None:
                self.values.move_to_end(key)
            return raw

    def put(self, key, raw):
        with self.lock:
            if key in self.values:
                self.values.move_to_end(key)
                return self.values[key]
            while self.values and (self.bytes + len(raw) > MAX_STORE_BYTES or len(self.values) >= 2048):
                _, old = self.values.popitem(last=False)
                self.bytes -= len(old)
            if len(raw) <= MAX_STORE_BYTES:
                self.values[key] = raw
                self.bytes += len(raw)
            return raw


_DECODED = _DecodedBytes()


def _cache_key(marker):
    return marker['sha256'], marker['bytes'], tuple(marker['chunks'])


def identity(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _identity(value):
    if (type(value) is not str or len(value) != 71 or not value.startswith('sha256:')
            or any(c not in '0123456789abcdef' for c in value[7:])):
        raise ValueError('Invalid creative blob identity')
    return value


def _marker(value, limit=MAX_STORE_BYTES):
    if (type(value) is not dict or set(value) != {MARKER, 'bytes', 'sha256', 'chunks'}
            or type(value[MARKER]) is not int or value[MARKER] != 1
            or type(value['bytes']) is not int or not 0 <= value['bytes'] <= limit
            or type(value['chunks']) is not list):
        raise ValueError('Invalid creative byte chunk marker')
    _identity(value['sha256'])
    if len(value['chunks']) != (value['bytes'] + CHUNK_BYTES - 1) // CHUNK_BYTES:
        raise ValueError('Creative chunk count/byte budget mismatch')
    for key in value['chunks']:
        _identity(key)
    return value


def _row(key, row, *, external=False):
    _identity(key)
    if (type(row) is not dict or set(row) != (_EXTERNAL_KEYS if external else _ROW_KEYS)
            or row['kind'] != 'bytes' or row['shape'] is not None or row['dtype'] is not None
            or type(row['bytes']) is not int or not 0 < row['bytes'] <= CHUNK_BYTES):
        raise ValueError('Invalid creative chunk asset row')
    if external:
        if row['blob'] != key:
            raise ValueError('Creative sidecar asset identity mismatch')
    elif (type(row['b64']) is not str
          or len(row['b64']) != 4 * ((row['bytes'] + 2) // 3)):
        raise ValueError('Creative chunk base64 length mismatch')
    return row['bytes']


def _raw(key, row):
    size = _row(key, row)
    raw = base64.b64decode(row['b64'], validate=True)
    if len(raw) != size or identity(raw) != key:
        raise ValueError('Creative chunk digest/length mismatch')
    return raw


def encode_bytes(raw, assets):
    if type(raw) is not bytes or len(raw) > MAX_STORE_BYTES:
        raise ValueError('Creative bytes exceed immutable storage budget')
    keys = []
    for start in range(0, len(raw), CHUNK_BYTES):
        block = raw[start:start + CHUNK_BYTES]
        key = identity(block)
        row = {'kind': 'bytes', 'shape': None, 'dtype': None,
               'bytes': len(block), 'b64': base64.b64encode(block).decode('ascii')}
        if key in assets and assets[key] != row:
            raise ValueError('Creative chunk conflicts with an existing canonical asset')
        assets.setdefault(key, row)
        keys.append(key)
    marker = {MARKER: 1, 'bytes': len(raw), 'sha256': identity(raw), 'chunks': keys}
    _DECODED.put(_cache_key(marker), raw)
    return marker


def decode_bytes(value, assets, *, limit=MAX_STORE_BYTES, cache=None):
    value = _marker(value, limit)
    if type(assets) is not dict:
        raise ValueError('Creative chunks require their canonical asset table')
    # Validate order and lengths even when the complete immutable bytes are cached.
    for index, key in enumerate(value['chunks']):
        size = _row(key, assets.get(key))
        expected = min(CHUNK_BYTES, value['bytes'] - index * CHUNK_BYTES)
        if size != expected:
            raise ValueError('Creative chunk order/length mismatch')
    cache_key = _cache_key(value)
    raw = cache.get(cache_key) if cache is not None else None
    signature = tuple(assets[key]['b64'] for key in value['chunks'])
    validated_key = ('validated-creative-chunks', cache_key)
    if raw is not None and cache.get(validated_key) == signature:
        # Scoped validation/decode cache: exact immutable encoded strings and
        # strict row metadata are unchanged, so history need not rehash pixels.
        return raw
    if raw is None:
        raw = _DECODED.get(cache_key)
    if raw is not None:
        # Asset tables are mutable dictionaries. Never let a global cached hash
        # hide a corrupt/replaced chunk in a different project or history frame.
        for key in value['chunks']:
            _raw(key, assets[key])
    else:
        raw = b''.join(_raw(key, assets[key]) for key in value['chunks'])
    if len(raw) != value['bytes'] or identity(raw) != value['sha256']:
        raise ValueError('Creative complete byte digest mismatch')
    raw = _DECODED.put(cache_key, raw)
    if cache is not None:
        cache[cache_key] = raw
        cache[validated_key] = signature
    return raw


def _references(project):
    keys, stack, nodes = set(), [(project, 0)], 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > 128 or nodes > 2_000_000:
            raise ValueError('Creative storage nesting/node budget exceeded')
        if type(value) is dict:
            if MARKER in value:
                keys.update(_marker(value)['chunks'])
            else:
                stack.extend((child, depth + 1) for key, child in value.items()
                             if key != 'assets' and isinstance(child, (dict, list, tuple)))
        elif isinstance(value, (list, tuple)):
            stack.extend((child, depth + 1) for child in value if isinstance(child, (dict, list, tuple)))
    return keys


def blob_inventory(project):
    if type(project) is not dict:
        raise ValueError('Invalid project manifest object')
    bank = project.get('assets')
    if type(bank) is not dict:
        raise ValueError('Missing canonical project asset table')
    referenced = _references(project)
    inventory = {}
    for key, row in bank.items():
        if type(row) is dict and 'blob' in row:
            if key not in referenced:
                raise ValueError('Unowned external creative blob')
            inventory[key] = _row(key, row, external=True)
    if sum(inventory.values()) > MAX_STORE_BYTES:
        raise ValueError('Creative sidecar byte budget exceeded')
    return inventory


def pack(project):
    """Own the manifest, retaining every active and inactive history chunk."""
    out = copy.deepcopy(project)
    bank = out.get('assets')
    if type(bank) is not dict:
        raise ValueError('Missing canonical project asset table')
    if blob_inventory(out):
        raise ValueError('External creative project must be hydrated before capture')
    blobs, total = {}, 0
    for key in sorted(_references(out)):
        raw = _raw(key, bank.get(key))
        total += len(raw)
        if total > MAX_STORE_BYTES:
            raise ValueError('Creative transport byte budget exceeded')
        blobs[key] = raw
        bank[key] = {'kind': 'bytes', 'shape': None, 'dtype': None,
                     'bytes': len(raw), 'blob': key}
    return out, blobs


def hydrate(project, blobs):
    inventory = blob_inventory(project)
    if type(blobs) is not dict or set(blobs) != set(inventory):
        raise ValueError('Creative blob inventory missing or contains unlisted bytes')
    out = copy.deepcopy(project)
    for key, size in inventory.items():
        raw = blobs[key]
        if type(raw) is not bytes or len(raw) != size or identity(raw) != key:
            raise ValueError('Creative blob hash/length mismatch')
        out['assets'][key] = {'kind': 'bytes', 'shape': None, 'dtype': None,
                              'bytes': size, 'b64': base64.b64encode(raw).decode('ascii')}
    return out


@dataclass(frozen=True)
class FrozenProject:
    manifest: bytes
    blobs: tuple


def freeze(project, manifest_limit):
    manifest, blobs = pack(project)
    chunks, size = [], 0
    for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False,
                                  separators=(',', ':')).iterencode(manifest):
        raw = chunk.encode('utf-8')
        size += len(raw)
        if size > manifest_limit:
            raise ValueError('Project manifest snapshot byte budget exceeded')
        chunks.append(raw)
    return FrozenProject(b''.join(chunks), tuple(blobs.items()))


def thaw(frozen):
    if type(frozen) is bytes:  # Existing small project/relink callers.
        return json.loads(frozen)
    if type(frozen) is not FrozenProject:
        raise ValueError('Invalid immutable project snapshot')
    return hydrate(json.loads(frozen.manifest), dict(frozen.blobs))


def sidecar_path(project_path):
    path = Path(os.path.abspath(os.fspath(project_path)))
    token = hashlib.sha256(os.fsencode(path.name)).hexdigest()[:32]
    return path.parent / ('.lrt-creative-' + token)


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _directory(path):
    if not path.is_dir() or path.resolve() != path:
        raise ValueError('Creative storage requires a real directory without symlinks')


def _read(path, key, size):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size != size:
            raise ValueError('Creative blob is not a bounded regular file')
        raw = source.read(size + 1)
        after = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Creative blob changed while reading')
    if len(raw) != size or identity(raw) != key:
        raise ValueError('Creative sidecar blob hash/length mismatch')
    return raw


def read_blobs(project, project_path):
    inventory = blob_inventory(project)
    if not inventory:
        return {}
    root = sidecar_path(project_path)
    _directory(root)
    return {key: _read(root / key[7:], key, size) for key, size in inventory.items()}


def write_blobs(project, blobs, project_path, *, reserve_bytes=RESERVE_BYTES):
    """Serialize writers sharing a sidecar, including capacity admission."""
    inventory = blob_inventory(project)
    if not inventory:
        if type(blobs) is not dict or blobs:
            raise ValueError('Unexpected creative blobs without inventory')
        return {'blob_bytes': 0, 'blob_count': 0}
    root = sidecar_path(project_path)
    _directory(root.parent)
    lock_path = root.with_name(root.name + '.lock')
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, 'a+b') as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError('Creative storage lock is not a regular file')
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            return _write_blobs(project, blobs, project_path, reserve_bytes=reserve_bytes)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _write_blobs(project, blobs, project_path, *, reserve_bytes):
    inventory = blob_inventory(project)
    if type(blobs) is not dict or set(blobs) != set(inventory):
        raise ValueError('Creative sidecar inventory mismatch')
    if not inventory:
        return {'blob_bytes': 0, 'blob_count': 0}
    if type(reserve_bytes) is not int or reserve_bytes < 0:
        raise ValueError('Invalid creative storage disk reserve')
    root = sidecar_path(project_path)
    _directory(root.parent)
    root.mkdir(exist_ok=True, mode=0o700)
    _directory(root)
    # Retained old generations count against the same explicit store budget.
    # Never remove history or orphan blobs to make a new save fit.
    used, present = 0, set()
    for path in root.iterdir():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or len(path.name) != 64 or any(c not in '0123456789abcdef' for c in path.name):
            raise ValueError('Unexpected file in immutable creative sidecar')
        if info.st_size > CHUNK_BYTES:
            raise ValueError('Creative sidecar entry exceeds chunk budget')
        used += info.st_size
        present.add('sha256:' + path.name)
    needed = sum(size for key, size in inventory.items() if key not in present)
    if used + needed > MAX_STORE_BYTES or shutil.disk_usage(root).free - needed < reserve_bytes:
        raise ValueError('Creative sidecar budget/reserve exhausted; retained history was not deleted')
    for key, size in inventory.items():
        raw = blobs[key]
        if type(raw) is not bytes or len(raw) != size or identity(raw) != key:
            raise ValueError('Creative blob hash/length mismatch before write')
        target = root / key[7:]
        if key in present:
            _read(target, key, size)
            continue
        # Stage outside the store so interrupted staging never resembles a blob.
        fd, temporary = tempfile.mkstemp(prefix='.lrt-creative-stage-', dir=root.parent)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError:
                _read(target, key, size)
            _read(target, key, size)
        finally:
            os.unlink(temporary)
    _sync(root)
    _sync(root.parent)
    return {'blob_bytes': sum(inventory.values()), 'blob_count': len(inventory)}
