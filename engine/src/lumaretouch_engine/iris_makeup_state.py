# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable original iris texture intent; no source anatomy travels in presets."""
import math
from copy import deepcopy
OP='lnx.iris_makeup.v1'
KEYS=('pattern','strength')
PATTERNS=('amber_rays','slate_fibres','olive_crypts','honey_speckle','ocean_arcs','copper_star','moss_lace','violet_fan','silver_rings','chestnut_branches','teal_mosaic')
REQUIREMENT='LNX-REF-PC-32471-C-62d685c7ac'
def neutral():return {'version':1,'pattern':PATTERNS[0],'strength':0.}
def check(value):
    if value is None:return neutral()
    if type(value) is not dict or set(value)!={'version',*KEYS} or type(value['version']) is not int or value['version']!=1:raise ValueError('美瞳配方字段无效')
    if type(value['pattern']) is not str or value['pattern'] not in PATTERNS:raise ValueError('未知美瞳纹理')
    if type(value['strength']) not in (int,float) or not math.isfinite(value['strength']) or not 0<=value['strength']<=1:raise ValueError('美瞳程度须为本地定义的 0–1 有限数值')
    return {'version':1,'pattern':value['pattern'],'strength':float(value['strength'])}
def active(value):return check(value)['strength']!=0
def preset(value):return check(value)
def patches(value):
    r=check(value);return [{'operation_id':OP,'parameter_path':'/'+k,'unset':False,'value':r[k]} for k in KEYS]
def validate_graph(state):
    from . import people_state as P
    state=P.check(state)
    for row in state['overrides']:
        if row['operation_id']==OP:
            key=row['parameter_path'][1:]
            if key not in KEYS or row['parameter_path']!='/'+key:raise ValueError('未知美瞳参数')
            check({**neutral(),key:row['value']})
    return deepcopy(state)
