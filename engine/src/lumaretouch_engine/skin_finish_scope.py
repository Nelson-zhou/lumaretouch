# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable finish scalars; the canonical people graph owns applied intent.

Capture facts are ephemeral target context, never preset/body support authority.
Original and derived reviewed face transfers use the existing full-source owner;
the generic derived-preset guard remains closed to this source-dependent module.
AUTHORED / UNRUN: no runtime or photographic acceptance is implied.
"""
from . import skin_finish_state as S

OP = S.OP
FIELD = '_skin_finish_preset'
TARGET = '_skin_finish_preset_target'
FIELDS = (FIELD,)
REQUESTED = '_skin_finish_preset_requested'
COVERAGE = '_skin_finish_preset_coverage'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('美白红润预设只接受版本化标量，不携带人物、身体审核、蒙版或分析')
    return {'recipe': S.check(raw['recipe'])}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('美白红润预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    if S.active(recipe):
        if state.get('_skin_finish_supported') is not True:
            raise ValueError(state.get('_skin_finish_refusal') or
                             '目标人物缺少自己的真实面部皮肤与遮挡分析')
        if state.get('_skin_finish_native_available') is not True:
            raise ValueError('美白红润 Rust 内核不可用，未应用色温/色调或全图曝光替代算法')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的美白红润须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Read the selected face; unrelated captures do not require finish support."""
    from . import people_state as P, people_algorithms as A, people_resolver as R
    out = engine._capture_state() if base is None else base
    recipe = S.neutral(); ref = None; supported = False; native = False; refusal = None; coverage = None
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
                from .skin_finish_native import available
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
                    from .skin_colour_transfer_review import attached, describe
                    body_bank = (engine._body_bank() if S.active(recipe)
                        and attached(graph, ref, family='skin_finish') else None)
                    coverage = describe(graph, getattr(engine, '_people_support', {}), ref,
                        body_bank, analysis, recipe, family='skin_finish')
                    supported = True
                except (ValueError, TypeError, AttributeError, KeyError) as error:
                    refusal = str(error)
    # Only FIELD enters preset parameters; target-owned review stays local.
    return {**out, FIELD: recipe, TARGET: ref, REQUESTED: False, COVERAGE: coverage,
            '_skin_finish_supported': supported, '_skin_finish_native_available': native,
            '_skin_finish_refusal': refusal}
