# SPDX-License-Identifier: GPL-3.0-or-later
"""Scalar-only transport for independently reviewed body-to-own-face chroma.

LNX-REF-PC-32465-C-d8b09012a9 is PARTIAL: version and amount travel, never
donor pixels, masks, reference samples, manual recipes or another body's consent.
Each target rebuilds its body and same-person actual face reference from its own
immutable effective-source stage, including frozen pre-portrait repairs. This
is neither brightness matching nor a promise
to match later corrected face pixels, learned AI or body-region evenness.
AUTHORED / UNRUN: no runtime, inference or photographic acceptance is claimed.
"""
from . import body_face_match_state as S

OP = S.OP
FAMILY = 'body_face_match'
FIELD = '_body_face_match_preset'
TARGET = '_body_face_match_preset_target'
OWNER = '_body_face_match_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_body_face_match_preset_requested'
COVERAGE = '_body_face_match_preset_coverage'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('身体与本人面部肤色匹配预设只接受版本化强度，不携带人物、身体审核、手绘范围、蒙版、像素或面部参考肤色')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    """Fence the exact document, portrait owner and immutable effective source."""
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'],
            'epoch': proof['document']['epoch'], 'people_scope': proof['people_scope'],
            'source_proof': proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('身体与本人面部肤色匹配预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET]); identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('身体与本人面部肤色匹配预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_body_face_match_supported') is not True:
            raise ValueError(state.get('_body_face_match_refusal') or
                             '目标人物缺少独立身体匹配审核、明确身体归属或自己的真实身体及面部皮肤观察；不能借用其他人物或其他身体审核')
        if state.get('_body_face_match_native_available') is not True:
            raise ValueError('身体与本人面部肤色匹配 Rust 内核不可用，未使用身体均匀、亮度匹配、磨皮或全图色调替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD)); require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的身体与本人面部肤色匹配须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    # Intent only. Do not copy/reset any other scalar or target-local evidence.
    state[FIELD] = recipe; state[REQUESTED] = True


def capture(engine, base=None):
    """Read target-local admission; never make a portable reference recipe.

    Neutral remains recoverable without live body/face evidence or a native
    solver, but never without exact owner/source/FaceRef. Active replay refreshes
    all admission facts and the complete renderer rebuilds BOTH target supports.
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
                from .body_face_match_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('身体与本人面部肤色匹配预设缺少当前文档的规范人物归属')
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('身体与本人面部肤色匹配预设人物与当前文档的有效来源不一致')
                    if not S.active(recipe):
                        coverage = {'face_ref': ref, 'scope': 'neutral-no-effect',
                                    'body_review_sha256': None, 'own_face_reference': None}
                    from .skin_colour_transfer_review import attached, describe
                    if not attached(graph, ref, family=FAMILY):
                        raise ValueError('目标人物尚未单独审核身体与本人面部肤色匹配范围；不能借用身体均匀、色温色调或美白红润审核')
                    from .people_render_runtime import verify_analysis
                    from .body_skin_semantics import check_analysis_fields as check_body
                    from .skin_colour_support import check_analysis_fields as check_face
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if (analysis is None or analysis.get('body_skin') is None
                            or analysis.get('face_skin') is None or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实身体皮肤、本人面部皮肤或遮挡观察，不能以合并皮肤、身体或其他人物参考替代')
                    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                        raise ValueError('目标人物身体与面部分析尺寸不属于当前有效来源')
                    shape = analysis['body_skin'].shape
                    verify_analysis(face, analysis, shape)
                    if check_body(analysis, shape) is None or check_face(analysis, shape) is None:
                        raise ValueError('身体与本人面部皮肤分析缺少各自真实来源与模型观察记录')
                    # An admission probe only: no sampling or effect is performed.
                    # The full immutable-source renderer, not this DTO, measures
                    # the actual reference and excludes every other person's face.
                    active_coverage = describe(graph, getattr(engine, '_people_support', {}), ref,
                        engine._body_bank(), analysis, {'version': 1, 'amount': 1.}, family=FAMILY)
                    supported = True
                    if S.active(recipe):
                        coverage = active_coverage
                except (ValueError, TypeError, AttributeError, KeyError, OSError) as error:
                    refusal = str(error)
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner_proof, REQUESTED: False, COVERAGE: coverage,
            '_body_face_match_supported': supported, '_body_face_match_native_available': native,
            '_body_face_match_refusal': refusal}
