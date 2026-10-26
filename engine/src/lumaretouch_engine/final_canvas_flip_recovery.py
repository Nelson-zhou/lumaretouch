"""Private, proved transaction outcomes. Wire flags cannot settle autosave."""

UNKNOWN_REASON = '翻转事务未确认完整回滚；请重新打开已确认的工程'


def guard_create(engine):
    runtime = engine.__dict__.get('_project_recovery_runtime')
    marker = engine.__dict__.get('_final_canvas_flip_unresolved_workspace')
    if ((marker is not None and marker == engine._document_versions().workspace)
            or (runtime is not None and runtime.tainted and runtime.reason == UNKNOWN_REASON)):
        raise ValueError('翻转结果未知；新建工程仍保留未确认的照片状态，不能用作恢复，请打开已确认工程')

def mark(engine, outcome):
    from .project_recovery_runtime import _local
    boundary = getattr(_local, 'boundary', None)
    if boundary is not None and boundary['engine'] is engine and boundary['message'].get('cmd') == 'final_canvas_flip':
        boundary['final_canvas_flip_outcome'] = outcome


def outcome(engine):
    from .project_recovery_runtime import _local
    boundary = getattr(_local, 'boundary', None)
    return boundary.get('final_canvas_flip_outcome') if boundary is not None and boundary['engine'] is engine else None


def finish(engine, boundary):
    if boundary['message'].get('cmd') != 'final_canvas_flip': return False
    runtime = engine.__dict__.get('_project_recovery_runtime')
    if not boundary['started']: return True
    outcome = boundary.get('final_canvas_flip_outcome')
    if outcome in ('no_write', 'rolled_back'): return True
    if outcome == 'applied':
        if runtime is not None: runtime.revision += 1
        return True
    engine._final_canvas_flip_unresolved_workspace = engine._document_versions().workspace
    # Preserve any earlier owner's taint/reason. A delivery failure after a
    # privately proved commit is not an unknown recipe transaction.
    if runtime is not None and not runtime.tainted:
        runtime.tainted = True
        runtime.reason = UNKNOWN_REASON
    return True
