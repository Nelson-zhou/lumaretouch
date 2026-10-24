# SPDX-License-Identifier: GPL-3.0-or-later
"""Scalar preset transport; applied skin colour lives only in the people graph.

Target references and admission facts below are ephemeral, locally captured
context. They never enter portable parameters, project state or a mask bank.
The canonical renderer must still prepare every target from its own analysis.
"""
from . import skin_colour_state as S

OP = S.OP
FIELD = '_skin_colour_preset'
TARGET = '_skin_colour_preset_target'
FIELDS = (FIELD,)
REQUESTED = '_skin_colour_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('面部肤色预设只接受版本化色温与色调参数，不携带人物、蒙版或分析')
    return {'recipe': S.check(raw['recipe'])}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('面部肤色预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    if S.active(recipe):
        if state.get('_skin_colour_supported') is not True:
            raise ValueError(state.get('_skin_colour_refusal') or
                             '目标人物缺少自己的真实面部皮肤与遮挡分析')
        if state.get('_skin_colour_native_available') is not True:
            raise ValueError('面部肤色色温/色调 Rust 内核不可用，未应用替代算法')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    # The generic route has no frozen effective-source portrait review. Direct
    # canonical edits and reviewed face transfers use their existing owners.
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的面部肤色须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Read the explicitly selected canonical face, never manufacture support.

    Do not fail unrelated preset captures when skin colour is unavailable.
    Selecting this module invokes params_of/install and surfaces the refusal.
    """
    from . import people_state as P, people_algorithms as A, people_resolver as R
    out = engine._capture_state() if base is None else base
    recipe = S.neutral(); ref = None; supported = False; native = False; refusal = None
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
                from .skin_colour_native import available
                native = available()
                try:
                    from .people_render_runtime import verify_analysis
                    from .skin_colour_support import check_analysis_fields
                    analyses = getattr(engine, '_people_analyses', {}).get(asset, {})
                    analysis = analyses.get(selected)
                    if (analysis is None or analysis.get('face_skin') is None
                            or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实面部皮肤与遮挡分析')
                    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                        raise ValueError('目标人物分析尺寸不属于当前有效来源')
                    shape = analysis['face_skin'].shape
                    verify_analysis(face, analysis, shape)
                    if check_analysis_fields(analysis, shape) is None:
                        raise ValueError('面部皮肤分析缺少真实来源与模型观察记录')
                    # The renderer owns neighbour protection: real measured
                    # landmarks when present, conservative retained boxes when
                    # not. Missing neighbour analysis is never positive skin.
                    supported = True
                except (ValueError, TypeError, AttributeError, KeyError) as error:
                    refusal = str(error)
    return {**out, FIELD: recipe, TARGET: ref, REQUESTED: False,
            '_skin_colour_supported': supported, '_skin_colour_native_available': native,
            '_skin_colour_refusal': refusal}
