"""Versioned deterministic grain recipe. Seed is data, never render-time entropy."""
import math
KEY = '_photo_grain'
ALGORITHM = 'lrt-source-grain-v1'
SPACE = 'extended-srgb-d65'
CONTROLS = ('strength', 'shadows', 'midtones', 'highlights', 'size', 'roughness', 'colour')


def neutral():
    return dict(version=1, algorithm=ALGORITHM, working_space=SPACE, size_unit='source_pixels',
                seed=1, strength=0., shadows=100., midtones=100., highlights=100.,
                size=1.5, roughness=50., colour=0.)


def check(value):
    if not isinstance(value, dict) or set(value) != set(neutral()):
        raise ValueError('Photo grain requires complete versioned recipe')
    if type(value['version']) is not int or value['version'] != 1 or value['algorithm'] != ALGORITHM or value['working_space'] != SPACE or value['size_unit'] != 'source_pixels':
        raise ValueError('Unsupported photo grain schema, space or pixel units')
    if type(value['seed']) is not int or not 0 <= value['seed'] <= 4294967295:
        raise ValueError('Photo grain seed must be an unsigned 32-bit integer')
    out = dict(value)
    for key in CONTROLS:
        v = value[key]
        lo, hi = (0.5, 16.) if key == 'size' else (0., 100.)
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError('Photo grain scalar outside finite range: ' + key)
        out[key] = float(v)
    return out


def from_state(state):
    return check(state[KEY]) if KEY in state else neutral()


def active(recipe):
    r = check(recipe)
    return r['strength'] != 0 and any(r[k] != 0 for k in ('shadows', 'midtones', 'highlights'))


def scalars(recipe):
    r = check(recipe)
    return [r[k] for k in CONTROLS]
