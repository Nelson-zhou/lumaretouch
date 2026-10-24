# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared direction-preserving headroom composition, not per-channel clipping."""
from . import people_source_vector as V

def apply_np(pixels, delta):
    return V.apply_np(pixels, delta, label='Existing eye makeup')

def apply_t(pixels, delta):
    return V.apply_t(pixels, delta, label='Existing eye makeup')
