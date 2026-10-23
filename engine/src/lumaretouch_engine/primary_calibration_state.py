"""Versioned primary basis controls, NOT selective HSL or camera profiling."""
import math
KEY = '_primary_calibration'
ALGORITHM = 'lrt-xy-primary-basis-v1'
SPACE = 'linear-srgb-d65'
PRIMARIES = ('red', 'green', 'blue')

def neutral():
    return {'version': 1, 'algorithm': ALGORITHM, 'working_space': SPACE,
            **{k: {'hue': 0.0, 'saturation': 0.0} for k in PRIMARIES}}

def check(value):
    if type(value) is not dict or set(value) != set(neutral()):
        raise ValueError('Primary calibration requires complete recipe')
    if type(value['version']) is not int or value['version'] != 1 or value['algorithm'] != ALGORITHM or value['working_space'] != SPACE:
        raise ValueError('Unsupported primary calibration version/space/algorithm')
    out = neutral()
    for k in PRIMARIES:
        row = value[k]
        if type(row) is not dict or set(row) != {'hue', 'saturation'}:
            raise ValueError('Primary calibration needs hue and saturation')
        for field in ('hue', 'saturation'):
            v = row[field]
            if type(v) not in (int, float) or not math.isfinite(v) or not -100 <= v <= 100:
                raise ValueError('Primary calibration scalar outside -100..100')
            out[k][field] = float(v)
    return out

def from_state(state):
    return check(state[KEY]) if KEY in state else neutral()

def active(recipe):
    r = check(recipe)
    return any(r[k][f] != 0 for k in PRIMARIES for f in ('hue', 'saturation'))

def scalars(recipe):
    r = check(recipe)
    return [r[k][f] for k in PRIMARIES for f in ('hue', 'saturation')]
