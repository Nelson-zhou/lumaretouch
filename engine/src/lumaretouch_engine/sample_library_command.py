# SPDX-License-Identifier: GPL-3.0-or-later
"""Narrow transport adapter; host routing/receipts must call dispatch explicitly.

This module does not register itself, mutate editor parameters, or imply UI reachability.
Host must serialize dispatch with the editor command thread and map request cancellation
into the supplied callback. Errors preserve committed/uncertain outcome information.
"""
from . import sample_library_state as S
from .sample_library_controller import SampleLibrary
from .sample_library_capture import capture_current, context, heavy_reason


def controller(engine):
    value = engine.__dict__.get('_sample_library_controller')
    if value is None:
        value = SampleLibrary(capture=lambda expected, cancel: capture_current(engine, expected, cancel))
        engine._sample_library_controller = value
    return value


def dispatch(engine, request, *, cancelled=lambda: False):
    if type(request) is not dict: S.fail('样片请求必须是对象')
    library = controller(engine)
    method = request.get('method')
    fields = {'snapshot': {'method'}, 'context': {'method'},
              'page': {'method', 'query', 'expected_revision'}, 'thumbnail': {'method', 'id'},
              'select': {'method', 'id', 'expected_revision'},
              'capture': {'method', 'name', 'group_id', 'expected_revision', 'expected_context'},
              'command': {'method', 'op', 'payload', 'expected_revision'},
              'reclaim_plan': {'method'}}
    if type(method) is not str or method not in fields or set(request) != fields[method]: S.fail('样片请求字段无效')
    if method == 'context': return context(engine)
    if method in ('select', 'capture') or (method == 'command' and request['op'] == 'import_paths'):
        reason = heavy_reason(engine)
        if reason: S.fail(reason, 'busy')
    if method == 'snapshot': return library.snapshot()
    if method == 'page': return library.page(request['query'], request['expected_revision'])
    if method == 'thumbnail': return {'data_url': library.thumbnail(request['id'])}
    if method == 'select': return library.select(request['id'], request['expected_revision'], cancelled=cancelled)
    if method == 'capture':
        return library.capture(request['name'], request['group_id'], request['expected_revision'],
                               expected_context=request['expected_context'], cancelled=cancelled)
    if method == 'command':
        return library.command(request['op'], request['payload'], request['expected_revision'], cancelled=cancelled)
    return library.reclaim_plan()


def error_payload(error):
    return {'code': getattr(error, 'code', 'storage'), 'message': str(error)[:1000],
            'outcome_unknown': bool(getattr(error, 'outcome_unknown', not isinstance(error, S.LibraryError))),
            'committed': getattr(error, 'committed', None)}
