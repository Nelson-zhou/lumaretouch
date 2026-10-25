# SPDX-License-Identifier: GPL-3.0-or-later
"""Serialized catalogue host; reader ingress is cancellation metadata only."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
import re
import threading
from . import background_material_state as S
from .background_material_command import dispatch, error_payload

MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_RETAINED_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 128


def request_id(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is None:
        S.fail('背景素材请求身份无效')
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


class BackgroundMaterialHost:
    def __init__(self):
        self.lock = threading.Lock(); self.events = {}; self.early_cancel = set()
        self.results = OrderedDict(); self.retained_bytes = 0
        self.stopped = False; self.control_overflow = False

    def register(self, ident):
        ident = request_id(ident)
        with self.lock:
            event = self.events.get(ident)
            if event is None:
                if len(self.events) >= MAX_RECORDS: S.fail('背景素材队列已满，请等待', 'busy')
                event = threading.Event()
                if self.stopped or self.control_overflow or ident in self.early_cancel: event.set()
                self.early_cancel.discard(ident); self.events[ident] = event
            return event

    def cancel(self, ident):
        ident = request_id(ident)
        with self.lock:
            event = self.events.get(ident)
            if event is not None: event.set()
            elif ident not in self.results:
                if len(self.early_cancel) < MAX_RECORDS: self.early_cancel.add(ident)
                else:
                    # Bounded control admission fails closed, never drops a cancel
                    # which may have overtaken an as-yet-unregistered command.
                    self.control_overflow = True
                    for event in self.events.values(): event.set()

    def stop(self):
        with self.lock:
            self.stopped = True
            for event in self.events.values(): event.set()

    def observe_line(self, line):
        if type(line) is not str or 'background_material_library' not in line: return False
        try:
            if len(line.encode('utf-8')) > MAX_REQUEST_BYTES: return False
            message = json.loads(line)
            if type(message) is not dict: return False
            if message.get('cmd') == 'background_material_library_cancel':
                if set(message) != {'cmd', 'request_id'}: return False
                self.cancel(message['request_id']); return True
            if message.get('cmd') == 'background_material_library':
                self.register(message.get('request_id'))
        except (ValueError, TypeError, UnicodeError):
            # Normal command handling emits the rejection. Reader never accesses
            # catalogue/source pixels, and never performs a requested mutation.
            return False
        return False

    def dispatch_rejected(self, message, error, started, emit):
        """Settle an outer-guard refusal without entering the catalogue command.

        A matching retained result outranks the new guard error. If entry already
        occurred and no authoritative result exists, no rollback is inferred.
        """
        if type(message) is not dict or message.get('cmd') != 'background_material_library': return
        try:
            ident = request_id(message.get('request_id'))
            raw = encoded(message)
            if len(raw) > MAX_REQUEST_BYTES: return
            signature = sha256(raw).hexdigest()
        except (ValueError, TypeError, UnicodeError): return
        unknown = bool(started)
        terminal = {'event': 'background_material_result', 'protocol': 1,
                    'request_id': ident, 'action': 'request', 'success': False,
                    'outcome_unknown': unknown, 'committed': None if unknown else False,
                    'error': str(error)[:1000],
                    'error_code': 'dispatch_unknown' if unknown else 'dispatch_rejected'}
        with self.lock:
            previous = self.results.get(ident)
            if previous is not None:
                if previous[0] == signature:
                    terminal = deepcopy(previous[1])
                else:
                    # Do not replace the original request's retained authority.
                    terminal.update(error='背景请求身份冲突；原请求回执已保留', error_code='request_conflict')
            else:
                size = len(encoded(terminal))
                while self.results and (len(self.results) >= MAX_RECORDS or self.retained_bytes + size > MAX_RETAINED_BYTES):
                    _, old = self.results.popitem(last=False); self.retained_bytes -= old[2]
                self.results[ident] = (signature, deepcopy(terminal), size)
                self.retained_bytes += size
            # Rejections are terminal too: queued ingress registration must not
            # accumulate until unrelated future requests hit MAX_RECORDS.
            self.events.pop(ident, None); self.early_cancel.discard(ident)
        emit(terminal)

    def handle(self, engine, message, emit):
        ident = message.get('request_id') if type(message) is dict else None
        terminal = {'event': 'background_material_result', 'protocol': 1,
                    'request_id': ident if type(ident) is str and len(ident) <= 128 else None,
                    'action': 'request'}
        signature = None; applied = False
        try:
            ident = request_id(ident)
            if (type(message) is not dict or set(message) != {'cmd', 'action', 'request_id', 'request'}
                    or message['cmd'] != 'background_material_library' or message['action'] != 'request'):
                S.fail('背景素材命令字段无效')
            raw = encoded(message)
            if len(raw) > MAX_REQUEST_BYTES: S.fail('背景素材请求超过传输预算', 'capacity')
            signature = sha256(raw).hexdigest()
            with self.lock:
                previous = self.results.get(ident)
                if previous is not None and previous[0] != signature:
                    signature = None
                    S.fail('背景请求身份不能复用不同内容', 'request_conflict')
                if previous is not None: self.events.pop(ident, None)
            if previous is not None:
                terminal = previous[1]
            else:
                stop = self.register(ident)
                S.cancelled(stop.is_set)
                result = dispatch(engine, message['request'], cancelled=stop.is_set)
                applied = message['request']['method'] == 'command' and result['changed']
                # Never check cancellation after dispatch: a durable write remains
                # a success even when a cancel arrives just after publication.
                terminal.update(success=True, outcome_unknown=False, committed=bool(applied), result=result)
                if len(encoded(terminal)) > MAX_RESULT_BYTES:
                    S.fail('背景操作已结束但回执超过预算，请查询并核对目录，勿重复提交',
                           'receipt_capacity', outcome_unknown=bool(applied), committed=bool(applied))
        except Exception as error:
            terminal.pop('result', None); detail = error_payload(error)
            terminal.update(success=False, error=detail['message'], error_code=detail['code'],
                            outcome_unknown=bool(applied) or detail['outcome_unknown'],
                            committed=True if applied else detail['committed'])
        if signature is not None:
            size = len(encoded(terminal))
            with self.lock:
                old = self.results.pop(ident, None)
                if old is not None: self.retained_bytes -= old[2]
                while self.results and (len(self.results) >= MAX_RECORDS or self.retained_bytes + size > MAX_RETAINED_BYTES):
                    _, old = self.results.popitem(last=False); self.retained_bytes -= old[2]
                self.results[ident] = (signature, terminal, size); self.retained_bytes += size
                self.events.pop(ident, None)
        elif type(ident) is str:
            with self.lock: self.events.pop(ident, None)
        emit(terminal)


def dispatch_rejected(engine, message, error, started, emit):
    """Shared server finally hook. This never calls handle() or dispatch()."""
    BackgroundMaterialHostMixin._background_material_host(engine).dispatch_rejected(
        message, error, started, emit)


class BackgroundMaterialHostMixin:
    def _background_material_host(self):
        owner = self.__dict__.get('_background_material_protocol')
        if owner is None:
            owner = BackgroundMaterialHost(); self._background_material_protocol = owner
        return owner

    def cmd_background_material_library(self, message):
        from .server import emit
        self._background_material_host().handle(self, message, emit)

    def cmd_background_material_library_cancel(self, message):
        S.fields(message, ('cmd', 'request_id'))
        if message['cmd'] != 'background_material_library_cancel': S.fail('背景取消命令无效')
        self._background_material_host().cancel(message['request_id'])
