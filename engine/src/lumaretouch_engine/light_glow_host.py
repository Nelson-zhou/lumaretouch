# SPDX-License-Identifier: GPL-3.0-or-later
"""Serialized current-photo glow review and canonical new-image return.

AUTHORED / UNRUN. No registration, render fallback, direct file export, second
history owner or cancellation of an entered write. Receipts survive UI unmount.
"""
from copy import deepcopy
import json
import time
import uuid
from . import light_glow_stage as stage
from .light_glow_jobs import canonical, command_hash, controller as jobs, token

MAX_READS = 256
MAX_WRITES = 128
MAX_SESSIONS = 64
MAX_RETAINED_BYTES = 1_500_000_000
LEDGER_RESERVE = 4 * 1024 * 1024
SESSION_SECONDS = 600.0
CANDIDATE_SECONDS = 180.0
JOB_SECONDS = 120.0


def _text(error):
    return str(error).replace('\0', '')[:512]


def _receipt(command, *, phase='done', outcome=None, message='', **facts):
    result = {k: deepcopy(command[k]) for k in
              ('version', 'operation_id', 'request_id', 'session_id', 'action', 'owner', 'token')}
    result.update(phase=phase, outcome_unknown=phase != 'done', message=message)
    if phase == 'done':
        result['outcome'] = outcome
    return {**result, **facts}


class Service:
    # Shared immutable-source/copy transaction; numerical stages stay independent.
    stage = stage
    jobs = staticmethod(jobs)
    command_hash = staticmethod(command_hash)
    command_name = "light_glow"
    event_name = "light_glow_result"
    job_seconds = JOB_SECONDS
    session_seconds = SESSION_SECONDS

    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.source = self.fence = self.candidate = None
        self.session_id = self.session_event = None
        self.session_deadline = self.candidate_deadline = 0.0
        self.sessions, self.reads, self.writes = {}, {}, {}
        self.uncertain = None

    def _guard(self):
        if self.uncertain is not None:
            raise ValueError('处理新图原请求结果待核对；只能查询，不得重发或假装取消')
        from .creative_document_host import CreativeHost
        from .sample_library_capture import capture_reason
        reason = capture_reason(self.engine) or CreativeHost(self.engine, self.emit).guard(self.command_name)
        if reason:
            raise ValueError(reason)
        host = self.engine.__dict__.get('_creative_host')
        if host is not None and host.pending is not None:
            raise ValueError('请先确认原创意回流请求')

    def _budget(self):
        from .creative_document_host import memory_budget
        return self.stage.Budget(min(2_000_000_000, memory_budget()) - LEDGER_RESERVE,
                            timeout_seconds=self.job_seconds)

    def _drop(self, status='closed'):
        if self.session_id is not None:
            self.jobs(self.engine).close_session(self.session_id)
            self.sessions[self.session_id]['status'] = status
        self.source = self.fence = self.candidate = None
        self.session_id = self.session_event = None
        self.session_deadline = self.candidate_deadline = 0.0

    def maintain(self):
        if self.uncertain is not None:
            return
        if self.source is not None and (time.monotonic() >= self.session_deadline or self.fence.stale(self.engine)):
            self._drop('expired')
        elif self.candidate is not None and time.monotonic() >= self.candidate_deadline:
            self.candidate = None

    def _stopped(self, external=lambda: False):
        return (external() or self.session_event is None or self.session_event.is_set()
                or self.fence is None or self.fence.stale(self.engine)
                or time.monotonic() >= self.session_deadline)

    def _require(self, command):
        if (self.source is None or command.get('session_id') != self.session_id
                or command.get('owner') != self.source.owner):
            raise ValueError('处理请求不是当前保留的完整编辑来源，请重新读取')
        self.fence.verify(self.engine, self._stopped)

    def _retained(self, candidate=None):
        # Original/ICC immutable bytes are shared, not decoded/copied again.
        total = LEDGER_RESERVE + self.source.retained_bytes
        if candidate is not None:
            total += candidate.retained_bytes
            for key in ('original', 'icc', 'content'):
                if getattr(candidate, key) is getattr(self.source.pixels, key):
                    total -= len(getattr(candidate, key))
        if total > MAX_RETAINED_BYTES:
            raise MemoryError('处理完整来源与候选超过保留数据预算；不会缩小最终图像')

    def current(self, request):
        self._guard()
        if len(self.sessions) >= MAX_SESSIONS:
            raise ValueError('Reviewed copy session ledger is full; earlier write proof was not evicted')
        self._drop()
        cap = self.stage.capability()
        if cap['status'] != 'available':
            return {'status': 'rejected', 'message': cap['reason']}
        def work(event):
            from .light_glow_source import capture_current
            deadline = time.monotonic() + JOB_SECONDS
            stopped = lambda: event() or time.monotonic() >= deadline
            source, fence = capture_current(self.engine, budget=self._budget(), cancelled=stopped)
            self.stage.admit_source(source, self._budget())
            if source.retained_bytes + LEDGER_RESERVE > MAX_RETAINED_BYTES:
                raise MemoryError('Reviewed copy source lease exceeds retained memory budget')
            fence.verify(self.engine, stopped)
            return source, fence
        source, fence = self.jobs(self.engine).run(request['request_id'], self.command_hash(request), work)
        ident = uuid.uuid4().hex
        self.sessions[ident] = {'owner': canonical(source.owner), 'tokens': set(), 'status': 'open'}
        self.source, self.fence, self.session_id = source, fence, ident
        self.session_event = self.jobs(self.engine).bind_session(ident, source.owner)
        self.session_deadline = time.monotonic() + self.session_seconds
        return {'status': 'ready', 'context': self.stage.context(source, ident, cap)}

    def preview(self, request):
        self._guard()
        command = request['command']
        self._require(command)
        if len(self.sessions[self.session_id]['tokens']) >= 64:
            raise ValueError('Reviewed copy preview lease limit reached; start a new source session')
        self.candidate = None
        def work(event):
            candidate = self.stage.prepare(command, self.source, budget=self._budget(),
                                      cancelled=lambda: self._stopped(event))
            self._require(command)
            self._retained(candidate)
            return candidate
        candidate = self.jobs(self.engine).run(request['request_id'], self.command_hash(request), work)
        self.candidate = candidate
        self.candidate_deadline = time.monotonic() + CANDIDATE_SECONDS
        self.sessions[self.session_id]['tokens'].add(candidate.token)
        return {'status': 'ready', 'review': candidate.review}

    def _save(self, command, receipt):
        ident = command['request_id']
        record = {'command': canonical(command), 'receipt': canonical(receipt)}
        if sum(map(len, record.values())) > 16 * 1024:
            raise ValueError('Reviewed copy write receipt exceeds its reserved bound')
        if ident not in self.writes and len(self.writes) >= MAX_WRITES:
            raise ValueError('Reviewed copy write ledger is full; no original outcome was evicted')
        self.writes[ident] = record
        return receipt

    def _known(self, command):
        old = self.writes.get(command['request_id'])
        if old is None:
            return None
        if old['command'] != canonical(command):
            raise ValueError('Reviewed copy write identity reused with different exact content')
        return json.loads(old['receipt'])

    def _cancel(self, command):
        if self.uncertain is not None:
            raise ValueError('处理新图提交结果未确认，取消不能撤销或掩盖原请求')
        session = self.sessions.get(command['session_id'])
        if session is None or session['owner'] != canonical(command['owner']):
            raise ValueError('Reviewed copy cancel does not identify an issued session')
        if session['status'] == 'applied':
            raise ValueError('处理结果已经另存新图，不能报告为取消')
        if command['token'] is not None and command['token'] not in session['tokens']:
            raise ValueError('Reviewed copy cancel token was not issued to this session')
        if self.session_id == command['session_id']:
            self._drop('cancelled')
        else:
            session['status'] = 'cancelled'
        return _receipt(command, outcome='cancelled', message='已释放处理暂存结果，没有创建新图或修改原图。')

    def _readback(self, pending, expected_id=None):
        e, base = self.engine, pending['fence'].base
        if (e._document_versions() is not base.versions or base.versions.workspace != base.epoch
                or not any(row is base.row for row in e._docs)
                or base.versions.version(base.row) != base.version):
            return None
        matches = []
        for row in e._docs:
            if row['document_id'] in pending['before_ids']:
                continue
            state = row.get('state') or {}
            document = state.get('_creative_document')
            if (state.get('_creative_base') != pending['asset'] or type(document) is not dict
                    or row.get('path') != base.path or row.get('source_asset_id') != base.row.get('source_asset_id')
                    or document.get('source_uid') != row['document_id'] or document.get('revision') != 0
                    or any(document.get(k) != pending['document'][k] for k in ('source_asset', 'canvas', 'layers', 'selected_id'))
                    or expected_id is not None and row['document_id'] != expected_id):
                continue
            if token(row['document_id']) and row['document_id'] != base.version.document_id:
                matches.append(row)
        if len(matches) != 1:
            return None
        row = matches[0]
        return _receipt(pending['command'], outcome='applied',
            message='完整处理结果已另存独立新图；原图及其编辑历史保留。',
            result_document_id=row['document_id'], copied_original_document_id=base.version.document_id,
            result_revision=str(base.versions.version(row).revision),
            result_source_sha256=pending['asset']['id'][7:], no_change=pending['no_change'])

    def _apply(self, command):
        self._guard()
        self._require(command)
        candidate = self.candidate
        if candidate is None or time.monotonic() >= self.candidate_deadline:
            raise ValueError('处理候选不存在或已过期，请重新生成完整对比')
        candidate.validate_apply(command)
        self._retained(candidate)
        if len(self.engine._docs) > 10_000:
            raise ValueError('Reviewed copy copy readback exceeds bounded document admission')
        from .creative_document_host import CreativeHost, require_photo_return
        from .creative_document_state import create
        asset = candidate.output_asset
        require_photo_return(asset)
        host = CreativeHost(self.engine, self.emit)
        ident = host.assets.intern(asset)
        document = create(command['owner']['document_id'], ident, host.assets)
        self._require(command)
        pending = {'command': deepcopy(command), 'fence': self.fence, 'asset': asset,
                   'document': document, 'no_change': candidate.no_change,
                   'before_ids': frozenset(row['document_id'] for row in self.engine._docs)}
        self._save(command, _receipt(command, phase='unknown', message='处理新图提交已进入不可重发阶段；请查询同一原请求。'))
        self.uncertain = pending
        result = host.commit_return({'mode': 'new_image', 'rendered_asset': ident, 'creative_document': document})
        receipt = self._readback(pending, result.get('document_id') if type(result) is dict else None)
        if type(result) is not dict or result.get('status') != 'applied' or receipt is None:
            raise RuntimeError('Reviewed copy new-image result lacks matching canonical readback; query only')
        self._save(command, receipt)
        self.uncertain = None
        self._drop('applied')
        return receipt

    def submit(self, command):
        command = self.stage.write_command(command)
        prior = self._known(command)
        if prior is not None:
            return prior
        if command['request_id'] in self.reads:
            raise ValueError('Reviewed copy write request identity collides with an earlier read')
        self._save(command, _receipt(command, phase='pending', message='原处理请求已登记，查询不会再次执行。'))
        try:
            result = self._apply(command) if command['action'] == 'apply' else self._cancel(command)
        except Exception as error:
            known = self._known(command)
            if known.get('phase') == 'done' and known.get('outcome') == 'applied':
                return known
            entered = self.uncertain is not None and self.uncertain['command']['request_id'] == command['request_id']
            result = _receipt(command, phase='unknown' if entered else 'done',
                              outcome=None if entered else 'rejected', message=_text(error))
        return self._save(command, result)

    def receipt(self, command):
        command = self.stage.write_command(command)
        prior = self._known(command)
        if prior is None:
            return _receipt(command, phase='unknown', message='当前进程没有原请求证明；不会重提或推断已取消。')
        if self.uncertain is not None and self.uncertain['command'] == command:
            result = self._readback(self.uncertain)
            if result is not None:
                self._save(command, result)
                self.uncertain = None
                self._drop('applied')
                return result
        return prior

    def _replay(self, request, prior):
        if prior['sha'] != self.command_hash(request):
            raise ValueError('Reviewed copy read identity reused with different content')
        if 'failure' in prior:
            return deepcopy(prior['failure'])
        if self.source is None or prior['session_id'] != self.session_id:
            raise ValueError('Reviewed copy read lease released; original read will not execute again')
        self._require({'session_id': self.session_id, 'owner': self.source.owner})
        if request['action'] == 'preview':
            if self.candidate is None or self.candidate.review['request_id'] != request['request_id']:
                raise ValueError('Reviewed copy preview superseded; no blind rerender')
            return {'status': 'ready', 'review': self.candidate.review}
        cap = self.stage.capability()
        return {'status': 'ready', 'context': self.stage.context(self.source, self.session_id, cap)}

    def handle(self, request):
        ident = request.get('request_id') if type(request) is dict else None
        action = request.get('action') if type(request) is dict else None
        sha = None
        try:
            if not token(ident) or request.get('cmd') != self.command_name:
                raise ValueError('Malformed reviewed copy transport identity')
            keys = {'cmd', 'action', 'request_id'}
            if action in ('preview', 'submit', 'receipt'):
                keys.add('command')
            elif action != 'current':
                raise ValueError('Unsupported reviewed copy action')
            if set(request) != keys:
                raise ValueError('Reviewed copy request has missing or unknown fields')
            sha = self.command_hash(request)
            request = json.loads(canonical(request))
            if action != 'current':
                c = request['command']
                if type(c) is not dict or action != 'receipt' and c.get('request_id') != ident:
                    raise ValueError('Reviewed copy transport and command identity differ')
                if action == 'preview' and c.get('action') != 'preview':
                    raise ValueError('Reviewed copy preview action mismatch')
            self.maintain()
            if action in ('submit', 'receipt'):
                result = {'status': 'ready', 'receipt': getattr(self, action)(request['command'])}
            else:
                if ident in self.writes:
                    raise ValueError('Reviewed copy read identity collides with an earlier write')
                if ident in self.reads:
                    result = self._replay(request, self.reads[ident])
                else:
                    if len(self.reads) >= MAX_READS:
                        raise ValueError('Reviewed copy read ledger is full; earlier outcomes were not evicted')
                    prior = self.reads[ident] = {'sha': sha, 'session_id': None}
                    try:
                        result = getattr(self, action)(request)
                        prior['session_id'] = self.session_id
                        if action == 'current' and result.get('context') is None:
                            prior['failure'] = deepcopy(result)
                    except Exception as error:
                        result = {'status': 'cancelled' if isinstance(error, InterruptedError) else 'rejected', 'message': _text(error)}
                        prior['failure'] = deepcopy(result)
        except Exception as error:
            result = {'status': 'rejected', 'message': _text(error)}
        finally:
            if action in ('current', 'preview') and sha is not None:
                self.jobs(self.engine).retire(ident, sha)
        self.emit({'event': self.event_name, 'request_id': ident, **result})


def service(engine, emit):
    owner = engine.__dict__.get('_light_glow_service')
    if owner is None:
        owner = Service(engine, emit)
        engine._light_glow_service = owner
    return owner


def handle(engine, request, emit):
    service(engine, emit).handle(request)


def read_only(request):
    return request.get('cmd') == 'light_glow' and request.get('action') in ('current', 'preview', 'receipt')


def guard_other(engine, name, request):
    owner = engine.__dict__.get('_light_glow_service')
    if (owner is not None and owner.uncertain is not None and name not in ('light_glow', 'hello', 'shutdown')
            and not (name == 'session' and request.get('action') == 'query')):
        raise ValueError('发光新图原请求结果待核对；其他修改暂受保护，请勿盲目重试')


def invalidate(engine):
    owner = engine.__dict__.get('_light_glow_service')
    if owner is not None:
        owner.maintain()


def dispatch_rejected(request, message, started, emit, *, engine=None):
    if engine is not None and request.get('action') in ('current', 'preview'):
        try:
            jobs(engine).retire(request.get('request_id'), command_hash(request))
        except (ValueError, TypeError, KeyError):
            pass
    result = {'event': 'light_glow_result', 'request_id': request.get('request_id'),
              'status': 'rejected', 'message': _text(message)}
    if request.get('action') in ('submit', 'receipt'):
        try:
            command = stage.write_command(request.get('command'))
            owner = service(engine, emit) if engine is not None else None
            receipt = owner._known(command) if owner is not None else None
            if receipt is None:
                unknown = bool(started or request['action'] == 'receipt' or owner is None)
                receipt = _receipt(command, phase='unknown' if unknown else 'done',
                                   outcome=None if unknown else 'rejected', message=_text(message))
                if owner is not None and not unknown:
                    owner._save(command, receipt)
            result.update(status='ready', receipt=receipt)
            result.pop('message', None)
        except (ValueError, TypeError, KeyError, MemoryError):
            pass
    emit(result)
