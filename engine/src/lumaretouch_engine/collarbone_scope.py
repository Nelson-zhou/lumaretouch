# SPDX-License-Identifier: GPL-3.0-or-later
"""Scalar-only transfer for manually reviewed visible clavicle source contrast.

LNX-REF-PC-32465-C-abf0a5c8c9 remains PARTIAL / UNRUN, not AI 3D detection.
Only version and amount travel; the target must retain its own eligible-category
confirmation, visible clavicle traces, body ownership and semantic/manual mask.
No source ridge, pixels, traces, support or demographic labels are transferred.
"""
from . import collarbone_state as S

OP = S.OP
FAMILY = 'collarbone'
FIELD = '_collarbone_preset'
TARGET = '_collarbone_preset_target'
OWNER = '_collarbone_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_collarbone_preset_requested'
COVERAGE = '_collarbone_preset_coverage'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('人工锁骨光影预设只接受版本化强度，不携带人物、身体审核、手绘范围、蒙版或参考肤色')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    """Fence exact current owner/effective source, not undo revision counters."""
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'],
            'epoch': proof['document']['epoch'], 'people_scope': proof['people_scope'],
            'source_proof': proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('人工锁骨光影预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET]); identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('人工锁骨光影预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_collarbone_supported') is not True:
            raise ValueError(state.get('_collarbone_refusal') or
                             '目标人物缺少人工锁骨光影专属审核、明确身体归属或真实身体皮肤观察；不能借用面部或其他身体审核')
        if state.get('_collarbone_native_available') is not True:
            raise ValueError('锁骨光影 Rust 内核不可用，未使用磨皮、面部匹配或全图色调替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD)); require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的人工锁骨光影须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    # Intent only. Do not import, migrate, reset or copy any other scalar,
    # manual recipe, retained body attachment, target reference or analysis.
    state[FIELD] = recipe; state[REQUESTED] = True


def capture(engine, base=None):
    """Read target-local admission without making a portable support recipe.

    Neutral recovery still needs exact owner/source/FaceRef, but never demands
    usable body evidence or native availability. Active replay re-captures these
    facts and the complete renderer rebuilds its target-owned body reference.
    """
    from . import people_state as P, people_algorithms as A, people_resolver as R
    out = engine._capture_state() if base is None else base
    recipe = S.neutral(); ref = None; owner_proof = None; coverage = None
    supported = False; native = False; refusal = None
    if engine._people_managed():
        graph = engine._people_owner().snapshot(); source = engine._people_source()
        asset = source['sha256']; selected = getattr(engine, '_people_cursors', {}).get(asset)
        face = graph['faces'].get(selected); target = getattr(engine, '_people_targets', {}).get(asset)
        if face and face['enabled'] and face['asset_sha256'] == asset:
            candidate_ref = P.face_ref(face)
            if target == {'scope': 'face', 'target_id': selected, 'face_ref': candidate_ref}:
                ref = candidate_ref; recipe = A.recipes(R.resolve(graph, selected, A.defaults()))[OP]
                from .collarbone_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('人工锁骨光影预设缺少当前文档的规范人物归属')
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('人工锁骨光影预设人物与当前文档的有效来源不一致')
                    from .skin_colour_transfer_review import attached, describe
                    if not attached(graph, ref, family=FAMILY):
                        raise ValueError('目标人物尚未单独审核人工锁骨光影范围；不能借用面部、色温色调或美白红润审核')
                    from .people_render_runtime import verify_analysis
                    from .body_skin_semantics import check_analysis_fields
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if (analysis is None or analysis.get('body_skin') is None
                            or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实身体皮肤与遮挡观察，不能以面部或合并皮肤蒙版替代')
                    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                        raise ValueError('目标人物身体分析尺寸不属于当前有效来源')
                    shape = analysis['body_skin'].shape
                    verify_analysis(face, analysis, shape)
                    if check_analysis_fields(analysis, shape) is None:
                        raise ValueError('身体皮肤分析缺少真实来源与模型观察记录')
                    # Validate the separate consent even when current amount is
                    # neutral, so a later active install cannot trust absence.
                    # This probe is admission only, not an effect or scalar edit.
                    coverage = describe(graph, getattr(engine, '_people_support', {}), ref,
                        engine._body_bank(), analysis, {'version': 1, 'amount': 1.}, family=FAMILY)
                    supported = True
                    if not S.active(recipe):
                        coverage = {'face_ref': ref, 'scope': 'neutral-no-effect', 'body_review_sha256': None}
                except (ValueError, TypeError, AttributeError, KeyError, OSError) as error:
                    refusal = str(error)
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner_proof, REQUESTED: False, COVERAGE: coverage,
            '_collarbone_supported': supported, '_collarbone_native_available': native,
            '_collarbone_refusal': refusal}
