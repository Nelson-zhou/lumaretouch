"""Actual per-face effect layers with source-local recovery and overlap ownership."""
from dataclasses import dataclass
import numpy as np
from . import people_state as S
from . import people_algorithms as A
from . import lip_makeup_state as L, facial_wrinkle_state as W
from .lip_makeup_layer import LipMakeupLayer
from .lip_makeup_runtime import bounds as lip_bounds
from .facial_wrinkle_layer import FacialWrinkleLayer, bounds as wrinkle_bounds
from .under_eye_layer import UnderEyeLayer, bounds as eye_bounds, KEYS as EYE_KEYS
from .ops import enhance as H

STAGES = ('skin_reference_match', 'skin_reference_body_match', 'body_face_match', 'body_skin_evenness', 'collarbone', 'neck_wrinkle', 'skin_evenness', 'skin_colour', 'facial_wrinkles', 'facial_sculpt', 'eye_makeup_enhance', 'eye_detail', 'eye_bag_preserve', 'lip_texture', 'lip_makeup', 'enhance', 'hair_colour', 'hair_unification', 'eye_light', 'blush_makeup', 'face_decoration', 'lipstick','eyeliner','eyelash','brow_enhance','brow_makeup','iris_makeup')


@dataclass(frozen=True)
class LocalEffect:
    face_ref: dict
    stage: str
    window: tuple
    delta: object = None
    weights: object = None
    amounts: object = None
    facts: object = None
    chroma_shift: object = None
    log_gain: object = None

    def contribution(self, current):
        y, x, h, w = self.window
        if self.stage == 'enhance':
            original = current[y:y+h, x:x+w]
            return np.asarray(H.enhance_np(original, self.weights, self.amounts)-original, np.float32)
        return self.delta


def prepare(face_ref, landmarks, recipes, source, *, excluded, skin, backend, semantic_sha, blush_review=None, lipstick_review=None, face_decoration_review=None, face_decoration_skin=None, face_decoration_excluded=None, source_only=False):
    """Source is frozen repaired working-sRGB, never another face's corrected RGB."""
    h, w = source.shape[:2]; records = []
    ref = S.check_ref(face_ref)
    if L.active(recipes[A.LIP]):
        if excluded is None: raise ValueError('Lip makeup needs actual source visibility evidence')
        window, lm = lip_bounds(landmarks, h, w); y, x, rh, rw = window
        layer = LipMakeupLayer(window, source[y:y+rh,x:x+rw], lm, excluded[y:y+rh,x:x+rw],
                               backend=backend, identity=ref['face_instance_id'])
        delta = layer.solve(recipes[A.LIP])
        records.append(LocalEffect(ref, 'lip_makeup', window, delta=delta, facts=layer.facts))
    # Both original and derived sources use these concrete reviewed consumers.
    # Neutral recipes need no native call; missing review/semantics still refuse.
    if A.BLUSH.active(recipes[A.BLUSH.OP]):
        from .blush_makeup_layer import prepare_record as prepare_blush
        blush=prepare_blush(ref,landmarks,recipes[A.BLUSH.OP],source,excluded=excluded,skin=skin,backend=backend,semantic_sha=semantic_sha,reviewed=blush_review)
        if blush is not None:records.append(blush)
    if A.LIPSTICK.active(recipes[A.LIPSTICK.OP]):
        from .lipstick_layer import prepare_record as prepare_lipstick
        lipstick=prepare_lipstick(ref,landmarks,recipes[A.LIPSTICK.OP],source,excluded=excluded,backend=backend,semantic_sha=semantic_sha,reviewed=lipstick_review)
        if lipstick is not None:records.append(lipstick)
    if A.FACE_DECORATION.active(recipes[A.FACE_DECORATION.OP]):
        from .face_decoration_layer import prepare_record as prepare_decoration
        decoration = prepare_decoration(ref,landmarks,recipes[A.FACE_DECORATION.OP],source,excluded=face_decoration_excluded,skin=face_decoration_skin,
            backend=backend,semantic_sha=semantic_sha,reviewed=face_decoration_review)
        if decoration is None: raise ValueError('Requested face decoration returned no effect record')
        records.append(decoration)
    amounts = recipes[A.WRINKLES]
    if W.active(amounts):
        if skin is None or semantic_sha is None: raise ValueError('Wrinkles need actual source skin evidence')
        window, lm = wrinkle_bounds(landmarks, h, w); y, x, rh, rw = window
        layer = FacialWrinkleLayer(window, source[y:y+rh,x:x+rw], lm, skin[y:y+rh,x:x+rw],
                                   backend=backend, model_identity=semantic_sha)
        delta = layer.solve(amounts)
        for key in W.KEYS:
            if amounts[key] and layer.facts[key].get('reason') not in (None, 'no_detected_wrinkle_lines'):
                raise ValueError('Requested wrinkle region refused: ' + key + ': ' + str(layer.facts[key]['reason']))
        records.append(LocalEffect(ref, 'facial_wrinkles', window, delta=delta, facts=layer.facts))
    amounts = recipes[A.ENHANCE]
    if any(amounts[k] for k in EYE_KEYS):
        window, lm = eye_bounds(landmarks, h, w); y, x, rh, rw = window
        layer = UnderEyeLayer(window, source[y:y+rh,x:x+rw], lm)
        delta = layer.solve(amounts)
        records.append(LocalEffect(ref, 'eye_detail', window, delta=delta, facts=layer.facts))
    if any(amounts[k] for k in H.PIXEL_KEYS):
        window, weights, _, facts = H.build_field(landmarks, h, w, source, strict_teeth=H.TEETH.active(amounts))
        if H.TEETH.active(amounts) and not np.any(weights[2] > 0):
            raise ValueError('Independent teeth colour refused: no measured visible teeth support')
        facts = dict(facts)
        for key in H.TEETH.KEYS:
            facts[key] = {**facts.get('teeth',{}), 'support': 'inner-cavity-geometric-photometric-not-segmentation',
                          'requested': amounts[key], 'native_solver': 'rust-teeth-colour-v1'}
        records.append(LocalEffect(ref, 'enhance', window, weights=weights, amounts=amounts, facts=facts))
    for record in records:
        for array in (record.delta, record.weights, record.chroma_shift, record.log_gain):
            if array is not None: array.setflags(write=False)
    return records


def verify_recovery(face_ref, stage, recovery, shape):
    """A face mask is never inherited or reused as another face's support."""
    if recovery is None: return None
    if type(recovery) is not dict or set(recovery) != {'face_ref', 'stage', 'weight', 'content_sha256', 'recipe_sha256'}:
        raise ValueError('Invalid source-owned recovery record')
    if recovery['face_ref'] != face_ref or recovery['stage'] != stage:
        raise ValueError('Recovery belongs to another face, analysis or operation')
    S.digest(recovery['recipe_sha256'])
    weight = recovery['weight']
    if type(weight) is not np.ndarray or weight.dtype != np.uint8 or weight.shape != tuple(shape):
        raise ValueError('Recovery must retain its source-frame uint8 coverage')
    import hashlib
    if hashlib.sha256(np.ascontiguousarray(weight).tobytes()).hexdigest() != recovery['content_sha256']:
        raise ValueError('Recovery coverage differs from its retained asset')
    return weight.astype(np.float32)/255.


def apply(stage, current, records, *, recovery=None):
    """One operator's before/after pair; no repeated application on overlap."""
    if stage not in STAGES: raise ValueError('Unknown portrait stage')
    if stage == 'skin_reference_body_match':
        from .skin_reference_body_composition import apply_records_np
        return apply_records_np(current, records, recovery)
    if stage == 'skin_reference_match':
        from .skin_reference_match_composition import apply_records_np
        return apply_records_np(current, records, recovery)
    if stage == 'hair_unification':
        from .hair_unification_composition import apply_records_np
        return apply_records_np(current, records, recovery)
    if stage == 'facial_sculpt':
        from .facial_sculpt_composition import apply_records_np
        return apply_records_np(current, records, recovery)
    if stage == 'neck_wrinkle':
        from .neck_wrinkle_composition import apply_records_np
        return apply_records_np(current, records, recovery)
    if stage == 'collarbone':
        from .collarbone_composition import apply_records_np
        return apply_records_np(current, records, recovery)
    if stage in ('skin_evenness', 'body_skin_evenness', 'body_face_match'):
        from .skin_evenness_composition import apply_records_np
        return apply_records_np(current, records, recovery, stage=stage)
    if current.ndim != 3 or current.shape[2] != 3 or not np.isfinite(current).all(): raise ValueError('Invalid portrait stage input')
    h, w = current.shape[:2]; total = np.zeros_like(current, dtype=np.float32)
    occupied = np.zeros((h, w), bool); overlap = 0
    for record in sorted((r for r in records if r.stage == stage), key=lambda r:r.face_ref['face_instance_id']):
        delta = record.contribution(current)
        if delta is None: continue
        y, x, rh, rw = record.window
        if min(y, x) < 0 or y+rh > h or x+rw > w or delta.shape != (rh,rw,3) or not np.isfinite(delta).all():
            raise ValueError('Face correction is not in the frozen source frame')
        weight = verify_recovery(record.face_ref, stage, (recovery or {}).get((record.face_ref['face_instance_id'], stage)), (h,w))
        if weight is not None: delta = delta * (1-weight[y:y+rh,x:x+rw,None])
        active = np.any(delta != 0, axis=2); used = occupied[y:y+rh,x:x+rw]
        overlap += int(np.count_nonzero(active & used)); take = active & ~used
        total[y:y+rh,x:x+rw][take] = delta[take]; used[take] = True
    if stage in ('eye_bag_preserve','face_decoration'):
        from .people_source_vector import apply_np
        out = apply_np(current, total, label='Face decoration' if stage == 'face_decoration' else 'Eye-bag preservation')
        return out, {'stage':stage, 'overlap_pixels':overlap,
                     'composition':'direction-preserving-per-pixel-SDR-headroom-gain-no-channel-clipping',
                     'changed_pixels':int(np.count_nonzero(np.any(out != current, axis=2)))}
    if stage == 'lip_texture':
        from .lip_texture_composition import apply_np
        out = apply_np(current, total)
        return out, {'stage':stage, 'overlap_pixels':overlap,
                     'changed_pixels':int(np.count_nonzero(np.any(out != current, axis=2)))}
    if stage == 'eye_makeup_enhance':
        from .eye_makeup_enhance_composition import apply_np
        out = apply_np(current, total)
        return out, {'stage':stage, 'overlap_pixels':overlap,
                     'changed_pixels':int(np.count_nonzero(np.any(out != current, axis=2)))}
    if stage == 'brow_enhance':
        from .brow_enhance_composition import apply_np
        out = apply_np(current, total)
        return out, {'stage':stage, 'overlap_pixels':overlap,
                     'changed_pixels':int(np.count_nonzero(np.any(out != current, axis=2)))}
    corrected=current+total
    # Existing working-sRGB stages remain unchanged. Eye-light does not clip its HDR-capable delta.
    out = np.where(total != 0, corrected if stage=='eye_light' else np.clip(corrected, 0, 1), current)
    return out, {'stage':stage, 'overlap_pixels':overlap, 'changed_pixels':int(np.count_nonzero(np.any(total != 0, axis=2)))}
