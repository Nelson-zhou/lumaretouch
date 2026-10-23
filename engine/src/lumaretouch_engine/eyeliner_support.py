"""Delegation hooks for canonical people_support_assets, never another store owner.

Caller passes the SAME project-level asset dictionary and stages returned graph
through PeopleGraphOwner / the existing transaction and history owner.
"""
from copy import deepcopy
import numpy as np
from . import people_state as S, local_mask_recipe as M
from .people_support_assets import content_digest
KIND='eyeliner_visibility'
def check_record(record):
    if type(record) is not dict or set(record)!={'version','face_ref','source','row'} or type(record['version']) is not int or record['version']!=1: raise ValueError('眼线审核资产无效')
    ref=S.check_ref(record['face_ref']); source=record['source']; row=record['row']
    if type(source) is not dict or set(source)!={'sha256','width','height'} or source['sha256']!=ref['asset_sha256'] or any(type(source[k]) is not int or source[k]<=0 for k in ('width','height')): raise ValueError('审核源图无效')
    if type(row) is not dict or set(row)!={'target','landmark_digest','eyes'} or row['target']!=KIND: raise ValueError('审核目标无效')
    S.digest(row['landmark_digest'])
    if type(row['eyes']) is not dict or not row['eyes'] or set(row['eyes'])-{'left','right'}: raise ValueError('审核眼侧无效')
    for eye in row['eyes'].values():
        if type(eye) is not dict or set(eye)!={'recipe','visible','unoccluded','ownership_confirmed','open_eye'} or any(eye[k] is not True for k in ('visible','unoccluded','ownership_confirmed','open_eye')): raise ValueError('须确认眼睑可见、无遮挡且属于此人物')
        recipe=M.check_stack(eye['recipe'])
        if not recipe['objects'] or any(o['kind']!='brush' or o['operation'] not in ('add','subtract') for o in recipe['objects']): raise ValueError('审核只接受原图手绘可见眼睑范围')
        if not any(o['enabled'] and o['opacity']>0 and o['operation']=='add' for o in recipe['objects']): raise ValueError('审核缺少有效可见区域')
    return deepcopy(record)

def retain(state,assets,face_ref,eyes):
    """Stage candidate only. The host commits via its existing receipt owner."""
    out=S.check(state); ref=S.check_ref(face_ref); face=out['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face)!=ref or face['evidence']['status']!='verified' or face['evidence']['backend']!='mediapipe': raise ValueError('需要当前真实人物')
    if KIND in face['local_assets']:
        previous,_=resolve(out,assets,ref)
        eyes={**previous['row']['eyes'],**eyes}
    e=face['evidence']; source={'sha256':ref['asset_sha256'],'width':e['source_width'],'height':e['source_height']}
    record=check_record({'version':1,'face_ref':ref,'source':source,'row':{'target':KIND,'landmark_digest':e['landmark_digest'],'eyes':eyes}})
    digest=content_digest(record); bank=deepcopy(assets)
    if digest in bank and bank[digest]!=record: raise ValueError('审核资产摘要冲突')
    bank[digest]=record; out['faces'][ref['face_instance_id']]['local_assets'][KIND]={'owner':ref,'content_sha256':digest,'kind':KIND};out['revision']+=1
    return S.check(out),bank

def resolve(state,assets,face_ref):
    ref=S.check_ref(face_ref);face=state['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face)!=ref: raise ValueError('审核人物已改变')
    descriptor=face['local_assets'].get(KIND)
    if descriptor is None: raise ValueError('请先审核此人物可见眼睑')
    key=descriptor['content_sha256'];record=check_record(assets.get(key))
    e=face['evidence']
    if content_digest(record)!=key or record['face_ref']!=ref or descriptor!={'owner':ref,'content_sha256':key,'kind':KIND} or e['status']!='verified' or record['row']['landmark_digest']!=e['landmark_digest'] or (record['source']['width'],record['source']['height'])!=(e['source_width'],e['source_height']): raise ValueError('审核已过期或来源不匹配')
    return record,key

def raster(state,assets,face_ref,shape,binding):
    record,key=resolve(state,assets,face_ref)
    if len(shape)!=2 or any(type(n) is not int or n<1 for n in shape): raise ValueError('眼部审核栅格尺寸无效')
    # Rebuild normalized source vectors at the requested preview/export size;
    # never resize a proxy raster. Record ownership retains original dimensions.
    result={}
    for side,eye in record['row']['eyes'].items():
        weight=M.raster(eye['recipe'],shape)
        result[side]={**binding,'side':side,'review_id':key,'reviewed':True,'occluded':False,'mask':np.ascontiguousarray(weight,dtype=np.float32)/np.float32(255)}
    return result

def validate_project(project):
    """Resolve active and historical descriptors using the one project bank."""
    assets=project.get('people_support_assets',{})
    def visit(value):
        if isinstance(value,dict):
            if 'face_instance_id' in value and KIND in value.get('local_assets',{}):
                state=S.empty();state['faces'][value['face_instance_id']]=value
                resolve(S.check(state),assets,S.face_ref(value))
            for child in value.values():visit(child)
        elif isinstance(value,(list,tuple)):
            for child in value:visit(child)
    visit(project)
