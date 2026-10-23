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


def validate_candidates(result, fields):
    """Bind the initially displayed candidates to the actual decoded labels.

    The worker's visualization is white RGBA with the binary labels as alpha;
    neither another mask's overlay nor invented counts may authorize review.
    Later review also hashes the complete owned result to reject mutation.
    """
    import numpy as np
    from PIL import Image
    counts, overlays = result.get('counts'), result.get('candidate_overlays')
    if (type(counts) is not dict or set(counts) != set(S.REGIONS)
            or type(overlays) is not dict or set(overlays) != set(S.REGIONS)
            or set(fields) != set(S.REGIONS)):
        raise ValueError('自动选区显示候选缺少完整的区域和像素计数')
    prefix = 'data:image/png;base64,'
    limit = 4 * M.MAX_MASK_PIXELS + 65536
    for region in S.REGIONS:
        labels = fields[region][0]
        if type(counts[region]) is not int or counts[region] != int(np.count_nonzero(labels > 0)):
            raise ValueError('自动选区候选计数与实际类别字段不一致')
        encoded = overlays[region]
        if (type(encoded) is not str or not encoded.startswith(prefix)
                or len(encoded) > len(prefix) + 4 * ((limit + 2) // 3)):
            raise ValueError('自动选区候选覆盖图格式无效或超过预算')
        raw = base64.b64decode(encoded[len(prefix):], validate=True)
        if len(raw) > limit:
            raise ValueError('自动选区候选覆盖图超过预算')
        with Image.open(io.BytesIO(raw)) as image:
            if (image.format != 'PNG' or image.mode != 'RGBA'
                    or list(image.size) != result['input_size'] or getattr(image, 'n_frames', 1) != 1):
                raise ValueError('自动选区候选覆盖图格式或尺寸不一致')
            rgba = np.asarray(image)
            if not np.all(rgba[..., :3] == 255) or not np.array_equal(rgba[..., 3], labels):
                raise ValueError('自动选区显示覆盖图与实际类别字段不一致')
    return fields


def validate_input(descriptor, immutable_input):
    """Prove a canonical packet against retained intent without inference.

    This is also required on cache hits. A cache cannot turn a display proxy,
    an original-file request, or another effective source into reviewed input.
    """
    from . import immutable_input as I
    descriptor = S.check(descriptor)
    if descriptor is None or descriptor['model'] != M.identity():
        raise ValueError('自动选区来自不同固定实现；请重新生成并审核，或移除自动初选后使用手工标记')
    packet = I.check(immutable_input, descriptor['source'])
    if any(packet[key] != descriptor[key] for key in ('input_sha256', 'input_size')):
        raise ValueError('自动选区规范推理输入与已审核来源不一致')
    return packet


def remember(descriptor, result, *, immutable_input=None):
    descriptor = S.check(descriptor)
    if (descriptor is None or descriptor['model'] != M.identity()
            or S.accept(result, result['source'], descriptor['regions']) != descriptor):
        raise ValueError('自动选区结果与已审核来源不一致')
    packet_proof = None
    if immutable_input is not None:
        from . import immutable_input as I
        packet = validate_input(descriptor, immutable_input)
        I.validate_result(packet, result)
        packet_proof = I.metadata(packet)
    elif result.get('_immutable_input') is not None:
        raise ValueError('不可变来源自动选区缺少规范推理输入证明')
    fields = validate_candidates(result, decode_fields(result))
    key = json.dumps(descriptor, sort_keys=True)
    with _LOCK:
        _CACHE[key] = (fields, M.installation_stamp(), packet_proof)
        _CACHE.move_to_end(key)
        while len(_CACHE) > 2:
            _CACHE.popitem(last=False)
    return fields


def resolve(descriptor, path, *, immutable_input=None, force=False, cancelled=lambda: False):
    from .job import SemanticJob
    descriptor = S.check(descriptor)
    if descriptor is None or descriptor['model'] != M.identity():
        raise ValueError('自动选区来自不同固定实现；请重新生成并审核，或移除自动初选后使用手工标记')
    packet = packet_proof = None
    if immutable_input is not None:
        from . import immutable_input as I
        if path is not None:
            raise ValueError('不可变来源自动选区不能同时携带原照片路径')
        packet = validate_input(descriptor, immutable_input)
        packet_proof = I.metadata(packet)
    else:
        from ..local_mask_state import file_stamp, source_digest
        if path is None:
            raise ValueError('自动选区缺少源照片路径或规范推理输入')
        before = file_stamp(path)
        if source_digest(path) != descriptor['source']['sha256'] or file_stamp(path) != before:
            raise ValueError('自动选区的源照片已变化')

    def verify_input():
        if cancelled():
            raise InterruptedError('自动选区解析已取消')
        if descriptor['model'] != M.identity():
            raise ValueError('自动选区固定实现已变化；请重新生成并审核')
        if packet is not None:
            if validate_input(descriptor, immutable_input) != packet:
                raise ValueError('自动选区解析期间规范推理输入变化')
        elif file_stamp(path) != before:
            raise ValueError('自动选区解析期间源照片变化')

    verify_input()
    # A cached proposal must not hide removal of its required installation.
    if not (M.directory() / 'receipt.json').is_file():
        raise ValueError('自动选区模型已缺失；请重新安装或明确移除该自动选区')
    key = json.dumps(descriptor, sort_keys=True)
    with _LOCK:
        cached = _CACHE.get(key)
    if cached is not None and not force:
        fields, stamp, cached_proof = cached
        if cached_proof != packet_proof:
            raise ValueError('已缓存自动选区的规范输入来源不一致；请重新生成并审核')
        if set(fields) != set(S.REGIONS):
            raise ValueError('已缓存自动选区缺少完整区域')
        expected_shape = tuple(reversed(descriptor['input_size']))
        for region, (labels, support) in fields.items():
            if (labels.shape != expected_shape or support.shape != expected_shape
                    or str(labels.dtype) != 'uint8' or str(support.dtype) != 'uint8'
                    or not ((labels == 0) | (labels == 255)).all()
                    or hashlib.sha256(labels.tobytes() + support.tobytes()).hexdigest()
                    != descriptor['fields_sha256'][region]):
                raise ValueError('已缓存自动选区字段与审核结果不一致')
        if stamp != M.installation_stamp():
            M.verify()
            with _LOCK:
                _CACHE[key] = (fields, M.installation_stamp(), packet_proof)
        verify_input()
        return fields
    job = (SemanticJob(path, descriptor['source'], descriptor['device']) if packet is None else
           SemanticJob(None, descriptor['source'], descriptor['device'], immutable_input=packet))
    try:
        while job.poll() == 'running':
            verify_input()
            time.sleep(.03)
        if job.state != 'ready':
            raise ValueError(job.error or '自动选区解析未完成')
        verify_input()
        # Exact input/runtime/result identity is required on strict replay.
        # A changed numerical result is visible and requires a fresh review.
        fields = remember(descriptor, job.result, immutable_input=packet)
        verify_input()
        return fields
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
