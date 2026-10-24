"""Saved-graph validation for project and history integration, without migration guesses."""
from . import people_state as S


def validate_records(value):
    """Use on active, undo and redo trees before any live-state mutation."""
    if isinstance(value,dict):
        from .eyeliner_project import check as check_eyeliner_library
        for name in ('eyeliner_library','_eyeliner_library'):
            if name in value:check_eyeliner_library(value[name])
        from .eyelash_project import check as check_eyelash_library
        for name in ('eyelash_library','_eyelash_library'):
            if name in value:check_eyelash_library(value[name])
        from .brow_makeup_project import check as check_brow_makeup_library
        for name in ('brow_makeup_library','_brow_makeup_library'):
            if name in value:check_brow_makeup_library(value[name])
        from .lipstick_project import check as check_lipstick_library
        for name in ('lipstick_library','_lipstick_library'):
            if name in value:check_lipstick_library(value[name])
        from .blush_makeup_project import check as check_blush_library
        for name in ('blush_makeup_library','_blush_makeup_library'):
            if name in value:check_blush_library(value[name])
        for key in ('people_graph','_people_state'):
            if key in value:
                if value[key] is None: raise ValueError('Saved people state cannot be null')
                from .blush_makeup_state import validate_graph
                validate_graph(value[key])
                from .lipstick_state import validate_graph as validate_lipstick_graph
                validate_lipstick_graph(value[key])
                from .eyeliner_state import validate_graph as validate_eyeliner_graph
                validate_eyeliner_graph(value[key])
                from .eyelash_state import validate_graph as validate_eyelash_graph
                validate_eyelash_graph(value[key])
                from .brow_makeup_state import validate_graph as validate_brow_makeup_graph
                validate_brow_makeup_graph(value[key])
                from .brow_enhance_project import validate_graph as validate_brow_enhance_graph
                validate_brow_enhance_graph(value[key])
                from .lip_texture_project import validate_graph as validate_lip_texture_graph
                validate_lip_texture_graph(value[key])
                from .skin_evenness_project import validate_graph as validate_skin_evenness_graph
                validate_skin_evenness_graph(value[key])
                from .iris_makeup_state import validate_graph as validate_iris_graph
                validate_iris_graph(value[key])
        if 'people_support_assets' in value:
            from .people_support_assets import check_store
            check_store(value['people_support_assets'])
            from .eye_light_support import validate_project
            validate_project(value)
            from .blush_makeup_support import validate_project as validate_blush_support
            validate_blush_support(value)
            from .lipstick_support import validate_project as validate_lipstick_support
            validate_lipstick_support(value)
            from .eyeliner_support import validate_project as validate_eyeliner_support
            validate_eyeliner_support(value)
            from .eyelash_support import validate_project as validate_eyelash_support
            validate_eyelash_support(value)
            from .brow_makeup_support import validate_project as validate_brow_makeup_support
            validate_brow_makeup_support(value)
            from .iris_makeup_support import validate_project as validate_iris_support
            validate_iris_support(value)
            from .skin_colour_body_support import validate_project as validate_body_skin_support
            validate_body_skin_support(value)
            validate_body_skin_support(value,family='skin_finish')
        if 'people_landmarks' in value:
            from .people_retained_analysis import check_store
            check_store(value['people_landmarks'])
        for child in value.values(): validate_records(child)
    elif isinstance(value,(list,tuple)):
        for child in value: validate_records(child)


def retained_intent(state,asset_sha256):
    state=S.check(state)
    if any(f['asset_sha256']==asset_sha256 for f in state['faces'].values()): return True
    return (any(r['asset_sha256']==asset_sha256 for r in state['unresolved_legacy']) or
            any(r['scope']=='all_people' and r['target_id']==asset_sha256 for r in state['overrides']))
