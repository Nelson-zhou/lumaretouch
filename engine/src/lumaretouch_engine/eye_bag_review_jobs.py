# SPDX-License-Identifier: GPL-3.0-or-later
"""Cancellation-only reader ingress; all image and graph work stays serialized.

AUTHORED / UNRUN. Setting an Event requests cancellation, never certifies stop.
Only the original read's unwind emits a terminal cancelled receipt. Confirmations
are deliberately absent and can never be canceled through this owner.
"""
from collections import OrderedDict
import json
import threading

READS = frozenset(('eye_bag_reference', 'eye_bag_source_image', 'eye_bag_preview', 'eye_bag_image'))
MAX_RECORDS = 128


class Cancelled(InterruptedError):
    pass


def valid_id(value):
    return type(value) is str and 0 < len(value) <= 128 and '\0' not in value


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = {}
        self.early = set()
        self.finished = OrderedDict()
        self.stopped = False
        self.overflow = False

    def ingress(self, line):
        if type(line) is not str or len(line) > 270000 or 'eye_bag' not in line:
            return False
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            return False
        if type(value) is not dict or not valid_id(value.get('request_id')):
            return False
        ident = value['request_id']
        if value.get('cmd') == 'eye_bag_cancel' and set(value) == {'cmd', 'request_id'}:
            with self.lock:
                event = self.events.get(ident)
                if event is not None:
                    event.set()
                elif ident not in self.finished:
                    if len(self.early) < MAX_RECORDS:
                        self.early.add(ident)
                    else:
                        self.overflow = True
                        for pending in self.events.values(): pending.set()
            return True
        # Registration never consumes the actual command or touches engine state.
        if value.get('cmd') == 'people' and value.get('action') in READS:
            try: self.register(ident)
            except ValueError: pass  # Main thread reports bounded admission refusal.
        return False

    def register(self, ident):
        if not valid_id(ident): raise ValueError('Invalid eye-bag read request identity')
        with self.lock:
            if ident in self.finished: return
            if ident not in self.events:
                if len(self.events) >= MAX_RECORDS:
                    self.overflow = True
                    for pending in self.events.values(): pending.set()
                    raise ValueError('Eye-bag read cancellation capacity exhausted; restart safely')
                self.events[ident] = threading.Event()
            if ident in self.early or self.stopped or self.overflow:
                self.events[ident].set()
            self.early.discard(ident)

    def begin(self, ident):
        self.register(ident)
        with self.lock:
            event = self.events.get(ident)
            if event is None: raise ValueError('Completed eye-bag read cannot be restarted')
            return event

    def complete(self, ident, event):
        """Linearize completion against cancellation on the same lock."""
        with self.lock:
            cancelled = event.is_set() or self.stopped or self.overflow
            self.events.pop(ident, None)
            self.early.discard(ident)
            self.finished[ident] = True
            while len(self.finished) > MAX_RECORDS: self.finished.popitem(last=False)
            return cancelled

    def retire(self, ident):
        """Release registrations for requests rejected before the read begins."""
        with self.lock:
            self.events.pop(ident, None)
            self.early.discard(ident)
            self.finished[ident] = True
            while len(self.finished) > MAX_RECORDS: self.finished.popitem(last=False)

    def stop(self):
        with self.lock:
            self.stopped = True
            for event in self.events.values(): event.set()


def controller(engine):
    # Initialize from engine setup/ingress before concurrent use. setdefault is
    # atomic under the Python interpreter; only the retained owner is returned.
    retained = engine.__dict__.get('_eye_bag_read_jobs')
    return retained if retained is not None else engine.__dict__.setdefault('_eye_bag_read_jobs', Jobs())


def cancelled(engine):
    callback = engine.__dict__.get('_eye_bag_read_cancelled')
    return bool(callback and callback())


def checkpoint(engine):
    if cancelled(engine): raise Cancelled('Eye-bag read cancelled; no candidate was applied')


def release_private(engine):
    """Invalidate unpublished review authority, never committed support/history."""
    engine._eye_bag_reference = None
    store = engine.__dict__.pop('_eye_bag_reviews', None)
    if store is not None:
        store['pending'].clear()
        store['images'].prune({})


def run(engine, request, method, state, target, payload):
    jobs = controller(engine); event = jobs.begin(request)
    engine._eye_bag_read_cancelled = event.is_set
    failed = None; result = None
    try:
        checkpoint(engine)
        result = method(engine, state, target, payload)
        checkpoint(engine)
    except Exception as error:
        failed = error
    finally:
        engine.__dict__.pop('_eye_bag_read_cancelled', None)
        was_cancelled = jobs.complete(request, event)
    if was_cancelled:
        try: release_private(engine)
        finally: raise Cancelled('Eye-bag read stopped after cancellation; no candidate was applied')
    if failed is not None: raise failed
    return result
