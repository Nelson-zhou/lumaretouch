# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned whole-photo portrait proposal, not a reviewed person or fine matte.

No caller-supplied alpha is accepted. A retained operand is replayed from the
bound original and the pinned six-class model. Class ``others`` is excluded;
person count, occlusion and accessory coverage remain unknown. RGB is untouched.
"""
from collections import OrderedDict
from copy import deepcopy
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import numpy as np

CONTRACT = 'mediapipe-selfie-multiclass-portrait-proposal-rgb8-512-u8-v1'
PINNED_SHA = 'c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0'
LIMIT = 262144
_CACHE = OrderedDict()
_LOCK = threading.Lock()


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('自动前景缺少实际 SHA256 来源')
    return value


def check_source(value):
    if (type(value) is not dict or set(value) != {'sha256', 'width', 'height'}
            or any(type(value[k]) is not int or value[k] < 1 for k in ('width', 'height'))
            or value['width'] * value['height'] > 64_000_000):
        raise ValueError('自动前景需要不超过 64MP 的完整源图身份')
    _digest(value['sha256'])
    return deepcopy(value)


def check_binding(value):
    expected = {'origin','contract','model_sha256','runtime','input_sha256',
                'alpha_sha256','width','height','source'}
    if (type(value) is not dict or set(value) != expected
            or value['origin'] != 'automatic' or value['contract'] != CONTRACT
            or value['model_sha256'] != PINNED_SHA
            or type(value['runtime']) is not str or not 1 <= len(value['runtime']) <= 80
            or any(type(value[k]) is not int or not 1 <= value[k] <= 512 for k in ('width','height'))
            or value['width'] * value['height'] > LIMIT):
        raise ValueError('自动前景模型来源回执无效；不能用通用语义或客户端蒙版代替')
    check_source(value['source'])
    _digest(value['input_sha256']); _digest(value['alpha_sha256'])
    return deepcopy(value)


def dependency_stamp():
    """Verify actual current model bytes, not only a manifest or cached path."""
    from .face import model_search_dirs, SELFIE_MULTICLASS_MODEL
    paths = [Path(folder) / SELFIE_MULTICLASS_MODEL for folder in model_search_dirs(None)]
    path = next((p for p in paths if p.is_file()), None)
    if path is None:
        raise ValueError('缺少已许可的六类模型；不会下载或回退到 SAM / 占位蒙版')
    with path.open('rb') as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PINNED_SHA:
        raise ValueError('自动前景模型字节不符合已核对的固定许可版本')
    return digest, importlib.metadata.version('mediapipe')


def channel(obj):
    return 'automatic_foreground_' + hashlib.sha256(obj['id'].encode()).hexdigest()[:24]


def _result(value, source):
    if type(value) is not dict or set(value) != {'binding', 'alpha_u8'}:
        raise ValueError('自动前景工作进程输出无效')
    binding = check_binding(value['binding'])
    if binding['source'] != source:
        raise ValueError('自动前景不属于当前源图')
    encoded = value['alpha_u8']
    if type(encoded) is not str or len(encoded) > 4 * LIMIT:
        raise ValueError('自动前景输出超过传输预算')
    raw = base64.b64decode(encoded, validate=True)
    if (len(raw) != binding['width'] * binding['height']
            or hashlib.sha256(raw).hexdigest() != binding['alpha_sha256']):
        raise ValueError('自动前景实际 alpha 与回执不一致')
    alpha = np.frombuffer(raw, np.uint8).reshape(binding['height'], binding['width'])
    return binding, np.ascontiguousarray(alpha, dtype=np.float32) / 255.


def generate(path, source, cancelled=lambda: False):
    """Synchronous owner call with one disposable, killable offline worker."""
    from .prompted_mask_job import PromptedJob
    from .cpu_memory_budget import available_estimate
    from .local_mask_state import source_digest
    source = check_source(source)
    if type(path) is not str or not path or len(path) > 32768:
        raise ValueError('自动前景目前只支持绑定的原照片，不支持派生源图')
    if available_estimate() < source['width'] * source['height'] * 32 + 2 * 1024**3:
        raise ValueError('完整源图自动前景内存预算不足')
    if cancelled():
        raise InterruptedError('自动前景已取消')
    stamp = dependency_stamp()
    # Reuse only existing bounded process lifecycle/poll/kill machinery, never
    # its prompted producer or proof. The worker and result schema are distinct.
    job = PromptedJob.__new__(PromptedJob)
    job.directory = tempfile.TemporaryDirectory(prefix='lumaretouch-automatic-foreground-')
    job.root = Path(job.directory.name)
    job.process = None
    job.state, job.result, job.error = 'running', None, None
    job.started = time.monotonic()
    try:
        raw = json.dumps({'path':path, 'source':source}, allow_nan=False)
        if len(raw.encode()) > 65536:
            raise ValueError('自动前景请求超过预算')
        (job.root / 'request.json').write_text(raw)
        job.process = subprocess.Popen([sys.executable, '-m', 'lumaretouch_engine.automatic_foreground_worker',
            '--directory', str(job.root), '--parent-pid', str(os.getpid())],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, start_new_session=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'})
        while job.poll() == 'running':
            if cancelled():
                raise InterruptedError('自动前景已取消')
            time.sleep(.05)
        if job.state != 'ready':
            raise ValueError(job.error or '自动前景模型未产生可用结果')
        binding, alpha = _result(job.result, source)
        if cancelled():
            raise InterruptedError('自动前景已取消')
        if (dependency_stamp() != stamp or (binding['model_sha256'], binding['runtime']) != stamp
                or source_digest(path) != source['sha256']):
            raise ValueError('自动前景准备期间模型、运行库或源图已变化')
        return binding, alpha
    finally:
        job.cancel()


def fields(stack, source, path, shape, *, force=False, cancelled=lambda: False,
           source_input=None, source_pixels=None, **unused):
    objects = [o for o in stack['objects'] if o['enabled'] and o['kind'] == 'automatic_foreground']
    if not objects:
        return {}
    if source_input is not None or source_pixels is not None or path is None:
        raise ValueError('自动前景目前仅支持原照片；派生图不能借用原照片的前景')
    if len(objects) > 8:
        raise ValueError('自动前景最多同时启用八个来源对象')
    from .local_mask_state import source_digest, file_stamp
    from PIL import Image
    source = check_source(source)
    h, w = shape
    if min(h, w) < 1 or h * w > 64_000_000:
        raise ValueError('自动前景输出超过 64MP 预算')
    stamp = dependency_stamp()
    if source_digest(path) != source['sha256']:
        raise ValueError('自动前景源图已变化')
    key = (json.dumps(source, sort_keys=True), file_stamp(path), stamp)
    with _LOCK:
        saved = None if force else _CACHE.get(key)
    if saved is None:
        saved = generate(path, source, cancelled)
        with _LOCK:
            _CACHE[key] = saved
            _CACHE.move_to_end(key)
            while len(_CACHE) > 8:
                _CACHE.popitem(last=False)
    binding, alpha = saved
    result = {}
    for obj in objects:
        if cancelled():
            raise InterruptedError('自动前景重放已取消')
        if check_binding(obj['selection']) != binding:
            raise ValueError('自动前景回执与实际源图 / 模型输出不符，请重新生成并独立审核')
        result[channel(obj)] = np.asarray(Image.fromarray(alpha).resize((w,h), Image.Resampling.BILINEAR), np.float32)
    if dependency_stamp() != stamp or source_digest(path) != source['sha256']:
        raise ValueError('自动前景重放期间源图或模型变化')
    return result
