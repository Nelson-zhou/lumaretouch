"""Local, explicitly prompted SAM image selection. Never downloads or edits photos.

This source is not a semantic classifier. Its pixels are disposable; retain the
validated prompts, candidate and actual loaded model/input identities in the
existing local-mask object stack. Missing/mismatched dependencies are errors,
including when the operand subtracts from another mask.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import math
import re
import threading

import numpy as np
from PIL import Image

CONTRACT = 'sam2.1-tiny-points-box-rgb8-longedge2048-fp32-v1'
MAX_POINTS = 64
MAX_PIXELS = 64_000_000
MAX_EDGE = 2048
_LOCK = threading.Lock()


class PromptedUnavailable(ValueError):
    pass


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Prompted selection requires a SHA256 identity')
    return value


def _unit(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Prompt coordinates must be finite normalized source coordinates')
    return float(value)


def check_prompts(value):
    if type(value) is not dict or set(value) != {'points', 'box'}:
        raise ValueError('Prompted selection needs points and an optional box')
    points = value['points']
    if type(points) is not list or len(points) > MAX_POINTS:
        raise ValueError('Prompted selection supports at most 64 clicks')
    checked = []
    for point in points:
        if (type(point) is not dict or set(point) != {'x', 'y', 'label'}
                or type(point['label']) is not int or point['label'] not in (0, 1)):
            raise ValueError('Each click needs x, y and foreground/background label 1/0')
        checked.append({'x': _unit(point['x']), 'y': _unit(point['y']), 'label': point['label']})
    box = value['box']
    if box is not None:
        if type(box) is not list or len(box) != 4:
            raise ValueError('Prompt box must have four XYXY coordinates')
        box = [_unit(v) for v in box]
        if box[0] >= box[2] or box[1] >= box[3]:
            raise ValueError('Prompt box must have positive width and height')
    if box is None and not any(p['label'] == 1 for p in checked):
        raise ValueError('Add a foreground click or a box before requesting selection')
    return {'points': checked, 'box': box}


def check_binding(value):
    """Validate retained intent without importing Torch or requiring installation."""
    if type(value) is not dict or set(value) != {'prompts', 'candidate', 'model', 'input_sha256', 'device'}:
        raise ValueError('Invalid prompted mask source binding')
    model = value['model']
    if type(model) is not dict or set(model) != {'id', 'checkpoint_sha256', 'config_sha256', 'code_revision', 'contract'}:
        raise ValueError('Invalid prompted model identity')
    if (type(model['id']) is not str or len(model['id']) > 80
            or type(model['code_revision']) is not str or not re.fullmatch('[0-9a-f]{40}', model['code_revision'])
            or type(model['contract']) is not str or len(model['contract']) > 128):
        raise ValueError('Invalid prompted model contract')
    _digest(model['checkpoint_sha256']); _digest(model['config_sha256'])
    if type(value['candidate']) is not int or not 0 <= value['candidate'] < 3:
        raise ValueError('Prompted candidate must be 0, 1 or 2')
    if value['device'] not in ('cpu', 'cuda'):
        raise ValueError('Prompted selection must retain its explicit inference device')
    return {'prompts': check_prompts(value['prompts']), 'candidate': value['candidate'],
            'model': deepcopy(model), 'input_sha256': _digest(value['input_sha256']), 'device': value['device']}


def inference_image(source):
    """Make a bounded SAM-only RGB8 copy; never replace the export source."""
    if (not isinstance(source, np.ndarray) or source.ndim != 3 or source.shape[2] != 3
            or min(source.shape[:2]) < 1 or source.shape[0]*source.shape[1] > MAX_PIXELS
            or source.dtype not in (np.dtype('uint8'), np.dtype('uint16'))):
        raise ValueError('Prompted selection needs full-source working-sRGB RGB8/RGB16 within 64 MP')
    if source.dtype == np.uint16:
        # Bound conversion scratch memory, even on a 64 MP photograph.
        rgb = np.empty(source.shape, np.uint8)
        for y in range(0, source.shape[0], 128):
            rgb[y:y+128] = ((source[y:y+128].astype(np.uint32)+128)//257).astype(np.uint8)
    else:
        rgb = np.array(source, copy=True, order='C')
    h, w = rgb.shape[:2]
    if max(h, w) > MAX_EDGE:
        scale = MAX_EDGE/max(h, w)
        rgb = np.asarray(Image.fromarray(rgb).resize((max(1, round(w*scale)), max(1, round(h*scale))),
                                                    Image.Resampling.LANCZOS)).copy()
    digest = hashlib.sha256()
    digest.update(f'{CONTRACT}:{rgb.shape[1]}:{rgb.shape[0]}:'.encode())
    digest.update(memoryview(rgb))
    rgb.flags.writeable = False
    return rgb, digest.hexdigest()


def decode_source(path, binding, *, device='cpu'):
    """Same true-bit-depth input/ICC policy as export, with immutable-file guard."""
    from .local_mask_state import file_stamp, source_digest
    from .decode import load_full, is_raw, _source_bits
    if type(binding) is not dict or set(binding) != {'sha256', 'width', 'height'}:
        raise ValueError('Prompted selection source binding is missing')
    if any(type(binding[k]) is not int or binding[k] < 1 for k in ('width', 'height')):
        raise ValueError('Invalid prompted source dimensions')
    if binding['width']*binding['height'] > MAX_PIXELS:
        raise ValueError('Prompted source exceeds the 64 MP budget')
    stamp = file_stamp(path)
    if stamp[2] > 4*1024**3:
        raise ValueError('Prompted source file exceeds the 4 GiB input budget')
    if source_digest(path) != _digest(binding['sha256']):
        raise PromptedUnavailable('Source content changed; reopen the photograph')
    if is_raw(path):
        bits = 16
    else:
        with Image.open(path) as image:
            bits = 16 if _source_bits(image) > 8 else 8
    decoded = load_full(path, max_px=MAX_PIXELS, device=device, want_bits=bits)
    if file_stamp(path) != stamp or source_digest(path) != binding['sha256']:
        raise PromptedUnavailable('Source changed during prompted-selection decoding')
    source = decoded.rgb
    if (source.shape[:2] != (binding['height'], binding['width']) or decoded.draft_used
            or (decoded.raw or {}).get('used_preview')):
        raise PromptedUnavailable('Prompted input is not the bound full source')
    if source.dtype == np.uint16 and decoded.source_icc:
        from .color16 import convert_rgb16
        from .export import _srgb_bytes
        source = convert_rgb16(source, decoded.source_icc, _srgb_bytes())
    return source


class Predictor:
    """One explicitly selected device, verified immutable weights/config, FP32.

    Owners should run this in a cancellable child process. Calls cannot interrupt
    an in-flight Torch kernel; the job boundary kills the owned process on cancel.
    """
    def __init__(self, device='cpu'):
        from . import prompted_model_install as install
        from . import prompted_model_manifest as manifest
        install.activate_runtime()
        import torch
        from hydra.utils import instantiate
        from omegaconf import OmegaConf
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        if device not in ('cpu', 'cuda'):
            raise PromptedUnavailable('Select CPU or the engine CUDA/ROCm device explicitly')
        if device == 'cuda' and not torch.cuda.is_available():
            raise PromptedUnavailable('Selected GPU is unavailable; no silent CPU fallback')
        config = install.verified_config_bytes()
        checkpoint = install.verified_checkpoint_bytes()
        self.identity = {'id': manifest.MODEL_ID,
                         'checkpoint_sha256': hashlib.sha256(checkpoint).hexdigest(),
                         'config_sha256': hashlib.sha256(config).hexdigest(),
                         'code_revision': manifest.SOURCE_REVISION, 'contract': CONTRACT}
        # Instantiate from the SAME verified config bytes and load the SAME
        # verified checkpoint buffer. No hash-then-reopen race or HF downloader.
        cfg = OmegaConf.create(config.decode('utf-8'))
        OmegaConf.resolve(cfg)
        model = instantiate(cfg.model, _recursive_=True)
        state = torch.load(io.BytesIO(checkpoint), map_location='cpu', weights_only=True)
        model.load_state_dict(state['model'], strict=True)
        del state, checkpoint
        model = model.to(device=device, dtype=torch.float32).eval()
        self.predictor = SAM2ImagePredictor(model, max_hole_area=0., max_sprinkle_area=0.)
        self.torch = torch
        self.device = 'ROCm' if device == 'cuda' and torch.version.hip else ('CUDA' if device == 'cuda' else 'CPU')

    def predict(self, source, prompts, *, expected=None, cancelled=lambda: False):
        prompts = check_prompts(prompts)
        if cancelled(): raise InterruptedError('Prompted selection cancelled')
        image, digest = inference_image(source)
        if expected is not None:
            expected = check_binding(expected)
            if expected['model'] != self.identity or expected['input_sha256'] != digest or expected['prompts'] != prompts:
                raise PromptedUnavailable('Prompted model or immutable input changed; selection is suspended')
        h, w = image.shape[:2]
        points = prompts['points']
        coords = np.array([[min(w-1, p['x']*w), min(h-1, p['y']*h)] for p in points], np.float32) if points else None
        labels = np.array([p['label'] for p in points], np.int32) if points else None
        box = np.array(prompts['box'], np.float32)*[w, h, w, h] if prompts['box'] is not None else None
        with _LOCK, self.torch.inference_mode():
            if cancelled(): raise InterruptedError('Prompted selection cancelled')
            self.predictor.set_image(image.copy())
            if cancelled(): raise InterruptedError('Prompted selection cancelled')
            masks, scores, _ = self.predictor.predict(point_coords=coords, point_labels=labels,
                box=box, multimask_output=True, return_logits=False, normalize_coords=True)
            self.predictor.reset_predictor()
        if cancelled(): raise InterruptedError('Prompted selection cancelled')
        if (masks.shape != (3, h, w) or np.asarray(scores).shape != (3,)
                or not np.isfinite(scores).all()):
            raise PromptedUnavailable('SAM returned an invalid candidate result')
        return {'masks': masks.astype(np.uint8), 'scores': [float(x) for x in scores],
                'model': deepcopy(self.identity), 'input_sha256': digest,
                'device': self.device, 'inference_size': [w, h]}


def resolve(source, binding, *, device='cpu', cancelled=lambda: False):
    """Recompute the accepted candidate; never silently skip an enabled operand."""
    binding = check_binding(binding)
    result = Predictor(binding['device']).predict(source, binding['prompts'], expected=binding, cancelled=cancelled)
    mask = result['masks'][binding['candidate']]
    h, w = source.shape[:2]
    # Model detail is bounded; this is resampling, not full-resolution inference.
    return np.asarray(Image.fromarray(mask*255).resize((w, h), Image.Resampling.BILINEAR), np.float32)/255.
