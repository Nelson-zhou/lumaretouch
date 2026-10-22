"""One cancellable owned process. No inference inside the engine event thread."""
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from . import manifest as M, state as S


class SemanticJob:
    def __init__(self, path, source, device):
        from ..cpu_memory_budget import available_estimate
        source = S.source(source)
        if device not in ('cpu', 'cuda'):
            raise ValueError('请选择自动选区的明确计算设备')
        if available_estimate() < source['width'] * source['height'] * 32 + 3 * 1024**3:
            raise ValueError('自动选区内存预算不足；手工标记仍可用')
        self.directory = tempfile.TemporaryDirectory(prefix='lumaretouch-sky-semantic-')
        self.root = Path(self.directory.name)
        self.process = None
        self.state, self.result, self.error = 'running', None, None
        self.started = time.monotonic()
        try:
            data = json.dumps({'path': str(path), 'source': source, 'device': device}, allow_nan=False)
            if len(data.encode()) > 65536:
                raise ValueError('自动选区源路径超出预算')
            (self.root / 'request.json').write_text(data)
            env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
            self.process = subprocess.Popen([sys.executable, '-m', 'lumaretouch_engine.sky_semantic.worker',
                '--directory', self.directory.name, '--parent-pid', str(os.getpid())], env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True, start_new_session=True)
        except BaseException:
            self.directory.cleanup()
            raise

    def poll(self):
        if self.state != 'running':
            return self.state
        if self.process.poll() is None:
            if time.monotonic() - self.started > 180:
                self.cancel()
                self.state, self.error = 'failed', '自动选区超过 180 秒预算；不会使用空白或全幅替代'
            return self.state
        try:
            if self.process.returncode:
                error = self.root / 'error.json'
                detail = json.loads(error.read_bytes()[:8192]).get('error') if error.is_file() else None
                raise ValueError(detail or '自动选区工作进程失败：' + str(self.process.returncode))
            result = self.root / 'result.json'
            info = result.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > M.MAX_RESULT_BYTES:
                raise ValueError('自动选区结果文件无效')
            self.result = json.loads(result.read_bytes())
            self.state = 'ready'
        except Exception as error:
            self.state, self.error = 'failed', str(error)[:2000]
        self.directory.cleanup()
        return self.state

    def cancel(self):
        if self.process is not None and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait()
        self.state, self.result = 'cancelled', None
        self.directory.cleanup()
