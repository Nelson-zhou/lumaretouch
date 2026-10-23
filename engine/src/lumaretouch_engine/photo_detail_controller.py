"""Transaction/receipt owner. Success requires frame and history commit, never just setting fields."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from typing import Callable
from . import photo_detail_state as S

@dataclass(frozen=True)
class Ports:
    guard: Callable[[], str | None]
    document: Callable[[], str]
    read: Callable[[], dict]
    commit: Callable[[dict], dict]
    revision: Callable[[], int] = lambda: 0

class PhotoDetailController:
    def __init__(self, ports, emit):
        self.ports, self.emit = ports, emit
        self.receipts = {}
        self.lock = RLock()

    def query(self, request_id):
        with self.lock:
            packet = self.receipts.get(request_id)
            return {'event': 'photo_detail_receipt', 'protocol': 1, 'request_id': request_id,
                    'phase': 'unknown' if packet is None else 'done',
                    'result': None if packet is None else deepcopy(packet[1])}

    def handle(self, request):
        with self.lock:
            return self._handle(request)

    def _handle(self, p):
        if type(p) is not dict: raise ValueError('Photo detail request must be an object')
        raw = json.dumps(p, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()
        if len(raw) > 8192: raise ValueError('Photo detail request exceeds 8 KiB')
        digest = sha256(raw).hexdigest()
        rid = p.get('request_id')
        doc = p.get('document_id')
        if type(rid) is not str or not 1 <= len(rid) <= 128 or type(doc) is not str or not 1 <= len(doc) <= 64: raise ValueError('Missing bounded request/document identity')
        if rid in self.receipts:
            old, result = self.receipts[rid]
            if old != digest: raise ValueError('Request ID already used with different data')
            self.emit(deepcopy(result)); return deepcopy(result)
        # Retain every admitted identity for this process lifetime; never silently replay an evicted request.
        if len(self.receipts) >= 4096: raise RuntimeError('Receipt capacity exhausted; reopen the engine before another edit')
        result = {'event': 'photo_detail_result', 'protocol': 1, 'request_id': rid,
                  'document_id': doc, 'success': False, 'outcome_unknown': False, 'requires_reload': False}
        try:
            if set(p) != {'cmd', 'request_id', 'document_id', 'revision', 'action', 'spec'} or p['cmd'] != 'photo_detail' or p['action'] not in ('set', 'reset'): raise ValueError('Invalid photo detail command fields')
            if p['action'] == 'reset' and p['spec'] is not None: raise ValueError('Reset requires null spec')
            spec = S.check(p['spec'])
            if p['action'] == 'set' and p['spec'] is None: raise ValueError('Set requires complete recipe')
            if self.ports.document() != doc: raise ValueError('Photo changed; edit was not submitted')
            if type(p['revision']) is not int or p['revision'] != self.ports.revision(): raise ValueError('编辑版本已变化，请读取当前细节后重试')
            why = self.ports.guard()
            if why: raise ValueError(why)
            before = S.check(self.ports.read())
            if spec == before:
                proof = {'no_change': True}
            else:
                try: proof = self.ports.commit(spec)
                except Exception as error:
                    result.update(outcome_unknown=bool(getattr(error, 'outcome_unknown', True)), requires_reload=bool(getattr(error, 'requires_reload', True)))
                    raise
            if self.ports.document() != doc or S.check(self.ports.read()) != spec:
                result.update(outcome_unknown=True, requires_reload=True)
                raise RuntimeError('Post-commit document/recipe proof mismatch')
            result.update(success=True, before=before, spec=spec, proof=proof)
        except Exception as error:
            result['error'] = str(error)[:2000]
        self.receipts[rid] = (digest, deepcopy(result))
        self.emit(deepcopy(result))
        return result
