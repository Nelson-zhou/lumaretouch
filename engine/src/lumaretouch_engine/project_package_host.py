"""Native command owner for immutable portable-package jobs and readback.

Runtime UNRUN. Snapshot only saved projects; packages never alter the live project.
Opening is a separate explicit normal project command with existing dirty guards.
"""
from __future__ import annotations
import copy
import json
import os
import threading
import uuid
from . import project_package_archive as A
from . import project_package_dependencies as D


class Packages:
    def __init__(self, engine, emit, validate):
        self.engine, self.emit, self.validate = engine, emit, validate
        self.lock = threading.RLock()
        self.active = None
        self.worker = None
        self.cancel = threading.Event()
        self.plans = {}
        self.operations = {}

    def blocks(self, name, p):
        with self.lock:
            return self.active is not None and name not in ('project_package', 'hello', 'ping', 'status', 'shutdown')

    def close(self):
        self.cancel.set()
        if self.worker and self.worker is not threading.current_thread(): self.worker.join()

    def result(self, rid, status, **fields):
        message = {'event': 'project_package_result', 'request_id': rid, 'status': status, **fields}
        if len(json.dumps(message, ensure_ascii=False).encode()) > 3_900_000:
            message = {'event':'project_package_result','request_id':rid,'status':'unknown',
                       'error':'回执超过安全大小预算，请保留目标并缩小工程后处理；不会重复写入'}
        self.emit(message)

    def snapshot(self):
        e = self.engine
        if e._project is None or not e._project_path: raise ValueError('请先打开工程')
        if e._project_dirty: raise ValueError('请先保存工程，再创建便携包；不会丢弃未保存修改')
        for key in ('bench', '_export', '_thumbs', '_picks'):
            owner = getattr(e, key, None)
            if owner is not None and owner.is_alive(): raise ValueError('请等待后台任务结束')
        relocation = getattr(e, '_source_relocation_controller', None)
        if relocation and (relocation.active or relocation.uncertain): raise ValueError('请先确认原图重定位结果')
        managed = getattr(e, "_managed_import_controller", None)
        if managed and (managed.active or managed.uncertain): raise ValueError("请先确认导入结果，再创建便携包")
        project = copy.deepcopy(e._project)
        project.pop('_source_path', None); project.pop('_source_sha256', None)
        self.validate(project)
        return project

    def handle(self, p):
        rid, action = p.get('request_id'), p.get('action')
        if not isinstance(rid, str) or not 1 <= len(rid) <= 128: raise ValueError('缺少便携包请求身份')
        allowed = {'cmd','action','request_id','operation_id','include_originals','include_references','archive_path',
                   'destination','preview_id','confirmed','mode','manifest_sha256'}
        if set(p) - allowed: raise ValueError('未知便携包参数')
        with self.lock:
            if action == 'status':
                oid = p.get('operation_id', rid)
                operation = self.operations.get(oid)
                if operation is not None and not (operation['status'] == 'unknown' and p.get('destination')):
                    self.result(rid, operation['status'], operation=copy.deepcopy(operation), **{k:v for k,v in operation.items() if k != 'status'})
                elif p.get('destination'):
                    self.operations.pop(oid, None)
                    self._start(rid, lambda: self.readback(p), destination=p['destination'], operation_id=oid, readback=True)
                else: self.result(rid, 'unknown', operation={'status':'unknown','operation_id':oid}, error='未找到操作记录；请核验原目标，勿重复创建')
                return
            if action == 'cancel':
                oid = p.get('operation_id')
                if oid == self.active:
                    self.cancel.set(); self.result(rid, 'running', operation=copy.deepcopy(self.operations[oid]), message='取消已请求；等待文件边界与最终核验')
                elif oid in self.operations:
                    self.result(rid, self.operations[oid]['status'], operation=copy.deepcopy(self.operations[oid]))
                else: self.result(rid, 'unknown', error='取消结果未知；请查询原操作与目标')
                return
            if self.active is not None: raise ValueError('便携包操作进行中，请等待或取消')
            if action == 'preview_create':
                project = self.snapshot()
                deps = D.inventory(project, p.get('include_originals', False), p.get('include_references', False))
                token = str(uuid.uuid4())
                self.plans = {token: {'mode':'create','project':project,'dependencies':deps}}
                self.result(rid, 'preview', preview={'preview_id':token, **D.summary(project,deps)})
                return
            if action == 'preview_restore':
                archive = p.get('archive_path')
                def preview():
                    inspected = A.inspect_archive(archive, cancel=self.cancel.is_set, progress=self.progress,
                                                  dependency_validator=D.validate_inventory)
                    self.validate(inspected['project'])
                    token = str(uuid.uuid4())
                    plan = {'mode':'restore','archive_path':archive,'manifest_sha256':inspected['manifest_sha256']}
                    with self.lock: self.plans = {token: plan}
                    return {'status':'preview','preview':{'preview_id':token,'manifest_sha256':inspected['manifest_sha256'],
                        'dependencies':inspected['manifest']['dependencies'],
                        'embedded_assets':inspected['manifest'].get('embedded_assets',[]),
                        'model_dependencies':inspected['manifest'].get('model_dependencies'), 'warnings':['恢复到新目录，现有文件不会覆盖；打开工程是单独操作。']}}
                self._start(rid, preview); return
            if action not in ('create','restore'): raise ValueError('未知便携包操作')
            if p.get('confirmed') is not True: raise ValueError('请确认目标和依赖选择')
            plan = self.plans.get(p.get('preview_id'))
            if plan is None or plan['mode'] != action: raise ValueError('预览已过期，请重新检查')
            destination = p.get('destination')
            if not isinstance(destination, str) or not os.path.isabs(destination): raise ValueError('请选择绝对本地目标路径')
            if action == 'create':
                if self.snapshot() != plan['project']: raise ValueError('工程已变化，请重新预览')
                work = lambda: A.create_archive(plan['project'], plan['dependencies'], destination, self.cancel.is_set, self.progress, operation_id=rid)
            else:
                def work():
                    current = A.inspect_archive(plan['archive_path'], cancel=self.cancel.is_set, progress=self.progress,
                                                dependency_validator=D.validate_inventory)
                    if current['manifest_sha256'] != plan['manifest_sha256']: raise ValueError('包在预览后变化，请重新预览')
                    return A.restore_archive(plan['archive_path'], destination, self.cancel.is_set, self.progress,
                                             dependency_validator=D.validate_inventory, project_validator=self.validate, operation_id=rid)
            self._start(rid, work, destination=destination)

    def readback(self, p):
        destination = p['destination']
        if p.get('mode') == 'restore':
            value = A.readback_restore(destination, cancel=self.cancel.is_set, progress=self.progress, dependency_validator=D.validate_inventory)
            if value.get('operation_id') != p.get('operation_id'): raise ValueError('目标恢复回执不属于原操作')
            if p.get('manifest_sha256') and value['manifest_sha256'] != p['manifest_sha256']: raise ValueError('目标清单与原预览不一致')
            return value
        if p.get('mode') != 'create': raise ValueError('缺少原操作类型，不能猜测恢复结果')
        value = A.inspect_archive(destination, cancel=self.cancel.is_set, progress=self.progress,
                                  dependency_validator=D.validate_inventory)
        if value['manifest'].get('operation_id') != p.get('operation_id'): raise ValueError('目标工程包不属于原操作')
        return {'destination':destination,'manifest_sha256':value['manifest_sha256'],
                'missing_dependencies':[d for d in value['manifest']['dependencies'] if d.get('status') != 'bundled']}

    def progress(self, value):
        with self.lock:
            if self.active in self.operations: self.operations[self.active]['progress'] = value

    def _start(self, rid, work, destination=None, operation_id=None, readback=False):
        if self.active is not None: raise ValueError('另一个便携包操作正在进行')
        oid = operation_id or rid
        if oid in self.operations: raise ValueError('操作身份已使用，请查询原操作')
        self.cancel.clear(); self.active = oid
        self.operations[oid] = {'status':'running','operation_id':oid,'destination':destination}
        def run():
            try:
                value = work()
                state = value.pop('status', 'completed')
                value.pop('manifest', None)
                if 'missing' in value: value['missing_dependencies'] = value['missing']
            except A.PackageCancelled as error:
                state, value = ('unknown' if readback else 'cancelled'), {'error':str(error)}
            except Exception as error:
                # Publication can outlive a transport/fsync failure; never report absence merely from an exception.
                state = 'unknown' if readback or (destination and os.path.lexists(destination)) else 'failed'
                value = {'error':str(error),'destination':destination}
            with self.lock:
                self.operations[oid].update(value, status=state)
                self.active = None
                receipt = copy.deepcopy(self.operations[oid])
                if len(self.operations)>64:
                    oldest=next(iter(self.operations))
                    if oldest != oid: self.operations.pop(oldest)
            self.result(rid,state,operation=receipt,**value)
        self.worker = threading.Thread(target=run, name='project-package', daemon=True)
        self.result(rid,'running',operation=copy.deepcopy(self.operations[oid]))
        self.worker.start()
