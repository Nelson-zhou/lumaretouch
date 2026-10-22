"""Honest reusable source planes from the existing six-class portrait model.

This module is not an object detector, promptable segmenter or person-instance
selector. Every plane covers the whole photograph. A face landmark selection
does not change its scope. The model's ``others`` class is deliberately neither
called a person nor silently merged into background.
"""
from __future__ import annotations

import numpy as np

from .semantic_masks import skin_from_multiclass, skin_edit_weight


# Stable source IDs are retained in local-mask recipe objects. Display labels
# explicitly distinguish portrait-category segmentation from generic subjects.
SOURCE_LABELS = {
    'skin': '全部皮肤（人像模型）',
    'face_skin': '全部面部皮肤（人像模型）',
    'body_skin': '全部身体皮肤（人像模型）',
    'hair': '全部头发（人像模型）',
    'clothes': '全部衣物（人像模型）',
    'background': '人像背景（六类模型）',
    'portrait_parts': '人像已知类别合并（头发、皮肤、衣物）',
}

CLASS_CHANNELS = {'background': 0, 'hair': 1, 'body_skin': 2,
                  'face_skin': 3, 'clothes': 4}


def probability_sources(confidence_masks):
    """Validate once and copy runtime-owned probabilities into named planes.

    Return probabilities, not edit weights. The caller must first resize to its
    actual source-domain shape, then call ``edit_sources``. Summing probabilities
    before the confidence margin preserves the existing skin behaviour; summing
    already-thresholded class masks would incorrectly discard ambiguous skin.
    No outputs or fallbacks are produced for malformed/wrong-model tensors.
    """
    confidence_masks = list(confidence_masks)
    skin = skin_from_multiclass(confidence_masks)
    result = {'skin': skin}
    for name, index in CLASS_CHANNELS.items():
        value = np.asarray(confidence_masks[index], dtype=np.float32)
        if value.ndim == 3:
            value = value[..., 0]
        # copy=True is intentional: np.ascontiguousarray may alias model buffers.
        result[name] = np.array(np.clip(value, 0, 1), dtype=np.float32,
                                order='C', copy=True)
    # These four known portrait classes are not a complete person silhouette:
    # accessories/other objects can belong to class 5. Name that limitation.
    result['portrait_parts'] = np.ascontiguousarray(np.clip(
        result['hair'] + skin + result['clothes'], 0, 1))
    return result


def edit_sources(probabilities):
    """Apply the existing conservative confidence policy after any resizing.

    Missing planes stay missing, never all-zero/all-one substitutes. An empty
    but valid plane is different: it truthfully selects no matching pixels.
    """
    if not isinstance(probabilities, dict):
        raise ValueError('Semantic source probabilities require named planes')
    unknown = set(probabilities) - set(SOURCE_LABELS)
    if unknown:
        raise ValueError('Unknown portrait semantic source')
    result = {}
    shape = None
    for name, value in probabilities.items():
        value = np.asarray(value, dtype=np.float32)
        if value.ndim != 2 or not value.size:
            raise ValueError('Semantic source requires a nonempty two-dimensional plane')
        if shape is not None and value.shape != shape:
            raise ValueError('Semantic source planes must have matching dimensions')
        shape = value.shape
        result[name] = skin_edit_weight(value)
    return result
