"""Explicit manual-only portability; never copy camera identity, guides or a solve."""
from . import optics_state as S
OP='lnx.optics_manual.v1'
FIELDS=('_optics',)
LENS=('distortion','vignette','midpoint','crop_lock')
PERSPECTIVE=(*S.MANUAL,'crop_lock','show_guides')


def check_params(raw):
    if type(raw) is not dict or set(raw)!={'recipe'}:raise ValueError('镜头/透视预设只接受手动参数配方')
    packet=raw['recipe']
    if type(packet) is not dict or set(packet)!={'version','lens','perspective'} or type(packet['version']) is not int or packet['version']!=1:raise ValueError('镜头/透视手动预设版本无效')
    if type(packet['lens']) is not dict or set(packet['lens'])!=set(LENS) or type(packet['perspective']) is not dict or set(packet['perspective'])!=set(PERSPECTIVE):raise ValueError('预设不能复制镜头身份、自动解算或引导线')
    value=S.empty();value['lens'].update(packet['lens']);value['perspective'].update(packet['perspective']);value=S.check(value)
    return {'recipe':{'version':1,'lens':{k:value['lens'][k] for k in LENS},'perspective':{k:value['perspective'][k] for k in PERSPECTIVE}}}


def params_of(state):
    value=S.check(state.get('_optics'))
    return check_params({'recipe':{'version':1,'lens':{k:value['lens'][k] for k in LENS},'perspective':{k:value['perspective'][k] for k in PERSPECTIVE}}})


def install(state,params):
    packet=check_params(params)['recipe'];target=S.check(state.get('_optics'))
    # A solve was measured after lens distortion. Never reinterpret its evidence.
    if target['perspective']['mode']!='off' and target['lens']['distortion']!=packet['lens']['distortion']:
        raise ValueError('目标有自动/引导透视；先关闭或重新分析，再同步不同的镜头畸变')
    target['lens'].update(packet['lens']);target['perspective'].update(packet['perspective']);state['_optics']=S.check(target)
