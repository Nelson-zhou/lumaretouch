# SPDX-License-Identifier: GPL-3.0-or-later
"""Separate flock/CAS catalogue and immutable objects. No automatic reset or GC."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import fcntl
import json
import os
import stat
from . import background_material_state as S


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out: S.fail('背景目录包含重复字段', 'catalog_corrupt')
        out[key] = value
    return out


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def _directory(path):
    # Refuse managed symlinks rather than resolving them to another store.
    try: path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error: S.fail(f'无法创建背景素材目录：{error}', 'storage')
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode): S.fail('背景素材目录不是实际文件夹', 'unsafe_path')
    return info.st_dev, info.st_ino


class Store:
    def __init__(self, root=None):
        base = os.environ.get('LRT_BACKGROUND_MATERIAL_DIR') if root is None else os.fspath(root)
        if base is None:
            data = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
            base = os.path.join(data, 'LumaRetouch', 'background-materials')
        if not isinstance(base, str) or not os.path.isabs(base) or '\x00' in base:
            S.fail('背景素材目录必须是本地绝对路径', 'storage')
        self.root = Path(os.path.normpath(base))
        self.objects = self.root / 'objects'; self.thumbnails = self.root / 'thumbnails'
        self.staging = self.root / 'staging'; self.catalog = self.root / 'catalog.json'
        self.previous = self.root / 'catalog.previous.json'; self.lock_path = self.root / 'catalog.lock'
        self.identities = {p: _directory(p) for p in (self.root, self.objects, self.thumbnails, self.staging)}
        raw_budget = os.environ.get('LRT_BACKGROUND_MATERIAL_MAX_BYTES', str(S.MAX_STORAGE_BYTES))
        if not raw_budget.isdecimal() or not 1 <= int(raw_budget) <= 1024**4:
            S.fail('背景素材存储预算无效', 'storage')
        self.budget_bytes = int(raw_budget)

    def check_layout(self):
        for path, identity in self.identities.items():
            try: info = path.lstat()
            except OSError: S.fail('背景素材目录已移动或丢失', 'unsafe_path')
            if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != identity:
                S.fail('背景素材目录身份已改变；未跟随替代路径', 'unsafe_path')

    @contextmanager
    def locked(self, expected_revision=None):
        self.check_layout()
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): S.fail('背景素材锁不是普通文件', 'unsafe_path')
            fcntl.flock(fd, fcntl.LOCK_EX)
            self.check_layout()
            if not self.catalog.exists() and not self.catalog.is_symlink():
                if self.previous.exists() or self.previous.is_symlink():
                    S.fail('背景目录缺失但恢复副本仍存在；不会静默重建', 'catalog_missing')
                if any(self.objects.iterdir()) or any(self.thumbnails.iterdir()):
                    S.fail('背景目录缺失但资源仍存在；不会静默丢失索引', 'catalog_missing')
                self._replace_initial(S.empty())
            catalog = self._read_catalog(self.catalog)
            if expected_revision is not None:
                S.integer(expected_revision)
                if expected_revision != catalog['revision']:
                    S.fail('背景目录版本已变化，请刷新后重试', 'stale')
            yield catalog
        finally:
            # Cleanup is not a second publication outcome. Closing also releases
            # flock; a cleanup error must not turn a durable commit into failure.
            try: fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError: pass
            try: os.close(fd)
            except OSError: pass

    @contextmanager
    def read(self):
        with self.locked() as catalog: yield catalog

    def _read_catalog(self, path):
        raw = self.read_file(path, S.MAX_CATALOG_BYTES)
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                               parse_constant=lambda _: S.fail('背景目录含非有限数值', 'catalog_corrupt'))
            return S.check(value)
        except S.MaterialError: raise
        except (ValueError, UnicodeError, TypeError, OverflowError) as error:
            S.fail(f'背景素材目录损坏；保留原文件：{error}', 'catalog_corrupt')

    def read_file(self, path, maximum):
        self.check_layout()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
                S.fail('背景素材资源不是有界普通文件', 'unsafe_path')
            with os.fdopen(os.dup(fd), 'rb') as stream: data = stream.read(maximum + 1)
            after = os.fstat(fd)
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if len(data) != before.st_size or stamp(before) != stamp(after):
                S.fail('背景素材资源在读取期间变化', 'changed')
            return data
        finally: os.close(fd)

    def _write_temp(self, data, prefix):
        self.check_layout(); path = self.root / (prefix + S.new_id() + '.tmp')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True); raise
        return path

    def sync_file(self, path):
        """Re-admitted orphan objects must be durable before catalogue publication."""
        self.check_layout()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): S.fail('背景对象不是普通文件', 'unsafe_path')
            os.fsync(fd)
        finally: os.close(fd)

    def _replace_initial(self, value):
        tmp = self._write_temp(_encoded(S.check(value)), '.initial-')
        published = False
        try:
            # The catalogue lock prevents two app owners from initialising it.
            os.link(tmp, self.catalog, follow_symlinks=False); published = True
            _sync_dir(self.root)
        except Exception as error:
            if published:
                S.fail(f'背景目录已创建但耐久性未确认：{error}', 'durability', outcome_unknown=True, committed=True)
            raise
        finally:
            try: tmp.unlink(missing_ok=True)
            except OSError: pass

    def commit(self, before, candidate, *, cancelled=lambda: False):
        """Caller holds locked(). No fallible post-publication receipt building."""
        self.check_layout(); before = S.check(before); candidate = S.check(candidate)
        if candidate['library_id'] != before['library_id'] or candidate['revision'] != before['revision']:
            S.fail('背景素材事务不能更换目录身份或版本')
        if candidate == before: return before
        if before['revision'] == S.MAX_REVISION: S.fail('背景素材版本已达到上限', 'capacity')
        candidate['revision'] += 1
        raw = _encoded(S.check(candidate))
        if len(raw) > S.MAX_CATALOG_BYTES: S.fail('背景目录超过 32 MiB', 'capacity')
        # Recheck the actual on-disk CAS immediately before preparing publication.
        current = self._read_catalog(self.catalog)
        if current != before: S.fail('背景目录在事务期间变化', 'stale')
        self.require_space(len(raw) * 2 + S.MAX_CATALOG_BYTES)
        tmp = self._write_temp(raw, '.catalog-'); backup = None; published = False
        try:
            S.cancelled(cancelled)
            backup = self._write_temp(_encoded(before), '.previous-')
            os.replace(backup, self.previous); backup = None
            _sync_dir(self.root); S.cancelled(cancelled)
            self.check_layout(); os.replace(tmp, self.catalog); published = True
            _sync_dir(self.root)
        except Exception as error:
            if published:
                S.fail(f'背景目录已发布但耐久性未确认，请查询原请求：{error}',
                       'durability', outcome_unknown=True, committed=True)
            raise
        finally:
            # Already-renamed temp is absent. Cleanup failure cannot invalidate a
            # confirmed durable catalogue write; no cancellation check follows it.
            for path in (tmp, backup):
                if path is not None:
                    try: path.unlink(missing_ok=True)
                    except OSError: pass
        return candidate

    def require_space(self, addition):
        info = os.statvfs(self.root)
        if addition + 32 * 1024**2 > info.f_bavail * info.f_frsize:
            S.fail('背景素材目录磁盘可用空间不足', 'storage_capacity')

    def usage(self):
        self.check_layout(); total = 0; count = 0
        for directory in (self.root, self.objects, self.thumbnails, self.staging):
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    if count > S.MAX_RECORDS * 4: S.fail('背景存储条目超过统计预算', 'capacity')
                    if directory == self.root and Path(entry.path) in (self.objects, self.thumbnails, self.staging):
                        continue
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        S.fail('背景存储包含非普通对象；未清理它们', 'unsafe_path')
                    total += entry.stat(follow_symlinks=False).st_size
        return total

    def check_budget(self, addition):
        if self.usage() + addition > self.budget_bytes:
            S.fail('背景素材达到存储预算；回收站原件仍保留，未删除任何文件', 'storage_capacity')
        self.require_space(addition)

    def object_path(self, row):
        if row['format'] not in S.FORMATS or row['object_name'] != S.digest(row['sha256']) + S.FORMATS[row['format']]:
            S.fail('背景原件对象名称无效', 'unsafe_path')
        return self.objects / row['object_name']

    def verify_object(self, row):
        path = self.object_path(row); data = self.read_file(path, S.MAX_OBJECT_BYTES)
        if len(data) != row['bytes'] or sha256(data).hexdigest() != row['sha256']:
            S.fail('背景素材原件缺失或发生变化；未使用同名替代文件', 'changed')
        if row['binding']['path'] != str(path):
            S.fail('背景素材目录位置变化；不能静默重新绑定', 'changed')
        return path
