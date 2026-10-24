# SPDX-License-Identifier: GPL-3.0-or-later
"""One full-source facial log-gain contribution, never solved on export tiles."""
import hashlib
import numpy as np
from . import facial_sculpt_state as S, facial_sculpt_native as N, people_state as P
from . import facial_sculpt_geometry as G
from .skin_colour_support import check_analysis_fields


def prepare(face_ref, analysis, source, recipe, *, byte_budget, reviewed, protected_boxes=(), cancelled=None):
    """Return one LocalEffect or None when neutral, for original OR derived RGB.

    Host authenticates the effective source and passes every other retained box,
    including disabled/unresolved faces. reviewed is resolved by this family's
    source+FaceRef+landmark-bound support bank on the exact render grid.
    """
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    def poll():
        if cancelled is not None and cancelled():
            raise InterruptedError('Facial structure cancelled before publication')
    poll()
    ref = P.check_ref(face_ref)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 1):
        raise ValueError('面部立体需要当前有效来源的 float32 RGB，不能隐式转换 alpha/HDR')
    h, w = source.shape[:2]
    baseline = h*w*32 + 32*1024*1024
    if type(byte_budget) is not int or byte_budget < baseline:
        raise MemoryError('Facial structure source validation exceeds budget before allocation')
    if type(analysis) is not dict or analysis.get('face_ref') != ref:
        raise ValueError('面部立体分析不属于当前人物')
    evidence = P.check_evidence(analysis.get('evidence'))
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('面部立体需要真实已验证的人物分析')
    P.digest(evidence['semantic_model_sha256'])
    lm = np.asarray(analysis.get('landmarks'), dtype='<f4')
    if (lm.shape != (478, 3) or not np.isfinite(lm).all()
            or hashlib.sha256(np.ascontiguousarray(lm).tobytes()).hexdigest() != evidence['landmark_digest']):
        raise ValueError('面部立体关键点与当前保留来源摘要不匹配')
    g = G.geometry(lm, (h, w)); window = g['window']; y, x, rh, rw = window
    if baseline + rh*rw*320 + N.memory_estimate((rh, rw)) > byte_budget:
        raise MemoryError('Facial structure full-source solve exceeds budget; no proxy fallback')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('面部立体不支持此 HDR 或非有限来源；未裁切数值')
    observation = check_analysis_fields(analysis, (h, w))
    if observation is None:
        raise ValueError('面部立体需要真实 face_skin 观察，不能借用合并皮肤蒙版')
    skin, excluded = analysis.get('face_skin'), analysis.get('excluded')
    G.mask(skin, (h, w), 'face_skin'); G.mask(excluded, (h, w), '遮挡排除')
    G.mask(reviewed, (h, w), '独立高光/阴影皮肤审核')
    foreign = G.boxes(protected_boxes)
    poll()
    support, target, facts = G.fields(g, (h, w), skin, excluded, reviewed, foreign, cancelled)
    field = N.field(source[y:y+rh, x:x+rw], support, target, recipe,
                    radius=g['radius'], cancelled=cancelled)
    poll()
    positive = int(np.count_nonzero(field > 0)); negative = int(np.count_nonzero(field < 0))
    from .people_effects import LocalEffect
    return LocalEffect(ref, 'facial_sculpt', window, log_gain=field, facts={**facts,
        'recipe': recipe, 'face_ref': ref, 'landmark_digest': evidence['landmark_digest'],
        'semantic_model_sha256': evidence['semantic_model_sha256'], 'skin_observation': observation,
        'source_dimensions': [evidence['source_width'], evidence['source_height']],
        'render_dimensions': [w, h], 'positive_structure_pixels': positive,
        'negative_structure_pixels': negative, 'changed_pixels': positive+negative,
        'reason': None if positive+negative else 'no_measurable_broad_structure',
        'native_solver': 'rust-facial-two-scale-log-structure-v1', 'policy': S.POLICY,
        'composition': 'source-log-gain-common-linear-rgb-gamut-bound',
        'limitations': ['not-3d-relighting-or-highlight-recovery', 'not-specular-gloss-or-skin-smoothing',
                        'review-is-not-complete-occlusion-segmentation', 'photo-and-numeric-acceptance-unrun']})
