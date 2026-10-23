"""Strict nine-family process-colour recipe. No HSL alias or ICC CMYK claim."""
import math
KEY = '_selective_colour'
ALGORITHM = 'lrt-rgb-ink-v1'
SPACE = 'extended-srgb-d65'
RANGES = ('reds', 'yellows', 'greens', 'cyans', 'blues', 'magentas', 'whites', 'neutrals', 'blacks')
INKS = ('cyan', 'magenta', 'yellow', 'black')


def neutral():
    return {'version': 1, 'algorithm': ALGORITHM, 'working_space': SPACE,
            'method': 'relative', 'ranges': {k: {c: 0.0 for c in INKS} for k in RANGES}}


def check(value):
    if type(value) is not dict or set(value) != set(neutral()):
        raise ValueError('Selective colour requires the complete versioned recipe')
    if type(value['version']) is not int or value['version'] != 1 or value['algorithm'] != ALGORITHM or value['working_space'] != SPACE or value['method'] not in ('relative', 'absolute'):
        raise ValueError('Unsupported selective colour algorithm/space/method/version')
    rows = value['ranges']
    if type(rows) is not dict or set(rows) != set(RANGES):
        raise ValueError('All nine selective colour ranges are required')
    out = neutral()
    out['method'] = value['method']
    for key in RANGES:
        row = rows[key]
        if type(row) is not dict or set(row) != set(INKS):
            raise ValueError('Each range requires exactly four CMYK amounts')
        for ink in INKS:
            v = row[ink]
            if type(v) not in (int, float) or not math.isfinite(v) or not -100 <= v <= 100:
                raise ValueError('Selective colour amounts must be finite percentages in [-100,100]')
            out['ranges'][key][ink] = float(v)
    return out


def from_state(state):
    return check(state[KEY]) if KEY in state else neutral()


def active(recipe):
    return any(v != 0 for row in check(recipe)['ranges'].values() for v in row.values())


def scalars(recipe):
    r = check(recipe)
    return [r['ranges'][k][c] / 100 for k in RANGES for c in INKS] + [float(r['method'] == 'relative')]
