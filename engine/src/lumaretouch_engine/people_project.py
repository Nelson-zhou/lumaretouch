"""Saved-graph validation for project and history integration, without migration guesses."""
from . import people_state as S


def validate_records(value):
    """Use on active, undo and redo trees before any live-state mutation."""
    if isinstance(value,dict):
        from .blush_makeup_project import check as check_blush_library
        for name in ('blush_makeup_library','_blush_makeup_library'):
            if name in value:check_blush_library(value[name])
        for key in ('people_graph','_people_state'):
            if key in value:
                if value[key] is None: raise ValueError('Saved people state cannot be null')
                from .blush_makeup_state import validate_graph
                validate_graph(value[key])
        if 'people_support_assets' in value:
            from .people_support_assets import check_store
            check_store(value['people_support_assets'])
            from .eye_light_support import validate_project
            validate_project(value)
            from .blush_makeup_support import validate_project as validate_blush_support
            validate_blush_support(value)
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
