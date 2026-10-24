# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional scalar transfer adapter. Target review is never portable.

The shared registry may expose this only after its target preflight and complete
original/derived render paths are integrated. This file does not enable transfer.
"""
from . import facial_sculpt_state as S
OP = S.OP
FIELD = '_facial_sculpt_preset'
TARGET = '_facial_sculpt_preset_target'
OWNER = '_facial_sculpt_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_facial_sculpt_preset_requested'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('面部立体预设只可携带两项强度，不含源图、审核、关键点或光影场')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'], 'epoch': proof['document']['epoch'],
            'people_scope': proof['people_scope'], 'source_proof': proof['source_proof']}


def require_target(state, recipe):
    from .people_state import check_ref
    ref = check_ref(state.get(TARGET)); identity = owner_identity(state)
    if ref['asset_sha256'] != identity['source_proof']['asset_sha256']:
        raise ValueError('面部立体预设目标不属于当前有效来源')
    if S.active(recipe) and (state.get('_facial_sculpt_supported') is not True
                             or state.get('_facial_sculpt_native_available') is not True):
        raise ValueError(state.get('_facial_sculpt_refusal') or '目标需要自己的可见皮肤审核、实测分析及专用内核')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD)); require_target(state, recipe)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']; require_target(state, recipe)
    if state.get('_creative_base') is not None:
        raise ValueError('合成来源的面部立体需使用已确认的人物参数映射，不经过通用预设通路')
    state[FIELD] = recipe; state[REQUESTED] = True


def capture(engine, base=None):
    from . import people_state as P, people_algorithms as A, people_resolver as R
    from .facial_sculpt_host import support_status
    from .facial_sculpt_native import available
    out = engine._capture_state() if base is None else base
    recipe = S.neutral(); ref = None; owner = None; supported = False; reason = None; ready = False
    if engine._people_managed():
        graph = engine._people_owner().snapshot(); source = engine._people_source()
        selected = engine._people_cursors.get(source['sha256']); face = graph['faces'].get(selected)
        if face and face['enabled'] and face['asset_sha256'] == source['sha256']:
            candidate_ref = P.face_ref(face)
            if engine._people_targets.get(source['sha256']) == {'scope': 'face', 'target_id': selected, 'face_ref': candidate_ref}:
                ref = candidate_ref; recipe = A.recipes(R.resolve(graph, selected, A.defaults()))[OP]
                ready = available()
                try:
                    from . import virtual_copy_people as V, people_transfer_inventory as I
                    row = V.current_row(engine)
                    if row is None:
                        raise ValueError('面部立体缺少当前规范文档归属')
                    owner = I.proof(engine, row, graph, source_row={**row, 'state': out})
                    if owner['source_proof']['asset_sha256'] != source['sha256']:
                        raise ValueError('面部立体当前有效来源已改变')
                    supported, reason, _ = support_status(engine, graph, source, ref)
                except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
                    reason = str(error)
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner, REQUESTED: False,
            '_facial_sculpt_supported': supported, '_facial_sculpt_refusal': reason,
            '_facial_sculpt_native_available': ready}
