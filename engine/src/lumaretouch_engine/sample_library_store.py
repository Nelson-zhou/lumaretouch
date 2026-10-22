# SPDX-License-Identifier: GPL-3.0-or-later
"""Linux local catalogue: nonblocking cross-process lock, CAS, atomic durable writes.

Remove/restore only change the catalogue. There is deliberately no unlink API for
originals, thumbnails or reference bundles. Recovery and global resource reclaim
have different ownership; a catalogue cannot prove a project no longer uses an asset.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import fcntl
import errno
import json
import os
import stat
import shutil
import tempfile
from . import sample_library_state as S


def root_path():
    override = os.environ.get('LRT_SAMPLE_LIBRARY_DIR')
    if override: return Path(override).expanduser().absolute()
    base = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    return base / 'LumaRetouch' / 'sample-library'


def hash_file(path):
    digest = sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= S.MAX_OBJECT_BYTES:
            S.fail('样片资源不是有界非空普通文件', 'asset_corrupt')
        total = 0
        while block := stream.read(1024 * 1024):
            total += len(block)
            if total > info.st_size: S.fail('读取时样片资源大小变化', 'asset_corrupt')
            digest.update(block)
        after = os.fstat(stream.fileno())
        if total != info.st_size or (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            S.fail('读取时样片资源变化', 'asset_corrupt')
    return digest.hexdigest()


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: S.fail('样片目录重复字段', 'catalog_corrupt')
        result[key] = value
    return result


class Store:
    def __init__(self, root=None):
        configured = os.environ.get('LRT_SAMPLE_LIBRARY_MAX_BYTES', str(S.MAX_STORAGE_BYTES))
        if not configured.isascii() or not configured.isdigit(): S.fail('LRT_SAMPLE_LIBRARY_MAX_BYTES 必须为正整数字节数', 'configuration')
        self.budget_bytes = S.integer(int(configured), 1, 2**53 - 1)
        self.root = Path(root) if root is not None else root_path()
        if self.root.is_symlink(): S.fail('样片根目录不能是符号链接')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = self.root.resolve()
        for sub in ('originals', 'thumbnails', 'staging'):
            path = self.root / sub
            if path.is_symlink(): S.fail('样片资源目录不能是符号链接')
            path.mkdir(exist_ok=True, mode=0o700)
        self.catalog = self.root / 'catalog-v1.json'
        self._cached_stamp = None
        self._cached_catalog = None

    @staticmethod
    def _stamp(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def _read(self):
        if not self.catalog.exists():
            if self.catalog.is_symlink(): S.fail('样片目录文件不安全')
            # A previously written backup but missing main file is corruption,
            # not a new empty library. Keep all bytes for manual recovery.
            if ((self.root / 'catalog-v1.previous.json').exists()
                    or any((self.root / 'originals').iterdir()) or any((self.root / 'thumbnails').iterdir())):
                S.fail('目录文件缺失但保留资源/备份仍在；未重置空库，请恢复后重试', 'catalog_corrupt')
            return S.empty()
        current = self.catalog.lstat()
        if not stat.S_ISREG(current.st_mode): S.fail('样片目录不是普通文件', 'catalog_corrupt')
        if self._cached_catalog is not None and self._cached_stamp == self._stamp(current):
            return self._cached_catalog
        fd = os.open(self.catalog, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > S.MAX_CATALOG_BYTES:
                S.fail('目录文件不是有界普通文件', 'catalog_corrupt')
            raw = stream.read(S.MAX_CATALOG_BYTES + 1)
            if len(raw) > S.MAX_CATALOG_BYTES: S.fail('目录文件超过读取预算', 'catalog_corrupt')
            if self._stamp(info) != self._stamp(os.fstat(stream.fileno())) or self._stamp(info) != self._stamp(self.catalog.lstat()):
                S.fail('读取期间样片目录被外部程序改变', 'catalog_corrupt')
        try:
            value = json.loads(raw, object_pairs_hook=_pairs,
                               parse_constant=lambda v: S.fail('目录包含非有限数值'))
            validated = S.check(value)
            self._cached_stamp = self._stamp(info); self._cached_catalog = validated
            return validated
        except (ValueError, UnicodeError, RecursionError) as error:
            raise S.LibraryError('样片目录损坏，原文件及备份均未覆盖：' + str(error), code='catalog_corrupt') from error

    def _replace(self, target, raw, before_replace=None):
        self.require_space(len(raw))
        fd, name = tempfile.mkstemp(prefix='.catalog-', dir=self.root)
        replaced = False; replacing = False
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            if target.is_symlink(): S.fail('样片目录文件不安全')
            self.require_space(0)
            if before_replace is not None: before_replace()
            replacing = True
            os.replace(name, target); replaced = True
            _sync_dir(self.root)
        except OSError as error:
            definite = {errno.EACCES, errno.EPERM, errno.ENOENT, errno.ENOTDIR, errno.EISDIR,
                        errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EEXIST, errno.EXDEV,
                        errno.ENAMETOOLONG, errno.EMLINK}
            unknown = replaced or (replacing and error.errno not in definite)
            raise S.LibraryError('样片目录保存失败；请刷新核对后再操作：' + str(error),
                                 code='storage', outcome_unknown=unknown, committed=None if unknown else False) from error
        finally:
            if os.path.exists(name): os.unlink(name)

    @contextmanager
    def read(self):
        """Read-only internal view. Consumers must not mutate this validated cache.

        Metadata identity is rechecked under the cross-process lock every time;
        atomic external writes invalidate it. Thumbnail reads need not reparse or
        deep-copy 2000 sample records for each of 48 visible cards.
        """
        fd = os.open(self.root / '.catalog.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: S.fail('样片库正被另一个操作使用，请稍后刷新', 'busy')
            catalog = self._read()
            if not self.catalog.exists():
                self._replace(self.catalog, json.dumps(catalog, separators=(',', ':'), allow_nan=False).encode())
            yield catalog
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)

    @contextmanager
    def locked(self, expected_revision=None, *, before_commit=None):
        fd = os.open(self.root / '.catalog.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: S.fail('样片库正被另一个操作使用，请稍后刷新', 'busy')
            old = self._read()
            if expected_revision is not None:
                S.integer(expected_revision, 0, 2**53 - 2)
                if expected_revision != old['revision']: S.fail('样片库已更新，请刷新后重试', 'stale')
            if not self.catalog.exists():
                # Persist the empty identity before any immutable object is
                # installed, so a failed first import cannot look like a new library.
                self._replace(self.catalog, json.dumps(old, separators=(',', ':'), allow_nan=False).encode())
            working = S.check(old)
            yield working
            if working != old:
                if expected_revision is None: S.fail('目录修改缺少版本条件')
                working['revision'] = old['revision'] + 1
                S.check(working)
                raw = json.dumps(working, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
                if len(raw) > S.MAX_CATALOG_BYTES: S.fail('样片目录超过保存预算')
                if self.catalog.exists():
                    previous = json.dumps(old, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
                    self._replace(self.root / 'catalog-v1.previous.json', previous)
                self._replace(self.catalog, raw, before_replace=before_commit)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)

    def usage(self):
        """Count every owned byte, including failed-operation orphans and trash."""
        total = 0
        for folder in ('originals', 'thumbnails', 'staging'):
            with os.scandir(self.root / folder) as entries:
                count = 0
                for entry in entries:
                    count += 1
                    if count > S.MAX_RECORDS * 3: S.fail('资源目录条目超限')
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        S.fail('资源目录包含不安全条目')
                    total += entry.stat(follow_symlinks=False).st_size
        # Include catalogue, previous recovery copy and any interrupted temp files.
        with os.scandir(self.root) as entries:
            for count, entry in enumerate(entries, 1):
                if count > S.MAX_RECORDS * 3: S.fail('样片根目录条目超限')
                if entry.name in ('catalog-v1.json', 'catalog-v1.previous.json', '.catalog.lock') or entry.name.startswith('.catalog-'):
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False): S.fail('样片目录元数据不安全')
                    total += entry.stat(follow_symlinks=False).st_size
        return total

    def free_bytes(self, path=None):
        return shutil.disk_usage(path or self.root).free

    def require_space(self, addition, path=None):
        # Real free space is separate from configured admission policy. A margin
        # protects catalogue/recovery writes; ENOSPC can still race and is handled.
        if self.free_bytes(path) < addition + 32 * 1024 * 1024:
            S.fail('磁盘可用空间不足（保留 32 MiB 恢复余量）；未删除原片或引用资源', 'disk_full')

    def admit_bytes(self, addition):
        if self.usage() + addition > self.budget_bytes:
            S.fail('本地样片达到配置的存储准入预算；可调整 LRT_SAMPLE_LIBRARY_MAX_BYTES，未删除任何资源', 'storage_capacity')
        self.require_space(addition)

    def verify_object(self, name, digest, *, thumbnail=False):
        S.digest(digest)
        if thumbnail:
            if name != digest + '.jpg': S.fail('缩略图路径无效')
        elif not any(name == digest + suffix for suffix in S.FORMATS.values()):
            S.fail('原片路径无效')
        path = self.root / ('thumbnails' if thumbnail else 'originals') / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > (1024 * 1024 if thumbnail else S.MAX_OBJECT_BYTES):
            S.fail('样片资源缺失、不安全或超限', 'asset_missing')
        if hash_file(path) != digest: S.fail('样片资源内容变化，未继续使用', 'asset_corrupt')
        return path

    def install(self, staged, digest, suffix, *, thumbnail=False):
        S.digest(digest)
        self.require_space(0)
        if suffix not in ('.jpg', '.png', '.tif', '.webp'): S.fail('资源格式无效')
        path = self.root / ('thumbnails' if thumbnail else 'originals') / (digest + suffix)
        if path.exists() or path.is_symlink():
            self.verify_object(path.name, digest, thumbnail=thumbnail)
        else:
            # The source is already private, fsynced and inside staging; caller
            # holds catalogue lock across admission, object install and commit.
            os.replace(staged, path); _sync_dir(path.parent)
        return path
