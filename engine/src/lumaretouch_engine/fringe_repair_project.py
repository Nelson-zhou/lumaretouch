"""Lossless fringe state/history codec adapters; no pixels or native imports."""
from . import fringe_repair_state as S

MAX_DEPTH = 64
_STATE_MARKERS = frozenset(('_strength', '_grade', '_exposure', '_creative_base',
                            '_local_masks', '_manual_liquify', '_optics'))


def capture(engine, record=None):
    # Do not deepcopy unrelated tensors/immutable assets into a second owner.
    result = {} if record is None else dict(record)
    result[S.KEY] = S.check(getattr(engine, S.KEY, S.neutral()))
    return result


def restore(engine, record):
    setattr(engine, S.KEY, S.from_state(record))


def validate_records(value, *, allowed=True, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError('Project nesting exceeds fringe repair validation budget')
    if isinstance(value, dict):
        for key in (S.KEY, 'fringe_repair'):
            if key in value:
                if not allowed:
                    raise ValueError('Fringe repair requires project v23; older schemas cannot carry it')
                S.check(value[key])
        for child in value.values():
            validate_records(child, allowed=allowed, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_records(child, allowed=allowed, depth=depth + 1)


def migrate_states(value, *, root=False, depth=0):
    """Owned legacy/history copies gain only disabled defaults where absent."""
    if depth > MAX_DEPTH:
        raise ValueError('Project nesting exceeds fringe repair migration budget')
    if isinstance(value, dict):
        for child in list(value.values()):
            migrate_states(child, depth=depth + 1)
        if root or _STATE_MARKERS.intersection(value):
            if S.KEY in value:
                S.check(value[S.KEY])
            else:
                value[S.KEY] = S.neutral()
    elif isinstance(value, (list, tuple)):
        for child in value:
            migrate_states(child, depth=depth + 1)


def configure_export(spec, snapshot, shape, *, for_document):
    # Rendering owns source/decode proofs; this adapter cannot fabricate them.
    from .fringe_repair_render import configure_export as configure
    return configure(spec, snapshot, shape, for_document=for_document)
