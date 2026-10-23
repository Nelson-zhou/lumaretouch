"""One cancellable owned process. No inference inside the engine event thread."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from . import manifest as M, state as S, immutable_input as I


class SemanticJob:
    def __init__(self, path, source, device, *, immutable_input=None):
        from ..cpu_memory_budget import available_estimate
        source = S.source(source)
        if immutable_input is not None:
            if path is not None:
                raise ValueError('规范自动选区输入不能同时指定原始文件路径')
            packet = I.check(immutable_input, source)
        else:
            if not isinstance(path, (str, os.PathLike)) or not str(path):
                raise ValueError('原始照片自动选区需要明确的源文件路径')
            packet = None
        if device not in ('cpu', 'cuda'):
            raise ValueError('请选择自动选区的明确计算设备')
        input_bytes = (source['width'] * source['height'] * 32 if packet is None
                       else len(packet['pixels']) * 8)
        if available_estimate() < input_bytes + 3 * 1024**3:
            raise ValueError('自动选区内存预算不足；手工标记仍可用')
        self.source, self.device, self.immutable_input = source, device, packet
        self.directory = tempfile.TemporaryDirectory(prefix='lumaretouch-sky-semantic-')
        self.root = Path(self.directory.name)
        self.process = None
        self.state, self.result, self.error = 'running', None, None
        self.started = time.monotonic()
        try:
            request = {'source': source, 'device': device}
            if packet is None:
                request['path'] = str(path)
            else:
                request['immutable_input'] = I.write_packet(self.root, packet)
            data = json.dumps(request, allow_nan=False)
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
                try:
                    detail = json.loads(I.read_regular_bytes(error, 8192)).get('error')
                except FileNotFoundError:
                    detail = None
                raise ValueError(detail or '自动选区工作进程失败：' + str(self.process.returncode))
            result = self.root / 'result.json'
            self.result = json.loads(I.read_regular_bytes(result, M.MAX_RESULT_BYTES))
            if (self.result.get('source') != self.source or self.result.get('device') != self.device):
                raise ValueError('自动选区结果属于另一个源或计算设备')
            if self.immutable_input is not None:
                I.validate_result(self.immutable_input, self.result)
            elif '_immutable_input' in self.result:
                raise ValueError('原始照片自动选区不能接收规范源输入结果')
            self.state = 'ready'
        except Exception as error:
            self.state, self.result, self.error = 'failed', None, str(error)[:2000]
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
