# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned current-photo portrait crop capture/review/commit service.

All methods run on the existing serialized engine command thread. The reader
may only set cancellation Events. No source override, parallel history stack,
transfer alias, alternate sampler or model fallback is introduced.
AUTHORED / UNRUN: no real photo/native/UI/runtime acceptance is claimed.
"""
from collections import OrderedDict
from copy import deepcopy
import json
import time
import uuid

from . import portrait_crop_capture as C
from . import portrait_crop_review as R
from . import portrait_crop_project as P
from .portrait_crop_controller import command_hash, controller as jobs, valid_id, digest, canonical, READS

VERSION = 1
MAX_RECEIPTS = 512
MAX_WRITE_RECEIPTS = 128
MAX_RECEIPT_BYTES = 128 * 1024 * 1024
READ_RESERVE = 48 * 1024 * 1024
SESSION_SECONDS = 600.
CANDIDATE_SECONDS = 180.
COMMON = {'cmd', 'action', 'request_id'}
FIELDS = {
    'capability': COMMON, 'current': COMMON,
    'preview': COMMON | {'session_id', 'capture_sha256', 'face_id', 'anchors', 'rules', 'anchor_review'},
    'apply': COMMON | {'session_id', 'capture_sha256', 'preview_request_id', 'preview_token',
                      'candidate_sha256', 'before_image_sha256', 'after_image_sha256', 'review'},
    'cancel': COMMON | {'session_id'}, 'status': COMMON | {'target_request_id'},
}


def capability(engine):
    from .portrait_crop_planner import capability as planner_capability
    reason = None
    from .final_canvas_flip_state import active as flip_active, REASON as FLIP_REASON
    planner = planner_capability()
    if flip_active(getattr(engine, '_final_canvas_flip', None)):
        reason = FLIP_REASON
    elif not planner['available']:
        reason = planner.get('reason') or 'Packaged portrait crop planner is unavailable'
    elif not callable(getattr(engine, '_commit_portrait_crop_candidate', None)):
        reason = 'Canonical portrait crop history integration is unavailable'
    elif not C.rotation_supported({'_crop_rotation': getattr(engine, '_crop_rotation', None)}):
        reason = C.ROTATION_REASON
    else:
        try:
            # Construction checks installed plugin/model paths only; never
            # downloads weights, initializes graphs or performs inference.
            from .face import build
            with build('mediapipe'):
                pass
            from .sample_library_capture import capture_reason
            reason = capture_reason(engine)
        except Exception as error:
            reason = str(error)
    return {'version': VERSION, 'operation_id': P.OPERATION_ID, 'available': not bool(reason),
            'reason': reason, 'supported_rotation_degrees': [0], 'planner': planner,
            'analysis': 'fresh_whole_frame_display_proxy', 'runtime_acceptance': 'UNRUN'}


def _validate(request):
    sha = command_hash(request)
    action = request['action']
    if action not in FIELDS or set(request) != FIELDS[action]:
        raise ValueError('Unsupported or malformed exact portrait crop request')
    for key in ('session_id', 'preview_request_id', 'preview_token', 'target_request_id'):
        if key in request and not valid_id(request[key]):
            raise ValueError('Invalid portrait crop ' + key)
    for key in ('capture_sha256', 'candidate_sha256', 'before_image_sha256', 'after_image_sha256'):
        if key in request and not digest(request[key]):
            raise ValueError('Invalid portrait crop ' + key)
    if action == 'apply' and request['review'] != 'full_before_after_confirmed':
        raise ValueError('Portrait crop apply requires explicit complete before/after photographic review')
    if action == 'preview' and not valid_id(request['face_id']):
        raise ValueError('Portrait crop requires a selected genuine fresh face identity')
    return sha


def _event(request, sha, phase, **facts):
    return {'event': 'portrait_crop_result', 'version': VERSION,
            'request_id': request.get('request_id') if type(request) is dict else None,
            'action': request.get('action') if type(request) is dict else None,
            'command_sha256': sha, 'original_request': deepcopy(request), 'phase': phase, **facts}


class Service:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.capture = None
        self.candidate = None
        self.session_id = None
        self.deadline = 0.
        self.candidate_deadline = 0.
        self.receipts = OrderedDict()
        self.uncertain = None

    def _drop(self):
        self.capture = self.candidate = self.session_id = None
        self.deadline = self.candidate_deadline = 0.

    def maintain(self):
        if self.uncertain is not None:
            return
        if self.capture is not None and (time.monotonic() >= self.deadline or self.capture.stale(self.engine)):
            self._drop()
        elif self.candidate is not None and time.monotonic() >= self.candidate_deadline:
            self.candidate = None
            self.candidate_deadline = 0.

    def _size(self):
        return sum(len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'))
                   for value in self.receipts.values())

    def _admit(self, request):
        # Write identity/results are never evicted. Released read image payloads
        # cannot cause re-execution; replay returns an explicit no-write refusal.
        reserve = READ_RESERVE if request['action'] in READS else 256 * 1024
        if len(self.receipts) >= MAX_RECEIPTS:
            raise ValueError('Portrait crop receipt capacity reached; no new work submitted')
        if request['action'] == 'apply' and sum(row['action'] == 'apply' for row in self.receipts.values()) >= MAX_WRITE_RECEIPTS:
            raise ValueError('Portrait crop canonical write-receipt capacity reached')
        if self._size() + reserve > MAX_RECEIPT_BYTES:
            for key, record in list(self.receipts.items()):
                if record['action'] not in READS or record['phase'] in ('working', 'unknown', 'rejected'):
                    continue
                self.receipts[key] = _event(record['original_request'], record['command_sha256'], 'rejected',
                    no_write=True, released_read=True,
                    message='Completed source/review display bytes were released; request a new current source, not a write retry')
                if self._size() + reserve <= MAX_RECEIPT_BYTES:
                    break
        if self._size() + reserve > MAX_RECEIPT_BYTES:
            raise ValueError('Portrait crop receipt memory budget reached; no new work submitted')

    def _guard(self):
        from .final_canvas_flip_state import require_processing_capture
        require_processing_capture(self.engine)
        if self.uncertain is not None:
            raise ValueError('原人像裁剪提交结果尚未核实，请只查询原请求，不要重复应用或假装取消')
        from .sample_library_capture import capture_reason
        reason = capture_reason(self.engine)
        if reason:
            raise ValueError(reason)
        if not callable(getattr(self.engine, '_commit_portrait_crop_candidate', None)):
            raise ValueError('Canonical portrait crop history integration is unavailable')

    def _current(self, request):
        self._guard()
        cap = capability(self.engine)
        if not cap['available']:
            raise ValueError(cap['reason'])
        self._drop()
        from .creative_document_host import memory_budget
        captured = jobs(self.engine).run(request, lambda stopped: C.capture_current(self.engine,
            max_bytes=min(C.MAX_WORK_BYTES, memory_budget()), cancelled=stopped))
        self.capture = captured
        self.session_id = uuid.uuid4().hex
        self.deadline = time.monotonic() + SESSION_SECONDS
        return {'phase': 'current_ready', 'current': {'session_id': self.session_id,
            'capture_sha256': captured.capture_sha256, 'binding': deepcopy(captured.binding),
            'source': deepcopy(captured.source), 'before': deepcopy(captured.before)}}

    def _require_current(self, request):
        self._guard()
        if (self.capture is None or self.session_id != request['session_id']
                or request.get('capture_sha256', self.capture.capture_sha256) != self.capture.capture_sha256):
            raise ValueError('Portrait crop current source/session has expired or changed')
        self.capture.verify(self.engine)

    def _preview(self, request):
        self._require_current(request)
        self.candidate = None
        capture = self.capture
        result = jobs(self.engine).run(request, lambda stopped: R.prepare(self.engine, capture, request,
            cancelled=lambda: stopped() or capture.stale(self.engine)))
        self.candidate = result
        self.candidate_deadline = time.monotonic() + CANDIDATE_SECONDS
        return {'phase': 'ready', 'preview': deepcopy(result.preview)}

    def _apply(self, request, sha):
        self._require_current(request)
        candidate = self.candidate
        if candidate is None:
            raise ValueError('Portrait crop full candidate review has expired or is not ready')
        preview = candidate.preview
        expected = {key: preview[key] for key in ('capture_sha256', 'preview_request_id', 'preview_token', 'candidate_sha256')}
        expected.update(before_image_sha256=preview['before']['sha256'], after_image_sha256=preview['after']['sha256'])
        if any(request[key] != value for key, value in expected.items()):
            raise ValueError('Portrait crop apply does not acknowledge its exact full before/after candidate')
        # All available validations happen before the uncertain mutation fence.
        P.verify_commit(self.engine, self.capture.state, candidate.state, candidate.proof)
        pending = _event(request, sha, 'unknown', outcome_unknown=True,
                         original_request_id=request['request_id'],
                         message='裁剪已进入唯一历史提交边界，请核对原请求，不要重发')
        self.receipts[request['request_id']] = pending
        self.uncertain = {'request': deepcopy(request), 'sha': sha, 'candidate': candidate,
                          'capture': self.capture}
        self.emit(deepcopy(pending))
        result = P.commit(self.engine, before_state=self.capture.state, candidate_state=candidate.state,
                          proof=candidate.proof, request_id=request['request_id'])
        return self._confirm_commit(request, result)

    def _confirm_commit(self, request, result, *, recovered=False):
        pending = self.uncertain
        if pending is None or pending['request'] != request:
            raise ValueError('Portrait crop canonical outcome lacks its original mutation identity')
        candidate, captured = pending['candidate'], pending['capture']
        if (type(result) is not dict or result.get('status') not in ('applied', 'no_change')
                or result.get('document_id') != captured.binding['document_id']
                or type(result.get('revision')) not in (int, str)):
            raise RuntimeError('Canonical portrait crop outcome is not proven; only query the original request')
        if not recovered:
            from .optics_candidate_identity import fingerprint
            live = self.engine._capture_state()
            version = self.engine._document_versions().version(self.engine._docs[self.engine._doc_index])
            if (version.document_id != result['document_id'] or str(version.revision) != str(result['revision'])
                    or P.non_crop_hash(live) != captured.binding['non_crop_sha256']
                    or fingerprint(live['_crop_rect']) != fingerprint(candidate.state['_crop_rect'])
                    or fingerprint(live['_crop_rotation']) != fingerprint(captured.state['_crop_rotation'])
                    or C.file_hash(captured.row['path']) != captured.binding['original_sha256']):
                raise RuntimeError('Portrait crop post-commit source/edit proof disagrees; outcome remains uncertain')
        # A recovered canonical receipt is historical outcome evidence, not a
        # claim the user has not edited or switched documents since that commit.
        self.uncertain = None
        self._drop()
        return {'phase': 'committed', 'result': deepcopy(result),
                'preview_token': candidate.preview['preview_token'],
                'candidate_sha256': candidate.preview['candidate_sha256'],
                'original_request_id': request['request_id'], 'recovered': recovered}

    def _status(self, request):
        ident = request['target_request_id']
        record = self.receipts.get(ident)
        if record is not None and record['phase'] == 'unknown' and self.uncertain is not None:
            method = getattr(self.engine, '_portrait_crop_candidate_status', None)
            if callable(method) and self.uncertain['request']['request_id'] == ident:
                result = method(ident)
                if result is not None:
                    original = self.uncertain['request']
                    sha = self.uncertain['sha']
                    facts = self._confirm_commit(original, result, recovered=True)
                    record = _event(original, sha, **facts)
                    self.receipts[ident] = record
        if record is None:
            return {'phase': 'unknown', 'outcome_unknown': True,
                    'original_request_id': ident, 'message': 'No retained original request receipt; absence never authorizes replay'}
        return {'phase': 'status', 'receipt': deepcopy(record)}

    def handle(self, request):
        sha = None
        ident = request.get('request_id') if type(request) is dict else None
        action = request.get('action') if type(request) is dict else None
        retained = False
        try:
            # Keep exact identity even for a safe schema rejection so the reader
            # registration can retire and the UI can verify the refusal echo.
            sha = command_hash(request)
            _validate(request)
            old = self.receipts.get(ident)
            if old is not None:
                if old['command_sha256'] != sha or old['original_request'] != request:
                    raise ValueError('Portrait crop request identity reused with different content')
                self.emit(deepcopy(old))
                return
            self.maintain()
            # Status must remain accessible even if every write receipt slot is
            # occupied. Do not recursively store status wrappers with imagery.
            if action != 'status':
                self._admit(request)
            if action in READS:
                working = _event(request, sha, 'working', no_write=True)
                self.receipts[ident] = working
                retained = True
                self.emit(deepcopy(working))
            if action == 'capability':
                facts = {'phase': 'capability', 'capability': capability(self.engine)}
            elif action == 'current':
                facts = self._current(request)
            elif action == 'preview':
                facts = self._preview(request)
            elif action == 'apply':
                facts = self._apply(request, sha)
            elif action == 'status':
                facts = self._status(request)
            else:
                self._guard()
                if self.session_id is not None and self.session_id != request['session_id']:
                    raise ValueError('Portrait crop cancellation belongs to another session')
                self._drop()
                facts = {'phase': 'cancelled', 'no_write': True, 'message': 'Portrait crop session released; original photo and edits unchanged'}
            event = _event(request, sha, **facts)
        except InterruptedError as error:
            event = _event(request, sha, 'cancelled', no_write=True, message=str(error)[:2000])
        except Exception as error:
            unknown = action == 'apply' and self.uncertain is not None and self.uncertain['request'].get('request_id') == ident
            event = _event(request, sha, 'unknown' if unknown else 'rejected',
                **({'outcome_unknown': True, 'original_request_id': ident} if unknown else {'no_write': True}),
                message=str(error)[:2000])
        if action in READS and sha is not None:
            jobs(self.engine).retire(ident, sha)
        if action != 'status' and valid_id(ident) and sha is not None and (retained or ident not in self.receipts) and len(self.receipts) < MAX_RECEIPTS:
            self.receipts[ident] = deepcopy(event)
        elif action == 'apply' and sha is not None and ident in self.receipts and self.receipts[ident]['command_sha256'] == sha:
            self.receipts[ident] = deepcopy(event)
        self.emit(event)


def service(engine, emit):
    owner = engine.__dict__.get('_portrait_crop_service')
    if owner is None:
        owner = engine._portrait_crop_service = Service(engine, emit)
    return owner
