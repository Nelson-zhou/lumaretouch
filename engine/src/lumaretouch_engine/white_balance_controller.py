"""One-shot WB actions with terminal, post-history receipts and bounded replay."""
import json
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
from . import white_balance_recipe as W


@dataclass(frozen=True)
class WhiteBalancePorts:
    guard: Callable[[], str | None]
    document_id: Callable[[], str]
    status: Callable[[], dict]
    apply: Callable[[dict], object]
    needs_reload: Callable[[], bool]


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

    @staticmethod
    def fingerprint(p):
        return tuple(identity(p.get(key),128) for key in ('action','document_id','algorithm'))

    def handle(self, p):
        result = {'event':'white_balance_result','protocol':1,'request_id':identity(p.get('request_id'),128),
                  'document_id':identity(p.get('document_id'),64),'action':identity(p.get('action'),32),
                  'success':False,'outcome_unknown':False,'requires_reload':False,'error':None}
        self.pending = (self.fingerprint(p), result)
        try:
            rid, doc, action = p.get('request_id'), p.get('document_id'), p.get('action')
            if identity(rid,128) is None:
                raise ValueError('Invalid white-balance request ID')
            if identity(doc,64) is None:
                raise ValueError('Invalid white-balance document ID')
            allowed = {'cmd','request_id','document_id','action'} | ({'algorithm'} if action=='set_algorithm' else set())
            if p.get('cmd')!='white_balance' or set(p)-allowed or action not in ('set_algorithm','reset'):
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
            if action == 'set_algorithm':
                options['algorithm'] = p.get('algorithm')
                options = W.check_options(options)
                no_change = options == before['options']
            else:
                options['picked_gains'] = [1.0,1.0,1.0]
                patch.update(temperature_shift=0.0,tint_shift=0.0)
                no_change = (options==before['options'] and before['temperature_shift']==0 and before['tint_shift']==0)
            patch['wb_options'] = options
            try:
                applied = True if no_change else self.ports.apply(patch)
            except Exception:
                result['outcome_unknown'] = True
                result['requires_reload'] = self.ports.needs_reload()
                raise
            if applied is not True:
                result['requires_reload'] = self.ports.needs_reload()
                result['outcome_unknown'] = result['requires_reload']
                raise ValueError('White-balance action did not commit; the exposure transaction reported failure')
            result.update(success=True,before=before,no_change=no_change)
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
        if dispatch_error:
            result.update(success=False,outcome_unknown=True,error=error_text(dispatch_error))
        if result.get('success') and not result.get('replayed'):
            try:
                status = self.ports.status()
                if status['document_id'] != result['document_id']:
                    raise ValueError('Document changed before white-balance receipt')
                result['after'] = deepcopy(status['exposure'])
                result['history'] = {k:status['history'][k] for k in ('undo_steps','redo_steps')}
            except Exception as error:
                result.update(success=False,outcome_unknown=True,error=error_text(error))
        rid = result.get('request_id')
        try:
            bounded = len(json.dumps(result, allow_nan=False).encode('utf-8')) <= 16384
        except (ValueError, TypeError, UnicodeError):
            bounded = False
        if not bounded:
            result = {k:result.get(k) for k in ('event','protocol','request_id','document_id','action')}
            result.update(success=False,outcome_unknown=True,requires_reload=True,error='WB receipt exceeded its validated bound')
        if identity(rid,128) and identity(result.get('document_id'),64) and result.get('action') in ('set_algorithm','reset') and rid not in self.cache:
            self.cache[rid] = (self.fingerprint(p), deepcopy(result))
            while len(self.cache)>64:
                self.cache.popitem(last=False)
        self.emit(result)
