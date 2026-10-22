"""Validate saved recipes and source-person ownership, including redo records."""
import re
from . import eye_shape_state as S

def check_saved(value):
    if value is None: raise ValueError('保存的眼形配方不能为 null')
    return S.check(value)

def validate_records(value):
    if isinstance(value,dict):
        if '_eye_shape' in value:
            r=check_saved(value['_eye_shape']); owner=value.get('_eye_shape_owner')
            if owner is not None and (type(owner) is not str or not re.fullmatch('[0-9a-f]{64}',owner)):
                raise ValueError('眼形人物归属无效')
            if S.active(r) and owner is None: raise ValueError('活动眼形缺少人物归属，不能猜测重绑')
        for child in value.values(): validate_records(child)
    elif isinstance(value,list):
        for child in value: validate_records(child)
