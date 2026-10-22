# SPDX-License-Identifier: AGPL-3.0-only
# Copyright Chris Cork. Adapted for LumaRetouch, 2026-10-22. See NOTICE.
"""sRGB <-> linear light, for edits that should behave like a change of light."""

from __future__ import annotations

import numpy as np



def _to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _to_srgb(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return _to_linear(np.asarray(c))


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    return _to_srgb(np.asarray(c))
