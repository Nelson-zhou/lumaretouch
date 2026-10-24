# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural body-evenness intent validation, including history. UNRUN.

No live support resolution occurs here: an undo entry may retain an old body
association. Active preparation separately requires the exact current review.
"""
from . import body_skin_evenness_state as S


def validate_leaf(path, value):
    if path != '/amount':
        raise ValueError('Unknown body skin evenness parameter; source, face targets and masks cannot persist')
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


def validate_records(value):
    """Validate every active/undo/redo graph without editing any live owner."""
    if isinstance(value, dict):
        for key in ('people_graph', '_people_state'):
            if key in value:
                if value[key] is None:
                    raise ValueError('Saved body skin evenness people state cannot be null')
                validate_graph(value[key])
        for child in value.values():
            validate_records(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_records(child)
