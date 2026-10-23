"""Exact reviewed makeup ports for immutable returned photo sources.

This registry does not own recipes, assets, visibility, rendering or history.
Each admitted family still uses its existing state and support validators and
Rust-backed consumer. No inferred visibility or cross-face support inheritance.
"""
OPERATIONS = frozenset('lnx.' + name + '.v1' for name in (
    'eye_light','lipstick','blush_makeup','eyeliner','eyelash','brow_makeup','iris_makeup'))
SUPPORT_KINDS = frozenset(name + '_visibility' for name in (
    'eye_light','lipstick','blush_makeup','eyeliner','eyelash','brow_makeup','iris_makeup'))
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
ACTIONS = frozenset(prefix + suffix for prefix in REVIEWS for suffix in ('_reference','_review')) | frozenset(prefix+'_palette' for prefix in PALETTES)


def check_action(action,payload,target):
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
    from . import eye_light_support,lipstick_support,blush_makeup_support
    from . import eyeliner_support,eyelash_support,brow_makeup_support,iris_makeup_support
    from .people_state import face_ref
    modules = {module.KIND:module for module in (eye_light_support,lipstick_support,
        blush_makeup_support,eyeliner_support,eyelash_support,brow_makeup_support,iris_makeup_support)}
    for face in state['faces'].values():
        if face['asset_sha256'] != asset_sha256: continue
        for kind in face['local_assets']:
            if kind not in modules: raise ValueError('Unadapted derived source support')
            if only_kind is not None and kind != only_kind: continue
            modules[kind].resolve(state,assets,face_ref(face))


def input_banks(assets):
    return {name+'_assets':assets for name in (
        'eye_light','lipstick','blush_makeup','eyeliner','eyelash','brow_makeup','iris_makeup')}
