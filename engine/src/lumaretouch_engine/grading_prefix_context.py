"""Audited narrow preview lane, based on actual prefix consumers, not recipes.

Eligible: normalized RGB8 proxy + exposure/WB + HSL; every other prefix consumer
must take its no-op branch. Unknown, missing, suspended or complex state misses.
This module does not enable the cache. See the adaptation document's audit table.
"""
import json
import math


def _numbers(values, count):
    return (type(values) in (tuple, list) and len(values) == count
            and all(type(v) in (int, float) and math.isfinite(v) for v in values))


def _zero_mapping(value):
    return (type(value) is dict and bool(value)
            and all(type(v) in (int, float) and v == 0 for v in value.values()))


def narrow_context(engine):
    """Return immutable actual-consumer state, or None. No tensor data reads.

    The surrounding caller checks source identity/version/shape/device/dtype,
    document/revision/generation, ordinary grading mode, original-source bypasses
    and cancellation. Missing attributes deliberately fail closed there.
    """
    p = engine._vram
    from .hand_shape_state import active as hand_shape_active
    if hand_shape_active(getattr(engine, '_hand_shape', None)):
        return None  # Never reuse a colour-only prefix over requested hand geometry.
    if engine._strength != 0 or engine._channel is not None:
        return None
    # Even a presently idle owned preview is excluded: its lifecycle may carry
    # temporary state without one of the conventional preview-active flags.
    if any(value is not None for name, value in vars(engine).items()
           if name.endswith('_preview_owner')):
        return None
    if any(getattr(engine, name, None) is not None for name in (
            '_inspection', '_prompted_mask_owner', '_sky_semantic_owner',
            '_semantic_colour_owner', '_local_grade_live_owner')):
        return None
    if any(value is not None for name, value in vars(engine).items()
           if name.endswith('_override')):
        return None
    if getattr(p, 'people_prepared', None) is not None or getattr(p, 'people_suspended', None):
        return None
    if not _numbers((p.light_exposure, p.grade_amount), 2):
        return None
    # Repair/light and all pre-exposure spatial/source-derived consumers.
    if (p.repair_base is not None or p.repair_ops or p.light_field_gpu is not None
            or p.light_ops or p.fabric.amount != 0 or p.fabric.field is not None
            or p.hand_tone.amount != 0 or p.hand_tone.field is not None
            or p.limb_vein.amount != 0 or p.limb_vein.field is not None
            or p.fabric_sweat.amount != 0 or p.fabric_sweat.field is not None
            or p.effect_recovery.required or p.effect_recovery.fields
            or p.effect_recovery.suspended or p.effect_recovery.suspended_targets
            or p.studio_background.required or p.studio_background.fields
            or p.studio_background.suspended or p.deform_units
            or not _zero_mapping(p.deform_amounts)
            or not _zero_mapping(p.enhance_amounts)):
        return None
    for name in ('facial_wrinkle_layer', 'facial_wrinkle_delta', 'under_eye_layer',
                 'under_eye_delta', 'enhance_gpu', 'enhance_local', 'lip_makeup_layer',
                 'lip_makeup_delta', 'brow_shape_field', 'nose_shape_field',
                 'eye_shape_field', 'mouth_shape_field'):
        if getattr(p, name) is not None:
            return None
    from . import lip_makeup_state as lips
    if p.lip_makeup != lips.neutral() or p.lip_makeup_suspended:
        return None
    if any(getattr(p, name) for name in ('brow_shape_suspended', 'nose_shape_suspended',
                                        'eye_shape_suspended', 'mouth_shape_suspended')):
        return None
    # Each flag below is the actual early-return predicate of its stage. Do not
    # infer inactive runtime state from the corresponding persisted engine recipe.
    if (p.primary_calibration.active is not False or p.extended_tone.active is not False
            or p.extended_tone_override is not None
            or p.levels_stage.active or any(v is not None for v in p.curves_compiled)
            or p.lut is not None or p.lut_vol is not None
            or p.grade_params != (0.0, 0.0, 0.0)
            or p.local_grade_layers.fields or p.local_grade_layers.suspended
            or p.bg_active or p.bg_matte is not None or p.bg_ref is not None
            or p.manual_liquify.field is not None or p.manual_liquify.suspended
            or p.optics.suspended or p.crop_rect != (0.0, 0.0, 1.0, 1.0)
            or p.crop_rotation != 0 or p.reference_color.active is not False
            or p.semantic_colour.active is not False or p.semantic_colour.suspension):
        return None
    from . import optics_state as optics
    if optics.active(p.optics.value):
        return None
    # These are every argument read by the two allowed non-neutral operators:
    # apply_exposure -> exposure_t and apply_hsl -> hsl_t. WB uses the prepared
    # gains, not mutable recipe metadata. Finite plain numbers only, never repr()
    # or hashes of opaque objects/arrays/tensor identities as content evidence.
    if (not _numbers(p.exposure_params, 7) or not _numbers(p.hsl_bands, 24)
            or type(p.exposure_ref_k) not in (int, float)
            or not math.isfinite(p.exposure_ref_k)
            or (p.prepared_wb is not None and not _numbers(p.prepared_wb, 3))):
        return None
    params = engine._params
    if (type(params) is not dict
            or set(params) != {'radius', 'eps', 'detail_gain', 'mid_gain', 'broad_gain', 'texture_radius'}
            or not all(type(v) in (int, float) and math.isfinite(v) for v in params.values())):
        return None
    state = {'lane': 'rgb8-exposure-hsl-v1', 'strength': engine._strength,
             'channel': engine._channel, 'filter': params,
             'exposure': p.exposure_params, 'reference_k': p.exposure_ref_k,
             'prepared_wb': p.prepared_wb, 'hsl': p.hsl_bands}
    return (json.dumps(state, sort_keys=True, allow_nan=False, separators=(',', ':')).encode(),
            'lumaretouch-encoded-working-rgb', 'rgb8-normalized-f32-extended-values')
