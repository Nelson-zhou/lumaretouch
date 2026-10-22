"""Read-only pinned inventory; importing this module never installs or imports ML."""
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT = 'oneformer-ade20k-swin-tiny-semantic-rgb8-512-1024-fp32-v1'
FORK_ID = 'lumaretouch-oneformer-semantic'
FORK_VERSION = '5.20.2+lumaretouch.semantic1'
MAX_MASK_PIXELS = 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024


def lock():
    return json.loads((HERE / 'assets-lock.json').read_text())


def identity():
    value = lock()
    return {'id': value['model_id'], 'revision': value['revision'], 'contract': CONTRACT,
            'weights_sha256': value['files'][-1]['sha256'], 'fork': FORK_ID,
            'fork_version': FORK_VERSION,
            'adapter_sha256': hashlib.sha256(b''.join((HERE / name).read_bytes() for name in
                ('predict.py', 'task_tokens.py', 'resolver.py', 'worker.py'))).hexdigest(),
            'inventory_sha256': hashlib.sha256(
                (HERE / 'assets-lock.json').read_bytes() + (HERE / 'fork-patches.json').read_bytes()
                + (HERE / 'checkpointing_support.py.txt').read_bytes()
                + (HERE / 'doc_identity.py.txt').read_bytes()
                + (HERE / 'ONEFORMER-LICENSE-MIT.txt').read_bytes()
                + (HERE / 'TRANSFORMERS-LICENSE-APACHE2.txt').read_bytes()).hexdigest()}


def directory():
    home = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    key = hashlib.sha256(json.dumps(identity(), sort_keys=True).encode()).hexdigest()
    return home / 'lumaretouch/optional-models/oneformer-sky-semantic' / key


def hash_file(path, *, limit, cancelled=lambda: False):
    digest, count = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            if cancelled():
                raise InterruptedError('自动选区校验已取消')
            count += len(block)
            if count > limit:
                raise ValueError('可选模型文件超出锁定大小')
            digest.update(block)
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


def verify(root=None, *, cancelled=lambda: False):
    """Verify every installed byte before the private runtime is importable."""
    root = Path(root or directory())
    receipt = root / 'receipt.json'
    if root.is_symlink() or receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 8 * 1024**2:
        raise ValueError('尚未安装经过校验的天空自动选区模型；手工标记仍可使用')
    record = json.loads(receipt.read_text())
    if record.get('identity') != identity() or not isinstance(record.get('files'), dict):
        raise ValueError('自动选区安装清单与当前固定版本不一致')
    from .install import expected_files
    expected_inventory = expected_files(root)
    if record['files'] != expected_inventory:
        raise ValueError('安装回执不匹配固定轮子与明确的语义运行库补丁')
    actual = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('自动选区安装中不允许符号链接')
        if not path.is_file() or path == receipt:
            continue
        relative = str(path.relative_to(root))
        actual.add(relative)
        expected = record['files'].get(relative)
        if (not expected or hash_file(path, limit=expected['size'], cancelled=cancelled)
                != (expected['size'], expected['sha256'])):
            raise ValueError('自动选区安装文件变化：' + relative)
    if actual != set(record['files']):
        raise ValueError('自动选区安装文件缺失')
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
