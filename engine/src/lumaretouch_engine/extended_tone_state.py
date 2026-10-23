"""Versioned independent seven-control recipe; all ranges are original product choices."""
import math
from copy import deepcopy
KEY = '_extended_tone'
NAMES = ('brightness', 'whites', 'blacks', 'texture', 'clarity', 'dehaze', 'vibrance')
IDS = dict(zip(NAMES, ('935d133b92', 'ef0ecc2e31', 'b6a3a387f1', 'df1b3249dd', '9dc1af72b2', '0b1f30c7f5', 'e25d667189')))
ALGORITHM = 'lrt-extended-tone-v1'

def default():
    return {'version': 1, 'algorithm': ALGORITHM, 'enabled': True, 'monochrome': False, **dict.fromkeys(NAMES, 0.0)}

def check(value):
    if value is None: return default()
    if type(value) is not dict or set(value) != set(default()): raise ValueError('Extended tone requires the complete v1 recipe')
    if type(value['version']) is not int or value['version'] != 1 or value['algorithm'] != ALGORITHM or type(value['enabled']) is not bool or type(value['monochrome']) is not bool:
        raise ValueError('Unsupported extended tone schema/algorithm')
    result = deepcopy(value)
    for key in NAMES:
        v = value[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not -100 <= v <= 100: raise ValueError(f'{key} must be finite in [-100,100]')
        result[key] = float(v)
    return result

def active(value, monochrome=False):
    s = check(value)
    monochrome = monochrome or s['monochrome']
    return s['enabled'] and (s['monochrome'] or any(s[k] != 0 for k in NAMES if not (monochrome and k == 'vibrance')))

def effective(value, monochrome=False):
    s = check(value)
    monochrome = monochrome or s['monochrome']
    return tuple(s[k] if s['enabled'] and not (monochrome and k == 'vibrance') else 0. for k in NAMES)

def status(value, monochrome=False):
    s = check(value)
    return {'spec': s, 'active': active(s, monochrome), 'monochrome': s['enabled'] and s['monochrome'],
            'limits': {k: {'min': -100, 'max': 100, 'default': 0, 'provenance': 'original-product-range; official-unspecified'} for k in NAMES},
            'requirements': {k: 'LNX-REF-PC-32455-C-' + v for k, v in IDS.items()}}
