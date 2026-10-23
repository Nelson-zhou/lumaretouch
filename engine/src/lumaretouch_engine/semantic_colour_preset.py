# SPDX-License-Identifier: GPL-3.0-or-later
"""Private bounded transport for an explicitly included, owned reference asset.

The image is the existing reference_color_assets lossless NPZ byte-for-byte.
An outer stored ZIP only packages intent and opaque chunks; it is not another
image codec. No ndarray, base64 image, or archive is a UI/native receipt.

This module is deliberately NOT registered in the existing text-preset UI or
scope. A future export owner must explicitly ask whether to include the full
reference photo, pass include_reference=True, and expose PreparedExport.metadata
only. Import authenticates pixels through the existing A.hydrate/A.load path.
"""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import os
import stat
import tempfile
from types import MappingProxyType
import zipfile

import numpy as np

from . import reference_color_assets as A
from . import semantic_colour_portable as P
from . import semantic_colour_state as S

SCHEMA = 'lrt.semantic-colour-preset.v1'
MAX_CHUNKS = 40
CHUNK_BYTES = 7_000_000
MAX_MANIFEST_BYTES = 64 * 1024
MAX_FILE_BYTES = A.MAX_BYTES + MAX_MANIFEST_BYTES + 64 * 1024
MANIFEST_NAME = 'manifest.json'


def _permission(include_reference):
    if include_reference is not True:
        raise ValueError('导出将包含完整样片照片；必须明确授权 include_reference=True，不能暗中附带照片')


def _integer(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError('AI 追色便携资源长度或分块预算无效')
    return value


def _immutable(part):
    # Readonly ndarray flags alone do not make an owning buffer immutable.
    # Reuse immutable bytes-backed arrays; otherwise snapshot each bounded part.
    base = part
    while isinstance(base, np.ndarray) and base.base is not None:
        base = base.base
    if isinstance(base, bytes) and not part.flags.writeable:
        return part
    return np.frombuffer(part.tobytes(), dtype=np.uint8)


def _chunks(chunks):
    if type(chunks) is not list or not 1 <= len(chunks) <= MAX_CHUNKS:
        raise ValueError('AI 追色便携样片分块数量无效')
    total = 0
    for part in chunks:
        if (type(part) is not np.ndarray or part.dtype != np.uint8 or part.ndim != 1
                or not part.flags.c_contiguous or not 0 < part.size <= CHUNK_BYTES):
            raise ValueError('AI 追色便携样片必须为有界的一维原始 uint8 字节块')
        total += part.size
        if total > A.MAX_BYTES:
            raise ValueError('AI 追色便携样片超过完整参考资源预算')
    # Never coerce lists, float arrays, or object arrays into image bytes.
    frozen = [_immutable(part) for part in chunks]
    digest = sha256()
    descriptors = []
    for part in frozen:
        digest.update(memoryview(part))
        descriptors.append({'bytes': int(part.size), 'sha256': sha256(memoryview(part)).hexdigest()})
    return frozen, {'included': True, 'asset_id': digest.hexdigest(),
                    'bytes': int(total), 'chunks': descriptors}


def _manifest(value):
    if type(value) is not dict or set(value) != {'schema', 'intent', 'reference_resource'} or value['schema'] != SCHEMA:
        raise ValueError('AI 追色便携预设清单字段或版本无效')
    intent = P.check(value['intent'])
    resource = value['reference_resource']
    if type(resource) is not dict or set(resource) != {'included', 'asset_id', 'bytes', 'chunks'} or resource['included'] is not True:
        raise ValueError('AI 追色便携预设必须显式声明包含完整样片资源')
    S.digest(resource['asset_id'])
    if resource['asset_id'] != intent['reference']['asset_id']:
        raise ValueError('AI 追色便携预设资源身份与样片意图不同')
    size = _integer(resource['bytes'], A.MAX_BYTES)
    descriptors = resource['chunks']
    if type(descriptors) is not list or not 1 <= len(descriptors) <= MAX_CHUNKS:
        raise ValueError('AI 追色便携清单的分块数量无效')
    total = 0
    for row in descriptors:
        if type(row) is not dict or set(row) != {'bytes', 'sha256'}:
            raise ValueError('AI 追色便携分块清单字段无效')
        total += _integer(row['bytes'], CHUNK_BYTES)
        S.digest(row['sha256'])
    if total != size:
        raise ValueError('AI 追色便携样片总长度与分块清单不同')
    return {'schema': SCHEMA, 'intent': intent, 'reference_resource': deepcopy(resource)}


def check(envelope):
    """Check exact intent, bytes and SHA identities without installing a cache.

    This is transport integrity only. Use hydrate before per-target fitting;
    that validates the authentic float32 image, provenance mask and NPZ headers.
    """
    if type(envelope) is not dict or set(envelope) != {'schema', 'intent', 'reference_resource', 'chunks'}:
        raise ValueError('AI 追色便携预设封装字段无效')
    manifest = _manifest({k: envelope[k] for k in ('schema', 'intent', 'reference_resource')})
    chunks, actual = _chunks(envelope['chunks'])
    if actual != manifest['reference_resource']:
        raise ValueError('AI 追色便携样片的长度、分块摘要或完整摘要不符')
    return {**manifest, 'chunks': chunks}


def build(recipe, *, include_reference):
    """Build a private envelope only after explicit full-reference permission."""
    _permission(include_reference)
    intent = P.extract(recipe)
    from .semantic_colour_canvas import reference_admission
    reference_admission(intent['reference'], include_bundle=True)
    # A.bundle authenticates the retained full-float owned image with A.load.
    chunks, resource = _chunks(A.bundle(intent['reference']))
    return check({'schema': SCHEMA, 'intent': intent,
                  'reference_resource': resource, 'chunks': chunks})


def hydrate(envelope):
    """Restore through the authentic reference validator; return intent only.

    No semantic model, target fit, or state installation is run here. Successful
    hydration does not authorize applying a preset to any target photograph.
    """
    checked = check(envelope)
    from .semantic_colour_batch_reference import hydrate as admitted_hydrate
    admitted_hydrate(checked['intent']['reference'], checked['chunks'])
    return checked['intent']


def _json(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=True, allow_nan=False).encode('utf-8')
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('AI 追色便携预设清单超过 64 KiB 预算')
    return raw


def _part_name(index):
    return f'reference/{index:02d}.bin'


def _member(archive, name, data):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o100600 << 16
    archive.writestr(info, data)


def _open_regular(path, maximum):
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    # Preserve the existing preset_store bounded-fd regular-file admission.
    # O_NOFOLLOW adds explicit symlink refusal on supported platforms.
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise ValueError('AI 追色便携预设必须为预算内的普通文件')
        return os.fdopen(fd, 'rb'), info.st_size
    except BaseException:
        os.close(fd)
        raise


def _file_identity(path):
    stream, size = _open_regular(path, MAX_FILE_BYTES)
    digest = sha256()
    count = 0
    with stream:
        while raw := stream.read(1024 * 1024):
            count += len(raw)
            if count > MAX_FILE_BYTES:
                raise ValueError('AI 追色便携预设读取时超过预算')
            digest.update(raw)
    if count != size:
        raise ValueError('AI 追色便携预设文件在读取时变化')
    return {'file_bytes': count, 'file_sha256': digest.hexdigest()}


@dataclass(frozen=True)
class PreparedExport:
    """Engine-owned staged file. Send ONLY metadata to the owned export UI."""
    _path: str
    _metadata: dict

    def __post_init__(self):
        object.__setattr__(self, '_metadata', MappingProxyType(deepcopy(self._metadata)))

    @property
    def metadata(self):
        return dict(self._metadata)

    def close(self):
        """Release the private staged file after export or user cancellation."""
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass


def prepare_export(recipe, *, include_reference):
    """Stage a private disk artifact; return small, exact inclusion metadata."""
    _permission(include_reference)
    envelope = build(recipe, include_reference=True)
    manifest = {k: envelope[k] for k in ('schema', 'intent', 'reference_resource')}
    fd, path = tempfile.mkstemp(prefix='semantic-colour-export-', suffix='.lrtcolour')
    try:
        with os.fdopen(fd, 'w+b') as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
                _member(archive, MANIFEST_NAME, _json(manifest))
                for index, part in enumerate(envelope['chunks']):
                    _member(archive, _part_name(index), memoryview(part))
            stream.flush()
            os.fsync(stream.fileno())
        metadata = {'schema': SCHEMA, 'reference_included': True,
                    'reference_bytes': manifest['reference_resource']['bytes'],
                    'reference_sha256': manifest['reference_resource']['asset_id'],
                    'quality_acceptance': 'UNRUN', **_file_identity(path)}
        return PreparedExport(path, metadata)
    except BaseException:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        raise


def _no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('AI 追色便携清单含有重复 JSON 字段')
        out[key] = value
    return out


def load_file(path):
    """Read bounded opaque chunks without extraction, inference, or hydration."""
    stream, admitted_size = _open_regular(path, MAX_FILE_BYTES)
    with stream, zipfile.ZipFile(stream, 'r') as archive:
        entries = archive.infolist()
        if not 2 <= len(entries) <= MAX_CHUNKS + 1 or archive.comment:
            raise ValueError('AI 追色便携预设归档条目预算无效')
        names = [row.filename for row in entries]
        if len(set(names)) != len(names) or MANIFEST_NAME not in names:
            raise ValueError('AI 追色便携预设清单缺失或归档条目重复')
        for entry in entries:
            limit = MAX_MANIFEST_BYTES if entry.filename == MANIFEST_NAME else CHUNK_BYTES
            if (entry.is_dir() or entry.compress_type != zipfile.ZIP_STORED
                    or entry.flag_bits & 1 or not 0 < entry.file_size <= limit
                    or entry.compress_size != entry.file_size):
                raise ValueError('AI 追色便携预设只接受有界、未加密的原样字节块')
        if sum(row.file_size for row in entries) > A.MAX_BYTES + MAX_MANIFEST_BYTES:
            raise ValueError('AI 追色便携归档总字节预算超限')
        raw = archive.read(MANIFEST_NAME)
        manifest = _manifest(json.loads(raw, object_pairs_hook=_no_duplicate_keys))
        descriptors = manifest['reference_resource']['chunks']
        expected = {MANIFEST_NAME} | {_part_name(i) for i in range(len(descriptors))}
        if set(names) != expected:
            raise ValueError('AI 追色便携预设含有未知、路径跳转或缺失的资源条目')
        chunks = []
        for index, row in enumerate(descriptors):
            name = _part_name(index)
            if archive.getinfo(name).file_size != row['bytes']:
                raise ValueError('AI 追色便携分块长度与清单不同')
            chunks.append(np.frombuffer(archive.read(name), dtype=np.uint8))
        if os.fstat(stream.fileno()).st_size != admitted_size:
            raise ValueError('AI 追色便携预设在读取时变化')
    return check({**manifest, 'chunks': chunks})


def write_prepared(prepared, path, *, overwrite=False):
    """Publish only the exact staged bytes, without implicit overwrite.

    The caller owns destination permission and overwrite confirmation. Storage
    uncertainty uses existing PresetStorageError semantics, not false success.
    Always close the PreparedExport after the caller resolves success/cancel.
    """
    from .preset_store import _storage_error, _sync_parent
    if type(prepared) is not PreparedExport or type(overwrite) is not bool:
        raise ValueError('AI 追色便携导出需要拥有的已准备文件及明确覆盖开关')
    expected = {k: prepared._metadata[k] for k in ('file_bytes', 'file_sha256')}
    destination = Path(path)
    if destination.is_symlink() or destination.absolute() == Path(prepared._path).absolute():
        raise ValueError('AI 追色便携导出不能写到符号链接或自己的临时文件')
    source, size = _open_regular(prepared._path, MAX_FILE_BYTES)
    temporary = None
    committing = committed = False
    try:
        with source:
            fd, temporary = tempfile.mkstemp(prefix='.semantic-colour-', dir=destination.parent)
            digest = sha256()
            total = 0
            with os.fdopen(fd, 'wb') as output:
                while raw := source.read(1024 * 1024):
                    total += len(raw)
                    if total > MAX_FILE_BYTES:
                        raise ValueError('AI 追色已准备导出文件在复制时超过预算')
                    digest.update(raw)
                    output.write(raw)
                actual = {'file_bytes': total, 'file_sha256': digest.hexdigest()}
                if size != total or actual != expected:
                    raise ValueError('AI 追色已准备导出文件内容变化；未发布')
                output.flush()
                os.fsync(output.fileno())
        committing = True
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
        committed = True
        _sync_parent(os.path.abspath(destination))
        return prepared.metadata
    except OSError as error:
        raise _storage_error(error, committing=committing, committed=committed) from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
