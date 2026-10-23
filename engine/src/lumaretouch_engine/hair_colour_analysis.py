"""Retain actual source semantic evidence, never rendered-canvas AI追色 masks."""
from copy import deepcopy
import hashlib
import numpy as np
from . import hair_colour_assets as A


def capture(precompute, binding):
    binding = A.source(binding)
    if precompute is None or precompute.backend != 'mediapipe' or precompute.semantic_model_sha256 != A.MODEL_SHA256:
        raise ValueError('Hair evidence needs the actual admitted six-class producer')
    value = precompute.masks.get('hair')
    if type(value) is not np.ndarray or value.ndim != 2 or not value.size or not np.isfinite(value).all() or np.any((value < 0) | (value > 1)):
        raise ValueError('Real source hair confidence coverage is unavailable')
    weight = np.array(value, dtype=np.float32, order='C', copy=True); weight.setflags(write=False)
    return {'domain': 'source-normalized', 'source': binding, 'model_sha256': precompute.semantic_model_sha256,
            'producer': 'mediapipe-six-class-confidence-gated-hair', 'weight': weight,
            'weight_sha256': hashlib.sha256(weight.tobytes()).hexdigest()}


def check(value, binding):
    if type(value) is not dict or set(value) != {'domain', 'source', 'model_sha256', 'producer', 'weight', 'weight_sha256'}:
        raise ValueError('Hair semantic evidence contract is missing')
    if value['domain'] != 'source-normalized' or value['source'] != A.source(binding) or value['model_sha256'] != A.MODEL_SHA256 or value['producer'] != 'mediapipe-six-class-confidence-gated-hair':
        raise ValueError('Hair semantic field belongs to a different source/domain/model')
    weight = value['weight']
    if type(weight) is not np.ndarray or weight.dtype != np.float32 or weight.ndim != 2 or not weight.size or weight.size > 64_000_000 or not np.isfinite(weight).all() or np.any((weight < 0) | (weight > 1)):
        raise ValueError('Invalid measured hair coverage')
    if hashlib.sha256(np.ascontiguousarray(weight).tobytes()).hexdigest() != value['weight_sha256']:
        raise ValueError('Measured hair field changed after capture')
    return weight


def at_dimensions(value, binding, shape):
    weight = check(value, binding)
    if len(shape) != 2 or any(type(n) is not int or n < 1 for n in shape) or shape[0]*shape[1] > 64_000_000:
        raise ValueError('Hair source dimensions exceed admission')
    if weight.shape != tuple(shape):
        import cv2
        weight = cv2.resize(weight, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return np.array(weight, dtype=np.float32, order='C', copy=True)


def freeze(value):
    if value is None: return None
    check(value, value['source'])
    result = {key: deepcopy(item) for key, item in value.items() if key != 'weight'}
    result['weight'] = np.array(value['weight'], dtype=np.float32, order='C', copy=True)
    result['weight'].setflags(write=False)
    return result
