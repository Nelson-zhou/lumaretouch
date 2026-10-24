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
    from . import skin_texture_scope as SKIN_TEXTURE
    from . import face_contour_scope as FACE_CONTOUR
    from . import slim_face_scope as SLIM_FACE
    from . import face_size_scope as FACE_SIZE
    from . import lower_face_scope as LOWER_FACE
    from . import mid_face_scope as MID_FACE
    from . import chin_shape_scope as CHIN_SHAPE
    from . import chin_length_scope as CHIN_LENGTH
    from . import philtrum_scope as PHILTRUM
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
    texture_recipe=SKIN_TEXTURE.S.check(state.get(SKIN_TEXTURE.FIELD))
    texture_requested=state.get(SKIN_TEXTURE.REQUESTED) is True
    if SKIN_TEXTURE.S.active(texture_recipe):kwargs['strict_local']=True
    contour_recipe=FACE_CONTOUR.S.check(state.get(FACE_CONTOUR.FIELD))
    contour_requested=state.get(FACE_CONTOUR.REQUESTED) is True
    if FACE_CONTOUR.S.active(contour_recipe):kwargs['strict_local']=True
    slim_recipe=SLIM_FACE.S.check(state.get(SLIM_FACE.FIELD))
    slim_requested=state.get(SLIM_FACE.REQUESTED) is True
    if SLIM_FACE.S.active(slim_recipe):kwargs['strict_local']=True
    size_recipe=FACE_SIZE.S.check(state.get(FACE_SIZE.FIELD))
    size_requested=state.get(FACE_SIZE.REQUESTED) is True
    if FACE_SIZE.S.active(size_recipe):kwargs['strict_local']=True
    lower_recipe=LOWER_FACE.S.check(state.get(LOWER_FACE.FIELD))
    lower_requested=state.get(LOWER_FACE.REQUESTED) is True
    if LOWER_FACE.S.active(lower_recipe):kwargs['strict_local']=True
    mid_recipe=MID_FACE.S.check(state.get(MID_FACE.FIELD))
    mid_requested=state.get(MID_FACE.REQUESTED) is True
    if MID_FACE.S.active(mid_recipe):kwargs['strict_local']=True
    chin_recipe=CHIN_SHAPE.S.check(state.get(CHIN_SHAPE.FIELD))
    chin_requested=state.get(CHIN_SHAPE.REQUESTED) is True
    if CHIN_SHAPE.S.active(chin_recipe):kwargs['strict_local']=True
    chin_length_recipe=CHIN_LENGTH.S.check(state.get(CHIN_LENGTH.FIELD))
    chin_length_requested=state.get(CHIN_LENGTH.REQUESTED) is True
    if CHIN_LENGTH.S.active(chin_length_recipe):kwargs['strict_local']=True
    philtrum_recipe=PHILTRUM.S.check(state.get(PHILTRUM.FIELD))
    philtrum_requested=state.get(PHILTRUM.REQUESTED) is True
    if PHILTRUM.S.active(philtrum_recipe):kwargs['strict_local']=True
    if not engine._people_managed():
        if skin_requested or SKIN_COLOUR.S.active(skin_recipe):
            raise ValueError('面部肤色预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if finish_requested or SKIN_FINISH.S.active(finish_recipe):
            raise ValueError('美白红润预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if gloss_requested or SKIN_GLOSS.S.active(gloss_recipe):
            raise ValueError('皮肤光泽预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if texture_requested or SKIN_TEXTURE.S.active(texture_recipe):
            raise ValueError('皮肤质感预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if contour_requested or FACE_CONTOUR.S.active(contour_recipe):
            raise ValueError('面部轮廓预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if slim_requested or SLIM_FACE.S.active(slim_recipe):
            raise ValueError('新版瘦脸预设需要当前明确的规范人物，不能静默丢弃或转换为旧版全图配方')
        if size_requested or FACE_SIZE.S.active(size_recipe):
            raise ValueError('脸部大小预设需要当前明确的规范人物，不能静默丢弃或转换为瘦脸配方')
        if lower_requested or LOWER_FACE.S.active(lower_recipe):
            raise ValueError('下庭长度预设需要当前明确的规范人物，不能静默丢弃或转换为旧版小下巴配方')
        if mid_requested or MID_FACE.S.active(mid_recipe):
            raise ValueError('中庭长度预设需要当前明确的规范人物，不能静默丢弃或转换为下庭长度或旧版小下巴配方')
        if chin_requested or CHIN_SHAPE.S.active(chin_recipe):
            raise ValueError('新版尖下巴预设需要当前明确的规范人物，不能静默丢弃或转换为旧版小下巴、长度或瘦脸配方')
        if chin_length_requested or CHIN_LENGTH.S.active(chin_length_recipe):
            raise ValueError('新版下巴长度预设需要当前明确的规范人物，不能静默丢弃或转换为旧版小下巴、尖下巴或其他长度配方')
        if philtrum_requested or PHILTRUM.S.active(philtrum_recipe):
            raise ValueError('人中预设需要当前明确的规范人物，不能静默丢弃或转换为中庭、下庭或下巴配方')
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
    current=SKIN_TEXTURE.capture(engine,current)
    current=FACE_CONTOUR.capture(engine,current)
    current=SLIM_FACE.capture(engine,current)
    current=FACE_SIZE.capture(engine,current)
    current=LOWER_FACE.capture(engine,current)
    current=MID_FACE.capture(engine,current)
    current=CHIN_SHAPE.capture(engine,current)
    current=CHIN_LENGTH.capture(engine,current)
    current=PHILTRUM.capture(engine,current)
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
    texture_involved=(SKIN_TEXTURE.FIELD in state and
                      (texture_requested or SKIN_TEXTURE.S.active(texture_recipe) or texture_recipe!=current[SKIN_TEXTURE.FIELD]))
    if texture_involved:
        # Captured target identity is only a fence. The canonical renderer
        # measures both detail scales from this target's own effective source.
        SKIN_TEXTURE.install(dict(current),{'recipe':texture_recipe})
        if state.get(SKIN_TEXTURE.TARGET)!=current[SKIN_TEXTURE.TARGET]:
            raise ValueError('皮肤质感预设目标已变化，请重新选择当前人物')
    contour_involved=(FACE_CONTOUR.FIELD in state and
                      (contour_requested or FACE_CONTOUR.S.active(contour_recipe) or contour_recipe!=current[FACE_CONTOUR.FIELD]))
    if contour_involved:
        # The exact owner and FaceRef fence intent only; target-local source
        # geometry, photometry and neighbour safety are recomputed by rendering.
        FACE_CONTOUR.install(dict(current),{'recipe':contour_recipe})
        if (state.get(FACE_CONTOUR.TARGET)!=current[FACE_CONTOUR.TARGET]
                or FACE_CONTOUR.owner_identity(state)!=FACE_CONTOUR.owner_identity(current)):
            raise ValueError('面部轮廓预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    slim_involved=(SLIM_FACE.FIELD in state and
                   (slim_requested or SLIM_FACE.S.active(slim_recipe) or slim_recipe!=current[SLIM_FACE.FIELD]))
    if slim_involved:
        # Freeze only identity, never source geometry. Re-read live target skin,
        # landmarks and native readiness before staging any canonical edit.
        SLIM_FACE.install(dict(current),{'recipe':slim_recipe})
        if (state.get(SLIM_FACE.TARGET)!=current[SLIM_FACE.TARGET]
                or SLIM_FACE.owner_identity(state)!=SLIM_FACE.owner_identity(current)):
            raise ValueError('新版瘦脸预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    size_involved=(FACE_SIZE.FIELD in state and
                   (size_requested or FACE_SIZE.S.active(size_recipe) or size_recipe!=current[FACE_SIZE.FIELD]))
    if size_involved:
        # Only portable amount is staged. Live owner, effective source, exact
        # FaceRef, observed skin/478 landmarks and the dedicated ABI are reread.
        FACE_SIZE.install(dict(current),{'recipe':size_recipe})
        if (state.get(FACE_SIZE.TARGET)!=current[FACE_SIZE.TARGET]
                or FACE_SIZE.owner_identity(state)!=FACE_SIZE.owner_identity(current)):
            raise ValueError('脸部大小预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    lower_involved=(LOWER_FACE.FIELD in state and
                    (lower_requested or LOWER_FACE.S.active(lower_recipe) or lower_recipe!=current[LOWER_FACE.FIELD]))
    if lower_involved:
        # Portable signed length only. Re-read the live effective source, exact
        # owner/FaceRef, observed skin/478 evidence and separate native capability.
        LOWER_FACE.install(dict(current),{'recipe':lower_recipe})
        if (state.get(LOWER_FACE.TARGET)!=current[LOWER_FACE.TARGET]
                or LOWER_FACE.owner_identity(state)!=LOWER_FACE.owner_identity(current)):
            raise ValueError('下庭长度预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    mid_involved=(MID_FACE.FIELD in state and
                  (mid_requested or MID_FACE.S.active(mid_recipe) or mid_recipe!=current[MID_FACE.FIELD]))
    if mid_involved:
        # Portable signed length only. The complete target renderer owns the
        # midface proxy map and composition; never reuse donor/original analysis.
        MID_FACE.install(dict(current),{'recipe':mid_recipe})
        if (state.get(MID_FACE.TARGET)!=current[MID_FACE.TARGET]
                or MID_FACE.owner_identity(state)!=MID_FACE.owner_identity(current)):
            raise ValueError('中庭长度预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    chin_involved=(CHIN_SHAPE.FIELD in state and
                   (chin_requested or CHIN_SHAPE.S.active(chin_recipe) or chin_recipe!=current[CHIN_SHAPE.FIELD]))
    if chin_involved:
        # Only the bilateral parameters travel. Exact owner/FaceRef admission is
        # refreshed here; target-local geometry and composition are never reused.
        CHIN_SHAPE.install(dict(current),{'recipe':chin_recipe})
        if (state.get(CHIN_SHAPE.TARGET)!=current[CHIN_SHAPE.TARGET]
                or CHIN_SHAPE.owner_identity(state)!=CHIN_SHAPE.owner_identity(current)):
            raise ValueError('新版尖下巴预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    chin_length_involved=(CHIN_LENGTH.FIELD in state and
                         (chin_length_requested or CHIN_LENGTH.S.active(chin_length_recipe) or chin_length_recipe!=current[CHIN_LENGTH.FIELD]))
    if chin_length_involved:
        # Identity admission is re-read from the live target. Its lip-plane/chin
        # support is rebuilt by the complete renderer, never imported or cached.
        CHIN_LENGTH.install(dict(current),{'recipe':chin_length_recipe})
        if (state.get(CHIN_LENGTH.TARGET)!=current[CHIN_LENGTH.TARGET]
                or CHIN_LENGTH.owner_identity(state)!=CHIN_LENGTH.owner_identity(current)):
            raise ValueError('新版下巴长度预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    philtrum_involved=(PHILTRUM.FIELD in state and
                      (philtrum_requested or PHILTRUM.S.active(philtrum_recipe) or philtrum_recipe!=current[PHILTRUM.FIELD]))
    if philtrum_involved:
        # The scalar travels, never donor nose/lip boundaries or gap evidence.
        # Re-read the live exact owner, effective source, FaceRef and capability;
        # the complete target renderer independently rebuilds its own anatomy.
        PHILTRUM.install(dict(current),{'recipe':philtrum_recipe})
        if (state.get(PHILTRUM.TARGET)!=current[PHILTRUM.TARGET]
                or PHILTRUM.owner_identity(state)!=PHILTRUM.owner_identity(current)):
            raise ValueError('人中预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
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
    if SKIN_TEXTURE.FIELD in state:fields[SKIN_TEXTURE.OP]=SKIN_TEXTURE.FIELD
    if FACE_CONTOUR.FIELD in state:fields[FACE_CONTOUR.OP]=FACE_CONTOUR.FIELD
    if SLIM_FACE.FIELD in state:fields[SLIM_FACE.OP]=SLIM_FACE.FIELD
    if FACE_SIZE.FIELD in state:fields[FACE_SIZE.OP]=FACE_SIZE.FIELD
    if LOWER_FACE.FIELD in state:fields[LOWER_FACE.OP]=LOWER_FACE.FIELD
    if MID_FACE.FIELD in state:fields[MID_FACE.OP]=MID_FACE.FIELD
    if CHIN_SHAPE.FIELD in state:fields[CHIN_SHAPE.OP]=CHIN_SHAPE.FIELD
    if CHIN_LENGTH.FIELD in state:fields[CHIN_LENGTH.OP]=CHIN_LENGTH.FIELD
    if PHILTRUM.FIELD in state:fields[PHILTRUM.OP]=PHILTRUM.FIELD
    for op,field in fields.items():
        validator=A.specifications()[op][1];left=A.leaves(validator(current.get(field)));right=A.leaves(validator(state.get(field)))
        patches.extend((op,path,value) for path,value in right.items() if left[path]!=value)
    from . import facial_wrinkle_state as W
    left=A.leaves(ENHANCE.amounts_of(current));right=A.leaves(ENHANCE.amounts_of(state))
    patches.extend((A.ENHANCE,path,value) for path,value in right.items() if left[path]!=value)
    left=W.check((current.get('_enhance') or {}).get('amounts',{}));right=W.check((state.get('_enhance') or {}).get('amounts',{}))
    patches.extend((A.WRINKLES,path,value) for path,value in A.leaves(right).items() if A.leaves(left)[path]!=value)
    if not patches:
        if chin_length_involved:
            # Unchanged active intent still cannot bypass the legacy conflict.
            from .people_resolver import resolve
            values=A.recipes(resolve(candidate,current[CHIN_LENGTH.TARGET]['face_instance_id'],A.defaults()))
            CHIN_LENGTH.S.check_coexistence(values[CHIN_LENGTH.OP],values[A.DEFORM]['small_chin'])
        return engine._replay_state(state,**kwargs)
    if len(faces)!=1:raise ValueError('A legacy portrait preset requires one explicit unambiguous enabled face; use people parameter review for multiple faces')
    key=faces[0]['face_instance_id']
    if skin_involved and current[SKIN_COLOUR.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('面部肤色预设的当前人物与唯一可应用目标不一致')
    if finish_involved and current[SKIN_FINISH.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('美白红润预设的当前人物与唯一可应用目标不一致')
    if gloss_involved and current[SKIN_GLOSS.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('皮肤光泽预设的当前人物与唯一可应用目标不一致')
    if texture_involved and current[SKIN_TEXTURE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('皮肤质感预设的当前人物与唯一可应用目标不一致')
    if contour_involved and current[FACE_CONTOUR.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('面部轮廓预设的当前人物与唯一可应用目标不一致')
    if slim_involved and current[SLIM_FACE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('新版瘦脸预设的当前人物与唯一可应用目标不一致')
    if size_involved and current[FACE_SIZE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('脸部大小预设的当前人物与唯一可应用目标不一致')
    if lower_involved and current[LOWER_FACE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('下庭长度预设的当前人物与唯一可应用目标不一致')
    if mid_involved and current[MID_FACE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('中庭长度预设的当前人物与唯一可应用目标不一致')
    if chin_involved and current[CHIN_SHAPE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('新版尖下巴预设的当前人物与唯一可应用目标不一致')
    if chin_length_involved and current[CHIN_LENGTH.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('新版下巴长度预设的当前人物与唯一可应用目标不一致')
    if philtrum_involved and current[PHILTRUM.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('人中预设的当前人物与唯一可应用目标不一致')
    for op,path,value in patches:candidate=S.set_override(candidate,'face',key,op,path,value)
    if chin_length_involved:
        # Resolve inheritance only after all selected modules have been staged.
        # Scalar preset install never inserts an old-small_chin reset or converts
        # its numeric value. A conflict rejects the whole transaction unchanged.
        from .people_resolver import resolve
        values=A.recipes(resolve(candidate,key,A.defaults()))
        CHIN_LENGTH.S.check_coexistence(values[CHIN_LENGTH.OP],values[A.DEFORM]['small_chin'])
    if chin_involved:
        # Linked equality belongs to the complete recipe, not intermediate
        # sparse writes. Validate the fully staged candidate before publication.
        from .people_resolver import resolve
        CHIN_SHAPE.S.check(A.recipes(resolve(candidate,key,A.defaults()))[CHIN_SHAPE.OP])
    if slim_involved or contour_involved:
        # Inspect the complete candidate, including inherited legacy strength
        # and any explicit contour changes in this transaction. Refusal cannot
        # clear/convert saved intent or partially commit another preset module.
        from .people_resolver import resolve
        values=A.recipes(resolve(candidate,key,A.defaults()))
        SLIM_FACE.S.check_coexistence(values[SLIM_FACE.OP],values[A.DEFORM]['slim_face'],values[FACE_CONTOUR.OP])
    owner=engine._people_owner()
    try:
        owner.commit(candidate,expected_fence=owner.fence);engine._people_analysis_key=None
        # Face size, face lengths, philtrum and chin shape compose in the complete
        # canonical renderer. Never clear/convert other intent for local success.
        if any(op in (A.ENHANCE,EYE_LIGHT,BLUSH,LIPSTICK,EYELINER,EYELASH,BROW_MAKEUP,IRIS,SKIN_COLOUR.OP,SKIN_FINISH.OP,SKIN_GLOSS.OP,SKIN_TEXTURE.OP,FACE_CONTOUR.OP,SLIM_FACE.OP,FACE_SIZE.OP,LOWER_FACE.OP,MID_FACE.OP,CHIN_SHAPE.OP,CHIN_LENGTH.OP,PHILTRUM.OP) for op,_,_ in patches):kwargs['strict_local']=True
        return engine._replay_state(state,**kwargs)
    except Exception:
        before['association_revision']=owner.association_fence
        owner.commit(before,expected_fence=owner.fence);engine._people_analysis_key=None
        raise
