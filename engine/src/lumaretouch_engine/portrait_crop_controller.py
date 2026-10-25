# SPDX-License-Identifier: GPL-3.0-or-later
"""Portrait crop reader cancellation only; serialized host owns every write.

AUTHORED / UNRUN. An ingress acknowledgement is not cancellation completion.
The original read must unwind before its cancelled receipt can be published.
"""
from collections import OrderedDict
import hashlib
import json
import threading

VERSION = 1
COMMAND = 'portrait_crop'
READS = frozenset(('current', 'preview'))
MAX_COMMAND_BYTES = 64 * 1024
MAX_JOBS = 32
MAX_FINISHED = 512


def valid_id(value):
    return (type(value) is str and 1 <= len(value) <= 128
            and all(c.isascii() and (c.isalnum() or c in '._:-') for c in value))


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def canonical(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(raw) > MAX_COMMAND_BYTES:
        raise ValueError('Portrait crop request exceeds its exact command budget')
    return raw


def command_hash(request):
    if (type(request) is not dict or request.get('cmd') != COMMAND
            or not valid_id(request.get('request_id')) or type(request.get('action')) is not str):
        raise ValueError('Portrait crop requires an exact request identity')
    return hashlib.sha256(canonical(request)).hexdigest()


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = {}
        self.finished = OrderedDict()
        self.early = set()
        self.stopped = False

    def register(self, ident, sha):
        if not valid_id(ident) or not digest(sha):
            raise ValueError('Invalid portrait crop read-job identity')
        key = (ident, sha)
        with self.lock:
            if any(rid == ident and known != sha for rid, known in (*self.events, *self.finished, *self.early)):
                raise ValueError('Portrait crop request ID reused with different content')
            if key in self.finished:
                raise ValueError('Finished portrait crop read cannot be restarted')
            if key not in self.events:
                if len(self.events) >= MAX_JOBS:
                    raise ValueError('Portrait crop read capacity reached')
                self.events[key] = threading.Event()
            event = self.events[key]
            if self.stopped or key in self.early:
                event.set()
            self.early.discard(key)
            return event

    def request_cancel(self, ident, sha):
        if not valid_id(ident) or not digest(sha):
            return False
        key = (ident, sha)
        with self.lock:
            if any(rid == ident and known != sha for rid, known in (*self.events, *self.finished, *self.early)):
                return False
            if key in self.events:
                self.events[key].set()
                return True
            if key in self.finished:
                return True
            if len(self.early) >= MAX_JOBS:
                return False
            self.early.add(key)
            return True

    def retire(self, ident, sha):
        key = (ident, sha)
        with self.lock:
            self.events.pop(key, None)
            self.early.discard(key)
            self.finished[key] = True
            while len(self.finished) > MAX_FINISHED:
                self.finished.popitem(last=False)

    def run(self, request, work):
        sha = command_hash(request)
        event = self.register(request['request_id'], sha)
        failure = None
        result = None
        try:
            if event.is_set():
                raise InterruptedError('Portrait crop read cancelled before start')
            result = work(event.is_set)
        except BaseException as error:
            failure = error
        # Observe cancellation under the same lock as ingress before retiring.
        with self.lock:
            cancelled = event.is_set() or self.stopped
            self.events.pop((request['request_id'], sha), None)
            self.early.discard((request['request_id'], sha))
            self.finished[(request['request_id'], sha)] = True
            while len(self.finished) > MAX_FINISHED:
                self.finished.popitem(last=False)
        if cancelled:
            raise InterruptedError('Portrait crop read actually unwound after cancellation')
        if failure is not None:
            raise failure
        return result

    def ingress(self, line):
        """Only an exact cancel packet is consumed. Apply is never cancellable."""
        if type(line) is not str or len(line) > MAX_COMMAND_BYTES or COMMAND not in line:
            return False
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            return False
        if type(value) is not dict:
            return False
        if value.get('cmd') == 'portrait_crop_cancel':
            return (set(value) == {'cmd', 'request_id', 'command_sha256'}
                    and self.request_cancel(value['request_id'], value['command_sha256']))
        if value.get('cmd') == COMMAND and value.get('action') in READS:
            # Dispatcher acknowledgement identity is removed by the serialized
            # server too; it is not part of the original operation's digest.
            value.pop('_host_request_id', None)
            try:
                self.register(value['request_id'], command_hash(value))
            except (ValueError, KeyError, TypeError):
                pass  # The serialized host emits the actual refusal.
        return False

    def stop(self):
        with self.lock:
            self.stopped = True
            for event in self.events.values():
                event.set()


def controller(engine):
    owner = engine.__dict__.get('_portrait_crop_jobs')
    if owner is None:
        owner = engine._portrait_crop_jobs = Jobs()
    return owner
