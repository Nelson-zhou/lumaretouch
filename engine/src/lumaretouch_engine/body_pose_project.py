"""Document-owned durable body evidence/intent; no inference during project I/O."""
from . import body_pose_state as B,shoulder_shape_project as P
KEY='_body_pose_bank'


def fields(state=None):
    state={} if state is None else state
    return {KEY:P.pack(P.unpack(state[KEY]) if KEY in state else B.empty())}


def bank(state):
    return P.unpack(state[KEY]) if KEY in state else B.empty()


def validate_records(value,*,allowed=True):
    if isinstance(value,dict):
        if KEY in value:
            if not allowed:raise ValueError('Body operation ownership requires project v13; old readers must reject it')
            P.unpack(value[KEY])
        if '_body_pose_transition' in value:
            if not allowed:raise ValueError('Body history requires project v13')
            from .body_pose_document_history import validate_transition
            validate_transition(value['_body_pose_transition'])
        for child in value.values():validate_records(child,allowed=allowed)
    elif isinstance(value,(list,tuple)):
        for child in value:validate_records(child,allowed=allowed)


def migrate(value,*,root=False):
    if isinstance(value,dict):
        for child in list(value.values()):migrate(child)
        if root or '_strength' in value or KEY in value:value.update(fields(value))
    elif isinstance(value,list):
        for child in value:migrate(child)
