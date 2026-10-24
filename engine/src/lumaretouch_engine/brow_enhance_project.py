# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate saved original-brow scalar intent, without analysis/native work."""
from . import brow_enhance_state as S


def validate_leaf(path, value):
    from .people_resolver import materialize
    if path not in ('/linked', '/left', '/right'):
        raise ValueError('Saved original-brow recipe contains an unknown parameter')
    # Sparse leaf types cannot rely on equality: True == 1 and False == 0.
    neutral = {**S.neutral(), 'linked': False}
    materialize({'conflicts': [], 'operations': {
        S.OP: {path: {'value': value}}}}, S.OP, neutral, S.check)


def validate_graph(state):
    from . import people_state as P
    from .people_algorithms import defaults
    from .people_resolver import resolve, materialize
    out = P.check(state)
    for row in out['overrides']:
        if row['operation_id'] != S.OP:
            continue
        validate_leaf(row['parameter_path'], row['value'])
    for face in out['faces']:
        resolved = resolve(out, face, defaults())
        if not any(conflict['operation_id'] == S.OP for conflict in resolved['conflicts']):
            materialize({**resolved, 'conflicts': []}, S.OP, S.neutral(), S.check)
    # Retain unresolved inheritance conflicts for explicit recovery rather than
    # silently averaging/copying sides. No source masks or measurement persist.
    return out
