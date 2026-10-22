"""Strict nested v8 studio intent validation; old schemas migrate only missing keys."""
from .studio_background_state import check_saved_record
STATE_KEYS=('_strength','_grade','_grade_scope','_local_masks','_local_grade_layers','_effect_recovery','_manual_liquify')

def validate_records(value,*,required=False,allowed=True):
    if isinstance(value,dict):
        if '_studio_background' in value:
            if not allowed:raise ValueError('背景调整配方不能保存到 v8 之前的项目版本')
            check_saved_record(value['_studio_background'])
        elif required and any(k in value for k in STATE_KEYS):
            raise ValueError('项目 v8 的文档或历史状态缺少背景调整配方')
        for child in value.values():validate_records(child,required=required,allowed=allowed)
    elif isinstance(value,list):
        for child in value:validate_records(child,required=required,allowed=allowed)
