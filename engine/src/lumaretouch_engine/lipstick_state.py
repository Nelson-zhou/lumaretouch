# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable lipstick intent. No anatomy, source binding, palette or recovery travels."""
import math
import re
from copy import deepcopy
OP = 'lnx.lipstick.v1'
PATTERNS = ('full', 'inner_bloom', 'soft_edge', 'contour', 'center_glow', 'upper_focus', 'lower_focus', 'cupid', 'corner_fade', 'vertical_ombre', 'horizontal_ombre', 'double_rim', 'petal')
TEXTURES = ('satin', 'matte', 'cream', 'pearl', 'water_gloss')
KEYS = ('pattern', 'strength', 'colour', 'texture')
IDS = {'family':'79b10e6c77','recommended':'afeef2f365','eyedropper':'aa527d3820','rgb':'7143856a26','hex':'ff8f73cbc7','saved':'adcea25fde', 'satin':'4c9236d46f','matte':'499cecca98','cream':'d0e1f03b0f','pearl':'565b3b9081','water_gloss':'bdd6881023'}


def colour(value):
    if type(value) is not str or not re.fullmatch('#[0-9a-fA-F]{6}',value):
        raise ValueError('口红 HEX 必须为 #RRGGBB')
    return value.upper()

def rgb(value):
    if type(value) not in (list,tuple) or len(value)!=3 or any(type(v) is not int or not 0<=v<=255 for v in value):
        raise ValueError('RGB 需要三个 0–255 整数')
    return '#'+''.join(f'{v:02X}' for v in value)

def neutral():return {'version':1,'pattern':'full','strength':0.,'colour':'#A94359','texture':'satin'}

def check(value):
    if value is None:return neutral()
    if type(value) is not dict or set(value)!={'version',*KEYS} or type(value['version']) is not int or value['version']!=1:
        raise ValueError('口红配方字段或版本无效')
    if type(value['pattern']) is not str or value['pattern'] not in PATTERNS:raise ValueError('未知口红图案')
    if type(value['strength']) not in (int,float) or not math.isfinite(value['strength']) or not 0<=value['strength']<=1:
        raise ValueError('口红程度需为 0–1 有限数值；本地定义范围')
    if type(value['texture']) is not str or value['texture'] not in TEXTURES:raise ValueError('未知口红质地')
    return {'texture':value['texture'],'version':1,'pattern':value['pattern'],'strength':float(value['strength']),'colour':colour(value['colour'])}

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
            if row['parameter_path']!='/'+key or key not in KEYS:raise ValueError('未知口红参数路径')
            check({**neutral(),key:row['value']})
    return deepcopy(state)
