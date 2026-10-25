# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only selection cancellation ingress. AUTHORED / UNRUN.

The reader only registers/set Events. It never changes creative documents,
candidate masks, receipts or history. Apply is deliberately non-cancellable.
Cancellation is not a success receipt; the original operation must unwind.
"""
from collections import OrderedDict
import json
import threading
from .creative_selection_recipe import sha, valid_id

READS = frozenset(('context', 'preview'))
MAX_JOBS = 32
MAX_FINISHED = 256


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = {}
        self.early = set()
        self.finished = OrderedDict()
        self.stopped = False
        self.overflow = False

    def register(self, request):
        rid, source = request.get('request_id'), request.get('source_uid')
        if request.get('action') not in READS or not valid_id(rid) or not valid_id(source):
            raise ValueError('Invalid selection read-job identity')
        digest = sha(request)
        key = (source, rid)
        with self.lock:
            old = self.events.get(key)
            done = self.finished.get(key)
            if (old and old[0] != digest) or (done and done != digest):
                raise ValueError('Selection request identity reused with different content')
            if done:
                raise ValueError('Completed selection read cannot be restarted')
            if old:
                return old[1]
            if len(self.events) >= MAX_JOBS:
                self.overflow = True
                for _, event in self.events.values():
                    event.set()
                raise ValueError('Selection read queue capacity exceeded')
            event = threading.Event()
            if key in self.early or self.stopped or self.overflow:
                event.set()
            self.early.discard(key)
            self.events[key] = (digest, event)
            return event

    def request_cancel(self, source, target):
        if not _valid_pair(source, target):
            return False
        with self.lock:
            key = (source, target)
            item = self.events.get(key)
            if item is not None:
                item[1].set()
                return True
            if key not in self.finished:
                if len(self.early) < MAX_JOBS:
                    self.early.add(key)
                else:
                    self.overflow = True
                    for _, event in self.events.values():
                        event.set()
                return True
            return False

    def retire(self, request):
        if request.get('action') not in READS:
            return
        key = (request.get('source_uid'), request.get('request_id'))
        with self.lock:
            item = self.events.pop(key, None)
            self.early.discard(key)
            self.finished[key] = item[0] if item is not None else sha(request)
            while len(self.finished) > MAX_FINISHED:
                self.finished.popitem(last=False)

    def run(self, request, work):
        event = self.register(request)
        try:
            if event.is_set():
                raise InterruptedError('Selection read cancelled before work began')
            result = work(event.is_set)
            if event.is_set():
                raise InterruptedError('Selection read actually unwound after cancellation')
            return result
        finally:
            self.retire(request)

    def ingress(self, line):
        if type(line) is not str or len(line) > 8_000_000 or 'creative_selection' not in line:
            return False
        try:
            request = json.loads(line)
            if type(request) is not dict or request.get('cmd') != 'creative_selection':
                return False
            # The native dispatcher adds this transport-only key. The serialized
            # Python handler removes it before hashing the identical command.
            request.pop('_host_request_id', None)
            if request.get('action') in READS:
                self.register(request)
            elif request.get('action') == 'cancel':
                if (set(request) <= {'cmd', 'action', 'request_id', 'source_uid', 'target_request_id', 'preview_token'}
                        and all(valid_id(request.get(k)) for k in ('request_id', 'source_uid', 'target_request_id'))):
                    self.request_cancel(request['source_uid'], request['target_request_id'])
        except (ValueError, TypeError, KeyError, OverflowError):
            pass  # Serialized host owns validation and the exact terminal receipt.
        return False  # Cancellation still gets a serialized, source-bound receipt.

    def stop(self):
        with self.lock:
            self.stopped = True
            for _, event in self.events.values():
                event.set()


def controller(engine):
    current = engine.__dict__.get('_creative_selection_jobs')
    return current if current is not None else engine.__dict__.setdefault('_creative_selection_jobs', Jobs())


def _valid_pair(source, target):
    return valid_id(source) and valid_id(target)
