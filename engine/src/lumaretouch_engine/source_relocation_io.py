"""Read-only, bounded source identity checks. No decoder, model, or source writes."""
from __future__ import annotations
import hashlib
import os
import stat
import time
from dataclasses import dataclass

MAX_FILES = 10000
MAX_BYTES = 16 * 1024**3
MAX_FILE_BYTES = 2 * 1024**3
MAX_SECONDS = 120
MAX_DEPTH = 16


@dataclass
class Budget:
    cancelled: object
    files: int = 0
    bytes: int = 0
    started: float = 0

    def __post_init__(self):
        self.started = time.monotonic()

    def check(self):
        if self.cancelled():
            raise InterruptedError('已取消，未修改项目或原图')
        if self.files > MAX_FILES or self.bytes > MAX_BYTES or time.monotonic() - self.started > MAX_SECONDS:
            raise TimeoutError('扫描达到数量、总字节或时间上限；请缩小目录范围')


def signature(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def open_directory(path):
    if not isinstance(path, str) or not os.path.isabs(path) or '\x00' in path or len(path) > 4096:
        raise ValueError('需要绝对本地目录')
    parts = [] if path == '/' else path.split('/')[1:]
    if any(part in ('', '.', '..') for part in parts): raise ValueError('目录包含非规范分量')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        result, fd = fd, None
        return result
    finally:
        if fd is not None: os.close(fd)


def open_regular(path):
    """Walk all components with directory FDs and O_NOFOLLOW; reject symlink ancestors."""
    if not isinstance(path, str) or not os.path.isabs(path) or '\x00' in path or len(path) > 4096:
        raise ValueError('需要绝对本地路径')
    parts = path.split('/')[1:]
    if not parts or any(p in ('', '.', '..') for p in parts):
        raise ValueError('路径包含非规范分量')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError('只接受普通文件，不读取链接、设备或管道')
        return fd
    finally:
        os.close(parent)


def hash_file(path, budget, expected_size=None):
    budget.check()
    budget.files += 1
    budget.check()
    fd = open_regular(path)
    try:
        before = os.fstat(fd)
        if before.st_size > MAX_FILE_BYTES:
            raise ValueError('单个源文件超过 2 GiB 安全上限')
        if expected_size is not None and before.st_size != expected_size:
            raise ValueError('源文件变化：大小不匹配')
        digest, count = hashlib.sha256(), 0
        while True:
            budget.check()
            data = os.read(fd, 1024 * 1024)
            if not data:
                break
            count += len(data)
            if count > MAX_FILE_BYTES: raise ValueError('读取时源文件超过 2 GiB 上限')
            budget.bytes += len(data)
            budget.check()
            digest.update(data)
        after = os.fstat(fd)
        if signature(before) != signature(after) or count != before.st_size:
            raise ValueError('读取时源文件发生变化，请重新扫描')
        # Detect rename/replacement while the original descriptor was being read.
        other = open_regular(path)
        try:
            if signature(os.fstat(other)) != signature(after):
                raise ValueError('源路径在核验期间被替换')
        finally:
            os.close(other)
        return {'path': path, 'sha256': digest.hexdigest(), 'bytes': count,
                'stat': list(signature(after))}
    finally:
        os.close(fd)


def candidates(paths, directory, budget, errors):
    if directory is None:
        if not isinstance(paths, list) or not 1 <= len(paths) <= 512:
            raise ValueError('请选择 1–512 个文件')
        for path in dict.fromkeys(paths):
            budget.check()
            yield path
        return
    if paths:
        raise ValueError('文件选择与目录扫描不能同时提交')
    if not isinstance(directory, str) or not os.path.isabs(directory):
        raise ValueError('请选择本地目录')
    # Open every directory without following links, including ancestor components.
    stack = [(directory.rstrip('/') or '/', 0)]
    visited = 0
    while stack:
        budget.check()
        root, depth = stack.pop()
        fd = None
        try:
            fd = open_directory(root)
            with os.scandir(fd) as entries:
                for entry in entries:
                    visited += 1
                    budget.check()
                    if visited > MAX_FILES:
                        raise TimeoutError('目录项目过多，请缩小扫描范围')
                    path = os.path.join(root, entry.name)
                    if entry.is_symlink():
                        if len(errors) < 64: errors.append({'path': path, 'reason': '已跳过符号链接'})
                    elif entry.is_dir(follow_symlinks=False):
                        if depth >= MAX_DEPTH:
                            raise TimeoutError('目录超过 16 层，请选择更具体的目录')
                        stack.append((path, depth + 1))
                    elif entry.is_file(follow_symlinks=False):
                        yield path
        except (PermissionError, FileNotFoundError) as error:
            if len(errors) < 64: errors.append({'path': root, 'reason': str(error)})
        finally:
            if fd is not None: os.close(fd)
