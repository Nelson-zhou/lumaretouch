# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded reader-thread cancellation ingress for the lens host.

AUTHORED / UNRUN. This module never decodes, renders, commits, emits a successful
receipt or interrupts a write. Only the serialized host reports actual unwind.
Request identities and their command hashes are never silently recycled.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading

READS = frozenset(('current', 'prepare_manual_plane', 'preview'))
MAX_WIRE_BYTES = 524_288 + 4096
MAX_JOBS = 8
MAX_IDENTITIES = 512
MAX_EARLY = 64


def token(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is not None


def digest(value):
    return type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value) is not None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def command_hash(request):
    raw = canonical(request)
    if len(raw) > MAX_WIRE_BYTES:
        raise ValueError('Lens transport request exceeds its byte budget')
    return hashlib.sha256(b'lrt-lens-host-command-v1\0' + raw).hexdigest()


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = {}
        self.identities = {}
        self.finished = set()
        self.early = set()
        self.session = None
        self.stopped = False
        self.overflow = False

    def register(self, ident, sha):
        if not token(ident) or not digest(sha):
            raise ValueError('Malformed lens source-job identity')
        with self.lock:
            old = self.identities.get(ident)
            if old is not None and old != sha:
                raise ValueError('Lens read request identity reused with different content')
            if ident in self.finished:
                raise ValueError('Completed lens source request cannot execute again')
            if ident not in self.identities:
                if len(self.identities) >= MAX_IDENTITIES:
                    raise ValueError('Lens read identity ledger is full; no identity was evicted')
                self.identities[ident] = sha
            if ident not in self.active:
                if len(self.active) >= MAX_JOBS:
                    self.overflow = True
                    for value in self.active.values():
                        value['event'].set()
                    raise ValueError('Lens source-job admission is full; no new allocation')
                self.active[ident] = {'sha': sha, 'event': threading.Event(), 'running': False}
            value = self.active[ident]
            if (ident, sha) in self.early or self.stopped or self.overflow:
                value['event'].set()
            self.early.discard((ident, sha))
            return value['event']

    def request_cancel(self, ident, sha):
        if not token(ident) or not digest(sha):
            return
        with self.lock:
            old = self.identities.get(ident)
            if old is not None and old != sha:
                return
            value = self.active.get(ident)
            if value is not None:
                value['event'].set()
            elif ident not in self.finished:
                if len(self.early) >= MAX_EARLY:
                    self.overflow = True
                    for value in self.active.values():
                        value['event'].set()
                else:
                    self.early.add((ident, sha))

    def bind_session(self, ident, owner):
        if not token(ident):
            raise ValueError('Malformed lens session identity')
        owner_json = canonical(owner)
        with self.lock:
            if self.session is not None:
                self.session['event'].set()
            event = threading.Event()
            if self.stopped or self.overflow:
                event.set()
            self.session = {'id': ident, 'owner': owner_json, 'event': event}
            return event

    def cancel_session(self, ident, owner):
        owner_json = canonical(owner)
        with self.lock:
            if (self.session is not None and self.session['id'] == ident
                    and self.session['owner'] == owner_json):
                self.session['event'].set()

    def close_session(self, ident):
        with self.lock:
            if self.session is not None and self.session['id'] == ident:
                self.session['event'].set()
                self.session = None

    def run(self, ident, sha, method):
        event = self.register(ident, sha)
        with self.lock:
            value = self.active[ident]
            if value['running']:
                raise ValueError('The exact lens read is already running')
            value['running'] = True
        result = None
        failure = None
        try:
            if event.is_set():
                raise InterruptedError('Lens source read cancelled before allocation')
            result = method(event.is_set)
        except BaseException as error:
            failure = error
        finally:
            with self.lock:
                cancelled = event.is_set() or self.stopped or self.overflow
                self.active.pop(ident, None)
                self.early.discard((ident, sha))
                self.finished.add(ident)
        if cancelled:
            raise InterruptedError('Lens source work actually unwound; no late result retained')
        if failure is not None:
            raise failure
        return result

    def retire(self, ident, sha):
        """Retire a queued read rejected by the host before allocation."""
        if not token(ident) or not digest(sha):
            return
        with self.lock:
            if self.identities.get(ident) != sha:
                return
            value = self.active.get(ident)
            if value is not None and value['running']:
                return
            self.active.pop(ident, None)
            self.early.discard((ident, sha))
            self.finished.add(ident)

    def ingress(self, line):
        """Only an explicit read-cancel control is consumed, never a write."""
        if type(line) is not str or len(line) > MAX_WIRE_BYTES or 'lens_blur' not in line:
            return False
        try:
            request = json.loads(line)
            if type(request) is not dict:
                return False
            if request.get('cmd') == 'lens_blur_cancel_read':
                if set(request) == {'cmd', 'request_id', 'command_sha256'}:
                    self.request_cancel(request['request_id'], request['command_sha256'])
                    return True
                if set(request) == {'cmd', 'request_id', 'request'}:
                    original = request['request']
                    if (type(original) is not dict or original.get('cmd') != 'lens_blur'
                            or original.get('action') not in READS
                            or original.get('request_id') != request['request_id']):
                        return False
                    expected = {'cmd', 'action', 'request_id'}
                    if original['action'] != 'current':
                        expected.add('command')
                    if set(original) != expected:
                        return False
                    # Native echoes the exact envelope it originally emitted.
                    # Python owns both hashes; no cross-language float JSON
                    # formatting is presented as a shared canonical digest.
                    self.request_cancel(request['request_id'], command_hash(original))
                    return True
                return False
            if request.get('cmd') != 'lens_blur':
                return False
            # Dispatcher metadata is stripped by server._process_line before
            # the serialized host. Hash the same application envelope here;
            # the out-of-band cancellation proof never contains this counter.
            request.pop('_host_request_id', None)
            if request.get('action') in READS:
                expected = {'cmd', 'action', 'request_id'}
                if request['action'] != 'current':
                    expected.add('command')
                if set(request) != expected:
                    return False
                if request['action'] != 'current':
                    command = request['command']
                    if (type(command) is not dict or type(command.get('version')) is not int
                            or command['version'] != 3 or command.get('action') != request['action']
                            or command.get('request_id') != request['request_id']):
                        return False
                self.register(request.get('request_id'), command_hash(request))
            elif request.get('action') == 'submit' and set(request) == {'cmd', 'action', 'request_id', 'command'}:
                command = request['command']
                if (type(command) is dict and set(command) == {'version', 'action', 'request_id', 'session_id', 'owner', 'token'}
                        and type(command['version']) is int and command['version'] == 3
                        and command['action'] == 'cancel' and command['request_id'] == request['request_id']
                        and token(command['request_id']) and token(command['session_id'])
                        and (command['token'] is None or token(command['token']))):
                    self.cancel_session(command['session_id'], command['owner'])
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            pass  # The serialized host, not the reader, owns failure receipts.
        return False

    def stop(self):
        with self.lock:
            self.stopped = True
            for value in self.active.values():
                value['event'].set()
            if self.session is not None:
                self.session['event'].set()


def controller(engine):
    owner = engine.__dict__.get('_lens_blur_source_jobs')
    if owner is None:
        owner = engine.__dict__.setdefault('_lens_blur_source_jobs', Jobs())
    return owner
