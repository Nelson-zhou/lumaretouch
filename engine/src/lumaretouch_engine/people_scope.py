"""Explicit target-context contract for portrait scopes and existing workflows."""
from . import people_algorithms as A,people_state as S
from . import local_mask_state as SOURCE


def describe():
    return [{'operation_id':op,'parameters':sorted(leaves),'neutral':leaves,
             'target_context':'asset_face_ref_or_explicit_confirmed_map',
             'transfer':'existing_frozen_batch_selected_parameter_leaves',
             'local_assets_transferable':False} for op,leaves in A.defaults().items()]


def legacy_batch_face_check(engine,row,*,live=False):
    path=engine._doc_path if live or row is None else row['path']
    state=engine._people_owner().snapshot();asset=SOURCE.source_digest(path)
    if any(face['asset_sha256']==asset for face in state['faces'].values()):
        return 'unresolved','Retained people edits require the explicit confirmed-face parameter review; a whole legacy recipe has no target map'
    return engine._face_known_single(row,live=live)


def replay_preset(engine,state,**kwargs):
    """Preserve existing single-face presets; never infer a multi-face target.

    The existing preset owner owns receipts, rollback, document fences/history.
    Only changed scalar leaves enter its uniquely evidenced target face.
    """
    if not engine._people_managed():return engine._replay_state(state,**kwargs)
    before=engine._people_owner().snapshot();asset=engine._people_source()['sha256']
    faces=[face for face in before['faces'].values() if face['asset_sha256']==asset and face['enabled']]
    from .eye_light_scope import capture as preset_capture, OP as EYE_LIGHT
    from .blush_makeup_scope import capture as blush_capture, OP as BLUSH
    current=blush_capture(engine,preset_capture(engine));candidate=S.check(before);patches=[]
    fields=dict(zip(A.GEOMETRY,('_brow_shape','_nose_shape','_eye_shape','_mouth_shape')))
    fields[A.LIP]='_lip_makeup'
    # Ephemeral preset transport is consumed here; never a parallel render owner.
    if '_eye_light_preset' in state:fields[EYE_LIGHT]='_eye_light_preset'
    if '_blush_makeup_preset' in state:fields[BLUSH]='_blush_makeup_preset'
    for op,field in fields.items():
        validator=A.specifications()[op][1];left=A.leaves(validator(current.get(field)));right=A.leaves(validator(state.get(field)))
        patches.extend((op,path,value) for path,value in right.items() if left[path]!=value)
    from . import facial_wrinkle_state as W
    left=W.check((current.get('_enhance') or {}).get('amounts',{}));right=W.check((state.get('_enhance') or {}).get('amounts',{}))
    patches.extend((A.WRINKLES,path,value) for path,value in A.leaves(right).items() if A.leaves(left)[path]!=value)
    if not patches:return engine._replay_state(state,**kwargs)
    if len(faces)!=1:raise ValueError('A legacy portrait preset requires one explicit unambiguous enabled face; use people parameter review for multiple faces')
    key=faces[0]['face_instance_id']
    for op,path,value in patches:candidate=S.set_override(candidate,'face',key,op,path,value)
    owner=engine._people_owner()
    try:
        owner.commit(candidate,expected_fence=owner.fence);engine._people_analysis_key=None
        if any(op in (EYE_LIGHT,BLUSH) for op,_,_ in patches):kwargs['strict_local']=True
        return engine._replay_state(state,**kwargs)
    except Exception:
        before['association_revision']=owner.association_fence
        owner.commit(before,expected_fence=owner.fence);engine._people_analysis_key=None
        raise
