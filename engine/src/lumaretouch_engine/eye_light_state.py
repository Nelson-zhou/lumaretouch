"""Independent per-eye material recipe, never aliases catchlight enhancement."""
import math
OPERATION='lnx.eye_light.v1'
ASSETS=('original-softbox-v1','original-window-v1')
EYE_FIELDS={'asset','strength','horizontal','vertical','rotation','flip'}
def neutral_eye():return dict(asset=ASSETS[0],strength=0.,horizontal=0.,vertical=0.,rotation=0.,flip=False)
def neutral():return {'version':2,'linked':True,'left':neutral_eye(),'right':neutral_eye()}
def check_eye(value):
    if type(value) is not dict or set(value)!=EYE_FIELDS or value['asset'] not in ASSETS or type(value['flip']) is not bool:raise ValueError('眼神光单眼素材字段无效')
    for key in ('strength','horizontal','vertical','rotation'):
        v=value[key];lo=0 if key=='strength' else -100
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=100:raise ValueError('眼神光数值越界')
    return dict(value)
def check(value):
    if value is None:return neutral()
    # Explicit isolated-v1 migration. No source or identity is inferred.
    if type(value) is dict and value.get('version')==1:
        if set(value)!=EYE_FIELDS|{'version','eyes'} or type(value['version']) is not int or value['eyes'] not in ('left','right','both'):raise ValueError('旧眼神光配方无效')
        eye=check_eye({k:value[k] for k in EYE_FIELDS});sides=value['eyes']
        return {'version':2,'linked':sides=='both','left':dict(eye) if sides in ('both','left') else neutral_eye(),'right':dict(eye) if sides in ('both','right') else neutral_eye()}
    if type(value) is not dict or set(value)!={'version','linked','left','right'} or type(value['version']) is not int or value['version']!=2 or type(value['linked']) is not bool:raise ValueError('眼神光配方版本或字段无效')
    left,right=check_eye(value['left']),check_eye(value['right'])
    if value['linked'] and left!=right:raise ValueError('联动眼神光需要两眼参数相同，不能只更新一眼')
    return {'version':2,'linked':value['linked'],'left':left,'right':right}
def active(value):return any(check(value)[side]['strength']>0 for side in ('left','right'))
def preset(value):return check(value)
