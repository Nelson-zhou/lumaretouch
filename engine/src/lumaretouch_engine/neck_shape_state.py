# SPDX-License-Identifier: GPL-3.0-or-later
"""Visible neck controls. All ranges and safety limits are original local policy."""
from copy import deepcopy
import math
OPERATION_ID='lnx.neck_shape.v1'
IDS={'length':'LNX-REF-PC-32473-C-903ca47834','width':'LNX-REF-PC-32473-C-614d728bcd'}
ANCHORS=(0,7,8,11,12)
SUPPORT_KIND='neck-visible-head-transport-v1'
FLAGS=('bounds_visible','contours_visible','not_occluded','not_foreshortened','ownership_confirmed','transition_reviewed','complete_head_hair_reviewed')
def neutral():return {'version':1,'length':0.,'width':{'linked':True,'left':0.,'right':0.}}
def number(n):return type(n) in (int,float) and math.isfinite(n)
def check(v):
    if type(v) is not dict or set(v)!={'version','length','width'} or type(v['version']) is not int or v['version']!=1:raise ValueError('Invalid neck recipe')
    b=v['width']
    if type(b) is not dict or set(b)!={'linked','left','right'} or type(b['linked']) is not bool:raise ValueError('Width requires its own persisted bilateral lock')
    if any(not number(n) or not -1<=n<=1 for n in (v['length'],b['left'],b['right'])):raise ValueError('Neck range is original local -1 to 1')
    return deepcopy(v)
def active(v):
    v=check(v);return any(n!=0 for n in (v['length'],v['width']['left'],v['width']['right']))
def portable(v):return check(v)
def adjust(v,key,amount,side='left'):
    v=check(v)
    if key=='length':v[key]=amount
    elif key=='width' and side in ('left','right'):
        for k in ('left','right') if v['width']['linked'] else (side,):v[key][k]=amount
    else:raise ValueError('Unknown neck control')
    return check(v)
def link(v,linked):
    v=check(v)
    if type(linked) is not bool:raise ValueError('Invalid width link')
    v['width']['linked']=linked;return v

def check_support(v,record=None):
    keys={'version','upper','lower','center_x','negative','positive','head_box','transition_box','anatomical_left','exclusions','confirmations'}
    if type(v) is not dict or set(v)!=keys or type(v['version']) is not int or v['version']!=1:raise ValueError('Invalid neck support')
    if type(v['confirmations']) is not dict or set(v['confirmations'])!=set(FLAGS) or any(v['confirmations'][k] is not True for k in FLAGS):raise ValueError('Review visible neck, full head/hair and clear transition; hidden collars/hair and severe perspective refuse')
    if not all(number(v[k]) and 0<v[k]<1 for k in ('upper','lower','center_x')) or v['upper']>=v['lower']:raise ValueError('Actual visible upper/lower neck bounds required')
    for key in ('negative','positive'):
        if type(v[key]) is not list or len(v[key])!=5 or any(not number(n) or not 0<n<.25 for n in v[key]):raise ValueError('Five actual visible contour widths per side required; never face/shoulder estimates')
    if v['anatomical_left'] not in ('negative','positive'):raise ValueError('Review anatomical left orientation explicitly')
    def box(b):return type(b) is list and len(b)==4 and all(number(n) and 0<n<1 for n in b) and b[0]<b[2] and b[1]<b[3]
    if not box(v['head_box']) or not box(v['transition_box']) or type(v['exclusions']) is not list or len(v['exclusions'])>32 or not all(box(b) for b in v['exclusions']):raise ValueError('Visible head/hair and external transition boxes required')
    a=v['head_box'];b=v['transition_box'];c=v['center_x'];r=2*max(*v['negative'],*v['positive'])
    if not b[0]<a[0]<c<a[2]<b[2] or not b[1]<a[1]<a[3]<=v['upper']<v['lower']<b[3] or not b[0]<c-r<c+r<b[2]:raise ValueError('Connected head plateau/neck/transition are not nested with clearance')
    if record is not None:
        from . import body_pose_evidence as E
        record=E.check(record);p=record['points'];w=record['source']['width'];h=record['source']['height']
        if (v['lower']-v['upper'])*h<16:raise ValueError('Neck too small to verify')
        for i in ANCHORS:
            q=p[i]
            if q['visibility']<.8 or q['presence']<.8:raise ValueError('Missing observed head/shoulder support')
        if any(not a[0]<p[i]['x']<a[2] or not a[1]<p[i]['y']<a[3] for i in (0,7,8)):raise ValueError('Reviewed complete-head plateau does not contain actual observed head')
        if abs(p[11]['z']-p[12]['z'])*w>abs(p[11]['x']-p[12]['x'])*w*.35:raise ValueError('Severe perspective is unsupported')
    return deepcopy(v)
def policy():
    from .body_pose_operations import OperationPolicy
    return OperationPolicy(OPERATION_ID,neutral,check,active,ANCHORS,SUPPORT_KIND,check_support)
def policies():return {OPERATION_ID:policy()}
