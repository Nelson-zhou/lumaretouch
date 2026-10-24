# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable exact-face makeup and optional paired bare-skin reference vectors.

Reviewed visible makeup is user evidence, never semantic cosmetic detection.
No source pixels are saved. The canonical bank/history owns confirmed records;
this module stages replacements only. Portable presets never carry these bytes.
"""
from copy import deepcopy
import math
from . import people_state as P
from .people_support_assets import content_digest

KIND = 'eye_makeup_enhance_visibility'
MAX_VERTICES = 96
MAX_EXCLUSIONS = 12
FLAGS = ('visible_makeup', 'unoccluded', 'ownership_confirmed', 'globe_lashes_brows_excluded')


def polygon(value):
    if type(value) is not list or not 3 <= len(value) <= MAX_VERTICES:
        raise ValueError('眼妆轮廓需要 3–96 个真实可见源图点')
    points = []
    for point in value:
        if (type(point) is not list or len(point) != 2
                or any(type(v) not in (int, float) or not 0 <= v <= 1 or not math.isfinite(v) for v in point)):
            raise ValueError('眼妆轮廓必须是有限源图归一化坐标')
        points.append(tuple(point))
    if len(set(points)) != len(points):
        raise ValueError('眼妆轮廓不得重复顶点或闭合点')
    area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(points, points[1:]+points[:1]))
    if abs(area) < 1e-10:
        raise ValueError('眼妆轮廓退化')
    # Reject intersections, including touching nonadjacent edges. No ambiguous fill rule.
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a, b, c):
        return abs(cross(a,b,c)) <= 1e-12 and min(a[0],b[0])-1e-12 <= c[0] <= max(a[0],b[0])+1e-12 and min(a[1],b[1])-1e-12 <= c[1] <= max(a[1],b[1])+1e-12
    edges = list(zip(points, points[1:]+points[:1]))
    for i, (a,b) in enumerate(edges):
        for j, (c,d) in enumerate(edges):
            if j <= i or j == i+1 or (i == 0 and j == len(edges)-1):
                continue
            if (cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0) or any((on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b))):
                raise ValueError('眼妆轮廓不能自交或自接触')
    return deepcopy(value)


def check_eyes(eyes):
    if type(eyes) is not dict or not eyes or set(eyes) - {'left', 'right'}:
        raise ValueError('须独立审核至少一侧可见眼妆')
    for eye in eyes.values():
        if (type(eye) is not dict or set(eye) != {'makeup','exclusions','reference_a','reference_b','reference_confirmed',*FLAGS}
                or any(eye[key] is not True for key in FLAGS)
                or type(eye['reference_confirmed']) is not bool):
            raise ValueError('必须确认已有眼妆、无遮挡、人物归属及眼球睫毛眉毛已排除')
        polygon(eye['makeup'])
        if type(eye['exclusions']) is not list or len(eye['exclusions']) > MAX_EXCLUSIONS:
            raise ValueError('眼妆排除区数量无效')
        for exclusion in eye['exclusions']:
            polygon(exclusion)
        a, b = eye['reference_a'], eye['reference_b']
        if (a is None) != (b is None):
            raise ValueError('原有妆效增强或减淡需要两块独立干净邻接皮肤参考')
        if a is None:
            if eye['reference_confirmed']:
                raise ValueError('没有实测皮肤参考不能声明已确认')
        else:
            polygon(a); polygon(b)
            if eye['reference_confirmed'] is not True:
                raise ValueError('须确认两块参考确为此眼附近无妆、无高光阴影及无遮挡的可见皮肤')
    return deepcopy(eyes)


def check_record(record):
    if (type(record) is not dict or set(record) != {'version','face_ref','source','row'}
            or type(record['version']) is not int or record['version'] != 1):
        raise ValueError('眼妆增强审核资产版本或字段无效')
    ref = P.check_ref(record['face_ref']); source = record['source']; row = record['row']
    if (type(source) is not dict or set(source) != {'sha256','width','height'}
            or source['sha256'] != ref['asset_sha256']
            or any(type(source[k]) is not int or not 2 <= source[k] <= 1_000_000 for k in ('width','height'))):
        raise ValueError('眼妆增强审核有效来源不匹配')
    if type(row) is not dict or set(row) != {'target','landmark_digest','eyes'} or row['target'] != KIND:
        raise ValueError('眼妆增强不能借用其他眼部功能的审核')
    P.digest(row['landmark_digest']); check_eyes(row['eyes'])
    return deepcopy(record)


def retain(state, assets, face_ref, eyes):
    """Stage a full replacement, preserving unreviewed opposite-side old records.

    The caller must authenticate live document/source/request fences before this
    call and atomically commit returned graph + bank via the existing owner.
    """
    out = P.check(state); ref = P.check_ref(face_ref); face = out['faces'].get(ref['face_instance_id'])
    if (face is None or P.face_ref(face) != ref or not face['enabled']
            or face['evidence']['status'] != 'verified' or face['evidence']['backend'] != 'mediapipe'):
        raise ValueError('眼妆审核需要当前已启用、真实分析的人物')
    eyes = check_eyes(eyes)
    if KIND in face['local_assets']:
        old, _ = resolve(out, assets, ref)
        eyes = {**old['row']['eyes'], **eyes}
    evidence = face['evidence']
    record = check_record({'version':1, 'face_ref':ref,
        'source':{'sha256':ref['asset_sha256'],'width':evidence['source_width'],'height':evidence['source_height']},
        'row':{'target':KIND,'landmark_digest':evidence['landmark_digest'],'eyes':eyes}})
    key = content_digest(record); bank = deepcopy(assets)
    if key in bank and bank[key] != record:
        raise ValueError('眼妆审核资产摘要冲突')
    bank[key] = record
    face['local_assets'][KIND] = {'owner':ref,'content_sha256':key,'kind':KIND}
    out['revision'] += 1
    return P.check(out), bank


def resolve(state, assets, face_ref):
    ref = P.check_ref(face_ref); face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref:
        raise ValueError('眼妆审核人物已经改变')
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None:
        raise ValueError('请先独立描绘并确认当前人物的可见原有眼妆')
    key = descriptor['content_sha256']; record = check_record(assets.get(key)); evidence = face['evidence']
    if (content_digest(record) != key or record['face_ref'] != ref
            or descriptor != {'owner':ref,'content_sha256':key,'kind':KIND}
            or evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe'
            or record['row']['landmark_digest'] != evidence['landmark_digest']
            or (record['source']['width'],record['source']['height']) != (evidence['source_width'],evidence['source_height'])):
        raise ValueError('眼妆审核来源、人物或关键点已过期')
    return record, key


def validate_project(project):
    assets = project.get('people_support_assets', {})
    def visit(value):
        if isinstance(value, dict):
            if 'face_instance_id' in value and KIND in value.get('local_assets', {}):
                state = P.empty(); state['faces'][value['face_instance_id']] = value
                resolve(P.check(state), assets, P.face_ref(value))
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
    visit(project)


def check_source(source):
    if (type(source) is not dict or set(source) != {'sha256','width','height'}
            or any(type(source[k]) is not int or not 2 <= source[k] <= 1_000_000 for k in ('width','height'))):
        raise ValueError('眼妆有效来源字段或尺寸无效')
    P.digest(source['sha256'])
    return deepcopy(source)
