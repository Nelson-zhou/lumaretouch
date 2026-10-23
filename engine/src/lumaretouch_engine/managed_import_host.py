"""Copy admission, cancellable worker, verified project commit and retained receipts.

Requires the shared dispatcher gate BEFORE any mutation fence. A successful disk
commit is never retried after a transport timeout. Reference uses existing add.
"""
from __future__ import annotations
import copy
import json
import os
import threading
import uuid
from . import managed_import_io as IO
from . import managed_import_transaction as TX
from . import project as PJ
from .source_relocation_transaction import read_project, project_digest
from .source_relocation_io import Budget as HashBudget, hash_file

class ManagedImport:
    def __init__(self, engine, emit):
        self.engine,self.emit = engine,emit
        self.lock = threading.RLock()
        self.active = None
        self.uncertain = None
        self.worker = None
        self.cancel = threading.Event()
        self.receipts = {}
        self.requests = {}
        self.workspace = engine._document_versions().workspace
        self.last_operation = None
    def adopt(self):
        workspace = self.engine._document_versions().workspace
        if not self.active and workspace != self.workspace:
            self.workspace = workspace
            self.uncertain = None; self.last_operation = None
            self.receipts.clear(); self.requests.clear()
    def blocks(self,name,p):
        with self.lock:
            self.adopt()
            if name=='project' and p.get('action')=='state': return False
            if not self.active and name=='project' and p.get('action')=='open' and p.get('force') is True: return False
            return bool(self.active or self.uncertain) and name not in ('managed_import','hello','ping','status','shutdown')
    def close(self):
        self.cancel.set()
        if self.worker and self.worker is not threading.current_thread(): self.worker.join()
    def guard(self):
        from .virtual_copy_host import VirtualCopies
        VirtualCopies(self.engine,self.emit).guard()
        e = self.engine
        package = getattr(e,"_project_package_controller",None)
        if package and package.active: raise ValueError("请先完成便携包操作")
        if not e._project or not e._project_path: raise ValueError('复制导入前请先创建并保存工程')
        if e._project_dirty: raise ValueError('复制导入前请先保存当前修改')
        if {r.get('document_id') for r in e._docs}!={r.get('document_id') for r in e._project.get('docs',[])}: raise ValueError('会话有尚未保存的导入，请先保存工程')
        if not isinstance(getattr(e,'_project_disk_sha256',None),str): raise ValueError('请重新保存或打开工程，建立磁盘指纹')
        if len(e._project.get('managed_import_receipts',{}))>=256: raise ValueError('工程导入回执已满，请新建工程')
    def state(self):
        self.adopt()
        reason = None
        try: self.guard()
        except (ValueError,RuntimeError) as error: reason = str(error)
        return {'available':not(reason or self.active or self.uncertain),'reason':reason,'busy':bool(self.active),
                'recovery_operation_id':self.active or self.last_operation,'requires_readback':bool(self.uncertain)}
    def result(self,rid,status,**fields):
        result = {'event':'managed_import_result','request_id':rid,'status':status,**fields}
        with self.lock:
            if isinstance(rid,str) and rid in self.requests: self.receipts[rid] = result
        self.emit(result)
        return result
    def handle(self,p):
        rid = p.get('request_id')
        try:
            if set(p)-{'cmd','action','request_id','operation_id','mode','paths','root'}: raise ValueError('未知导入参数')
            if not isinstance(rid,str) or str(uuid.UUID(rid))!=rid: raise ValueError('导入需要规范 UUID 请求身份')
            with self.lock:
                self.adopt()
                action = p.get('action')
                if action=='state': return self.result(rid,'readback',state=self.state())
                if action=='cancel':
                    if p.get('operation_id')==self.active: self.cancel.set()
                    return self.result(rid,'readback',state=self.state())
                if action=='query':
                    operation = p.get('operation_id')
                    if self.uncertain and operation==self.uncertain['id']:
                        pending = self.uncertain
                        raw,digest = read_project(pending['path'])
                        if digest==pending['sha']:
                            self.publish(json.loads(raw),pending['rows'],digest)
                            self.uncertain = None
                            self.result(operation,'succeeded',imported=len(pending['rows']),reconciled=True)
                    receipt = self.receipts.get(operation) or (self.engine._project or {}).get('managed_import_receipts',{}).get(operation)
                    return self.result(rid,'readback',operation=receipt or {'request_id':operation,'status':'unknown'},state=self.state())
                if action!='start': raise ValueError('未知导入动作')
                if rid in self.requests:
                    if self.requests[rid]!=p: raise ValueError('请求身份冲突，未重试')
                    return self.emit(self.receipts[rid])
                previous = (self.engine._project or {}).get('managed_import_receipts',{}).get(rid)
                if previous: return self.result(rid,previous['status'],imported=previous['imported'],replayed=True)
                if self.active or self.uncertain: raise ValueError('请先查询原导入操作')
                if len(self.requests)>=256: raise ValueError('会话回执已满，请保存后重启')
                mode = p.get('mode','reference')
                if mode not in ('reference','copy'): raise ValueError('请选择引用或复制模式')
                if mode=='reference':
                    if p.get('root'): raise ValueError('引用模式不使用托管目录')
                    from .export_destination_import import expand
                    from .session import IMAGE_EXTS, MAX_DOCS
                    paths,_ = expand(p.get('paths',[]),IMAGE_EXTS,MAX_DOCS)
                    before = len(self.engine._docs)
                    self.engine.cmd_session({'cmd':'session','action':'add','paths':p['paths']})
                    if not all(any(r['path']==path for r in self.engine._docs) for path in paths): raise ValueError('引用添加尚未确认，请检查会话')
                    if len(self.engine._docs)!=before and self.engine._project is not None: self.engine._project_dirty = True
                    self.requests[rid] = copy.deepcopy(p)
                    return self.result(rid,'succeeded',imported=len(self.engine._docs)-before,mode='reference')
                self.guard()
                if not isinstance(p.get('root'),str): raise ValueError('请选择托管目录')
                project = copy.deepcopy(self.engine._project)
                snapshot = (project,self.engine._project_path,self.engine._project_disk_sha256,self.workspace)
                self.active = rid; self.last_operation = rid; self.cancel.clear()
                self.requests[rid] = copy.deepcopy(p)
                self.result(rid,'pending',progress={'phase':'preparing','bytes':0,'total':0})
                self.worker = threading.Thread(target=self.work,args=(copy.deepcopy(p),snapshot),daemon=True,name='managed-import')
                try: self.worker.start()
                except Exception:
                    self.active = None
                    raise
        except Exception as error:
            return self.result(rid,'unknown' if self.uncertain else 'failed',error=str(error))
    def work(self,p,snapshot):
        rid,rootfd = p['request_id'],None
        prepared = []
        try:
            project,path,disk_sha,workspace = snapshot
            before_digest = project_digest(project)
            from .session import IMAGE_EXTS
            budget = IO.Budget(self.cancel.is_set,lambda progress:self.result(rid,'pending',progress=progress))
            items = IO.select(p.get('paths'),IMAGE_EXTS,budget)
            rootfd = IO.open_directory(p['root'])
            free = os.fstatvfs(rootfd)
            if free.f_bavail*free.f_frsize < budget.total+IO.RESERVE: raise OSError('托管目录空间不足，未开始复制')
            for item in items: prepared.append(IO.prepare(item,rootfd,p['root'],rid,budget))
            rows = []
            for item in prepared:
                row = self.engine._new_row(item['path'])
                row['name'] = os.path.basename(item['source'])
                row['fingerprint'] = item['fingerprint']
                row['import_origin'] = item['origin']
                row['managed_import'] = {'operation_id':rid,'original_path':item['source'],'original_stat':item['signature'],
                                         'content_sha256':item['sha256'],'managed_root':p['root'],'mode':'copy'}
                stored = PJ.add_doc(project,row['path'],row['state'],fp=row['fingerprint'],version_id=row['recipe_version_id'],
                                    **{k:row[k] for k in ('document_id','source_asset_id','root_document_id','copy_number','recipe_version_id')})
                from .virtual_copy_project import save_row
                save_row(project,row,stored,PJ)
                stored['managed_import'] = copy.deepcopy(row['managed_import'])
                rows.append(row)
            def recheck():
                budget.check()
                e = self.engine
                if e._document_versions().workspace!=workspace or e._project_path!=path or e._project_dirty or project_digest(e._project)!=before_digest:
                    raise ValueError('导入期间工程已变化，未登记复制文件')
                checks = HashBudget(self.cancel.is_set)
                for item in prepared:
                    found = hash_file(item['path'],checks,item['size'])
                    if found['sha256']!=item['sha256']: raise ValueError('登记前托管文件内容已变化')
            receipt = TX.persist(path,project,disk_sha,rid,PJ.validate,self.cancel.is_set,recheck,imported=len(rows))
            with self.lock:
                self.uncertain = {'id':rid,'path':path,'sha':receipt['sha256'],'rows':rows}
                if receipt['status']=='unknown': self.result(rid,'unknown',error=receipt.get('error'),requires_readback=True)
                else:
                    self.publish(receipt['project'],rows,receipt['sha256'])
                    self.uncertain = None
                    self.result(rid,'succeeded',imported=len(rows),mode='copy')
        except Exception as error:
            self.result(rid,'unknown' if self.uncertain else ('cancelled' if isinstance(error,InterruptedError) else 'failed'),
                        error=str(error),verified_copies=[r['path'] for r in prepared],
                        notice='已发布的完整复制文件保留供核对；未登记的不算导入成功。原图未移动或删除。')
        finally:
            if rootfd is not None: os.close(rootfd)
            with self.lock: self.active = None
    def publish(self,project,rows,digest):
        e = self.engine
        with e._doclock:
            existing = {row['document_id'] for row in e._docs}
            e._docs.extend(row for row in rows if row['document_id'] not in existing)
            e._project = {**project,'_source_path':e._project_path,'_source_sha256':digest}
            e._project_disk_sha256 = digest
            e._project_saved_ns = project.get('updated_ns')
            e._project_dirty = False
        e.emit_session_state()


def handle(engine,payload,emit):
    if not hasattr(engine,'_managed_import_controller'): engine._managed_import_controller = ManagedImport(engine,emit)
    return engine._managed_import_controller.handle(payload)
