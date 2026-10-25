# SPDX-License-Identifier: GPL-3.0-or-later
"""Versioned Rust scalar planner bridge. No build, download, model or fallback.

Loading occurs only on an explicit capability/solve call, not module import.
AUTHORED / UNRUN, including the native ABI and library admission.
"""
from __future__ import annotations

import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

from . import portrait_crop_state as S

ABI = 1
CAPABILITIES = 15
RESULT_LENGTH = 20
P = C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).parent / 'bin' / 'liblrt_portrait_crop.so'
    if not path.is_file():
        raise RuntimeError('Portrait crop Rust core is not installed; no substitute planner was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_portrait_crop_abi.argtypes = []
        lib.lrt_portrait_crop_abi.restype = C.c_uint32
        lib.lrt_portrait_crop_capabilities.argtypes = []
        lib.lrt_portrait_crop_capabilities.restype = C.c_uint64
        lib.lrt_portrait_crop_result_len.argtypes = []
        lib.lrt_portrait_crop_result_len.restype = C.c_size_t
        if (lib.lrt_portrait_crop_abi() != ABI
                or lib.lrt_portrait_crop_capabilities() & CAPABILITIES != CAPABILITIES
                or lib.lrt_portrait_crop_result_len() != RESULT_LENGTH):
            raise RuntimeError('Portrait crop native ABI/capability mismatch')
        fn = lib.lrt_portrait_crop_plan_v1
        fn.argtypes = [C.c_uint32, C.c_uint32, P, C.c_size_t, P, C.c_size_t, P, C.c_size_t]
        fn.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise RuntimeError('Portrait crop native library cannot satisfy the version-1 contract') from error
    return lib


def capability():
    """Presence/ABI probe only. available does NOT claim numerical acceptance."""
    try:
        native()
    except RuntimeError as error:
        return {'version': 1, 'backend': S.BACKEND, 'available': False,
                'abi': None, 'capabilities': 0, 'reason': str(error)}
    return {'version': 1, 'backend': S.BACKEND, 'available': True,
            'abi': ABI, 'capabilities': CAPABILITIES, 'reason': None}


def solve(width, height, anchors, rules):
    """Return ABI-1 vector. Public serializable plans live in the planner module."""
    width, height = S.check_size(width, height)
    anchors = S.check_anchors(anchors, width, height)
    rules = S.check_rules(rules)
    a = (C.c_double * 6)(*(v for name in S.ANCHOR_NAMES for v in anchors[name]))
    r = (C.c_double * 4)(*(rules[name] for name in S.RULE_NAMES))
    output = (C.c_double * RESULT_LENGTH)()
    code = native().lrt_portrait_crop_plan_v1(width, height, a, 6, r, 4, output, RESULT_LENGTH)
    failures = {
        2: ('invalid_geometry', 'Portrait crop native input is invalid'),
        3: ('infeasible', 'Requested portrait composition does not fit the current image; no clamping or padding'),
        4: ('pixel_rounding', 'Pixel-edge rounding collapses the crop or excludes a reviewed anchor'),
    }
    if code in failures:
        raise S.PortraitCropError(*failures[code])
    if code:
        raise RuntimeError(f'Portrait crop native planner refused its ABI transaction ({code}); no plan published')
    values = list(output)
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError('Portrait crop native planner produced nonfinite geometry')
    return values
