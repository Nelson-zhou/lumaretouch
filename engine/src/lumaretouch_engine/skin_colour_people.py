# SPDX-License-Identifier: GPL-3.0-or-later
"""One source-domain colour effect for face and explicitly reviewed body skin.

The scalar recipe and Rust stage stay shared. A dedicated target-owned review
may extend coverage, never infer a body from the selected face or borrow masks.
"""
import numpy as np
from . import skin_colour_state as S, people_state as P


def prepare(face_ref, analysis, other_analyses, source, recipe, *, byte_budget, protected_boxes=(),
            people_state=None, body_assets=None, body_bank=None):
    r = S.check(recipe)
    if not S.active(r):
        return []
    from .face_scope import selected_face_skin
    from .skin_colour_native import apply
    from .people_effects import LocalEffect
    ref = P.check_ref(face_ref)
    if analysis['face_ref'] != ref or analysis['evidence']['backend'] != 'mediapipe':
        raise ValueError('Face-skin colour needs the actual target-owned measured face')
    P.digest(analysis['evidence']['semantic_model_sha256'])
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3):
        raise ValueError('Face-skin colour requires finite SDR working-sRGB source pixels')
    h, w = source.shape[:2]
    if (type(byte_budget) is not int or byte_budget < h*w*256 + 128*1024*1024):
        raise ValueError('Face-skin colour geometry and private buffers exceed memory budget')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('Face-skin colour does not clip HDR or invalid source pixels')
    from .skin_colour_support import check_analysis_fields as verify_skin_observation
    verify_skin_observation(analysis, (h,w))
    skin, excluded = analysis.get('face_skin'), analysis.get('excluded')
    for value in (skin, excluded):
        if (type(value) is not np.ndarray or value.shape != (h,w)
                or not np.isfinite(value).all() or np.any((value < 0) | (value > 1))):
            raise ValueError('Face-skin colour lacks target source face-skin and exclusion evidence')
    others = []
    for other in other_analyses:
        if other['face_ref']['asset_sha256'] != ref['asset_sha256']:
            raise ValueError('Other-face exclusion belongs to a different source')
        others.append(other['landmarks'])
    # Never feed merged body+face skin into this face-specific selector.
    support = selected_face_skin(skin, analysis['landmarks'], other_landmarks=others)
    support *= 1 - excluded
    # Retained manual/unresolved neighbours have no invented landmarks. Their
    # exact source boxes are used only as conservative protection, never skin.
    for box in protected_boxes:
        if (type(box) not in (list,tuple) or len(box) != 4
                or any(type(v) not in (int,float) or not 0 <= v <= 1 for v in box)
                or not (box[0] < box[2] and box[1] < box[3])):
            raise ValueError('Neighbour protection needs a retained source-normalized box')
        left, top, right, bottom = np.asarray(box)*[w,h,w,h]
        feather = max(1., .015*max(right-left,bottom-top))
        pad = feather + np.sqrt(.5) + 1
        x0, y0 = max(0,int(np.floor(left-pad))), max(0,int(np.floor(top-pad)))
        x1, y1 = min(w,int(np.ceil(right+pad))), min(h,int(np.ceil(bottom+pad)))
        if not np.any(support[y0:y1,x0:x1] > 0):
            continue
        xx = np.arange(x0,x1,dtype=np.float64)[None,:]+.5
        yy = np.arange(y0,y1,dtype=np.float64)[:,None]+.5
        dx = np.maximum(np.maximum(left-xx,xx-right),0)
        dy = np.maximum(np.maximum(top-yy,yy-bottom),0)
        # Protect whole pixel footprints, then feather strictly outside box.
        support[y0:y1,x0:x1] *= np.clip((np.hypot(dx,dy)-np.sqrt(.5))/feather,0,1)
    body_facts = {'enabled': False}
    if people_state is not None:
        from .skin_colour_body_support import raster as body_raster
        body_coverage, body_facts = body_raster(people_state, body_assets or {}, ref,
            body_bank, analysis, (h,w), byte_budget=byte_budget-source.nbytes-support.nbytes)
        if body_coverage is not None:
            if (type(body_coverage) is not np.ndarray or body_coverage.dtype != np.float32
                    or body_coverage.shape != (h,w) or not np.isfinite(body_coverage).all()
                    or np.any((body_coverage < 0) | (body_coverage > 1))):
                raise ValueError('Reviewed body skin must be finite source-domain float32 coverage')
            # Union, not addition or a second colour pass: the same signed
            # parameters are applied exactly once before the shared body warp.
            np.maximum(support, body_coverage, out=support)
            del body_coverage
    elif body_assets is not None or body_bank is not None:
        raise ValueError('Body skin colour needs the actual canonical people graph')
    visible = support > 0
    if np.count_nonzero(support >= .25) < 32:
        raise ValueError('Skin colour has insufficient confidently visible target-owned skin')
    ys, xs = np.nonzero(visible)
    y, x = int(ys.min()), int(xs.min())
    rh, rw = int(ys.max())-y+1, int(xs.max())-x+1
    original = source[y:y+rh, x:x+rw]
    coverage = np.ascontiguousarray(support[y:y+rh, x:x+rw], dtype=np.float32)
    result = apply(original, coverage, r['temperature'], r['tint'])
    delta = np.ascontiguousarray(np.where(coverage[...,None] > 0, result-original, 0), dtype=np.float32)
    if not np.isfinite(delta).all():
        raise ValueError('Invalid face-skin colour output; no partial result published')
    delta.setflags(write=False)
    facts = {'face_ref': ref, 'recipe': r, 'semantic_model_sha256': analysis['evidence']['semantic_model_sha256'],
             'support': 'source-face-skin-confidence-intersected-measured-face-oval',
             'scope': 'face-only-not-full-body', 'other_face_exclusions': len(others),
             'unresolved_neighbour_box_vetoes': len(protected_boxes),
             'semantic_observation': dict(analysis['face_skin_observation']),
             'occlusion': 'six-class-and-anatomy-not-complete-hand-or-glasses-segmentation',
             'semantic_resolution': 'source-bound-model-coverage-may-be-resampled',
             'body_extension': body_facts,
             'support_pixels': int(np.count_nonzero(visible)),
             'changed_pixels': int(np.count_nonzero(np.any(delta != 0, axis=2))),
             'native_solver': 'rust-skin-colour-v1'}
    if body_facts.get('enabled'):
        facts['scope'] = 'face-and-explicitly-reviewed-body-skin'
        facts['support'] = 'source-face-skin-plus-confirmed-body-semantic-manual-coverage'
    return [LocalEffect(ref, 'skin_colour', (y,x,rh,rw), delta=delta, facts=facts)]
