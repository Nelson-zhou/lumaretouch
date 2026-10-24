# SPDX-License-Identifier: GPL-3.0-or-later
"""One ordered source-domain skin effect, before the existing common warp.

Colour and finish have independent recipes and operation-specific body reviews.
Colour runs first, then finish reads its result. Only the final-minus-original
delta enters the existing skin_colour stage, never two additive corrections
computed from the original. AUTHORED / UNRUN, not image-quality acceptance.
"""
import numpy as np
from . import skin_colour_state as S, skin_finish_state as F, people_state as P


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Skin composition cancelled; no partial result published')


def _coverage(face_support, ref, analysis, *, family, people_state, assets, body_bank,
              byte_budget, reserved_bytes):
    """Never union the other operation's consent or coverage into this one."""
    support = face_support.copy()
    body_facts = {'enabled': False}
    if people_state is not None:
        from .skin_colour_body_support import raster as body_raster
        body_coverage, body_facts = body_raster(people_state, assets or {}, ref,
            body_bank, analysis, support.shape, family=family,
            byte_budget=byte_budget-reserved_bytes-support.nbytes)
        if body_coverage is not None:
            if (type(body_coverage) is not np.ndarray or body_coverage.dtype != np.float32
                    or body_coverage.shape != support.shape or not np.isfinite(body_coverage).all()
                    or np.any((body_coverage < 0) | (body_coverage > 1))):
                raise ValueError('Reviewed body skin must be finite source-domain float32 coverage')
            # Each recipe applies once on its own face/body max-union. Sharing
            # semantic evidence is not sharing body consent between operations.
            np.maximum(support, body_coverage, out=support)
    elif assets is not None or body_bank is not None:
        raise ValueError('Body skin ' + family + ' needs the actual canonical people graph')
    if np.count_nonzero(support >= .25) < 32:
        raise ValueError('Skin ' + family + ' has insufficient confidently visible target-owned skin')
    support.setflags(write=False)
    return support, body_facts


def _owned_result(value, shape):
    if (type(value) is not np.ndarray or value.dtype != np.float32 or value.shape != shape
            or not np.isfinite(value).all() or np.any((value < 0) | (value > 1))):
        raise ValueError('Invalid composed skin SDR output; no partial result published')
    owned = np.array(value, dtype=np.float32, order='C', copy=True)
    owned.setflags(write=False)
    return owned


def prepare(face_ref, analysis, other_analyses, source, recipe, *, byte_budget, protected_boxes=(),
            people_state=None, body_assets=None, body_bank=None, finish_recipe=None,
            finish_body_assets=None, cancelled=None):
    r = S.check(recipe); finish = F.check(finish_recipe)
    colour_active, finish_active = S.active(r), F.active(finish)
    if not colour_active and not finish_active:
        return []
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    _poll(cancelled)
    from .face_scope import selected_face_skin
    from .people_effects import LocalEffect
    ref = P.check_ref(face_ref)
    if analysis['face_ref'] != ref or analysis['evidence']['backend'] != 'mediapipe':
        raise ValueError('Face-skin colour needs the actual target-owned measured face')
    P.digest(analysis['evidence']['semantic_model_sha256'])
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3):
        raise ValueError('Face-skin colour requires finite SDR working-sRGB source pixels')
    h, w = source.shape[:2]
    # Preserve the original colour-only admission. Finish reserves additional
    # coverage, immutable intermediate/output copies and bounded validation
    # scratch before any raster or native call; this is not a measured peak.
    reserve_per_pixel = 256 + (64 if finish_active else 0)
    if (type(byte_budget) is not int or byte_budget < h*w*reserve_per_pixel + 128*1024*1024):
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
    support = np.array(selected_face_skin(skin, analysis['landmarks'], other_landmarks=others),
                       dtype=np.float32, order='C', copy=True)
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
    support.setflags(write=False)
    _poll(cancelled)
    colour_support = finish_support = None
    body_facts = finish_body_facts = {'enabled': False}
    reserved = source.nbytes + support.nbytes
    if colour_active:
        colour_support, body_facts = _coverage(support, ref, analysis, family='skin_colour',
            people_state=people_state, assets=body_assets, body_bank=body_bank,
            byte_budget=byte_budget, reserved_bytes=reserved)
        reserved += colour_support.nbytes
    _poll(cancelled)
    if finish_active:
        finish_support, finish_body_facts = _coverage(support, ref, analysis, family='skin_finish',
            people_state=people_state, assets=finish_body_assets, body_bank=body_bank,
            byte_budget=byte_budget, reserved_bytes=reserved)
    # Both active ownership checks finish before either native solver runs.
    support = (np.maximum(colour_support, finish_support) if colour_active and finish_active
               else colour_support if colour_active else finish_support)
    visible = support > 0
    ys, xs = np.nonzero(visible)
    y, x = int(ys.min()), int(xs.min())
    rh, rw = int(ys.max())-y+1, int(xs.max())-x+1
    original = np.array(source[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    original.setflags(write=False)
    result = original
    native_kwargs = {} if cancelled is None else {'cancelled': cancelled}
    if colour_active:
        from .skin_colour_native import apply as apply_colour
        coverage = np.array(colour_support[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
        coverage.setflags(write=False)
        _poll(cancelled)
        result = _owned_result(apply_colour(result, coverage, r['temperature'], r['tint'],
                                           **native_kwargs), original.shape)
    if finish_active:
        from .skin_finish_native import apply as apply_finish
        coverage = np.array(finish_support[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
        coverage.setflags(write=False)
        _poll(cancelled)
        # Crucially, finish consumes the colour-corrected working pixels, not
        # another copy of original. No sum-and-clip between these two solvers.
        result = _owned_result(apply_finish(result, coverage, finish['whitening'], finish['rosiness'],
                                           **native_kwargs), original.shape)
    _poll(cancelled)
    delta = np.ascontiguousarray(np.where(support[y:y+rh, x:x+rw,None] > 0,
                                         result-original, 0), dtype=np.float32)
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
    if body_facts.get('enabled') or finish_body_facts.get('enabled'):
        facts['scope'] = 'face-and-explicitly-reviewed-body-skin'
        facts['support'] = 'source-face-skin-plus-confirmed-body-semantic-manual-coverage'
    if finish_active:
        facts['operation_order'] = ([S.OP] if colour_active else []) + [F.OP]
        if colour_active:
            facts['skin_colour'] = {'recipe': r, 'body_extension': body_facts,
                'support_pixels': int(np.count_nonzero(colour_support > 0)),
                'native_solver': 'rust-skin-colour-v1'}
        facts['skin_finish'] = {'recipe': finish, 'body_extension': finish_body_facts,
            'support_pixels': int(np.count_nonzero(finish_support > 0)),
            'native_solver': 'rust-skin-finish-v1'}
        facts['native_solver'] = ('rust-skin-colour-v1-then-rust-skin-finish-v1' if colour_active
                                  else 'rust-skin-finish-v1')
        facts['composition'] = 'ordered-native-results-one-final-minus-original-source-delta'
    _poll(cancelled)
    return [LocalEffect(ref, 'skin_colour', (y,x,rh,rw), delta=delta, facts=facts)]
