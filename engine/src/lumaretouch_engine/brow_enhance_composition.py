# SPDX-License-Identifier: GPL-3.0-or-later
"""Stable brow composition API; unchanged algebra in shared vector helper."""
from . import people_source_vector as V


def apply_np(pixels, delta):
    return V.apply_np(pixels, delta, label='Brow')


def apply_t(pixels, delta):
    return V.apply_t(pixels, delta, label='Brow')
