# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable bilateral contour intent, never transferable source geometry.

Only three link flags and six signed scalars enter a preset. Capture authenticates
the selected face's own measured skin observation and actual 478 landmarks;
the target renderer independently decides pose, spatial, photometric and neighbour
safety. This is measured 2D geometry, not AI reconstruction or a 3D face model.
AUTHORED / UNRUN: source wiring is not runtime or photographic acceptance.
"""
from . import face_contour_state as S

OP = S.OP
FIELD = '_face_contour_preset'
TARGET = '_face_contour_preset_target'
OWNER = '_face_contour_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_face_contour_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('面部轮廓预设只接受版本化左右联动与六项标量，不携带人物、分析、蒙版或控制点')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    """Reuse the existing owner proof, excluding its transaction revisions.

    The preset controller owns document revisions and rollback; graph commits
    advance monotonic revisions even when restoring old intent. Owner identity
    is document_id/epoch, people_scope and the exact effective source proof.
    FaceRef remains a separate mandatory target fence. None of this is portable.
    """
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'],
            'epoch': proof['document']['epoch'], 'people_scope': proof['people_scope'],
            'source_proof': proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('面部轮廓预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('面部轮廓预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_face_contour_supported') is not True:
            raise ValueError(state.get('_face_contour_refusal') or
                             '目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析')
        if state.get('_face_contour_native_available') is not True:
            raise ValueError('面部轮廓 Rust 内核不可用，未应用旧版瘦脸、全图变形或 AI/3D 替代算法')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的面部轮廓须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Read explicit canonical intent; no source pixels or support are copied.

    Admission does not claim front/mild-yaw contour support. Only the actual
    target renderer can establish that. Neutral reset still requires the exact
    owner/face, but does not depend on stale support or native availability.
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
                from .face_contour_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('面部轮廓预设缺少当前文档的规范人物归属')
                    # Use the captured live baseline, not a parked row state.
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('面部轮廓预设人物与当前文档的有效来源不一致')
                    from .people_render_runtime import verify_analysis
                    from .skin_colour_support import check_analysis_fields
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if (analysis is None or analysis.get('face_skin') is None
                            or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析')
                    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                        raise ValueError('目标人物分析尺寸不属于当前有效来源')
                    shape = analysis['face_skin'].shape
                    # This verifies exact (478, 3), finite bytes and their digest,
                    # matching FaceRef, actual MediaPipe evidence and model IDs.
                    verify_analysis(face, analysis, shape)
                    if check_analysis_fields(analysis, shape) is None:
                        raise ValueError('面部皮肤分析缺少真实来源与模型观察记录')
                    supported = True
                except (ValueError, TypeError, AttributeError, KeyError, OSError) as error:
                    refusal = str(error)
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner_proof, REQUESTED: False,
            '_face_contour_supported': supported, '_face_contour_native_available': native,
            '_face_contour_refusal': refusal}
