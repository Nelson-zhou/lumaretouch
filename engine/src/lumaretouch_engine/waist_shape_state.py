# SPDX-License-Identifier: GPL-3.0-or-later
"""Original manual visible-waist contract, not inferred anatomy or AI segmentation."""
from copy import deepcopy
import math
OPERATION_ID='lnx.waist_shape.v1'
REQUIREMENT_ID='LNX-REF-PC-32473-C-8268ea3e37'
SUPPORT_KIND='waist-source-visible-contour-v1'
ANCHORS=(11,12,23,24)
STATIONS=tuple(i/10 for i in range(1,10))
FACTOR=1.8
FLAGS=('bilateral_visible','bounds_reviewed','not_occluded','not_foreshortened',
       'ownership_confirmed','visible_material_only','transition_pixels_reviewed')


def neutral():return {'version':1,'amount':0.}


def check(value):
    if type(value) is not dict or set(value)!={'version','amount'} or type(value['version']) is not int or value['version']!=1:
        raise ValueError('Invalid waist recipe')
    n=value['amount']
    if type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1:
        raise ValueError('Waist amount must use the original local 0–1 inward-only range')
    return deepcopy(value)


def active(value):return check(value)['amount']!=0


def rectangle(value):
    if type(value) is not list or len(value)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in value) or value[0]>=value[2] or value[1]>=value[3]:
        raise ValueError('Review a source-normalized XYXY ownership rectangle')
    return deepcopy(value)


def axis(record):
    from . import body_pose_evidence as E
    record=E.check(record);w,h=record['source']['width']-1,record['source']['height']-1
    points=[record['points'][i] for i in ANCHORS]
    for p in points:
        if p['visibility']<.8 or p['presence']<.8 or not 0<p['x']<1 or not 0<p['y']<1:
            raise ValueError('Waist orientation requires all four actual visible shoulder/hip points')
    a,b,c,d=points
    start=((a['x']+b['x'])*w/2,(a['y']+b['y'])*h/2)
    end=((c['x']+d['x'])*w/2,(c['y']+d['y'])*h/2)
    dx,dy=end[0]-start[0],end[1]-start[1];length=math.hypot(dx,dy)
    if length<64 or length<min(w,h)*.08:raise ValueError('Torso orientation is too small to review')
    u=(dx/length,dy/length);n=(-u[1],u[0]);spans=[]
    for left,right in ((a,b),(c,d)):
        x,y=(right['x']-left['x'])*w,(right['y']-left['y'])*h
        span=x*n[0]+y*n[1];spans.append(span)
        if abs(span)<length*.2 or abs(x*u[0]+y*u[1])>abs(span)*.6 or abs(left['z']-right['z'])*w>abs(span)*.6:
            raise ValueError('Side-on, rotated-depth or severe perspective torso is unsupported')
    if spans[0]*spans[1]<=0 or max(map(abs,spans))>min(map(abs,spans))*2:
        raise ValueError('Twisted or severely perspective shoulder/hip orientation is ambiguous')
    return start,u,length,min(w,h)


def check_support(value,record):
    required={'version','upper','lower','stations','negative','positive','region','confirmations'}
    if type(value) is not dict or set(value)!=required or type(value['version']) is not int or value['version']!=1 or value['stations']!=list(STATIONS):
        raise ValueError('Invalid reviewed bilateral waist contour support')
    if type(value['confirmations']) is not dict or set(value['confirmations'])!=set(FLAGS) or any(value['confirmations'][k] is not True for k in FLAGS):
        raise ValueError('Review both visible waist contours and bounds, ownership, occlusion and transition; hidden anatomy is unsupported')
    start,u,length,scale=axis(record)
    upper,lower=value['upper'],value['lower']
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (upper,lower)) or not 0<upper<lower<1 or (lower-upper)*length<32:
        raise ValueError('Explicit source-reviewed upper and lower waist bounds are required, at least 32 pixels apart')
    for side in ('negative','positive'):
        widths=value[side]
        if type(widths) is not list or len(widths)!=len(STATIONS) or any(type(x) not in (int,float) or not math.isfinite(x) or not 2<=x*scale<=length*.8 for x in widths):
            raise ValueError('Nine independently measured visible contour widths are required on each side')
    region=value['region']
    if type(region) is not dict or set(region)!={'selection_box','exclusions'} or type(region['exclusions']) is not list or len(region['exclusions'])>32:
        raise ValueError('Explicit waist ownership and exclusion scope is required')
    box=rectangle(region['selection_box'])
    for exclusion in region['exclusions']:rectangle(exclusion)
    w,h=record['source']['width']-1,record['source']['height']-1;n=(-u[1],u[0])
    radius=max(*value['negative'],*value['positive'])*scale*FACTOR
    if radius>3*(lower-upper)*length:raise ValueError('Waist transition exceeds the original compact-field budget')
    corners=[(start[0]+t*length*u[0]+s*radius*n[0],start[1]+t*length*u[1]+s*radius*n[1]) for t in (upper,lower) for s in (-1,1)]
    if any(not 1<=x<=w-1 or not 1<=y<=h-1 for x,y in corners):raise ValueError('Waist transition support is cropped')
    if any(not box[0]<=x/w<=box[2] or not box[1]<=y/h<=box[3] for x,y in corners):
        raise ValueError('Entire waist transition must fit the reviewed ownership region')
    for side,sign in (('negative',-1),('positive',1)):
        for t,width in zip(STATIONS,value[side]):
            along=length*(upper+t*(lower-upper))
            x=(start[0]+along*u[0]+sign*width*scale*n[0])/w;y=(start[1]+along*u[1]+sign*width*scale*n[1])/h
            if not box[0]<x<box[2] or not box[1]<y<box[3]:raise ValueError('Waist contour leaves its reviewed ownership scope')
    return deepcopy(value)


def policy():
    from .body_pose_operations import OperationPolicy
    return OperationPolicy(OPERATION_ID,neutral,check,active,ANCHORS,SUPPORT_KIND,check_support)


def policies():return {OPERATION_ID:policy()}


def portable(value):return check(value)
