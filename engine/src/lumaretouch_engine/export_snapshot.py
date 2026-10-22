"""One stored-state to export snapshot mapping, shared by active and other docs."""
from . import local_mask_state as LM, local_grade_layers as LG, effect_recovery_state as ERS
from . import manual_liquify_state as MLS, studio_background_state as SBS, optics_state as OPS, sky_replacement_state as SKS
from . import lip_makeup_state as LIPS, brow_shape_state as BROWS, nose_shape_state as NOSES, eye_shape_state as EYES, mouth_shape_state as MOUTHS
from . import reference_color_state as RCS, white_balance_recipe as WB
from .ops import curves as CURVES, levels as LEVELS


def state_to_export_snap(self,st,*,device,scale,upscale_backend,sharpen,source_path=None,people_graph=None):
    snap = dict(people=self._people_export_snapshot(st,source_path,people_graph), strength=float(st.get("_strength", 0.0)),
                    params=dict(st.get("_params") or self._params),
                    grade=tuple(st.get("_grade", (0.0, 0.0, 0.0, 1.0))),
                    grade_scope=str(st.get("_grade_scope") or "all"),
                    grade_mask=st.get("_grade_mask"), local_masks=LM.check(st.get("_local_masks")), local_mask_owner=LM.owner_from_state(st), local_grade_groups=LG.check(st.get("_local_grade_layers")),
                    effect_recovery=ERS.check(st.get("_effect_recovery")), manual_liquify=MLS.check(st.get("_manual_liquify")), studio_background=SBS.check(st.get("_studio_background")), optics=OPS.check(st.get("_optics")), sky_replacement=SKS.check(st.get("_sky_replacement")), lip_makeup=LIPS.check(st.get("_lip_makeup")), brow_shape=BROWS.check(st.get("_brow_shape")), brow_shape_owner=st.get("_brow_shape_owner"), nose_shape=NOSES.check(st.get("_nose_shape")), nose_shape_owner=st.get("_nose_shape_owner"), eye_shape=EYES.check(st.get("_eye_shape")), eye_shape_owner=st.get("_eye_shape_owner"), reference_color=RCS.check(st.get("_reference_color")), mouth_shape=MOUTHS.check(st.get("_mouth_shape")), mouth_shape_owner=st.get("_mouth_shape_owner"),
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
                    enhance=dict(st.get("_enhance") or {"amounts": {}, "built": False}),
                    enhance_defer=bool(st.get("_enhance_defer")),
                    channel=st.get("_channel"),
                    _bg=dict(st.get("_bg") or {}),
                    precompute=st.get("_precompute"),
                    device=device, scale=scale, upscale_backend=upscale_backend,
                    sharpen=sharpen)
    return self._semantic_snapshot(snap,st,source_path)
