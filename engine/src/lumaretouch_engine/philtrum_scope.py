# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable philtrum intent, never source-owned geometry or gap evidence.

LNX-REF-PC-32466-C-2605502c27 is the independent signed nose-safe-to-above-lips
length scalar: negative shortens, positive lengthens that measured 2D interval.
Lips and the lower face translate together. Target-local anatomy uses all 24
nose and 40 lip vertices plus independent gap evidence, not clinical anatomy,
semantic segmentation or 3D reconstruction. The host reuses the unchanged
shared Rust midface primitive through philtrum_native, not a new binary.
Only the amount travels; each target's complete renderer rebuilds its own
geometry and composition. AUTHORED / UNRUN, not photographic acceptance.
"""
from . import philtrum_state as S

OP = S.OP
FIELD = '_philtrum_preset'
TARGET = '_philtrum_preset_target'
OWNER = '_philtrum_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_philtrum_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('人中预设只接受版本化长度标量，不携带人物、分析、间隙证据、蒙版或控制点')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    """Fence exact document ownership/source without monotonic undo revisions."""
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'],
            'epoch': proof['document']['epoch'], 'people_scope': proof['people_scope'],
            'source_proof': proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('人中预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('人中预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_philtrum_supported') is not True:
            raise ValueError(state.get('_philtrum_refusal') or
                             '目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析')
        if state.get('_philtrum_native_available') is not True:
            raise ValueError('人中共用的 Rust 中庭几何内核不可用，未使用其他操作或独立二进制替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的人中须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    # Never clear/convert small_chin, chin length, midface or any other intent.
    # Complete target rendering owns independent gap reconstruction/composition.
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Authenticate live effective-source evidence, not donor or parked data.

    Observed support and shared native capability are separate admission facts,
    not proof of a renderable gap. Neutral recovery needs neither, but still
    requires the exact owner/FaceRef. No anatomical or native work is required
    by require_target for neutral intent; this capture only reports readiness.
    """
    from . import people_state as P, people_algorithms as A, people_resolver as R
    out = engine._capture_state() if base is None else base
    recipe = S.neutral(); ref = None; owner_proof = None
    supported = False; native = False; refusal = None
    if engine._people_managed():
        graph = engine._people_owner().snapshot(); source = engine._people_source()
        asset = source['sha256']
        selected = getattr(engine, '_people_cursors', {}).get(asset)
        face = graph['faces'].get(selected)
        target = getattr(engine, '_people_targets', {}).get(asset)
        if face and face['enabled'] and face['asset_sha256'] == asset:
            candidate_ref = P.face_ref(face)
            if target == {'scope': 'face', 'target_id': selected, 'face_ref': candidate_ref}:
                ref = candidate_ref
                recipe = A.recipes(R.resolve(graph, selected, A.defaults()))[OP]
                from .philtrum_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('人中预设缺少当前文档的规范人物归属')
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('人中预设人物与当前文档的有效来源不一致')
                    from .people_render_runtime import verify_analysis
                    from .skin_colour_support import check_analysis_fields
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if (analysis is None or analysis.get('face_skin') is None
                            or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析')
                    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                        raise ValueError('目标人物分析尺寸不属于当前有效来源')
                    shape = analysis['face_skin'].shape
                    verify_analysis(face, analysis, shape)
                    if check_analysis_fields(analysis, shape) is None:
                        raise ValueError('面部皮肤分析缺少真实来源与模型观察记录')
                    supported = True
                except (ValueError, TypeError, AttributeError, KeyError, OSError) as error:
                    refusal = str(error)
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner_proof, REQUESTED: False,
            '_philtrum_supported': supported, '_philtrum_native_available': native,
            '_philtrum_refusal': refusal}
