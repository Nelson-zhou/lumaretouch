# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone source-owned visible hand geometry. No body/face prerequisites.

All limits and signed controls are original local policy, not handbook numbers.
One explicitly reviewed hand is retained per document in v1. No identity inference.
"""
from copy import deepcopy
import math
import re

FAMILY='hand_shape'
OP='lnx.hand_shape.v1'
KINDS=('palm','finger','joint')
PARTS=('palm','thumb','index','middle','ring','little')
FLAGS=('visible_only','ownership','no_contact','transitions','protection_reviewed')


def digest(value):
    if type(value) is not str or re.fullmatch('[a-f0-9]{64}',value) is None:raise ValueError('Hand geometry needs exact SHA-256 provenance')
    return value


def token(value):
    if type(value) is not str or re.fullmatch('[A-Za-z0-9_.:-]{1,128}',value) is None:raise ValueError('Invalid hand instance/region identity')
    return value


def source(value):
    if type(value) is not dict or set(value)!={'sha256','width','height'}:raise ValueError('Hand geometry requires exact canonical source dimensions')
    digest(value['sha256'])
    if any(type(value[k]) is not int or not 2<=value[k]<=65536 for k in ('width','height')) or value['width']*value['height']>32_000_000:raise ValueError('Hand geometry source exceeds 32 MP budget')
    return deepcopy(value)


def number(value,lo,hi):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('Invalid finite hand geometry number')
    return float(value)


def point(value):
    if type(value) is not list or len(value)!=2:raise ValueError('Mark an actual source-normalized xy point')
    return [number(x,0,1) for x in value]


def amounts(value):
    if type(value) is not dict or set(value)!=set(KINDS):raise ValueError('Hand width, fingers and joints need separate explicit controls')
    return {k:number(value[k],-1,1) for k in KINDS}


def review(value):
    keys={'version','domain','hand_id','regions','protect','proposal_id','confirmed'}
    if type(value) is not dict or set(value)!=keys or type(value['version']) is not int or value['version']!=1 or value['domain']!='source-normalized':raise ValueError('Invalid visible hand support review')
    token(value['hand_id'])
    if value['proposal_id'] is not None:token(value['proposal_id'])
    if type(value['confirmed']) is not dict or set(value['confirmed'])!=set(FLAGS) or any(value['confirmed'][k] is not True for k in FLAGS):raise ValueError('Explicitly review visible anatomy, ownership, contact, transition pixels and protection')
    if type(value['regions']) is not list or not 1<=len(value['regions'])<=32:raise ValueError('Mark 1..32 real hand regions; never fill hidden anatomy')
    ids=set()
    for r in value['regions']:
        if type(r) is not dict or set(r)!={'id','kind','part','start','end','negative','positive'} or r['kind'] not in KINDS or r['part'] not in PARTS:raise ValueError('Invalid hand/palm/finger/joint support')
        token(r['id'])
        if r['id'] in ids:raise ValueError('Duplicate hand region would repeat strength')
        ids.add(r['id'])
        if (r['kind']=='palm')!=(r['part']=='palm'):raise ValueError('Palm and digit regions must retain their actual anatomical role')
        for k in ('start','end','negative','positive'):point(r[k])
    if type(value['protect']) is not list or len(value['protect'])>32:raise ValueError('Protection rectangle budget exceeded')
    for b in value['protect']:
        if type(b) is not list or len(b)!=4:raise ValueError('Invalid source protection rectangle')
        for x in b:number(x,0,1)
        if b[0]>=b[2] or b[1]>=b[3]:raise ValueError('Protection rectangle must have positive area')
    return deepcopy(value)


def region_geometry(region,frame):
    """Derive only from independently marked visible axis and contour points."""
    w,h=frame['width']-1,frame['height']-1
    def xy(k):return (region[k][0]*w,region[k][1]*h)
    a,b=xy('start'),xy('end');dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
    if length<8:raise ValueError('Visible hand region is too small to review (8 source pixels)')
    u=(dx/length,dy/length);n=(-u[1],u[0]);c=((a[0]+b[0])/2,(a[1]+b[1])/2)
    widths=[]
    for key,sign in (('negative',-1),('positive',1)):
        q=xy(key);v=(q[0]-c[0],q[1]-c[1]);ax=v[0]*u[0]+v[1]*u[1];side=sign*(v[0]*n[0]+v[1]*n[1])
        if abs(ax)>length*.25 or side<2:raise ValueError('Mark both actual opposite contours near the axis midpoint, at least 2 source pixels away')
        widths.append(side)
    if max(widths)>min(widths)*2:raise ValueError('Strong asymmetry needs smaller separate visible regions; do not infer an ideal hand')
    along=length/2;across=max(widths)*1.8
    if not .2<=along/across<=5:raise ValueError('Hand support aspect is outside conservative local policy')
    ex=math.hypot(along*u[0],across*n[0]);ey=math.hypot(along*u[1],across*n[1])
    if c[0]-ex<1 or c[0]+ex>w-1 or c[1]-ey<1 or c[1]+ey>h-1:raise ValueError('Hand transition ellipse reaches a cropped source edge')
    return (*c,*u,along,across)


def validate_support(value,frame):
    value=review(value);frame=source(frame)
    geometries=[region_geometry(r,frame) for r in value['regions']]
    # Conservative preimage envelope covers all preceding same-hand transforms.
    # Protection is refusal, not discontinuous field masking at a painted edge.
    prefix=0.
    for g in geometries:
        cx,cy,ux,uy,a,b=g;radius=max(a,b)+prefix
        for box in value['protect']:
            x0,y0,x1,y1=box[0]*(frame['width']-1),box[1]*(frame['height']-1),box[2]*(frame['width']-1),box[3]*(frame['height']-1)
            if math.hypot(cx-max(x0,min(x1,cx)),cy-max(y0,min(y1,cy)))<=radius:raise ValueError('Hand transition/preimage intersects a protected contact, nail, jewelry or other-hand region')
        prefix+=.12*b
    if prefix>min(128.,min(frame['width'],frame['height'])*.05):raise ValueError('Hand region total displacement exceeds source budget; reduce the reviewed region set')
    return value


def check(value):
    if value is None:return None
    if type(value) is not dict or set(value)!={'version','source','repair_sha256','review','amounts','proposal'} or type(value['version']) is not int or value['version']!=1:raise ValueError('Invalid standalone hand geometry recipe')
    frame=source(value['source']);digest(value['repair_sha256']);r=validate_support(value['review'],frame);amounts(value['amounts'])
    if r['proposal_id'] is None:
        if value['proposal'] is not None:raise ValueError('Manual support cannot claim an automatic model proposal')
    else:
        from .hand_shape_provenance import check_proposal
        proposal=check_proposal(value['proposal'])
        if proposal['proposal_id']!=r['proposal_id'] or proposal['source']!=frame:raise ValueError('Hand proposal belongs to another source or instance')
    for kind,amount in value['amounts'].items():
        if amount!=0 and not any(region['kind']==kind for region in r['regions']):raise ValueError('Active '+kind+' control lacks independently reviewed visible support')
    return deepcopy(value)


def active(value):
    value=check(value)
    return value is not None and any(value['amounts'].values())
