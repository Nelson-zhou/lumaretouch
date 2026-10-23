# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent reviewed visible iris + measured pupil + highlight source vectors.

Not eye-light visibility, not generated pupil circles. The canonical immutable
people support bank owns these records and existing history owns descriptors.
"""
import math
from copy import deepcopy
from . import people_state as S
from .people_support_assets import content_digest
KIND='iris_makeup_visibility'
FIELDS=('iris','pupil','highlights')
def polygon(value):
    if type(value) is not list or not 3<=len(value)<=128:raise ValueError('轮廓需 3–128 个实测原图点')
    for p in value:
        if type(p) is not list or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in p):raise ValueError('轮廓必须使用源图归一化坐标')
    return deepcopy(value)
def check_record(record):
    if type(record) is not dict or set(record)!={'version','face_ref','source','row'} or type(record['version']) is not int or record['version']!=1:raise ValueError('美瞳审核资产无效')
    ref=S.check_ref(record['face_ref']);source=record['source'];row=record['row']
    if type(source) is not dict or set(source)!={'sha256','width','height'} or source['sha256']!=ref['asset_sha256'] or any(type(source[k]) is not int or not 1<=source[k]<=1000000 for k in ('width','height')):raise ValueError('美瞳源图无效')
    if type(row) is not dict or set(row)!={'target','landmark_digest','eyes'} or row['target']!=KIND:raise ValueError('美瞳审核目标无效')
    S.digest(row['landmark_digest'])
    if type(row['eyes']) is not dict or set(row['eyes'])!={'left','right'}:raise ValueError('需要两侧独立虹膜审核')
    for eye in row['eyes'].values():
        if type(eye) is not dict or set(eye)!={*FIELDS,'confirmed'} or eye['confirmed'] is not True:raise ValueError('须确认清晰可见、无遮挡、瞳孔完整且高光已排除')
        polygon(eye['iris']);polygon(eye['pupil'])
        if type(eye['highlights']) is not list or len(eye['highlights'])>16:raise ValueError('高光轮廓无效')
        for p in eye['highlights']:polygon(p)
    return deepcopy(record)
def retain(state,assets,face_ref,eyes):
    out=S.check(state);ref=S.check_ref(face_ref);face=out['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face)!=ref or face['evidence']['status']!='verified' or face['evidence']['backend']!='mediapipe':raise ValueError('需要当前真实人物分析')
    e=face['evidence'];source={'sha256':ref['asset_sha256'],'width':e['source_width'],'height':e['source_height']}
    record=check_record({'version':1,'face_ref':ref,'source':source,'row':{'target':KIND,'landmark_digest':e['landmark_digest'],'eyes':eyes}})
    key=content_digest(record);bank=deepcopy(assets)
    if key in bank and bank[key]!=record:raise ValueError('审核摘要冲突')
    bank[key]=record;face['local_assets'][KIND]={'owner':ref,'content_sha256':key,'kind':KIND};out['revision']+=1
    return S.check(out),bank

def resolve(state,assets,face_ref):
    ref=S.check_ref(face_ref);face=state['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face)!=ref:raise ValueError('美瞳审核人物已改变')
    d=face['local_assets'].get(KIND)
    if d is None:raise ValueError('请先独立审核可见虹膜、瞳孔及高光')
    key=d['content_sha256'];r=check_record(assets.get(key));e=face['evidence']
    if content_digest(r)!=key or r['face_ref']!=ref or d!={'owner':ref,'content_sha256':key,'kind':KIND} or e['status']!='verified' or e['backend']!='mediapipe' or r['row']['landmark_digest']!=e['landmark_digest'] or (r['source']['width'],r['source']['height'])!=(e['source_width'],e['source_height']):raise ValueError('美瞳审核已过期')
    return r,key

def validate_project(project):
    assets=project.get('people_support_assets',{})
    def visit(v):
        if isinstance(v,dict):
            if 'face_instance_id' in v and KIND in v.get('local_assets',{}):
                state=S.empty();state['faces'][v['face_instance_id']]=v;resolve(S.check(state),assets,S.face_ref(v))
            for c in v.values():visit(c)
        elif isinstance(v,(list,tuple)):
            for c in v:visit(c)
    visit(project)
