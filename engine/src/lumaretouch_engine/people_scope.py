"""Explicit target-context contract for portrait scopes and existing workflows."""
from . import people_algorithms as A,people_state as S
from . import local_mask_state as SOURCE


def describe():
    return [{'operation_id':op,'parameters':sorted(leaves),'neutral':leaves,
             'target_context':'asset_face_ref_or_explicit_confirmed_map',
             'transfer':('dormant_scalars_only_active_requires_dedicated_face_visual_review'
                         if op == A.EYE_BAG_PRESERVE.OP else 'existing_frozen_batch_selected_parameter_leaves'),
             'local_assets_transferable':False} for op,leaves in A.defaults().items()]


def legacy_batch_face_check(engine,row,*,live=False):
    path=engine._doc_path if live or row is None else row['path']
    from .virtual_copy_people import row_snapshot
    state=row_snapshot(engine,row) if row is not None and not live else engine._people_owner().snapshot()
    asset=SOURCE.source_digest(path)
    if any(face['asset_sha256']==asset for face in state['faces'].values()):
        return 'unresolved','Retained people edits require the explicit confirmed-face parameter review; a whole legacy recipe has no target map'
    return engine._face_known_single(row,live=live)


def plan_preset(engine,state,*,require_active=True,reviewed_collarbone=False,reviewed_eye_bag=False,reviewed_eye_bag_aliases=False,replace_legacy_eye_bag=False,**kwargs):
    """Preserve existing single-face presets; never infer a multi-face target.

    The existing preset owner owns receipts, rollback, document fences/history.
    Only changed scalar leaves enter its uniquely evidenced target face. This
    preparation does not commit a graph or invoke live replay/rendering.
    """
    from .people_preset_plan import snapshot, require_active_owner
    if type(reviewed_eye_bag) is not bool or type(replace_legacy_eye_bag) is not bool or (replace_legacy_eye_bag and not reviewed_eye_bag):
        raise ValueError('Eye-bag preset review policy requires explicit private boolean choices')
    if type(reviewed_eye_bag_aliases) is not bool or (reviewed_eye_bag_aliases and not reviewed_eye_bag):
        raise ValueError('Shared eye-bag planning requires its exact dedicated review owner')
    managed=engine._people_managed()
    if managed and require_active:require_active_owner(engine)
    from . import enhance_scope as ENHANCE, teeth_colour_apply as TEETH, red_eye_apply as RED_EYE
    from . import sclera_purify_apply as SCLERA_PURIFY
    from . import skin_colour_scope as SKIN_COLOUR
    from . import skin_finish_scope as SKIN_FINISH
    from . import skin_gloss_scope as SKIN_GLOSS
    from . import skin_texture_scope as SKIN_TEXTURE
    from . import skin_evenness_scope as SKIN_EVENNESS
    from . import body_skin_evenness_scope as BODY_SKIN_EVENNESS
    from . import collarbone_scope as COLLARBONE
    from . import body_face_match_scope as BODY_FACE_MATCH
    from . import face_contour_scope as FACE_CONTOUR
    from . import slim_face_scope as SLIM_FACE
    from . import face_size_scope as FACE_SIZE
    from . import lower_face_scope as LOWER_FACE
    from . import mid_face_scope as MID_FACE
    from . import chin_shape_scope as CHIN_SHAPE
    from . import chin_length_scope as CHIN_LENGTH
    from . import philtrum_scope as PHILTRUM
    from . import eye_symmetry_scope as EYE_SYMMETRY
    from . import face_decoration_scope as FACE_DECORATION
    from . import brow_enhance_scope as BROW_ENHANCE
    from . import lip_texture_scope as LIP_TEXTURE
    from . import eye_bag_preserve_scope as EYE_BAG_PRESERVE
    # Even an otherwise unchanged or legacy preset must not publish success
    # after an active independent eye/tooth layer failed on its own target.
    amounts=ENHANCE.amounts_of(state)
    if TEETH.active(amounts) or RED_EYE.active(amounts):kwargs['strict_local']=True
    if SCLERA_PURIFY.active(amounts):kwargs['strict_local']=True
    decoration_recipe=FACE_DECORATION.S.check(state.get(FACE_DECORATION.FIELD))
    decoration_requested=state.get(FACE_DECORATION.REQUESTED) is True
    if FACE_DECORATION.S.active(decoration_recipe):kwargs['strict_local']=True
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
    evenness_recipe=SKIN_EVENNESS.S.check(state.get(SKIN_EVENNESS.FIELD))
    evenness_requested=state.get(SKIN_EVENNESS.REQUESTED) is True
    if SKIN_EVENNESS.S.active(evenness_recipe):kwargs['strict_local']=True
    collarbone_recipe=COLLARBONE.S.check(state.get(COLLARBONE.FIELD))
    collarbone_requested=state.get(COLLARBONE.REQUESTED) is True
    if COLLARBONE.S.active(collarbone_recipe):kwargs['strict_local']=True
    body_evenness_recipe=BODY_SKIN_EVENNESS.S.check(state.get(BODY_SKIN_EVENNESS.FIELD))
    body_evenness_requested=state.get(BODY_SKIN_EVENNESS.REQUESTED) is True
    if BODY_SKIN_EVENNESS.S.active(body_evenness_recipe):kwargs['strict_local']=True
    body_face_match_recipe=BODY_FACE_MATCH.S.check(state.get(BODY_FACE_MATCH.FIELD))
    body_face_match_requested=state.get(BODY_FACE_MATCH.REQUESTED) is True
    if BODY_FACE_MATCH.S.active(body_face_match_recipe):kwargs['strict_local']=True
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
    symmetry_recipe=EYE_SYMMETRY.S.check(state.get(EYE_SYMMETRY.FIELD))
    symmetry_requested=state.get(EYE_SYMMETRY.REQUESTED) is True
    if EYE_SYMMETRY.S.active(symmetry_recipe):kwargs['strict_local']=True
    brow_enhance_recipe=BROW_ENHANCE.S.check(state.get(BROW_ENHANCE.FIELD))
    brow_enhance_requested=state.get(BROW_ENHANCE.REQUESTED) is True
    if BROW_ENHANCE.S.active(brow_enhance_recipe):kwargs['strict_local']=True
    lip_texture_recipe=LIP_TEXTURE.S.check(state.get(LIP_TEXTURE.FIELD))
    lip_texture_requested=state.get(LIP_TEXTURE.REQUESTED) is True
    if LIP_TEXTURE.S.active(lip_texture_recipe):kwargs['strict_local']=True
    eye_bag_recipe=EYE_BAG_PRESERVE.S.check(state.get(EYE_BAG_PRESERVE.FIELD))
    eye_bag_requested=state.get(EYE_BAG_PRESERVE.REQUESTED) is True
    if EYE_BAG_PRESERVE.S.active(eye_bag_recipe):kwargs['strict_local']=True
    if not managed:
        if decoration_requested or decoration_recipe!=FACE_DECORATION.S.neutral():
            raise ValueError('面部装饰预设需要当前明确规范人物，不能静默丢弃或转换为腮红')
        if skin_requested or SKIN_COLOUR.S.active(skin_recipe):
            raise ValueError('面部肤色预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if finish_requested or SKIN_FINISH.S.active(finish_recipe):
            raise ValueError('美白红润预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if gloss_requested or SKIN_GLOSS.S.active(gloss_recipe):
            raise ValueError('皮肤光泽预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if texture_requested or SKIN_TEXTURE.S.active(texture_recipe):
            raise ValueError('皮肤质感预设需要当前明确的规范人物，不能静默丢弃为旧版全图配方')
        if evenness_requested or SKIN_EVENNESS.S.active(evenness_recipe):
            raise ValueError('面部肤色均匀预设需要当前明确的规范人物，不能静默丢弃或转换为旧版磨皮或全图色调配方')
        if collarbone_requested or COLLARBONE.S.active(collarbone_recipe):
            raise ValueError('人工锁骨光影预设需要当前明确的规范人物，不能静默丢弃或转换为面部肤色均匀、旧版磨皮或全图色调配方')
        if body_evenness_requested or BODY_SKIN_EVENNESS.S.active(body_evenness_recipe):
            raise ValueError('身体肤色均匀预设需要当前明确的规范人物，不能静默丢弃或转换为面部肤色均匀、旧版磨皮或全图色调配方')
        if body_face_match_requested or BODY_FACE_MATCH.S.active(body_face_match_recipe):
            raise ValueError('身体与本人面部肤色匹配预设需要当前明确的规范人物，不能静默丢弃或转换为身体均匀、亮度匹配或其他肤色配方')
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
        # A manual reference is dormant intent even with zero strengths. It
        # still belongs to the canonical face, not the legacy whole-image DTO.
        if symmetry_requested or symmetry_recipe!=EYE_SYMMETRY.S.neutral():
            raise ValueError('眼睛对称预设需要当前明确的规范人物，不能静默丢弃或转换为旧版大眼或眼形配方')
        # Unlinked zero amounts are dormant intent, not a legacy no-op which
        # may be silently discarded or converted to added eyebrow makeup.
        if brow_enhance_requested or brow_enhance_recipe!=BROW_ENHANCE.S.neutral():
            raise ValueError('眉毛增强预设需要当前明确的规范人物，不能静默丢弃或转换为眉妆配方')
        if lip_texture_requested or LIP_TEXTURE.S.active(lip_texture_recipe):
            raise ValueError('唇部暗细纹预设需要当前明确的规范人物，不能静默丢弃或转换为口红或 AI 祛瑕配方')
        if eye_bag_requested or eye_bag_recipe!=EYE_BAG_PRESERVE.S.neutral():
            raise ValueError('眼袋保留预设需要当前规范人物，不能静默丢弃或转换旧版眼袋配方')
        return snapshot(state,kwargs)
    owner=engine._people_owner();owner_fence=owner.fence
    before=owner.snapshot();asset=engine._people_source()['sha256']
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
    current=FACE_DECORATION.capture(engine,current)
    current=SKIN_COLOUR.capture(engine,current)
    current=SKIN_FINISH.capture(engine,current)
    current=SKIN_GLOSS.capture(engine,current)
    current=SKIN_TEXTURE.capture(engine,current)
    current=SKIN_EVENNESS.capture(engine,current)
    current=COLLARBONE.capture(engine,current)
    current=BODY_SKIN_EVENNESS.capture(engine,current)
    current=BODY_FACE_MATCH.capture(engine,current)
    current=FACE_CONTOUR.capture(engine,current)
    current=SLIM_FACE.capture(engine,current)
    current=FACE_SIZE.capture(engine,current)
    current=LOWER_FACE.capture(engine,current)
    current=MID_FACE.capture(engine,current)
    current=CHIN_SHAPE.capture(engine,current)
    current=CHIN_LENGTH.capture(engine,current)
    current=PHILTRUM.capture(engine,current)
    current=EYE_SYMMETRY.capture(engine,current)
    current=BROW_ENHANCE.capture(engine,current)
    current=LIP_TEXTURE.capture(engine,current)
    current=EYE_BAG_PRESERVE.capture(engine,current)
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
    evenness_involved=(SKIN_EVENNESS.FIELD in state and
                      (evenness_requested or SKIN_EVENNESS.S.active(evenness_recipe)
                       or evenness_recipe!=current[SKIN_EVENNESS.FIELD]))
    if evenness_involved:
        # Only amount travels. Refresh exact live owner/source/FaceRef and
        # actual face-skin/478 observation before staging; the complete target
        # renderer independently measures reference chroma and composes its
        # typed shift without clearing or copying the legacy skin.broad amount.
        SKIN_EVENNESS.install(dict(current),{'recipe':evenness_recipe})
        if (state.get(SKIN_EVENNESS.TARGET)!=current[SKIN_EVENNESS.TARGET]
                or SKIN_EVENNESS.owner_identity(state)!=SKIN_EVENNESS.owner_identity(current)):
            raise ValueError('面部肤色均匀预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    collarbone_involved=(COLLARBONE.FIELD in state and
                           (collarbone_requested or COLLARBONE.S.active(collarbone_recipe)
                            or collarbone_recipe!=current[COLLARBONE.FIELD]))
    if collarbone_involved:
        # The selected target must independently retain clavicle consent.
        # Re-capture live body/person/source proof before staging amount only;
        # final strict rendering rebuilds manual/semantic coverage and reference.
        if reviewed_collarbone and current.get('_creative_base') is not None:
            # Only the exact read-only preset reviewer enables this branch.
            # Generic legacy replay/install remain fenced for derived sources.
            from .collarbone_derived_preset import validate_target
            validate_target(current,collarbone_recipe)
        else:
            COLLARBONE.install(dict(current),{'recipe':collarbone_recipe})
        if (state.get(COLLARBONE.TARGET)!=current[COLLARBONE.TARGET]
                or COLLARBONE.owner_identity(state)!=COLLARBONE.owner_identity(current)):
            raise ValueError('人工锁骨光影预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    body_evenness_involved=(BODY_SKIN_EVENNESS.FIELD in state and
                           (body_evenness_requested or BODY_SKIN_EVENNESS.S.active(body_evenness_recipe)
                            or body_evenness_recipe!=current[BODY_SKIN_EVENNESS.FIELD]))
    if body_evenness_involved:
        # The selected target must independently retain body-evenness consent.
        # Re-capture live body/person/source proof before staging amount only;
        # final strict rendering rebuilds manual/semantic coverage and reference.
        BODY_SKIN_EVENNESS.install(dict(current),{'recipe':body_evenness_recipe})
        if (state.get(BODY_SKIN_EVENNESS.TARGET)!=current[BODY_SKIN_EVENNESS.TARGET]
                or BODY_SKIN_EVENNESS.owner_identity(state)!=BODY_SKIN_EVENNESS.owner_identity(current)):
            raise ValueError('身体肤色均匀预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    body_face_match_involved=(BODY_FACE_MATCH.FIELD in state and
                             (body_face_match_requested or BODY_FACE_MATCH.S.active(body_face_match_recipe)
                              or body_face_match_recipe!=current[BODY_FACE_MATCH.FIELD]))
    if body_face_match_involved:
        # Both the independently reviewed body and actual own-face observation
        # must still belong to this exact target and immutable effective source.
        # Only amount is staged; strict rendering measures both supports anew.
        BODY_FACE_MATCH.install(dict(current),{'recipe':body_face_match_recipe})
        if (state.get(BODY_FACE_MATCH.TARGET)!=current[BODY_FACE_MATCH.TARGET]
                or BODY_FACE_MATCH.owner_identity(state)!=BODY_FACE_MATCH.owner_identity(current)):
            raise ValueError('身体与本人面部肤色匹配预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
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
    symmetry_involved=(EYE_SYMMETRY.FIELD in state and
                      (symmetry_requested or EYE_SYMMETRY.S.active(symmetry_recipe) or symmetry_recipe!=current[EYE_SYMMETRY.FIELD]))
    if symmetry_involved:
        # Strengths and reference policy travel, never the source's actual eye
        # selection, measurements or pixels. Complete target rendering validates
        # BOTH eyes and resolves auto/manual policy from target-owned evidence.
        EYE_SYMMETRY.install(dict(current),{'recipe':symmetry_recipe})
        if (state.get(EYE_SYMMETRY.TARGET)!=current[EYE_SYMMETRY.TARGET]
                or EYE_SYMMETRY.owner_identity(state)!=EYE_SYMMETRY.owner_identity(current)):
            raise ValueError('眼睛对称预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    brow_enhance_involved=(BROW_ENHANCE.FIELD in state and
                          (brow_enhance_requested or BROW_ENHANCE.S.active(brow_enhance_recipe)
                           or brow_enhance_recipe!=current[BROW_ENHANCE.FIELD]))
    if brow_enhance_involved:
        # Transfer signed intent only. The live owner/source and authentic
        # analysis are re-read; each complete target render measures its own
        # actual brows and adjacent forehead, never donor reference samples.
        BROW_ENHANCE.install(dict(current),{'recipe':brow_enhance_recipe})
        if (state.get(BROW_ENHANCE.TARGET)!=current[BROW_ENHANCE.TARGET]
                or BROW_ENHANCE.owner_identity(state)!=BROW_ENHANCE.owner_identity(current)):
            raise ValueError('眉毛增强预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    lip_texture_involved=(LIP_TEXTURE.FIELD in state and
                         (lip_texture_requested or LIP_TEXTURE.S.active(lip_texture_recipe)
                          or lip_texture_recipe!=current[LIP_TEXTURE.FIELD]))
    if lip_texture_involved:
        # Only the amount travels. Re-read exact live owner/source/FaceRef,
        # observed semantic/478 evidence and native readiness before staging.
        # Full rendering measures target-owned lip ring and dark-furrow support;
        # lipstick review and donor pixels never stand in for that observation.
        LIP_TEXTURE.install(dict(current),{'recipe':lip_texture_recipe})
        if (state.get(LIP_TEXTURE.TARGET)!=current[LIP_TEXTURE.TARGET]
                or LIP_TEXTURE.owner_identity(state)!=LIP_TEXTURE.owner_identity(current)):
            raise ValueError('唇部暗细纹预设的文档、人物归属、有效来源或当前人物已变化，请重新选择')
    eye_bag_involved=(EYE_BAG_PRESERVE.FIELD in state and
                      (eye_bag_requested or eye_bag_recipe!=current[EYE_BAG_PRESERVE.FIELD]))
    if eye_bag_involved:
        if reviewed_eye_bag:
            from .eye_bag_preset_plan import admit
            admit(engine, before, current[EYE_BAG_PRESERVE.TARGET], eye_bag_recipe, reviewed_aliases=reviewed_eye_bag_aliases)
            EYE_BAG_PRESERVE.install_reviewed(dict(current),{'recipe':eye_bag_recipe},replace_legacy=replace_legacy_eye_bag)
        else:
            EYE_BAG_PRESERVE.install(dict(current),{'recipe':eye_bag_recipe})
        if (state.get(EYE_BAG_PRESERVE.TARGET)!=current[EYE_BAG_PRESERVE.TARGET]
                or EYE_BAG_PRESERVE.owner_identity(state)!=EYE_BAG_PRESERVE.owner_identity(current)):
            raise ValueError('眼袋保留预设的文档、人物归属或有效来源已变化，请重新选择')
    decoration_involved=(FACE_DECORATION.FIELD in state and
        (decoration_requested or decoration_recipe!=current[FACE_DECORATION.FIELD]))
    if decoration_involved:
        FACE_DECORATION.install(dict(current),{'recipe':decoration_recipe})
        if (state.get(FACE_DECORATION.TARGET)!=current[FACE_DECORATION.TARGET]
                or FACE_DECORATION.owner_identity(state)!=FACE_DECORATION.owner_identity(current)):
            raise ValueError('面部装饰预设的文档、有效来源或人物归属已改变')
    fields=dict(zip(A.GEOMETRY,('_brow_shape','_nose_shape','_eye_shape','_mouth_shape')))
    fields[A.LIP]='_lip_makeup'
    # Ephemeral preset transport is consumed here; never a parallel render owner.
    if '_eye_light_preset' in state:fields[EYE_LIGHT]='_eye_light_preset'
    if FACE_DECORATION.FIELD in state:fields[FACE_DECORATION.OP]=FACE_DECORATION.FIELD
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
    if SKIN_EVENNESS.FIELD in state:fields[SKIN_EVENNESS.OP]=SKIN_EVENNESS.FIELD
    if COLLARBONE.FIELD in state:fields[COLLARBONE.OP]=COLLARBONE.FIELD
    if BODY_SKIN_EVENNESS.FIELD in state:fields[BODY_SKIN_EVENNESS.OP]=BODY_SKIN_EVENNESS.FIELD
    if BODY_FACE_MATCH.FIELD in state:fields[BODY_FACE_MATCH.OP]=BODY_FACE_MATCH.FIELD
    if FACE_CONTOUR.FIELD in state:fields[FACE_CONTOUR.OP]=FACE_CONTOUR.FIELD
    if SLIM_FACE.FIELD in state:fields[SLIM_FACE.OP]=SLIM_FACE.FIELD
    if FACE_SIZE.FIELD in state:fields[FACE_SIZE.OP]=FACE_SIZE.FIELD
    if LOWER_FACE.FIELD in state:fields[LOWER_FACE.OP]=LOWER_FACE.FIELD
    if MID_FACE.FIELD in state:fields[MID_FACE.OP]=MID_FACE.FIELD
    if CHIN_SHAPE.FIELD in state:fields[CHIN_SHAPE.OP]=CHIN_SHAPE.FIELD
    if CHIN_LENGTH.FIELD in state:fields[CHIN_LENGTH.OP]=CHIN_LENGTH.FIELD
    if PHILTRUM.FIELD in state:fields[PHILTRUM.OP]=PHILTRUM.FIELD
    if EYE_SYMMETRY.FIELD in state:fields[EYE_SYMMETRY.OP]=EYE_SYMMETRY.FIELD
    if BROW_ENHANCE.FIELD in state:fields[BROW_ENHANCE.OP]=BROW_ENHANCE.FIELD
    if LIP_TEXTURE.FIELD in state:fields[LIP_TEXTURE.OP]=LIP_TEXTURE.FIELD
    if EYE_BAG_PRESERVE.FIELD in state:fields[EYE_BAG_PRESERVE.OP]=EYE_BAG_PRESERVE.FIELD
    for op,field in fields.items():
        validator=A.specifications()[op][1];left=A.leaves(validator(current.get(field)));right=A.leaves(validator(state.get(field)))
        patches.extend((op,path,value) for path,value in right.items() if left[path]!=value)
    from . import facial_wrinkle_state as W
    left=A.leaves(ENHANCE.amounts_of(current));right=A.leaves(ENHANCE.amounts_of(state))
    patches.extend((A.ENHANCE,path,value) for path,value in right.items() if left[path]!=value)
    left=W.check((current.get('_enhance') or {}).get('amounts',{}));right=W.check((state.get('_enhance') or {}).get('amounts',{}))
    patches.extend((A.WRINKLES,path,value) for path,value in A.leaves(right).items() if A.leaves(left)[path]!=value)
    if not patches:
        if eye_bag_involved:
            from .eye_bag_preset_plan import check_graph
            check_graph(candidate, current[EYE_BAG_PRESERVE.TARGET], eye_bag_recipe)
        if chin_length_involved:
            # Unchanged active intent still cannot bypass the legacy conflict.
            from .people_resolver import resolve
            values=A.recipes(resolve(candidate,current[CHIN_LENGTH.TARGET]['face_instance_id'],A.defaults()))
            CHIN_LENGTH.S.check_coexistence(values[CHIN_LENGTH.OP],values[A.DEFORM]['small_chin'])
        return snapshot(state,kwargs,owner=owner,owner_fence=owner_fence,before=before,candidate=candidate,
                        target_ref=S.face_ref(faces[0]) if len(faces)==1 else None)
    if len(faces)!=1:raise ValueError('A legacy portrait preset requires one explicit unambiguous enabled face; use people parameter review for multiple faces')
    key=faces[0]['face_instance_id']
    if decoration_involved and current[FACE_DECORATION.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('面部装饰预设的当前人物与唯一应用目标不一致')
    if skin_involved and current[SKIN_COLOUR.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('面部肤色预设的当前人物与唯一可应用目标不一致')
    if finish_involved and current[SKIN_FINISH.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('美白红润预设的当前人物与唯一可应用目标不一致')
    if gloss_involved and current[SKIN_GLOSS.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('皮肤光泽预设的当前人物与唯一可应用目标不一致')
    if texture_involved and current[SKIN_TEXTURE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('皮肤质感预设的当前人物与唯一可应用目标不一致')
    if evenness_involved and current[SKIN_EVENNESS.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('面部肤色均匀预设的当前人物与唯一可应用目标不一致')
    if collarbone_involved and current[COLLARBONE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('人工锁骨光影预设的当前人物与唯一可应用目标不一致')
    if body_evenness_involved and current[BODY_SKIN_EVENNESS.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('身体肤色均匀预设的当前人物与唯一可应用目标不一致')
    if body_face_match_involved and current[BODY_FACE_MATCH.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('身体与本人面部肤色匹配预设的当前人物与唯一可应用目标不一致')
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
    if symmetry_involved and current[EYE_SYMMETRY.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('眼睛对称预设的当前人物与唯一可应用目标不一致')
    if brow_enhance_involved and current[BROW_ENHANCE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('眉毛增强预设的当前人物与唯一可应用目标不一致')
    if lip_texture_involved and current[LIP_TEXTURE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('唇部暗细纹预设的当前人物与唯一可应用目标不一致')
    if eye_bag_involved and current[EYE_BAG_PRESERVE.TARGET]!=S.face_ref(faces[0]):
        raise ValueError('眼袋保留预设的当前人物与唯一可应用目标不一致')
    for op,path,value in patches:candidate=S.set_override(candidate,'face',key,op,path,value)
    if decoration_involved:
        from .face_decoration_project import require_transition
        require_transition(engine,before,candidate)
    if eye_bag_involved:
        from .eye_bag_preset_plan import check_graph
        check_graph(candidate, current[EYE_BAG_PRESERVE.TARGET], eye_bag_recipe)
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
    if brow_enhance_involved:
        # Linked equality belongs to the complete atomic recipe. Never repair
        # an unequal pair by averaging, copying a side, or clearing brow makeup.
        from .people_resolver import resolve
        BROW_ENHANCE.S.check(A.recipes(resolve(candidate,key,A.defaults()))[BROW_ENHANCE.OP])
    if slim_involved or contour_involved:
        # Inspect the complete candidate, including inherited legacy strength
        # and any explicit contour changes in this transaction. Refusal cannot
        # clear/convert saved intent or partially commit another preset module.
        from .people_resolver import resolve
        values=A.recipes(resolve(candidate,key,A.defaults()))
        SLIM_FACE.S.check_coexistence(values[SLIM_FACE.OP],values[A.DEFORM]['slim_face'],values[FACE_CONTOUR.OP])
    # Shared by preview and application: strict rendering requirements cannot
    # depend on whether graph publication has already happened.
    if any(op in (A.ENHANCE,EYE_LIGHT,FACE_DECORATION.OP,BLUSH,LIPSTICK,EYELINER,EYELASH,BROW_MAKEUP,IRIS,SKIN_COLOUR.OP,SKIN_FINISH.OP,SKIN_GLOSS.OP,SKIN_TEXTURE.OP,SKIN_EVENNESS.OP,BODY_SKIN_EVENNESS.OP,COLLARBONE.OP,BODY_FACE_MATCH.OP,FACE_CONTOUR.OP,SLIM_FACE.OP,FACE_SIZE.OP,LOWER_FACE.OP,MID_FACE.OP,CHIN_SHAPE.OP,CHIN_LENGTH.OP,PHILTRUM.OP,EYE_SYMMETRY.OP,BROW_ENHANCE.OP,LIP_TEXTURE.OP,EYE_BAG_PRESERVE.OP) for op,_,_ in patches):kwargs['strict_local']=True
    return snapshot(state,kwargs,owner=owner,owner_fence=owner_fence,before=before,candidate=candidate,
                    patches=patches,target_ref=S.face_ref(faces[0]))


def execute_plan(engine,plan,**kwargs):
    """Publish the exact prepared candidate under the existing transaction.

    This is not another transaction/history owner. The visual preset adapter
    additionally fences document, source, full state and support before entry.
    """
    from .people_preset_plan import PresetReplayPlan, clone_state
    if not isinstance(plan,PresetReplayPlan):raise ValueError('Exact portrait preset plan required')
    options={**plan.kwargs,**kwargs}
    if plan.kwargs.get('strict_local') is True:options['strict_local']=True
    if not plan.managed:
        return engine._replay_state(clone_state(plan.state),**options)
    owner=engine._people_owner()
    if owner is not plan.owner or owner.fence!=plan.owner_fence or owner.snapshot()!=plan.before:
        raise ValueError('Portrait owner changed after preset preparation; no graph was published')
    if not plan.patches:
        return engine._replay_state(clone_state(plan.state),**options)
    committed=False
    try:
        owner.commit(plan.candidate,expected_fence=plan.owner_fence);engine._people_analysis_key=None
        committed=True;published_fence=owner.fence
        return engine._replay_state(clone_state(plan.state),**options)
    except Exception:
        if committed:
            # Never overwrite a later owner's mutation during rollback.
            before=S.check(plan.before);before['association_revision']=owner.association_fence
            owner.commit(before,expected_fence=published_fence);engine._people_analysis_key=None
        raise


def restore_plan(engine,plan,previous_state,*,expected_owner_fence=None,**kwargs):
    """Restore exact prior intent, not a reverse diff against transported leaves.

    Accept only this plan's before/candidate content. Outer preset transaction
    remains responsible for source/document/non-people state and history fences.
    """
    from .people_preset_plan import PresetReplayPlan, clone_state, graph_content
    if not isinstance(plan,PresetReplayPlan):raise ValueError('Exact portrait preset rollback plan required')
    options={**kwargs,'strict_local':True}
    if not plan.managed:return engine._replay_state(clone_state(previous_state),**options)
    owner=engine._people_owner()
    if owner is not plan.owner or (expected_owner_fence is not None and owner.fence!=expected_owner_fence):
        raise ValueError('Portrait owner changed before exact preset rollback')
    current=owner.snapshot();content=graph_content(current)
    before_content=graph_content(plan.before)
    if content not in (before_content,graph_content(plan.candidate)):
        raise ValueError('Preset rollback cannot overwrite unrelated portrait changes')
    if content!=before_content:
        before=S.check(plan.before);before['association_revision']=owner.association_fence
        owner.commit(before,expected_fence=owner.fence);engine._people_analysis_key=None
    return engine._replay_state(clone_state(previous_state),**options)


def replay_preset(engine,state,**kwargs):
    """Legacy and visual preset application share the complete planner."""
    return execute_plan(engine,plan_preset(engine,state,require_active=False,**kwargs))
