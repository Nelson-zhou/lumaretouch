# SPDX-License-Identifier: GPL-3.0-or-later
"""Facial-structure-only, immutable source/face/landmark-owned visible-skin review.

The canonical people support bank owns bytes and the existing graph owns its
pointer. No gloss, finish or makeup consent, source pixels, proxy raster or donor face transfers.
A painted region only vetoes support; measured anatomical zones further restrict it.
"""
from copy import deepcopy
import numpy as np
from . import people_state as S, local_mask_recipe as M
from .people_support_assets import content_digest

KIND = 'facial_sculpt_visibility'


def check_region(region):
    if (type(region) is not dict or set(region) != {'recipe','visible','unoccluded','ownership_confirmed'}
            or any(region[key] is not True for key in ('visible','unoccluded','ownership_confirmed'))):
        raise ValueError('请独立确认面部立体范围为此人物可见、无遮挡的皮肤')
    recipe = M.check_stack(region['recipe'])
    if (not recipe['objects'] or any(item['kind'] != 'brush' or item['operation'] not in ('add','subtract')
                                   for item in recipe['objects'])):
        raise ValueError('面部立体审核只接受当前源图上的归一化手绘皮肤范围')
    if not any(item['enabled'] and item['opacity'] > 0 and item['operation'] == 'add' for item in recipe['objects']):
        raise ValueError('面部立体审核缺少有效手绘可见区域')
    return deepcopy(region)


def check_source(source):
    if (type(source) is not dict or set(source) != {'sha256','width','height'}
            or any(type(source[key]) is not int or not 2 <= source[key] <= 1_000_000 for key in ('width','height'))):
        raise ValueError('面部立体审核源图无效')
    S.digest(source['sha256'])
    return deepcopy(source)


def check_record(record):
    if (type(record) is not dict or set(record) != {'version','face_ref','source','row'}
            or type(record['version']) is not int or record['version'] != 1):
        raise ValueError('面部立体审核资产字段或版本无效')
    ref = S.check_ref(record['face_ref']); source = check_source(record['source']); row = record['row']
    if source['sha256'] != ref['asset_sha256']:
        raise ValueError('面部立体审核不属于此人物的有效来源')
    if type(row) is not dict or set(row) != {'target','landmark_digest','region'} or row['target'] != KIND:
        raise ValueError('面部立体审核不能借用其他功能的可见性同意')
    S.digest(row['landmark_digest']); check_region(row['region'])
    return deepcopy(record)


def retain(state, assets, face_ref, region):
    """Stage only; publication/history/rollback remain with PeopleGraphOwner."""
    out = S.check(state); ref = S.check_ref(face_ref); face = out['faces'].get(ref['face_instance_id'])
    if (face is None or S.face_ref(face) != ref or not face['enabled']
            or face['evidence']['status'] != 'verified' or face['evidence']['backend'] != 'mediapipe'):
        raise ValueError('面部立体审核需要当前已启用的真实分析人物')
    evidence = face['evidence']
    record = check_record({'version':1,'face_ref':ref,
        'source':{'sha256':ref['asset_sha256'],'width':evidence['source_width'],'height':evidence['source_height']},
        'row':{'target':KIND,'landmark_digest':evidence['landmark_digest'],'region':region}})
    digest = content_digest(record); bank = deepcopy(assets)
    if digest in bank and bank[digest] != record:
        raise ValueError('面部立体审核资产摘要冲突')
    bank[digest] = record
    out['faces'][ref['face_instance_id']]['local_assets'][KIND] = {'owner':ref,'content_sha256':digest,'kind':KIND}
    # An explicit re-confirmation is a new graph revision even for identical paint.
    out['revision'] += 1
    return S.check(out), bank


def resolve(state, assets, face_ref):
    ref = S.check_ref(face_ref); face = state['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face) != ref:
        raise ValueError('面部立体审核人物已改变')
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None:
        raise ValueError('请先独立审核此人物的面部立体可见皮肤范围')
    key = descriptor['content_sha256']; record = check_record(assets.get(key)); evidence = face['evidence']
    if (content_digest(record) != key or record['face_ref'] != ref
            or descriptor != {'owner':ref,'content_sha256':key,'kind':KIND}
            or evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe'
            or record['row']['landmark_digest'] != evidence['landmark_digest']
            or (record['source']['width'],record['source']['height']) != (evidence['source_width'],evidence['source_height'])):
        raise ValueError('面部立体审核已过期或源图、人物、关键点不匹配')
    return record, key


def raster(state, assets, face_ref, shape):
    record, _ = resolve(state,assets,face_ref)
    if len(shape) != 2 or any(type(size) is not int or size < 1 for size in shape):
        raise ValueError('面部立体审核栅格尺寸无效')
    # Re-rasterize normalized source vectors at the actual preview/export grid.
    recipe = record['row']['region']['recipe']; M.validate_budget(recipe,shape)
    weight = np.ascontiguousarray(M.raster(recipe,shape),dtype=np.float32)/np.float32(255)
    if not np.any(weight > 0):
        raise ValueError('面部立体审核范围为空，未生成任何装饰')
    weight.setflags(write=False)
    return weight


def validate_project(project):
    assets = project.get('people_support_assets',{})
    def visit(value):
        if isinstance(value,dict):
            if 'face_instance_id' in value and KIND in value.get('local_assets',{}):
                state = S.empty(); state['faces'][value['face_instance_id']] = value
                resolve(S.check(state),assets,S.face_ref(value))
            for child in value.values(): visit(child)
        elif isinstance(value,(list,tuple)):
            for child in value: visit(child)
    visit(project)
