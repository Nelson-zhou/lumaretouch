"""Strict hair-only replay of already retained measured inputs, without inference.

This is not a replacement face producer. It restores original hash-pinned
landmark bytes only when no requested non-hair operator needs missing semantic
inputs. Absent exclusion/skin stays None, never a fabricated all-zero field.
"""
import numpy as np
from . import hair_colour_state as H, hair_colour_assets as ASSETS, hair_colour_evidence as FIELDS
from . import people_state as P, people_algorithms as A, people_resolver as R
from . import people_retained_analysis as RA, people_binding as B
from . import hair_unification_state as U, hair_unification_assets as UA
from . import hair_volume_state as V, hair_volume_support as VA, hair_volume_project as VP
from . import hair_smoothing_state as SM, hair_smoothing_support as SMA, hair_smoothing_project as SMP
from .people_support_assets import content_digest


def _retained_smoothing_support(face, support_bank, hair_bank, evidence_bank):
    """Validate dormant immutable consent without rebinding it to live ownership."""
    ref = P.face_ref(face); descriptor = face['local_assets'].get(SMA.KIND)
    if descriptor is None:
        raise ValueError('Hair smoothing replay lacks its independent retained visible-hair support')
    record = SMA.check_record(support_bank.get(descriptor['content_sha256']))
    if (record['face_ref'] != ref
            or descriptor != {'owner': ref, 'kind': SMA.KIND, 'content_sha256': content_digest(record)}):
        raise ValueError('Hair smoothing replay support is changed or owned by another exact FaceRef')
    SMA.retained_support(record, hair_bank, evidence_bank)
    return record


def analyses(engine, state, binding):
    """Return exact retained rows, or None if the normal analysis path is needed.

    Caller must use this only for the explicitly supplied original source and
    preserve normal publication/render/export admission. No new face is made,
    no detector count or face box is treated as hair-instance ownership.
    """
    state = P.check(state); binding = ASSETS.source(binding)
    if H.OPERATION not in A.specifications(): return None  # Not integrated yet.
    if (any(row['operation_id'] == V.OP for row in state['overrides'])
            or any(VA.KIND in face['local_assets'] for face in state['faces'].values())):
        VP.validate_graph(state)  # Volume has no group/person/batch admission.
    smoothing_declared = (any(row['operation_id'] == SM.OP for row in state['overrides'])
        or any(SMA.KIND in face['local_assets'] for face in state['faces'].values()))
    if smoothing_declared:
        SMP.validate_graph(state)  # No inherited/cohort activation through replay.
    smoothing_targets = {row['target_id'] for row in state['overrides']
        if row['operation_id'] == SM.OP and row['scope'] == 'face' and row['value'] != 0}
    smoothing_active_faces = {key for key, face in state['faces'].items()
        if face['asset_sha256'] == binding['sha256'] and face['enabled'] and key in smoothing_targets}
    smoothing_faces = {key for key, face in state['faces'].items()
        if face['asset_sha256'] == binding['sha256']
        and (SMA.KIND in face['local_assets'] or key in smoothing_active_faces)}
    defaults = A.defaults(); specs = A.specifications(); result = {}; has_hair = bool(smoothing_faces)
    evidence_bank = engine.__dict__.get('_hair_colour_evidence', {})
    measured = FIELDS.for_source(evidence_bank, binding)
    if measured is None:
        if smoothing_faces:
            raise ValueError('Hair smoothing replay lost its retained measured evidence; no model inference fallback')
        return None
    semantic_id = FIELDS.identity(measured)
    if smoothing_faces:
        support_bank = engine.__dict__.get('_people_support', {})
        hair_bank = engine.__dict__.get('_hair_colour_assets', {})
        # Historical pointers remain exact even when neutral or disabled. They
        # do not authorize rendering and must not be rebound to a later census
        # or current ownership edit merely to reopen or detach that old review.
        for key in sorted(smoothing_faces):
            face = state['faces'][key]
            record = _retained_smoothing_support(face, support_bank, hair_bank, evidence_bank)
            if record['source'] != binding or record['row']['semantic_evidence_sha256'] != semantic_id:
                raise ValueError('Hair smoothing replay source or measured semantics differ from the reviewed support')
            if key in smoothing_active_faces:
                # Only enabled nonzero intent needs current census/ownership.
                # Dormant consent cannot become active through historical replay.
                SMA.resolve(state, support_bank, P.face_ref(face), hair_bank)
    if smoothing_active_faces:
        # For active rendering all competing claims, including disabled owners,
        # must be exact/manual. Actual collision/eligibility is still checked
        # by full-source preparation, never settled by order during replay.
        for _, owner in SMA._owners(state, binding, hair_bank):
            if owner['semantic_evidence_sha256'] != semantic_id:
                raise ValueError('Hair smoothing replay retained owners disagree about measured semantic evidence')
    for face in state['faces'].values():
        if face['asset_sha256'] != binding['sha256'] or not face['enabled']: continue
        resolved = R.resolve(state, face['face_instance_id'], defaults)
        if resolved['conflicts']: return None
        recipes = A.recipes(resolved)
        if any(value != specs[operation][0] for operation, value in recipes.items()
               if operation not in (H.OPERATION, U.OP, V.OP, SM.OP)): return None
        if any(kind not in (ASSETS.KIND, UA.KIND, VA.KIND, SMA.KIND) for kind in face['local_assets']): return None
        volume = recipes.get(V.OP, V.neutral())
        if VA.KIND in face['local_assets']:
            support = VA.resolve(state, engine.__dict__.get('_people_support', {}), P.face_ref(face))
            if support['source'] != binding:
                raise ValueError('Retained hair-volume replay belongs to another exact source')
            VA.verify_evidence(support, measured)
            VA.support_vector(support, volume)
        elif V.active(volume):
            raise ValueError('Retained hair-volume replay lacks its reviewed per-region support')
        if UA.KIND in face['local_assets']:
            reference = UA.resolve(state, engine.__dict__.get('_hair_unification_assets', {}), P.face_ref(face), engine.__dict__.get('_hair_colour_assets', {}))
            if reference['semantic_evidence_sha256'] != semantic_id:
                raise ValueError('Retained hair-unification replay evidence differs from reviewed samples')
        if U.active(recipes[U.OP]) and UA.KIND not in face['local_assets']: return None
        recipe = recipes[H.OPERATION]
        smoothing = recipes.get(SM.OP, SM.neutral())
        wanted = (SM.active(smoothing) or SMA.KIND in face['local_assets']
                  or V.active(volume) or VA.KIND in face['local_assets'] or U.active(recipes[U.OP])
                  or UA.KIND in face['local_assets'] or H.active(recipe)
                  or ASSETS.KIND in face['local_assets'] or recipe != H.neutral())
        if not wanted: continue
        has_hair = True; ref = P.face_ref(face)
        ASSETS.verify_face(state, ref, binding)
        if ASSETS.KIND in face['local_assets']:
            support = ASSETS.resolve(state, engine.__dict__.get('_hair_colour_assets', {}), ref)
            if support['semantic_evidence_sha256'] != semantic_id: raise ValueError('Retained hair replay evidence differs from reviewed support')
        elif H.active(recipe): return None  # Missing ownership is not repaired here.
        row = engine.__dict__.get('_people_landmarks', {}).get(RA.key(ref))
        if row is None or row['face_ref'] != ref or row['evidence'] != face['evidence']:
            if ref['face_instance_id'] in smoothing_faces:
                raise ValueError('Hair smoothing replay lost exact retained measured landmarks; no model inference fallback')
            return None
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
