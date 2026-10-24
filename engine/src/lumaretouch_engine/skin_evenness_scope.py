# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable partial facial colour-evenness intent, not a learned-AI treatment.

LNX-REF-PC-32465-C-60b7c0e3d1 is only partially covered: each target measures
its own facial-skin chroma variation from its actual effective source. Only
version and amount travel, never source reference samples, shifts or masks.
This is not body/multi-person tone matching, defect recognition, blur or a
global tint alias. Legacy skin.broad remains independent and unchanged.
AUTHORED / UNRUN: no runtime, inference or photographic acceptance is claimed.
"""
from . import skin_evenness_state as S

OP = S.OP
FIELD = '_skin_evenness_preset'
TARGET = '_skin_evenness_preset_target'
OWNER = '_skin_evenness_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_skin_evenness_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('面部肤色均匀预设只接受版本化强度，不携带人物、分析、蒙版、参考样本或色度位移')
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
        raise ValueError('面部肤色均匀预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('面部肤色均匀预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_skin_evenness_supported') is not True:
            raise ValueError(state.get('_skin_evenness_refusal') or
                             '目标人物缺少自己的真实面部皮肤观察、遮挡与 478 点分析；参考肤色须完整重算')
        if state.get('_skin_evenness_native_available') is not True:
            raise ValueError('面部肤色均匀专用 Rust 内核不可用，未使用磨皮、全图色调或 AI 祛瑕替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的面部肤色均匀须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    # Atomic scalar intent only. Never import donor chroma or copy/clear the
    # old skin.broad amount, another colour operation, or a body attachment.
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Authenticate current ownership/observation, not reusable chroma support.

    Each complete target render independently rebuilds facial support and its
    log-chroma shift from its own effective source. Native availability and
    observed evidence are independent admission facts, not a quality claim.
    Neutral recovery requires exact owner/source/FaceRef but no native kernel
    or usable anatomical evidence, and never resets legacy broad smoothing.
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
                from .skin_evenness_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('面部肤色均匀预设缺少当前文档的规范人物归属')
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('面部肤色均匀预设人物与当前文档的有效来源不一致')
                    from .people_render_runtime import verify_analysis
                    from .skin_colour_support import check_analysis_fields
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if (analysis is None or analysis.get('face_skin') is None
                            or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实面部皮肤观察、遮挡与 478 点分析；参考肤色须完整重算')
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
            '_skin_evenness_supported': supported, '_skin_evenness_native_available': native,
            '_skin_evenness_refusal': refusal}
