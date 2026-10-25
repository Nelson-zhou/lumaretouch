# SPDX-License-Identifier: GPL-3.0-or-later
"""Background catalogue mutations never mutate a photograph or colour sample."""
from copy import deepcopy
from hashlib import sha256
import base64
import time
from . import background_material_state as S, background_material_images as I, background_material_query as Q
from .background_material_store import Store

OPERATIONS = {'group_create': {'name'}, 'group_rename': {'id', 'name'},
              'group_delete': {'id'}, 'group_reorder': {'ids'},
              'import_paths': {'paths', 'group_id'}, 'material_rename': {'id', 'name'},
              'material_move': {'ids', 'group_id'}, 'material_remove': {'ids'},
              'material_restore': {'ids'}, 'material_reorder': {'ids'}}


class BackgroundMaterialLibrary:
    def __init__(self, root=None): self.store = Store(root)

    def snapshot(self):
        with self.store.read() as catalog: return Q.snapshot(catalog, self.store)

    def page(self, query, expected_revision):
        S.integer(expected_revision)
        with self.store.locked(expected_revision) as catalog: return Q.page(catalog, query)

    def thumbnail(self, ident, expected_revision):
        S.identifier(ident); S.integer(expected_revision)
        with self.store.locked(expected_revision) as catalog:
            row = next((row for row in catalog['materials'] if row['id'] == ident), None)
            if row is None: S.fail('背景缩略图不存在', 'stale')
            raw = self.store.read_file(self.store.thumbnails / row['thumbnail_name'], S.MAX_THUMB_BYTES)
            if sha256(raw).hexdigest() != row['thumbnail_sha256'] or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                S.fail('背景缩略图内容已变化', 'changed')
            return {'version': S.VERSION, 'id': ident, 'revision': catalog['revision'],
                    'thumbnail_sha256': row['thumbnail_sha256'],
                    'data_url': 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')}

    def select(self, ident, expected_revision, *, cancelled=lambda: False):
        S.integer(expected_revision); S.cancelled(cancelled)
        with self.store.locked(expected_revision) as catalog:
            row = S.selected(catalog, [ident])[0]
            self.store.verify_object(row); S.cancelled(cancelled)
            return {'version': S.VERSION, 'library_id': catalog['library_id'],
                    'material_id': row['id'], 'catalog_revision': catalog['revision'], 'sha256': row['sha256']}

    def command(self, op, payload, expected_revision, *, cancelled=lambda: False):
        if type(op) is not str or op not in OPERATIONS: S.fail('未知背景素材操作')
        S.fields(payload, OPERATIONS[op]); S.integer(expected_revision); S.cancelled(cancelled)
        paths = I.expand_paths(payload['paths']) if op == 'import_paths' else None
        S.cancelled(cancelled)
        with self.store.locked(expected_revision) as current:
            candidate = deepcopy(current); outcomes = None
            if op == 'group_create':
                if len(candidate['groups']) >= S.MAX_GROUPS: S.fail('背景分类达到 200 个上限', 'capacity')
                candidate['groups'].append({'id': S.new_id(), 'name': S.name(payload['name'])})
            elif op in ('group_rename', 'group_delete'):
                gid = S.group(candidate, payload['id'])
                if gid == S.UNGROUPED: S.fail('未分类是固定分组，不能删除或重命名')
                if op == 'group_rename':
                    next(g for g in candidate['groups'] if g['id'] == gid)['name'] = S.name(payload['name'])
                else:
                    candidate['groups'] = [g for g in candidate['groups'] if g['id'] != gid]
                    for row in candidate['materials']:
                        if row['group_id'] == gid: row['group_id'] = S.UNGROUPED
            elif op == 'group_reorder':
                rows = {g['id']: g for g in candidate['groups']}
                candidate['groups'] = self._reorder(payload['ids'], rows)
            elif op == 'material_rename':
                S.selected(candidate, [payload['id']])[0]['name'] = S.name(payload['name'])
            elif op == 'material_move':
                gid = S.group(candidate, payload['group_id'])
                for row in S.selected(candidate, payload['ids']): row['group_id'] = gid
            elif op == 'material_remove':
                now = int(time.time() * 1000)
                for row in S.selected(candidate, payload['ids']): row['deleted_at'] = now
            elif op == 'material_restore':
                rows = S.selected(candidate, payload['ids'], archived=True)
                if S.counts(candidate)['active'] + len(rows) > S.MAX_ACTIVE:
                    S.fail('恢复后背景素材超过 2000 张', 'capacity')
                for row in rows:
                    self.store.verify_object(row); row['deleted_at'] = None
            elif op == 'material_reorder':
                active = {r['id']: r for r in candidate['materials'] if r['deleted_at'] is None}
                candidate['materials'] = self._reorder(payload['ids'], active) + [
                    r for r in candidate['materials'] if r['deleted_at'] is not None]
            elif op == 'import_paths':
                gid = S.group(candidate, payload['group_id'])
                outcomes = self._import(candidate, paths, gid, cancelled)
            S.check(candidate)
            result = Q.receipt(current, candidate, outcomes)
            # Imports retain successful files even when a later cancellation is
            # requested. Other commands cancel before any catalogue publication.
            self.store.commit(current, candidate, cancelled=(lambda: False) if paths is not None else cancelled)
            return result

    @staticmethod
    def _reorder(ids, rows):
        if (type(ids) is not list or any(type(v) is not str for v in ids)
                or len(ids) != len(rows) or len(set(ids)) != len(ids) or set(ids) != set(rows)):
            S.fail('背景排序需包含完整且不重复的项目，请刷新', 'stale')
        return [rows[ident] for ident in ids]

    def _import(self, catalog, paths, gid, cancelled):
        outcomes = []; known = {row['sha256']: row for row in catalog['materials']}
        for index, path in enumerate(paths):
            staged = None
            outcome = {'index': index, 'name': I.display_name(path), 'status': 'error',
                       'material_id': None, 'message': ''}
            try:
                S.cancelled(cancelled)
                staged, digest, size = I.copy_original(self.store, path, cancelled)
                if digest in known:
                    row = known[digest]; self.store.verify_object(row)
                    outcome.update(status='duplicate' if row['deleted_at'] is None else 'trashed_duplicate',
                                   material_id=row['id'], message='相同原件已存在，未重复导入；回收站中的素材可恢复')
                else:
                    if S.counts(catalog)['active'] >= S.MAX_ACTIVE or len(catalog['materials']) >= S.MAX_RECORDS:
                        S.fail('背景素材目录达到容量上限', 'capacity')
                    row = I.make_row(self.store, staged, digest, size, path, gid, cancelled)
                    S.cancelled(cancelled)
                    catalog['materials'].append(row); known[digest] = row
                    outcome.update(status='imported', material_id=row['id'], message='已保留完整原件')
            except S.MaterialError as error:
                outcome.update(status='cancelled' if error.code == 'cancelled' else 'error', message=str(error)[:500])
            except InterruptedError:
                outcome.update(status='cancelled', message='当前文件导入取消，保留此前成功项')
            except Exception as error:
                outcome['message'] = str(error)[:500]
            finally:
                if staged is not None:
                    try: staged.unlink(missing_ok=True)
                    except OSError: pass
            outcomes.append(outcome)
        return outcomes
