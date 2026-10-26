"""Adapt prompted operands into transient fields for the one Rust compositor."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import base64
import io
import json
import threading
import time
import numpy as np
from PIL import Image
from .prompted_mask_source import check_binding

_CACHE = OrderedDict()
_LOCK = threading.Lock()
MAX_PROMPTED = 8


def _decode_field(encoded):
    data = base64.b64decode(encoded, validate=True)
    if len(data) > 4*1024**2: raise ValueError('Prompted candidate exceeds field budget')
    with Image.open(io.BytesIO(data)) as image:
        if image.mode != 'L' or max(image.size) > 2048:
            raise ValueError('Invalid worker prompted field')
        mask = np.asarray(image, np.uint8).copy()//255
    return mask


def seed(binding, source_binding, path, encoded, device, *, source_input=None):
    """Use the exact worker-produced field at Apply, not its displayed thumbnail."""
    from .local_mask_state import file_stamp
    mask = _decode_field(encoded)
    input_stamp=_input_stamp(path,source_binding,source_input)
    if source_input is not None and list(reversed(mask.shape))!=[source_input['descriptor']['width'],source_input['descriptor']['height']]:
        raise ValueError('Prompted field extent differs from immutable input')
    if source_input is not None and binding['input_sha256']!=source_input['descriptor']['input_sha256']:
        raise ValueError('Prompted selection differs from the owned immutable input')
    key = (json.dumps(check_binding(binding), sort_keys=True), json.dumps(source_binding, sort_keys=True),
           input_stamp, dependency_stamp(), device)
    with _LOCK:
        _CACHE[key] = mask
        _CACHE.move_to_end(key)
        while len(_CACHE) > 16: _CACHE.popitem(last=False)


def channel(obj):
    # Never alias a MediaPipe class or depend on user-supplied channel text.
    return 'prompted_' + hashlib.sha256(obj['id'].encode()).hexdigest()[:32]


def active(stack):
    return [obj for obj in stack['objects'] if obj['enabled'] and obj['kind'] == 'prompted']


def lower(stack):
    result = deepcopy(stack)
    for obj in result['objects']:
        if obj['kind'] == 'automatic_foreground':
            from .automatic_foreground import channel as automatic_channel
            name = automatic_channel(obj)
            obj.pop('selection')
            obj.update(kind='semantic', channel=name)
        if obj['kind'] == 'prompted':
            obj.pop('selection')
            obj.update(kind='semantic', channel=channel(obj))
    return result


def dependency_stamp():
    from .prompted_model_install import model_root, installed_runtime_identity
    from .prompted_model_manifest import CHECKPOINT_FILENAME
    from .local_mask_state import file_stamp
    # Verify installed code identity, never claim manifest metadata is loaded code.
    identity = installed_runtime_identity()
    return (json.dumps(identity, sort_keys=True), file_stamp(model_root()/CHECKPOINT_FILENAME))


def _input_stamp(path,source,packet):
    if packet is None:
        from .local_mask_state import file_stamp
        if not path:raise ValueError('Original prompted replay requires its bound source path')
        return file_stamp(path)
    if path is not None:raise ValueError('Derived prompted replay cannot read original-file inputs')
    from .creative_derived_prompted import cache_identity
    return cache_identity(packet,source)


def fields(stack, source_binding, path, shape, *, device='cpu', force=False, cancelled=lambda: False, source_input=None, source_pixels=None):
    """Canonical decode is independent of export's chosen output bitdepth.

    Only reduced model fields are cached. Explicit export/inspection calls use
    force=True and regenerate every enabled operand before delivering pixels.
    """
    from .automatic_foreground import fields as automatic_fields
    automatic = automatic_fields(stack,source_binding,path,shape,force=force,cancelled=cancelled,
                                 source_input=source_input,source_pixels=source_pixels)
    objects = active(stack)
    if not objects: return automatic
    if source_input is not None and source_pixels is not None:raise ValueError('Choose one owned prompted input')
    if source_pixels is not None:
        if path is not None:raise ValueError('Derived float prompted replay cannot read original path')
        from .creative_derived_prompted import from_pixels
        source_input=from_pixels(source_binding,source_pixels)
    input_stamp=_input_stamp(path,source_binding,source_input)
    if len(objects) > MAX_PROMPTED:
        raise ValueError('At most eight active prompted objects fit this inference budget')
    h, w = shape
    if min(h, w) < 1 or h*w > 64_000_000:
        raise ValueError('Prompted output exceeds 64 MP raster budget')
    from .local_mask_state import file_stamp
    stamp = dependency_stamp()
    keys = [(json.dumps(check_binding(obj['selection']), sort_keys=True),
             json.dumps(source_binding, sort_keys=True), input_stamp, stamp, obj['selection']['device']) for obj in objects]
    with _LOCK:
        missing = [i for i, key in enumerate(keys) if force or key not in _CACHE]
        if missing:
            from .prompted_mask_job import PromptedJob
            for i in missing:
                if cancelled(): raise InterruptedError('Prompted mask recomputation cancelled')
                obj = objects[i]
                binding = check_binding(obj['selection'])
                if source_input is None:
                    job = PromptedJob(path, source_binding, binding['prompts'], binding['device'])
                else:
                    if binding['input_sha256']!=source_input['descriptor']['input_sha256']:
                        raise ValueError('Retained prompted intent belongs to another immutable model input')
                    job = PromptedJob(None,source_binding,binding['prompts'],binding['device'],source_input=source_input)
                try:
                    while job.poll() == 'running':
                        if cancelled(): raise InterruptedError('Prompted mask recomputation cancelled')
                        time.sleep(.05)
                    if job.state != 'ready': raise ValueError(job.error or 'Prompted source is unavailable')
                    result = job.result
                    from .creative_derived_prompted import verify_result
                    verify_result(result,source_binding,source_input)
                    if (result['model'] != binding['model'] or result['input_sha256'] != binding['input_sha256']
                            or result['prompts'] != binding['prompts']):
                        raise ValueError('Prompted model or immutable input changed; selection is suspended')
                    if dependency_stamp()!=stamp:raise ValueError('Prompted dependency changed during recomputation')
                    mask = _decode_field(result['_mask_fields'][binding['candidate']])
                    if list(reversed(mask.shape))!=result['inference_size']:raise ValueError('Prompted field extent differs from actual input')
                finally:
                    job.cancel()
                _CACHE[keys[i]] = mask
                _CACHE.move_to_end(keys[i])
        result = dict(automatic)
        for obj, key in zip(objects, keys):
            mask = _CACHE[key]
            result[channel(obj)] = np.asarray(Image.fromarray(mask*255).resize((w, h), Image.Resampling.BILINEAR), np.float32)/255.
        while len(_CACHE) > 16: _CACHE.popitem(last=False)
        return result
