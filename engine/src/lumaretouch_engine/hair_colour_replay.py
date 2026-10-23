"""Strict hair-only replay of already retained measured inputs, without inference.

This is not a replacement face producer. It restores original hash-pinned
landmark bytes only when no requested non-hair operator needs missing semantic
inputs. Absent exclusion/skin stays None, never a fabricated all-zero field.
"""
import numpy as np
from . import hair_colour_state as H, hair_colour_assets as ASSETS, hair_colour_evidence as FIELDS
from . import people_state as P, people_algorithms as A, people_resolver as R
from . import people_retained_analysis as RA, people_binding as B


def analyses(engine, state, binding):
    """Return exact retained rows, or None if the normal analysis path is needed.

    Caller must use this only for the explicitly supplied original source and
    preserve normal publication/render/export admission. No new face is made,
    no detector count or face box is treated as hair-instance ownership.
    """
    state = P.check(state); binding = ASSETS.source(binding)
    if H.OPERATION not in A.specifications(): return None  # Not integrated yet.
    defaults = A.defaults(); specs = A.specifications(); result = {}; has_hair = False
    measured = FIELDS.for_source(engine.__dict__.get('_hair_colour_evidence', {}), binding)
    if measured is None: return None
    semantic_id = FIELDS.identity(measured)
    for face in state['faces'].values():
        if face['asset_sha256'] != binding['sha256'] or not face['enabled']: continue
        resolved = R.resolve(state, face['face_instance_id'], defaults)
        if resolved['conflicts']: return None
        recipes = A.recipes(resolved)
        if any(value != specs[operation][0] for operation, value in recipes.items() if operation != H.OPERATION): return None
        if any(kind != ASSETS.KIND for kind in face['local_assets']): return None
        recipe = recipes[H.OPERATION]
        wanted = H.active(recipe) or ASSETS.KIND in face['local_assets'] or recipe != H.neutral()
        if not wanted: continue
        has_hair = True; ref = P.face_ref(face)
        ASSETS.verify_face(state, ref, binding)
        if ASSETS.KIND in face['local_assets']:
            support = ASSETS.resolve(state, engine.__dict__.get('_hair_colour_assets', {}), ref)
            if support['semantic_evidence_sha256'] != semantic_id: raise ValueError('Retained hair replay evidence differs from reviewed support')
        elif H.active(recipe): return None  # Missing ownership is not repaired here.
        row = engine.__dict__.get('_people_landmarks', {}).get(RA.key(ref))
        if row is None or row['face_ref'] != ref or row['evidence'] != face['evidence']: return None
        points = np.array(row['landmarks'], dtype='<f4', order='C', copy=True)
        if points.shape != (478,3) or not np.isfinite(points).all() or B.landmark_digest(points) != face['evidence']['landmark_digest']:
            raise ValueError('Saved measured landmarks are corrupt; no synthetic replacement was made')
        points.setflags(write=False)
        result[ref['face_instance_id']] = {'face_ref':ref, 'evidence':face['evidence'],
                                         'landmarks':points, 'excluded':None, 'skin':None}
    return result if has_hair else None


def restore_open(engine, decoded):
    """Before people_open.prepare creates any model, return True if replay is ready."""
    from .local_mask_state import source_digest
    state = engine._people_owner().snapshot()
    binding = {'sha256': source_digest(engine._doc_path), 'width':int(decoded.src_w), 'height':int(decoded.src_h)}
    restored = analyses(engine, state, binding)
    if restored is None: return False
    engine._people_analyses[binding['sha256']] = restored
    # _people_bind's existing pc=None path consumes these actual retained rows.
    # Leave _precompute absent rather than faking a model execution receipt.
    return True
