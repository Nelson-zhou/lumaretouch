# SPDX-License-Identifier: GPL-3.0-or-later
"""Serialized library commands with an out-of-band cancellation-only ingress.

Reader-thread work is limited to validating control metadata and setting Events.
No catalogue, editor, source image, inference, or renderer is touched there.
"""
from collections import OrderedDict
from hashlib import sha256
import json
import re
import threading
from . import sample_library_state as S
from .sample_library_command import dispatch, error_payload

MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_RETAINED_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 128  # Native host admits at most 64 outstanding requests.


def request_id(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        S.fail('样片请求身份无效')
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


class SampleLibraryHost:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = {}
        self.early_cancel = set()
        self.results = OrderedDict()
        self.retained_bytes = 0
        self.stopped = False
        self.control_overflow = False

    def register(self, ident):
        ident = request_id(ident)
        with self.lock:
            event = self.events.get(ident)
            if event is None:
                if len(self.events) >= MAX_RECORDS:
                    S.fail('样片请求队列已满，请等待已提交请求结束', 'busy')
                event = threading.Event()
                if self.stopped or self.control_overflow or ident in self.early_cancel:
                    event.set()
                self.early_cancel.discard(ident)
                self.events[ident] = event
            return event

    def cancel(self, ident):
        ident = request_id(ident)
        with self.lock:
            event = self.events.get(ident)
            if event is not None:
                event.set()
            elif ident not in self.results:
                if len(self.early_cancel) < MAX_RECORDS:
                    self.early_cancel.add(ident)
                else:
                    # Do not silently lose a cancellation that overtook a queued
                    # request in the native dispatcher. Restart clears this fence.
                    self.control_overflow = True
                    for pending in self.events.values(): pending.set()

    def stop(self):
        with self.lock:
            self.stopped = True
            for event in self.events.values(): event.set()

    def observe_line(self, line):
        """True consumes only a strict cancellation control, never an edit."""
        if type(line) is not str or 'sample_library' not in line:
            return False
        try:
            if len(line.encode('utf-8')) > MAX_REQUEST_BYTES: return False
            message = json.loads(line)
            if type(message) is not dict: return False
            if message.get('cmd') == 'sample_library_cancel':
                if set(message) != {'cmd', 'request_id'}: return False
                self.cancel(message['request_id'])
                return True
            if message.get('cmd') == 'sample_library':
                self.register(message.get('request_id'))
        except (ValueError, TypeError, UnicodeError):
            # The normal command owner will produce the failure/host ack.
            return False
        return False

    def handle(self, engine, message, emit):
        ident = message.get('request_id')
        terminal = {'event': 'sample_library_result', 'protocol': 1,
                    'request_id': ident if type(ident) is str and len(ident) <= 128 else None, 'action': 'request'}
        signature = None
        try:
            ident = request_id(ident)
            if set(message) != {'cmd', 'request_id', 'action', 'request'} or message['action'] != 'request':
                S.fail('样片命令字段无效')
            raw = encoded(message)
            if len(raw) > MAX_REQUEST_BYTES: S.fail('样片请求超过传输预算', 'capacity')
            signature = sha256(raw).hexdigest()
            with self.lock:
                previous = self.results.get(ident)
                if previous is not None:
                    if previous[0] != signature:
                        signature = None  # Never overwrite the first request's terminal identity.
                        S.fail('同一请求身份不能绑定不同内容', 'request_conflict')
                    self.events.pop(ident, None)
            if previous is not None:
                emit(previous[1])
                return
            stop = self.register(ident)
            if stop.is_set(): S.fail('请求已取消，未执行样片操作', 'cancelled')
            result = dispatch(engine, message['request'], cancelled=stop.is_set)
            terminal.update(success=True, outcome_unknown=False, committed=True, result=result)
            if len(encoded(terminal)) > MAX_RESULT_BYTES:
                raise S.LibraryError('操作已结束，但回执超过预算；请刷新目录核对结果，勿自动重试',
                                     code='receipt_capacity', outcome_unknown=True, committed=None)
        except Exception as error:
            terminal.pop('result', None)
            detail = error_payload(error)
            terminal.update(success=False, error=detail['message'], error_code=detail['code'],
                            outcome_unknown=detail['outcome_unknown'], committed=detail['committed'])
        if signature is not None:
            size = len(encoded(terminal))
            with self.lock:
                # Retention is an optimization for duplicate stdin delivery, not
                # persistence. Native terminal receipts remain until explicit release.
                old = self.results.pop(ident, None)
                if old is not None: self.retained_bytes -= old[2]
                while self.results and (len(self.results) >= MAX_RECORDS or self.retained_bytes + size > MAX_RETAINED_BYTES):
                    _, old = self.results.popitem(last=False)
                    self.retained_bytes -= old[2]
                self.results[ident] = (signature, terminal, size)
                self.retained_bytes += size
                self.events.pop(ident, None)
        elif type(ident) is str:
            with self.lock: self.events.pop(ident, None)
        emit(terminal)


class SampleLibraryHostMixin:
    def _sample_library_host(self):
        owner = self.__dict__.get('_sample_library_protocol')
        if owner is None:
            owner = SampleLibraryHost()
            self._sample_library_protocol = owner
        return owner

    def cmd_sample_library(self, message):
        from .server import emit
        self._sample_library_host().handle(self, message, emit)

    def cmd_sample_library_cancel(self, message):
        # Normally consumed by the reader; retained for direct command hosts.
        if set(message) != {'cmd', 'request_id'}: S.fail('样片取消字段无效')
        self._sample_library_host().cancel(message['request_id'])
