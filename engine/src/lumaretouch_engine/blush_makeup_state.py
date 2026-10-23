# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable blush intent. No anatomy, source binding, palette or recovery travels."""
import math
import re
from copy import deepcopy
OP = 'lnx.blush_makeup.v1'
PATTERNS = ('apple', 'oval', 'lift', 'ribbon', 'under_eye', 'sunset', 'petal', 'crescent',
            'cloud', 'diagonal', 'draped', 'soft_square')
KEYS = ('pattern', 'strength', 'colour')
IDS = {'family':'e7ccb5a9e2', 'recommended':'6be18714f8', 'eyedropper':'53df3c11b3',
       'rgb':'3f0064d896', 'hex':'8059d0cdd0', 'saved':'6f5d708f87'}

def colour(value):
    if type(value) is not str or not re.fullmatch('#[0-9a-fA-F]{6}',value):
        raise ValueError('腮红 HEX 必须为 #RRGGBB')
    return value.upper()

def rgb(value):
    if type(value) not in (list,tuple) or len(value)!=3 or any(type(v) is not int or not 0<=v<=255 for v in value):
        raise ValueError('RGB 需要三个 0–255 整数')
    return '#'+''.join(f'{v:02X}' for v in value)

def neutral():return {'version':1,'pattern':'apple','strength':0.,'colour':'#D77A87'}

def check(value):
    if value is None:return neutral()
    if type(value) is not dict or set(value)!={'version',*KEYS} or type(value['version']) is not int or value['version']!=1:
        raise ValueError('腮红配方字段或版本无效')
    if type(value['pattern']) is not str or value['pattern'] not in PATTERNS:raise ValueError('未知腮红图案')
    if type(value['strength']) not in (int,float) or not math.isfinite(value['strength']) or not 0<=value['strength']<=1:
        raise ValueError('腮红程度需为 0–1 有限数值；本地定义范围')
    return {'version':1,'pattern':value['pattern'],'strength':float(value['strength']),'colour':colour(value['colour'])}

def active(value):return check(value)['strength']!=0

def preset(value):return check(value)

def check_palette(value):
    if type(value) is not list or len(value)>6:raise ValueError('最多收藏 6 款颜色')
    result=[colour(c) for c in value]
    if len(set(result))!=len(result):raise ValueError('收藏颜色不能重复')
    return result

def save_colour(palette,value):
    result=check_palette(palette);value=colour(value)
    if value in result:return result
    if len(result)==6:raise ValueError('已收藏 6 色，请先移除一色')
    return result+[value]

def remove_colour(palette,value):return [c for c in check_palette(palette) if c!=colour(value)]

def patches(value):
    r=check(value)
    return [{'operation_id':OP,'parameter_path':'/'+key,'unset':False,'value':r[key]} for key in KEYS]

def validate_graph(state):
    """Run at project/history restore, including dormant faces and shared scopes."""
    from . import people_state as P
    state=P.check(state)
    for row in state['overrides']:
        if row['operation_id']==OP:
            key=row['parameter_path'][1:]
            if row['parameter_path']!='/'+key or key not in KEYS:raise ValueError('未知腮红参数路径')
            check({**neutral(),key:row['value']})
    return deepcopy(state)
