# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-only v1 adapter for one optional Rust hint predicate; UNRUN.

No detector construction, inference, synthetic fallback, photo selection or edits.
Evidence is captured from the SAME real FacePrecompute used for eye aperture.
"""
from __future__ import annotations

import ctypes as C
from functools import lru_cache
import hashlib
import math
from pathlib import Path

VERSION = 1
MAX_THRESHOLD = 31
DETECTION_LIMIT = 32
EVIDENCE_SCHEMA = 'lrt.pick.detected-faces.v1'


def settings(value=None):
    """Absent old settings mean disabled. Malformed/new versions do not migrate."""
    if value is None:
        return {'version': VERSION, 'more_than': None}
    if (type(value) is not dict or set(value) != {'version', 'more_than'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('闭眼例外规则版本无效；未应用')
    n = value['more_than']
    if n is not None and (type(n) is not int or not 1 <= n <= MAX_THRESHOLD):
        raise ValueError('例外阈值须为 1–31 的整数；检测上限为 32，不是完整人数统计')
    return dict(value)


def _stamp(path):
    st = Path(path).stat()
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def _model(path):
    """Actual current model bytes, bounded read; stat is only a change fence."""
    before = _stamp(path)
    with open(path, 'rb') as stream:
        data = stream.read(64 * 1024 * 1024 + 1)
    if not data or len(data) > 64 * 1024 * 1024 or _stamp(path) != before:
        raise ValueError('Detector model missing, over limit or changed during read')
    return before, hashlib.sha256(data).hexdigest()


def capture(pc, fn, m):
    """Never derive verified count from legacy Measures.faces or UI metadata."""
    try:
        from .face import FACE_LANDMARKER_MODEL
        pool = pc.all_landmarks
        count = len(pool)
        path = str(Path(fn.model_paths[FACE_LANDMARKER_MODEL]).resolve())
        stamp, digest = _model(path)
        if (pc.backend != 'mediapipe' or fn.name != 'mediapipe' or pc.manual
                or not 1 <= count <= DETECTION_LIMIT or pc.num_faces != count
                or pc.detection_limit != DETECTION_LIMIT
                or pc.detection_limit_reached != (count == DETECTION_LIMIT)
                or digest != pc.detector_model_sha256 or digest != fn.detector_model_sha256
                or m.eye_open is None or not math.isfinite(m.eye_open)
                or any(lm.shape != (478, 3) for lm in pool)
                or any(not math.isfinite(float(v)) for lm in pool for v in lm.flat)):
            return {}
        return {'schema': EVIDENCE_SCHEMA, 'status': 'verified', 'count': count,
                'backend': pc.backend, 'detector_sha256': digest,
                'model_path': path, 'model_stamp': stamp,
                'source_path': str(Path(m.path).absolute()), 'source_stamp': list(m.source_stamp),
                'decode_size': list(m.decode_size), 'decoded_from': m.decoded_from,
                'eye_open': m.eye_open, 'limit': DETECTION_LIMIT,
                'limit_reached': count == DETECTION_LIMIT}
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return {}


def current(m, *, hash_model=True):
    """None = unavailable/stale/inconsistent, NEVER zero detected or pass.

    The cheap display fence checks stat. Rule evaluation/reuse hashes bytes too.
    A concurrent external rewrite after a fence remains a filesystem limitation.
    """
    e = m.face_detection
    try:
        if (type(e) is not dict or e.get('schema') != EVIDENCE_SCHEMA
                or e.get('status') != 'verified' or e.get('backend') != 'mediapipe'
                or type(e.get('count')) is not int or not 1 <= e['count'] <= DETECTION_LIMIT
                or e.get('count') != m.faces or e.get('limit') != DETECTION_LIMIT
                or type(e.get('limit_reached')) is not bool
                or e['limit_reached'] != (e['count'] == DETECTION_LIMIT)
                or m.eye_open is None or not math.isfinite(m.eye_open)
                or e.get('eye_open') != m.eye_open
                or e.get('source_path') != str(Path(m.path).absolute())
                or e.get('source_stamp') != m.source_stamp or _stamp(m.path) != m.source_stamp
                or e.get('decode_size') != list(m.decode_size)
                or len(m.decode_size) != 2 or min(m.decode_size) <= 0
                or e.get('decoded_from') != m.decoded_from
                or e.get('model_stamp') != _stamp(e['model_path'])
                or not isinstance(e.get('detector_sha256'), str) or len(e['detector_sha256']) != 64):
            return None
        if hash_model:
            stamp, digest = _model(e['model_path'])
            if stamp != e['model_stamp'] or digest != e['detector_sha256']:
                return None
        return e['count']
    except (KeyError, OSError, TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def native():
    """Optional library; default-disabled path does not load it. No fallback."""
    path = Path(__file__).parent / 'bin' / 'liblrt_pick_group_eye.so'
    lib = C.CDLL(str(path))
    lib.lrt_pick_group_eye_abi.argtypes = []
    lib.lrt_pick_group_eye_abi.restype = C.c_uint32
    if lib.lrt_pick_group_eye_abi() != VERSION:
        raise RuntimeError('闭眼例外 Rust 规则版本不匹配')
    fn = lib.lrt_pick_group_eye_evaluate_v1
    fn.argtypes = [C.c_uint32] * 4
    fn.restype = C.c_int32
    return lib


def decision(m, rule):
    rule = settings(rule)
    if rule['more_than'] is None:
        return 'disabled'
    count = current(m)
    if count is None:
        return 'unknown'
    try:
        code = native().lrt_pick_group_eye_evaluate_v1(rule['more_than'], 1, count, DETECTION_LIMIT)
    except (OSError, AttributeError, RuntimeError):
        return 'unavailable'
    return {1: 'unknown', 2: 'not_matched', 3: 'omit'}.get(code, 'unavailable')
