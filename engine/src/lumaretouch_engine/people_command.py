"""Pure command fence adapter. Dispatcher/receipt system owns atomic publication."""
from . import people_state as S


def validate_envelope(command, state, *, document_id, document_epoch, document_revision):
    state = S.check(state)
    required = {'document_id', 'document_epoch', 'document_revision', 'state_revision', 'association_revision', 'target', 'request_id'}
    if type(command) is not dict or not required <= set(command):
        raise ValueError('People edit requires a document-bound receipt envelope')
    for key in ('document_id', 'document_epoch', 'request_id'): S.token(command[key])
    for key in ('document_revision', 'state_revision', 'association_revision'): S.revision(command[key])
    if (command['document_id'], command['document_epoch'], command['document_revision']) != (document_id, document_epoch, document_revision):
        raise ValueError('Stale people command document binding')
    if (command['state_revision'], command['association_revision']) != (state['revision'], state['association_revision']):
        raise ValueError('Stale people command graph binding')
    target = command['target']
    if type(target) is not dict or set(target) != {'scope', 'target_id', 'face_ref'}:
        raise ValueError('Explicit people edit target required')
    scope, key = target['scope'], target['target_id']
    if scope not in S.SCOPES: raise ValueError('Invalid people target scope')
    if scope == 'all_people':
        S.digest(key)
        if target['face_ref'] is not None: raise ValueError('Invalid all-people target')
    else:
        collection = state[{'face': 'faces', 'person': 'persons', 'group': 'groups'}[scope]]
        if key not in collection: raise ValueError('People target no longer exists')
        if scope == 'face':
            if S.check_ref(target['face_ref']) != S.face_ref(collection[key]): raise ValueError('Face analysis changed')
        elif target['face_ref'] is not None: raise ValueError('Group/person target cannot carry a single-face alias')
    return target.copy()
