"""Virtual document operations. Source files are read-only; writes stay in project memory.

Receipts make retries idempotent in a workspace. Saving persists the receipt with
all document rows; a restarted unsaved operation remains unknown, never replayed.
"""
from copy import deepcopy
import uuid

IDENTITY_KEYS = ('document_id', 'source_asset_id', 'root_document_id', 'copy_number', 'recipe_version_id')


def initialize(row):
    row.setdefault('document_id', uuid.uuid4().hex)
    row.setdefault('source_asset_id', uuid.uuid4().hex)
    row.setdefault('root_document_id', row['document_id'])
    row.setdefault('copy_number', 0)
    row.setdefault('recipe_version_id', uuid.uuid4().hex)
    row.setdefault('document_revision', 0)
    return row


def affected(rows, ids, action):
    selected = [r for r in rows if r['document_id'] in ids]
    wanted = set(ids)
    if action == 'trash':
        roots = {r['root_document_id'] for r in selected if r['copy_number'] == 0}
        wanted.update(r['document_id'] for r in rows if r['root_document_id'] in roots)
    elif action == 'restore':
        wanted.update(r['root_document_id'] for r in selected)
    return [r for r in rows if r['document_id'] in wanted]


class VirtualCopies:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.receipts = {}
        self.workspace = engine._document_versions().workspace

    def state(self):
        e = self.engine
        return {'workspace': e._document_versions().workspace, 'project_id':(e._project or {}).get('project_id'),
                'rows': [{**{k:r[k] for k in IDENTITY_KEYS}, 'path':r['path'],
                          'trashed':bool(r.get('trashed')), 'revision':e._document_versions().version(r).revision}
                         for r in e._docs], 'runtime_verified':False}

    def guard(self):
        e = self.engine
        relocation = getattr(e,'_source_relocation_controller',None)
        if relocation is not None and (relocation.active is not None or relocation.uncertain is not None):
            raise ValueError('原图重定位仍在进行或结果待确认，请先查询原操作')
        for key in ('bench','_export','_thumbs','_picks'):
            task = getattr(e,key,None)
            if task is not None and task.is_alive(): raise ValueError('请等待后台任务结束再管理副本')
        from .sample_library_capture import heavy_reason
        reason = heavy_reason(e)
        if reason: raise ValueError(reason)
        for key in ('_optics_preview_owner','_effect_recovery_preview_owner','_semantic_colour_owner',
                    '_manual_liquify_preview_owner','_studio_background_preview_owner','_sky_replacement_preview_owner','_local_grade_live_owner'):
            owner = getattr(e,key,None)
            if owner is not None and (getattr(owner,'job',None) is not None or getattr(owner,'latest',None) is not None or getattr(owner,'session',None) is not None):
                raise ValueError('请先完成或关闭效果预览，再管理副本')

    def handle(self, p):
        e, rid = self.engine, p.get('request_id')
        result = None
        published = False
        try:
            if not isinstance(rid,str) or not 1 <= len(rid) <= 128: raise ValueError('缺少有界请求身份')
            if set(p)-{'cmd','action','request_id','workspace','document_ids','expected_revisions','operation_id','project_id','original_workspace'}:
                raise ValueError('副本请求包含未知字段')
            action = p.get('action')
            workspace = e._document_versions().workspace
            if workspace != self.workspace:
                self.receipts.clear(); self.workspace = workspace
            key = (workspace,rid)
            if action == 'state': result = self.state()
            elif action == 'query':
                if p.get('project_id') is not None and p['project_id'] != (e._project or {}).get('project_id'):
                    raise ValueError('查询操作属于另一项目，请打开原工程核对')
                prior = self.receipts.get((workspace,p.get('operation_id')))
                persisted = (e._project or {}).get('virtual_copy_receipts',{}).get(p.get('operation_id'))
                result = deepcopy(prior['result'] if prior else persisted) if prior or persisted else {'status':'unknown','operation_id':p.get('operation_id')}
                result['state'] = self.state()
            else:
                if key in self.receipts:
                    prior = self.receipts[key]
                    if prior['request'] != p: raise ValueError('请求身份冲突；原操作未重试')
                    return self.emit(prior['event'])
                if action not in ('create','trash','restore'): raise ValueError('未知副本动作')
                if rid in (e._project or {}).get('virtual_copy_receipts',{}):
                    raise ValueError('此操作身份已有已保存回执，请查询原操作，不能重新执行')
                if p.get('workspace') != workspace: raise ValueError('工作区已变化，请刷新')
                ids = p.get('document_ids')
                if not isinstance(ids,list) or not 1 <= len(ids) <= 64 or any(not isinstance(x,str) for x in ids) or len(set(ids)) != len(ids):
                    raise ValueError('请选择 1–64 个独立文档')
                by_id = {r['document_id']:r for r in e._docs}
                if set(ids)-set(by_id): raise ValueError('文档已变化，请刷新')
                rows = affected(e._docs,ids,action)
                revisions = p.get('expected_revisions')
                if not isinstance(revisions,dict) or any(revisions.get(r['document_id']) != e._document_versions().version(r).revision for r in rows):
                    raise ValueError('关联文档已变化，请重新审核全部受影响文档')
                if len(self.receipts) >= 256: raise ValueError('操作回执已满，请保存并重新打开项目')
                self.guard()
                e._remember_current()
                current = e._docs[e._doc_index] if 0 <= e._doc_index < len(e._docs) else None
                changed = []
                if action == 'create':
                    from . import project as PJ
                    staged = []
                    verified_sources = {}
                    numbers = {}
                    for identity in ids:
                        source = by_id[identity]
                        if source.get('trashed'): raise ValueError('请先恢复回收站中的文档')
                        from .virtual_copy_source import fingerprint_for
                        fp, _ = fingerprint_for(source)
                        verified_sources[source["source_asset_id"]] = fp
                        root = source['root_document_id']
                        number = numbers.get(root,max(r['copy_number'] for r in e._docs if r['root_document_id']==root)) + 1
                        if number > 9007199254740991: raise ValueError("副本编号超出协议整数范围")
                        numbers[root] = number
                        row = deepcopy(source)
                        row.update(document_id=uuid.uuid4().hex,recipe_version_id=uuid.uuid4().hex,
                                   copy_number=number,document_revision=0,undo=[],redo=[],fingerprint=fp)
                        row.pop('_lrt_runtime_version',None)
                        row.pop('_project_version_id',None)
                        row['_history_owned'] = True
                        from .virtual_copy_people import inherit
                        inherit(e,source,row)
                        staged.append(row)
                    # No live list mutation until every selected source is validated.
                    new_rows = list(e._docs)
                    for row in staged:
                        last = max(i for i,r in enumerate(new_rows) if r['root_document_id']==row['root_document_id'])
                        new_rows.insert(last+1,row)
                        changed.append(row['document_id'])
                    for sibling in new_rows:
                        if sibling["source_asset_id"] in verified_sources:
                            sibling["fingerprint"] = deepcopy(verified_sources[sibling["source_asset_id"]])
                    e._docs = new_rows
                    published = True
                else:
                    for row in rows:
                        e._document_versions().check_advance(row)
                    for row in rows:
                        target = action == 'trash'
                        if bool(row.get('trashed')) != target:
                            published = True
                            row['trashed'] = target
                            e._document_versions().advance(row)
                            changed.append(row['document_id'])
                if current is not None: e._doc_index = next(i for i,r in enumerate(e._docs) if r is current)
                if changed:
                    e._project_dirty = True
                    e._cancel_snapshot('virtual_copy:'+action)
                    if current is not None and current.get('trashed'):
                        e._load_id = ''
                        e._image_loaded = False
                        e._doc_index, e._doc_path = -1, None
                        e._history_bind(None)
                result = {'status':'succeeded','operation_id':rid,'changed_document_ids':changed,'state':self.state()}
                event = {'event':'virtual_copy_result','request_id':rid,'success':True,'result':result}
                self.receipts[key] = {'request':deepcopy(p),'result':deepcopy(result),'event':deepcopy(event)}
                e.emit_session_state()
            self.emit({'event':'virtual_copy_result','request_id':rid,'success':True,'result':result})
        except Exception as error:
            event = {'event':'virtual_copy_result','request_id':rid,'success':False,'error':str(error)}
            failure = {'status':'unknown' if published else 'failed','operation_id':rid,'error':str(error)}
            if published: event.update(success=True,result=failure)
            if isinstance(rid,str) and p.get('action') in ('create','trash','restore'):
                key = (e._document_versions().workspace,rid)
                if key not in self.receipts:
                    self.receipts[key] = {'request':deepcopy(p),'event':deepcopy(event),
                        'result':failure}
            self.emit(event)
