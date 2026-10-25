# SPDX-License-Identifier: GPL-3.0-or-later
"""Reader-thread cancellation ingress only; all source and writes stay serialized.

A cancellation request sets an Event. Only the original operation's actual unwind
can report cancelled. Apply requests are never registered or cancelled here.
"""
from collections import OrderedDict
import hashlib
import json
import threading

READS = frozenset(('current','choose_donor','preview'))
MAX_JOBS = 64
MAX_FINISHED = 256


def valid_id(value):
    return type(value) is str and 1 <= len(value) <= 256 and not any(ord(c)<32 or ord(c)==127 for c in value)


def valid_hash(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def current_hash(request):
    if set(request)!={'cmd','action','request_id'} or request['cmd']!='expression_replacement' or request['action']!='current' or not valid_id(request['request_id']):
        raise ValueError('Malformed current-expression acquisition')
    return hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


class Jobs:
    def __init__(self):
        self.lock=threading.Lock()
        self.events={}
        self.early=set()
        self.finished=OrderedDict()
        self.stopped=False
        self.overflow=False

    def register(self, ident, digest):
        if not valid_id(ident) or not valid_hash(digest):raise ValueError('Invalid source-job identity')
        key=(ident,digest)
        with self.lock:
            if any(rid==ident and sha!=digest for rid,sha in (*self.events,*self.finished,*self.early)):
                raise ValueError('Expression job request identity reused with different content')
            if key in self.finished:return None
            if key not in self.events:
                if len(self.events)>=MAX_JOBS:
                    self.overflow=True
                    for event in self.events.values():event.set()
                    raise ValueError('Expression source-job capacity exceeded; finish outstanding requests')
                self.events[key]=threading.Event()
            if key in self.early or self.stopped or self.overflow:self.events[key].set()
            self.early.discard(key)
            return self.events[key]

    def request_cancel(self, ident, digest):
        if not valid_id(ident) or not valid_hash(digest):return
        key=(ident,digest)
        with self.lock:
            event=self.events.get(key)
            if event is not None:event.set()
            elif key not in self.finished:
                if len(self.early)<MAX_JOBS:self.early.add(key)
                else:
                    self.overflow=True
                    for event in self.events.values():event.set()

    def finish(self, ident, digest, event):
        key=(ident,digest)
        with self.lock:
            cancelled=event.is_set() or self.stopped or self.overflow
            self.events.pop(key,None);self.early.discard(key)
            self.finished[key]=True
            while len(self.finished)>MAX_FINISHED:self.finished.popitem(last=False)
            return cancelled

    def run(self, ident, digest, method):
        event=self.register(ident,digest)
        if event is None:raise ValueError('Completed expression source job cannot be restarted')
        failure=None;result=None
        try:
            if event.is_set():raise InterruptedError('Expression source operation cancelled before start')
            result=method(event.is_set)
        except BaseException as error:failure=error
        cancelled=self.finish(ident,digest,event)
        if cancelled:raise InterruptedError('Expression source operation actually unwound after cancellation')
        if failure is not None:raise failure
        return result

    def retire(self,ident,digest):
        """Retire a reader registration rejected before source work began."""
        key=(ident,digest)
        with self.lock:
            self.events.pop(key,None);self.early.discard(key)
            self.finished[key]=True
            while len(self.finished)>MAX_FINISHED:self.finished.popitem(last=False)

    def ingress(self,line):
        if type(line) is not str or len(line)>600_000 or 'expression_replacement' not in line:return False
        try:value=json.loads(line)
        except (ValueError,TypeError):return False
        if type(value) is not dict:return False
        if value.get('cmd')=='expression_replacement_cancel':
            if set(value)=={'cmd','request_id','command_sha256'}:
                self.request_cancel(value['request_id'],value['command_sha256'])
                return True
            return False
        if value.get('cmd')!='expression_replacement' or value.get('action') not in READS:return False
        try:
            digest=current_hash(value) if value['action']=='current' else value['packet']['command_sha256']
            self.register(value['request_id'],digest)
        except (ValueError,KeyError,TypeError):pass  # Serialized host reports admission failure.
        return False

    def stop(self):
        with self.lock:
            self.stopped=True
            for event in self.events.values():event.set()


def controller(engine):
    current=engine.__dict__.get('_expression_source_jobs')
    return current if current is not None else engine.__dict__.setdefault('_expression_source_jobs',Jobs())
