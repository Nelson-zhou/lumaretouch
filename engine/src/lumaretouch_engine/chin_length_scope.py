# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable NEW chin-length intent, never source-owned geometry.

LNX-REF-PC-32466-C-44a42baef4 is the independent signed lip-plane-to-chin
length scalar: positive lengthens that measured 2D interval, negative shortens.
Neither legacy small_chin nor bilateral chin shape is converted or cleared.
Capture authenticates the effective source, exact owner/FaceRef, observed face
skin and actual 478 landmarks. Each target reconstructs its own full candidate;
no masks, geometry, analysis, readiness claims or identity enter the recipe.
AUTHORED / UNRUN: source wiring is not runtime or photographic acceptance.
"""
from . import chin_length_state as S

OP = S.OP
FIELD = '_chin_length_preset'
TARGET = '_chin_length_preset_target'
OWNER = '_chin_length_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_chin_length_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('新版下巴长度预设只接受版本化长度标量，不携带人物、分析、蒙版或控制点')
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
        raise ValueError('新版下巴长度预设需要当前明确的已启用人物；批量请使用已确认的人物参数映射')
    ref = check_ref(state[TARGET])
    identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('新版下巴长度预设人物不属于当前文档的有效来源')
    if S.active(recipe):
        if state.get('_chin_length_supported') is not True:
            raise ValueError(state.get('_chin_length_refusal') or
                             '目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析')
        if state.get('_chin_length_native_available') is not True:
            raise ValueError('新版下巴长度共用的 Rust 几何内核不可用，未使用旧版小下巴、尖下巴或下庭操作替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的新版下巴长度须使用已确认的人物参数映射，不能使用通用预设通路')
    require_target(state, recipe)
    # Scalar transport cannot reset legacy intent. Coexistence is checked on the
    # complete canonical candidate before publication, never by number migration.
    state[FIELD] = recipe
    state[REQUESTED] = True


def capture(engine, base=None):
    """Authenticate live target intent, not parked/original-source evidence.

    Neutral recovery retains owner/FaceRef fences without requiring anatomy or
    native readiness. Active admission is not a successful full-candidate render.
    The renderer independently rebuilds target-local support and checks legacy
    small_chin conflict; capture preserves all saved and inherited intent.
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
                from .chin_length_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('新版下巴长度预设缺少当前文档的规范人物归属')
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner_proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('新版下巴长度预设人物与当前文档的有效来源不一致')
                    from .people_render_runtime import verify_analysis
                    from .skin_colour_support import check_analysis_fields
                    analysis = getattr(engine, '_people_analyses', {}).get(asset, {}).get(selected)
                    if (analysis is None or analysis.get('face_skin') is None
                            or analysis.get('excluded') is None):
                        raise ValueError('目标人物缺少自己的真实面部皮肤、遮挡与 478 点分析')
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
            '_chin_length_supported': supported, '_chin_length_native_available': native,
            '_chin_length_refusal': refusal}
