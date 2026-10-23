"""Strict original tonal grading recipe; legacy omission alone means neutral."""
import math
KEY = '_colour_grading'
ALGORITHM = 'lrt-tonal-opponent-v1'
SPACE = 'linear-srgb-d65'
RANGES = ('shadows', 'midtones', 'highlights', 'global')


def neutral():
    return {'version': 1, 'algorithm': ALGORITHM, 'working_space': SPACE,
            **{k: {'hue': 0.0, 'saturation': 0.0, 'luminance': 0.0} for k in RANGES},
            'blending': 50.0, 'balance': 0.0}


def number(value, lo, hi):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError('Colour grading scalar outside finite range')
    return float(value)


def check(value):
    if not isinstance(value, dict) or set(value) != set(neutral()):
        raise ValueError('Colour grading requires the complete versioned recipe')
    if type(value['version']) is not int or value['version'] != 1 or value['algorithm'] != ALGORITHM or value['working_space'] != SPACE:
        raise ValueError('Unsupported colour grading algorithm/space/version')
    out = neutral()
    for key in RANGES:
        row = value[key]
        if not isinstance(row, dict) or set(row) != {'hue', 'saturation', 'luminance'}:
            raise ValueError('Colour grading wheel requires hue/saturation/luminance')
        out[key] = {'hue': number(row['hue'], 0, 360) % 360,
                    'saturation': number(row['saturation'], 0, 100),
                    'luminance': number(row['luminance'], -100, 100)}
    out['blending'] = number(value['blending'], 0, 100)
    out['balance'] = number(value['balance'], -100, 100)
    return out


def from_state(state):
    return check(state[KEY]) if KEY in state else neutral()


def active(recipe):
    r = check(recipe)
    return any(r[k]['saturation'] != 0 or r[k]['luminance'] != 0 for k in RANGES)


def scalars(recipe):
    r = check(recipe)
    return [r[k][v] for k in RANGES for v in ('hue', 'saturation', 'luminance')] + [r['blending'], r['balance']]
