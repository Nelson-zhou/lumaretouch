# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable v2 scalar intent without portable ridge review or anatomy claims.

Only version, amount and preserve are serialized. Activating the effect, or
changing preservation while active, needs the target's dedicated whole-portrait
before/after review. Generic preset/batch review cannot stand in for that proof.
Dormant preservation and explicit resets remain usable without native/analysis.
AUTHORED / UNRUN: this contract is not photographic or runtime acceptance.
"""
from . import eye_bag_preserve_state as S

OP = S.OP
FIELD = '_eye_bag_preserve_preset'
TARGET = '_eye_bag_preserve_preset_target'
OWNER = '_eye_bag_preserve_preset_owner'
FIELDS = (FIELD,)
REQUESTED = '_eye_bag_preserve_preset_requested'
REVIEW_REQUIRED = '眼袋与卧蚕保留须在每个目标人物独立圈定可见范围并审核完整前后结果；通用预设或批量不能代替此审核'


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'} or raw['recipe'] is None:
        raise ValueError('眼袋保留预设只接受版本化强度与保留量，不携带人物、范围、蒙版或审核')
    return {'recipe': S.check(raw['recipe'])}


def owner_identity(state):
    from .people_transfer_inventory import check_proof
    proof = check_proof(state.get(OWNER))
    return {'document_id': proof['document']['document_id'],
            'epoch': proof['document']['epoch'], 'people_scope': proof['people_scope'],
            'source_proof': proof['source_proof']}


def require_target(state):
    from .people_state import check_ref
    if state.get(TARGET) is None:
        raise ValueError('眼袋保留参数需要当前明确的已启用人物，不推断其他目标')
    ref = check_ref(state[TARGET])
    if ref['asset_sha256'] != owner_identity(state)['source_proof']['asset_sha256']:
        raise ValueError('眼袋保留参数人物不属于当前文档的有效来源')
    return ref


def params_of(state):
    recipe = S.check(state.get(FIELD))
    require_target(state)
    return {'recipe': recipe}


def install(state, params):
    recipe = check_params(params)['recipe']
    require_target(state)
    if S.active(recipe):
        raise ValueError(REVIEW_REQUIRED)
    # amount=0 keeps preservation dormant. Never convert/clear legacy eye_bags,
    # copy support, or manufacture a target visual receipt to make import pass.
    state[FIELD] = recipe
    state[REQUESTED] = True


def install_reviewed(state, params, *, replace_legacy=False):
    """Stage scalars for the dedicated full-image preset planner only.

    This is not publication authority. Generic install remains active-refusing;
    the preset transaction must retain and verify the exact reviewed plan.
    """
    if type(replace_legacy) is not bool:
        raise ValueError('Eye-bag legacy replacement must be explicitly chosen')
    recipe = check_params(params)['recipe']; require_target(state)
    state[FIELD] = recipe; state[REQUESTED] = True
    if S.active(recipe) and replace_legacy:
        from .people_preset_plan import clone_state
        state['_enhance'] = clone_state(state.get('_enhance') or {})
        state['_enhance']['amounts'] = dict(state['_enhance'].get('amounts') or {})
        state['_enhance']['amounts']['eye_bags'] = 0.0


def capture(engine, base=None):
    from . import people_state as P, people_algorithms as A, people_resolver as R
    out = engine._capture_state() if base is None else base
    recipe = S.neutral(); ref = None; owner_proof = None
    if engine._people_managed():
        graph = engine._people_owner().snapshot(); source = engine._people_source()
        asset = source['sha256']; selected = getattr(engine, '_people_cursors', {}).get(asset)
        face = graph['faces'].get(selected)
        target = getattr(engine, '_people_targets', {}).get(asset)
        if face and face['enabled'] and face['asset_sha256'] == asset:
            candidate_ref = P.face_ref(face)
            if target == {'scope': 'face', 'target_id': selected, 'face_ref': candidate_ref}:
                ref = candidate_ref
                recipe = A.recipes(R.resolve(graph, selected, A.defaults()))[OP]
                from . import virtual_copy_people as V, people_transfer_inventory as I
                row = V.current_row(engine)
                if row is not None:
                    owner_proof = I.proof(engine, row, graph, source_row={**row, 'state': out})
    return {**out, FIELD: recipe, TARGET: ref, OWNER: owner_proof, REQUESTED: False}
