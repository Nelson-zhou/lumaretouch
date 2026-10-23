"""Bounded, data-only portable packages. No extractall, execution or model fetching.

Runtime validation is intentionally separate from project schema migrations: callers
must validate project.json with the normal project loader before adopting a restore.
The immutable manifest is an integrity inventory, not a publisher signature.
"""
from __future__ import annotations

import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
import unicodedata
import zipfile
from . import creative_document_storage as CS

SCHEMA = 'lrt.portable.v1'
CHUNK = 1024 * 1024
MAX_ENTRIES = 20000
MAX_FILE = 8 * 1024**3
MAX_TOTAL = 32 * 1024**3
MAX_PROJECT = 256_000_000
MAX_MANIFEST = 16_000_000
MAX_RATIO = 64
RESERVE_BYTES = 64_000_000
SHA = re.compile(r'^[0-9a-f]{64}$')


class PackageError(ValueError):
    pass


class PackageCancelled(PackageError):
    pass


def _check(cancel):
    if cancel and cancel():
        raise PackageCancelled('Portable package cancelled; no destination published')


def _report(progress, phase, done, total):
    if progress:
        progress({'phase': phase, 'completed_bytes': done, 'total_bytes': total})


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise PackageError('Duplicate JSON key')
        value[key] = item
    return value


def _decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(PackageError('Non-finite JSON')))
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise PackageError(f'Invalid package JSON: {exc}') from exc


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _destination(path):
    target = Path(os.path.abspath(os.fspath(path)))
    if not target.name or target.name in ('.', '..') or os.path.lexists(target):
        raise PackageError('Destination already exists; choose a new name')
    parent = target.parent
    if not parent.is_dir() or parent.resolve() != parent:
        raise PackageError('Destination parent must be an existing real directory, not a symlink')
    return target


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _reserve(path, next_bytes):
    """Admission is based on current free space, including existing staging."""
    if type(next_bytes) is not int or next_bytes < 0:
        raise PackageError('Invalid package disk-space admission')
    if shutil.disk_usage(path).free - next_bytes < RESERVE_BYTES:
        raise PackageError('Portable package disk reserve exhausted; no destination published')


def _publish_directory(source, destination):
    """Linux renameat2 is atomic and refuses even an existing empty directory."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        raise PackageError('Atomic no-clobber directory publication unavailable on this platform')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(destination))


def _read_source(path, limit=MAX_FILE):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        os.close(fd)
        raise PackageError('Dependency is not a bounded regular file')
    return os.fdopen(fd, 'rb'), info


def _same_file(left, right):
    return (left.st_dev, left.st_ino, left.st_size, left.st_mtime_ns, left.st_ctime_ns) == (right.st_dev, right.st_ino, right.st_size, right.st_mtime_ns, right.st_ctime_ns)


def _mandatory_inventory(manifest, project):
    """Creative bytes are mandatory project state, never optional dependencies."""
    try:
        required = {key[7:]: size for key, size in CS.blob_inventory(project).items()}
    except ValueError as exc:
        raise PackageError(f'Invalid creative blob references: {exc}') from exc
    rows = manifest.get('mandatory_blobs', [])
    if not isinstance(rows, list) or len(rows) > MAX_ENTRIES - 2:
        raise PackageError('Invalid mandatory creative blob inventory')
    recorded = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'sha256', 'size', 'archive_path'}:
            raise PackageError('Invalid mandatory creative blob descriptor')
        sha, size = row['sha256'], row['size']
        if (not isinstance(sha, str) or not SHA.fullmatch(sha) or sha in recorded
                or type(size) is not int or row['archive_path'] != f'blobs/{sha}'):
            raise PackageError('Invalid mandatory creative blob identity')
        recorded[sha] = size
    if recorded != required:
        raise PackageError('Mandatory creative inventory does not match project bindings')
    return required


def _hydrate(project, blobs):
    try:
        return CS.hydrate(project, blobs)
    except ValueError as exc:
        raise PackageError(f'Invalid creative blob content: {exc}') from exc


def _payload_inventory(manifest, project):
    descriptor, dependencies = manifest.get('project'), manifest.get('dependencies')
    if (not isinstance(descriptor, dict) or descriptor.get('path') != 'project.json'
            or type(descriptor.get('size')) is not int or not 0 <= descriptor['size'] <= MAX_PROJECT
            or not isinstance(descriptor.get('sha256'), str) or not SHA.fullmatch(descriptor['sha256'])
            or not isinstance(dependencies, list) or len(dependencies) > MAX_ENTRIES - 2):
        raise PackageError('Invalid project/dependency inventory')
    mandatory = _mandatory_inventory(manifest, project)
    expected = {'project.json': descriptor}
    for sha, size in mandatory.items():
        expected[f'blobs/{sha}'] = {'sha256':sha, 'size':size}
    ids = set()
    for record in dependencies:
        if not isinstance(record, dict) or not isinstance(record.get('id'), str) or not record['id'] or record['id'] in ids:
            raise PackageError('Invalid dependency identity')
        ids.add(record['id'])
        if record.get('status') not in ('bundled', 'excluded', 'missing') or not isinstance(record.get('type'), str):
            raise PackageError('Invalid dependency state/type')
        if not isinstance(record.get('bindings', []), list) or any(not isinstance(b, str) or not b.startswith('/') for b in record.get('bindings', [])):
            raise PackageError('Invalid dependency binding')
        if record['status'] == 'bundled':
            sha, size = record.get('sha256'), record.get('size')
            if (not isinstance(sha, str) or not SHA.fullmatch(sha)
                    or record.get('archive_path') != f'blobs/{sha}'
                    or type(size) is not int or not 0 <= size <= MAX_FILE
                    or not record.get('licence') or not record.get('provenance')
                    or record['type'] in ('model', 'model-weight', 'model_weights', 'model-weight-file')):
                raise PackageError('Invalid bundled dependency')
            previous = expected.setdefault(record['archive_path'], record)
            if previous.get('size') != size:
                raise PackageError('Conflicting deduplicated dependency')
    if len(expected) + 1 > MAX_ENTRIES or sum(row['size'] for row in expected.values()) > MAX_TOTAL:
        raise PackageError('Package inventory budget exceeded')
    return expected, mandatory


def create_archive(project, dependencies, destination, cancel=None, progress=None, operation_id=None):
    """dependencies: id/type/path/include/licence/provenance/bindings(JSON pointers).

    Optional sha256 and size pin a dry-preview. Excluded and missing records stay
    in the manifest. Model weights can never be included by this transport.
    """
    target = _destination(destination)
    _check(cancel)
    try:
        stored_project, creative_blobs = CS.pack(project)
    except ValueError as exc:
        raise PackageError(f'Invalid creative project storage: {exc}') from exc
    if len(creative_blobs) > MAX_ENTRIES - 2:
        raise PackageError('Too many mandatory creative archive payloads')
    payload = _json(stored_project)
    if len(payload) > MAX_PROJECT or not isinstance(dependencies, list) or len(dependencies) > MAX_ENTRIES - 2:
        raise PackageError('Project or dependency count exceeds package budget')
    manifest = {'schema': SCHEMA, 'project': {'path': 'project.json', 'sha256': _digest(payload), 'size': len(payload)}, 'dependencies': [], 'model_dependencies': {'status': 'not-bundled', 'policy': 'Install separately after licence review; no weights or downloads'}}
    from .project_package_dependencies import model_inventory
    if operation_id is not None: manifest['operation_id'] = operation_id
    manifest['model_dependencies'] = model_inventory(project)
    manifest['embedded_assets'] = [{'id':key,'kind':asset.get('kind'),'bytes':asset.get('bytes'),
        'include':True,
        'status':'mandatory-blob' if 'blob' in asset else 'mandatory-in-project',
        'licence':'retained user asset; redistribution rights not inferred'}
        for key,asset in stored_project.get('assets',{}).items()]
    manifest['mandatory_blobs'] = [{'sha256':key[7:], 'size':len(raw), 'archive_path':f'blobs/{key[7:]}'}
                                   for key, raw in sorted(creative_blobs.items())]
    _mandatory_inventory(manifest, stored_project)
    total = len(payload) + sum(len(raw) for raw in creative_blobs.values())
    processed = total
    ids = set()
    with tempfile.TemporaryDirectory(prefix='.lrt-package-', dir=target.parent) as temporary:
        work = Path(temporary)
        blobs = {}
        for source in dependencies:
            _check(cancel)
            record = copy.deepcopy(source)
            ident = record.get('id')
            if not isinstance(ident, str) or not ident or ident in ids:
                raise PackageError('Dependency IDs must be unique nonempty strings')
            ids.add(ident)
            if not isinstance(record.get('type'), str) or not isinstance(record.get('bindings', []), list):
                raise PackageError('Dependency type/bindings missing')
            record.pop('archive_path', None)
            record['status'] = 'excluded'
            if isinstance(record.get('sha256_expected'), str) and SHA.fullmatch(record['sha256_expected']):
                record['sha256'] = record['sha256_expected']
            if record.get('include'):
                if record['type'] in ('model', 'model-weight', 'model_weights', 'model-weight-file'):
                    raise PackageError('Model weights cannot be bundled')
                if not record.get('licence') or not record.get('provenance'):
                    raise PackageError('Included dependency needs explicit licence and provenance')
                path = record.get('path')
                try:
                    stream, before = _read_source(path)
                except FileNotFoundError:
                    record['status'] = 'missing'
                    manifest['dependencies'].append(record)
                    continue
                try:
                    _reserve(work, before.st_size)
                except BaseException:
                    stream.close()
                    raise
                staging = work / f'source-{len(ids)}'
                digest = hashlib.sha256()
                amount = 0
                with stream, staging.open('xb') as out:
                    while True:
                        _check(cancel)
                        block = stream.read(CHUNK)
                        if not block:
                            break
                        amount += len(block)
                        if amount > MAX_FILE or processed + amount > MAX_TOTAL:
                            raise PackageError('Package byte budget exceeded')
                        _reserve(work, len(block))
                        digest.update(block)
                        out.write(block)
                        _report(progress, 'copy', total + amount, min(MAX_TOTAL, total + before.st_size))
                    out.flush()
                    os.fsync(out.fileno())
                    if not _same_file(before, os.fstat(stream.fileno())):
                        raise PackageError('Dependency changed during copying; preview again')
                current_stream, current_info = _read_source(path)
                current_stream.close()
                if not _same_file(before, current_info):
                    raise PackageError('Dependency path changed during copying; preview again')
                processed += amount
                sha = digest.hexdigest()
                if source.get('sha256') not in (None, sha) or source.get('sha256_expected') not in (None, sha) or source.get('size') not in (None, amount):
                    raise PackageError('Dependency changed since preview')
                record.update(status='bundled', sha256=sha, size=amount, archive_path=f'blobs/{sha}')
                if sha not in blobs and 'sha256:' + sha not in creative_blobs:
                    blobs[sha] = staging
                    total += amount
            manifest['dependencies'].append(record)
        if len(blobs) + len(creative_blobs) + 2 > MAX_ENTRIES:
            raise PackageError('Too many mandatory and optional archive payloads')
        raw_manifest = _json(manifest)
        if len(raw_manifest) > MAX_MANIFEST:
            raise PackageError('Manifest byte budget exceeded')
        # ZIP_STORED writes all bytes again while source staging still exists.
        # Fixed short filenames, empty comments and ZIP64 metadata fit this bound.
        zip_metadata = 4096 + 1024 * (len(blobs) + len(creative_blobs) + 2)
        _reserve(work, total + len(raw_manifest) + zip_metadata)
        archive = work / 'package.tmp'
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            _reserve(work, len(raw_manifest) + zip_metadata)
            z.writestr('manifest.json', raw_manifest)
            _reserve(work, len(payload) + zip_metadata)
            z.writestr('project.json', payload)
            for key, raw in creative_blobs.items():
                with z.open(f'blobs/{key[7:]}', 'w', force_zip64=True) as out:
                    for offset in range(0, len(raw), CHUNK):
                        _check(cancel)
                        _reserve(work, min(CHUNK, len(raw) - offset) + zip_metadata)
                        out.write(memoryview(raw)[offset:offset + CHUNK])
            for sha, blob in blobs.items():
                with blob.open('rb') as source, z.open(f'blobs/{sha}', 'w', force_zip64=True) as out:
                    while True:
                        _check(cancel)
                        block = source.read(CHUNK)
                        if not block:
                            break
                        _reserve(work, len(block) + zip_metadata)
                        out.write(block)
            _reserve(work, zip_metadata)
        # Read every byte back before making a destination visible.
        del creative_blobs
        verified_sha = inspect_archive(archive, cancel=cancel, progress=progress)['manifest_sha256']
        with archive.open('rb') as stream:
            os.fsync(stream.fileno())
        _reserve(work, 0)
        _check(cancel)
        os.link(archive, target)  # exclusive, same filesystem; never overwrite
        _sync_dir(target.parent)
        return {'path': str(target), 'manifest': manifest, 'manifest_sha256': verified_sha, 'missing': [d for d in manifest['dependencies'] if d['status'] != 'bundled']}


def _members(z):
    entries = z.infolist()
    if len(entries) > MAX_ENTRIES:
        raise PackageError('Too many archive entries')
    seen, total, members = set(), 0, {}
    for entry in entries:
        name = entry.filename
        parts = PurePosixPath(name).parts
        key = unicodedata.normalize('NFC', name).casefold()
        mode = entry.external_attr >> 16
        if (not name or len(name) > 240 or '\\' in name or ':' in name or '\x00' in name
                or name.startswith('/') or any(p in ('', '.', '..') for p in name.split('/'))
                or key in seen or entry.is_dir() or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                or entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise PackageError(f'Unsafe, duplicate or unsupported archive member: {name!r}')
        if name not in ('manifest.json', 'project.json') and not (len(parts) == 2 and parts[0] == 'blobs' and SHA.fullmatch(parts[1])):
            raise PackageError('Unexpected archive entry')
        limit = MAX_MANIFEST if name == 'manifest.json' else MAX_PROJECT if name == 'project.json' else MAX_FILE
        total += entry.file_size
        if entry.file_size > limit or total > MAX_TOTAL or entry.file_size > max(1, entry.compress_size) * MAX_RATIO:
            raise PackageError('Archive expansion budget exceeded')
        seen.add(key)
        members[name] = entry
    if not {'manifest.json', 'project.json'} <= members.keys():
        raise PackageError('Package lacks project or manifest')
    return members


def _read_member(z, entry, cancel=None, progress=None, sink=None, keep=False):
    digest, amount, blocks = hashlib.sha256(), 0, []
    with z.open(entry, 'r') as stream:
        while True:
            _check(cancel)
            block = stream.read(CHUNK)
            if not block:
                break
            amount += len(block)
            if amount > entry.file_size:
                raise PackageError('Expanded size disagrees with directory')
            digest.update(block)
            if sink:
                sink.write(block)
            elif keep or entry.filename in ('manifest.json', 'project.json'):
                blocks.append(block)
            _report(progress, 'verify', amount, entry.file_size)
    if amount != entry.file_size:
        raise PackageError('Truncated archive member')
    return digest.hexdigest(), b''.join(blocks)


def _inspect(z, cancel=None, progress=None, dependency_validator=None):
    members = _members(z)
    manifest_sha, raw = _read_member(z, members['manifest.json'], cancel, progress)
    manifest = _decode(raw)
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA:
        raise PackageError('Unsupported package manifest')
    descriptor = manifest.get('project', {})
    dependencies = manifest.get('dependencies')
    if not isinstance(descriptor, dict) or descriptor.get('path') != 'project.json' or not isinstance(dependencies, list) or len(dependencies) > MAX_ENTRIES - 2:
        raise PackageError('Invalid project/dependency inventory')
    if type(descriptor.get('size')) is not int or members['project.json'].file_size != descriptor['size']:
        raise PackageError('Manifest project size mismatch')
    project_sha, project_raw = _read_member(z, members['project.json'], cancel, progress)
    if project_sha != descriptor.get('sha256'):
        raise PackageError('Full project SHA-256 mismatch')
    stored_project = _decode(project_raw)
    if not isinstance(stored_project, dict):
        raise PackageError('Project is not an object')
    expected, mandatory = _payload_inventory(manifest, stored_project)
    if set(members) != {'manifest.json', *expected}:
        raise PackageError('Unlisted or missing archive payload')
    creative_blobs = {}
    for name, descriptor in expected.items():
        if type(descriptor.get('size')) is not int or members[name].file_size != descriptor['size']:
            raise PackageError('Manifest size mismatch')
        if name == 'project.json':
            continue
        sha = name.split('/')[1]
        # Only bounded, inventoried creative chunks are retained in memory.
        # Optional originals can remain as large as MAX_FILE and are streamed.
        digest, raw = _read_member(z, members[name], cancel, progress, keep=sha in mandatory)
        if digest != descriptor.get('sha256'):
            raise PackageError('Full SHA-256 mismatch')
        if sha in mandatory:
            creative_blobs['sha256:' + sha] = raw
    project = _hydrate(stored_project, creative_blobs)
    if dependency_validator:
        dependency_validator(project, dependencies)
    return {'manifest': manifest, 'manifest_sha256': manifest_sha, 'project': project,
            'stored_project': stored_project, 'creative_blobs': creative_blobs}


def _preflight(stream):
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(max(0, size - 65557))
    tail = stream.read(65557)
    offset = tail.rfind(b'PK\x05\x06')
    if offset < 0 or len(tail) - offset < 22:
        raise PackageError('Missing ZIP end directory')
    end = struct.unpack_from('<4s4H2IH', tail, offset)
    if end[1] or end[2] or end[3] != end[4] or offset + 22 + end[7] != len(tail):
        raise PackageError('Split or malformed ZIP directory')
    count, directory_size = end[4], end[5]
    if count == 65535 or directory_size == 0xffffffff or end[6] == 0xffffffff:
        absolute_end = size - len(tail) + offset
        if absolute_end < 20:
            raise PackageError('Invalid ZIP64 locator')
        stream.seek(absolute_end - 20)
        locator = struct.unpack('<4sIQI', stream.read(20))
        if locator[0] != b'PK\x06\x07' or locator[1] or locator[3] != 1 or locator[2] > absolute_end - 76:
            raise PackageError('Invalid ZIP64 locator')
        stream.seek(locator[2])
        raw = stream.read(56)
        if len(raw) != 56:
            raise PackageError('Truncated ZIP64 directory')
        info = struct.unpack('<4sQ2H2I4Q', raw)
        if info[0] != b'PK\x06\x06' or info[4] or info[5] or info[6] != info[7]:
            raise PackageError('Invalid ZIP64 directory')
        count, directory_size = info[7], info[8]
    if count > MAX_ENTRIES or directory_size > 32_000_000:
        raise PackageError('ZIP central directory exceeds memory budget')
    stream.seek(0)


def inspect_archive(path, cancel=None, progress=None, dependency_validator=None):
    stream, before = _read_source(path, MAX_TOTAL)
    try:
        _preflight(stream)
    except BaseException:
        stream.close()
        raise
    with stream, zipfile.ZipFile(stream, 'r') as z:
        result = _inspect(z, cancel, progress, dependency_validator)
        if not _same_file(before, os.fstat(stream.fileno())):
            raise PackageError('Archive changed while reading')
        return result


def _bind(project, pointer, path):
    parts = [p.replace('~1', '/').replace('~0', '~') for p in pointer[1:].split('/')]
    value = project
    try:
        for part in parts[:-1]:
            value = value[int(part)] if isinstance(value, list) else value[part]
        key = int(parts[-1]) if isinstance(value, list) else parts[-1]
        if not isinstance(value[key], str):
            raise PackageError('Dependency binding does not address a path string')
        value[key] = path
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise PackageError('Invalid project dependency binding') from exc


def _relocated_project(original, manifest, target, dependency_validator=None):
    project = copy.deepcopy(original)
    if 'root' in project: project['root'] = str(target)
    bound = set()
    for record in manifest['dependencies']:
        identity = _digest(record['id'].encode())
        suffix = Path(record.get('path') or '').suffix.lower()
        if not re.fullmatch(r'\.[a-z0-9]{1,12}', suffix):
            suffix = '.bin'
        relative = ('sources/' if record['status'] == 'bundled' else 'missing/') + identity + suffix
        for binding in record.get('bindings', []):
            if binding in bound:
                raise PackageError('Multiple dependencies target one project binding')
            bound.add(binding)
            # Even absent a caller validator, arbitrary manifest writes are forbidden.
            if not dependency_validator and (record['type'] != 'original' or not re.fullmatch(r'/(?:docs/[0-9]+|source_assets/[^/]+)/(?:path|fingerprint/path)', binding)):
                raise PackageError('Unsupported operational dependency binding')
            _bind(project, binding, str(target / relative))
            match = re.fullmatch(r'/docs/([0-9]+)/path', binding)
            if match and isinstance(record.get('sha256'), str) and SHA.fullmatch(record['sha256']):
                project['docs'][int(match[1])].setdefault('source_relocation_aliases', {})[record['path']] = record['sha256']
            if record['type'] == 'original' and binding.endswith('/path') and '/fingerprint/' not in binding and record['status'] == 'bundled':
                parts = binding[1:].split('/')
                owner = project['docs'][int(parts[1])] if parts[0] == 'docs' else project['source_assets'][parts[1].replace('~1', '/').replace('~0', '~')]
                owner.setdefault('fingerprint', {}).update(path=str(target / relative), sha256=record['sha256'], hash_level='full', bytes=record['size'])
                if parts[0] == 'source_assets' and record['sha256'] not in owner.setdefault('fingerprint_aliases', []):
                    owner['fingerprint_aliases'].append(record['sha256'])
    return project


def restore_archive(path, destination, cancel=None, progress=None, dependency_validator=None, project_validator=None, operation_id=None):
    target = _destination(destination)
    stream, before = _read_source(path, MAX_TOTAL)
    try:
        _preflight(stream)
    except BaseException:
        stream.close()
        raise
    with stream, zipfile.ZipFile(stream, 'r') as z:
        result = _inspect(z, cancel, progress, dependency_validator)
        manifest = result['manifest']
        # Disk publication must retain external blob rows, not re-expand base64.
        del result['project']
        project = _relocated_project(result['stored_project'], manifest, target, dependency_validator)
        if project_validator:
            project_validator(_hydrate(project, result['creative_blobs']))
        restored_bytes = _json(project)
        if len(restored_bytes) > MAX_PROJECT:
            raise PackageError('Restored project exceeds byte budget')
        receipt = {'operation_id':operation_id, 'schema': SCHEMA, 'manifest_sha256': result['manifest_sha256'], 'project_sha256': _digest(restored_bytes), 'project_path': 'restored.lrproject.json'}
        receipt_bytes = _json(receipt)
        if len(receipt_bytes) > MAX_MANIFEST:
            raise PackageError('Restore receipt exceeds byte budget')
        # Original archive inventory and the reopened-project sidecar coexist.
        # Restored source paths are hardlinks, so never charge source bytes twice.
        entries = z.infolist()
        pending_bytes = (sum(entry.file_size for entry in entries)
                         + sum(len(raw) for raw in result['creative_blobs'].values())
                         + len(restored_bytes) + len(receipt_bytes))
        directory_overhead = 4096 * (len(entries) + len(result['creative_blobs'])
                                    + sum(row['status'] == 'bundled' for row in manifest['dependencies']) + 8)
        _check(cancel)
        _reserve(target.parent, pending_bytes + directory_overhead)
        with tempfile.TemporaryDirectory(prefix='.lrt-restore-', dir=target.parent) as temporary:
            root = Path(temporary) / 'payload'
            root.mkdir(mode=0o700)
            (root / 'blobs').mkdir(mode=0o700)
            for entry in entries:
                _check(cancel)
                _reserve(root, pending_bytes + directory_overhead)
                # Names have already passed strict whitelist; never use extract().
                with (root / entry.filename).open('xb') as out:
                    digest, _ = _read_member(z, entry, cancel, progress, out)
                    out.flush()
                    os.fsync(out.fileno())
                pending_bytes -= entry.file_size
                if entry.filename == 'manifest.json' and digest != result['manifest_sha256']:
                    raise PackageError('Manifest changed during restore')
                if entry.filename.startswith('blobs/') and digest != entry.filename.split('/')[1]:
                    raise PackageError('Payload changed during restore')
                if entry.filename == 'project.json' and digest != manifest['project']['sha256']:
                    raise PackageError('Project changed during restore')
            (root / 'sources').mkdir(mode=0o700)
            for record in manifest['dependencies']:
                if record['status'] != 'bundled':
                    continue
                suffix = Path(record.get('path') or '').suffix.lower()
                if not re.fullmatch(r'\.[a-z0-9]{1,12}', suffix):
                    suffix = '.bin'
                relative = 'sources/' + _digest(record['id'].encode()) + suffix
                os.link(root / record['archive_path'], root / relative)
            _sync_dir(root / 'sources')
            _check(cancel)
            # The basename-derived directory moves with this unpublished root.
            # Immutable raw bytes are durable before the small manifest commits.
            _reserve(root, pending_bytes + directory_overhead)
            CS.write_blobs(project, result['creative_blobs'], root / 'restored.lrproject.json')
            _check(cancel)
            _reserve(root, len(restored_bytes) + len(receipt_bytes) + directory_overhead)
            with (root / 'restored.lrproject.json').open('xb') as out:
                out.write(restored_bytes)
                out.flush()
                os.fsync(out.fileno())
            _reserve(root, len(receipt_bytes) + directory_overhead)
            with (root / '.lrt-package-receipt.json').open('xb') as out:
                out.write(receipt_bytes)
                out.flush()
                os.fsync(out.fileno())
            _sync_dir(root / 'blobs')
            _sync_dir(root)
            _reserve(root, 0)
            if not _same_file(before, os.fstat(stream.fileno())):
                raise PackageError('Archive changed during restore')
            _check(cancel)
            _publish_directory(root, target)
            _sync_dir(target.parent)
    return {'destination': str(target), 'project_path': str(target / 'restored.lrproject.json'), 'manifest': manifest, 'manifest_sha256': result['manifest_sha256'], 'missing': [d for d in manifest['dependencies'] if d['status'] != 'bundled']}


def _read_restored_blobs(project, project_path):
    """A freshly restored sidecar must have exactly the immutable inventory."""
    try:
        inventory = CS.blob_inventory(project)
        directory = CS.sidecar_path(project_path)
        if inventory or os.path.lexists(directory):
            if directory.resolve() != directory or not directory.is_dir():
                raise PackageError('Restored creative sidecar is not a real directory')
            before = directory.stat()
            if {entry.name for entry in directory.iterdir()} != {key[7:] for key in inventory}:
                raise PackageError('Restored creative sidecar has missing or unlisted blobs')
            blobs = CS.read_blobs(project, project_path)
            if not _same_file(before, directory.stat()):
                raise PackageError('Restored creative sidecar changed during readback')
            return blobs
        return {}
    except ValueError as exc:
        raise PackageError(f'Invalid restored creative sidecar: {exc}') from exc


def readback_restore(path, cancel=None, progress=None, dependency_validator=None, project_validator=None):
    """Verify a published directory after uncertain response/restart; never retry writes."""
    root = Path(os.path.abspath(path))
    if root.resolve() != root or not root.is_dir():
        raise PackageError('Restore readback needs a real directory')

    read_total = 0

    def read(name, limit, keep=False):
        nonlocal read_total
        file = root / name
        if file.parent.resolve() != file.parent:
            raise PackageError('Restore contains a symlink directory')
        source, before = _read_source(file, limit)
        digest, count, blocks = hashlib.sha256(), 0, []
        with source:
            while True:
                _check(cancel)
                block = source.read(CHUNK)
                if not block:
                    break
                count += len(block)
                read_total += len(block)
                if count > limit or read_total > 3 * MAX_TOTAL:
                    raise PackageError('Readback budget exceeded')
                digest.update(block)
                if keep:
                    blocks.append(block)
                _report(progress, 'readback', count, before.st_size)
            if not _same_file(before, os.fstat(source.fileno())):
                raise PackageError('Restore file changed during readback')
        return digest.hexdigest(), count, b''.join(blocks)

    _, _, raw = read('.lrt-package-receipt.json', MAX_MANIFEST, True)
    receipt = _decode(raw)
    digest, _, raw = read('manifest.json', MAX_MANIFEST, True)
    if (not isinstance(receipt, dict) or receipt.get('schema') != SCHEMA
            or receipt.get('project_path') != 'restored.lrproject.json'
            or digest != receipt.get('manifest_sha256')):
        raise PackageError('Restore receipt/manifest mismatch')
    manifest = _decode(raw)
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA or not isinstance(manifest.get('dependencies'), list) or len(manifest['dependencies']) > MAX_ENTRIES - 2:
        raise PackageError('Invalid restored manifest')
    project_sha, project_size, project_raw = read('project.json', MAX_PROJECT, True)
    original = _decode(project_raw)
    if not isinstance(original, dict):
        raise PackageError('Original project is not an object')
    expected, _ = _payload_inventory(manifest, original)
    if project_sha != expected['project.json']['sha256'] or project_size != expected['project.json']['size']:
        raise PackageError('Original project integrity mismatch')
    # Verify mandatory project chunks even if every optional source was excluded.
    for name, descriptor in expected.items():
        if name == 'project.json':
            continue
        digest, size, _ = read(name, descriptor['size'])
        if digest != descriptor['sha256'] or size != descriptor['size']:
            raise PackageError('Restored payload integrity mismatch')
    for record in manifest['dependencies']:
        if record.get('status') != 'bundled':
            continue
        suffix = Path(record.get('path') or '').suffix.lower()
        if not re.fullmatch(r'\.[a-z0-9]{1,12}', suffix):
            suffix = '.bin'
        source_name = 'sources/' + _digest(record['id'].encode()) + suffix
        # Source hardlinks may have been individually replaced after publication.
        digest, size, _ = read(source_name, MAX_FILE)
        if digest != record['sha256'] or size != record['size']:
            raise PackageError('Restored source integrity mismatch')
    digest, _, raw = read('restored.lrproject.json', MAX_PROJECT, True)
    if digest != receipt.get('project_sha256'):
        raise PackageError('Restored project changed after publication; do not retry restore')
    expected_project = _relocated_project(original, manifest, root, dependency_validator)
    if raw != _json(expected_project):
        raise PackageError('Restored project bindings or retained history differ from immutable inventory')
    _check(cancel)
    creative_blobs = _read_restored_blobs(expected_project, root / 'restored.lrproject.json')
    _check(cancel)
    if dependency_validator:
        dependency_validator(_hydrate(original, creative_blobs), manifest['dependencies'])
    if project_validator:
        project_validator(_hydrate(expected_project, creative_blobs))
    return {'operation_id':receipt.get('operation_id'), 'destination': str(root), 'project_path': str(root / 'restored.lrproject.json'),
            'manifest': manifest, 'manifest_sha256': receipt['manifest_sha256'],
            'missing': [d for d in manifest['dependencies'] if d['status'] != 'bundled']}
