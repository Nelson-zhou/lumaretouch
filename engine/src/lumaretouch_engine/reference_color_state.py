"""Strict separate late-colour recipe; never overwrites manual WB/exposure edits."""
from copy import deepcopy
import math
import re
ALGORITHM='matched-patch-linear-rgb-v1'
DOMAIN='working-srgb-encoded-late-color-v1'
OP='lnx.reference_color.v1'
KEY='_reference_color'


def number(value,lo,hi):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError('参考色彩数值无效')
    return float(value)


def digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value): raise ValueError('参考色彩摘要无效')
    return value


def binding(value):
    if type(value) is not dict or set(value)!={'sha256','width','height'}:
        raise ValueError('参考色彩源图身份不完整')
    digest(value['sha256'])
    if any(type(value[k]) is not int or not 1<=value[k]<=100000 for k in ('width','height')):
        raise ValueError('参考色彩源图尺寸无效')
    return deepcopy(value)


def empty():
    return {'version':1,'algorithm':ALGORITHM,'domain':DOMAIN,'strength':0.,
            'log2_gains':[0.,0.,0.],'source':None,'reference':None}


def check(value):
    if value is None: return empty()
    if type(value) is not dict or set(value)!=set(empty()): raise ValueError('参考色彩配方字段无效')
    if type(value['version']) is not int or value['version']!=1 or value['algorithm']!=ALGORITHM or value['domain']!=DOMAIN:
        raise ValueError('参考色彩配方版本/色域无效')
    out=deepcopy(value);out['strength']=number(value['strength'],0,1)
    gains=value['log2_gains']
    if type(gains) is not list or len(gains)!=3: raise ValueError('参考色彩需三个通道增益')
    out['log2_gains']=[number(v,-2,2) for v in gains]
    if value['source'] is not None: out['source']=binding(value['source'])
    ref=value['reference']
    if ref is not None:
        if type(ref) is not dict or set(ref)!={'source','render_sha256','asset_id'}:
            raise ValueError('参考色彩样片身份无效')
        binding(ref['source']);digest(ref['render_sha256']);digest(ref['asset_id'])
    if out['strength'] and (out['source'] is None or ref is None): raise ValueError('活动参考色彩缺少双图身份')
    return out


def active(value):
    p=check(value)
    return p['strength']!=0 and any(v!=0 for v in p['log2_gains'])


def install(state,recipe):
    # New object, only this feature's key. No manual WB/EV/curve state replacement.
    return {**state,KEY:check(recipe)}


def portable(value):
    p=check(value)
    if p["strength"]==0: return {'version':1,'strength':0.,'reference':None}
    # Crucially no fitted target gains/source/geometry in a batch/preset intent.
    return {'version':1,'strength':p['strength'],'reference':deepcopy(p['reference'])}
