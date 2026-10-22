"""Validate saved recipes and source-person ownership, including redo records."""
import re
from . import nose_shape_state as S

def check_saved(value):
    if value is None: raise ValueError('保存的鼻形配方不能为 null')
    return S.check(value)

def validate_records(value):
    if isinstance(value,dict):
        if '_nose_shape' in value:
            r=check_saved(value['_nose_shape']); owner=value.get('_nose_shape_owner')
            if owner is not None and (type(owner) is not str or not re.fullmatch('[0-9a-f]{64}',owner)):
                raise ValueError('鼻形人物归属无效')
            if S.active(r) and owner is None: raise ValueError('活动鼻形缺少人物归属，不能猜测重绑')
        for child in value.values(): validate_records(child)
    elif isinstance(value,list):
        for child in value: validate_records(child)
