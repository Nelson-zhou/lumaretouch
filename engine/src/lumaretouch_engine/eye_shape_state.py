"""PC-32466 eye v1: portable person-relative bilateral geometry intent.

All numeric bounds are LumaRetouch product policy, not PixCake specifications.
Relinking never changes values. The next explicit linked adjustment writes both.
"""
import math
VERSION = 1
KEYS = ('size', 'iris_size', 'height', 'width', 'spacing', 'inner_corner', 'outer_corner', 'lower_lid', 'tilt', 'position')
SIDES = ('left', 'right')
CONTROL_IDS = dict(zip(('family', *KEYS), ('PC-32466-C-9069cc8f2c', 'PC-32466-C-350a901827', 'PC-32466-C-a40648c2c9', 'PC-32466-C-c39023ab15', 'PC-32466-C-02e379c464', 'PC-32466-C-4aa3486419', 'PC-32466-C-59bdc2ef4c', 'PC-32466-C-6f1eb8b201', 'PC-32466-C-b2458f8502', 'PC-32466-C-89afddb33a', 'PC-32466-C-37e5823f58')))


def neutral():
    return {'version': VERSION, **{k: {'linked': True, 'left': 0., 'right': 0.} for k in KEYS}}


def check(value):
    if value is None: return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('眼形配方仅接受版本和十项独立双侧参数，不能携带人脸或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此眼形配方版本')
    out = {'version': VERSION}
    for key in KEYS:
        v = value[key]
        if type(v) is not dict or set(v) != {'linked', *SIDES} or type(v['linked']) is not bool:
            raise ValueError(f'眼形 {key} 需要明确的联动状态和人物左/右值')
        for side in SIDES:
            a = v[side]
            if type(a) not in (float, int) or not math.isfinite(a) or not -1 <= a <= 1:
                raise ValueError(f'眼形 {key}/{side} 必须为 [-1,1] 有限数值')
        out[key] = {'linked': v['linked'], **{s: float(v[s]) for s in SIDES}}
    return out


def active(value):
    r = check(value)
    return any(r[k][s] != 0 for k in KEYS for s in SIDES)


def side_active(value, side):
    if side not in SIDES: raise ValueError('未知人物侧别')
    r = check(value)
    return any(r[k][side] != 0 for k in KEYS)


def adjust(value, key, side, amount):
    r = check(value)
    if key not in KEYS or side not in SIDES: raise ValueError('未知眼形控件或人物侧别')
    for target in SIDES if r[key]['linked'] else (side,): r[key][target] = amount
    return check(r)


def link(value, key, linked):
    r = check(value)
    if key not in KEYS or type(linked) is not bool: raise ValueError('非法眼形联动设置')
    r[key]['linked'] = linked
    return r


def preset(value):
    return check(value)
