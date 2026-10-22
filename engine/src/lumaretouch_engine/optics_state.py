"""PC-32455 retained optical intent, independent of legacy crop/rotation.

This version explicitly runs after final manual liquify and before crop. Old
projects receive an exact neutral stage; no historical operator is reordered.
"""
from copy import deepcopy
import math
import re

VERSION = 1
DOMAIN = 'post-manual-liquify-pre-crop-normalized'
IDENTITY = [1., 0., 0., 0., 1., 0., 0., 0., 1.]
MANUAL = {'vertical': 0., 'horizontal': 0., 'rotation': 0., 'aspect': 0.,
          'scale': 100., 'offset_x': 0., 'offset_y': 0.}


def empty():
    return {'version': VERSION, 'domain': DOMAIN, 'source': None,
            'lens': {'enabled': False, 'profile': None, 'distortion': 0.,
                     'vignette': 0., 'midpoint': 50., 'crop_lock': True},
            'perspective': {'mode': 'off', 'matrix': IDENTITY.copy(), 'guides': [],
                            'analysis': None, **MANUAL, 'show_guides': False, 'crop_lock': True}}


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'镜头/透视数值必须在 [{low}, {high}] 内且有限')
    return float(value)


def text(value, *, empty=False):
    if type(value) is not str or len(value) > 512 or (not empty and not value) or '\0' in value:
        raise ValueError('镜头/透视身份字段无效')
    return value


def binding(value):
    if value is None: return None
    if type(value) is not dict or set(value) != {'sha256', 'width', 'height'}:
        raise ValueError('镜头/透视源图身份无效')
    if type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ValueError('镜头/透视源图摘要无效')
    for key in ('width', 'height'):
        if type(value[key]) is not int or not 1 <= value[key] <= 65536: raise ValueError('源图尺寸无效')
    return deepcopy(value)


def profile(value):
    if value is None: return None
    fields = {'camera_maker', 'camera_model', 'camera_variant', 'lens_maker', 'lens_model',
              'crop', 'focal', 'aperture', 'distance', 'database_sha256', 'library_version', 'orientation', 'flags'}
    if type(value) is not dict or set(value) != fields: raise ValueError('Lensfun 配置记录不兼容')
    out = {key: text(value[key], empty=key == 'camera_variant') for key in
           ('camera_maker', 'camera_model', 'camera_variant', 'lens_maker', 'lens_model', 'library_version')}
    digest = value['database_sha256']
    if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}', digest): raise ValueError('镜头数据库摘要无效')
    out['database_sha256'] = digest
    for key, lo, hi in (('crop', .1, 100), ('focal', .1, 10000), ('aperture', .1, 128), ('distance', .01, 100000)):
        out[key] = None if value[key] is None and key in ('aperture','distance') else number(value[key], lo, hi)
    if type(value['flags']) is not list or not value['flags'] or any(x not in ('distortion', 'tca', 'vignette') for x in value['flags']) or len(set(value['flags'])) != len(value['flags']):
        raise ValueError('镜头校正必须记录实际存在的标定分支')
    if 'vignette' in value['flags'] and (out['aperture'] is None or out['distance'] is None): raise ValueError('暗角标定必须有真实光圈及对焦距离')
    if type(value['orientation']) is not int or value['orientation'] not in range(1,9): raise ValueError('镜头标定方向无效')
    out['orientation'] = value['orientation']
    out['flags'] = list(value['flags'])
    return out


def guide(value):
    if type(value) is not dict or set(value) != {'id', 'axis', 'start', 'end'}: raise ValueError('透视引导线字段无效')
    if value['axis'] not in ('horizontal', 'vertical'): raise ValueError('引导线方向无效')
    ident = text(value['id'])
    if not re.fullmatch('[A-Za-z0-9_-]{1,64}', ident): raise ValueError('引导线身份无效')
    points = []
    for key in ('start', 'end'):
        p = value[key]
        if type(p) is not list or len(p) != 2: raise ValueError('引导线端点无效')
        points.append([number(x, 0, 1) for x in p])
    if math.dist(*points) < .02: raise ValueError('引导线过短，请沿真实直边绘制')
    return {'id': ident, 'axis': value['axis'], 'start': points[0], 'end': points[1]}


def check(value):
    if value is None: return empty()
    if type(value) is not dict or set(value) != {'version', 'domain', 'source', 'lens', 'perspective'} or type(value['version']) is not int or value['version'] != VERSION or value['domain'] != DOMAIN:
        raise ValueError('镜头/透视配方版本或顺序不兼容')
    out = empty(); out['source'] = binding(value['source'])
    lens, persp = value['lens'], value['perspective']
    if type(lens) is not dict or set(lens) != set(out['lens']) or type(persp) is not dict or set(persp) != set(out['perspective']):
        raise ValueError('镜头/透视配方字段不兼容')
    for owner, source in ((out['lens'], lens), (out['perspective'], persp)):
        for key in ('crop_lock',):
            if type(source[key]) is not bool: raise ValueError('锁定裁剪必须是布尔值')
            owner[key] = source[key]
    if type(lens['enabled']) is not bool or type(persp['show_guides']) is not bool: raise ValueError('镜头/辅助线开关无效')
    out['lens'].update(enabled=lens['enabled'], profile=profile(lens['profile']),
                       distortion=number(lens['distortion'], -100, 100), vignette=number(lens['vignette'], -100, 100), midpoint=number(lens['midpoint'], 0, 100))
    if lens['enabled'] and out['lens']['profile'] is None: raise ValueError('没有有效镜头配置，不能宣称已启用自动矫正；请使用手动调整')
    p = out['perspective']; p['show_guides'] = persp['show_guides']
    for key in MANUAL: p[key] = number(persp[key], 25 if key == 'scale' else -45 if key == 'rotation' else -100, 400 if key == 'scale' else 45 if key == 'rotation' else 100)
    if persp['mode'] not in ('off', 'smart', 'horizontal', 'vertical', 'guided'): raise ValueError('透视模式无效')
    p['mode'] = persp['mode']
    if type(persp['matrix']) is not list or len(persp['matrix']) != 9: raise ValueError('透视矩阵无效')
    p['matrix'] = [number(v, -100, 100) for v in persp['matrix']]
    if abs(p['matrix'][8]-1) > 1e-12: raise ValueError('透视矩阵必须以右下角 1 归一化')
    if type(persp['guides']) is not list or len(persp['guides']) > 4: raise ValueError('最多 4 条透视引导线')
    p['guides'] = [guide(g) for g in persp['guides']]
    if len({g['id'] for g in p['guides']}) != len(p['guides']): raise ValueError('引导线身份重复')
    if p['mode'] == 'off' and p['matrix'] != IDENTITY: raise ValueError('关闭自动/引导透视后不能保留隐藏矩阵')
    if p['mode'] == 'guided' and len(p['guides']) < 2 and p['matrix'] != IDENTITY: raise ValueError('第 2 条引导线完成前不能保留解算结果')
    analysis = persp['analysis']
    if analysis is not None:
        if type(analysis) is not dict or set(analysis) != {'method', 'confidence', 'lines', 'residual_degrees', 'message'}: raise ValueError('透视分析报告无效')
        p['analysis'] = {'method': text(analysis['method']), 'confidence': number(analysis['confidence'], 0, 1),
                         'lines': int(number(analysis['lines'], 0, 512)), 'residual_degrees': number(analysis['residual_degrees'], 0, 90), 'message': text(analysis['message'], empty=True)}
    if source_bound(out) and out['source'] is None: raise ValueError('镜头配置与自动/引导透视必须绑定本张照片')
    return deepcopy(out)


def source_bound(value):
    return value['lens']['profile'] is not None or value['perspective']['mode'] != 'off' or bool(value['perspective']['guides'])


def active(value):
    v = check(value); l, p = v['lens'], v['perspective']
    return bool(l['enabled'] or l['distortion'] or l['vignette'] or p['matrix'] != IDENTITY or any(p[k] != d for k, d in MANUAL.items()))


def portable(value):
    """Only manual numbers transfer. Auto modes are requests to reanalyse each target."""
    v = check(value); out = empty()
    for key in ('distortion', 'vignette', 'midpoint', 'crop_lock'): out['lens'][key] = v['lens'][key]
    for key in (*MANUAL, 'crop_lock', 'show_guides'): out['perspective'][key] = v['perspective'][key]
    return {'version': 1, 'manual': out, 'auto_mode': v['perspective']['mode'] if v['perspective']['mode'] in ('smart', 'horizontal', 'vertical') else 'off',
            'lens_auto': v['lens']['enabled'], 'excluded': ['profile identity', 'guide geometry', 'solved matrix']}


def migrate_legacy_states(value, *, root=False):
    if isinstance(value, dict):
        for child in list(value.values()): migrate_legacy_states(child)
        if root or any(k in value for k in ('_strength', '_grade', '_manual_liquify')): value.setdefault('_optics', empty())
    elif isinstance(value, list):
        for child in value: migrate_legacy_states(child)
