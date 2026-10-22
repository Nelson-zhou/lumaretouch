"""Saved-graph validation for project and history integration, without migration guesses."""
from . import people_state as S


def validate_records(value):
    """Use on active, undo and redo trees before any live-state mutation."""
    if isinstance(value,dict):
        for key in ('people_graph','_people_state'):
            if key in value:
                if value[key] is None: raise ValueError('Saved people state cannot be null')
                S.check(value[key])
        if 'people_support_assets' in value:
            from .people_support_assets import check_store
            check_store(value['people_support_assets'])
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
