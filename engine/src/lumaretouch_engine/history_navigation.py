"""Bounded navigation of the EXISTING retained chain, never a second history store.

Only metadata crosses the wire. Every edge is the canonical adjacent controller
transition, including its sparse people/body ownership guards and rendering.
"""
from copy import deepcopy
from .optics_candidate_identity import fingerprint

COMMAND = 'history_navigation'
REQUEST_PREFIX = 'history-nav-v1:'
MAX_HISTORY = 64  # Protocol budget; the actual owner supplies its smaller limit.
VIEW_FIELDS = {'workspace', 'document_id', 'load_id', 'revision', 'digest',
               'cursor', 'undo_steps', 'redo_steps', 'history_max'}
UNKNOWN_REASON = '历史跳转结果未确认；请查询原操作或重新打开已确认的工程'


def navigation_id(value):
    return (type(value) is str and value.startswith(REQUEST_PREFIX)
            and len(REQUEST_PREFIX) < len(value.encode('utf-8')) <= 128 and '\0' not in value)


def borrowed_namespace(value):
    if type(value) is dict:
        return any(((key == 'id' or key.endswith('_id')) and type(item) is str
                    and item.startswith(REQUEST_PREFIX)) or borrowed_namespace(item)
                   for key, item in value.items())
    if type(value) is list:
        return any(borrowed_namespace(item) for item in value)
    return False


def namespace_allowed(request):
    if type(request) is not dict:
        return True  # Ordinary parser/type validation remains the existing owner.
    return (navigation_id(request.get('request_id')) if request.get('cmd') == COMMAND
            else not borrowed_namespace(request))


def reader_namespace_allowed(line):
    """Reject borrowing BEFORE read/cancel controllers see a reader-thread line.

    Return False only to bypass ingress controllers; the original line is still
    queued for executor-side rejection and its normal command_done acknowledgement.
    """
    import json
    try:
        return namespace_allowed(json.loads(line))
    except (ValueError, TypeError):
        return True  # Keep existing malformed JSON handling, not reader shutdown.


def admit_namespace(request):
    if not namespace_allowed(request):
        raise ValueError('历史导航请求身份为保留命名空间；其他操作未执行')


def exact(value):
    return fingerprint(value, exact=True)


def identity(engine):
    if not engine._image_loaded or not 0 <= engine._doc_index < len(engine._docs):
        raise ValueError('尚未载入可读取历史的照片')
    row = engine._docs[engine._doc_index]
    versions = engine._document_versions()
    version = versions.version(row)
    return {'workspace': versions.workspace, 'document_id': version.document_id,
            'load_id': str(engine._load_id), 'revision': str(version.revision)}


def checkpoint(engine):
    """Exact current/ordered stack/graph evidence; no rounding or skipped fences."""
    history = engine._history_controller()
    limit = history.limit
    if type(limit) is not int or not 1 <= limit <= MAX_HISTORY:
        raise ValueError('历史保留上限超出当前导航协议')
    if len(history.undo) > limit or len(history.redo) > limit:
        raise ValueError('历史栈超出实际保留上限')
    current = engine._history_capture()
    graph = engine._people_owner() if engine._people_managed() else None
    proof = (identity(engine), current, history.undo, history.redo,
             history.group, history.group_ns,
             None if graph is None else (graph.snapshot(), graph.fence,
                                        graph.association_fence, graph.asset_fences))
    view = {**identity(engine), 'digest': exact(proof), 'cursor': len(history.undo),
            'undo_steps': len(history.undo), 'redo_steps': len(history.redo), 'history_max': limit}
    # Snapshot and owner references stay private and are used only during this
    # serialized command. They are not replay authority or a retained ledger.
    return view, current, list(history.undo), list(history.redo)


def validate_view(value):
    if type(value) is not dict or set(value) != VIEW_FIELDS:
        raise ValueError('历史选择缺少完整绑定')
    for key in ('workspace', 'document_id', 'load_id'):
        if type(value[key]) is not str or not 1 <= len(value[key]) <= 128:
            raise ValueError('历史身份无效')
    revision = value['revision']
    if (type(revision) is not str or not revision.isascii() or not revision.isdecimal()
            or str(int(revision)) != revision or not 0 <= int(revision) < 2**64):
        raise ValueError('历史版本无效')
    digest = value['digest']
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('历史摘要无效')
    if any(type(value[k]) is not int for k in ('cursor', 'undo_steps', 'redo_steps', 'history_max')):
        raise ValueError('历史步数无效')
    limit = value['history_max']
    if not 1 <= limit <= MAX_HISTORY or value['cursor'] != value['undo_steps'] or not all(0 <= value[k] <= limit for k in ('undo_steps', 'redo_steps')):
        raise ValueError('历史步数超出保留范围')
    return value


def plan(request):
    if type(request) is not dict or request.get('cmd') != COMMAND:
        raise ValueError('历史请求无效')
    rid = request.get('request_id')
    if not navigation_id(rid):
        raise ValueError('历史请求缺少有界身份')
    from .named_recipe_versions import ACTIONS, validate_request
    if request.get('action') in ACTIONS:
        return validate_request(request)
    if request.get('action') == 'state' and set(request) == {'cmd', 'action', 'request_id'}:
        return None
    if request.get('action') != 'navigate' or set(request) != {'cmd', 'action', 'request_id', 'view', 'target'}:
        raise ValueError('历史请求字段无效')
    view = validate_view(request['view'])
    target = request['target']
    total = view['undo_steps'] + view['redo_steps']
    if type(target) is not int or not 0 <= target <= total:
        raise ValueError('所选历史已不在保留范围')
    if total > view['history_max']:
        raise ValueError('此历史的两侧总长度超过保留上限；为避免跳转时淘汰端点，未修改')
    delta = target - view['cursor']
    if int(view['revision']) + abs(delta) >= 2**64:
        raise ValueError('文档版本不足以完成此跳转；请保存并重新打开工程')
    return ('redo' if delta > 0 else 'undo', abs(delta))


def mark(engine, phase):
    from .project_recovery_runtime import _local
    boundary = getattr(_local, 'boundary', None)
    if boundary is not None and boundary['engine'] is engine and boundary['message'].get('cmd') == COMMAND:
        boundary['history_navigation_phase'] = phase
    if phase == 'unknown':
        engine._history_navigation_unresolved = engine._document_versions().workspace
    elif phase in ('applied', 'partial', 'rejected', 'no_change'):
        engine.__dict__.pop('_history_navigation_unresolved', None)


def guard(engine, name, message):
    if engine.__dict__.get('_history_navigation_unresolved') is None:
        return
    if (name in ('hello', 'shutdown') or (name == 'session' and message.get('action') in ('state', 'query'))
            or (name == 'project' and message.get('action') in ('open', 'state'))):
        return
    raise ValueError(UNKNOWN_REASON + '；新建工程、切照片或等待不能恢复，不能继续编辑或重发')


def finish(engine, boundary):
    if boundary['message'].get('cmd') != COMMAND:
        return False
    if boundary['message'].get('action') in ('state', 'named_state') or not boundary['started']:
        return True
    runtime = engine.__dict__.get('_project_recovery_runtime')
    phase = boundary.get('history_navigation_phase')
    if phase in ('rejected', 'no_change', 'replayed'):
        return True
    if phase in ('applied', 'partial'):
        if runtime is not None: runtime.revision += 1
        return True
    mark(engine, 'unknown')
    if runtime is not None and not runtime.tainted:
        runtime.tainted = True
        runtime.reason = UNKNOWN_REASON
    return True


def packet(request):
    return {'event': 'history_navigation_result', 'protocol': 1,
            'request_id': request.get('request_id'), 'original_request': deepcopy(request),
            'success': False, 'outcome_unknown': False, 'requires_reload': False,
            'phase': 'rejected', 'completed_steps': 0, 'reached': None, 'last_confirmed': None}


def navigate(engine, request, result):
    direction, count = plan(request)
    before = checkpoint(engine)
    if before[0] != request['view']:
        raise ValueError('照片、载入、版本或实际历史已变化；旧选择失效，请刷新历史')
    history = engine._history_controller()
    owned_row = engine._docs[engine._doc_index]
    owned_versions = engine._document_versions()
    owned_graph = engine._people_owner() if engine._people_managed() else None
    result['last_confirmed'] = deepcopy(before[0])
    result['reached'] = deepcopy(before[0])
    if not count:
        result.update(success=True, phase='no_change')
        mark(engine, 'no_change')
        return
    for index in range(count):
        # Any failure to re-establish the current checkpoint (including after a
        # conservative revision fence) must not leave an old reached claim.
        mark(engine, 'unknown')
        result['reached'] = None
        # Between adjacent steps the same session and exact checkpoint must hold.
        # No count of queue ACKs and no arbitrary old full-snapshot apply exists.
        if (engine._docs[engine._doc_index] is not owned_row or engine._document_versions() is not owned_versions
                or (owned_graph is not None and engine._people_owner() is not owned_graph)
                or checkpoint(engine)[0] != before[0]):
            raise RuntimeError('历史步骤之间的实际所有权或状态变化；结果需要核对')
        reason = engine._history_guard(direction)
        if reason:
            result.update(phase='partial' if index else 'rejected', reached=before[0],
                          last_confirmed=before[0], error=reason)
            mark(engine, result['phase'])
            return
        # Mirror legacy per-edge revision fencing, but retain the exact reached
        # state AFTER that conservative attempt fence even on prewrite refusal.
        engine._fence_current_document()
        before = checkpoint(engine)
        trace = {}
        outcome = history.handle_command({'cmd': 'history', 'action': direction}, trace=trace)
        if outcome.get('status') != 'applied':
            # Legacy rollback can increment graph/body fences or partially restore
            # a frame. Returning normally from restore is NOT proof of rollback.
            if trace.get('restore_entered') or outcome.get('status') == 'unknown':
                raise RuntimeError(outcome.get('message') or '历史相邻步骤未确认完成')
            actual = checkpoint(engine)
            if actual[0] != before[0]:
                raise RuntimeError('历史拒绝后的状态证明已变化')
            result.update(phase='partial' if index else 'rejected', reached=actual[0],
                          last_confirmed=actual[0], error=outcome.get('message') or '历史相邻步骤被拒绝')
            mark(engine, result['phase'])
            return
        actual = checkpoint(engine)
        from .body_pose_history_chain import decorate
        undo, redo = list(before[2]), list(before[3])
        stack, other = (undo, redo) if direction == 'undo' else (redo, undo)
        stack.pop()
        other.append(decorate(before[1], actual[1]))
        # Topology and the exact reverse sparse patch are proved, not inferred
        # from equal stack counts or an old full snapshot's recipe signature.
        if (exact((undo, redo)) != exact((actual[2], actual[3]))
                or any(actual[0][k] != before[0][k] for k in ('workspace', 'document_id', 'load_id', 'revision'))
                or actual[0]['cursor'] != request['view']['cursor'] + (index + 1) * (1 if direction == 'redo' else -1)):
            raise RuntimeError('历史提交后的实际相邻链证明不匹配')
        # Navigation is a document mutation even after a save cleared dirty.
        # Do not create a new history entry or alter ordinary undo/redo behavior.
        history.ports.mark_dirty()
        result.update(completed_steps=index + 1, reached=actual[0], last_confirmed=actual[0])
        before = actual
    result.update(success=True, phase='applied')
    mark(engine, 'applied')


def command(engine, request, emit):
    guard(engine, COMMAND, request)  # Direct callers cannot replay an unresolved mutation.
    mark(engine, 'rejected')
    route = plan(request)
    receipts = engine.__dict__.setdefault('_history_navigation_receipts', {})
    rid = request['request_id']
    if rid in receipts:
        original, retained = receipts[rid]
        if original != request: raise ValueError('历史请求身份冲突；未修改')
        mark(engine, 'replayed')
        emit(deepcopy(retained))
        return
    if len(receipts) >= 4096: raise ValueError('历史导航回执容量已满；请保存并重启应用')
    result = packet(request)
    try:
        if route is None:
            state_view = checkpoint(engine)[0]
            metadata = {}
            if request['action'] == 'named_state':
                from .named_recipe_versions import catalog
                metadata = catalog(engine)
            result.update(success=True, phase='state', view=state_view, **metadata)
            if request['action'] == 'named_state':
                from .named_recipe_versions import check_packet
                check_packet(result)
        elif route[0] == 'named':
            from .named_recipe_versions import apply
            apply(engine, request, result, emit)
        else:
            navigate(engine, request, result)
    except Exception as error:
        from .project_recovery_runtime import _local
        boundary = getattr(_local, 'boundary', None)
        phase = None if boundary is None else boundary.get('history_navigation_phase')
        # Once a successful edge has happened or the restore boundary was entered,
        # an exception without the exact current proof is unknown, never target success.
        unknown = phase == 'unknown' or engine.__dict__.get('_history_navigation_unresolved') is not None or bool(result['completed_steps'])
        if request.get('action', '').startswith('named_'):
            result = packet(request)  # Exact phase envelope; no stale view/catalog on refusal.
        result.update(success=False, phase='unknown' if unknown else 'rejected',
                      outcome_unknown=unknown, requires_reload=unknown, error=str(error)[:2000])
        if unknown:
            result['reached'] = None
            mark(engine, 'unknown')
    if request.get('action', '').startswith('named_') and result['phase'] in ('rejected', 'unknown'):
        from .named_recipe_versions import bound_error
        bound_error(result)
    receipts[rid] = (deepcopy(request), deepcopy(result))
    emit(deepcopy(result))


def dispatch_rejected(engine, request, error, started, emit):
    retained = engine.__dict__.get('_history_navigation_receipts', {}).get(request.get('request_id'))
    if retained is not None and retained[0] == request:
        emit(deepcopy(retained[1]))
        return
    result = packet(request)
    from .project_recovery_runtime import _local
    boundary = getattr(_local, 'boundary', None)
    phase = None if boundary is None else boundary.get('history_navigation_phase')
    unknown = started and request.get('action') in ('navigate', 'named_create', 'named_rename', 'named_select') and phase not in ('rejected', 'no_change')
    result.update(phase='unknown' if unknown else 'rejected', outcome_unknown=unknown,
                  requires_reload=unknown, error=str(error)[:2000])
    if unknown: mark(engine, 'unknown')
    if request.get('action', '').startswith('named_'):
        from .named_recipe_versions import bound_error
        bound_error(result)
    emit(result)
