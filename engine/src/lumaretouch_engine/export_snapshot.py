from copy import deepcopy
from . import id_background_state as IDBS
from . import photo_grain_state as PGS
from . import fringe_repair_state as FRS
from . import primary_calibration_state as PCS
from . import colour_grading_state as CGS
from . import selective_colour_state as SCSL
from . import colour_editor_state as CES
"""One stored-state to export snapshot mapping, shared by active and other docs."""
from . import local_mask_state as LM, local_grade_layers as LG, effect_recovery_state as ERS
from . import manual_liquify_state as MLS, studio_background_state as SBS, optics_state as OPS, sky_replacement_state as SKS
from . import lip_makeup_state as LIPS, brow_shape_state as BROWS, nose_shape_state as NOSES, eye_shape_state as EYES, mouth_shape_state as MOUTHS
from . import photo_detail_state as PDS
from . import reference_color_state as RCS, white_balance_recipe as WB, extended_tone_state as ETS
from .ops import curves as CURVES, levels as LEVELS


def state_to_export_snap(self,st,*,device,scale,upscale_backend,sharpen,source_path=None,people_graph=None,people_context=None,people_document_id=None):
    from .creative_document_base import check as check_creative_base
    creative_base = deepcopy(check_creative_base(st.get("_creative_base")))
    # Select only observations measured on this exact immutable pixel source.
    # Original graph slices remain retained for history but cannot enter the
    # returned composite's portrait snapshot. Body owns a separate source proof.
    from .people_document_owner import capture as capture_owner
    document_id=capture_owner(self,st,source_path or self._doc_path,
        document_id=people_document_id,context_supplied=people_context is not None)
    people = self._people_export_snapshot(st,source_path,people_graph,context=people_context,document_id=document_id)
    snap = dict(people_document_id=document_id,creative_base=creative_base, id_background=IDBS.check(st.get("_id_background")), id_background_bundle=deepcopy(st.get("_id_background_bundle")), people=people, strength=float(st.get("_strength", 0.0)),
                    params=dict(st.get("_params") or self._params),
                    grade=tuple(st.get("_grade", (0.0, 0.0, 0.0, 1.0))),
                    grade_scope=str(st.get("_grade_scope") or "all"),
                    grade_mask=st.get("_grade_mask"), local_masks=LM.check(st.get("_local_masks")), local_mask_owner=LM.owner_from_state(st), local_grade_groups=LG.check(st.get("_local_grade_layers")),
                    effect_recovery=ERS.check(st.get("_effect_recovery")), manual_liquify=MLS.check(st.get("_manual_liquify")), studio_background=SBS.check(st.get("_studio_background")), optics=OPS.check(st.get("_optics")), sky_replacement=SKS.check(st.get("_sky_replacement")), lip_makeup=LIPS.check(st.get("_lip_makeup")), brow_shape=BROWS.check(st.get("_brow_shape")), brow_shape_owner=st.get("_brow_shape_owner"), nose_shape=NOSES.check(st.get("_nose_shape")), nose_shape_owner=st.get("_nose_shape_owner"), eye_shape=EYES.check(st.get("_eye_shape")), eye_shape_owner=st.get("_eye_shape_owner"), reference_color=RCS.check(st.get("_reference_color")), mouth_shape=MOUTHS.check(st.get("_mouth_shape")), mouth_shape_owner=st.get("_mouth_shape_owner"),
                    extended_tone=ETS.check(st.get("_extended_tone")), photo_detail=PDS.check(st.get("_photo_detail")), photo_grain=PGS.from_state(st), fringe_repair=FRS.from_state(st), colour_grading=CGS.from_state(st), selective_colour=SCSL.from_state(st), colour_editor=CES.from_state(st), primary_calibration=PCS.from_state(st),
                    exposure=tuple(st.get("_exposure", (0.0,) * 7)),
                    exposure_ref_k=st.get("_exposure_ref_k"),
                    wb_options=WB.normalize_state(st)["_wb_options"],
                    hsl=tuple(st.get("_hsl", (0.0,) * 24)),
                    curves=CURVES.check_curves(st.get("_curves")), levels=LEVELS.check_levels(st.get("_levels")),
                    crop_rect=tuple(st.get("_crop_rect", (0.0, 0.0, 1.0, 1.0))),
                    crop_rotation=float(st.get("_crop_rotation", 0.0)),
                    lut=st.get("_lut"), lut_amount=float(st.get("_lut_amount", 0.0)),
                    light=dict(st.get("_light") or self._light),
                    light_ops=list(st.get("_light_ops") or []),
                    repair_ops=list(st.get("_repair_ops") or []),
                    deform=dict(st.get("_deform") or {"amounts": {}, "built": False}),
                    deform_defer=bool(st.get("_deform_defer")),
                    fabric_amount=float(st.get("_fabric_amount", 0.0)),
                    hand_shape=deepcopy(st.get("_hand_shape")),
                    hand_tone=deepcopy(st.get("_hand_tone")),
                    limb_vein=deepcopy(st.get("_limb_vein")),
                    fabric_sweat=deepcopy(st.get("_fabric_sweat")),
                    enhance=dict(st.get("_enhance") or {"amounts": {}, "built": False}),
                    enhance_defer=bool(st.get("_enhance_defer")),
                    channel=st.get("_channel"),
                    _bg=dict(st.get("_bg") or {}),
                    precompute=st.get("_precompute"),
                    device=device, scale=scale, upscale_backend=upscale_backend,
                    sharpen=sharpen)
    if snap['fringe_repair']['source'] is not None:
        from .creative_derived_source import binding as source_binding
        path = source_path or self._doc_path
        before = LM.file_stamp(path)
        dimensions = None
        if creative_base is None:
            rows = [row for row in self._docs if row.get('document_id') == document_id and row.get('path') == path]
            if document_id is None or len(rows) != 1:
                raise ValueError('Fringe repair snapshot lacks its exact source document')
            dimensions = (rows[0].get('src_w'), rows[0].get('src_h'))
        source = source_binding(st, path, dimensions)
        if source != snap['fringe_repair']['source'] or LM.file_stamp(path) != before:
            raise ValueError('Fringe repair snapshot source changed or belongs to another image')
        snap['fringe_repair_source'] = source
        snap['fringe_repair_path'] = path
        snap['fringe_repair_stamp'] = list(before)
    if snap['fabric_sweat'] is not None:
        from .fabric_sweat_state import check as sweat_check
        from .creative_derived_source import binding as sweat_source
        from .creative_derived_repairs import stack_digest
        recipe = sweat_check(snap['fabric_sweat'])
        path = source_path or self._doc_path
        rows = [r for r in self._docs if r.get('document_id') == document_id and r.get('path') == path]
        if len(rows) != 1: raise ValueError('衣物汗渍导出缺少精确来源文档')
        current_source = sweat_source(st,path,(rows[0].get('src_w'),rows[0].get('src_h')))
        if current_source != recipe['source']: raise ValueError('衣物汗渍禁止跨照片复制参考')
        snap['fabric_sweat_repair_sha256'] = stack_digest(st)
        if snap['fabric_sweat_repair_sha256'] != recipe['repair_sha256']:
            raise ValueError('衣物汗渍修复来源已改变，需要重新审核')
    if snap['limb_vein'] is not None:
        from .limb_vein_state import check as vein_check
        from .creative_derived_source import binding as vein_source
        from .creative_derived_repairs import stack_digest
        recipe = vein_check(snap['limb_vein'])
        path = source_path or self._doc_path
        rows = [r for r in self._docs if r.get('document_id') == document_id and r.get('path') == path]
        if len(rows) != 1: raise ValueError('肢体青筋导出缺少精确来源文档')
        current_source = vein_source(st,path,(rows[0].get('src_w'),rows[0].get('src_h')))
        if current_source != recipe['source']: raise ValueError('肢体青筋禁止跨照片复制参考')
        snap['limb_vein_repair_sha256'] = stack_digest(st)
        if snap['limb_vein_repair_sha256'] != recipe['repair_sha256']:
            raise ValueError('肢体青筋修复来源已改变，需要重新审核')
    if snap['hand_tone'] is not None:
        from .hand_tone_state import check as hand_tone_check
        from .creative_derived_source import binding as hand_tone_source
        from .creative_derived_repairs import stack_digest
        recipe = hand_tone_check(snap['hand_tone'])
        path = source_path or self._doc_path
        rows = [r for r in self._docs if r.get('document_id') == document_id and r.get('path') == path]
        if len(rows) != 1: raise ValueError('手部中性灰导出缺少精确来源文档')
        current_source = hand_tone_source(st,path,(rows[0].get('src_w'),rows[0].get('src_h')))
        if current_source != recipe['source']: raise ValueError('手部中性灰禁止跨照片复制参考')
        snap['hand_tone_repair_sha256'] = stack_digest(st)
        if snap['hand_tone_repair_sha256'] != recipe['repair_sha256']:
            raise ValueError('手部中性灰修复来源已改变，需要重新审核')
    from .creative_derived_repairs import validate_stacks
    validate_stacks(st)
    from .hand_shape_runtime import capture_export as capture_hand_shape
    from .virtual_copy_people import view
    snap=capture_hand_shape(view(self,people_context) if people_context is not None else self,snap,st,source_path or self._doc_path)
    from .body_pose_render import capture as capture_body
    snap=capture_body(view(self,people_context) if people_context is not None else self,snap,st,source_path or self._doc_path,people_graph)
    if creative_base is not None:
        from .creative_derived_id_background import capture as capture_id
        id_path=source_path or self._doc_path
        id_stamp=LM.file_stamp(id_path)
        snap["creative_id_background_context"]=capture_id(st,id_path)
        if snap["creative_id_background_context"] is not None:
            from .id_background_runtime import check_export_decode as verify_id_provenance
            verify_id_provenance(snap,id_path,id_stamp,None)
        from .creative_derived_sky import capture as capture_sky
        sky_path=source_path or self._doc_path
        sky_stamp=LM.file_stamp(sky_path)
        snap["creative_sky_context"]=capture_sky(st,sky_path)
        if snap["creative_sky_context"] is not None:
            from .sky_replacement_runtime import check_export_decode as verify_sky_provenance
            verify_sky_provenance(snap,sky_path,sky_stamp,None)
        from .creative_derived_studio import capture as capture_studio
        studio_path=source_path or self._doc_path
        studio_stamp=LM.file_stamp(studio_path)
        snap["creative_studio_context"]=capture_studio(st,studio_path)
        if snap["creative_studio_context"] is not None:
            from .studio_background_runtime import check_export_decode as verify_studio_provenance
            verify_studio_provenance(snap,studio_path,studio_stamp,None)
        from .creative_derived_smoothing import capture as capture_smoothing
        snap['creative_smoothing_context']=capture_smoothing(st,source_path or self._doc_path)
        if snap['fabric_amount']:
            from .creative_derived_fabric import capture as capture_fabric
            snap['creative_fabric_context']=capture_fabric(st,source_path or self._doc_path)
        if snap['effect_recovery']['targets']:
            from .creative_derived_global_recovery import capture as capture_recovery
            snap['creative_recovery_context']=capture_recovery(st,snap['effect_recovery'],source_path or self._doc_path)
        from .creative_derived_masks import masks, capture
        values=masks(snap)
        if values:snap['creative_mask_context']=capture(st,values,source_path or self._doc_path,active_values=masks(snap,active_only=True))
    return self._semantic_snapshot(snap,st,source_path)
