# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable original lip dark-furrow attenuation, never added lip material.

LNX-REF-PC-32464-C-b6315c40ca is only partially covered: this independent
non-AI operation reduces eligible narrow dark furrows. It does not repair dry
flakes or cracks, reconstruct lips, add lipstick or broadly blur their surface.
Only version and amount travel. The complete renderer independently measures
each target's own visible lip ring and source photometry; capture authenticates
ownership/observation, not anatomy or successful rendering.
AUTHORED / UNRUN: no runtime, inference or photographic acceptance is claimed.
"""
from . import lip_texture_state as S

OP = S.OP
FIELD = '_lip_texture_preset'
TARGET = '_lip_texture_preset_target'
OWNER = '_lip_texture_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_lip_texture_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('唇部暗细纹预设只接受版本化强度，不携带人物、分析、蒙版、嘴唇样本或口红审核')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    """Fence exact live owner/effective source, not monotonic undo revisions."""
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'],
            'epoch': proof['document']['epoch'], 'people_scope': proof['people_scope'],
            'source_proof': proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('唇部暗细纹预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('唇部暗细纹预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_lip_texture_supported') is not True:
            raise ValueError(state.get('_lip_texture_refusal') or
                             '目标人物缺少自己的真实遮挡、语义模型与 478 点分析；可见唇环与暗细纹须完整重算')
        if state.get('_lip_texture_native_available') is not True:
            raise ValueError('唇部暗细纹专用 Rust 内核不可用，未使用口红、模糊或 AI 祛瑕替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的唇部暗细纹须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    # Atomic scalar intent only. Never borrow lipstick review, import donor
    # photometry, change lip makeup or clear another operation for local success.
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Authenticate current effective source/FaceRef without caching lip support.

    Native capability and genuine semantic/478 observation are independent
    admission facts, not visible-lip or furrow acceptance. Full-source rendering
    owns those measurements. Neutral recovery retains exact ownership fences
    while requiring neither anatomical support nor native readiness.
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
                from .lip_texture_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('唇部暗细纹预设缺少当前文档的规范人物归属')
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('唇部暗细纹预设人物与当前文档的有效来源不一致')
                    from .people_render_runtime import verify_analysis
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if analysis is None or analysis.get('excluded') is None:
                        raise ValueError('目标人物缺少自己的真实遮挡、语义模型与 478 点分析；可见唇环与暗细纹须完整重算')
                    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                        raise ValueError('目标人物分析尺寸不属于当前有效来源')
                    shape = analysis['excluded'].shape
                    if len(shape) != 2 or not all(shape):
                        raise ValueError('唇部遮挡分析缺少有效观察网格')
                    verify_analysis(face, analysis, shape)
                    # The semantic model is authenticated by retained evidence
                    # and verify_analysis, not by lipstick visibility or a
                    # face-skin class that need not include the vermilion.
                    supported = True
                except (ValueError, TypeError, AttributeError, KeyError, OSError) as error:
                    refusal = str(error)
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner_proof, REQUESTED: False,
            '_lip_texture_supported': supported, '_lip_texture_native_available': native,
            '_lip_texture_refusal': refusal}
