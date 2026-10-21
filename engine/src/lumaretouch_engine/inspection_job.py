"""One private spool/CPU-worker/result lease, driven by the Engine command thread."""
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from .inspection_bundle import BundleWriter, _open_regular
from .inspection_worker import source_identity


def validate_config(value):
    keys = {'epoch', 'ticket', 'roi', 'source_size', 'canvas_size', 'max_source_pixels',
            'max_display_pixels', 'max_address_bytes', 'timeout_seconds'}
    if type(value) is not dict or set(value) != keys:
        raise ValueError('Inspection render needs an exact admitted configuration')
    def number(v, low, high):
        if type(v) is not int or not low <= v <= high:
            raise ValueError('Invalid inspection admission integer')
        return v
    epoch = value['epoch']
    if type(epoch) is not str or len(epoch) != 32 or any(c not in '0123456789abcdef' for c in epoch) or int(epoch, 16) == 0:
        raise ValueError('Inspection epoch must be nonzero canonical hex')
    ticket = value['ticket']
    if type(ticket) is not list or len(ticket) != 5:
        raise ValueError('Inspection ticket needs five u64 strings')
    for index, part in enumerate(ticket):
        if type(part) is not str or not part.isascii() or not part.isdecimal() or len(part) > 20 or str(int(part)) != part or not (1 if index == 0 else 0) <= int(part) < 2**64:
            raise ValueError('Inspection ticket needs canonical u64 strings')
    for key, length in (('roi',4), ('source_size',2), ('canvas_size',2)):
        if type(value[key]) is not list or len(value[key]) != length:
            raise ValueError('Invalid inspection dimensions')
        for i, n in enumerate(value[key]):
            number(n, 0 if key == 'roi' and i < 2 else 1, 2**32-1)
    source_limit = number(value['max_source_pixels'], 1, 64*1024**2)
    display_limit = number(value['max_display_pixels'], 1, 16*1024**2)
    number(value['max_address_bytes'], 512*1024**2, 8*1024**3)
    number(value['timeout_seconds'], 1, 120)
    sw, sh = value['source_size']; cw, ch = value['canvas_size']
    x, y, w, h = value['roi']
    if sw*sh > source_limit or w*h > display_limit or x+w > cw or y+h > ch:
        raise ValueError('Inspection dimensions exceed admission')
    return {k: list(v) if type(v) is list else v for k,v in value.items()}


class InspectionJob:
    def __init__(self, owned, path, identity, config, max_asset_bytes):
        self.config = validate_config(config)
        self.request = dict(self.config)
        self.request.update(path=path, source_identity=identity, max_asset_bytes=max_asset_bytes)
        self.state = 'spooling'
        self.asset_bytes = owned.asset_bytes
        self.error = None
        self.process = None
        self.writer = None
        self._stderr = None
        self._started = None
        self._cancelled = False
        self._directory = tempfile.TemporaryDirectory(prefix='lumaretouch-inspection-',
                                                     dir=os.environ.get('LRT_INSPECTION_ROOT'))
        self.directory = self._directory.name
        try:
            self.writer = BundleWriter(self.directory, owned)
            with open(os.path.join(self.directory, 'request.json'), 'x', encoding='utf-8') as out:
                json.dump(self.request, out, allow_nan=False, separators=(',',':'))
        except BaseException:
            self.cleanup()
            raise

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def _error(self, message):
        self.error = str(message)[:2000]
        self.state = 'failed'
        self.cleanup()

    def tick(self, max_bytes):
        if self._cancelled:
            if not self.running:
                self.cleanup()
                self.state = 'cancelled'
            return
        try:
            if self.state == 'spooling':
                if not self.writer.advance(max_bytes):
                    return
                self.writer = None
                self._stderr = open(os.path.join(self.directory, 'worker.stderr'), 'xb')
                self.process = subprocess.Popen([sys.executable, '-m', 'lumaretouch_engine.inspection_worker',
                    '--directory', self.directory,
                    '--parent-pid', str(os.getpid()),
                    '--address-bytes', str(self.config['max_address_bytes']),
                    '--output-bytes', str(max(65536, 128+self.config['max_display_pixels']*4)),
                    '--cpu-seconds', str(self.config['timeout_seconds'])],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self._stderr,
                    close_fds=True, start_new_session=True)
                self._started = time.monotonic()
                self.state = 'rendering'
            if self.state == 'rendering':
                rc = self.process.poll()
                if rc is None:
                    if time.monotonic() - self._started > self.config['timeout_seconds']:
                        self.error = 'Inspection worker exceeded wall-clock limit'
                        self.cancel()
                    return
                self._stderr.close(); self._stderr = None
                if rc != 0:
                    message = 'Inspection worker exited with code ' + str(rc)
                    try:
                        f, size = _open_regular(self.directory, 'error.json', 16384)
                        with f:
                            message += ': ' + json.loads(f.read(size)).get('error', '')
                    except Exception:
                        pass
                    self._error(message)
                    return
                result = os.lstat(os.path.join(self.directory, 'result.lrif'))
                w, h = self.config['roi'][2:]
                if not stat.S_ISREG(result.st_mode) or result.st_size != 128+w*h*4:
                    raise ValueError('Inspection worker result has invalid length/type')
                self.state = 'ready'
        except Exception as exc:
            if self.running:
                self.error = str(exc)[:2000]
                self.cancel()
            else:
                self._error(exc)

    def cancel(self):
        self._cancelled = True
        if self.writer is not None:
            self.writer.cancel(); self.writer = None
        if self.running:
            # Only our own session/process group, created by this job. Do not
            # release the directory/lease until poll confirms actual child exit.
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.state = 'cancelling'
        else:
            self.cleanup()
            self.state = 'cancelled'

    def cleanup(self):
        if self.running:
            raise RuntimeError('Cannot free a live inspection worker lease')
        if self.writer is not None:
            self.writer.cancel(); self.writer = None
        if self._stderr is not None:
            self._stderr.close(); self._stderr = None
        self._directory.cleanup()
