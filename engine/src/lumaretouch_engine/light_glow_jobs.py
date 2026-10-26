# SPDX-License-Identifier: GPL-3.0-or-later
"""Glow reader ingress; reuse the existing bounded event/identity coordinator.

Only read events/session cancellation are signalled out of band. The serialized
host alone settles receipts after actual unwind. Apply is never interrupted.
"""
import hashlib
import json
from .lens_blur_jobs import Jobs as BoundedJobs, canonical, token, digest

READS = frozenset(('current', 'preview'))
MAX_WIRE_BYTES = 16 * 1024


def command_hash(request):
    raw = canonical(request)
    if len(raw) > MAX_WIRE_BYTES:
        raise ValueError('Glow command exceeds bounded wire budget')
    return hashlib.sha256(b'lrt-light-glow-host-command-v1\0' + raw).hexdigest()


class Jobs(BoundedJobs):
    command_name = "light_glow"
    operation_id = "lnx.light_glow.v1"
    command_hash = staticmethod(command_hash)

    def ingress(self, line):
        if type(line) is not str or len(line) > MAX_WIRE_BYTES or self.command_name not in line:
            return False
        try:
            request = json.loads(line)
            if type(request) is not dict:
                return False
            if request.get('cmd') == self.command_name + '_cancel_read':
                if set(request) == {'cmd', 'request_id', 'request'}:
                    original = request['request']
                    if (type(original) is not dict or original.get('cmd') != self.command_name
                            or original.get('action') not in READS
                            or original.get('request_id') != request['request_id']):
                        return False
                    self.request_cancel(request['request_id'], self.command_hash(original))
                    return True
                if set(request) == {'cmd', 'request_id', 'command_sha256'}:
                    self.request_cancel(request['request_id'], request['command_sha256'])
                    return True
                return False
            if request.get('cmd') != self.command_name:
                return False
            request.pop('_host_request_id', None)
            if request.get('action') in READS:
                expected = {'cmd', 'action', 'request_id'}
                if request['action'] == 'preview':
                    expected.add('command')
                    c = request.get('command')
                    if (type(c) is not dict or type(c.get('version')) is not int or c['version'] != 1
                            or c.get('operation_id') != self.operation_id
                            or c.get('action') != 'preview' or c.get('request_id') != request['request_id']):
                        return False
                if set(request) == expected:
                    self.register(request['request_id'], self.command_hash(request))
            elif request.get('action') == 'submit':
                c = request.get('command')
                if (set(request) == {'cmd', 'action', 'request_id', 'command'} and type(c) is dict
                        and set(c) == {'version', 'operation_id', 'action', 'request_id', 'session_id', 'owner', 'token'}
                        and type(c['version']) is int and c['version'] == 1
                        and c['operation_id'] == self.operation_id and c['action'] == 'cancel'
                        and c['request_id'] == request['request_id']
                        and token(c['request_id']) and token(c['session_id'])
                        and (c['token'] is None or token(c['token']))):
                    self.cancel_session(c['session_id'], c['owner'])
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            pass
        return False


def controller(engine):
    owner = engine.__dict__.get('_light_glow_source_jobs')
    if owner is None:
        owner = engine.__dict__.setdefault('_light_glow_source_jobs', Jobs())
    return owner
