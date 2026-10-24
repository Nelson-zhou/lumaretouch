# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable eye-symmetry strengths and reference policy, never measured eyes.

Only horizontal/size strengths and auto/left/right size-reference policy travel.
Auto selects the larger eye afresh on each target; manual sides name that
target's own eye. Horizontal correction remains independent of size reference.
Neither reference pixels, actual selected side, coordinates nor measured eye
size/level enter presets. The canonical complete renderer independently checks
BOTH target eyes against authentic 478-point, RGB and occluder evidence, then
rebuilds composition. Capture authenticates admission, not visible-eye geometry.
AUTHORED / UNRUN, not photographic acceptance or a new segmentation model.
"""
from . import eye_symmetry_state as S

OP = S.OP
FIELD = '_eye_symmetry_preset'
TARGET = '_eye_symmetry_preset_target'
OWNER = '_eye_symmetry_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_eye_symmetry_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('眼睛对称预设只接受版本化强度与参考策略，不携带人物、眼部像素、实测参考眼、分析或控制点')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    """Fence exact owner/effective source without monotonic undo revisions."""
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'],
            'epoch': proof['document']['epoch'], 'people_scope': proof['people_scope'],
            'source_proof': proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('眼睛对称预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('眼睛对称预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_eye_symmetry_supported') is not True:
            raise ValueError(state.get('_eye_symmetry_refusal') or
                             '目标人物缺少自己的真实遮挡与 478 点分析；双眼可见性须完整重算')
        if state.get('_eye_symmetry_native_available') is not True:
            raise ValueError('眼睛对称共用的 Rust 几何内核不可用，未使用复制眼睛或其他操作替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的眼睛对称须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    # Reference is target-local policy, not the source's selected reference eye.
    # Never clear or convert legacy big_eye, eye shape or any other intent.
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Authenticate live source/FaceRef; no RGB/eye measurement is cached here.

    Observed analysis and native capability are independent admission facts,
    not proof that either eye is renderable. Neutral strengths need neither in
    require_target, including when a manual reference policy remains retained.
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
                from .eye_symmetry_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('眼睛对称预设缺少当前文档的规范人物归属')
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('眼睛对称预设人物与当前文档的有效来源不一致')
                    from .people_render_runtime import verify_analysis
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if analysis is None or analysis.get('excluded') is None:
                        raise ValueError('目标人物缺少自己的真实遮挡与 478 点分析；双眼可见性须完整重算')
                    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                        raise ValueError('目标人物分析尺寸不属于当前有效来源')
                    shape = analysis['excluded'].shape
                    if len(shape) != 2 or min(shape) <= 0:
                        raise ValueError('目标人物遮挡分析必须为真实二维来源网格')
                    verify_analysis(face, analysis, shape)
                    supported = True
                except (ValueError, TypeError, AttributeError, KeyError, OSError) as error:
                    refusal = str(error)
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner_proof, REQUESTED: False,
            '_eye_symmetry_supported': supported, '_eye_symmetry_native_available': native,
            '_eye_symmetry_refusal': refusal}
