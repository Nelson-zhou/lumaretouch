# SPDX-License-Identifier: GPL-3.0-or-later
"""Scalar-only portable intent; every target remeasures its own reviewed skin."""
from . import face_decoration_state as S
OP = S.OP
FIELD = '_face_decoration_preset'
TARGET = '_face_decoration_preset_target'
OWNER = '_face_decoration_preset_owner'
REQUESTED = '_face_decoration_preset_requested'
FIELDS = (FIELD,)


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('面部装饰预设只接受版本化图案与程度，不能携带人物、皮肤、蒙版、审核或源像素')
    return {'recipe':S.check(raw['recipe'])}


def owner_identity(state):
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id':proof['document']['document_id'],'epoch':proof['document']['epoch'],
            'people_scope':proof['people_scope'],'source_proof':proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    ref = check_ref(state.get(TARGET)); identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('面部装饰预设人物不属于当前文档有效来源')
    if S.active(recipe):
        if state.get('_face_decoration_supported') is not True:
            raise ValueError(state.get('_face_decoration_refusal') or '目标人物缺少自己独立审核的可见面部皮肤与真实分析')
        if state.get('_face_decoration_native_available') is not True:
            raise ValueError('面部装饰专用 Rust 内核不可用，未使用腮红或其他操作替代')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD)); require_target(state,recipe)
    return {'recipe':S.preset(recipe)}


def install(state, params):
    recipe = check_params(params)['recipe']; require_target(state,recipe)
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的面部装饰须使用已确认的人物参数映射，不能绕过通用预设来源限制')
    state[FIELD] = recipe; state[REQUESTED] = True


def capture(engine, base=None):
    from . import people_state as P, people_algorithms as A, people_resolver as R
    out = engine._capture_state() if base is None else base
    recipe = S.neutral(); ref = None; proof = None; supported = False; native = False; refusal = None
    if engine._people_managed():
        graph = engine._people_owner().snapshot(); source = engine._people_source(); asset = source['sha256']
        selected = engine._people_cursors.get(asset); face = graph['faces'].get(selected)
        target = engine._people_targets.get(asset)
        if face and face['enabled'] and face['asset_sha256'] == asset:
            candidate_ref = P.face_ref(face)
            if target == {'scope':'face','target_id':selected,'face_ref':candidate_ref}:
                ref = candidate_ref; recipe = A.recipes(R.resolve(graph,selected,A.defaults()))[OP]
                from .face_decoration_native import available
                native = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None: raise ValueError('面部装饰预设缺少当前规范文档归属')
                    proof = I.proof(engine,row,graph,source_row={**row,'state':out})
                    if proof['source_proof']['asset_sha256'] != asset:
                        raise ValueError('面部装饰人物与当前有效来源不一致')
                    from .face_decoration_host import support_status
                    supported, refusal, _ = support_status(engine,graph,source,ref)
                except (ValueError,TypeError,KeyError,AttributeError,OSError) as error:
                    refusal = str(error)
    return {**out,FIELD:recipe,TARGET:ref,OWNER:proof,REQUESTED:False,
            '_face_decoration_supported':supported,'_face_decoration_native_available':native,
            '_face_decoration_refusal':refusal}
