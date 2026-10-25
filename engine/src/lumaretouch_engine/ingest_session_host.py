"""Engine-owned bounded lease around the established atomic managed-copy host.

No project switching, auto-save, recipe mutation, camera calls or mutation-receipt eviction.
Server integration must install blocks() before ordinary command side effects.
All public methods except trusted_precommit run on the serialized command thread.
"""
from copy import deepcopy
import json
import os
import threading
import uuid
from . import ingest_session_protocol as P
from .source_relocation_transaction import read_project, project_digest


class IngestSession:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.lock = threading.RLock()
        self.lease = None
        self.requests = {}
        self.receipts = {}
        self.operations = {}
        self.closed = False

    @property
    def active(self):
        # Existing recovery ownership inspection discovers this lease too.
        return self.lease['session_id'] if self.lease else None

    def _managed(self):
        owner = getattr(self.engine, '_managed_import_controller', None)
        if owner is None:
            from .managed_import_host import ManagedImport
            owner = ManagedImport(self.engine, self.emit)
            self.engine._managed_import_controller = owner
        return owner

    def _binding(self):
        e = self.engine
        return P.binding({'project_id': (e._project or {}).get('project_id'),
                          'path': e._project_path, 'workspace': e._document_versions().workspace,
                          'disk_sha256': getattr(e, '_project_disk_sha256', None)})

    def _selection(self):
        e = self.engine
        return (getattr(e, '_doc_index', -1), getattr(e, '_load_id', None), getattr(e, '_doc_path', None))

    def _capacity(self):
        managed = self._managed()
        with managed.lock:
            return max(0, min(256 - len((self.engine._project or {}).get('managed_import_receipts', {})),
                              256 - len(managed.requests)))

    def _identity(self, lease):
        current = self._binding()
        if any(current[key] != lease['binding'][key] for key in ('project_id', 'path', 'workspace')):
            raise ValueError('当前工程或工作区已变化；原接入会话未转移到新工程')
        if self.engine._project_dirty:
            raise ValueError('当前工程有未保存编辑；接入会话不会自动保存或覆盖')
        if self._selection() != lease['selection']:
            raise ValueError('当前编辑照片已变化；接入会话不自动切换或采用新照片')
        return current

    def _exact(self, lease):
        current = self._identity(lease)
        if current != lease['binding'] or read_project(current['path'])[1] != current['disk_sha256']:
            raise ValueError('已保存工程磁盘指纹变化；未登记新的接入文件')
        return current

    def _session(self, session_id):
        if self.lease is None or self.lease['session_id'] != session_id:
            raise ValueError('原接入会话已结束或引擎重启；先核对原工程与导入回执，不能重发')
        return self.lease

    def _view(self):
        if self.lease is None:
            return None
        lease = self.lease
        phase = ('unknown' if lease.get('uncertain') else 'pending' if lease.get('operation_id') else
                 'stopped' if lease.get('stop_reason') else 'exhausted' if lease['used'] >= lease['max_operations'] else 'armed')
        return {'session_id': lease['session_id'], 'owner': lease['owner'], 'phase': phase,
                'binding': deepcopy(lease['binding']), 'max_operations': lease['max_operations'],
                'used_operations': lease['used'], 'remaining_operations': max(0, lease['max_operations'] - lease['used']),
                'operation_id': lease.get('operation_id'), 'stop_reason': lease.get('stop_reason'),
                'requires_readback': bool(lease.get('uncertain')),
                'rotation_supported': False, 'runtime_verified': False}

    def _result(self, request, status, **fields):
        rid = request.get('request_id')
        action = request.get('action')
        rid = rid if isinstance(rid, str) and len(rid) <= 128 else None
        action = action if isinstance(action, str) and action in P.FIELDS else None
        value = {'event': 'ingest_session_result', 'protocol': P.PROTOCOL,
                 'request_id': rid, 'action': action,
                 'status': status, 'session': self._view(), **fields}
        if rid is not None and self.requests.get(rid) == request:
            self.receipts[rid] = deepcopy(value)
        self.emit(value)
        return value

    def _reserve(self, request):
        self._prune_completed_reads()
        rid = request['request_id']
        recovery = request['action'] in ('state', 'query', 'cancel', 'release')
        limit = P.MAX_RECEIPTS if recovery else P.MAX_RECEIPTS - P.RECOVERY_RESERVE
        if len(self.requests) >= limit:
            raise ValueError('接入请求回执已满；停止并核对后重启应用，不能丢弃原操作身份')
        self.requests[rid] = deepcopy(request)

    def _prune_completed_reads(self):
        # A query that reports an unknown ORIGINAL operation is still a finished
        # read when its own outer status is readback. The original import and
        # operation ledgers remain retained. Never infer completion from presence
        # of any result, or from failed/unknown read envelopes.
        completed = [rid for rid, request in self.requests.items()
                     if request.get('action') in ('state', 'query')
                     and self.receipts.get(rid, {}).get('status') == 'readback']
        for rid in completed:
            del self.requests[rid]
            self.receipts.pop(rid, None)

    def blocks(self, name, payload):
        """No global workflow exemption; a lease excludes all unrelated writers."""
        with self.lock:
            if self.lease is None:
                return False
            if name in ('hello', 'ping', 'status', 'shutdown'):
                return False
            if name == 'workflow_owner':
                from .workflow_owner_host import ingest_passthrough
                return not ingest_passthrough(self.engine, payload)
            if name == 'ingest_session':
                return False  # Strict schema/session/operation checks remain in handle.
            if name == 'project' and payload.get('action') == 'state':
                return False
            if name == 'session' and payload.get('action') == 'query':
                return False
            return True

    def managed_passthrough(self, payload):
        """Only exact own recovery reads/cancellation may cross ManagedImport.blocks.

        This is an authorization predicate, not an invocation. All other existing
        package/recovery/lens/expression/creative/source-relocation guards remain.
        """
        try:
            request = P.command(payload)
            if request['action'] not in ('query', 'cancel'):
                return False
            with self.lock:
                lease = self._session(request['session_id'])
                self._identity(lease)
                operation = self.operations.get(request['operation_id'])
                if operation is None or operation['session_id'] != lease['session_id']:
                    return False
                managed = self._managed()
                with managed.lock:
                    uncertain = managed.uncertain
                    return (lease.get('operation_id') == request['operation_id']
                            and (managed.active == request['operation_id']
                                 or bool(uncertain and uncertain.get('id') == request['operation_id']))
                            and (request['action'] != 'cancel' or uncertain is None))
        except (ValueError, TypeError, KeyError, OSError):
            return False

    def _committed_documents(self, operation, lease):
        """Accept only the actual rows registered by the original managed write."""
        e = self.engine
        current = self._identity(lease)
        raw, disk_sha = read_project(current['path'])
        disk = json.loads(raw)
        project = {key: value for key, value in e._project.items() if key not in ('_source_path', '_source_sha256')}
        if disk_sha != current['disk_sha256'] or project_digest(disk) != project_digest(project):
            raise ValueError('原操作磁盘回执与当前工程尚未一致，不能继续接入')
        rid = operation['operation_id']
        durable = disk.get('managed_import_receipts', {}).get(rid)
        proofs = operation['request']['completed_sources']
        if durable != {'request_id': rid, 'status': 'succeeded', 'imported': len(proofs)}:
            raise ValueError('原操作缺少精确持久化成功回执')
        rows = [row for row in e._docs if (row.get('managed_import') or {}).get('operation_id') == rid]
        saved = {row.get('document_id'): row for row in disk.get('docs', [])}
        if len(rows) != len(proofs) or len({row['document_id'] for row in rows}) != len(rows):
            raise ValueError('原操作实际文档数量或身份不匹配')
        by_source = {row['managed_import']['original_path']: row for row in rows}
        if set(by_source) != {proof['path'] for proof in proofs}:
            raise ValueError('原操作实际来源集合不匹配')
        documents = []
        for proof in proofs:
            row = by_source[proof['path']]
            record, fp = row['managed_import'], row.get('fingerprint') or {}
            expected_target = os.path.join(operation['request']['root'],
                str(uuid.uuid5(uuid.UUID(rid), proof['path'])) + os.path.splitext(proof['path'])[1].lower())
            stored = saved.get(row['document_id']) or {}
            if (record.get('mode') != 'copy' or record.get('content_sha256') != proof['sha256']
                    or record.get('original_stat') != [int(part) for part in proof['stat']]
                    or record.get('managed_root') != operation['request']['root']
                    or fp.get('hash_level') != 'full' or fp.get('sha256') != proof['sha256']
                    or fp.get('bytes') != proof['size'] or row.get('path') != expected_target
                    or row.get('name') != os.path.basename(proof['path'])
                    or stored.get('managed_import') != record or stored.get('path') != expected_target
                    or stored.get('fingerprint') != fp
                    or (disk.get('source_assets', {}).get(row['source_asset_id']) or {}).get('fingerprint') != fp):
                raise ValueError('原操作文档缺少完整字节、原始文件名或来源证据')
            documents.append({'document_id': row['document_id'],
                              'revision': str(e._document_versions().version(row).revision),
                              'source_asset_id': row['source_asset_id'], 'recipe_version_id': row['recipe_version_id'],
                              'path': row['path'], 'original_path': proof['path'], 'filename': row['name'],
                              'source_sha256': proof['sha256'], 'size': proof['size'], 'stat': deepcopy(proof['stat']),
                              'occurrence_id': proof['occurrence_id'], 'completion': proof['completion'],
                              'import_receipt_id': rid})
        # Only this verified own transaction may advance the session CAS base.
        lease['binding'] = current
        return documents

    def _observe(self, lease):
        rid = lease.get('operation_id')
        if rid is None:
            self._exact(lease)
            return None
        operation = self.operations[rid]
        managed = self._managed()
        with managed.lock:
            self._identity(lease)
            receipt = deepcopy(managed.receipts.get(rid) or operation.get('dispatch_receipt'))
            active = managed.active == rid
            uncertain = managed.uncertain
            if uncertain is not None and uncertain.get('id') != rid:
                raise ValueError('另一个导入结果不确定；原接入会话保持锁定')
            if receipt is None:
                lease['uncertain'] = True
                operation['status'] = 'unknown'
            elif receipt.get('status') == 'succeeded' and not active and uncertain is None:
                try:
                    operation['documents'] = self._committed_documents(operation, lease)
                    operation['status'] = 'succeeded'
                    operation['receipt'] = receipt
                    lease['operation_id'] = None
                    lease['uncertain'] = False
                except Exception:
                    lease['uncertain'] = True
                    operation['status'] = 'unknown'
                    self._emit_original(operation)
                    raise
            elif receipt.get('status') in ('failed', 'cancelled') and not active and uncertain is None:
                self._exact(lease)
                operation['status'] = receipt['status']
                operation['receipt'] = receipt
                lease['operation_id'] = None
                lease['uncertain'] = False
                lease['stop_reason'] = '原导入未成功；已核验但未登记的文件需核对，不能自动重试'
            elif receipt.get('status') == 'unknown' or uncertain is not None:
                lease['uncertain'] = True
                operation['status'] = 'unknown'
                operation['receipt'] = receipt
            else:
                operation['status'] = 'pending'
                operation['receipt'] = receipt
            self._emit_original(operation)
        return self._operation(operation)

    def _emit_original(self, operation):
        """Settle the original native write fence, never only the query receipt."""
        status = operation['status']
        if status == 'pending':
            return
        outer_status = 'failed' if status == 'cancelled' else status
        if operation.get('last_emitted_status') == outer_status:
            return
        operation['last_emitted_status'] = outer_status
        self._result(operation['request'], outer_status, operation=self._operation(operation))

    @staticmethod
    def _operation(operation):
        return {'operation_id': operation['operation_id'], 'request_id': operation['request_id'],
                'status': operation['status'], 'documents': deepcopy(operation.get('documents', [])),
                'receipt': deepcopy(operation.get('receipt'))}

    def _arm(self, request):
        if self.closed or self.lease is not None:
            raise ValueError('接入会话已运行或宿主已关闭；先结束原会话')
        managed = self._managed()
        with managed.lock:
            managed.adopt()
            managed.guard()
            if managed.active or managed.uncertain:
                raise ValueError('请先核对原导入操作')
            current = self._binding()
            if current != request['expected'] or read_project(current['path'])[1] != current['disk_sha256']:
                raise ValueError('工程已变化；必须重新查看真实已保存工程身份')
            if request['max_operations'] > self._capacity():
                raise ValueError('剩余导入回执容量不足；减少本次上限或显式选择新工程，不支持自动轮换')
            self._prune_completed_reads()
            if len(self.requests) + request['max_operations'] + 2 > P.MAX_RECEIPTS - P.RECOVERY_RESERVE:
                raise ValueError('本会话无法保留全部请求与结束回执；请核对后重启应用')
            self._reserve(request)
            self.lease = {'session_id': str(uuid.uuid4()), 'owner': request['owner'], 'binding': current,
                          'selection': self._selection(), 'max_operations': request['max_operations'],
                          'used': 0, 'operation_id': None, 'uncertain': False, 'occurrences': set()}
        return self._result(request, 'succeeded')

    def _import(self, request, lease):
        self._observe(lease)
        if self.closed or lease.get('operation_id') or lease.get('uncertain') or lease.get('stop_reason'):
            raise ValueError('原导入未结束或会话已停止；只能查询并核对原操作')
        if lease['used'] >= lease['max_operations'] or self._capacity() < 1:
            raise ValueError('有界会话或持久化回执上限已到；请明确结束，不会自动换工程或遗忘回执')
        proofs = request['completed_sources']
        completion = 'completed_transfer' if lease['owner'] == 'tether' else 'stable_read'
        if any(proof['completion'] != completion for proof in proofs):
            raise ValueError('来源完成证据与会话类型不匹配')
        if any(proof['occurrence_id'] in lease['occurrences'] for proof in proofs):
            raise ValueError('来源事件已提交过；查询原操作，不能重复登记')
        self._exact(lease)
        # The bridge only accepts actual files, never expands a directory whose
        # completed manifest could change between native observation and copying.
        from .source_relocation_io import open_regular, signature
        for proof in proofs:
            fd = open_regular(proof['path'])
            try:
                if list(signature(os.fstat(fd))) != [int(part) for part in proof['stat']]:
                    raise ValueError('文件在完整读取后变化；未开始新导入')
            finally:
                os.close(fd)
        managed = self._managed()
        managed.guard()  # Existing saved-project/preview/background guard is unchanged.
        rid = P.operation_id(lease['session_id'], request['request_id'])
        expected_binding = deepcopy(lease['binding'])
        expected_project = project_digest(self.engine._project)
        expected_proofs = deepcopy(proofs)
        expected_root = request['root']
        expected_root_identity = P.root_identity(request['root_identity'])
        expected_session = lease['session_id']

        def trusted_root(root_fd):
            # Check the actual descriptor used for every destination write, not
            # merely a pathname sampled before asynchronous worker dispatch.
            from .source_relocation_io import open_directory
            actual = os.fstat(root_fd)
            if (actual.st_dev, actual.st_ino) != expected_root_identity:
                raise ValueError('原始目标目录已被替换；未向替代目录写入')
            current_fd = open_directory(expected_root)
            try:
                current = os.fstat(current_fd)
                if (current.st_dev, current.st_ino) != expected_root_identity:
                    raise ValueError('目标目录路径变化；不登记新复制文件')
            finally:
                os.close(current_fd)

        def trusted_precommit(prepared):
            with self.lock:
                current = self._session(expected_session)
                if current.get('operation_id') != rid or current['binding'] != expected_binding:
                    raise ValueError('原接入会话或提交身份已变化')
                self._exact(current)
                if project_digest(self.engine._project) != expected_project:
                    raise ValueError('接入期间工程内容变化；不登记新复制文件')
                P.prepared_matches(prepared, expected_proofs, expected_root, rid)

        self._reserve(request)
        lease['used'] += 1
        lease['occurrences'].update(proof['occurrence_id'] for proof in proofs)
        lease['operation_id'] = rid
        operation = {'operation_id': rid, 'request_id': request['request_id'], 'session_id': lease['session_id'],
                     'request': deepcopy(request), 'status': 'pending'}
        self.operations[rid] = operation
        inner = {'cmd': 'managed_import', 'action': 'start', 'request_id': rid,
                 'mode': 'copy', 'paths': deepcopy(request['paths']), 'root': request['root']}
        operation['inner_request'] = deepcopy(inner)
        # Record recovery identity before dispatch. Neither an exception nor a
        # lost outer response can authorize another start or a fresh identity.
        self._result(request, 'pending', operation=self._operation(operation))
        try:
            returned = managed.handle(inner, trusted_precommit=trusted_precommit, trusted_root=trusted_root)
            if (isinstance(returned, dict) and returned.get('request_id') == rid
                    and returned.get('status') == 'failed' and rid not in managed.requests):
                # ManagedImport does not retain pre-admission rejections. Its
                # exact returned no-write failure is still safe terminal proof.
                operation['dispatch_receipt'] = deepcopy(returned)
        except Exception:
            lease['uncertain'] = True
            operation['status'] = 'unknown'
            raise
        result = self._observe(lease)
        if operation['status'] != 'pending':
            return deepcopy(self.receipts[request['request_id']])
        return self._result(request, 'pending', operation=result)

    def handle(self, payload):
        request = payload if isinstance(payload, dict) else {}
        try:
            request = P.command(payload)
            with self.lock:
                prior = self.requests.get(request['request_id'])
                if prior is not None:
                    if prior != request:
                        raise ValueError('请求身份与原始参数冲突；没有重发')
                    # Replaying a retained reply never re-enters managed.handle.
                    result = deepcopy(self.receipts[request['request_id']])
                    self.emit(result)
                    return result
                action = request['action']
                if action == 'state':
                    self._reserve(request)
                    current, reason = None, None
                    try:
                        current = self._binding()
                        if self.lease is None:
                            self._managed().guard()
                            if self._managed().active or self._managed().uncertain:
                                raise ValueError('原导入进行中或结果不确定')
                        else:
                            self._observe(self.lease)
                    except Exception as error:
                        reason = str(error)
                    return self._result(request, 'readback', state={'current_binding': current,
                        'available': not (reason or self.lease or self.closed), 'reason': reason,
                        'receipt_capacity': self._capacity(), 'max_operations': P.MAX_OPERATIONS,
                        'rotation_supported': False, 'runtime_verified': False})
                if action == 'arm':
                    return self._arm(request)
                lease = self._session(request['session_id'])
                self._identity(lease)
                if action == 'import':
                    return self._import(request, lease)
                if action in ('query', 'cancel'):
                    self._reserve(request)
                    operation = self.operations.get(request['operation_id'])
                    if operation is None or operation['session_id'] != lease['session_id']:
                        raise ValueError('操作不属于原接入会话')
                    self._observe(lease)
                    managed = self._managed()
                    with managed.lock:
                        if action == 'cancel' and (lease.get('uncertain') or managed.uncertain is not None):
                            raise ValueError('原提交结果未知；只能查询，取消不能推断回滚')
                        if lease.get('operation_id') == operation['operation_id']:
                            if action == 'cancel':
                                lease['stop_reason'] = '已请求停止；等待原导入在安全边界结束'
                            managed.handle({'cmd': 'managed_import', 'action': action,
                                'request_id': str(uuid.uuid4()), 'operation_id': operation['operation_id']})
                    if lease.get('operation_id'):
                        self._observe(lease)
                    else:
                        self._exact(lease)
                    return self._result(request, 'readback', operation=self._operation(operation))
                if action == 'release':
                    self._observe(lease)
                    if lease.get('operation_id') or lease.get('uncertain'):
                        raise ValueError('原导入仍在进行或结果未知；不能释放工程锁')
                    self._exact(lease)
                    self._reserve(request)
                    released = self._view()
                    self.lease = None
                    return self._result(request, 'succeeded', released_session=released)
        except Exception as error:
            with self.lock:
                unknown = bool(self.lease and self.lease.get('uncertain'))
                return self._result(request, 'unknown' if unknown else 'failed', error=str(error))

    def close(self):
        with self.lock:
            self.closed = True
            managed = self._managed()
            if self.lease and self.lease.get('operation_id') == managed.active:
                managed.cancel.set()
        # Do not join while holding the lease lock: trusted_precommit also uses it.
        managed.close()
        # Closing never erases an uncertain lease or an original operation ID.


def controller(engine, emit):
    owner = getattr(engine, '_ingest_session_host', None)
    if owner is None:
        owner = IngestSession(engine, emit)
        engine._ingest_session_host = owner
    return owner


def handle(engine, payload, emit):
    return controller(engine, emit).handle(payload)


def guard_command(engine, name, payload):
    owner = getattr(engine, '_ingest_session_host', None)
    if owner is not None and owner.blocks(name, payload):
        raise ValueError('有界接入会话正在保护当前已保存工程；请先停止并核对原操作，再继续编辑')


def managed_passthrough(engine, payload):
    owner = getattr(engine, '_ingest_session_host', None)
    return bool(owner is not None and owner.managed_passthrough(payload))


def dispatch_rejected(engine, payload, error, started, emit):
    """Correlated rejection before admission; never invent rollback after entry."""
    try:
        P.identity(payload.get('request_id'))
        if payload.get('action') not in P.FIELDS:
            return
    except (ValueError, TypeError, AttributeError):
        return
    if started:
        owner = getattr(engine, '_ingest_session_host', None)
        # Preserve any original pending/terminal receipt. An unhandled exception
        # cannot prove that a copy or project replacement did not happen.
        if owner is not None:
            with owner.lock:
                retained = owner.receipts.get(payload['request_id'])
                if retained is not None:
                    emit(deepcopy(retained))
                    return
                owner._result(payload, 'unknown', error=str(error))
        return
    emit({'event': 'ingest_session_result', 'protocol': P.PROTOCOL,
          'request_id': payload['request_id'], 'action': payload['action'],
          'status': 'failed', 'session': None, 'error': str(error),
          'dispatch_rejected': True})
