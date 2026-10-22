"""Portable PC-32466 mouth2D intent; only gummy has official bilateral unlock.

Signs and limits are explicit product policy; no mesh, mask, or identity travels
in a preset. Positive vertical moves DOWN (opposite nose/eye position).
"""
import math
VERSION = 1
KEYS = ('size', 'width', 'vertical', 'horizontal', 'gummy', 'm_lip', 'tilt', 'upper', 'lower')
SCALARS = tuple(k for k in KEYS if k != 'gummy')
SIDES = ('left', 'right')
CONTROL_IDS = dict(zip(('family', *KEYS), ('PC-32466-C-cbb4c198e8',
    'PC-32466-C-c6608e6df0', 'PC-32466-C-25a12375ad', 'PC-32466-C-d9f05e02e0',
    'PC-32466-C-76ebd0c9bb', 'PC-32466-C-eb54b58b96', 'PC-32466-C-64e1410070',
    'PC-32466-C-120b651906', 'PC-32466-C-71447c0f00', 'PC-32466-C-5fd3068bc8')))


def neutral():
    return {'version': VERSION, **dict.fromkeys(SCALARS, 0.),
            'gummy': {'linked': True, 'left': 0., 'right': 0.}}


def amount(value, low=-1.):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= 1:
        raise ValueError(f'嘴形数值必须在 [{low},1] 内且有限')
    return float(value)


def check(value):
    if value is None: return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('嘴形配方仅接受版本和九项参数，不能携带人脸、蒙版或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此嘴形配方版本')
    gummy = value['gummy']
    if type(gummy) is not dict or set(gummy) != {'linked', *SIDES} or type(gummy['linked']) is not bool:
        raise ValueError('露龈调整需要明确联动状态及人物左/右值')
    return {'version': VERSION, **{k: amount(value[k]) for k in SCALARS},
            'gummy': {'linked': gummy['linked'], **{s: amount(gummy[s], 0.) for s in SIDES}}}


def active(value):
    r = check(value)
    return any(r[k] != 0 for k in SCALARS) or any(r['gummy'][s] != 0 for s in SIDES)


def adjust(value, key, value_amount, side=None):
    r = check(value)
    if key not in KEYS: raise ValueError('未知嘴形控件')
    if key == 'gummy':
        if side not in SIDES: raise ValueError('露龈调整需要人物侧别')
        for target in SIDES if r[key]['linked'] else (side,): r[key][target] = value_amount
    else:
        if side is not None: raise ValueError('此嘴形控件不拆分左右')
        r[key] = value_amount
    return check(r)


def link(value, linked):
    r = check(value)
    if type(linked) is not bool: raise ValueError('露龈联动状态无效')
    r['gummy']['linked'] = linked
    return r


def preset(value): return check(value)


def vector(value):
    r = check(value)
    return [r[k] for k in ('size','width','vertical','horizontal','m_lip','tilt','upper','lower')] + [r['gummy'][s] for s in SIDES]
