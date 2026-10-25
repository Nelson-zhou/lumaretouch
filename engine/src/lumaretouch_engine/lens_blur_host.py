# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned current-photo lens review and explicit canonical save-copy boundary.

AUTHORED / UNRUN. All methods execute on the existing serialized engine thread.
The reader may only set cancellation Events. There is no depth model, pixel
solver, alternate image renderer, independent history stack or file export here.
Source/depth/candidate leases are private; only CreativeHost.commit_return may
publish a reviewed result as a distinct new image. Original pixels stay intact.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import time
import uuid

from . import lens_blur_stage as stage
from .lens_blur_jobs import canonical, command_hash, controller as jobs, digest, token

PROTOCOL = 3
MAX_RETAINED_BYTES = 1_000_000_000
MAX_WORK_BYTES = 2_000_000_000
MAX_READS = 256
MAX_WRITES = 128
MAX_SESSIONS = 64
MAX_LEDGER_BYTES = 2 * 1024 * 1024
MAX_WRITE_RECORD_BYTES = 16 * 1024
LEDGER_RESERVE = 4 * 1024 * 1024
SESSION_SECONDS = 600.0
CANDIDATE_SECONDS = 180.0
JOB_SECONDS = 120.0


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Lens source/session ownership expired or work was cancelled')


def _text(error):
    # Bound escaped JSON bytes as well as visible characters. This reserves
    # enough room to replace every admitted pending write with its final error.
    return str(error).replace('\0', '')[:512]


def _file_hash(path, cancelled):
    """Cold content verification; hot native polls never hash the source file."""
    from .local_mask_state import file_stamp
    from .creative_document_assets import MAX_ORIGINAL_BYTES
    before = file_stamp(path)
    if before[2] > MAX_ORIGINAL_BYTES:
        raise ValueError('Lens original provenance exceeds the retained source budget')
    sha = hashlib.sha256()
    total = 0
    with open(path, 'rb') as stream:
        while True:
            _poll(cancelled)
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_ORIGINAL_BYTES:
                raise ValueError('Lens original source grew beyond its provenance budget')
            sha.update(block)
    if file_stamp(path) != before:
        raise ValueError('Lens original source changed during its content proof')
    return sha.hexdigest()


@dataclass(frozen=True)
class _Fence:
    index: int
    row: object
    versions: object
    version: object
    epoch: str
    load_id: object
    creative_owner: str
    graph_owner: object
    graph_fence: object
    path: str
    stamp: tuple
    file_sha256: str
    graph_sha256: str

    @classmethod
    def capture(cls, engine, cancelled):
        from .creative_document_host import token as creative_token
        from .local_mask_state import file_stamp
        index = engine._doc_index
        if not 0 <= index < len(engine._docs):
            raise ValueError('Open a genuine current photograph before lens capture')
        row = engine._docs[index]
        versions = engine._document_versions()
        graph_owner = engine._people_owner()
        graph_fence = graph_owner.fence
        path = row['path']
        stamp = file_stamp(path)
        version = versions.version(row)
        epoch, load_id, owner = versions.workspace, engine._load_id, creative_token(engine)
        file_sha = _file_hash(path, cancelled)
        graph_sha = hashlib.sha256(canonical(graph_owner.snapshot())).hexdigest()
        result = cls(index, row, versions, version, epoch, load_id, owner,
                     graph_owner, graph_fence, path, stamp, file_sha, graph_sha)
        result.verify(engine, cancelled, cold=False)
        return result

    def stale(self, engine):
        from .creative_document_host import token as creative_token
        from .local_mask_state import file_stamp
        try:
            return (engine._doc_index != self.index or not 0 <= self.index < len(engine._docs)
                    or engine._docs[self.index] is not self.row or self.row.get('path') != self.path
                    or engine._document_versions() is not self.versions
                    or self.versions.workspace != self.epoch
                    or self.versions.version(self.row) != self.version
                    or engine._load_id != self.load_id or creative_token(engine) != self.creative_owner
                    or engine._people_owner() is not self.graph_owner
                    or self.graph_owner.fence != self.graph_fence or file_stamp(self.path) != self.stamp)
        except (ValueError, OSError, IndexError, KeyError):
            return True

    def verify(self, engine, cancelled, *, cold=True):
        stopped = lambda: cancelled() or self.stale(engine)
        _poll(stopped)
        if cold:
            if _file_hash(self.path, stopped) != self.file_sha256:
                raise ValueError('Lens original provenance changed; the retained review is stale')
            if hashlib.sha256(canonical(self.graph_owner.snapshot())).hexdigest() != self.graph_sha256:
                raise ValueError('Lens current-edit people context changed; no old source reuse')
        _poll(stopped)


def capability():
    """Query separately versioned packaged renderers, never a filename fallback."""
    from .lens_aperture_native import capability as direct_query
    from .lens_cohort_native import capability as cohort_query
    from .creative_layer_native import native, CreativeLayerNativeUnavailable
    direct, cohort = direct_query(), cohort_query()
    renderers, kernels, reasons = [], set(), []
    if direct['lens_aperture_available']:
        renderers.append('direct-v1'); kernels.update(direct['kernels'])
    elif direct['lens_aperture_reason']:
        reasons.append(direct['lens_aperture_reason'])
    if cohort['available']:
        renderers.append('cohort-fft-v2'); kernels.update(cohort['kernels'])
    elif cohort['reason']:
        reasons.append(cohort['reason'])
    if renderers:
        try:
            native()
        except CreativeLayerNativeUnavailable as error:
            renderers, kernels, reasons = [], set(), [_text(error)]
    return {'version': 2, 'operation_id': stage.OPERATION,
            'status': 'available' if renderers else 'unavailable', 'renderers': renderers,
            'kernels': sorted(kernels), 'reason': _text('; '.join(reasons))}


def _write(command):
    if type(command) is not dict or type(command.get('version')) is not int or command['version'] != PROTOCOL:
        raise ValueError('Lens writes require explicit copy-review protocol 3')
    action = command.get('action')
    keys = {'version', 'action', 'request_id', 'session_id', 'owner', 'token'}
    if action == 'apply':
        keys |= {'recipe_sha256', 'before_sha256', 'after_sha256', 'reviewed', 'return_mode', 'result_source_sha256'}
    elif action != 'cancel':
        raise ValueError('Unsupported lens write action')
    if set(command) != keys or not token(command['request_id']) or not token(command['session_id']):
        raise ValueError('Malformed exact lens write envelope')
    stage._owner(command['owner'])
    if action == 'apply':
        if (not token(command['token']) or command['reviewed'] is not True or command['return_mode'] != 'new_image'
                or any(not digest(command[key]) for key in ('recipe_sha256', 'before_sha256', 'after_sha256', 'result_source_sha256'))):
            raise ValueError('Lens apply requires exact full-image acknowledgement and explicit new-image return')
    elif command['token'] is not None and not token(command['token']):
        raise ValueError('Malformed lens cancellation token')
    raw = canonical(command)
    if len(raw) > 8192:
        raise ValueError('Lens write exceeds its receipt identity budget')
    return json.loads(raw)


def _receipt(command, *, phase='done', outcome=None, message='', **facts):
    result = {key: deepcopy(command[key]) for key in ('version', 'request_id', 'session_id', 'action', 'owner', 'token')}
    result.update(phase=phase, outcome_unknown=phase != 'done', message=message)
    if phase == 'done':
        result['outcome'] = outcome
    return {**result, **facts}


class Service:
    """Engine-lifetime bounded receipts outlive any mounted workspace panel."""

    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.source = None
        self.depth = None
        self.candidate = None
        self.fence = None
        self.session_id = None
        self.session_event = None
        self.session_deadline = 0.0
        self.candidate_deadline = 0.0
        self.sessions = {}
        self.reads = {}
        self.writes = {}
        self.uncertain = None

    def _guard(self):
        if self.uncertain is not None:
            raise ValueError('镜头新图原请求结果待核对；只能查询，不能重发或假装取消')
        from .sample_library_capture import capture_reason
        reason = capture_reason(self.engine)
        if reason:
            raise ValueError(reason)
        from .creative_document_host import CreativeHost
        reason = CreativeHost(self.engine, self.emit).guard('lens_blur')
        if reason:
            raise ValueError(reason)
        creative = self.engine.__dict__.get('_creative_host')
        if creative is not None and creative.pending is not None:
            raise ValueError('请先确认原创意回流请求')

    def _drop(self, status='closed'):
        if self.session_id is not None:
            jobs(self.engine).close_session(self.session_id)
            self.sessions[self.session_id]['status'] = status
        self.source = self.depth = self.candidate = self.fence = None
        self.session_id = self.session_event = None
        self.session_deadline = self.candidate_deadline = 0.0

    def maintain(self):
        """Lazy lease reclamation; never discard an unresolved write's proof."""
        if self.uncertain is not None:
            return
        if self.source is not None and (time.monotonic() >= self.session_deadline or self.fence.stale(self.engine)):
            self._drop('expired')
        elif self.candidate is not None and time.monotonic() >= self.candidate_deadline:
            self.candidate = None

    def _admit_retained(self, *values):
        total, seen = LEDGER_RESERVE, set()
        for value in values:
            if value is None:
                continue
            total += value.retained_bytes
            # Immutable canonical records share actual original/ICC bytes; count
            # physical object identity, never deduplicate merely equal contents.
            for key in ('content', 'original', 'icc'):
                data = getattr(value, key, None)
                if type(data) is bytes:
                    if id(data) in seen:
                        total -= len(data)
                    seen.add(id(data))
        if total > MAX_RETAINED_BYTES:
            raise MemoryError('Lens retained source/depth/candidate lease exceeds one bounded session')

    def _budget(self):
        from .creative_document_host import memory_budget
        ceiling = min(MAX_WORK_BYTES, memory_budget())
        if ceiling <= LEDGER_RESERVE + 16 * 1024 * 1024:
            raise MemoryError('Insufficient bounded lens workspace after receipt reservation')
        return stage.Budget(ceiling - LEDGER_RESERVE, timeout_seconds=JOB_SECONDS)

    def _stopped(self, external=lambda: False):
        return (external() or self.session_event is None or self.session_event.is_set()
                or self.fence is None or self.fence.stale(self.engine)
                or time.monotonic() >= self.session_deadline)

    def _require(self, command, *, cold=True):
        if (self.source is None or self.session_id != command.get('session_id')
                or canonical(command.get('owner')) != self.source.owner_json):
            raise ValueError('Lens command is not owned by the retained current full-source session')
        _poll(self._stopped)
        self.fence.verify(self.engine, self._stopped, cold=cold)

    def _context(self):
        result = stage.context(self.source, self.session_id, self.depth)
        from .lens_blur_admission import source_notice
        result['message'] += ' 仅接受不透明 SDR 完整编辑结果；确认后另存新图，原图不改。'+source_notice(self.source.owner['source'],self._budget(),renderers=capability()['renderers'])
        return result

    def current(self, request):
        self._guard()
        if len(self.sessions) >= MAX_SESSIONS:
            raise ValueError('Lens session ledger is full; no old write proof was evicted')
        cap = capability()
        if cap['status'] != 'available':
            return {'status': 'ready', 'capability': cap, 'context': None, 'message': cap['reason']}
        self._drop()
        def work(event):
            deadline = time.monotonic() + JOB_SECONDS
            cancelled = lambda: event() or time.monotonic() >= deadline
            maximum = self._budget()
            fence = _Fence.capture(self.engine, cancelled)
            stopped = lambda: cancelled() or fence.stale(self.engine)
            from .creative_document_assets import AssetStore
            from .creative_document_base import capture_current_asset
            from .creative_document_host import require_photo_return
            # Never use CreativeHost.assets here: failed/late captures must not
            # leak pixels into a document cache, project or undo frame.
            assets = AssetStore(max_bytes=min(MAX_RETAINED_BYTES, maximum.max_bytes))
            state = self.engine._capture_state()
            asset = capture_current_asset(self.engine, fence.row, state, assets,
                                          max_bytes=maximum.max_bytes, cancelled=stopped,
                                          neutral_import_version=1 if 'cohort-fft-v2' in cap['renderers'] else 0,
                                          allow_legacy_import_budget_fallback='direct-v1' in cap['renderers'],
                                          edited_capture_version=1 if 'cohort-fft-v2' in cap['renderers'] else 0)
            del assets, state  # Release imported intermediates before display staging.
            _poll(stopped)
            require_photo_return(asset)  # Exact opaque SDR gate, never a clip.
            from .lens_blur_admission import source_admission
            source_admission(asset,maximum,display_reserve=stage.DISPLAY_RESERVE,renderers=cap['renderers'],
                             retained_limit=MAX_RETAINED_BYTES-LEDGER_RESERVE)
            owner = {'document_id': fence.version.document_id, 'document_epoch': fence.epoch,
                     'document_revision': str(fence.version.revision),
                     'source': {'sha256': asset['id'][7:], 'width': asset['width'],
                                'height': asset['height'], 'orientation': stage.ORIENTATION}}
            source = stage.capture_source(asset, owner, budget=maximum, cancelled=stopped)
            self._admit_retained(source)
            fence.verify(self.engine, cancelled)
            return source, fence
        source, fence = jobs(self.engine).run(request['request_id'], command_hash(request), work)
        session_id = uuid.uuid4().hex
        self.sessions[session_id] = {'owner': source.owner_json, 'status': 'open', 'tokens': set()}
        self.source, self.fence, self.session_id = source, fence, session_id
        self.session_event = jobs(self.engine).bind_session(session_id, source.owner)
        self.session_deadline = time.monotonic() + SESSION_SECONDS
        return {'status': 'ready', 'capability': cap, 'context': self._context()}

    def prepare_manual_plane(self, request):
        command = request['command']
        self._guard()
        self._require(command)
        self.candidate = self.depth = None
        def work(event):
            depth = stage.prepare_manual_plane(command, self.source, budget=self._budget(),
                                                cancelled=lambda: self._stopped(event))
            self._require(command)
            self._admit_retained(self.source, depth)
            return depth
        self.depth = jobs(self.engine).run(request['request_id'], command_hash(request), work)
        return {'status': 'ready', 'context': self._context()}

    def preview(self, request):
        command = request['command']
        self._guard()
        self._require(command)
        if self.depth is None:
            raise ValueError('请先明确选择人工散焦基准面；AI 景深不可用，不会编造景深')
        if len(self.sessions[self.session_id]['tokens']) >= 64:
            raise ValueError('Lens session preview limit reached; explicitly begin a new source session')
        self.candidate = None
        def work(event):
            candidate = stage.prepare(command, self.source, self.depth, budget=self._budget(),
                                      cancelled=lambda: self._stopped(event))
            from .creative_document_host import require_photo_return
            require_photo_return(candidate.output_asset)
            self._require(command)
            self._admit_retained(self.source, self.depth, candidate)
            return candidate
        candidate = jobs(self.engine).run(request['request_id'], command_hash(request), work)
        self.candidate = candidate
        self.candidate_deadline = time.monotonic() + CANDIDATE_SECONDS
        self.sessions[self.session_id]['tokens'].add(candidate.token)
        return {'status': 'ready', 'review': candidate.review}

    def _save_write(self, command, receipt):
        ident = command['request_id']
        record = {'command': canonical(command), 'receipt': canonical(receipt)}
        if len(record['command']) + len(record['receipt']) > MAX_WRITE_RECORD_BYTES:
            raise ValueError('Lens receipt exceeds its per-write reserved record budget')
        if ident not in self.writes and len(self.writes) >= MAX_WRITES:
            raise ValueError('Lens write receipt ledger is full; original outcomes remain queryable')
        total = sum(len(value['command']) + len(value['receipt']) for key, value in self.writes.items() if key != ident)
        if total + len(record['command']) + len(record['receipt']) > MAX_LEDGER_BYTES:
            raise MemoryError('Lens write receipt memory limit reached before transaction')
        self.writes[ident] = record
        return receipt

    def _known_write(self, command):
        old = self.writes.get(command['request_id'])
        if old is None:
            return None
        if old['command'] != canonical(command):
            raise ValueError('Lens write request identity reused with a different exact command')
        return json.loads(old['receipt'])

    def _cancel(self, command):
        if self.uncertain is not None:
            raise ValueError('保存新图已进入提交阶段且结果未确认，取消不能撤销或掩盖原请求')
        session = self.sessions.get(command['session_id'])
        if session is None or session['owner'] != canonical(command['owner']):
            raise ValueError('Lens cancellation does not identify an issued session')
        if session['status'] == 'applied':
            raise ValueError('镜头结果已经另存新图，不能将已完成请求报告为取消')
        if command['token'] is not None and command['token'] not in session['tokens']:
            raise ValueError('Lens cancellation token was not issued to this session')
        # This runs only after any earlier source job has actually unwound on
        # the serialized command thread, not when the reader first sets Event.
        if self.session_id == command['session_id']:
            self._drop('cancelled')
        else:
            session['status'] = 'cancelled'
        return _receipt(command, outcome='cancelled', message='已取消本次镜头编辑，暂存结果已释放；没有创建新图或修改原图。')

    def _readback(self, pending, expected_document_id=None):
        """Positive authoritative copy proof only; absence is not safe to retry."""
        e = self.engine
        fence = pending['fence']
        if (e._document_versions() is not fence.versions or fence.versions.workspace != fence.epoch
                or not any(row is fence.row for row in e._docs)
                or fence.versions.version(fence.row) != fence.version):
            return None
        matches = []
        for row in e._docs:
            if row['document_id'] in pending['before_ids']:
                continue
            state = row.get('state') or {}
            base, document = state.get('_creative_base'), state.get('_creative_document')
            if (type(base) is not dict or base != pending['asset'] or type(document) is not dict
                    or row.get('source_asset_id') != fence.row.get('source_asset_id') or row.get('path') != fence.path
                    or document.get('source_uid') != row['document_id'] or document.get('revision') != 0
                    or any(document.get(key) != pending['document'][key] for key in ('source_asset', 'canvas', 'layers', 'selected_id'))):
                continue
            if expected_document_id is not None and row['document_id'] != expected_document_id:
                continue
            if not token(row['document_id']) or row['document_id'] == fence.version.document_id:
                continue
            matches.append(row)
        if len(matches) != 1:
            return None
        row = matches[0]
        revision = fence.versions.version(row).revision
        command = pending['command']
        return _receipt(command, outcome='applied', message='完整镜头结果已另存为独立新图；原图及其编辑历史保留。',
            recipe_sha256=command['recipe_sha256'], before_sha256=command['before_sha256'],
            after_sha256=command['after_sha256'], return_mode='new_image',
            result_document_id=row['document_id'], copied_original_document_id=fence.version.document_id,
            result_revision=str(revision), result_source_sha256=pending['asset_id'][7:], no_change=pending['no_change'])

    def _apply(self, command):
        self._guard()
        self._require(command)
        candidate = self.candidate
        if candidate is None or time.monotonic() >= self.candidate_deadline:
            raise ValueError('镜头候选已过期或不存在，请重新生成完整对比')
        candidate.validate_apply(command)
        self._admit_retained(self.source, self.depth, candidate)
        from .creative_document_host import CreativeHost, require_photo_return
        from .creative_document_state import create
        require_photo_return(candidate.output_asset)
        # A private return store holds ONLY the candidate; failed capture never
        # interns into the active creative-document host or history assets.
        host = CreativeHost(self.engine, self.emit)
        asset_id = host.assets.intern(candidate.output_asset)
        document = create(command['owner']['document_id'], asset_id, host.assets)
        if len(self.engine._docs) > 10_000:
            raise ValueError('Lens copy readback exceeds bounded document identity admission')
        self._require(command)  # Last cold source/revision proof before commit.
        pending = {'command': deepcopy(command), 'fence': self.fence, 'asset_id': asset_id, 'asset': candidate.output_asset,
                   'document': document, 'no_change': candidate.no_change,
                   'before_ids': frozenset(row['document_id'] for row in self.engine._docs)}
        self._save_write(command, _receipt(command, phase='unknown', message='新图提交已进入不可重发阶段；请查询同一原请求。'))
        self.uncertain = pending
        # Never register, poll, cancel or repeat this common atomic transaction.
        result = host.commit_return({'mode': 'new_image', 'rendered_asset': asset_id, 'creative_document': document})
        receipt = self._readback(pending, result.get('document_id') if type(result) is dict else None)
        if type(result) is not dict or result.get('status') != 'applied' or receipt is None:
            raise RuntimeError('Lens new-image publication lacks authoritative matching readback; query only')
        self._save_write(command, receipt)  # Persist before emitting or dropping pixels.
        self.uncertain = None
        self._drop('applied')
        return receipt

    def submit(self, command):
        command = _write(command)
        prior = self._known_write(command)
        if prior is not None:
            return prior  # No implicit retry, even for unknown or rejected.
        if command['request_id'] in self.reads:
            raise ValueError('Lens write identity collides with an earlier read request')
        self._save_write(command, _receipt(command, phase='pending', message='原镜头请求已登记；查询不会再次执行。'))
        try:
            result = self._apply(command) if command['action'] == 'apply' else self._cancel(command)
        except Exception as error:
            known = self._known_write(command)
            if known is not None and known.get('phase') == 'done' and known.get('outcome') == 'applied':
                return known  # Cleanup/publication failure cannot negate known commit.
            entered = self.uncertain is not None and self.uncertain['command']['request_id'] == command['request_id']
            result = _receipt(command, phase='unknown' if entered else 'done',
                              outcome=None if entered else 'rejected', message=_text(error))
        return self._save_write(command, result)

    def receipt(self, command):
        command = _write(command)
        prior = self._known_write(command)
        if prior is None:
            return _receipt(command, phase='unknown', message='当前进程没有原请求的提交证明；不会重新提交或推断已经取消。')
        if self.uncertain is not None and self.uncertain['command'] == command:
            result = self._readback(self.uncertain)
            if result is not None:
                self._save_write(command, result)
                self.uncertain = None
                self._drop('applied')
                return result
        return prior

    def _replay_read(self, request, old):
        if old['sha'] != command_hash(request):
            raise ValueError('Lens read identity reused with different exact content')
        if old.get('failure') is not None:
            return deepcopy(old['failure'])
        if self.source is None or self.session_id != old['session_id']:
            raise ValueError('Lens read lease was released; original read will not execute again')
        self._require({'session_id': self.session_id, 'owner': self.source.owner})
        if request['action'] == 'preview':
            if self.candidate is None or self.candidate.review['request_id'] != request['request_id']:
                raise ValueError('Lens reviewed read has been superseded; no blind read retry')
            return {'status': 'ready', 'review': self.candidate.review}
        if request['action'] == 'prepare_manual_plane':
            if self.depth is None or self.depth.asset['provenance'].get('acknowledgement_id') != request['request_id']:
                raise ValueError('Lens manual-plane read has been superseded')
        result = {'status': 'ready', 'context': self._context()}
        if request['action'] == 'current':
            result['capability'] = capability()
        return result

    def handle(self, request):
        ident = request.get('request_id') if type(request) is dict else None
        action = request.get('action') if type(request) is dict else None
        sha = None
        try:
            if not token(ident) or request.get('cmd') != 'lens_blur':
                raise ValueError('Malformed lens transport identity')
            keys = {'cmd', 'action', 'request_id'}
            if action in ('prepare_manual_plane', 'preview', 'submit', 'receipt'):
                keys.add('command')
            elif action != 'current':
                raise ValueError('Unknown lens host action')
            if set(request) != keys:
                raise ValueError('Lens host request contains missing or unknown fields')
            raw = canonical(request)
            sha = command_hash(request)
            request = json.loads(raw)
            if action != 'current':
                command = request['command']
                if type(command) is not dict or len(canonical(command)) > stage.MAX_REQUEST_BYTES:
                    raise ValueError('Lens complete inner command exceeds its exact request budget')
                if action != 'receipt' and command.get('request_id') != ident:
                    raise ValueError('Lens transport and command request identities differ')
                if action in ('preview', 'prepare_manual_plane') and command.get('action') != action:
                    raise ValueError('Lens read action differs from its exact inner command')
            self.maintain()
            if action in ('submit', 'receipt'):
                result = {'status': 'ready', 'receipt': getattr(self, action)(request['command'])}
            else:
                if ident in self.writes:
                    raise ValueError('Lens read identity collides with an earlier write request')
                old = self.reads.get(ident)
                if old is not None:
                    result = self._replay_read(request, old)
                else:
                    if len(self.reads) >= MAX_READS:
                        raise ValueError('Lens read ledger is full; retained write outcomes were not discarded')
                    self.reads[ident] = {'sha': sha, 'session_id': None}
                    try:
                        result = getattr(self, action)(request)
                        self.reads[ident]['session_id'] = self.session_id
                        if result.get('context') is None and action == 'current':
                            self.reads[ident]['failure'] = deepcopy(result)
                    except Exception as error:
                        result = {'status': 'cancelled' if isinstance(error, InterruptedError) else 'rejected', 'message': _text(error)}
                        self.reads[ident]['failure'] = deepcopy(result)
                    finally:
                        jobs(self.engine).retire(ident, sha)
        except Exception as error:
            result = {'status': 'rejected', 'message': _text(error)}
        finally:
            if action in ('current', 'prepare_manual_plane', 'preview') and sha is not None:
                jobs(self.engine).retire(ident, sha)
        self.emit({'event': 'lens_blur_result', 'request_id': ident, **result})


def service(engine, emit):
    owner = engine.__dict__.get('_lens_blur_service')
    if owner is None:
        owner = Service(engine, emit)
        engine._lens_blur_service = owner
    return owner


def handle(engine, request, emit):
    service(engine, emit).handle(request)


def read_only(request):
    return request.get('cmd') == 'lens_blur' and request.get('action') in ('current', 'prepare_manual_plane', 'preview', 'receipt')


def guard_other(engine, name, request):
    owner = engine.__dict__.get('_lens_blur_service')
    if (owner is not None and owner.uncertain is not None and name not in ('lens_blur', 'hello', 'shutdown')
            and not (name == 'session' and request.get('action') == 'query')):
        raise ValueError('镜头新图原请求结果尚未确认，其他修改暂时受保护；只能查询，不能盲目重试')


def invalidate(engine):
    """Optional lifecycle cleanup; never clear or replace the receipt owner."""
    owner = engine.__dict__.get('_lens_blur_service')
    if owner is not None:
        owner.maintain()


def dispatch_rejected(request, message, started, emit, *, engine=None):
    """Complete the outer native mailbox when a shared guard prevented entry."""
    if engine is not None and request.get('action') in ('current','prepare_manual_plane','preview'):
        try:jobs(engine).retire(request.get('request_id'),command_hash(request))
        except (ValueError,TypeError,KeyError):pass
    result = {'event': 'lens_blur_result', 'request_id': request.get('request_id'),
              'status': 'rejected', 'message': _text(message)}
    if request.get('action') in ('submit', 'receipt'):
        try:
            command = _write(request.get('command'))
            owner = service(engine, emit) if engine is not None else None
            receipt = owner._known_write(command) if owner is not None else None
            if receipt is None:
                unknown = started or request['action'] == 'receipt' or owner is None
                receipt = _receipt(command, phase='unknown' if unknown else 'done',
                    outcome=None if unknown else 'rejected', message=_text(message))
                if owner is not None and not unknown:
                    owner._save_write(command, receipt)
            result.update(status='ready', receipt=receipt)
            result.pop('message', None)  # Write envelopes carry the reason inside the exact receipt.
        except (ValueError, TypeError, KeyError, MemoryError):
            pass
    emit(result)
