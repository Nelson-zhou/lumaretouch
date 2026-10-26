# SPDX-License-Identifier: GPL-3.0-or-later
"""Cached-only explicit rule application, no worker/detection/edit ownership."""
from . import picks as PK
from . import pick_group_eye as GE


def targets(engine, command):
    indices, ids = command.get('indices'), command.get('pick_documents')
    if (type(indices) is not list or not 1 <= len(indices) <= 8
            or any(type(i) is not int for i in indices) or len(set(indices)) != len(indices)
            or type(ids) is not list or len(ids) != len(indices)
            or any(type(v) is not str or not v for v in ids)):
        raise ValueError('请选择1–8张照片，并提交精确文档身份；不会自动处理全图库')
    with engine._doclock:
        if any(not 0 <= i < len(engine._docs) for i in indices):
            raise ValueError('图库位置变化，请刷新后重试')
        if any(engine._docs[i].get('document_id') != ident for i, ident in zip(indices, ids)):
            raise ValueError('选择的文档身份变化，请刷新后重试')
        return [(engine._docs[i], engine._docs[i]['path'], engine._docs[i].get('pick')) for i in indices]


def apply(engine, command, emit):
    """Only row.pick/pick_error may change; human decisions are never rewritten."""
    try:
        if set(command) - {'cmd', 'action', 'indices', 'pick_documents', 'group_eye_rule'}:
            raise ValueError('缓存规则动作不接受测量参数')
        if 'group_eye_rule' not in command:
            raise ValueError('请显式提交规则；未修改现有提示')
        rule = GE.settings(command['group_eye_rule'])
        if engine._picks is not None and engine._picks.is_alive():
            raise ValueError('挑图任务仍在运行；请先停止或等待结束')
        rows = targets(engine, command)
        count = failed = 0
        for row, path, previous in rows:
            result, error = None, None
            try:
                if not previous:
                    raise ValueError('没有当前测量缓存；未知，不代表睁眼。请先显式测量')
                result = PK.reapply_eye_rule(previous, path, rule)
            except (KeyError, TypeError, ValueError, OSError) as exc:
                error = str(exc)
            with engine._doclock:
                if (not any(d is row for d in engine._docs) or row['path'] != path
                        or row.get('pick') is not previous):
                    failed += 1
                    continue
                # Final publication fence (also model bytes), separate from decision.
                if result is not None and not PK.reusable(result, path, result['edge'],
                                                          result['sensitivities'], result.get('model_dir')):
                    result, error = None, '来源在规则重算时变化；请显式重新测量'
                if result is not None:
                    result['overridden_by_user'] = bool(row.get('tags') or row.get('label') or row.get('trashed'))
                row['pick'], row['pick_error'] = result, error
            count += int(result is not None)
            failed += int(result is None)
        emit({'event': 'pick_done', 'action': 'group_rule', 'count': count,
              'failed': failed, 'groups': [], 'group_eye_rule': rule,
              'cached_only': True, 'measured': 0, 'running': False})
        engine.emit_session_state()
    except (KeyError, TypeError, ValueError) as exc:
        emit({'event': 'pick_failed', 'action': 'group_rule', 'error': str(exc),
              'running': bool(engine._picks is not None and engine._picks.is_alive())})
