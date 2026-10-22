"""Strict v9 nested optical intent validation without changing earlier schemas."""
from .optics_state import check
KEYS=('_strength','_grade','_local_masks','_local_grade_layers','_effect_recovery','_manual_liquify','_studio_background')
def validate_records(value,*,required=False,allowed=True):
    if isinstance(value,dict):
        if '_optics' in value:
            if not allowed: raise ValueError('镜头/透视配方要求项目 v9 或更高版本')
            if value['_optics'] is None: raise ValueError('镜头/透视保存记录不能是空值')
            check(value['_optics'])
        elif required and any(k in value for k in KEYS): raise ValueError('项目 v9 文档或历史缺少镜头/透视配方')
        for child in value.values(): validate_records(child,required=required,allowed=allowed)
    elif isinstance(value,list):
        for child in value: validate_records(child,required=required,allowed=allowed)
