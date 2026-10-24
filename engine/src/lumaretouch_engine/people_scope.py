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
    from .virtual_copy_people import row_snapshot
    state=row_snapshot(engine,row) if row is not None and not live else engine._people_owner().snapshot()
    asset=SOURCE.source_digest(path)
    if any(face['asset_sha256']==asset for face in state['faces'].values()):
        return 'unresolved','Retained people edits require the explicit confirmed-face parameter review; a whole legacy recipe has no target map'
    return engine._face_known_single(row,live=live)


def replay_preset(engine,state,**kwargs):
    """Preserve existing single-face presets; never infer a multi-face target.

    The existing preset owner owns receipts, rollback, document fences/history.
    Only changed scalar leaves enter its uniquely evidenced target face.
    """
    from . import enhance_scope as ENHANCE, teeth_colour_apply as TEETH, red_eye_apply as RED_EYE
    from . import sclera_purify_apply as SCLERA_PURIFY
    from . import skin_colour_scope as SKIN_COLOUR
    from . import skin_finish_scope as SKIN_FINISH
    from . import skin_gloss_scope as SKIN_GLOSS
    # Even an otherwise unchanged or legacy preset must not publish success
    # after an active independent eye/tooth layer failed on its own target.
    amounts=ENHANCE.amounts_of(state)
    if TEETH.active(amounts) or RED_EYE.active(amounts):kwargs['strict_local']=True
    if SCLERA_PURIFY.active(amounts):kwargs['strict_local']=True
    skin_recipe=SKIN_COLOUR.S.check(state.get(SKIN_COLOUR.FIELD))
    skin_requested=state.get(SKIN_COLOUR.REQUESTED) is True
    if SKIN_COLOUR.S.active(skin_recipe):kwargs['strict_local']=True
    finish_recipe=SKIN_FINISH.S.check(state.get(SKIN_FINISH.FIELD))
    finish_requested=state.get(SKIN_FINISH.REQUESTED) is True
    if SKIN_FINISH.S.active(finish_recipe):kwargs['strict_local']=True
    gloss_recipe=SKIN_GLOSS.S.check(state.get(SKIN_GLOSS.FIELD))
    gloss_requested=state.get(SKIN_GLOSS.REQUESTED) is True
    if SKIN_GLOSS.S.active(gloss_recipe):kwargs['strict_local']=True
    if not engine._people_managed():
        if skin_requested or SKIN_COLOUR.S.active(skin_recipe):
            raise ValueError('面部肤色预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if finish_requested or SKIN_FINISH.S.active(finish_recipe):
            raise ValueError('美白红润预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if gloss_requested or SKIN_GLOSS.S.active(gloss_recipe):
            raise ValueError('皮肤光泽预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        return engine._replay_state(state,**kwargs)
    before=engine._people_owner().snapshot();asset=engine._people_source()['sha256']
    faces=[face for face in before['faces'].values() if face['asset_sha256']==asset and face['enabled']]
    from .eye_light_scope import capture as preset_capture, OP as EYE_LIGHT
    from .blush_makeup_scope import capture as blush_capture, OP as BLUSH
    from .lipstick_scope import capture as lipstick_capture, OP as LIPSTICK
    from .eyeliner_scope import capture as eyeliner_capture, OP as EYELINER
    from .eyelash_scope import capture as eyelash_capture, OP as EYELASH
    from .brow_makeup_scope import capture as brow_makeup_capture, OP as BROW_MAKEUP
    from .iris_makeup_scope import capture as iris_capture, OP as IRIS
    current=eyelash_capture(engine,brow_makeup_capture(engine,eyeliner_capture(engine,lipstick_capture(engine,blush_capture(engine,preset_capture(engine))))));candidate=S.check(before);patches=[]
    current=iris_capture(engine,current)
    current=SKIN_COLOUR.capture(engine,current)
    current=SKIN_FINISH.capture(engine,current)
    current=SKIN_GLOSS.capture(engine,current)
    skin_involved=(SKIN_COLOUR.FIELD in state and
                   (skin_requested or SKIN_COLOUR.S.active(skin_recipe) or skin_recipe!=current[SKIN_COLOUR.FIELD]))
    if skin_involved:
        # Re-read the current target/evidence/native ABI at replay, not an old
        # captured boolean or a preset's source FaceRef. No graph mutation yet.
        SKIN_COLOUR.install(dict(current),{'recipe':skin_recipe})
        if state.get(SKIN_COLOUR.TARGET)!=current[SKIN_COLOUR.TARGET]:
            raise ValueError('面部肤色预设目标已变化，请重新选择当前人物')
    finish_involved=(SKIN_FINISH.FIELD in state and
                     (finish_requested or SKIN_FINISH.S.active(finish_recipe) or finish_recipe!=current[SKIN_FINISH.FIELD]))
    if finish_involved:
        SKIN_FINISH.install(dict(current),{'recipe':finish_recipe})
        if state.get(SKIN_FINISH.TARGET)!=current[SKIN_FINISH.TARGET]:
            raise ValueError('美白红润预设目标已变化，请重新选择当前人物')
    gloss_involved=(SKIN_GLOSS.FIELD in state and
                    (gloss_requested or SKIN_GLOSS.S.active(gloss_recipe) or gloss_recipe!=current[SKIN_GLOSS.FIELD]))
    if gloss_involved:
        # The captured FaceRef is an admission fence, never reusable highlight
        # evidence. The strict canonical replay recomputes target source facts.
        SKIN_GLOSS.install(dict(current),{'recipe':gloss_recipe})
        if state.get(SKIN_GLOSS.TARGET)!=current[SKIN_GLOSS.TARGET]:
            raise ValueError('皮肤光泽预设目标已变化，请重新选择当前人物')
    fields=dict(zip(A.GEOMETRY,('_brow_shape','_nose_shape','_eye_shape','_mouth_shape')))
    fields[A.LIP]='_lip_makeup'
    # Ephemeral preset transport is consumed here; never a parallel render owner.
    if '_eye_light_preset' in state:fields[EYE_LIGHT]='_eye_light_preset'
    if '_blush_makeup_preset' in state:fields[BLUSH]='_blush_makeup_preset'
    if '_lipstick_preset' in state:fields[LIPSTICK]='_lipstick_preset'
    if '_eyeliner_preset' in state:fields[EYELINER]='_eyeliner_preset'
    if '_iris_makeup_preset' in state:fields[IRIS]='_iris_makeup_preset'
    if '_eyelash_preset' in state:fields[EYELASH]='_eyelash_preset'
    if '_brow_makeup_preset' in state:fields[BROW_MAKEUP]='_brow_makeup_preset'
    if SKIN_COLOUR.FIELD in state:fields[SKIN_COLOUR.OP]=SKIN_COLOUR.FIELD
    if SKIN_FINISH.FIELD in state:fields[SKIN_FINISH.OP]=SKIN_FINISH.FIELD
    if SKIN_GLOSS.FIELD in state:fields[SKIN_GLOSS.OP]=SKIN_GLOSS.FIELD
    for op,field in fields.items():
        validator=A.specifications()[op][1];left=A.leaves(validator(current.get(field)));right=A.leaves(validator(state.get(field)))
        patches.extend((op,path,value) for path,value in right.items() if left[path]!=value)
    from . import facial_wrinkle_state as W
    left=A.leaves(ENHANCE.amounts_of(current));right=A.leaves(ENHANCE.amounts_of(state))
    patches.extend((A.ENHANCE,path,value) for path,value in right.items() if left[path]!=value)
    left=W.check((current.get('_enhance') or {}).get('amounts',{}));right=W.check((state.get('_enhance') or {}).get('amounts',{}))
    patches.extend((A.WRINKLES,path,value) for path,value in A.leaves(right).items() if A.leaves(left)[path]!=value)
    if not patches:return engine._replay_state(state,**kwargs)
    if len(faces)!=1:raise ValueError('A legacy portrait preset requires one explicit unambiguous enabled face; use people parameter review for multiple faces')
    key=faces[0]['face_instance_id']
    if skin_involved and current[SKIN_COLOUR.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('面部肤色预设的当前人物与唯一可应用目标不一致')
    if finish_involved and current[SKIN_FINISH.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('美白红润预设的当前人物与唯一可应用目标不一致')
    if gloss_involved and current[SKIN_GLOSS.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('皮肤光泽预设的当前人物与唯一可应用目标不一致')
    for op,path,value in patches:candidate=S.set_override(candidate,'face',key,op,path,value)
    owner=engine._people_owner()
    try:
        owner.commit(candidate,expected_fence=owner.fence);engine._people_analysis_key=None
        if any(op in (A.ENHANCE,EYE_LIGHT,BLUSH,LIPSTICK,EYELINER,EYELASH,BROW_MAKEUP,IRIS,SKIN_COLOUR.OP,SKIN_FINISH.OP,SKIN_GLOSS.OP) for op,_,_ in patches):kwargs['strict_local']=True
        return engine._replay_state(state,**kwargs)
    except Exception:
        before['association_revision']=owner.association_fence
        owner.commit(before,expected_fence=owner.fence);engine._people_analysis_key=None
        raise
