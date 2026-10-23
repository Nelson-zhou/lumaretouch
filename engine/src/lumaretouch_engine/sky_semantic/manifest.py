"""Read-only pinned inventory; importing this module never installs or imports ML."""
import hashlib
import json
import os
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
CONTRACT = 'oneformer-ade20k-swin-tiny-semantic-rgb8-512-1024-fp32-v1'
FORK_ID = 'lumaretouch-oneformer-semantic'
FORK_VERSION = '5.20.2+lumaretouch.semantic1'
MAX_MASK_PIXELS = 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_INSTALL_FILES = 65536
MAX_INSTALL_BYTES = 4 * 1024**3
MAX_RECEIPT_BYTES = 8 * 1024**2


def lock():
    return json.loads((HERE / 'assets-lock.json').read_text())


def identity():
    value = lock()
    return {'id': value['model_id'], 'revision': value['revision'], 'contract': CONTRACT,
            'weights_sha256': value['files'][-1]['sha256'], 'fork': FORK_ID,
            'fork_version': FORK_VERSION,
            'adapter_sha256': hashlib.sha256(b''.join((HERE / name).read_bytes() for name in
                ('predict.py', 'task_tokens.py', 'resolver.py', 'worker.py', 'immutable_input.py'))).hexdigest(),
            'inventory_sha256': hashlib.sha256(
                (HERE / 'assets-lock.json').read_bytes() + (HERE / 'fork-patches.json').read_bytes()
                + (HERE / 'checkpointing_support.py.txt').read_bytes()
                + (HERE / 'doc_identity.py.txt').read_bytes()
                + (HERE / 'ONEFORMER-LICENSE-MIT.txt').read_bytes()
                + (HERE / 'TRANSFORMERS-LICENSE-APACHE2.txt').read_bytes()).hexdigest()}


def namespace(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def directory():
    home = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return home.absolute() / 'lumaretouch/optional-models/oneformer-sky-semantic' / namespace(identity())


def directory_handle(path):
    """Traverse every ancestor with openat/O_NOFOLLOW, not a path check race."""
    path = Path(path).absolute()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            if part in ('.', '..'):
                raise ValueError('自动选区安装路径必须规范化')
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def regular_file(path, *, limit):
    """Open bounded regular data, never a FIFO, device or symlink."""
    path = Path(path).absolute()
    parent = directory_handle(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= limit:
            raise ValueError('自动选区安装文件不是预算内的普通文件')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise


def file_identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def hash_file(path, *, limit, cancelled=lambda: False):
    with regular_file(path, limit=limit) as stream:
        return hash_stream(stream, limit=limit, cancelled=cancelled)


def hash_stream(stream, *, limit, cancelled=lambda: False):
    digest, count = hashlib.sha256(), 0
    before = file_identity(os.fstat(stream.fileno()))
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        if cancelled():
            raise InterruptedError('自动选区校验已取消')
        count += len(block)
        if count > limit:
            raise ValueError('可选模型文件超出锁定大小')
        digest.update(block)
    if file_identity(os.fstat(stream.fileno())) != before:
        raise ValueError('自动选区安装文件在校验期间变化')
    return count, digest.hexdigest()


def installation_stamp():
    """Fast cache invalidation, never a substitute for strict replay/hash proof."""
    root = directory()
    if root.is_symlink():
        raise ValueError('自动选区安装不允许符号链接')
    paths = [root / 'receipt.json']
    paths.extend(root / 'model' / entry['filename'] for entry in lock()['files'])
    patches = json.loads((HERE / 'fork-patches.json').read_text())
    paths.extend(root / 'runtime' / entry['path'] for entry in patches['patches'])
    paths.extend(root / 'runtime' / patches[key]['path'] for key in ('support', 'documentation_adapter'))
    stamps = []
    for path in paths:
        if path.is_symlink():
            raise ValueError('自动选区安装文件不允许符号链接')
        stat = path.stat()
        stamps.append((str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    return tuple(stamps)


def inventory_paths(root, expected, *, cancelled=lambda: False):
    """Exact bounded tree inventory, including directories and special files."""
    allowed = set(expected) | {'receipt.json'}
    directories = set()
    for name in allowed:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name:
            raise ValueError('自动选区安装清单路径无效')
        directories.update(str(parent) for parent in path.parents if str(parent) != '.')
    seen, pending, count = set(), [root], 0
    while pending:
        parent = pending.pop()
        directory = directory_handle(parent)
        try:
            entries = os.scandir(directory)
        except BaseException:
            os.close(directory)
            raise
        try:
            with entries:
                for entry in entries:
                    if cancelled():
                        raise InterruptedError('自动选区校验已取消')
                    count += 1
                    if count > len(allowed) + len(directories):
                        raise ValueError('自动选区安装条目超过固定清单')
                    path = parent / entry.name
                    relative = str(path.relative_to(root))
                    if entry.is_symlink():
                        raise ValueError('自动选区安装中不允许符号链接')
                    if entry.is_dir(follow_symlinks=False):
                        if relative not in directories:
                            raise ValueError('自动选区安装包含清单外目录')
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False) and relative in allowed:
                        seen.add(relative)
                    else:
                        raise ValueError('自动选区安装包含额外文件或特殊文件')
        finally:
            os.close(directory)
    if seen != allowed:
        raise ValueError('自动选区安装文件缺失')
    return sorted(expected)


def _verify_installation(root, expected_identity, *, cancelled=lambda: False):
    """Internal: expected identity must be code-owned, NEVER read from a receipt.

    The normal worker uses identity(); only explicit offline migration supplies
    its single historical allowlisted identity. This does not validate or replay
    an old adapter, nor upgrade any accepted semantic descriptor.
    """
    root = Path(root).absolute()
    receipt = root / 'receipt.json'
    if root.resolve() != root or not root.is_dir():
        raise ValueError('尚未安装经过校验的天空自动选区模型；手工标记仍可使用')
    with regular_file(receipt, limit=MAX_RECEIPT_BYTES) as stream:
        before = file_identity(os.fstat(stream.fileno()))
        raw = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(raw) > MAX_RECEIPT_BYTES or file_identity(os.fstat(stream.fileno())) != before:
            raise ValueError('自动选区回执在读取期间变化或超过预算')
        record = json.loads(raw)
    if (type(record) is not dict or record.get('identity') != expected_identity
            or type(record.get('files')) is not dict or len(record['files']) > MAX_INSTALL_FILES):
        raise ValueError('自动选区安装清单与当前固定版本不一致')
    from .install import expected_files
    expected_inventory = expected_files(root, cancelled=cancelled)
    if record['files'] != expected_inventory:
        raise ValueError('安装回执不匹配固定轮子与明确的语义运行库补丁')
    for relative in inventory_paths(root, expected_inventory, cancelled=cancelled):
        path = root / relative
        expected = record['files'].get(relative)
        if (not expected or hash_file(path, limit=expected['size'], cancelled=cancelled)
                != (expected['size'], expected['sha256'])):
            raise ValueError('自动选区安装文件变化：' + relative)
    for item in lock()['files']:
        if record['files'].get('model/' + item['filename']) != {
                'size': item['size'], 'sha256': item['sha256']}:
            raise ValueError('自动选区模型与官方固定清单不一致')
    patches = json.loads((HERE / 'fork-patches.json').read_text())
    for patch in patches['patches']:
        if record['files'].get('runtime/' + patch['path'], {}).get('sha256') != patch['after_sha256']:
            raise ValueError('语义专用运行库补丁身份不一致')
    if record['files'].get('runtime/' + patches['support']['path'], {}).get('sha256') != patches['support']['sha256']:
        raise ValueError('语义专用运行库支持模块身份不一致')
    return root, record


def verify(root=None, *, cancelled=lambda: False):
    """Verify every installed byte before the CURRENT runtime is importable."""
    return _verify_installation(root or directory(), identity(), cancelled=cancelled)


def disclosure():
    value = lock()
    return {'identity': identity(), 'model_bytes': sum(x['size'] for x in value['files']),
            'weight_bytes': value['files'][-1]['size'], 'license': value['license'],
            'license_url': value['license_evidence'], 'runtime': [
                {'name': x['name'], 'version': x['version'], 'license': x['license'],
                 'source': x['metadata_url']} for x in value['runtime']],
            'note': '可选本地语义模型，仅提出天空/人物/水面选区。必须检查并可用画笔修正；水面反射仍需明确地平线。',
            'quality_status': '尚未在本机验收；不保证细发丝、透明物体或倒影边缘质量',
            'fork': {'id': FORK_ID, 'version': FORK_VERSION,
                     'unsupported': ['general tokenizers', 'text generation', 'training', 'dynamic documentation']}}
