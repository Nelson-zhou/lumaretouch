# SPDX-License-Identifier: GPL-3.0-or-later
"""One PC32473 family; four internal visibility policies, never hidden joints.

All numbers, defaults and partial-segment behavior are ORIGINAL local policy.
Neither segment amplitudes nor left/right linking introduce additional warps.
"""
from copy import deepcopy
import math

FAMILY_ID = 'lnx.arm_shape.v1'
REQUIREMENT_ID = 'LNX-REF-PC-32473-C-5d25f1744f'
SEGMENTS = ('left_upper', 'left_forearm', 'right_upper', 'right_forearm')
JOINTS = {'left_upper':(11,13), 'left_forearm':(13,15),
          'right_upper':(12,14), 'right_forearm':(14,16)}
OPERATION_IDS = {key:'lnx.arm_shape.'+key+'.v1' for key in SEGMENTS}
SUPPORT_KIND = 'arm-source-visible-contour-v1'
STRATEGIES = ('reviewed-contour', 'sam2-prompted-contour')
STATIONS = tuple(i/10 for i in range(1,10))
FLAGS = ('joints_visible', 'entire_segment_visible', 'not_crossing',
         'not_foreshortened', 'clear_torso_border', 'ownership_confirmed',
         'visible_material_only', 'transition_pixels_reviewed')
FACTORS = {'reviewed-contour':1.8, 'sam2-prompted-contour':1.4}


def neutral():
    return {'version':1, 'strategy':'reviewed-contour', 'amount':0.}


def check(value):
    if type(value) is not dict or set(value)!={'version','strategy','amount'} or type(value['version']) is not int or value['version']!=1 or value['strategy'] not in STRATEGIES:
        raise ValueError('Invalid arm strategy/recipe')
    n=value['amount']
    if type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1:
        raise ValueError('Arm strength must be within the original local 0–1 thinning range')
    return deepcopy(value)


def active(value): return check(value)['amount']!=0


def segment_for(operation_id):
    for key,value in OPERATION_IDS.items():
        if value==operation_id: return key
    raise ValueError('Unknown arm segment operation')


def rectangle(value):
    if type(value) is not list or len(value)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in value) or value[0]>=value[2] or value[1]>=value[3]:
        raise ValueError('Review a finite source-normalized XYXY rectangle')
    return deepcopy(value)


def region(value):
    if type(value) is not dict or set(value)!={'selection_box','exclusions'}:
        raise ValueError('Arm ownership scope is missing')
    rectangle(value['selection_box'])
    if type(value['exclusions']) is not list or not 1<=len(value['exclusions'])<=32:
        raise ValueError('Explicitly mark torso/contact/other-person exclusion rectangles')
    for box in value['exclusions']: rectangle(box)
    return deepcopy(value)


def axis(record, segment):
    from . import body_pose_evidence as E
    record=E.check(record)
    if segment not in SEGMENTS: raise ValueError('Unknown arm segment')
    w,h=record['source']['width']-1,record['source']['height']-1
    a,b=(record['points'][i] for i in JOINTS[segment])
    for p in (a,b):
        if p['visibility']<.8 or p['presence']<.8 or not 0<p['x']<1 or not 0<p['y']<1:
            raise ValueError('This segment needs both actual visible source endpoints')
    start=(a['x']*w,a['y']*h); dx,dy=(b['x']-a['x'])*w,(b['y']-a['y'])*h
    length=math.hypot(dx,dy)
    if length<32 or length<min(w,h)*.04: raise ValueError('Arm segment is too small to review')
    if abs(a['z']-b['z'])*w>length*.65:
        raise ValueError('Strong arm foreshortening/depth ambiguity is unsupported')
    return start,(dx/length,dy/length),length,min(w,h)


def check_support(value, record, *, segment):
    from . import body_pose_evidence as E
    required={'version','segment','strategy','stations','negative','positive','region','selection','confirmations'}
    if type(value) is not dict or set(value)!=required or type(value['version']) is not int or value['version']!=1 or value['segment']!=segment or value['strategy'] not in STRATEGIES or value['stations']!=list(STATIONS):
        raise ValueError('Arm source support schema/segment/strategy mismatch')
    if type(value['confirmations']) is not dict or set(value['confirmations'])!=set(FLAGS) or any(value['confirmations'][k] is not True for k in FLAGS):
        raise ValueError('Review visible joints, silhouette, ownership, torso separation and transition pixels; never invent hidden anatomy')
    region(value['region']); start,u,length,scale=axis(record,segment)
    for side in ('negative','positive'):
        widths=value[side]
        if type(widths) is not list or len(widths)!=len(STATIONS) or any(type(x) not in (int,float) or not math.isfinite(x) or not 2<=x*scale<=length*.3 for x in widths):
            raise ValueError('Nine actual source contour widths per side are required, not pose-derived widths')
    if value['strategy']=='reviewed-contour':
        if value['selection'] is not None: raise ValueError('Manual review cannot claim a neural selection receipt')
    else:
        from .arm_shape_selection import check_selection, measured_widths
        selection=check_selection(value['selection'],record,segment,value['region'])
        negative,positive=measured_widths(selection,record,segment)
        if value['negative']!=negative or value['positive']!=positive:
            raise ValueError('Neural widths must be the exact image-conditioned mask measurements')
    # Support boxes are conservative envelopes around the real, rotated axis.
    radius=max(*value['negative'],*value['positive'])*scale*FACTORS[value['strategy']]
    if radius>length*.46: raise ValueError('Arm falloff exceeds the local segment budget')
    w,h=record['source']['width']-1,record['source']['height']-1
    n=(-u[1],u[0]); corners=[(start[0]+t*length*u[0]+s*radius*n[0],start[1]+t*length*u[1]+s*radius*n[1]) for t in (0,1) for s in (-1,1)]
    if any(not 1<=x<=w-1 or not 1<=y<=h-1 for x,y in corners):
        raise ValueError('Arm transition support is cropped')
    # Widths are checked against the reviewed ownership window at each station.
    box=value['region']['selection_box']
    for side,sign in (('negative',-1),('positive',1)):
        for t,width in zip(STATIONS,value[side]):
            x=(start[0]+t*length*u[0]+sign*width*scale*n[0])/w
            y=(start[1]+t*length*u[1]+sign*width*scale*n[1])/h
            if not box[0]<x<box[2] or not box[1]<y<box[3]:
                raise ValueError('Visible contour leaves the reviewed ownership scope')
    return deepcopy(value)


def _check_left_upper(value,record):return check_support(value,record,segment='left_upper')
def _check_left_forearm(value,record):return check_support(value,record,segment='left_forearm')
def _check_right_upper(value,record):return check_support(value,record,segment='right_upper')
def _check_right_forearm(value,record):return check_support(value,record,segment='right_forearm')
CHECKERS=dict(zip(SEGMENTS,(_check_left_upper,_check_left_forearm,_check_right_upper,_check_right_forearm)))


def policies():
    from .body_pose_operations import OperationPolicy
    return {OPERATION_IDS[key]:OperationPolicy(OPERATION_IDS[key],neutral,check,active,JOINTS[key],SUPPORT_KIND,CHECKERS[key]) for key in SEGMENTS}


def family(row):
    return {key:check(row['operations'].get(OPERATION_IDS[key],{}).get('recipe',neutral())) for key in SEGMENTS}


def check_family(value):
    if type(value) is not dict or set(value)!=set(SEGMENTS): raise ValueError('Arm family needs explicit intent for each side and segment')
    return {key:check(value[key]) for key in SEGMENTS}
