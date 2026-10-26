"""Optional v24 records; validate every retained version and history."""
from . import final_canvas_flip_state as S

def validate_records(value, *, allowed=True, depth=0):
    if depth > 64:
        raise ValueError('Final canvas flip project nesting exceeds bounds')
    if isinstance(value, dict):
        for key in (S.KEY, 'final_canvas_flip'):
            if key in value:
                if not allowed:
                    raise ValueError('Final canvas flip requires project v24')
                S.check(value[key])
        for child in value.values():
            validate_records(child, allowed=allowed, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_records(child, allowed=allowed, depth=depth + 1)
