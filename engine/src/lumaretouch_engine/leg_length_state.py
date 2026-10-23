# SPDX-License-Identifier: GPL-3.0-or-later
"""Original length-only policy. No anatomy guessed; no width-control alias."""
from copy import deepcopy
import math
OPERATION_ID='lnx.leg_length.v1'
IDS={'overall':'LNX-REF-PC-32473-C-d79658697a','thigh':'LNX-REF-PC-32473-C-eefc19db17','calf':'LNX-REF-PC-32473-C-17fb085b4c'}
KEYS=('thigh','calf')
REQUIRED_ANCHORS=(23,24,25,26,27,28,29,30,31,32)
SUPPORT_KIND='leg-length-visible-transition-review-v1'
FLAGS=('joints_visible','separate_legs','not_foreshortened','ownership_confirmed','background_support_reviewed','foot_contours_visible','torso_transition_reviewed')
SIDES=('left','right')
COLUMNS=('outer_left','inner_left','inner_right','outer_right','foot_end','support_end')
def neutral():return {'version':1,'thigh':0.,'calf':0.}
def check(value):
    if type(value) is not dict or set(value)!={'version',*KEYS} or type(value['version']) is not int or value['version']!=1:raise ValueError('Invalid length recipe; overall is not a stored warp')
    for k in KEYS:
        if type(value[k]) not in (int,float) or not math.isfinite(value[k]) or not 0<=value[k]<=1:raise ValueError('Length strength outside original local 0–1 range')
    return deepcopy(value)
def adjust(value,key,amount):
    out=check(value)
    if key not in (*KEYS,'overall'):raise ValueError('Unknown length control')
    for k in KEYS if key=='overall' else (key,):out[k]=amount
    return check(out)
def active(value):return any(check(value)[k]!=0 for k in KEYS)
def vector(value):return [check(value)[k] for k in KEYS]
def portable(value):return check(value)
def check_support(value,record=None):
    if type(value) is not dict or set(value)!={'version','method','legs',*FLAGS} or type(value['version']) is not int or value['version']!=1 or value['method']!='user-reviewed-visible-length-support':raise ValueError('Invalid explicit length support')
    if any(value[k] is not True for k in FLAGS):raise ValueError('Review actual joints, contours, torso/foot transitions and background; no inferred anatomy')
    if type(value['legs']) is not dict or set(value['legs'])!=set(SIDES):raise ValueError('Both visible legs need independent source review')
    for side in SIDES:
        item=value['legs'][side]
        if type(item) is not dict or set(item)!=set(COLUMNS):raise ValueError('Review four horizontal support boundaries and two foot transition levels')
        if any(type(n) not in (int,float) or not math.isfinite(n) or not 0<n<1 for n in item.values()):raise ValueError('Use finite normalized original-source coordinates')
        if not item['outer_left']<item['inner_left']<item['inner_right']<item['outer_right'] or not item['foot_end']<item['support_end']:raise ValueError('Support boundaries must be strictly ordered')
    a,b=(value['legs'][s] for s in SIDES)
    if not (a['outer_right']<b['outer_left'] or b['outer_right']<a['outer_left']):raise ValueError('Length supports overlap: crossed or inseparable legs are unsupported')
    if record is not None:
        from . import body_pose_evidence as E
        record=E.check(record);p=record['points'];w=record['source']['width']-1;h=record['source']['height']-1
        for i in REQUIRED_ANCHORS:
            q=p[i]
            if not 0<q['x']<1 or not 0<q['y']<1 or q['visibility']<.8 or q['presence']<.8:raise ValueError('Hidden or cropped hip/knee/ankle/heel/toe cannot be overridden by review')
        for side,indices in zip(SIDES,((23,25,27,29,31),(24,26,28,30,32))):
            s=value['legs'][side];hip,knee,ankle,heel,toe=(p[i] for i in indices)
            if not hip['y']<knee['y']<ankle['y']<s['foot_end']<s['support_end']:raise ValueError('Only upright visible legs with room below complete feet are supported')
            if any(not s['inner_left']<p[i]['x']<s['inner_right'] for i in indices):raise ValueError('Real joints/feet must lie inside reviewed contour plateau')
            if any(not ankle['y']<=q['y']<s['foot_end'] for q in (heel,toe)):raise ValueError('Foot transition does not contain observed heel and toe')
            for a,b in ((hip,knee),(knee,ankle)):
                dx=(b['x']-a['x'])*w;dy=(b['y']-a['y'])*h
                if dy<32 or abs(dx)>dy*.35 or abs(b['z']-a['z'])*w>dy*.35:raise ValueError('Bent, tiny or strongly foreshortened leg is unsupported')
    return deepcopy(value)
def policy_check_support(value,record):return check_support(value,record)
def support_vector(value):
    value=check_support(value)
    return [value['legs'][side][k] for side in SIDES for k in COLUMNS]
def policy():
    from .body_pose_operations import OperationPolicy
    return OperationPolicy(OPERATION_ID,neutral,check,active,REQUIRED_ANCHORS,SUPPORT_KIND,policy_check_support)
def policies():return {OPERATION_ID:policy()}
