"""One bounded prompted worker. Cancellation terminates the owned process only."""
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time


class PromptedJob:
    def __init__(self, path, source, prompts, device, *, source_input=None):
        from .cpu_memory_budget import available_estimate
        pixels = source['width']*source['height']
        if pixels > 64_000_000 or available_estimate() < pixels*32 + 2*1024**3:
            raise ValueError('Insufficient admitted RAM for full-source prompted selection (source buffers + 2 GiB reserve)')
        if source_input is not None:
            from .creative_derived_prompted import validate
            if path is not None:raise ValueError('Derived prompted worker cannot decode an original pathname')
            validate(source_input,source)
        self.directory = tempfile.TemporaryDirectory(prefix='lumaretouch-prompted-')
        self.root = Path(self.directory.name)
        self.process = None
        self.state, self.result, self.error = 'running', None, None
        self.started = time.monotonic()
        try:
            request_value={'path':path,'source':source,'prompts':prompts,'device':device}
            if source_input is not None:
                request_value['source_input']=source_input['descriptor']
                with (self.root/'source.rgb8').open('xb') as stream:stream.write(source_input['pixels'])
            request = json.dumps(request_value, allow_nan=False)
            if len(request.encode()) > 65536: raise ValueError('Prompt request is too large')
            (self.root/'request.json').write_text(request)
            self.process = subprocess.Popen([sys.executable, '-m', 'lumaretouch_engine.prompted_mask_worker',
                '--directory', self.directory.name, '--parent-pid', str(os.getpid())],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True, start_new_session=True)
        except BaseException:
            self.directory.cleanup()
            raise

    def poll(self):
        if self.state != 'running': return self.state
        if self.process.poll() is None:
            if time.monotonic()-self.started > 180:
                self.cancel()
                self.state, self.error = 'failed', 'Prompted selection exceeded its 180-second deadline'
            return self.state
        try:
            if self.process.returncode:
                error = self.root/'error.json'
                detail = json.loads(error.read_bytes()[:8192]).get('error') if error.is_file() else None
                raise ValueError(detail or f'Prompted worker exited with code {self.process.returncode}')
            path = self.root/'result.json'
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 8*1024**2:
                raise ValueError('Prompted worker returned an invalid result file')
            self.result = json.loads(path.read_bytes())
            self.state = 'ready'
        except Exception as error:
            self.state, self.error = 'failed', str(error)[:2000]
        self.directory.cleanup()
        return self.state

    def cancel(self):
        if self.process is not None and self.process.poll() is None:
            try: os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            self.process.wait()
        self.result = None
        self.state = 'cancelled'
        self.directory.cleanup()
