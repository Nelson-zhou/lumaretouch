"""Ordinary queue control identity/preflight. No output or source file operations."""
from __future__ import annotations
import copy
import json
import uuid
from . import tasks as T

PREFIX = 'lrt-task-control:'
TERMINAL = (T.SUCCEEDED, T.FAILED, T.CANCELLED)


def current_owner(host):
    versions = host._document_versions()
    return {'project_id': (host._project or {}).get('project_id'),
            'workspace_generation': versions.workspace, 'session_id': versions.owner}


def bind(host, task):
    # Only creation/restore may establish authority; list/readback never adopts it.
    task['_control_owner'] = current_owner(host)
    task['_control_token'] = uuid.uuid4().hex
    task.pop('_control_result', None)


def require_owner(host, task):
    if task.get('_control_owner') != current_owner(host):
        raise T.TaskError('任务属于另一工程/工作区/会话；保留旧记录但拒绝接管')


def receipt(task, request_id, action, success, **extra):
    return {**task['_control_owner'], 'task_id': task['task_id'],
            'token': task['_control_token'], 'request_id': request_id,
            'action': action, 'success': success, **extra}


def metadata(host, task):
    token = task.get('_control_token')
    owner = task.get('_control_owner') or {}
    available = bool(token) and owner == current_owner(host)
    live = host._task_worker_is_live(task)
    state = task['state']
    allowed = []
    if live and state in (T.QUEUED, T.RUNNING, T.RETRYING):
        allowed.append('pause')
    restored = bool(task.get('_restored_snapshot') and task.get('recipe_persisted')
                    and host._task_args.get(task['task_id']))
    if state == T.PAUSED and (live or (restored and not (host._export and host._export.is_alive()))):
        allowed.append('resume')
    if state in T.LIVE_STATES and state != T.CANCELLING:
        allowed.append('cancel')
    if not live and state in TERMINAL:
        allowed.append('delete')
        if task.get('recipe_persisted') and host._task_args.get(task['task_id']) and T.pending_items(task) and not (host._export and host._export.is_alive()):
            allowed.append('retry')
    return {'protocol': 1, 'token': token, **owner, 'available': available,
            'revision': str(task['updated_ns']), 'allowed': allowed if available else [],
            'result': task.get('_control_result')}


def resolve(host, value):
    if not isinstance(value, str) or not value.startswith(PREFIX):
        raise T.TaskError('任务变更需要精确会话/工程/工作区引用；不接受裸 ID、默认任务或 all')
    try:
        ref = json.loads(value[len(PREFIX):])
        task = host._tasks[ref['task_id']]
        require_owner(host, task)
        owner = task['_control_owner']
        if ref['token'] != task.get('_control_token') or any(ref.get(key) != value for key, value in owner.items()):
            raise ValueError('任务或工程/工作区/会话身份已变化')
        if not isinstance(ref['request_id'], str) or not 1 <= len(ref['request_id']) <= 100:
            raise ValueError('缺少请求身份')
        return task, ref['request_id'], ref.get('revision')
    except (ValueError, KeyError, TypeError) as error:
        raise T.TaskError(f'拒绝过期或无效的任务引用：{error}') from error


def preflight(host, targets, action):
    # No mutation before ALL members pass. Multiple retry workers are not supported.
    if action == 'retry' and len(targets) != 1:
        raise T.TaskError('重试必须指定唯一任务；不启动部分批次')
    for task in targets:
        require_owner(host, task)
        sample = copy.deepcopy(task)
        live = host._task_worker_is_live(task)
        if action == 'pause' and not live:
            raise T.TaskError('任务没有正在运行的 worker')
        if action == 'resume' and not live:
            if (not task.get('_restored_snapshot') or not task.get('recipe_persisted')
                    or not host._task_args.get(task['task_id'])
                    or (host._export and host._export.is_alive())):
                raise T.TaskError('没有可恢复的认证快照或已有 worker；不能继续')
        if action == 'pause': T.request_pause(sample)
        elif action == 'resume': T.request_resume(sample)
        elif action == 'cancel':
            if sample['state'] != T.CANCELLING: T.request_cancel(sample)
        elif action == 'retry':
            if live or (host._export and host._export.is_alive()):
                raise T.TaskError('已有 worker；不能重复启动')
            T.begin_retry(sample)
        elif action == 'delete' and (live or task['state'] not in TERMINAL):
            raise T.TaskError('只能删除已结束且 worker 已退出的任务记录；文件始终保留')


def start(host, task):
    with host._task_lock:
        if task['state'] in (T.QUEUED, T.RETRYING):
            T.transit(task, T.RUNNING, 'worker 开工')
            host._emit_task(task, '开工')
        # A queued pause/cancel must survive worker startup; boundary handles it.


def finish(host, task, stopped):
    with host._task_lock:
        counts = T.counts(task)
        if stopped or task['state'] == T.CANCELLING:
            if task['state'] != T.CANCELLING:
                T.transit(task, T.CANCELLING, '边界上确认取消')
            T.transit(task, T.CANCELLED, f"{counts['succeeded']} 条已提交输出原样保留")
        elif counts['failed']:
            T.transit(task, T.FAILED, f"{counts['failed']} 条失败")
        else:
            # Last item already committed: no remaining boundary to pause at.
            T.transit(task, T.SUCCEEDED, f"{counts['succeeded']} 条已提交，{counts['skipped']} 条跳过")
        host._emit_task(task, '收尾')
