"""Exact command replies shared with an internal read-only observer."""
from copy import deepcopy


def responder(request, emit, trusted_result=None):
    if trusted_result is not None and not callable(trusted_result):
        raise ValueError('Internal export observer must be callable')
    preview = request.get('action') == 'preview'

    def respond(payload):
        if preview and payload.get('event') == 'error':
            payload = {'event': 'export_destination_result',
                       'request_id': request.get('request_id'),
                       'status': 'failed', 'error': payload.get('error')}
        emit(payload)
        if trusted_result is not None:
            trusted_result(deepcopy(payload))
    return respond
