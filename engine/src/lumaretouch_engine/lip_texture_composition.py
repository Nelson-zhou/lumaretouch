# SPDX-License-Identifier: GPL-3.0-or-later
"""Lip-furrow source delta feasibility, not a second texture algorithm."""
from . import people_source_vector as V


def apply_np(pixels, delta):
    return V.apply_np(pixels, delta, label='Lip texture')


def apply_t(pixels, delta):
    return V.apply_t(pixels, delta, label='Lip texture')
