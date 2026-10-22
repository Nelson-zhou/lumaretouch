"""Bounded Rust scalar proposals. Pixels and recipes are producer-owned, not IPC input."""
import json
import subprocess
from copy import deepcopy
from .white_balance_math import _helper_path, _number
from .ops import levels as L, curves as C, hsl as H

POLICY='stage-targeted-srgb-v1'
ACTIONS=('levels_black','levels_white','curve','hsl')
CHANNELS=('master','red','green','blue','luminance')

def selection(action,channel):
    if action not in ACTIONS or channel not in CHANNELS or (action!='curve' and channel!='master'):
        raise ValueError('Unknown targeted color action/channel')
    return action,channel


def calculate(rows,action,channel,delta,recipe):
    selection(action,channel)
    delta=_number(delta)
    limit=60 if action=='hsl' else 1 if action=='curve' else 0
    if abs(delta)>limit:raise ValueError('Targeted color drag exceeds its range')
    if not isinstance(rows,(list,tuple)) or not 1<=len(rows)<=121:raise ValueError('Color pick needs 1–121 samples')
    values=[]
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=4:raise ValueError('Color pick requires RGB and coverage')
        values.extend(_number(v) for v in row)
    payload=f'color-action-v1 {action} {channel} {delta!r} {len(rows)} '+' '.join(map(repr,values))
    if action.startswith('levels_'):
        checked=L.check_levels(recipe)
        if not checked['enabled']:raise ValueError('Enable levels before using its eyedropper')
        payload+=' '+' '.join(repr(checked[c][k]) for c in L.CHANNELS for k in L.KEYS)
    elif action=='curve':
        checked=C.check_curves(recipe)
        if not checked['enabled']:raise ValueError('Enable curves before using its eyedropper')
        points=checked.get(channel,[[0.,0.],[1.,1.]])
        payload+=' '+str(len(points))+' '+' '.join(repr(v) for p in points for v in p)
    else:
        checked=H.check_hsl(recipe);payload+=' '+' '.join(map(repr,checked))
    if len(payload.encode('ascii'))>16384:raise ValueError('Color picker request exceeds 16 KiB')
    helper=_helper_path()
    if not helper.is_file():raise RuntimeError('Matching Rust color picker helper missing; rebuild the engine package')
    result=subprocess.run([str(helper)],input=payload,text=True,capture_output=True,timeout=3,check=False)
    if result.returncode:raise ValueError('Rust color picker rejected sample: '+result.stderr[:512])
    if len(result.stdout)>32768:raise ValueError('Oversized Rust color picker result')
    data=json.loads(result.stdout)
    common={'version','policy','action','channel','samples','mean_srgb','hsl'}
    extra={'levels'} if action.startswith('levels_') else {'points','point_index','sample_x','achieved_delta'} if action=='curve' else {'bands','weights','achieved_delta'}
    if type(data) is not dict or set(data)!=common|extra or data['version']!=1 or type(data['version']) is not int or data['policy']!=POLICY or data['action']!=action or data['channel']!=channel or type(data['samples']) is not int or data['samples']!=len(rows):
        raise ValueError('Color picker reply contract mismatch')
    for key in ('mean_srgb','hsl'):
        if type(data[key]) is not list or len(data[key])!=3:raise ValueError('Color picker sample vector mismatch')
        data[key]=[_number(v) for v in data[key]]
    if any(not 0<=v<=1 for v in data['mean_srgb']) or not 0<=data['hsl'][0]<360 or any(not 0<=v<=1 for v in data['hsl'][1:]):raise ValueError('Color picker readout range mismatch')
    if action.startswith('levels_'):
        rows=data.pop('levels')
        if type(rows) is not list or len(rows)!=4 or any(type(r) is not list or len(r)!=5 for r in rows):raise ValueError('Color picker levels shape mismatch')
        next_recipe={**deepcopy(checked),**{c:dict(zip(L.KEYS,r)) for c,r in zip(L.CHANNELS,rows)}}
        next_recipe=L.check_levels(next_recipe)
    elif action=='curve':
        next_recipe=deepcopy(checked)
        if channel=='luminance' and next_recipe['version']==1:
            next_recipe.update(version=2,luminance_space=C.LUMINANCE_SPACE)
        next_recipe[channel]=data.pop('points');next_recipe=C.check_curves(next_recipe)
        if type(data['point_index']) is not int or not 0<=data['point_index']<len(next_recipe[channel]):raise ValueError('Color picker point index mismatch')
        data['point']=next_recipe[channel][data['point_index']]
        if not 0<=_number(data['sample_x'])<=1 or abs(_number(data['achieved_delta']))>1:raise ValueError('Invalid curve pick result')
        # Merely aiming, or dragging against an output limit, must not insert a
        # zero-effect PCHIP control point that changes neighbouring interpolation.
        if data['achieved_delta']==0:next_recipe=deepcopy(checked)
    else:
        next_recipe=list(H.check_hsl(data.pop('bands')))
        if type(data['weights']) is not list or len(data['weights'])!=8 or any(not 0<=_number(w)<=1 for w in data['weights']):raise ValueError('Invalid hue weights')
        if abs(_number(data['achieved_delta']))>120:raise ValueError('Invalid achieved hue delta')
    return next_recipe,data
