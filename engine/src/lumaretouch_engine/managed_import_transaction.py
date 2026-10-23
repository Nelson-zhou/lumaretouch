"""Atomic project registration after verified bytes; outcome remains queryable."""
import fcntl
import hashlib
import os
import stat
import time
import uuid
from .source_relocation_io import open_directory
from .source_relocation_transaction import MAX_PROJECT, encoded, read_project


def persist(path, output, before_sha, operation_id, validate, cancelled, recheck, *, imported=0):
    """Return old on pre-replace error; unknown after replace, never overwrite rollback."""
    validate(output)
    body = {k: v for k, v in output.items() if k not in ('_source_path', '_source_sha256')}
    body['updated_ns'] = time.time_ns()
    receipts = dict(body.get('managed_import_receipts', {}))
    if operation_id not in receipts and len(receipts) >= 256: raise ValueError('导入回执已达 256 项，请新建项目；不能遗忘幂等身份')
    receipts[operation_id] = {'request_id': operation_id, 'status': 'succeeded', 'imported': imported}
    body['managed_import_receipts'] = receipts
    data = encoded(body)
    if len(data) > MAX_PROJECT: raise ValueError('项目超过大小上限')
    after_sha = hashlib.sha256(data).hexdigest()
    directory = os.path.dirname(path)
    parent = open_directory(directory)
    target = os.path.basename(path)
    lock, temp, replaced = None, None, False
    try:
        lock = os.open(target + '.relocation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(lock).st_mode): raise ValueError('项目锁不是普通文件')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if read_project(path)[1] != before_sha: raise ValueError('磁盘项目已变化，请重新打开并审核')
        temp = '.lrt-managed-import-' + uuid.uuid4().hex
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if cancelled(): raise InterruptedError('已取消，项目保持原样')
        recheck()
        if cancelled(): raise InterruptedError('已取消，项目保持原样')
        if read_project(path)[1] != before_sha: raise ValueError('提交前项目发生变化')
        latest_parent = open_directory(directory)
        try:
            if (os.fstat(parent).st_dev, os.fstat(parent).st_ino) != (os.fstat(latest_parent).st_dev, os.fstat(latest_parent).st_ino):
                raise ValueError('项目所在目录发生变化')
        finally:
            os.close(latest_parent)
        os.replace(temp, target, src_dir_fd=parent, dst_dir_fd=parent)
        replaced, temp = True, None
        os.fsync(parent)
        return {'status': 'succeeded', 'sha256': after_sha, 'project': body}
    except Exception as error:
        if replaced:
            return {'status': 'unknown', 'sha256': after_sha, 'error': str(error), 'requires_readback': True}
        raise
    finally:
        if temp is not None:
            try: os.unlink(temp, dir_fd=parent)
            except OSError: pass
        if lock is not None: os.close(lock)
        os.close(parent)
