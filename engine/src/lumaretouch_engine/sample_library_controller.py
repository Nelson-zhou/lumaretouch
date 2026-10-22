# SPDX-License-Identifier: GPL-3.0-or-later
"""Versioned library operations, recoverable removal, lazy immutable reference pick.

Transport-neutral. The host must serialize commands against editor mutations and
provide a trustworthy full-resolution capture adapter, never a UI/proxy data URL.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import base64
import os
import stat
import time
from . import sample_library_state as S, sample_library_images as I, sample_library_query as Q
from .sample_library_store import Store, _sync_dir


class SampleLibrary:
    def __init__(self, root=None, *, capture=None):
        self.store = Store(root)
        self.capture_provider = capture

    def _reference_usage(self, catalog):
        # Include retained/unindexed bundles, not just live rows. This shared
        # pool may also contain project references; never infer deletion rights.
        from . import reference_color_assets as A
        root = A.cache_root(); total = 0
        with os.scandir(root) as entries:
            for count, entry in enumerate(entries, 1):
                if count > S.MAX_RECORDS * 3: S.fail('共享参考缓存条目超过统计预算')
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    S.fail('共享参考缓存包含不安全条目')
                total += entry.stat(follow_symlinks=False).st_size
        return total

    def _budget(self, catalog, addition, *, reference=False):
        if self.store.usage() + self._reference_usage(catalog) + addition > self.store.budget_bytes:
            S.fail('样片及共享参考缓存达到配置的准入预算；可调整 LRT_SAMPLE_LIBRARY_MAX_BYTES，未删除任何资源', 'storage_capacity')
        if reference:
            from . import reference_color_assets as A
            self.store.require_space(addition, A.cache_root())
        else: self.store.require_space(addition)

    def _reference_free_bytes(self):
        from . import reference_color_assets as A
        return self.store.free_bytes(A.cache_root())

    def _public(self, catalog):
        usage = self.store.usage(); reference_bytes = self._reference_usage(catalog)
        totals, group_totals = Q.counts(catalog)
        return {'version': 1, 'revision': catalog['revision'], 'groups': deepcopy(catalog['groups']),
                'capacity': Q.capacity(catalog), 'counts': totals, 'group_counts': group_totals,
                'order_ids': [s['id'] for s in catalog['samples'] if s['deleted_at'] is None],
                'storage': {'bytes': usage + reference_bytes, 'budget_bytes': self.store.budget_bytes,
                            'library_bytes': usage, 'shared_reference_bytes': reference_bytes,
                            'free_disk_bytes': self.store.free_bytes(),
                            'shared_free_disk_bytes': self._reference_free_bytes()},
                'warnings': ['回收站仍保留原片并占用存储；移除样片不会删除工程/预设引用资源',
                             '手动本地样片库，不含官方云样片、AI 推荐或语义 AI 追色',
                             '存储统计含整个共享参考缓存（含其它工程与未索引资源），不表示有权清理']}

    def snapshot(self):
        with self.store.read() as catalog: result = self._public(catalog)
        return result

    def page(self, query, expected_revision):
        with self.store.read() as catalog:
            S.integer(expected_revision, 0, 2**53 - 1)
            if expected_revision != catalog['revision']:
                S.fail('目录版本已变化，请刷新后重新浏览；未拼接不同版本的页面', 'stale_page')
            return Q.page(catalog, query)

    @staticmethod
    def _fields(payload, fields):
        if type(payload) is not dict or set(payload) != set(fields): S.fail('样片操作参数不完整或含未知字段')

    def command(self, op, payload, expected_revision, *, cancelled=lambda: False):
        """CAS one catalogue transaction. Per-file failures do not erase successes."""
        operations = {'group_create': {'name'}, 'group_rename': {'id', 'name'},
                      'group_delete': {'id'}, 'group_reorder': {'ids'},
                      'import_paths': {'paths', 'group_id'}, 'sample_rename': {'id', 'name'},
                      'sample_move': {'ids', 'group_id'}, 'sample_remove': {'ids'},
                      'sample_restore': {'ids'}, 'sample_reorder': {'ids'}}
        if type(op) is not str or op not in operations: S.fail('未知样片操作')
        self._fields(payload, operations[op]); I.cancelled(cancelled)
        # Expansion and its cap are checked before acquiring/mutating a catalogue.
        paths = I.expand_paths(payload['paths']) if op == 'import_paths' else None
        guard = None if op == 'import_paths' else lambda: I.cancelled(cancelled)
        with self.store.locked(expected_revision, before_commit=guard) as catalog:
            original = deepcopy(catalog); outcomes = None
            if op == 'group_create':
                if len(catalog['groups']) >= S.MAX_GROUPS: S.fail('本地分组最多 200 个', 'capacity')
                catalog['groups'].append({'id': S.new_id(), 'name': S.name(payload['name'])})
            elif op in ('group_rename', 'group_delete'):
                gid = S.group(catalog, payload['id'])
                if gid == S.UNGROUPED: S.fail('未分组为固定分组，不能重命名或删除')
                if op == 'group_rename':
                    next(g for g in catalog['groups'] if g['id'] == gid)['name'] = S.name(payload['name'])
                else:
                    catalog['groups'] = [g for g in catalog['groups'] if g['id'] != gid]
                    for item in catalog['samples']:
                        if item['group_id'] == gid: item['group_id'] = S.UNGROUPED
            elif op == 'group_reorder':
                ids = payload['ids']; by_id = {g['id']: g for g in catalog['groups']}
                if type(ids) is not list or any(type(gid) is not str for gid in ids) or len(ids) != len(by_id) or len(set(ids)) != len(ids) or set(ids) != set(by_id):
                    S.fail('分组排序必须包含完整且不重复的分组列表')
                catalog['groups'] = [by_id[gid] for gid in ids]
            elif op == 'sample_rename':
                item = S.selected(catalog, [payload['id']])[0]; item['name'] = S.name(payload['name'])
            elif op == 'sample_move':
                gid = S.group(catalog, payload['group_id'])
                for item in S.selected(catalog, payload['ids']): item['group_id'] = gid
            elif op == 'sample_remove':
                now = int(time.time() * 1000)
                for item in S.selected(catalog, payload['ids']): item['deleted_at'] = now
            elif op == 'sample_restore':
                items = S.selected(catalog, payload['ids'], archived=True)
                if S.active_count(catalog) + len(items) > S.MAX_ACTIVE:
                    S.fail('恢复后超过 2000 张；请先移除其它活动样片', 'capacity')
                for item in items: item['deleted_at'] = None
            elif op == 'sample_reorder':
                ids = payload['ids']; active = {s['id']: s for s in catalog['samples'] if s['deleted_at'] is None}
                if type(ids) is not list or any(type(sid) is not str for sid in ids) or len(ids) != len(active) or len(set(ids)) != len(ids) or set(ids) != set(active):
                    S.fail('排序需包含完整且不重复的活动样片列表，请刷新', 'stale')
                catalog['samples'] = [active[sid] for sid in ids] + [s for s in catalog['samples'] if s['deleted_at'] is not None]
            elif op == 'import_paths':
                gid = S.group(catalog, payload['group_id'])
                outcomes = self._import(catalog, paths, gid, cancelled)
            # Import cancellation retains and reports completed files, whereas
            # all other mutations are all-or-none until this final check.
            if op != 'import_paths': I.cancelled(cancelled)
            S.check(catalog)
            result = Q.receipt(catalog, original)
            if outcomes is not None: result['outcomes'] = outcomes
        # Commit has now succeeded; do not relabel it cancelled after this point.
        return result

    def _import(self, catalog, paths, group_id, check_cancel):
        outcomes = []; known = {s['original_sha256']: s for s in catalog['samples'] if s['kind'] == 'import'}
        for index, path in enumerate(paths):
            staged = None
            display_name = path.name.encode('utf-8', 'replace').decode('utf-8')[:240]
            outcome = {'index': index, 'name': display_name, 'status': 'error', 'message': '', 'sample_id': None}
            try:
                I.cancelled(check_cancel)
                source_info = path.lstat()
                if not stat.S_ISREG(source_info.st_mode): S.fail('请选择普通文件；不跟随符号链接')
                size = source_info.st_size
                self._budget(catalog, min(size, S.MAX_OBJECT_BYTES) + 1024 * 1024)
                staged, digest, length = I.copy_original(self.store, path, check_cancel)
                if digest in known:
                    existing = known[digest]
                    outcome.update(status='duplicate', sample_id=existing['id'],
                                   message='相同原片已在回收站，请恢复' if existing['deleted_at'] is not None else '相同原片已在样片库中，未重复保存')
                else:
                    S.room(catalog)
                    metadata, thumbnail = I.inspect_and_thumbnail(staged)
                    I.cancelled(check_cancel)
                    thumb_id = I.save_thumbnail(self.store, thumbnail)
                    stored = self.store.install(staged, digest, S.FORMATS[metadata['format']])
                    staged = None
                    item = {'id': S.new_id(), 'name': S.name(path.stem[:120] or '样片'), 'group_id': group_id,
                            'kind': 'import', 'original_sha256': digest, 'bytes': length,
                            'created_at': int(time.time() * 1000), 'deleted_at': None, 'reference': None,
                            'object_name': stored.name, 'thumbnail_sha256': thumb_id, **metadata}
                    catalog['samples'].append(item); known[digest] = item
                    outcome.update(status='imported', sample_id=item['id'], message='原片已完整保留；参考资源按需展开')
            except (S.LibraryError, OSError, ValueError, RuntimeError) as error:
                outcome.update(status='cancelled' if getattr(error, 'code', '') == 'cancelled' else 'error', message=str(error).encode('utf-8', 'replace').decode('utf-8')[:500])
            finally:
                if staged is not None and staged.exists(): staged.unlink()
            outcomes.append(outcome)
        return outcomes

    def thumbnail(self, sample_id):
        S.identifier(sample_id)
        with self.store.read() as catalog:
            item = next((s for s in catalog['samples'] if s['id'] == sample_id), None)
            if item is None: S.fail('样片不存在', 'stale')
            digest = item['thumbnail_sha256']
            path = self.store.verify_object(digest + '.jpg', digest, thumbnail=True)
            return 'data:image/jpeg;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')

    def select(self, sample_id, expected_revision, *, cancelled=lambda: False):
        from . import reference_color_assets as A
        with self.store.locked(expected_revision, before_commit=lambda: I.cancelled(cancelled)) as catalog:
            before = deepcopy(catalog); item = S.selected(catalog, [sample_id])[0]
            I.cancelled(cancelled)
            if item['reference'] is None:
                admission = lambda: self._budget(catalog, I.reference_reservation(item['width'], item['height']), reference=True)
                admission()
                item['reference'] = I.materialize(self.store, item, cancelled, admit_reference=admission)
            from .cpu_memory_budget import available_estimate
            if available_estimate() < item['width'] * item['height'] * 48 + 128 * 1024 * 1024:
                S.fail('当前内存不足以验证完整参考画布，未使用缩略图替代', 'memory_budget')
            frame = A.load(A.cache_root(), item['reference'])  # Verify content and full metadata, not only filename.
            if frame.rgb.shape[:2] != (item['height'], item['width']):
                S.fail('样片目录与完整参考画布尺寸不一致', 'asset_corrupt')
            I.cancelled(cancelled)
            result = {**Q.receipt(catalog, before), 'sample_id': sample_id, 'reference': deepcopy(item['reference']),
                      'notice': '已选择本地参考样片，尚未执行颜色匹配或 AI 追色'}
        return result

    def capture(self, name, group_id, expected_revision, *, expected_context, cancelled=lambda: False):
        """Capture only from trusted engine adapter, then CAS a durable catalogue row."""
        from .sample_library_capture import validate_capture
        from . import reference_color_assets as A
        if self.capture_provider is None: S.fail('完整冻结渲染入口尚未接入，不能以截图创建样片', 'capture_unavailable')
        name = S.name(name)
        # Admission before expensive capture; CAS is checked again before commit.
        with self.store.read() as initial:
            if expected_revision != initial['revision']: S.fail('样片库已更新，请刷新', 'stale')
            S.group(initial, group_id); S.room(initial); self._budget(initial, 1024 * 1024, reference=True)
        I.cancelled(cancelled)
        capture = self.capture_provider(expected_context, cancelled)
        validate_capture(capture)
        if expected_context != {'document_id': capture.frame.document_id, 'revision': capture.frame.revision}:
            S.fail('冻结结果与请求照片不一致', 'stale_document')
        I.cancelled(cancelled)
        with self.store.locked(expected_revision, before_commit=capture.verify_current) as catalog:
            before = deepcopy(catalog)
            S.group(catalog, group_id); S.room(catalog); self._budget(catalog, I.reference_reservation(capture.width, capture.height) + 1024 * 1024, reference=True)
            capture.verify_current(); I.cancelled(cancelled)
            reference = A.save(A.cache_root(), capture.frame)
            _sync_dir(A.cache_root())  # Resource rename durable before catalogue publication.
            self.store.require_space(0, A.cache_root())
            I.cancelled(cancelled); capture.verify_current()
            duplicate = next((s for s in catalog['samples'] if s['kind'] == 'render'
                              and s['reference']['asset_id'] == reference['asset_id']), None)
            if duplicate is not None:
                result = {**Q.receipt(catalog, before), 'sample_id': duplicate['id'],
                          'duplicate': True, 'archived': duplicate['deleted_at'] is not None, 'message': '相同冻结结果已保存；如已移除可从回收站恢复'}
            else:
                thumb = I.save_thumbnail(self.store, I.render_thumbnail(capture.frame))
                item = {'id': S.new_id(), 'name': name, 'group_id': group_id, 'kind': 'render',
                        'original_sha256': capture.frame.source['sha256'],
                        'bytes': (A.cache_root() / (reference['asset_id'] + '.npz')).stat().st_size,
                        'width': capture.width, 'height': capture.height, 'format': 'FLOAT32-NPZ',
                        'precision': 'float32 full rendered canvas; 8-bit display thumbnail',
                        'created_at': int(time.time() * 1000), 'deleted_at': None,
                        'reference': reference, 'object_name': None, 'thumbnail_sha256': thumb,
                        'reference_supported': True, 'reference_reason': '',
                        'notes': ['原分辨率当前效果冻结，保留浮点值与实际像素来源支持；不是预览截图',
                                  '不包含仅导出使用的放大或输出锐化']}
                I.cancelled(cancelled); capture.verify_current()
                catalog['samples'].append(item); S.check(catalog)
                result = {**Q.receipt(catalog, before), 'sample_id': item['id'], 'duplicate': False, 'archived': False}
        result['reference'] = deepcopy(reference)
        result['capture'] = {'sample_id': result['sample_id'], 'document_id': capture.frame.document_id,
                             'revision': capture.frame.revision, 'state_key': capture.frame.state_key,
                             'source_kind': 'frozen_render', 'original_resolution': True,
                             'render_sha256': reference['render_sha256']}
        return result

    def reclaim_plan(self):
        """Read-only orphan report, never a deletion grant or global reachability proof."""
        with self.store.read() as catalog:
            indexed = {s['object_name'] for s in catalog['samples'] if s['object_name'] is not None}
            thumbs = {s['thumbnail_sha256'] + '.jpg' for s in catalog['samples']}
            candidates = []; candidate_count = 0; candidate_bytes = 0; scanned = 0
            for directory, retained in (('originals', indexed), ('thumbnails', thumbs)):
                for path in (self.store.root / directory).iterdir():
                    scanned += 1
                    if scanned > S.MAX_RECORDS * 6: S.fail('资源目录条目超过检查预算')
                    if not path.is_symlink() and path.is_file() and path.name not in retained:
                        size = path.stat().st_size; candidate_count += 1; candidate_bytes += size
                        if len(candidates) < 100:
                            candidates.append({'kind': directory, 'name': path.name, 'bytes': size})
            return {'revision': catalog['revision'], 'unindexed_candidates': candidates,
                    'candidate_count': candidate_count, 'candidate_bytes': candidate_bytes,
                    'shown_count': len(candidates), 'report_limited': candidate_count > len(candidates),
                    'safe_to_delete': False, 'reference_cache_excluded': True,
                    'reason': '仅报告未索引资源；未核验其它使用者，不提供永久删除。回收站和共享参考资源均保留。'}
