# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict portable eye-bag intent including stored history. AUTHORED / UNRUN."""
from . import eye_bag_preserve_state as S


def validate_leaf(path, value):
    if path not in ('/amount', '/preserve'):
        raise ValueError('Eye-bag preservation stores only amount/preserve scalar leaves')
    S.check({**S.neutral(), path[1:]: value})


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
        if not any(row['operation_id'] == S.OP for row in resolved['conflicts']):
            materialize({**resolved, 'conflicts': []}, S.OP, S.neutral(), S.check)
    # Historical conflicts remain readable for explicit recovery. Compatibility
    # is enforced on the complete staged candidate and at render admission.
    return out


def validate_records(value):
    if isinstance(value, dict):
        for key in ('people_graph', '_people_state'):
            if key in value:
                if value[key] is None:
                    raise ValueError('Saved eye-bag people state cannot be null')
                validate_graph(value[key])
        for child in value.values():
            validate_records(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_records(child)


def require_unreviewed_transition(before, candidate):
    """Generic graph workflows cannot introduce/change an enabled v2 effect.

    The dedicated full-image review publishes through the existing owner and
    intentionally does not call this guard. Ordinary reset, dormant disabled
    intent and unrelated edits retain their existing workflows. Support merely
    being present is never authorization to change an active reviewed effect.
    """
    from . import people_state as P, people_algorithms as A
    from .people_resolver import resolve
    before = P.check(before); candidate = P.check(candidate)
    for key, face in candidate['faces'].items():
        if not face['enabled']:
            continue
        resolved = resolve(candidate, key, A.defaults())
        # Existing conflict handling must remain reviewable. If the v2 value
        # itself is ambiguous, no active recipe is admitted by rendering either.
        if any(row['operation_id'] == S.OP for row in resolved['conflicts']):
            continue
        from .people_resolver import materialize
        recipe = materialize({**resolved, 'conflicts': []}, S.OP, S.neutral(), S.check)
        if not S.active(recipe):
            continue
        old_face = before['faces'].get(key)
        old_resolved = resolve(before, key, A.defaults()) if old_face is not None else None
        old_recipe = (materialize({**old_resolved, 'conflicts': []}, S.OP, S.neutral(), S.check)
            if old_resolved is not None and not any(row['operation_id'] == S.OP
                for row in old_resolved['conflicts']) else None)
        if (old_face is None or not old_face['enabled'] or old_recipe != recipe
                or P.face_ref(old_face) != P.face_ref(face) or old_face['evidence'] != face['evidence']
                or old_face['box'] != face['box']
                or old_face['local_assets'].get(S.KIND) != face['local_assets'].get(S.KIND)):
            raise ValueError('Active eye-bag preservation requires the exact full-image reviewed action')
    return candidate
