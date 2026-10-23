"""Versioned continuous colour selection; never aliases HSL or selective CMYK."""
import math
KEY = '_colour_editor'
ALGORITHM = 'lrt-continuous-colour-editor-v1'
SPACE = 'extended-srgb-d65'
def neutral():
    return {'version': 1, 'algorithm': ALGORITHM, 'working_space': SPACE, 'scope': 'all',
            'selection': {'hue': 0.0, 'half_width': 0.08, 'saturation': [0.0, 1.0], 'luminance': [0.0, 1.0]},
            'colour_smoothness': 0.1, 'luminance_smoothness': 0.1, 'linked': True,
            'offsets': [0.0, 0.0, 0.0], 'uniformity': [0.0, 0.0, 0.0], 'invert': False}
def number(x, lo, hi):
    if type(x) not in (int, float) or not math.isfinite(x) or not lo <= x <= hi:
        raise ValueError('Colour editor number outside finite bounds')
    return float(x)
def vector(x, n, lo, hi):
    if type(x) is not list or len(x) != n: raise ValueError('Colour editor vector shape')
    return [number(v, lo, hi) for v in x]
def check(value):
    if type(value) is not dict or set(value) != set(neutral()): raise ValueError('Complete colour editor recipe required')
    if type(value['version']) is not int or value['version'] != 1 or value['algorithm'] != ALGORITHM or value['working_space'] != SPACE: raise ValueError('Unsupported colour editor schema')
    if value['scope'] not in ('all','local'): raise ValueError('Colour editor scope must be all or current local mask')
    r = neutral(); r['scope'] = value['scope']; s = value['selection']
    if type(s) is not dict or set(s) != set(r['selection']): raise ValueError('Continuous selection required')
    for k in ('linked', 'invert'):
        if type(value[k]) is not bool: raise ValueError('Boolean colour editor toggle required')
        r[k] = value[k]
    r['selection'] = {'hue': number(s['hue'], 0, 1), 'half_width': number(s['half_width'], 0, .5),
                      'saturation': vector(s['saturation'], 2, 0, 1), 'luminance': vector(s['luminance'], 2, 0, 1)}
    for k in ('saturation', 'luminance'):
        if r['selection'][k][0] > r['selection'][k][1]: raise ValueError('Selection lower bound exceeds upper bound')
    for k in ('colour_smoothness', 'luminance_smoothness'): r[k] = number(value[k], 0, 1)
    if r['linked'] and r['colour_smoothness'] != r['luminance_smoothness']: raise ValueError('Linked smoothing must match')
    for k in ('offsets', 'uniformity'): r[k] = vector(value[k], 3, -100, 100)
    return r
def from_state(state): return check(state[KEY]) if KEY in state else neutral()
def active(r): return any(v != 0 for k in ('offsets', 'uniformity') for v in check(r)[k])
def scalars(r):
    r = check(r); s = r['selection']
    return [s['hue'], s['half_width'], *s['saturation'], *s['luminance'], r['colour_smoothness'], r['luminance_smoothness'],
            *(v / 100 for v in r['offsets']), *(v / 100 for v in r['uniformity']), float(r['invert']), 1.0]
