# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable original-brow contrast intent, never source samples or makeup.

LNX-REF-PC-32471-C-18765fa8ea strengthens existing brow contrast for positive
amounts and reduces it for negative amounts. Only version, the link flag and
two signed person-relative amounts travel. It does not add eyebrow makeup.
Each target independently measures its actual brows and adjacent forehead from
its effective source and authentic face_skin/excluded observation. Capture
authenticates admission only, not visible anatomy or successful rendering.
AUTHORED / UNRUN: no runtime, inference or photographic acceptance is claimed.
"""
from . import brow_enhance_state as S

OP = S.OP
FIELD = '_brow_enhance_preset'
TARGET = '_brow_enhance_preset_target'
OWNER = '_brow_enhance_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_brow_enhance_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('眉毛增强预设只接受版本化左右联动与两项正负强度，不携带人物、分析、蒙版、参考样本或实测对比度')
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
        raise ValueError('眉毛增强预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('眉毛增强预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_brow_enhance_supported') is not True:
            raise ValueError(state.get('_brow_enhance_refusal') or
                             '目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析；眉毛与邻接额头须完整重算')
        if state.get('_brow_enhance_native_available') is not True:
            raise ValueError('眉毛增强专用 Rust 内核不可用，未使用眉妆或其他操作替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的眉毛增强须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    # Replace the complete intent atomically. Never average on relink, import
    # source contrast, change brow makeup or clear another operation to succeed.
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Authenticate current effective source/FaceRef, never cache brow samples.

    Native capability and genuine observed analysis are independent admission
    facts. Actual brows, adjacent forehead and composition remain the complete
    target renderer's responsibility. Neutral recovery keeps ownership fences
    but requires neither anatomy nor native readiness, retaining link intent.
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
                from .brow_enhance_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('眉毛增强预设缺少当前文档的规范人物归属')
                    # Authenticate the live baseline, never a parked row or the
                    # original image behind a distinct creative source.
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('眉毛增强预设人物与当前文档的有效来源不一致')
                    from .people_render_runtime import verify_analysis
                    from .skin_colour_support import check_analysis_fields
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if (analysis is None or analysis.get('face_skin') is None
                            or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析；眉毛与邻接额头须完整重算')
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
            '_brow_enhance_supported': supported, '_brow_enhance_native_available': native,
            '_brow_enhance_refusal': refusal}
