# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict transport-neutral commands; no photograph mutation or module registration."""
from . import background_material_state as S
from .background_material_controller import BackgroundMaterialLibrary


def controller(engine):
    owner = engine.__dict__.get('_background_material_library')
    if owner is None:
        owner = BackgroundMaterialLibrary()
        engine._background_material_library = owner
    return owner


def dispatch(engine, request, *, cancelled=lambda: False):
    if type(request) is not dict: S.fail('背景素材请求必须是对象')
    method = request.get('method')
    fields = {'snapshot': {'method'}, 'page': {'method', 'query', 'expected_revision'},
              'thumbnail': {'method', 'id', 'expected_revision'},
              'select': {'method', 'id', 'expected_revision'},
              'command': {'method', 'op', 'payload', 'expected_revision'}}
    if type(method) is not str or method not in fields: S.fail('未知背景素材请求')
    S.fields(request, fields[method]); S.cancelled(cancelled)
    library = controller(engine)
    if method == 'snapshot': return library.snapshot()
    if method == 'page': return library.page(request['query'], request['expected_revision'])
    if method == 'thumbnail': return library.thumbnail(request['id'], request['expected_revision'])
    if method == 'select': return library.select(request['id'], request['expected_revision'], cancelled=cancelled)
    return library.command(request['op'], request['payload'], request['expected_revision'], cancelled=cancelled)


def error_payload(error):
    return {'code': getattr(error, 'code', 'storage'), 'message': str(error)[:1000],
            'outcome_unknown': bool(getattr(error, 'outcome_unknown', not isinstance(error, S.MaterialError))),
            'committed': getattr(error, 'committed', None)}
