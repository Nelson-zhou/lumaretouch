# SPDX-License-Identifier: AGPL-3.0-only
# Original work: Chris Cork, RapidRetouch, pinned in the adjacent NOTICE.
# Extracted for LumaRetouch on2026-10-22; imports are lazy for optional runtimes.
from ...optional_dependencies import optional_module
import numpy as np
cv2 = optional_module('cv2')

def blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur whose cost doesn't grow with sigma.

    Wide blurs are done on a shrunken copy and scaled back up — the result is a
    smooth field, so nothing visible is lost, and it's orders of magnitude faster
    than a direct kernel hundreds of pixels wide.
    """
    if sigma <= 8:
        return cv2.GaussianBlur(img, (0, 0), sigma)
    h, w = img.shape[:2]
    factor = sigma / 4
    small = cv2.resize(
        img,
        (max(1, round(w / factor)), max(1, round(h / factor))),
        interpolation=cv2.INTER_AREA,
    )
    small = cv2.GaussianBlur(small, (0, 0), 4)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def masked_blur(img: np.ndarray, weight: np.ndarray, sigma: float) -> np.ndarray:
    """Normalised convolution: blur only the weighted pixels, filling gaps from them.

    Where no weighted pixel is within reach of ``sigma``, a much wider pass fills
    in so the field is defined everywhere.
    """
    single = img.ndim == 2
    if single:
        img = img[..., None]
    out = np.zeros_like(img)
    remaining = np.ones(img.shape[:2] + (1,), np.float32)  # share not yet filled
    for i, s in enumerate((sigma, sigma * 4, sigma * 16, sigma * 64)):
        num = blur(img * weight[..., None], s)
        if num.ndim == 2:  # OpenCV drops a single channel's axis
            num = num[..., None]
        den = blur(weight, s)[..., None]
        est = num / np.maximum(den, 1e-6)
        conf = np.clip(den / 0.05, 0, 1) if i < 3 else np.ones_like(den)
        out += remaining * conf * est
        remaining *= 1 - conf
        if remaining.max() <= 0:
            break
    return out[..., 0] if single else out

