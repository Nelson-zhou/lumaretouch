# SPDX-License-Identifier: GPL-3.0-or-later
"""AI full-source review reuses the existing immutable new-copy owner. UNRUN."""
from . import upscale_restore_stage as stage
from .light_glow_host import Service as SharedService, _text, _receipt
from .upscale_restore_jobs import controller as jobs, command_hash


class Service(SharedService):
    stage = stage
    jobs = staticmethod(jobs)
    command_hash = staticmethod(command_hash)
    command_name = 'upscale_restore'
    event_name = 'upscale_restore_result'
    # The isolated CPU worker has a 610-second hard wall cap. Source capture
    # retains the shared 120-second capture deadline. The shared stage polls
    # its earlier 600-second deadline; 610 is a final worker cleanup boundary.
    job_seconds = 600.0
    session_seconds = 900.0

def service(engine, emit):
    owner = engine.__dict__.get('_upscale_restore_service')
    if owner is None:
        owner = Service(engine, emit)
        engine._upscale_restore_service = owner
    return owner


def handle(engine, request, emit):
    service(engine, emit).handle(request)


def read_only(request):
    return request.get('cmd') == 'upscale_restore' and request.get('action') in ('current', 'preview', 'receipt')


def guard_other(engine, name, request):
    owner = engine.__dict__.get('_upscale_restore_service')
    if (owner is not None and owner.uncertain is not None and name not in ('upscale_restore', 'hello', 'shutdown')
            and not (name == 'session' and request.get('action') == 'query')):
        raise ValueError('AI 超清新图原请求结果待核对；其他修改暂受保护，请勿盲目重试')


def invalidate(engine):
    owner = engine.__dict__.get('_upscale_restore_service')
    if owner is not None:
        owner.maintain()


def dispatch_rejected(request, message, started, emit, *, engine=None):
    if engine is not None and request.get('action') in ('current', 'preview'):
        try:
            jobs(engine).retire(request.get('request_id'), command_hash(request))
        except (ValueError, TypeError, KeyError):
            pass
    result = {'event': 'upscale_restore_result', 'request_id': request.get('request_id'),
              'status': 'rejected', 'message': _text(message)}
    if request.get('action') in ('submit', 'receipt'):
        try:
            command = stage.write_command(request.get('command'))
            owner = service(engine, emit) if engine is not None else None
            receipt = owner._known(command) if owner is not None else None
            if receipt is None:
                unknown = bool(started or request['action'] == 'receipt' or owner is None)
                receipt = _receipt(command, phase='unknown' if unknown else 'done',
                                   outcome=None if unknown else 'rejected', message=_text(message))
                if owner is not None and not unknown:
                    owner._save(command, receipt)
            result.update(status='ready', receipt=receipt)
            result.pop('message', None)
        except (ValueError, TypeError, KeyError, MemoryError):
            pass
    emit(result)
