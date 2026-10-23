"""Only portable intent lives in the canonical people graph."""
import math
from .blush_makeup_state import colour,rgb,check_palette,save_colour,remove_colour
OP=OPERATION='lnx.eyeliner.v1'
PATTERNS=('fine','outer','arch','taper','bold','split')
KEYS=('linked','left','right')
def neutral_eye():return {'pattern':'fine','strength':0.,'colour':'#28232A'}
def neutral():return {'version':1,'linked':True,'left':neutral_eye(),'right':neutral_eye()}
def check_eye(v):
    if type(v) is not dict or set(v)!={'pattern','strength','colour'} or type(v['pattern']) is not str or v['pattern'] not in PATTERNS:raise ValueError('眼线单眼配方无效')
    if type(v['strength']) not in (int,float) or not math.isfinite(v['strength']) or not 0<=v['strength']<=1:raise ValueError('眼线程度需为 0–1 有限数值')
    return {'pattern':v['pattern'],'strength':float(v['strength']),'colour':colour(v['colour'])}
def check(v):
    if v is None:return neutral()
    if type(v) is not dict or set(v)!={'version',*KEYS} or type(v['version']) is not int or v['version']!=1 or type(v['linked']) is not bool:raise ValueError('眼线配方版本或字段无效')
    left,right=check_eye(v['left']),check_eye(v['right'])
    if v['linked'] and left!=right:raise ValueError('联动眼线必须一次提交两眼相同参数；不支持的眼需先解除联动并归零')
    return {'version':1,'linked':v['linked'],'left':left,'right':right}
def active(v):return any(check(v)[s]['strength']>0 for s in ('left','right'))
def preset(v):return check(v)
def patches(v):
    r=check(v)
    return [{'operation_id':OP,'parameter_path':'/linked','unset':False,'value':r['linked']}]+[{'operation_id':OP,'parameter_path':'/'+s+'/'+k,'unset':False,'value':r[s][k]} for s in ('left','right') for k in ('pattern','strength','colour')]
def validate_graph(state):
    from . import people_state as P
    from .people_algorithms import defaults
    from .people_resolver import resolve,materialize
    out=P.check(state)
    allowed={p['parameter_path'] for p in patches(neutral())}
    for row in out['overrides']:
        if row['operation_id']!=OP:continue
        path=row['parameter_path']
        if path not in allowed:raise ValueError('未知眼线参数路径')
        if path=='/linked':
            if type(row['value']) is not bool:raise ValueError('眼线联动必须为布尔值')
        else:
            _,side,key=path.split('/')
            check_eye({**neutral_eye(),key:row['value']})
    for face in out['faces']:
        resolved=resolve(out,face,defaults())
        if not any(c['operation_id']==OP for c in resolved['conflicts']):
            materialize({**resolved,'conflicts':[]},OP,neutral(),check)
    return out
