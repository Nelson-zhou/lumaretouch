"""Only parameters transfer; target coverage and source are always reset."""
import hashlib
import json
from . import fringe_repair_state as S

OP = 'lnx.fringe_repair.v1'
FIELDS = (S.KEY,)


def check_params(value):
    if type(value) is not dict or set(value) != {'enabled', 'strength'}:
        raise ValueError('Fringe repair transfer accepts enabled and strength only')
    if type(value['enabled']) is not bool:
        raise ValueError('Fringe repair transfer enabled must be boolean')
    return {'enabled': value['enabled'],
            'strength': S.number(value['strength'], 0.0, 100.0, 'strength')}


def params_of(state):
    recipe = S.from_state(state)
    return {key: recipe[key] for key in ('enabled', 'strength')}


def install(state, params):
    recipe = S.neutral()
    recipe.update(check_params(params))
    state[S.KEY] = recipe


def restore(state, previous):
    # Undo is not a parameter transfer. Its reviewed prior target owns strokes.
    state[S.KEY] = S.from_state(previous)


def undo_key(state):
    # A later brush edit is a scope conflict even if strength is unchanged.
    raw = json.dumps(S.from_state(state), sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def validate_target(state, path, shape):
    S.verify_source(S.from_state(state), state, path, (shape[1], shape[0]))
