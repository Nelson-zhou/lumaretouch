"""Explicit offline reuse of one audited historical installation's payload.

This copies model/runtime data, not an adapter or accepted descriptor. The old
namespace and receipt are never edited or removed. An old receipt is not trusted
as inventory: every expected byte is derived again from locked original wheels,
model hashes, and the unchanged audited runtime patches. No inference or package
installer runs. Only a separately verified current-identity directory is published.
"""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from . import manifest as M

# Frozen from read-only `git show e3dfe7b7:<path>`, NOT the live edited sources.
# The legacy adapter hash concatenates predict/task_tokens/resolver/worker only.
LEGACY_IDENTITY = {
    'id': 'shi-labs/oneformer_ade20k_swin_tiny',
    'revision': '05f2812b1eccf9909b3897777450f8d68148cafc',
    'contract': 'oneformer-ade20k-swin-tiny-semantic-rgb8-512-1024-fp32-v1',
    'weights_sha256': '909b07dbf4129c2bbb8df4498e35dcd46f305e3ec45329d3ff6d4f0360de27f3',
    'fork': 'lumaretouch-oneformer-semantic',
    'fork_version': '5.20.2+lumaretouch.semantic1',
    'adapter_sha256': 'f02bc1811ddb9787c80cb967fd1e10a334c96e4725a8a020bc9f8da273adf379',
    'inventory_sha256': '32a0d69bfd71205106bd1818892c9525830f2bfa4d8d1b2173367ed6f5a2d7b6',
}
LEGACY_NAMESPACE = 'bf7bdae029942fbc2cd88115ac9b419b02307035a933b3105bfa0ddac8cf19d6'
RESERVE_BYTES = 64 * 1024**2


def _cancel(cancelled):
    if cancelled():
        raise InterruptedError('离线模型迁移已取消；旧安装保持不变')


def _source():
    current = M.identity()
    if (M.namespace(LEGACY_IDENTITY) != LEGACY_NAMESPACE or current == LEGACY_IDENTITY
            or set(current) != set(LEGACY_IDENTITY)
            or any(current[key] != value for key, value in LEGACY_IDENTITY.items()
                   if key != 'adapter_sha256')):
        raise ValueError('当前模型/运行库清单不符合已审核的离线迁移范围；请使用明确下载流程')
    target = M.directory()
    return target.parent / LEGACY_NAMESPACE, target


def _inspect(*, cancelled=lambda: False):
    source, target = _source()
    if os.path.lexists(target):
        raise ValueError('当前身份目录已存在；离线迁移不会覆盖或修复现有安装')
    _, record = M._verify_installation(source, dict(LEGACY_IDENTITY), cancelled=cancelled)
    # Retain the hash of the actual verified historical receipt as provenance,
    # not as permission to claim that the historical adapter is current.
    with M.regular_file(source / 'receipt.json', limit=M.MAX_RECEIPT_BYTES) as stream:
        before = M.file_identity(os.fstat(stream.fileno()))
        raw = stream.read(M.MAX_RECEIPT_BYTES + 1)
        if (len(raw) > M.MAX_RECEIPT_BYTES or json.loads(raw) != record
                or M.file_identity(os.fstat(stream.fileno())) != before):
            raise ValueError('旧安装回执在校验期间变化')
    return source, target, record, hashlib.sha256(raw).hexdigest()


def status(*, cancelled=lambda: False):
    result = {'migration_available': False, 'requires_descriptor_review': True}
    try:
        _, _, record, _ = _inspect(cancelled=cancelled)
        result.update(migration_available=True,
                      migration_bytes=sum(item['size'] for item in record['files'].values()),
                      migration_source_identity=dict(LEGACY_IDENTITY))
    except (ValueError, OSError) as error:
        if isinstance(error, InterruptedError):
            raise
        result['migration_reason'] = str(error)[:2000]
    return result


def _sync_dir(path):
    fd = M.directory_handle(path)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish(source, target):
    """Atomic Linux no-clobber rename, including existing empty directories."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        raise ValueError('当前平台缺少原子无覆盖目录发布能力；旧安装未修改')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if source.parent != target.parent:
        raise ValueError('离线迁移必须在同一真实父目录内原子发布')
    parent = M.directory_handle(target.parent)
    try:
        if rename(parent, os.fsencode(source.name), parent, os.fsencode(target.name), 1) != 0:
            number = ctypes.get_errno()
            raise OSError(number, os.strerror(number), str(target))
    finally:
        os.close(parent)


def _copy_file(source, target, expected, *, cancelled):
    digest, size = hashlib.sha256(), 0
    with M.regular_file(source, limit=expected['size']) as input_stream:
        before = M.file_identity(os.fstat(input_stream.fileno()))
        with target.open('xb') as output:
            for block in iter(lambda: input_stream.read(1024 * 1024), b''):
                _cancel(cancelled)
                size += len(block)
                if size > expected['size']:
                    raise ValueError('旧安装文件在复制期间超过固定大小')
                output.write(block)
                digest.update(block)
            if ((size, digest.hexdigest()) != (expected['size'], expected['sha256'])
                    or M.file_identity(os.fstat(input_stream.fileno())) != before):
                raise ValueError('旧安装文件在复制期间变化或校验不匹配')
            output.flush()
            os.fsync(output.fileno())
    return size


def migrate(*, cancelled=lambda: False):
    # Fail closed: even a later implementation mistake cannot turn migration
    # into a download path. This process has no source-photo argument or model.
    from ..privacy import install_offline_policy
    install_offline_policy()
    from .install import emit, plan
    value = plan()
    _, target = _source()
    parent = target.parent
    if parent.resolve() != parent or not parent.is_dir():
        raise ValueError('未找到可用的真实旧安装父目录')
    parent_handle = M.directory_handle(parent)
    try:
        fd = os.open('.install.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=parent_handle)
    finally:
        os.close(parent_handle)
    with os.fdopen(fd, 'a') as mutex:
        if not stat.S_ISREG(os.fstat(mutex.fileno()).st_mode):
            raise ValueError('自动选区安装锁不是普通文件')
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _cancel(cancelled)
        if os.path.lexists(target):
            M.verify(target, cancelled=cancelled)
            emit(state='ready', **{**value, 'installed': True, 'migration_available': False,
                                  'requires_descriptor_review': True})
            return
        emit(state='verifying', offline=True, requires_descriptor_review=True)
        source, target, old, receipt_sha256 = _inspect(cancelled=cancelled)
        expected = old['files']
        total = sum(item['size'] for item in expected.values())
        if shutil.disk_usage(parent).free < total + 2 * M.MAX_RECEIPT_BYTES + RESERVE_BYTES:
            raise ValueError('离线迁移空间不足；需保留完整旧安装并复制到新身份目录')
        published, warning = False, None
        try:
            with tempfile.TemporaryDirectory(prefix='.semantic-migration-', dir=parent) as temporary:
                root, received, last_bytes, last_time = Path(temporary), 0, 0, time.monotonic()
                directories = {root}
                for name in sorted(expected):
                    _cancel(cancelled)
                    destination = root / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    directories.update(parent for parent in destination.parents if parent == root or root in parent.parents)
                    if shutil.disk_usage(root).free < expected[name]['size'] + RESERVE_BYTES:
                        raise ValueError('离线迁移可用空间不足；未发布不完整安装')
                    received += _copy_file(source / name, destination, expected[name], cancelled=cancelled)
                    now = time.monotonic()
                    if received - last_bytes >= 16 * 1024**2 or now - last_time >= 2:
                        emit(state='migrating', offline=True, received=received, total=total)
                        last_bytes, last_time = received, now
                current = M.identity()
                if M.namespace(current) != target.name:
                    raise ValueError('应用实现在迁移期间变化；请重新开始')
                record = {'identity': current, 'files': expected, 'fork': M.FORK_VERSION,
                          'licenses': M.disclosure()['runtime'],
                          'migration': {'version': 1, 'method': 'verified-offline-copy',
                                        'source_identity': dict(LEGACY_IDENTITY),
                                        'source_receipt_sha256': receipt_sha256,
                                        'descriptors_upgraded': False, 'runtime_executed': False}}
                receipt = json.dumps(record, sort_keys=True).encode()
                if len(receipt) > M.MAX_RECEIPT_BYTES:
                    raise ValueError('迁移回执超出固定预算')
                with (root / 'receipt.json').open('xb') as output:
                    output.write(receipt); output.flush(); os.fsync(output.fileno())
                emit(state='verifying', offline=True, received=received, total=total)
                M.verify(root, cancelled=cancelled)
                # A concurrently modified old receipt/tree is not silently accepted.
                if M.hash_file(source / 'receipt.json', limit=M.MAX_RECEIPT_BYTES, cancelled=cancelled)[1] != receipt_sha256:
                    raise ValueError('旧安装回执在迁移期间变化')
                M.inventory_paths(source, expected, cancelled=cancelled)
                for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
                    _cancel(cancelled)
                    _sync_dir(directory)
                emit(state='publishing', offline=True, received=received, total=total)
                _cancel(cancelled)
                if M.identity() != current:
                    raise ValueError('应用实现在发布前变化；请重新开始')
                _publish(root, target)
                published = True
                # Publication is the commit point. A later cancellation must not
                # falsely report that the already published directory was removed.
                _sync_dir(parent)
        except Exception as error:
            if not published:
                raise
            warning = '新身份目录已原子发布，未回滚；目录持久化或暂存清理需检查：' + str(error)[:1500]
        emit(state='ready', **{**value, 'installed': True, 'migrated': True,
                              'migration_available': False, 'migration_bytes': total,
                              'migration_source_identity': dict(LEGACY_IDENTITY),
                              'requires_descriptor_review': True, 'offline': True,
                              **({'publication_warning': warning} if warning else {})})
