"""Decode the documented six-class MediaPipe confidence-mask contract.

Class order is fixed by Google's SelfieMulticlass model metadata, not guessed
from whichever number of channels a runtime happens to return. Probabilities
remain soft for antialiased boundaries. This is not a pixel-perfect guarantee.
"""
from __future__ import annotations
import numpy as np

CLASS_NAMES = ("background", "hair", "body_skin", "face_skin", "clothes", "others")


def skin_from_multiclass(confidence_masks):
    """Copy model-owned buffers and sum the two disjoint skin probabilities.

    Fail closed on an old person-only model or invalid confidence tensors.
    Do not normalize malformed outputs: that would conceal a logits/probability
    or wrong-model contract mismatch. The runtime must apply model activation.
    """
    if len(confidence_masks) != len(CLASS_NAMES):
        raise ValueError("skin segmentation requires exactly six semantic confidence masks")
    arrays = []
    for value in confidence_masks:
        a = np.asarray(value, dtype=np.float32)
        if a.ndim == 3 and a.shape[-1] == 1:
            a = a[..., 0]
        if a.ndim != 2 or not a.size:
            raise ValueError("semantic confidence mask must be a nonempty 2-D array")
        if not np.isfinite(a).all() or np.any(a < -1e-6) or np.any(a > 1 + 1e-6):
            raise ValueError("semantic confidence values must be finite probabilities")
        if arrays and a.shape != arrays[0].shape:
            raise ValueError("semantic confidence masks must have matching shapes")
        arrays.append(a)
    total = np.sum(arrays, axis=0)
    if not np.allclose(total, 1.0, atol=1e-4, rtol=0):
        raise ValueError("semantic confidence masks must sum to one, not raw logits")
    return np.ascontiguousarray(np.clip(arrays[2] + arrays[3], 0, 1))


def skin_edit_weight(probability):
    """Conservative, continuous binary-confidence margin for automatic editing.

    The disjoint skin classes are grouped first. A pixel only receives an
    automatic edit when skin is more likely than all non-skin classes combined.
    Unlike hard argmax this ramps continuously from zero at the decision boundary
    to full weight at confidence one. It cannot repair a confident model error.
    """
    p = np.asarray(probability, dtype=np.float32)
    if not np.isfinite(p).all() or np.any(p < 0) or np.any(p > 1):
        raise ValueError("skin probability must be finite and within [0,1]")
    return np.ascontiguousarray(np.maximum(2 * p - 1, 0))


def clothes_from_multiclass(confidence_masks):
    """Keep only the documented clothes class, after the same strict validation.

    A class must beat all other classes combined. No person-mask or skin inverse
    fallback is allowed: hair, arms and background are not clothes.
    """
    skin_from_multiclass(confidence_masks)
    value = np.asarray(confidence_masks[4], dtype=np.float32)
    if value.ndim == 3:
        value = value[..., 0]
    return np.ascontiguousarray(np.clip(value, 0, 1))
