"""Bounded recipe-only protocol; one pending preview, latest intent fencing.

Host serializes all render/state mutations on engine owner thread. Transport may
call invalidate() as soon as cancel/new intent is received to interrupt chunks.
No live state changes occur until commit of the exact shown preview.
"""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import Event, RLock
from . import colour_grading_state as S


@dataclass
class Ticket:
    epoch: int
    document: str
    revision: int
    request: str
    cancelled: Event


def ident(v):
    if not isinstance(v, str) or not 1 <= len(v) <= 128 or any(ord(c) < 32 for c in v):
        raise ValueError('Invalid colour grading request/document identity')
    return v


class ColourGradingController:
    def __init__(self, host):
        self.host = host
        self.lock = RLock()
        self.epoch = 0
        self.ticket = None
        self.pending = None
        self.receipts = OrderedDict()

    def invalidate(self):
        """Call on close/load/history/other edits and cancellation ingress."""
        with self.lock:
            self.epoch += 1
            if self.ticket is not None:
                self.ticket.cancelled.set()
            self.ticket = None
            self.pending = None

    def current(self, t):
        return not t.cancelled.is_set() and self.ticket is t and self.host.context() == (t.document, t.revision)

    def handle(self, p):
        # Limit before forwarding to any renderer; message has no image payload.
        if not isinstance(p, dict) or len(p) > 9:
            raise ValueError('Colour grading IPC exceeds bounds')
        action = p.get('action')
        base = {'cmd', 'action', 'request_id', 'document_id', 'revision'}
        extra = {'recipe'} if action == 'preview' else {'preview_id'} if action == 'commit' else set()
        if set(p) != base | extra or p.get('cmd') != 'colour_grading' or action not in ('preview', 'commit', 'cancel', 'status'):
            raise ValueError('Unknown colour grading message fields/action')
        rid, doc = ident(p['request_id']), ident(p['document_id'])
        if type(p['revision']) is not int or not 0 <= p['revision'] <= 9007199254740991:
            raise ValueError('Invalid colour grading revision')
        if action == 'preview':
            S.check(p['recipe'])
        if action == 'commit':
            ident(p['preview_id'])
        if len(json.dumps(p, allow_nan=False)) > 4096:
            raise ValueError('Colour grading IPC exceeds bounds')
        if action == 'status':
            old = self.receipts.get(rid)
            if old is not None and old['document_id'] == doc:
                return deepcopy(old)
            return {'event': 'colour_grading_result', 'request_id': rid, 'status': 'unknown'}
        if action == 'commit' and rid in self.receipts:
            old = self.receipts[rid]
            digest = sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
            if old['digest'] != digest:
                raise ValueError('Colour grading request ID reused with different content')
            return deepcopy(old)
        if self.host.context() != (doc, p['revision']):
            raise ValueError('Colour grading document or revision changed')
        if action == 'cancel':
            self.invalidate()
            return {'event': 'colour_grading_result', 'request_id': rid, 'status': 'cancelled', 'document_id': doc, 'frame': self.host.render_committed()}
        if action == 'preview':
            recipe = S.check(p['recipe'])
            self.invalidate()
            with self.lock:
                t = self.ticket = Ticket(self.epoch, doc, p['revision'], rid, Event())
            frame = self.host.render_preview(recipe, t.cancelled.is_set)
            with self.lock:
                if not self.current(t):
                    raise InterruptedError('Stale colour grading preview discarded')
                self.pending = (t, recipe)
                return {'event': 'colour_grading_preview', 'request_id': rid, 'document_id': doc,
                        'revision': t.revision, 'preview_id': rid, 'recipe': recipe, 'frame': frame}
        # Commit identity deduplicates retries; original successful receipt survives
        # newer context via status; callers must query, never blindly reissue.
        digest = sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if rid in self.receipts:
                old = self.receipts[rid]
                if old['digest'] != digest:
                    raise ValueError('Colour grading request ID reused with different content')
                return deepcopy(old)
            preview = ident(p['preview_id'])
            if self.pending is None or self.pending[0].request != preview or not self.current(self.pending[0]):
                raise ValueError('Commit needs the latest displayed colour grading preview')
            t, recipe = self.pending
            # Holds ingress lock for the final atomic install only, not rendering.
            try:
                result = self.host.commit(recipe, doc, t.revision)
                receipt = {'event': 'colour_grading_result', 'request_id': rid, 'document_id': doc,
                           'status': 'applied', 'digest': digest, **result}
            except Exception:
                # The host owns rollback and exposes whether reload is required.
                receipt = {'event': 'colour_grading_result', 'request_id': rid, 'document_id': doc,
                           'status': 'failed', 'digest': digest,
                           'requires_reload': bool(self.host.requires_reload)}
                self.receipts[rid] = receipt
                self.invalidate()
                while len(self.receipts) > 64:
                    self.receipts.popitem(last=False)
                raise
            self.receipts[rid] = receipt
            while len(self.receipts) > 64:
                self.receipts.popitem(last=False)
            self.invalidate()
            return deepcopy(receipt)
