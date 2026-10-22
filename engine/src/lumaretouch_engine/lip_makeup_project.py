"""Validate every nested saved document/history/version recipe.

Missing legacy field means neutral. Present malformed/null recipe is rejected;
never silently erase an active effect from a newer or corrupted project.
"""
from . import lip_makeup_state as S

def check_saved(value):
    if value is None: raise ValueError('已保存唇妆配方不能为 null')
    return S.check(value)

def validate_records(value):
    if isinstance(value,dict):
        if '_lip_makeup' in value: check_saved(value['_lip_makeup'])
        for child in value.values(): validate_records(child)
    elif isinstance(value,list):
        for child in value: validate_records(child)
