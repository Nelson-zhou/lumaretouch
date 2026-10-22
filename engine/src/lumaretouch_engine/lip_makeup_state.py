"""PC-32471 lip subgroup: portable numeric intent, not cached anatomy.

Product-defined signed [-1,1] controls. These are not official PixCake ranges.
No global makeup amount, lipstick asset, recolouring swatch or texture preset.
"""
import math
VERSION = 1
KEYS = ('saturation', 'brightness', 'dimensionality')
CONTROL_IDS = {'family': '944899f5fd', 'saturation': '3d1502871b',
               'brightness': 'd5fc30a763', 'dimensionality': '21e4a8d464'}


def neutral():
    return {'version': VERSION, **dict.fromkeys(KEYS, 0.0)}


def check(value):
    if value is None: return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('唇妆配方必须包含版本和三个独立控件，不能携带人脸或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此唇妆配方版本')
    for key in KEYS:
        v = value[key]
        if type(v) not in (float, int) or not math.isfinite(v) or not -1 <= v <= 1:
            raise ValueError(f'唇妆 {key} 必须为 [-1,1] 有限数值')
    return {'version': VERSION, **{k: float(value[k]) for k in KEYS}}


def active(value):
    return any(check(value)[k] != 0 for k in KEYS)


def patch(value, updates):
    if type(updates) is not dict or set(updates) - set(KEYS):
        raise ValueError('唇妆修改包含未知字段')
    return check({**check(value), **updates})


def preset(value):
    return check(value)  # Deliberately excludes source, landmarks and recovery.
