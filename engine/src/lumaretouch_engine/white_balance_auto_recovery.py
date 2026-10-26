"""Private terminal settlement on the existing recovery boundary, no wire trust."""

UNKNOWN_REASON = '自动白平衡原事务未确认；请查询原请求或重新打开已确认的工程'


def guard_create(engine):
    runtime = engine.__dict__.get('_project_recovery_runtime')
    marker = engine.__dict__.get('_white_balance_auto_unresolved')
    if ((marker is not None and marker == engine._document_versions().workspace)
            or (runtime is not None and runtime.tainted and runtime.reason == UNKNOWN_REASON)):
        raise ValueError('自动白平衡结果未知；新建工程会保留未确认的照片状态，不能用作恢复，请打开已确认工程')


def mark(engine, phase):
    from .project_recovery_runtime import _local
    boundary = getattr(_local, 'boundary', None)
    if (boundary is not None and boundary['engine'] is engine
            and boundary['message'].get('cmd') == 'white_balance'
            and boundary['message'].get('action') == 'auto'):
        boundary['white_balance_auto_phase'] = phase
        if phase == 'unknown':
            engine._white_balance_auto_unresolved = engine._document_versions().workspace


def guard(engine, name, message):
    unresolved = engine.__dict__.get('_white_balance_auto_unresolved')
    if unresolved is None or unresolved != engine._document_versions().workspace:
        return
    # A different loaded photo is not proof that an unknown edit was recovered.
    # Local native receipt queries do not dispatch. Only state reads/shutdown or
    # the existing verified project-open recovery route can continue. Creating
    # a project keeps live _docs and is not a state-replacing recovery.
    if (name in ('hello', 'shutdown') or (name == 'session' and message.get('action') in ('state', 'query'))
            or (name == 'project' and message.get('action') == 'open')
            or (name == 'project_recovery' and message.get('action') in ('state', 'list', 'open'))):
        return
    raise ValueError('自动白平衡原事务结果未知；仅可查询原回执或重新打开已确认的工程，不能重发或继续修改')


def finish(engine, boundary, error):
    request = boundary['message']
    if request.get('cmd') != 'white_balance' or request.get('action') != 'auto':
        return False
    runtime = engine.__dict__.get('_project_recovery_runtime')
    if not boundary['started']:
        return True  # Pre-fence sample/identity rejection cannot taint saved state.
    phase = boundary.get('white_balance_auto_phase')
    if not error and boundary['returned']:
        if phase in ('rejected', 'no_change', 'rolled_back', 'replayed'):
            return True
        if phase == 'applied':
            if runtime is not None: runtime.revision += 1
            return True
    if runtime is not None and not runtime.tainted:
        runtime.tainted = True
        runtime.reason = UNKNOWN_REASON
    engine._white_balance_auto_unresolved = engine._document_versions().workspace
    return True
