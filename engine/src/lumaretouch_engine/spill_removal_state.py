"""Versioned ID spill intent; manual coverage only restricts confidence.

The containing ID recipe owns source identity, independently reviewed subject
support and history. This record never contains estimated foreground/background
pixels, learned alpha, or rendered correction fields. Numeric scales are ours.
"""
from copy import deepcopy
from .local_mask_recipe import number

VERSION = 1
ALGORITHM = 'lrt-spill-removal-v1'


def neutral():
    return {'version': VERSION, 'algorithm': ALGORITHM, 'enabled': False,
            'strength': 50., 'coverage': None}


def check(raw):
    if (type(raw) is not dict or set(raw) != set(neutral())
            or type(raw['version']) is not int or raw['version'] != VERSION
            or raw['algorithm'] != ALGORITHM or type(raw['enabled']) is not bool):
        raise ValueError('祛染色需要完整且受支持的版本、算法和启用状态')
    from .spill_removal_coverage import check_binding
    coverage = None if raw['coverage'] is None else check_binding(raw['coverage'])
    return {'version': VERSION, 'algorithm': ALGORITHM, 'enabled': raw['enabled'],
            'strength': number(raw['strength'], 0, 100), 'coverage': coverage}


def active(raw):
    value = check(raw)
    return value['enabled'] and value['strength'] > 0


def check_portable(raw):
    if (type(raw) is not dict or set(raw) != {'enabled', 'strength'}
            or type(raw['enabled']) is not bool):
        raise ValueError('祛染色预设只接受启用与强度，不接受其他照片的覆盖度')
    return {'enabled': raw['enabled'], 'strength': number(raw['strength'], 0, 100)}


def portable(raw):
    value = check(raw)
    return {key: value[key] for key in ('enabled', 'strength')}


def apply_portable(target, raw):
    """Parameters transfer; explicit target-owned manual coverage survives."""
    value = check(target)
    value.update(check_portable(raw))
    return deepcopy(value)
