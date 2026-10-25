# SPDX-License-Identifier: GPL-3.0-or-later
"""Private one-command admission through the unchanged dispatcher/history path.

Only a retained workflow handoff may enter this scope. No JSON flag grants it.
The normal subsystem guards, handler, history record and preset finish still run.
"""
from contextvars import ContextVar
from copy import deepcopy
import json

_CURRENT = ContextVar('workflow_preset_dispatch', default=None)


def permits(engine, name, payload):
    current = _CURRENT.get()
    return bool(current is not None and current[0] is engine
                and name == current[1].get('cmd') and payload == current[1])


def dispatch(engine, payload, recheck):
    if _CURRENT.get() is not None:
        raise ValueError('Nested workflow handoff dispatch is not permitted')
    if payload.get('cmd') not in ('load_image', 'preset'):
        raise ValueError('Workflow handoff cannot dispatch an unrelated command')
    if not callable(recheck):
        raise ValueError('Workflow handoff requires its retained owner proof')
    recheck()
    exact = deepcopy(payload)
    from . import project_recovery_runtime as recovery
    previous_boundary = getattr(recovery._local, 'boundary', None)
    token = _CURRENT.set((engine, exact))
    try:
        # _process_line owns both history capture/record and PresetController.finish.
        # Direct PresetController.apply would bypass that authoritative boundary.
        engine._process_line(json.dumps(exact, ensure_ascii=False, allow_nan=False), engine._dispatch_table())
    finally:
        recovery._local.boundary = previous_boundary
        _CURRENT.reset(token)
