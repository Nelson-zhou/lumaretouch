# SPDX-License-Identifier: GPL-3.0-or-later
"""Three explicit same-source manual roles using the existing Rust mask owner."""
from copy import deepcopy
import json
import numpy as np
from . import local_mask_recipe as M

ROLES = ('limb', 'target', 'protect')


def check_review(value):
    keys = {'version', 'domain', *ROLES, 'same_limb_confirmed', 'limb_kind'}
    if type(value) is not dict or set(value) != keys or type(value['version']) is not int or value['version'] != 1 or value['domain'] != 'source-normalized':
        raise ValueError('Hand tone requires three explicit source-normalized mask roles')
    if value['same_limb_confirmed'] is not True:
        raise ValueError('Confirm the same visible hand; protect nails, jewelry, tattoos and edges')
    if len(json.dumps(value, allow_nan=False, separators=(',', ':')).encode()) > 256 * 1024:
        raise ValueError('Hand tone review exceeds 256 KiB; simplify explicitly')
    if value['limb_kind'] != 'hand' or type(value['limb_kind']) is not str:
        raise ValueError('Choose the visible hand explicitly')
    out = deepcopy(value)
    total_points = 0
    for role in ROLES:
        stack = M.check_stack(value[role])
        if any(o['kind'] != 'brush' or o['operation'] not in ('add', 'subtract') for o in stack['objects']):
            raise ValueError('Hand tone accepts manual add/subtract brushes only')
        if role == 'protect' and any(not o['enabled'] or o['operation'] != 'add' or o['opacity'] != 1 or o['feather'] != 0 for o in stack['objects']):
            raise ValueError('Protection is an opaque hard union; delete strokes to revise it')
        if role != 'protect' and not any(o['enabled'] and o['operation'] == 'add' and o['opacity'] > 0 for o in stack['objects']):
            raise ValueError('Draw the visible hand and affected skin')
        total_points += sum(len(o['points']) for o in stack['objects'])
        out[role] = stack
    if total_points > M.MAX_TOTAL_POINTS:
        raise ValueError('Hand tone masks exceed aggregate brush budget')
    return out


def rasterize(review, source, *, byte_budget, cancelled=None):
    """Actual source grid only. No semantic/face/skin-inverse fallback."""
    from .hand_tone_state import source as checked_source
    source = checked_source(source); review = check_review(review)
    shape = (source['height'], source['width']); pixels = shape[0] * shape[1]
    plans = [M.validate_budget(review[role], shape) for role in ROLES]
    if sum(p['work'] for p in plans) > M.MAX_WORK:
        raise ValueError('Hand tone masks exceed aggregate raster work budget')
    # Three byte rasters plus two float masks and bounded native tile scratch.
    required = 20 * pixels + 128 * 1024**2
    if type(byte_budget) is not int or byte_budget < required:
        raise MemoryError('Hand tone mask raster budget refused')
    arrays = {}
    for role in ROLES:
        if cancelled and cancelled():
            raise InterruptedError('Hand tone raster cancelled')
        raw = M.raster(review[role], shape)
        if raw.dtype != np.uint8 or raw.shape != shape:
            raise ValueError('Mask owner returned an invalid canonical raster')
        arrays[role] = (raw > 0).astype(np.uint8) if role == 'protect' else raw.astype(np.float32) / np.float32(255)
    limb, target, protect = (arrays[k] for k in ROLES)
    # Explicit limb containment shrinks painted roles; it never expands them.
    target *= limb
    blocked = protect != 0
    target[blocked] = 0
    if not np.any(target > 0):
        raise ValueError('No unprotected target remains inside the hand')
    return arrays
