"""Portable PC-32466 nose intent. Numeric limits are local product policy.

Official 鼻高 means vertical POSITION, not longitudinal scale or 3D projection.
左右 is one positional amount, never a bilateral identity/unlock selector.
"""
import math
VERSION = 1
KEYS = ('size', 'height', 'position', 'bridge', 'wing', 'tip')
CONTROL_IDS = dict(zip(('family', *KEYS), ('PC-32466-C-ba582ff45d',
    'PC-32466-C-0025490aa7', 'PC-32466-C-180241806a', 'PC-32466-C-1ef85157f8',
    'PC-32466-C-6598ad2758', 'PC-32466-C-aed80c5608', 'PC-32466-C-aec9e15569')))


def neutral(): return {'version': VERSION, **dict.fromkeys(KEYS, 0.)}


def check(value):
    if value is None: return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('鼻形配方只接受版本和六项参数，不能携带人脸、蒙版或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此鼻形配方版本')
    result = {'version': VERSION}
    for key in KEYS:
        a = value[key]
        if type(a) not in (float, int) or not math.isfinite(a) or not -1 <= a <= 1:
            raise ValueError(f'鼻形 {key} 必须为 [-1,1] 有限数值')
        result[key] = float(a)
    return result


def active(value): return any(check(value)[k] != 0 for k in KEYS)


def adjust(value, key, amount):
    r = check(value)
    if key not in KEYS: raise ValueError('未知鼻形控件')
    r[key] = amount
    return check(r)


def preset(value): return check(value)
