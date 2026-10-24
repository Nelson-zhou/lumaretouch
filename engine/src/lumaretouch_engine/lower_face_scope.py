# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable lower-third length intent, never source-owned geometry.

LNX-REF-PC-32466-C-1ae8316994 is a separate signed scalar: positive lengthens,
negative shortens the local nose/chin proxy interval. Mouth participates in its
vertical map; its own map retains width and upper face while feathered adjacent
neck/background may move. This is not clinical measurement, AI or segmentation.
Capture authenticates the effective source, exact owner/FaceRef, observed face
skin and actual 478 landmarks. The full target renderer owns reconstruction and
composition; legacy small-chin and all other saved controls remain independent.
AUTHORED / UNRUN: source wiring is not runtime or photographic acceptance.
"""
from . import lower_face_state as S

OP = S.OP
FIELD = '_lower_face_preset'
TARGET = '_lower_face_preset_target'
OWNER = '_lower_face_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_lower_face_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('下庭长度预设只接受版本化长度标量，不携带人物、分析、蒙版或控制点')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    """Fence exact ownership/source, excluding monotonic undo revisions."""
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'],
            'epoch': proof['document']['epoch'], 'people_scope': proof['people_scope'],
            'source_proof': proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('下庭长度预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('下庭长度预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_lower_face_supported') is not True:
            raise ValueError(state.get('_lower_face_refusal') or
                             '目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析')
        if state.get('_lower_face_native_available') is not True:
            raise ValueError('下庭长度专用 Rust 内核不可用，未使用旧版小下巴或其他几何内核替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的下庭长度须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Capture one canonical target without rebinding original-source analysis.

    Admission is not a successful render. Each original or derived target must
    independently reconstruct the complete candidate from its effective source.
    Neutral recovery keeps the owner/FaceRef fence without requiring anatomy or
    native readiness. Other operations' saved intent/evidence remain untouched.
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
                from .lower_face_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('下庭长度预设缺少当前文档的规范人物归属')
                    # Authenticate the captured live baseline, not a parked row.
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('下庭长度预设人物与当前文档的有效来源不一致')
                    from .people_render_runtime import verify_analysis
                    from .skin_colour_support import check_analysis_fields
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if (analysis is None or analysis.get('face_skin') is None
                            or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析')
                    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                        raise ValueError('目标人物分析尺寸不属于当前有效来源')
                    shape = analysis['face_skin'].shape
                    # Exact finite (478, 3) bytes/digest, FaceRef, actual MediaPipe
                    # evidence and a matching observed face-skin model/source.
                    verify_analysis(face, analysis, shape)
                    if check_analysis_fields(analysis, shape) is None:
                        raise ValueError('面部皮肤分析缺少真实来源与模型观察记录')
                    supported = True
                except (ValueError, TypeError, AttributeError, KeyError, OSError) as error:
                    refusal = str(error)
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner_proof, REQUESTED: False,
            '_lower_face_supported': supported, '_lower_face_native_available': native,
            '_lower_face_refusal': refusal}
