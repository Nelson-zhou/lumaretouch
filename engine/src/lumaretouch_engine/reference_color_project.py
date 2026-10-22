"""Saved reference intent and lossless project-bundled reference asset validation."""
from . import reference_color_state as S


def validate_records(value):
    if isinstance(value,dict):
        if S.KEY in value:
            recipe=S.check(value[S.KEY]);bundle=value.get('_reference_color_bundle')
            if recipe['reference'] is not None and not bundle:
                raise ValueError('项目参考校正缺少保留的参考图资源，不能静默丢失样片')
            if bundle is not None and (type(bundle) is not list or not 1<=len(bundle)<=40):
                raise ValueError('项目参考图资源分块无效')
        for child in value.values():validate_records(child)
    elif isinstance(value,list):
        for child in value:validate_records(child)
