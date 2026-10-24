# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural body-to-own-face intent validation, including history. UNRUN.

Old history may retain old face/body associations. Live source/reference review
is resolved separately; structural validation never grants that permission.
"""
from . import body_face_match_state as S


def validate_leaf(path, value):
    if path != '/amount':
        raise ValueError('Unknown body-face match parameter; source, reference and masks cannot persist')
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
    """Validate active/undo/redo graphs without editing any live owner."""
    if isinstance(value, dict):
        for key in ('people_graph', '_people_state'):
            if key in value:
                if value[key] is None:
                    raise ValueError('Saved body-face match people state cannot be null')
                validate_graph(value[key])
        for child in value.values():
            validate_records(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_records(child)
