#!/usr/bin/env python3
"""Install an externally authenticated, already prepared runtime; never acquire assets."""
from __future__ import annotations
import argparse
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys
import tempfile

# Pending explicit review: no manifest declaration can override these exclusions.
BLOCKED = {('tokenizers', '0.22.2'), ('safetensors', '0.8.0'),
           ('markdown-it-py', '4.2.0'), ('mdurl', '0.1.2')}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'duplicate JSON key: {key}')
        result[key] = value
    return result


def verify(bundle, trusted):
    require(digest(bundle / 'SHA256SUMS') == trusted, 'inventory trust mismatch')
    inventory = {}
    for row in (bundle / 'SHA256SUMS').read_text('ascii').splitlines():
        require(re.fullmatch(r'[0-9a-f]{64}  [A-Za-z0-9_./+\-]+', row), 'invalid checksum row')
        sha, name = row.split('  ', 1)
        require(not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/')), 'unsafe path')
        require(name not in inventory and name != 'SHA256SUMS', 'duplicate/self inventory')
        inventory[name] = sha
    actual = set()
    for path in bundle.rglob('*'):
        mode = path.lstat().st_mode
        require(not stat.S_ISLNK(mode), 'symlink forbidden')
        require(not mode & 0o6022, 'group/world writable or privileged bundle entry')
        if stat.S_ISDIR(mode):
            continue
        require(stat.S_ISREG(mode) and path.stat().st_nlink == 1, 'special file/hardlink forbidden')
        name = path.relative_to(bundle).as_posix()
        if name == 'SHA256SUMS':
            continue
        actual.add(name)
        require(inventory.get(name) == digest(path), f'integrity mismatch: {name}')
    require(actual == set(inventory), 'inventory mismatch')
    manifest = json.loads((bundle / 'BUNDLE.json').read_text(), object_pairs_hook=unique_object)
    require(manifest['schema'] == 'lrt-offline-runtime-v1', 'unsupported schema')
    require(manifest['variant'] == 'cpu', 'only explicitly prepared CPU bundles are supported')
    require(manifest['relocation_review']['status'] == 'approved', 'relocation review missing')
    target = manifest['target']
    host_os = platform.freedesktop_os_release()
    require(platform.system() == 'Linux' and platform.machine() == target['machine'], 'unsupported architecture/OS')
    require(host_os.get('ID') == target['os_id'] and host_os.get('VERSION_ID') == target['os_version'], 'unsupported distribution version')
    require(sys.implementation.name == 'cpython' and platform.python_version() == target['python_version'], 'interpreter version mismatch')
    libc_name, libc_version = platform.libc_ver()
    require((libc_name, libc_version) == (target['libc_name'], target['libc_version']), 'unsupported libc (exact target required)')
    # Evidence files are themselves covered by the trusted inventory, not a bare
    # approved=true switch. External reviewer authentication remains indispensable.
    def evidence(review):
        require(review['status'] == 'approved' and bool(review['reviewer'].strip()), 'review approval/identity missing')
        for key in ('evidence', 'decision'):
            name = review[key]
            require(name.startswith('reviews/') and name in inventory and (bundle / name).stat().st_size > 0, f'missing {key}')
    evidence(manifest['relocation_review'])
    evidence(manifest['dependency_closure_review'])
    covered = set()
    components = manifest['components']
    require(isinstance(components, list) and components, 'empty component review')
    identities = set()
    for component in components:
        name = re.sub(r'[-_.]+', '-', component['name']).lower()
        identity = (name, component['version'])
        require(identity not in identities, 'duplicate component')
        identities.add(identity)
        require(identity not in BLOCKED, f'pending license approval: {name} {identity[1]}')
        require(component['license_expression'].strip().lower() not in ('', 'unknown', 'unverified', 'none'), 'unknown license')
        evidence(component['review'])
        require(component['files'], 'component lacks file inventory')
        for filename in component['files']:
            require(filename.startswith('payload/') and filename in inventory and filename not in covered, 'invalid/duplicate component file')
            covered.add(filename)
        for filename in component['license_files']:
            require(filename in inventory and (bundle / filename).stat().st_size > 0, 'license text missing')
        require(component['license_files'], 'license text required')
    # Cross-check actual installed distribution metadata without importing packages.
    for path in (bundle / 'payload').rglob('*.dist-info/METADATA'):
        metadata = Parser().parsestr(path.read_text())
        name = re.sub(r'[-_.]+', '-', metadata.get('Name', '')).lower()
        identity = (name, metadata.get('Version', ''))
        require(identity not in BLOCKED, f'pending installed distribution: {identity}')
        require(identity in identities, f'unreviewed installed distribution: {identity}')
    require(covered == {p for p in inventory if p.startswith('payload/')}, 'runtime file coverage incomplete')
    require('payload/bin/python' in covered, 'interpreter missing')
    require(not (bundle / 'payload' / '.offline-delivery-receipt').exists(), 'reserved receipt path')
    return inventory


def writable_staging_directories(root):
    """Only our private copy: permit construction/removal even for mode-0555 input."""
    if not root.exists():
        return
    root.chmod(stat.S_IMODE(root.stat().st_mode) | 0o700)
    def walk_error(error):
        raise error
    for base, dirs, _files in os.walk(root, topdown=True, onerror=walk_error, followlinks=False):
        for name in dirs:
            directory = Path(base) / name
            require(not directory.is_symlink(), 'unexpected staging directory link')
            directory.chmod(stat.S_IMODE(directory.stat().st_mode) | 0o700)


def install(bundle, prefix, trusted):
    inventory = verify(bundle, trusted)
    require(prefix.is_absolute() and '..' not in prefix.parts, 'absolute non-traversing prefix required')
    # Never replace a working runtime. No archive extraction or in-place upgrades.
    for ancestor in reversed((prefix, *prefix.parents)):
        require(not ancestor.is_symlink(), 'destination symlink forbidden')
    require(not prefix.exists(), 'destination exists; use a new prefix')
    prefix.parent.mkdir(parents=True, exist_ok=True)
    parent_stat = prefix.parent.stat()
    require(parent_stat.st_uid == os.geteuid() and not parent_stat.st_mode & 0o022, 'destination parent must be owned and not group/world writable')
    lock = prefix.parent / ('.' + prefix.name + '.offline-install.lock')
    lock.mkdir(mode=0o700)  # A stale lock is an explicit recovery issue, never deleted speculatively.
    temp = None
    try:
        require(not prefix.exists(), 'destination appeared during admission')
        temp = Path(tempfile.mkdtemp(prefix='.offline-runtime-', dir=prefix.parent))
        payload = bundle / 'payload'
        directory_modes = {Path('.'): stat.S_IMODE(payload.stat().st_mode)}
        directory_modes.update({p.relative_to(payload): stat.S_IMODE(p.stat().st_mode)
                                for p in payload.rglob('*') if p.is_dir()})
        shutil.copytree(payload, temp / 'runtime', symlinks=True)
        writable_staging_directories(temp / 'runtime')
        for name, sha in inventory.items():
            if name.startswith('payload/'):
                copied = temp / 'runtime' / name.removeprefix('payload/')
                require(not copied.is_symlink() and digest(copied) == sha, 'copy integrity mismatch')
        # Keep review materials alongside the runtime for later release audit.
        (temp / 'receipt').mkdir()
        for entry in bundle.iterdir():
            if entry.name == 'payload':
                continue
            destination = temp / 'receipt' / entry.name
            if entry.is_dir():
                shutil.copytree(entry, destination, symlinks=True)
            else:
                shutil.copy2(entry, destination)
        require(not prefix.exists(), 'refusing overwrite')
        (temp / 'receipt').rename(temp / 'runtime' / '.offline-delivery-receipt')
        # Restore validated payload modes only after construction; root last.
        for relative in sorted(directory_modes, key=lambda p: len(p.parts), reverse=True):
            (temp / 'runtime' / relative).chmod(directory_modes[relative])
        (temp / 'runtime').rename(prefix)
    finally:
        # copytree can fail after preserving a read-only directory mode. Cleanup
        # repairs only private staged directories, never source/published runtime.
        # Cleanup errors must neither mask the primary failure nor skip unlocking.
        try:
            if temp is not None:
                writable_staging_directories(temp)
                shutil.rmtree(temp)
        except (OSError, ValueError) as cleanup_error:
            print(f'warning: private staging cleanup requires attention: {temp}: {cleanup_error}', file=sys.stderr)
        finally:
            try:
                lock.rmdir()
            except OSError as lock_error:
                print(f'warning: installer lock cleanup requires attention: {lock}: {lock_error}', file=sys.stderr)
    print(f'Offline runtime bytes installed: {prefix}; product/relocation acceptance NOT RUN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    try:
        install(args.bundle, args.prefix, args.manifest_sha256)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'offline runtime refused: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
