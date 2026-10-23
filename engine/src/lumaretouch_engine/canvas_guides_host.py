"""Serialized view-only canvas guide commands and correlated readback."""
from copy import deepcopy
from . import canvas_guides as G


def current_row(engine):
    index = getattr(engine, '_doc_index', -1)
    rows = getattr(engine, '_docs', [])
    return rows[index] if 0 <= index < len(rows) else None


def report(engine):
    row = current_row(engine)
    # Live records have already passed the command/restore boundary. A frame
    # readback copies only visible metadata, not 64 full history snapshots.
    value = row.get(G.KEY) if row is not None else None
    if value is None:
        value = G.record()
    geometry = None
    if (row is not None and getattr(engine, '_image_loaded', False)
            and getattr(engine, '_load_id', '') and getattr(engine, '_vram', None) is not None):
        geometry = str(engine._frame_presentation(kind='edited').geometry)
    return {'protocol': 1, 'document_id': row['document_id'] if row is not None else '',
            'load_id': getattr(engine, '_load_id', ''),
            'workspace': engine._document_versions().workspace, 'geometry': geometry,
            'revision': value['revision'], **deepcopy(value['state']),
            'undo_steps': len(value['undo']), 'redo_steps': len(value['redo']),
            'max_lines': G.MAX_LINES, 'max_history': G.MAX_HISTORY,
            'view_only': True}


def rejected(engine, command, error, emit):
    emit({'event': 'canvas_guides_result', 'request_id': command.get('request_id'),
          'action': command.get('action'), 'success': False, 'error': str(error),
          'canvas_guides': report(engine)})


class CanvasGuides:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.receipts, self.workspace = {}, None

    def handle(self, command):
        e, emit = self.engine, self.emit
        try:
            rid = G.identifier(command.get('request_id'))
            workspace = e._document_versions().workspace
            if workspace != self.workspace:
                self.receipts.clear()
                self.workspace = workspace
            if rid in self.receipts:
                request, event = self.receipts[rid]
                if request != command:
                    raise ValueError('参考线请求身份冲突，未重试')
                emit(deepcopy(event))
                return
            action = command.get('action')
            keys = {'cmd', 'action', 'request_id', 'document_id', 'workspace', 'revision', 'geometry', 'load_id'}
            if action == 'set':
                keys.add('state')
            if command.get('cmd') != 'canvas_guides' or set(command) - keys:
                raise ValueError('参考线命令包含未知字段')
            if action not in ('state', 'set', 'undo', 'redo'):
                raise ValueError('未知参考线动作')
            row = current_row(e)
            changed = False
            if action != 'state':
                if (row is None or row.get('trashed') or not getattr(e, '_image_loaded', False)
                        or not getattr(e, '_load_id', '')):
                    raise ValueError('请先打开一张照片再编辑参考线')
                if command.get('document_id') != row['document_id'] or command.get('workspace') != workspace:
                    raise ValueError('文档或工程已切换，参考线修改未应用')
                if command.get('load_id') != e._load_id:
                    raise ValueError('照片已重新载入，参考线修改未应用')
                if type(command.get('geometry')) is not str or command['geometry'] != report(e)['geometry']:
                    raise ValueError('画布裁剪或旋转已变化，参考线修改未应用')
                before = G.record(row.get(G.KEY))
                revision = command.get('revision')
                if type(revision) is not int or revision != before['revision']:
                    raise ValueError('参考线已变化，请刷新后重试')
                after = G.change(before, action, command.get('state'))
                changed = after != before
                if changed:
                    # The only publication point. Never touch row.state/undo/redo,
                    # image revisions, render, captures, or export snapshots.
                    row[G.KEY] = after
                    e._project_dirty = True
                    # This atomic view publication has no partial pixel state.
                    # Rejected stale/no-op guide requests must not taint recovery.
                    recovery = getattr(e, '_project_recovery_runtime', None)
                    if recovery is not None:
                        recovery.revision += 1
            event = {'event': 'canvas_guides_result', 'request_id': rid, 'action': action,
                     'success': True, 'changed': changed, 'canvas_guides': report(e)}
            self.receipts[rid] = (deepcopy(command), deepcopy(event))
            while len(self.receipts) > 128:
                self.receipts.pop(next(iter(self.receipts)))
            emit(event)
            if changed:
                emit({'event': 'project_state', **e._project_state()})
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            rejected(e, command, error, emit)


def handle(engine, command, emit):
    owner = getattr(engine, '_canvas_guides_controller', None)
    if owner is None:
        owner = CanvasGuides(engine, emit)
        engine._canvas_guides_controller = owner
    owner.handle(command)
