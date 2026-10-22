"""Strict retained sky intent across documents, inactive versions and history."""
from .sky_replacement_state import check_saved_record
STATE_KEYS=('_strength','_grade','_grade_scope','_local_masks','_local_grade_layers',
            '_effect_recovery','_manual_liquify','_studio_background','_optics')


def validate_records(value,*,required=False,allowed=True):
    if isinstance(value,dict):
        if '_sky_replacement' in value:
            if not allowed:
                raise ValueError('换天空配方不能伪装成未支持它的旧项目版本')
            check_saved_record(value['_sky_replacement'])
        elif required and any(k in value for k in STATE_KEYS):
            raise ValueError('项目文档或历史状态缺少换天空配方')
        for child in value.values():
            validate_records(child,required=required,allowed=allowed)
    elif isinstance(value,list):
        for child in value:
            validate_records(child,required=required,allowed=allowed)
