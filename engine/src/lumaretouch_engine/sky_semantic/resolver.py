"""Resolve a reviewed semantic base, then exact Rust add/subtract corrections."""
from collections import OrderedDict
from copy import deepcopy
import base64
import hashlib
import io
import json
import threading
import time
from . import manifest as M, state as S

_CACHE = OrderedDict()
_LOCK = threading.Lock()


def decode_fields(result):
    import numpy as np
    from PIL import Image
    size = result['input_size']
    if size[0] * size[1] > M.MAX_MASK_PIXELS or set(result['_fields']) != set(S.REGIONS):
        raise ValueError('自动选区字段超出固定预算')
    out = {}
    for key in S.REGIONS:
        fields = []
        for field in ('labels', 'support'):
            raw = base64.b64decode(result['_fields'][key][field], validate=True)
            if len(raw) > 2 * 1024**2:
                raise ValueError('自动选区字段超过传输预算')
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != 'PNG' or image.mode != 'L' or list(image.size) != size:
                    raise ValueError('自动选区字段格式或尺寸不一致')
                fields.append(np.asarray(image).copy())
        if not np.all((fields[0] == 0) | (fields[0] == 255)):
            raise ValueError('语义类别字段不是明确的类别选择')
        if hashlib.sha256(fields[0].tobytes() + fields[1].tobytes()).hexdigest() != result['fields_sha256'][key]:
            raise ValueError('自动选区字段校验失败')
        for field in fields:
            field.flags.writeable = False
        out[key] = tuple(fields)
    return out


def remember(descriptor, result):
    descriptor = S.check(descriptor)
    fields = decode_fields(result)
    for key in ('model', 'host', 'device', 'input_sha256', 'input_size', 'fields_sha256'):
        if descriptor[key] != result[key]:
            raise ValueError('自动选区结果与已审核来源不一致')
    key = json.dumps(descriptor, sort_keys=True)
    with _LOCK:
        _CACHE[key] = (fields, M.installation_stamp())
        _CACHE.move_to_end(key)
        while len(_CACHE) > 2:
            _CACHE.popitem(last=False)
    return fields


def resolve(descriptor, path, *, force=False, cancelled=lambda: False):
    from ..local_mask_state import file_stamp, source_digest
    from .job import SemanticJob
    descriptor = S.check(descriptor)
    if descriptor['model'] != M.identity():
        raise ValueError('自动选区来自不同固定实现；请重新生成并审核，或移除自动初选后使用手工标记')
    before = file_stamp(path)
    if source_digest(path) != descriptor['source']['sha256']:
        raise ValueError('自动选区的源照片已变化')
    # A cached proposal must not hide removal of its required installation.
    if not (M.directory() / 'receipt.json').is_file():
        raise ValueError('自动选区模型已缺失；请重新安装或明确移除该自动选区')
    key = json.dumps(descriptor, sort_keys=True)
    with _LOCK:
        cached = _CACHE.get(key)
    if cached is not None and not force:
        fields, stamp = cached
        if stamp != M.installation_stamp():
            M.verify()
            with _LOCK:
                _CACHE[key] = (fields, M.installation_stamp())
        return fields
    job = SemanticJob(path, descriptor['source'], descriptor['device'])
    try:
        while job.poll() == 'running':
            if cancelled():
                raise InterruptedError('自动选区解析已取消')
            time.sleep(.03)
        if job.state != 'ready':
            raise ValueError(job.error or '自动选区解析未完成')
        if file_stamp(path) != before:
            raise ValueError('自动选区解析期间源照片变化')
        # Exact input/runtime/result identity is required on strict replay.
        # A changed numerical result is visible and requires a fresh review.
        return remember(descriptor, job.result)
    finally:
        if job.state == 'running':
            job.cancel()


def raster_region(stack, shape, descriptor, fields, region):
    from .. import local_mask_recipe as L
    import numpy as np
    import cv2
    descriptor = S.check(descriptor)
    if descriptor is None or region not in descriptor['regions']:
        return L.raster(stack, shape)
    stack = deepcopy(L.check_stack(stack))
    labels, support = fields[region]
    base = ((labels > 0) & (support.astype(np.float32) / 255 >= descriptor['regions'][region])).astype(np.float32)
    if not np.any(base) or np.all(base):
        raise ValueError('该自动选区为空或覆盖全幅；请使用手工标记或重新审核')
    base = cv2.resize(base, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    channel = 'sky_semantic_' + region
    operand = {'id': 'sky_semantic_base', 'name': '已审核语义选区', 'enabled': True,
               'operation': 'add', 'kind': 'semantic', 'opacity': 1., 'feather': 0., 'channel': channel}
    if any(item['id'] == operand['id'] for item in stack['objects']):
        raise ValueError('画笔对象使用了保留的自动选区身份')
    # No lossy contour conversion or stroke truncation. The same LMR2 compositor
    # applies all existing corrections in order after the genuine semantic base.
    stack['objects'].insert(0, operand)
    return L.raster(stack, shape, semantic={channel: base})
