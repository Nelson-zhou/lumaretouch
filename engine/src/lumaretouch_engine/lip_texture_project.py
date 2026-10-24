# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate portable lip-furrow intent without native/source work."""
from . import lip_texture_state as S


def validate_leaf(path, value):
    if path != '/amount':
        raise ValueError('Unknown lip texture parameter; no masks or source samples may persist')
    S.check({'version': 1, 'amount': value})


def validate_graph(state):
    from . import people_state as P
    from .people_algorithms import defaults
    from .people_resolver import resolve, materialize
    out = P.check(state)
    for row in out['overrides']:
        if row['operation_id'] == S.OP:
            validate_leaf(row['parameter_path'], row['value'])
    for face in out['faces']:
        resolved = resolve(out, face, defaults())
        if not any(c['operation_id'] == S.OP for c in resolved['conflicts']):
            materialize({**resolved, 'conflicts': []}, S.OP, S.neutral(), S.check)
    return out
