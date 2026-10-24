"""Exact reviewed makeup ports for immutable returned photo sources.

This registry does not own recipes, assets, visibility, rendering or history.
Each admitted family still uses its existing state and support validators and
Rust-backed consumer. No inferred visibility or cross-face support inheritance.
"""
OPERATIONS = frozenset('lnx.' + name + '.v1' for name in (
    'eye_light','lipstick','blush_makeup','face_decoration','facial_sculpt','eyeliner','eyelash','brow_makeup','iris_makeup'))
SUPPORT_KINDS = frozenset(name + '_visibility' for name in (
    'eye_light','lipstick','blush_makeup','face_decoration','facial_sculpt','eyeliner','eyelash','brow_makeup','iris_makeup'))
REVIEWS = {
    'eye_light':('eyes',frozenset(('left','right')),False),
    'lipstick':('regions',frozenset(('upper','lower')),True),
    'blush':('cheeks',frozenset(('left','right')),True),
    'eyeliner':('eyes',frozenset(('left','right')),False),
    'eyelash':('eyes',frozenset(('left_upper','left_lower','right_upper','right_lower')),False),
    'brow_makeup':('brows',frozenset(('left','right')),False),
    'iris':('eyes',frozenset(('left','right')),True),
}
PALETTES = frozenset(('lipstick','blush','eyeliner','eyelash','brow_makeup'))
ACTIONS = frozenset(('facial_sculpt_reference','facial_sculpt_review')) | frozenset(('face_decoration_reference','face_decoration_review','face_decoration_alias_preview','face_decoration_alias_image','face_decoration_alias_confirm','face_decoration_support_alias_preview','face_decoration_support_alias_image','face_decoration_support_alias_confirm')) | frozenset(prefix + suffix for prefix in REVIEWS for suffix in ('_reference','_review')) | frozenset(prefix+'_palette' for prefix in PALETTES)


def check_action(action,payload,target):
    if action in ('facial_sculpt_reference','facial_sculpt_review'):
        from .facial_sculpt_host import check_action as sculpt_action
        sculpt_action(action,payload,target)
        return
    if action.startswith('face_decoration_support_alias_'):
        from .face_decoration_support_alias_review import check_action as support_action
        support_action(action,payload,target)
        return
    if action.startswith('face_decoration_alias_'):
        from .face_decoration_alias_review import check_action as alias_action
        alias_action(action,payload,target)
        return
    if action in ('face_decoration_reference','face_decoration_review'):
        from .face_decoration_host import check_action as decoration_action
        decoration_action(action,payload,target)
        return
    if action not in ACTIONS or target['scope'] != 'face' or type(payload) is not dict:
        raise ValueError('Reviewed makeup requires an exact local face and known action')
    prefix,kind = action.rsplit('_',1)
    if kind == 'reference':
        if payload != {}: raise ValueError('Makeup reference accepts no source override')
    elif kind == 'palette':
        if set(payload) != {'action','colour'} or payload['action'] not in ('save','remove'):
            raise ValueError('Makeup palette accepts only bounded save/remove colour intent')
        from .lipstick_state import colour
        colour(payload['colour']) # Same explicit #RRGGBB contract; owner checks capacity.
    else:
        field,allowed,complete = REVIEWS[prefix]
        if set(payload) != {field} or type(payload[field]) is not dict or not payload[field]:
            raise ValueError('Makeup review requires explicit target-owned regions')
        actual = set(payload[field])
        if actual-allowed or (complete and actual != allowed):
            raise ValueError('Makeup review side coverage is incomplete or unknown')
        # Family stage_review/check_record owns the complete geometry schema.


def check_leaf(operation,path,value,neutral,validator):
    from .people_resolver import materialize
    if operation not in OPERATIONS: raise ValueError('Unadapted makeup operation')
    if operation == 'lnx.eyelash.v1':
        neutral = {**neutral,'link_lr':False,'link_ud':False}
    elif operation in ('lnx.eye_light.v1','lnx.eyeliner.v1','lnx.brow_makeup.v1'):
        neutral = {**neutral,'linked':False}
    # The canonical graph owner checks complete atomic linked recipes, including
    # string patterns/colours/material IDs, after all requested leaves are staged.
    materialize({'conflicts':[], 'operations':{operation:{path:{'value':value}}}},operation,neutral,validator)


def validate_supports(state,assets,asset_sha256,*,only_kind=None):
    from .creative_derived_recovery import TARGETS
    from . import eye_light_support,lipstick_support,blush_makeup_support,face_decoration_support,facial_sculpt_support
    from . import eyeliner_support,eyelash_support,brow_makeup_support,iris_makeup_support
    from .people_state import face_ref
    modules = {module.KIND:module for module in (eye_light_support,lipstick_support,
        blush_makeup_support,face_decoration_support,facial_sculpt_support,eyeliner_support,eyelash_support,brow_makeup_support,iris_makeup_support)}
    for face in state['faces'].values():
        if face['asset_sha256'] != asset_sha256: continue
        for kind in face['local_assets']:
            if kind in ('hair_colour','skin_colour_body_visibility','skin_finish_body_visibility','body_skin_evenness_visibility','body_face_match_visibility','collarbone_visibility','eye_bag_ridge_visibility') or kind in TARGETS:continue # Independent support owners.
            if kind not in modules: raise ValueError('Unadapted derived source support')
            if only_kind is not None and kind != only_kind: continue
            if kind == 'facial_sculpt_visibility':
                from . import facial_sculpt_state as SCULPT, people_algorithms as A, people_resolver as R
                recipe = A.recipes(R.resolve(state,face['face_instance_id'],A.defaults()))[SCULPT.OP]
                if not SCULPT.active(recipe): continue
            if kind == 'face_decoration_visibility':
                from . import face_decoration_state as D, people_algorithms as A, people_resolver as R
                recipe = A.recipes(R.resolve(state,face['face_instance_id'],A.defaults()))[D.OP]
                if not D.active(recipe): continue
            modules[kind].resolve(state,assets,face_ref(face))


def input_banks(assets):
    return {name+'_assets':assets for name in (
        'eye_light','lipstick','blush_makeup','face_decoration','facial_sculpt','eyeliner','eyelash','brow_makeup','iris_makeup')}
