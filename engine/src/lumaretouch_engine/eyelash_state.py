"""Only portable intent lives in the canonical people graph."""
import math
from .blush_makeup_state import colour,rgb,check_palette,save_colour,remove_colour
OP=OPERATION='lnx.eyelash.v1'
PATTERNS=('airy', 'natural', 'long', 'dense', 'curl', 'outer', 'round', 'wispy', 'fan', 'petal', 'silk', 'defined', 'soft', 'dramatic')
PARTS=('left_upper','left_lower','right_upper','right_lower')
KEYS=('link_lr','link_ud',*PARTS)
def neutral_eye():return {'pattern':'airy','strength':0.,'colour':'#28232A'}
def neutral():return {'version':1,'link_lr':True,'link_ud':True,**{p:neutral_eye() for p in PARTS}}
def check_eye(v):
    if type(v) is not dict or set(v)!={'pattern','strength','colour'} or type(v['pattern']) is not str or v['pattern'] not in PATTERNS:raise ValueError('睫毛单眼配方无效')
    if type(v['strength']) not in (int,float) or not math.isfinite(v['strength']) or not 0<=v['strength']<=1:raise ValueError('睫毛程度需为 0–1 有限数值')
    return {'pattern':v['pattern'],'strength':float(v['strength']),'colour':colour(v['colour'])}
def check(v):
    if v is None:return neutral()
    if type(v) is not dict or set(v)!={'version',*KEYS} or type(v['version']) is not int or v['version']!=1 or any(type(v[k]) is not bool for k in ('link_lr','link_ud')):raise ValueError('睫毛配方版本或字段无效')
    out={'version':1,'link_lr':v['link_lr'],'link_ud':v['link_ud'],**{p:check_eye(v[p]) for p in PARTS}}
    for p in PARTS:
        side,lid=p.split('_')
        if out['link_lr'] and out[p]!=out[('right' if side=='left' else 'left')+'_'+lid]:raise ValueError('左右联动必须原子更新两侧')
        if out['link_ud'] and out[p]!=out[side+'_'+('lower' if lid=='upper' else 'upper')]:raise ValueError('上下联动必须原子更新上下睫毛')
    return out
def active(v):return any(check(v)[s]['strength']>0 for s in PARTS)
def preset(v):return check(v)
def edit(v,part,eye):
    r=check(v)
    if part not in PARTS:raise ValueError('未知睫毛部位')
    eye=check_eye(eye);side,lid=part.split('_')
    for p in PARTS:
        s,l=p.split('_')
        if (s==side or r['link_lr']) and (l==lid or r['link_ud']):r[p]=dict(eye)
    return check(r)
def patches(v):
    r=check(v)
    return [{'operation_id':OP,'parameter_path':'/'+k,'unset':False,'value':r[k]} for k in ('link_lr','link_ud')]+[{'operation_id':OP,'parameter_path':'/'+s+'/'+k,'unset':False,'value':r[s][k]} for s in PARTS for k in ('pattern','strength','colour')]
def validate_graph(state):
    from . import people_state as P
    from .people_algorithms import defaults
    from .people_resolver import resolve,materialize
    out=P.check(state)
    allowed={p['parameter_path'] for p in patches(neutral())}
    for row in out['overrides']:
        if row['operation_id']!=OP:continue
        path=row['parameter_path']
        if path not in allowed:raise ValueError('未知睫毛参数路径')
        if path in ('/link_lr','/link_ud'):
            if type(row['value']) is not bool:raise ValueError('睫毛联动必须为布尔值')
        else:
            _,side,key=path.split('/')
            check_eye({**neutral_eye(),key:row['value']})
    for face in out['faces']:
        resolved=resolve(out,face,defaults())
        if not any(c['operation_id']==OP for c in resolved['conflicts']):
            materialize({**resolved,'conflicts':[]},OP,neutral(),check)
    return out
