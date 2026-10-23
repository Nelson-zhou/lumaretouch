"""Source-only spill evidence and current-pixel application for the ID stage.

The estimator consumes immutable, exact-dtype-normalized source RGB and reviewed
foreground coverage. Its correction is transported with the ID fields, then
applied to CURRENT edited RGB. It never replaces those pixels with source RGB.
Source HDR is rejected, without clipping. An edited HDR pixel is explicitly
neutral for spill correction; the existing ID compositor retains its own HDR
semantics. Confidence already contains user strength exactly once.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
import numpy as np


FIELD_KEYS = frozenset(('spill_delta', 'spill_confidence', 'spill_source'))
PROOF_KEYS = frozenset(('version', 'algorithm', 'estimator', 'encoding', 'source', 'shape',
                        'dtype', 'input_sha256', 'linear_sha256', 'reviewed_alpha_sha256'))


def active(value):
    from . import id_background_state as I, spill_removal_state as S
    return I.active(value) and S.active(I.spill_of(value))


def _hash(array, cancelled=lambda: False):
    digest = sha256()
    for row in array:
        if cancelled():
            raise InterruptedError('Spill-removal preparation cancelled')
        digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return digest.hexdigest()


def source_identity(pixels, source, *, full_source=False, cancelled=lambda: False):
    """Bind actual encoded pixels, not an object id, path or RGB8 surrogate."""
    from . import local_mask_state as M
    binding = M.check({'source': source, 'semantic_owner': None,
                       'recipe': M.empty()['recipe']})['source']
    if (binding is None or type(full_source) is not bool or type(pixels) is not np.ndarray
            or pixels.dtype not in (np.dtype('uint8'), np.dtype('uint16'), np.dtype('float32'))
            or pixels.ndim != 3 or pixels.shape[2] != 3 or min(pixels.shape[:2]) < 1
            or pixels.shape[0] > binding['height'] or pixels.shape[1] > binding['width']
            or full_source and pixels.shape[:2] != (binding['height'], binding['width'])):
        raise ValueError('Spill removal requires exact source-grid uint8/uint16/float32 encoded RGB')
    for y in range(0, len(pixels), 64):
        if cancelled():
            raise InterruptedError('Spill-removal source verification cancelled')
        block = pixels[y:y+64]
        if not np.isfinite(block).all() or pixels.dtype == np.float32 and (np.any(block < 0) or np.any(block > 1)):
            raise ValueError('Spill removal requires finite SDR source pixels; no implicit HDR clipping')
    return {'source': deepcopy(binding), 'shape': list(pixels.shape),
            'dtype': pixels.dtype.str, 'input_sha256': _hash(pixels, cancelled)}


def linear_source(pixels, *, cancelled=lambda: False):
    """Decode encoded sRGB at its actual dtype precision, with bounded scratch.

    Caller validates source_identity first. In particular uint16 never takes
    an RGB8 detour, and float32 is never divided by an inferred maximum.
    """
    if pixels.dtype not in (np.dtype('uint8'), np.dtype('uint16'), np.dtype('float32')):
        raise ValueError('Unsupported spill-removal source dtype')
    divisor = 255. if pixels.dtype == np.uint8 else 65535. if pixels.dtype == np.uint16 else 1.
    result = np.empty(pixels.shape, dtype=np.float32)
    for y in range(0, len(pixels), 64):
        if cancelled():
            raise InterruptedError('Spill-removal source decoding cancelled')
        block = pixels[y:y+64].astype(np.float32) / divisor
        if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
            raise ValueError('Spill removal cannot clip or reinterpret source radiance')
        result[y:y+64] = np.where(block <= .04045, block / 12.92,
                                  ((block + .055) / 1.055) ** 2.4)
    result.setflags(write=False)
    return result


def check_source_proof(proof, shape, source=None):
    if (type(shape) not in (tuple,list) or len(shape)!=2 or any(type(v) is not int or v<1 for v in shape)
            or type(proof) is not dict or set(proof) != PROOF_KEYS
            or type(proof['version']) is not int or proof['version'] != 1
            or proof['algorithm'] != 'lrt-spill-removal-v1' or proof['encoding'] != 'linear-srgb-d65'
            or proof['estimator'] != 'fixed-alpha-fb-edge-reflection-v1'
            or proof['shape'] != [*shape, 3]
            or proof['dtype'] not in (np.dtype('uint8').str, np.dtype('uint16').str, np.dtype('float32').str)
            or any(type(proof[k]) is not str or not re.fullmatch('[0-9a-f]{64}', proof[k])
                   for k in ('input_sha256', 'linear_sha256', 'reviewed_alpha_sha256'))):
        raise ValueError('Spill fields lack their exact source preparation evidence')
    from . import local_mask_state as M
    binding = M.check({'source': proof['source'], 'semantic_owner': None,
                       'recipe': M.empty()['recipe']})['source']
    if (binding is None or shape[0] > binding['height'] or shape[1] > binding['width']
            or source is not None and binding != source):
        raise ValueError('Spill fields belong to a different source extent')
    return json.dumps(proof, sort_keys=True, separators=(',', ':'), allow_nan=False)


def memory_estimate(shape, value):
    if not active(value):
        return 0
    from . import spill_removal_native as N
    # Estimator bound includes its source inputs, outputs and scratch. Reserve
    # the additional decoded source plus a possible manual coverage raster and
    # float conversion. The host separately reserves its ID/pipeline fields.
    h, w = shape
    return N.memory_estimate(shape) + 20 * h * w + 64 * max(1, w) * 48


def prepare(value, pixels, reviewed_alpha, *, full_source=False, render_scale=1.,
            cancelled=lambda: False):
    if not active(value):
        return {}
    from . import id_background_state as I, spill_removal_native as N
    from . import spill_removal_coverage as C
    spill = I.spill_of(value)
    before = source_identity(pixels, value['source'], full_source=full_source, cancelled=cancelled)
    if (type(reviewed_alpha) is not np.ndarray or reviewed_alpha.dtype != np.float32
            or reviewed_alpha.shape != pixels.shape[:2] or not np.isfinite(reviewed_alpha).all()
            or np.any(reviewed_alpha < 0) or np.any(reviewed_alpha > 1)):
        raise ValueError('Spill estimation requires the original reviewed source alpha')
    alpha_hash = _hash(reviewed_alpha, cancelled)
    linear = linear_source(pixels, cancelled=cancelled)
    linear_hash = _hash(linear, cancelled)
    fields = N.prepare(linear, reviewed_alpha, strength=spill['strength']/100.,
                       render_scale=render_scale, encoding='linear-srgb-d65', cancelled=cancelled)
    if (type(fields) is not dict or set(fields) != {'delta', 'confidence', 'encoding', 'render_scale', 'domain_shape', 'estimator'}
            or fields['encoding'] != 'linear-srgb-d65' or fields['render_scale'] != render_scale
            or fields['estimator'] != 'fixed-alpha-fb-edge-reflection-v1'
            or tuple(fields['domain_shape']) != pixels.shape[:2]):
        raise ValueError('Spill estimator returned an incompatible source-domain field contract')
    delta, confidence = fields['delta'], fields['confidence']
    for field, shape in ((delta, pixels.shape), (confidence, pixels.shape[:2])):
        if type(field) is not np.ndarray or field.dtype != np.float32 or field.shape != shape or not np.isfinite(field).all():
            raise ValueError('Spill estimator returned invalid full-domain fields')
    if np.any(confidence < 0) or np.any(confidence > 1):
        raise ValueError('Spill estimator confidence is not bounded coverage')
    if spill['coverage'] is not None:
        coverage = C.raster(spill['coverage'], pixels.shape[:2], source=value['source'],
                            full_source=full_source, cancelled=cancelled)
        # Manual vectors select WHERE an independently supported correction may
        # act. They never modify the matte, evidence, delta or user strength.
        confidence = confidence * coverage
    if (source_identity(pixels, value['source'], full_source=full_source, cancelled=cancelled) != before
            or _hash(reviewed_alpha, cancelled) != alpha_hash or _hash(linear, cancelled) != linear_hash):
        raise ValueError('Spill source or reviewed alpha changed during preparation')
    proof = {'version': 1, 'algorithm': spill['algorithm'], 'estimator': fields['estimator'], 'encoding': 'linear-srgb-d65',
             **before, 'linear_sha256': linear_hash, 'reviewed_alpha_sha256': alpha_hash}
    check_source_proof(proof, pixels.shape[:2], value['source'])
    delta.setflags(write=False)
    confidence.setflags(write=False)
    return {'spill_delta': delta, 'spill_confidence': confidence, 'spill_source': proof}


def apply_t(rgb, delta, confidence):
    """Line-limit a shared RGB correction vector; never channel-clip radiance.

    Mirrors spill_removal_native's common per-pixel k. Raw delta is luminance
    null; confidence/strength and the single k preserve that direction. The
    shrink only at a gamut boundary protects against final floating roundoff.
    No correction is attempted for any edited pixel outside finite SDR.
    """
    import torch
    if (rgb.ndim != 4 or rgb.shape[1] != 3 or delta.shape != rgb.shape
            or confidence.shape != (rgb.shape[0], 1, *rgb.shape[2:])):
        raise ValueError('Spill-removal current RGB and aligned fields disagree')
    if (not torch.isfinite(rgb).all() or not torch.isfinite(delta).all()
            or not torch.isfinite(confidence).all() or torch.any(confidence < 0) or torch.any(confidence > 1)):
        raise ValueError('Spill-removal current RGB/fields must be finite with bounded confidence')
    eligible = (rgb >= 0).all(dim=1, keepdim=True) & (rgb <= 1).all(dim=1, keepdim=True)
    linear = torch.where(rgb <= .04045, rgb / 12.92,
                         ((rgb + .055) / 1.055).clamp_min(0).pow(2.4))
    d = delta * confidence
    nonzero = d != 0
    denominator = torch.where(nonzero, d.abs(), torch.ones_like(d))
    bound = torch.where(d > 0, (1 - linear) / denominator,
                        torch.where(d < 0, linear / denominator, torch.ones_like(d)))
    k = bound.amin(dim=1, keepdim=True).clamp(0, 1)
    k = torch.where(k < 1, k * (1 - 2**-20), k)
    corrected = linear + d * k
    changed = eligible & (confidence > 0) & (k > 0) & (corrected != linear).any(dim=1, keepdim=True)
    encoded = torch.where(corrected <= .0031308, corrected * 12.92,
                          1.055 * corrected.clamp_min(0).pow(1/2.4) - .055)
    return torch.where(changed, encoded, rgb)
