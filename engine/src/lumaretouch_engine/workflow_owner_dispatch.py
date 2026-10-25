"""Correlated dispatcher rejection without inventing a mutation rollback."""
from . import workflow_owner_protocol as P


def rejected(engine, payload, error, started, emit):
    request = payload if type(payload) is dict else {}
    owner = getattr(engine, '_workflow_owner_host', None)
    try:
        request = P.envelope(payload)
        if owner is not None and request['action'] == 'execute':
            record = owner.requests.get(request['request_id'])
            if record is not None and record['request'] == request:
                return owner._publish(request, record)
            command = P.command(request['command'])
            record = owner.operations.get(command['identity']['operation_id'])
            if (record is not None and record['command'] == command
                    and record['request']['session_id'] == request['session_id']):
                return owner._publish(request, record)
    except (ValueError, TypeError, KeyError, OSError):
        pass
    # This marker is affirmative proof ONLY that the dispatcher did not enter
    # this original handler. Once entered, missing state is unknown, not failed.
    result = {'event': 'workflow_owner_result', 'protocol': 1,
        'request_id': request.get('request_id'), 'action': request.get('action'),
        'session_id': request.get('session_id'), 'runtime_verified': False,
        'status': 'unknown' if started else 'failed', 'error': str(error)[:2048]}
    if request.get('action') in ('review_step', 'review_image'):
        result['operation_id'] = request.get('operation_id')
    if request.get('action') == 'review_step':
        result['step'] = request.get('step')
    if not started: result['dispatch_rejected'] = True
    emit(result)
    return result
