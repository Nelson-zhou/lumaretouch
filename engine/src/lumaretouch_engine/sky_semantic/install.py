"""Explicit acquisition helper, never called from an offline photo worker.

Only --install opens the network. It accepts no photo/path/URL arguments. Wheels
are data: no pip, setup.py, entry point, .pth, custom code, or model is executed.
The original wheels are retained so verification derives identities from pinned
archives, not a user-editable receipt. All host accelerator packages are untouched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from . import manifest as M

NOTICE = '''LumaRetouch OneFormer semantic-only fork 5.20.2+lumaretouch.semantic1
Derived from Hugging Face Transformers 5.20.2, Apache License 2.0.
Upstream commit: 18329f1065382e54db698e242cf98bd3f3e5a766.
Original licenses/notices are retained in the distribution metadata.
Changes: remove regex dependency; replace the unused generated-documentation
path with two explicit identity decorators (no regex substitution); direct Swin
backbone construction; separate unchanged checkpointing support; direct
typing_extensions.Unpack; defer legacy GGUF import to its GGUF-only branch.
Only the pinned OneFormer semantic inference path is supported. This is NOT
a replacement for a general Transformers installation. Tokenizer, generation,
training and generated-documentation APIs are unsupported. No model math was
intentionally changed. Runtime/output equivalence has not yet been validated.
'''


def emit(**value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


def wheels():
    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename
    if sys.platform != 'linux' or not (3, 12) <= sys.version_info[:2] < (3, 15):
        raise ValueError('自动选区运行库目前只提供 Linux Python 3.12–3.14 的固定轮子')
    ranks = {tag: i for i, tag in enumerate(sys_tags())}
    chosen = []
    for package in M.lock()['runtime']:
        compatible = []
        for wheel in package['wheels']:
            tags = parse_wheel_filename(wheel['filename'])[3]
            scores = [ranks[t] for t in tags if t in ranks]
            if scores:
                compatible.append((min(scores), wheel))
        if not compatible:
            raise ValueError('当前平台没有固定兼容轮子：' + package['name'])
        chosen.append(min(compatible, key=lambda pair: pair[0])[1])
    return chosen


def plan():
    selected = wheels()
    value = M.disclosure()
    value.update(wheel_bytes=sum(x['size'] for x in selected),
                 download_bytes=sum(x['size'] for x in selected) + value['model_bytes'],
                 installed=False, wheels=[{'filename': x['filename'], 'size': x['size'],
                                          'sha256': x['sha256']} for x in selected])
    return value


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ''
    allowed = (host == 'huggingface.co' or host == 'files.pythonhosted.org'
               or host.endswith('.hf.co') or host.endswith('.huggingface.co'))
    if parsed.scheme != 'https' or parsed.username or parsed.password or not allowed:
        raise ValueError('可选模型下载被重定向到非批准地址')


def download(item, path, done, total):
    check_url(item['url'])
    digest, count = hashlib.sha256(), 0
    opener = urllib.request.build_opener(Redirects())
    with opener.open(urllib.request.Request(item['url'], headers={
            'User-Agent': 'LumaRetouch-Optional-Sky/1'}), timeout=30) as response, path.open('xb') as output:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            count += len(block)
            if count > item['size']:
                raise ValueError('下载文件超过固定大小')
            output.write(block)
            digest.update(block)
            emit(state='downloading', file=item['filename'], received=done + count, total=total)
    if count != item['size'] or digest.hexdigest() != item['sha256']:
        raise ValueError('下载校验失败：' + item['filename'])
    return done + count


def archive_files(path):
    """Yield bounded wheel data without importing it or interpreting scripts."""
    with zipfile.ZipFile(path) as archive:
        total = 0
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = PurePosixPath(info.filename)
            total += info.file_size
            mode = (info.external_attr >> 16) & 0o170000
            if (name.is_absolute() or '..' in name.parts or '\\' in str(name)
                    or mode == stat.S_IFLNK or info.file_size > 128 * 1024**2
                    or total > 512 * 1024**2 or name.suffix in ('.pth', '.pyc')):
                raise ValueError('运行库轮子包含不安全或过大的条目')
            # Wheels in this lock use only root purelib/platlib and dist-info.
            if any(part.endswith('.data') for part in name.parts):
                raise ValueError('固定轮子意外包含安装脚本或重定位数据')
            yield str(name), archive.read(info)


def runtime_files(root, selected):
    """Derive expected installed bytes from hash-locked original wheels + fork."""
    patches = json.loads((M.HERE / 'fork-patches.json').read_text())
    edits = {x['path']: x for x in patches['patches']}
    seen = set()
    for wheel in selected:
        archive = root / 'wheels' / wheel['filename']
        if archive.is_symlink() or M.hash_file(archive, limit=wheel['size']) != (wheel['size'], wheel['sha256']):
            raise ValueError('原始运行库轮子校验失败')
        for name, data in archive_files(archive):
            if name in seen:
                raise ValueError('固定运行库文件冲突：' + name)
            seen.add(name)
            if name in edits:
                patch = edits[name]
                if hashlib.sha256(data).hexdigest() != patch['before_sha256']:
                    raise ValueError('官方轮子源代码与已审计补丁不匹配：' + name)
                text = data.decode()
                for change in patch['replacements']:
                    if text.count(change['old']) != 1:
                        raise ValueError('语义运行库补丁上下文不唯一')
                    text = text.replace(change['old'], change['new'], 1)
                data = text.encode()
                if hashlib.sha256(data).hexdigest() != patch['after_sha256']:
                    raise ValueError('语义运行库补丁结果身份不匹配')
            if name == 'transformers-5.20.2.dist-info/METADATA':
                lines = data.decode().splitlines()
                lines = [line for line in lines if not line.lower().startswith('requires-dist: regex')]
                lines = [('Version: ' + M.FORK_VERSION) if line == 'Version: 5.20.2' else line for line in lines]
                data = ('\n'.join(lines) + '\n').encode()
            # RECORD describes the original wheel; the explicit fork receipt
            # below owns installed hashes. Keep it as provenance, not a proof.
            yield 'runtime/' + name, data
    if not set(edits).issubset(seen):
        raise ValueError('官方轮子缺少预期的语义运行库源代码')
    support = (M.HERE / 'checkpointing_support.py.txt').read_bytes()
    if hashlib.sha256(support).hexdigest() != patches['support']['sha256']:
        raise ValueError('语义支持模块与固定清单不一致')
    yield 'runtime/' + patches['support']['path'], support
    docs = (M.HERE / 'doc_identity.py.txt').read_bytes()
    if hashlib.sha256(docs).hexdigest() != patches['documentation_adapter']['sha256']:
        raise ValueError('语义文档适配器与固定清单不一致')
    yield 'runtime/' + patches['documentation_adapter']['path'], docs
    yield 'runtime/LUMARETOUCH_SEMANTIC_FORK_NOTICE.txt', NOTICE.encode()
    yield 'fork-patches.json', (M.HERE / 'fork-patches.json').read_bytes()
    yield 'assets-lock.json', (M.HERE / 'assets-lock.json').read_bytes()
    yield 'model/LICENSE-MIT.txt', (M.HERE / 'ONEFORMER-LICENSE-MIT.txt').read_bytes()
    yield 'runtime/LUMARETOUCH_SEMANTIC_APACHE2.txt', (M.HERE / 'TRANSFORMERS-LICENSE-APACHE2.txt').read_bytes()


def expected_files(root):
    expected = {}
    for item in M.lock()['files']:
        expected['model/' + item['filename']] = {'size': item['size'], 'sha256': item['sha256']}
    selected = wheels()
    for item in selected:
        expected['wheels/' + item['filename']] = {'size': item['size'], 'sha256': item['sha256']}
    for name, data in runtime_files(root, selected):
        expected[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return expected


def install():
    import fcntl
    value, selected, target = plan(), wheels(), M.directory()
    target.parent.mkdir(parents=True, exist_ok=True)
    with (target.parent / '.install.lock').open('a') as mutex:
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if target.exists():
            M.verify(target)
            emit(state='ready', **{**value, 'installed': True})
            return
        required = value['download_bytes'] * 3 + 512 * 1024**2
        if shutil.disk_usage(target.parent).free < required:
            raise ValueError('可选语义模型安装空间不足（包含原始轮子及解包校验空间）')
        with tempfile.TemporaryDirectory(prefix='.semantic-staging-', dir=target.parent) as staging:
            root, done = Path(staging), 0
            (root / 'wheels').mkdir(); (root / 'model').mkdir()
            for item in M.lock()['files']:
                done = download(item, root / 'model' / item['filename'], done, value['download_bytes'])
            for item in selected:
                done = download(item, root / 'wheels' / item['filename'], done, value['download_bytes'])
            emit(state='verifying', received=done, total=value['download_bytes'])
            for name, data in runtime_files(root, selected):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as output:
                    output.write(data)
            record = {'identity': M.identity(), 'files': expected_files(root),
                      'fork': M.FORK_VERSION, 'licenses': M.disclosure()['runtime']}
            (root / 'receipt.json').write_text(json.dumps(record, sort_keys=True))
            M.verify(root)
            root.rename(target)
        emit(state='ready', **{**value, 'installed': True})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    def stop(_signal, _frame):
        raise InterruptedError('可选模型下载已取消；未发布不完整安装')
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    try:
        if args.install:
            install()
        else:
            value = plan()
            try:
                M.verify(); value['installed'] = True
            except (ValueError, OSError) as error:
                value['reason'] = str(error)
            emit(state='ready' if value['installed'] else 'unavailable', **value)
    except InterruptedError as error:
        emit(state='cancelled', error=str(error)); raise SystemExit(2)
    except Exception as error:
        emit(state='failed', error=str(error)[:2000]); raise SystemExit(1)


if __name__ == '__main__':
    main()
