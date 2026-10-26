"""One-shot WB actions with terminal, post-history receipts and bounded replay."""
import json
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
from hashlib import sha256

PROOF_KEYS = ("capture_id", "ticket", "generation", "recipe_document_id", "recipe_revision")
AUTO_KEYS = ('input_id', 'recipe_document_id', 'recipe_revision')
from . import white_balance_recipe as W


@dataclass(frozen=True)
class WhiteBalancePorts:
    guard: Callable[[], str | None]
    document_id: Callable[[], str]
    status: Callable[[], dict]
    apply: Callable[[dict], object]
    needs_reload: Callable[[], bool]
    prepare_pick: Callable[[dict], dict] | None = None
    prepare_auto: Callable[[dict], dict] | None = None
    apply_auto: Callable[[dict], object] | None = None
    auto_outcome: Callable[[], str] | None = None
    settle_auto: Callable[[str], None] | None = None
    verify_auto: Callable[[str], None] | None = None


def identity(value, limit):
    if type(value) is not str or not value:
        return None
    try:
        return value if len(value.encode('utf-8')) <= limit else None
    except UnicodeError:
        return None


def error_text(value):
    return str(value).encode('utf-8', errors='replace').decode('utf-8')[:1500]


class WhiteBalanceController:
    def __init__(self, ports, emit):
        self.ports, self.emit = ports, emit
        self.pending = None
        self.cache = OrderedDict()
        self.prepared_pick = None
        self.prepared_auto = None

    @staticmethod
    def fingerprint(p):
        raw = json.dumps(p, sort_keys=True, allow_nan=False).encode('utf-8')
        if len(raw) > 8192:
            raise ValueError('WB action exceeds its bounded request size')
        return sha256(raw).hexdigest()

    def prepare(self, p):
        """Pick scalar calculation/proof redemption happens before mutation fencing."""
        self.prepared_pick = None
        self.prepared_auto = None
        if p.get('action') == 'auto':
            return self._prepare_auto(p)
        if p.get('action') != 'pick':
            return True
        result = {'event':'white_balance_result','protocol':1,'request_id':identity(p.get('request_id'),128),
                  'document_id':identity(p.get('document_id'),64),'action':'pick',
                  **{key:identity(p.get(key),128) for key in PROOF_KEYS},
                  'success':False,'outcome_unknown':False,'requires_reload':False,'error':None}
        fingerprint = None
        self.pending = (fingerprint, result)
        try:
            fingerprint = self.fingerprint(p)
            self.pending = (fingerprint, result)
            if set(p) != {'cmd','request_id','document_id','action','region',*PROOF_KEYS} or p.get('cmd') != 'white_balance':
                raise ValueError('Invalid WB pick fields')
            if result['request_id'] is None or result['document_id'] is None or any(result[key] is None for key in PROOF_KEYS):
                raise ValueError('Invalid WB pick identity')
            if p['request_id'] in self.cache:
                old, cached = self.cache[p['request_id']]
                if old != fingerprint:
                    raise ValueError('White-balance request ID was reused with different parameters')
                self.pending = (fingerprint, {**deepcopy(cached),'replayed':True})
                return False
            if p['document_id'] != self.ports.document_id():
                raise ValueError('Photo changed; WB pick was not applied')
            why = self.ports.guard()
            if why:
                raise ValueError(why)
            if self.ports.prepare_pick is None:
                raise ValueError('WB input capture is unavailable')
            proof = self.ports.prepare_pick(p)
            if any(proof.get(key) != p[key] for key in ('document_id',*PROOF_KEYS)):
                raise ValueError('WB input proof does not match this action')
            gains = W.check_options({**self.ports.status()['exposure']['options'],'picked_gains':proof['gains']})['picked_gains']
            self.prepared_pick = (fingerprint, deepcopy(gains))
            return True
        except Exception as error:
            result['error'] = error_text(error)
            self.emit({'event':'error','error':result['error']})
            return False

    def _prepare_auto(self, p):
        result = {'event': 'white_balance_result', 'protocol': 1,
                  'request_id': identity(p.get('request_id'), 128), 'document_id': identity(p.get('document_id'), 64),
                  'action': 'auto', 'success': False, 'outcome_unknown': False, 'requires_reload': False,
                  'phase': 'rejected', 'no_write': True, 'error': None}
        self.pending = (None, result)
        try:
            fingerprint = self.fingerprint(p)
            result['original_request'] = deepcopy(p)
            self.pending = (fingerprint, result)
            if set(p) != {'cmd', 'request_id', 'document_id', 'action', *AUTO_KEYS} or p.get('cmd') != 'white_balance':
                raise ValueError('Invalid auto white-balance fields; gains cannot be supplied by the UI')
            if result['request_id'] is None or result['document_id'] is None or any(identity(p.get(k), 128) is None for k in AUTO_KEYS):
                raise ValueError('Invalid auto white-balance identity')
            if p['request_id'] in self.cache:
                old, cached = self.cache[p['request_id']]
                if old != fingerprint:
                    raise ValueError('White-balance request ID was reused with different parameters')
                self.pending = (fingerprint, {**deepcopy(cached), 'replayed': True})
                return False
            if p['document_id'] != self.ports.document_id():
                raise ValueError('Photo changed; auto white balance was not applied')
            why = self.ports.guard()
            if why:
                raise ValueError(why)
            if self.ports.prepare_auto is None or self.ports.apply_auto is None:
                raise ValueError('Auto white-balance sampling is unavailable')
            status = self.ports.status()
            before = deepcopy(status['exposure'])
            history = {k: status['history'][k] for k in ('undo_steps', 'redo_steps')}
            history_limit = status['history']['history_max']
            if type(history_limit) is not int or history_limit < 1:
                raise ValueError('Auto WB history limit is unavailable')
            proof = self.ports.prepare_auto(p)
            if any(proof.get(k) != p[k] for k in AUTO_KEYS):
                raise ValueError('Auto white-balance input identity changed')
            options = W.check_options({**before['options'], 'picked_gains': proof['gains']})
            if self.ports.status()['exposure'] != before:
                raise ValueError('White-balance controls changed while sampling')
            result['diagnostic'] = deepcopy(proof['diagnostic'])
            if options == before['options']:
                result.update(success=True, before=before, before_history=history, history_limit=history_limit, no_change=True, phase='no_change')
                return False  # No generic fence/history or autosave revision for a no-op.
            self.prepared_auto = (fingerprint, options, before, deepcopy(proof['diagnostic']), history, history_limit)
            return True
        except Exception as error:
            result['error'] = error_text(error)
            self.emit({'event': 'error', 'error': result['error']})
            return False

    def handle(self, p):
        result = {'event':'white_balance_result','protocol':1,'request_id':identity(p.get('request_id'),128),
                  'document_id':identity(p.get('document_id'),64),'action':identity(p.get('action'),32),
                  'success':False,'outcome_unknown':False,'requires_reload':False,'error':None}
        if p.get('action') == 'pick':
            result.update({key:identity(p.get(key),128) for key in PROOF_KEYS})
        if p.get('action') == 'auto':
            result.update(original_request=deepcopy(p), phase='rejected', no_write=True)
        self.pending = (None, result)
        try:
            self.pending = (self.fingerprint(p), result)
            rid, doc, action = p.get('request_id'), p.get('document_id'), p.get('action')
            if identity(rid,128) is None:
                raise ValueError('Invalid white-balance request ID')
            if identity(doc,64) is None:
                raise ValueError('Invalid white-balance document ID')
            allowed = {'cmd','request_id','document_id','action'} | ({'algorithm'} if action=='set_algorithm' else ({'region',*PROOF_KEYS} if action=='pick' else (set(AUTO_KEYS) if action=='auto' else set())))
            if p.get('cmd')!='white_balance' or set(p)-allowed or action not in ('set_algorithm','reset','pick','clear_pick','auto'):
                raise ValueError('Invalid white-balance action or fields')
            if rid in self.cache:
                fingerprint, cached = self.cache[rid]
                if fingerprint != self.fingerprint(p):
                    raise ValueError('White-balance request ID was reused with different parameters')
                self.pending = (self.fingerprint(p), {**deepcopy(cached), 'replayed':True})
                return
            if doc != self.ports.document_id():
                raise ValueError('Photo changed; white-balance action was not applied')
            why = self.ports.guard()
            if why:
                raise ValueError(why)
            before = deepcopy(self.ports.status()['exposure'])
            options = W.check_options(before['options'])
            patch = {'action':'set'}
            if action == 'auto':
                prepared, self.prepared_auto = self.prepared_auto, None
                if prepared is None or prepared[0] != self.fingerprint(p) or prepared[2] != before:
                    raise ValueError('Auto white balance must be prepared from this exact input before the mutation fence')
                options = prepared[1]
                result['diagnostic'] = prepared[3]
                result.update(before=before, before_history=prepared[4], history_limit=prepared[5])
                no_change = options == before['options']
            elif action == 'set_algorithm':
                options['algorithm'] = p.get('algorithm')
                options = W.check_options(options)
                no_change = options == before['options']
            elif action in ('pick','clear_pick'):
                if action == 'pick':
                    prepared, self.prepared_pick = self.prepared_pick, None
                    if prepared is None or prepared[0] != self.fingerprint(p):
                        raise ValueError('WB pick must be prepared before the mutation fence')
                    options['picked_gains'] = prepared[1]
                else:
                    options['picked_gains'] = [1.0,1.0,1.0]
                no_change = options == before['options']
            else:
                options['picked_gains'] = [1.0,1.0,1.0]
                patch.update(temperature_shift=0.0,tint_shift=0.0)
                no_change = (options==before['options'] and before['temperature_shift']==0 and before['tint_shift']==0)
            patch['wb_options'] = options
            try:
                applied = True if no_change else (self.ports.apply_auto(patch) if action == 'auto' else self.ports.apply(patch))
            except Exception:
                result['outcome_unknown'] = True
                result['requires_reload'] = self.ports.needs_reload()
                raise
            if applied is not True:
                result['requires_reload'] = self.ports.needs_reload()
                result['outcome_unknown'] = result['requires_reload']
                if action == 'auto':
                    phase = self.ports.auto_outcome() if self.ports.auto_outcome else 'unknown'
                    result['phase'] = 'rejected' if phase == 'no_write' else phase
                    result['outcome_unknown'] = phase not in ('no_write', 'rolled_back')
                    result['requires_reload'] = result['outcome_unknown']
                    result['no_write'] = not result['outcome_unknown']
                raise ValueError('White-balance action did not commit; the exposure transaction reported failure')
            result.update(success=True,before=before,no_change=no_change)
            if action == 'auto':
                result.update(phase='no_change' if no_change else 'applied', no_write=no_change)
        except Exception as error:
            result['error'] = error_text(error)
            self.emit({'event':'error','error':result['error']})

    def finish(self, p, dispatch_error=None):
        pending = self.pending
        self.pending = None
        if pending is None:
            result = {'event':'white_balance_result','protocol':1,'request_id':identity(p.get('request_id'),128),
                      'document_id':identity(p.get('document_id'),64),'action':identity(p.get('action'),32),
                      'success':False,'outcome_unknown':True,'requires_reload':self.ports.needs_reload(),
                      'error':dispatch_error or 'White-balance action produced no outcome'}
        else:
            _, result = pending
        if p.get("action") == "pick":
            result.update({key:identity(p.get(key),128) for key in PROOF_KEYS})
        self.prepared_pick = None
        self.prepared_auto = None
        if dispatch_error:
            result.update(success=False,outcome_unknown=True,error=error_text(dispatch_error))
        if (result.get('success') or (p.get('action') == 'auto' and result.get('phase') == 'rolled_back')) and not result.get('replayed'):
            try:
                status = self.ports.status()
                if status['document_id'] != result['document_id']:
                    raise ValueError('Document changed before white-balance receipt')
                result['after'] = deepcopy(status['exposure'])
                result['history'] = {k:status['history'][k] for k in ('undo_steps','redo_steps')}
                if p.get('action') == 'auto' and self.ports.verify_auto:
                    self.ports.verify_auto(result['phase'])
            except Exception as error:
                result.update(success=False,outcome_unknown=True,error=error_text(error))
        if p.get('action') == 'auto':
            if result.get('outcome_unknown'):
                result.update(phase='unknown', no_write=False, requires_reload=True)
        rid = result.get('request_id')
        try:
            bounded = len(json.dumps(result, allow_nan=False).encode('utf-8')) <= 16384
        except (ValueError, TypeError, UnicodeError):
            bounded = False
        if not bounded:
            result = {k:result.get(k) for k in ('event','protocol','request_id','document_id','action',*PROOF_KEYS)}
            result.update(success=False,outcome_unknown=True,requires_reload=True,error='WB receipt exceeded its validated bound')
        if p.get('action') == 'auto' and self.ports.settle_auto:
            self.ports.settle_auto('unknown' if result.get('outcome_unknown') else ('replayed' if result.get('replayed') else result.get('phase', 'unknown')))
        fingerprint = pending[0] if pending is not None else None
        if fingerprint is not None and identity(rid,128) and identity(result.get('document_id'),64) and result.get('action') in ('set_algorithm','reset','pick','clear_pick','auto') and rid not in self.cache:
            self.cache[rid] = (fingerprint, deepcopy(result))
            while len(self.cache)>64:
                self.cache.popitem(last=False)
        self.emit(result)


def get_controller(engine, emit):
    owner = engine.__dict__.get('_white_balance_owner')
    if owner is None:
        from .white_balance_capture import WhiteBalanceCapture
        from .white_balance_auto import AutomaticWhiteBalance
        capture = WhiteBalanceCapture(engine, emit)
        automatic = AutomaticWhiteBalance(engine)
        owner = WhiteBalanceController(WhiteBalancePorts(
            guard=lambda:engine._guard_editable('white balance'),
            document_id=lambda:engine._load_id, status=lambda:engine.doc_state(),
            apply=lambda patch:engine.cmd_exposure(patch, preserve_reference=True),
            needs_reload=lambda:engine._vram is None, prepare_pick=capture.prepare_apply,
            prepare_auto=automatic.prepare, apply_auto=automatic.apply,
            auto_outcome=lambda:automatic.transaction['phase'], settle_auto=automatic.settle,
            verify_auto=automatic.verify), emit)
        owner.capture = capture
        engine._white_balance_owner = owner
    return owner
