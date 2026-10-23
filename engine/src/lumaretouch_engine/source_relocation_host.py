"""Registered native engine integration port; runtime verification remains UNRUN.

One worker owns bounded I/O. While busy or uncertain, blocks() fences competing
commands before their mutation fences. Never call project open to publish paths:
that would regenerate canonical document IDs and discard runtime histories.
"""
from __future__ import annotations
import copy
import os
import threading
from . import source_relocation_transaction as T
from .source_relocation_io import Budget, hash_file


class SourceRelocation:
    def __init__(self, engine, emit, validate):
        self.engine, self.emit, self.validate = engine, emit, validate
        self.lock = threading.RLock()
        self.active = None
        self.cancel = threading.Event()
        self.plans = {}
        self.receipts = {}
        self.uncertain = None
        self.last_operation = None
        self.workspace = engine._document_versions().workspace
        self.worker = None

    def adopt_workspace(self):
        # Only a successfully completed explicit open/create changes workspace.
        current = self.engine._document_versions().workspace
        if self.active is None and current != self.workspace:
            self.workspace = current
            self.uncertain = None
            self.plans.clear()
            self.last_operation = None

    def blocks(self, name, payload):
        # Conservative by design: even document selection can rewrite live state.
        with self.lock:
            self.adopt_workspace()
            if self.active is None and name == 'project' and payload.get('action') == 'open' and payload.get('force') is True:
                return False  # Explicit recovery; failed opens do not clear the fence.
            if self.active is None and self.uncertain is None: return False
            if name == 'session' and payload.get('action') == 'query': return False
            if name == 'project' and payload.get('action') == 'state': return False
            if name == 'preset_organisation' and payload.get('action') in ('snapshot', 'receipt'): return False
            return name not in ('source_relocation', 'hello', 'ping', 'status', 'shutdown')

    def close(self):
        self.cancel.set()
        worker = self.worker
        if worker is not None and worker is not threading.current_thread():
            worker.join()  # Wait for read boundary or the short durable publication.

    def _snapshot(self, ids=None):
        e = self.engine
        recovery = getattr(e, '_project_recovery_runtime', None)
        if recovery and recovery.host.active: raise ValueError('请先完成工程恢复操作')
        managed = getattr(e, "_managed_import_controller", None)
        package = getattr(e, "_project_package_controller", None)
        if managed and (managed.active or managed.uncertain): raise ValueError("请先确认导入结果")
        if package and package.active: raise ValueError("请先完成便携包操作")
        if e._project is None or not e._project_path: raise ValueError('请先打开并保存项目')
        if e._project_dirty: raise ValueError('工程有未保存修改，请先保存再重定位')
        for key in ('bench', '_export', '_thumbs', '_picks'):
            worker = getattr(e, key, None)
            if worker is not None and worker.is_alive(): raise ValueError('请等待后台任务结束')
        from .sample_library_capture import heavy_reason
        reason = heavy_reason(e)
        if reason: raise ValueError(reason)
        for key in ('_optics_preview_owner', '_effect_recovery_preview_owner', '_semantic_colour_owner'):
            pending = getattr(e, key, None)
            if pending is not None and (getattr(pending, 'job', None) is not None or getattr(pending, 'latest', None) is not None):
                raise ValueError('请先完成或关闭当前效果预览，再重定位原图')
        owner = e._document_versions()
        identities = []
        for row in e._docs:
            version = owner.version(row)
            if ids is not None and version.document_id not in ids: continue
            if ids is None and os.path.lexists(row['path']): continue
            identity = {'document_id': version.document_id, 'revision': version.revision,
                        'source_asset_id':row['source_asset_id'], 'old_path': row['path'], 'width': row.get('src_w'), 'height': row.get('src_h'),
                        'format': (row.get('_library_metadata') or {}).get('format') or row.get('source_format'), 'orientation': row.get('source_orientation')}
            if ids is None:
                stored = next((r for r in e._project['docs'] if r.get('document_id') == row['document_id']), {})
                try: T.expected(stored,e._project); identity['eligible'] = True
                except ValueError as error: identity.update(eligible=False, reason=str(error))
            identities.append(identity)
        if ids is not None and {r['document_id'] for r in identities} != set(ids):
            raise ValueError('文档身份失效，请刷新项目')
        disk_sha = getattr(e, '_project_disk_sha256', None)
        if not isinstance(disk_sha, str) or not T.DIGEST.fullmatch(disk_sha):
            raise ValueError('缺少已加载项目的磁盘指纹，请重新打开或保存项目')
        return (copy.deepcopy(e._project) if ids is not None else e._project), identities, e._project_path, owner.workspace, disk_sha

    def report(self):
        self.adopt_workspace()
        try:
            _, rows, path, workspace, _ = self._snapshot()
            return {'available': self.uncertain is None and self.active is None, 'rows': rows, 'project_path': path,
                    'workspace': workspace, 'busy': self.active is not None,
                    'requires_readback': self.uncertain is not None,
                    'recovery_operation_id': (self.uncertain or {}).get('id') or self.last_operation or self.active}
        except (ValueError, OSError) as error:
            return {'available': False, 'rows': [], 'reason': str(error)}

    def _result(self, request_id, status, **fields):
        value = {'event': 'source_relocation_result', 'request_id': request_id, 'status': status, **fields}
        with self.lock:
            if request_id in self.receipts: self.receipts[request_id] = value
        self.emit(value)
        return value

    def handle(self, p):
        allowed = {'cmd', 'action', 'request_id', 'document_ids', 'paths', 'directory', 'preview_id', 'choices', 'confirmed', 'operation_id'}
        if not isinstance(p, dict) or set(p) - allowed: raise ValueError('未知重定位参数')
        rid, action = p.get('request_id'), p.get('action')
        if not isinstance(rid, str) or not 1 <= len(rid) <= 128: raise ValueError('缺少请求身份')
        with self.lock:
            self.adopt_workspace()
            if action == 'query':
                operation = p.get('operation_id')
                if not isinstance(operation, str): raise ValueError('缺少待查询操作身份')
                if self.uncertain is not None and self.uncertain['id'] == operation:
                    if self.active is not None:
                        return self._result(rid, 'readback', operation={'request_id': operation, 'status': 'pending'}, state=self.report())
                    self.active = rid
                    self.cancel.clear()
                    thread = threading.Thread(target=self._query_work, args=(rid,), daemon=True, name='source-relocation-query')
                    self.worker = thread
                    try: thread.start()
                    except Exception:
                        self.active = None
                        raise
                    return
                prior = self.receipts.get(operation)
                if prior is None and self.engine._project_path:
                    import json
                    raw, _ = T.read_project(self.engine._project_path)
                    persisted = json.loads(raw).get('source_relocation_receipt', {})
                    if persisted.get('operation_id') == operation:
                        prior = {'request_id': operation, 'status': 'succeeded', 'reconciled': True,
                                 'relocated': persisted.get('relocated', 0)}
                return self._result(rid, 'readback', operation=prior or {'status': 'unknown', 'request_id': operation}, state=self.report())
            if action == 'state': return self._result(rid, 'readback', state=self.report())
            if action == 'cancel':
                if self.active != p.get('operation_id'): raise ValueError('取消目标已失效')
                self.cancel.set()
                return self._result(rid, 'cancel_requested', operation_id=self.active)
            if rid in self.receipts: return self.emit(self.receipts[rid])
            if self.active is not None or self.uncertain is not None: raise ValueError('上次操作仍在进行或结果待确认；禁止重复提交')
            if len(self.receipts) >= 128: raise ValueError('重定位操作记录已满，请保存并重新启动')
            if action not in ('scan', 'commit'): raise ValueError('未知重定位操作')
            if action == 'scan':
                ids = p.get('document_ids')
                if not isinstance(ids, list) or not 1 <= len(ids) <= 64 or len(set(ids)) != len(ids) or not all(isinstance(x, str) for x in ids):
                    raise ValueError('请选择 1–64 张缺失原图')
                snapshot = self._snapshot(ids)
            else:
                if p.get('confirmed') is not True: raise ValueError('需要审核并确认路径映射')
                plan = self.plans.get(p.get('preview_id'))
                if plan is None: raise ValueError('预览已失效，请重新扫描')
                snapshot = self._snapshot([r['document_id'] for r in plan['rows']])
                if snapshot[3] != plan['workspace'] or snapshot[1] != plan['identities']:
                    raise ValueError('文档或版本发生变化，请重新扫描')
            self.active = rid
            self.last_operation = rid
            self.cancel.clear()
            self.receipts[rid] = {'event': 'source_relocation_result', 'request_id': rid, 'status': 'pending'}
            thread = threading.Thread(target=self._work, args=(copy.deepcopy(p), snapshot), daemon=True, name='source-relocation')
            self.worker = thread
            try: thread.start()
            except Exception:
                self.active = None
                self.receipts.pop(rid, None)
                raise

    def _work(self, p, snapshot):
        rid = p['request_id']
        project, identities, path, workspace, expected_disk_sha = snapshot
        try:
            if p['action'] == 'scan':
                disk_sha = T.read_project(path)[1]
                if disk_sha != expected_disk_sha: raise ValueError('项目文件在加载后被外部修改，请重新打开后核对')
                plan = T.preview(project, identities, p.get('paths', []), p.get('directory'), self.cancel.is_set)
                plan.update(preview_id=rid, workspace=workspace, identities=identities, disk_sha256=disk_sha)
                with self.lock:
                    if self.cancel.is_set(): raise InterruptedError('扫描已取消')
                    self.plans.clear()
                    self.plans[rid] = plan
                    self.active = None
                self._result(rid, 'preview', preview=plan)
            else:
                plan = self.plans[p['preview_id']]
                output, updates = T.stage(project, plan, p.get('choices'), self.cancel.is_set)
                if any(update['new_path'] == path for update in updates):
                    raise ValueError('工程文件不能作为自己的原图来源')
                # All competing dispatch writes must be fenced via blocks().
                now = self._snapshot([r['document_id'] for r in plan['rows']])
                if now[1] != identities or now[3] != workspace or T.project_digest(now[0]) != T.project_digest(project):
                    raise ValueError('项目在预览后改变，未提交')
                for update in updates:
                    row = self.engine._document_versions().find(self.engine._docs, update['document_id'])[1]
                    self.engine._document_versions().check_advance(row)
                def recheck():
                    budget = Budget(self.cancel.is_set)
                    for update in updates:
                        if os.path.lexists(update['old_path']): raise ValueError('原路径重新出现')
                        found = hash_file(update['new_path'], budget, update['bytes'])
                        candidate = next(c for c in update['candidates'] if c['path'] == update['new_path'])
                        if found != candidate: raise ValueError('提交前来源再次变化')
                    current = self._snapshot([r['document_id'] for r in plan['rows']])
                    if current[1] != identities or current[3] != workspace or T.project_digest(current[0]) != T.project_digest(project):
                        raise ValueError('提交前项目或文档再次变化')
                receipt = T.persist(path, output, plan['disk_sha256'], rid, self.validate, self.cancel.is_set, recheck, relocated=len(updates))
                self.uncertain = {'id': rid, 'path': path, 'sha256': receipt['sha256'], 'updates': updates,
                                  'before_sha256': plan['disk_sha256'], 'project': receipt.get('project'),
                                  'workspace': workspace, 'identities': identities}
                if receipt['status'] == 'unknown':
                    self._result(rid, 'unknown', error=receipt.get('error'), requires_readback=True)
                else:
                    self._publish(receipt['project'], updates, receipt['sha256'])
                    self.uncertain = None
                    self.plans.clear()
                    self.active = None
                    self._result(rid, 'succeeded', relocated=len(updates), state=self.report())
        except InterruptedError as error:
            self._result(rid, 'cancelled', error=str(error))
        except Exception as error:
            # Once disk committed, an in-memory publication error also needs query.
            self._result(rid, 'unknown' if self.uncertain else 'failed', error=str(error), requires_readback=self.uncertain is not None)
        finally:
            with self.lock:
                if self.active == rid: self.active = None

    def _publish(self, project, updates, sha):
        with self.lock:
            self._publish_locked(project, updates, sha)

    def _publish_locked(self, project, updates, sha):
        e = self.engine
        owner = e._document_versions()
        rows = []
        for update in updates:
            found = owner.find(e._docs, update['document_id'])
            if found is None: raise ValueError('原文档已离开当前会话，需要重新打开已保存项目')
            row = found[1]
            # Publication is idempotent during uncertain-result reconciliation.
            if row['path'] not in (update['old_path'], update['new_path']): raise ValueError('文档路径发生冲突')
            rows.append((row, update))
        for row, update in rows:
            if row['path'] == update['old_path']:
                row.setdefault('_source_relocation_aliases', {})[update['old_path']] = update['sha256']
                row['path'] = update['new_path']
                row['name'] = os.path.basename(update['new_path'])
                row['bytes_on_disk'] = update['bytes']
                row['fingerprint'] = {**row['fingerprint'], 'path': update['new_path']}
                candidate = next(c for c in update['candidates'] if c['path'] == update['new_path'])
                row['_library_source_stamp'] = tuple(candidate['stat'])
                if row.get('_local_source_stamp') is not None: row['_local_source_stamp'] = tuple(candidate['stat'])
                owner.advance(row)
                if e._doc_path == update['old_path']: e._doc_path = update['new_path']
                if getattr(e, '_people_path', None) == update['old_path']: e._people_path = update['new_path']
        e._project = {**project, '_source_path': e._project_path, '_source_sha256': sha}
        e._project_saved_ns = project.get('updated_ns')
        e._project_disk_sha256 = sha
        missing = [{'path': row['path'], 'exists': False} for row in e._docs if not os.path.lexists(row['path'])]
        e._project_source_notice = {**getattr(e, '_project_source_notice', {}), 'missing': missing[:12], 'missing_count': len(missing)}
        # No image load, cache regeneration, history reset, task-input rewrite or recipe change.
        e.emit_session_state()

    def _query_work(self, rid):
        try:
            self._reconcile(rid)
        except Exception as error:
            self._result(rid, 'unknown', error=str(error), requires_readback=True)
        finally:
            with self.lock:
                if self.active == rid: self.active = None

    def _reconcile(self, rid):
        pending = self.uncertain
        raw, digest = T.read_project(pending['path'])
        if digest == pending['sha256']:
            import json
            project = json.loads(raw)
            self.validate(project)
            marker = project.get('source_relocation_receipt', {})
            if marker.get('operation_id') != pending['id']: raise ValueError('磁盘操作标记不匹配')
            if self.engine._document_versions().workspace != pending['workspace']: raise ValueError('工作区变化，请重开已保存项目')
            dfd = os.open(os.path.dirname(pending['path']), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(dfd)
            finally: os.close(dfd)
            budget = Budget(self.cancel.is_set)
            for update in pending['updates']:
                found = hash_file(update['new_path'], budget, update['bytes'])
                if found['sha256'] != update['sha256']:
                    raise ValueError('已保存引用的源文件随后变化；不能沿用旧缓存，请重新打开并处理源文件变化提示')
            self._publish(project, pending['updates'], digest)
            self.uncertain = None
            self.plans.clear()
            self.active = None
            completed = self._result(pending['id'], 'succeeded', relocated=len(pending['updates']), reconciled=True)
            return self._result(rid, 'readback', operation=completed, state=self.report())
        # A changed project never authorizes a compensating overwrite.
        return self._result(rid, 'unknown', error='磁盘内容与提交证据不一致；保留文件，请备份并重新打开项目', requires_readback=True)


def controller(engine, emit, validate):
    value = getattr(engine, '_source_relocation_controller', None)
    if value is None:
        value = SourceRelocation(engine, emit, validate)
        engine._source_relocation_controller = value
    return value


def handle(engine, payload, emit, validate):
    service = controller(engine, emit, validate)
    try:
        return service.handle(payload)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
        request_id = payload.get('request_id')
        emit({'event': 'source_relocation_result', 'request_id': request_id, 'status': 'unknown' if service.uncertain else 'failed',
              'requires_readback': service.uncertain is not None, 'error': str(error)})
