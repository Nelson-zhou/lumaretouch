# SPDX-License-Identifier: GPL-3.0-or-later
"""Authenticated-analysis boundary for canonical source-owned face contour.

The canonical people renderer authenticates durable FaceRef/source ownership and
passes EVERY other retained face's normalized box, including unresolved/disabled
faces. This module additionally validates the exact retained landmark hash and
existing face_skin observation contract. It never generates analysis, acquires a
source, substitutes a face template or serializes masks/geometry into parameters.
"""
import hashlib
import numpy as np

from . import face_contour_state as S
from .face_contour_geometry import build_controls, FaceContourRefusal
from .face_contour_field import FaceContourField


def _landmark_digest(value):
    lm = np.asarray(value, dtype='<f4')
    if lm.shape != (478, 3) or not np.isfinite(lm).all() or np.any((lm[:, :2] < 0) | (lm[:, :2] > 1)):
        raise ValueError('Face contour requires actual normalized 478x3 retained landmarks')
    return hashlib.sha256(np.ascontiguousarray(lm).tobytes()).hexdigest()


def require_analysis(landmarks, analysis, shape, excluded):
    from .people_state import check_ref, check_evidence
    from .skin_colour_support import check_analysis_fields
    if type(analysis) is not dict or not {'face_ref', 'evidence', 'landmarks', 'excluded'}.issubset(analysis):
        raise ValueError('Face contour requires source-owned retained face analysis')
    check_ref(analysis['face_ref'])
    evidence = check_evidence(analysis['evidence'])
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('Face contour refuses unverified or synthetic face evidence')
    digest = _landmark_digest(landmarks)
    if digest != evidence['landmark_digest'] or digest != _landmark_digest(analysis['landmarks']):
        raise ValueError('Face contour landmarks differ from the exact retained person evidence')
    if check_analysis_fields(analysis, shape) is None:
        raise ValueError('Face contour requires authenticated face_skin, never merged skin or landmarks alone')
    retained = analysis['excluded']
    if (type(retained) is not np.ndarray or type(excluded) is not np.ndarray
            or retained.shape != tuple(shape) or excluded.shape != tuple(shape)
            or not np.isfinite(retained).all() or np.any((retained < 0) | (retained > 1))
            or not np.array_equal(retained, excluded)):
        raise ValueError('Face contour exclusion must be the retained same-source known-occluder field')
    return analysis['face_skin']


def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes=()):
    r = S.check(recipe)
    # Neutral has no field, native-library requirement, mask read or cache change.
    if not S.active(r):
        return None
    if type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3:
        raise ValueError('Face contour needs the actual frozen RGB source')
    shape = source.shape[:2]
    skin = require_analysis(landmarks, analysis, shape, excluded)
    # Geometry uses the authenticated canonical float32 observation, not extra
    # precision a caller might attach without changing its canonical hash.
    retained_landmarks = np.asarray(analysis['landmarks'], dtype='<f4')
    P, D, meta = build_controls(retained_landmarks, shape, r, source, excluded, backend=backend,
                                skin=skin, protected_boxes=protected_boxes)
    try:
        return FaceContourField(P, D, meta, shape)
    except (ValueError, np.linalg.LinAlgError) as error:
        facts = {key: {**fact, 'reason': str(error) if fact['requested'] else fact['reason']}
                 for key, fact in meta['controls'].items()}
        raise FaceContourRefusal(facts, 'Face contour field admission failed') from error
