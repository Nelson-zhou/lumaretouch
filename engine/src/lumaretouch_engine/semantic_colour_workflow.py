# SPDX-License-Identifier: GPL-3.0-or-later
"""Concrete small-message batch/preset workflow, ready for the shared native host.

All editor mutations still use the existing batch ledger. File export inclusion
is explicit; private reference bytes and proposal masks never become receipts.
"""
import os
import uuid
from . import semantic_colour_state as S, semantic_colour_batch as B, semantic_colour_preset as E
from .semantic_colour_project import BUNDLE
ACTIONS={
    'batch_prepare':{'action','context','session_id','targets','policy'},
    'batch_preview':{'action','preflight_token','document_id'},
    'batch_apply':{'action','context','preflight_token','reviewed'},
    'batch_restore':{'action','context','batch_id','redo'},
    'workflow_cancel':{'action','session_id'},
    'workflow_release':{'action'},
    'workflow_inspect':{'action'},
    'preset_export_prepare':{'action','context','include_reference'},
    'preset_export_write':{'action','export_id','path','overwrite'},
    'preset_export_release':{'action','export_id'},
    'preset_export_status':{'action','export_id','path','expected'},
    'preset_import':{'action','path'},
    'preset_forget':{'action','import_id'},
    'preset_prepare':{'action','context','session_id','import_id'},
}


class Workflow:
    def __init__(self,photo):
        self.photo=photo;self.engine=photo.engine;self.sessions={};self.exports={};self.imports={};self.workspace=self.engine._document_versions().workspace
    def tick(self):
        workspace=self.engine._document_versions().workspace
        if self.workspace!=workspace:self.close();self.workspace=workspace
        batch=self.engine.__dict__.get('_batch_sync');service=self.engine.__dict__.get('_semantic_colour_batch_owner')
        if batch is not None and service is not None:
            service.assets.prune(batch.preflight.store)
            self.sessions={s:t for s,t in self.sessions.items() if t in batch.preflight.store.pending}
    def close(self):
        for prepared in self.exports.values():prepared.close()
        self.exports.clear();self.imports.clear()
        for session in list(self.sessions):self.cancel(session)
        service=self.engine.__dict__.get('_semantic_colour_batch_owner')
        if service is not None:service.close();self.engine.__dict__.pop('_semantic_colour_batch_owner',None)
    def cancel(self,session):
        S.identifier(session);token=self.sessions.pop(session,None)
        if token is not None:
            batch=self.engine._batch_controller();batch.preflight.store.pending.pop(token,None)
            B.owner(self.engine).assets.release(token)
        return {'state':'cancelled','session_id':session}
    def _prepared(self,token):
        batch=self.engine._batch_controller()
        return batch,batch.preflight.store.get(token,batch.versions.workspace)
    def _flag_write(self):self.photo.write_started=True
    def _progress(self,session,value):
        self.photo.emit({'event':'semantic_colour_progress','session_id':session,'progress':value})
    def execute(self,request,*,cancelled=lambda:False):
        self.tick();action=request.get('action')
        if action not in ACTIONS or set(request)!=ACTIONS[action]:raise ValueError('追色批量/便携预设字段无效')
        if cancelled():raise InterruptedError('追色操作已取消')
        if 'context' in request:self.photo._guard(request['context'])
        if action=='workflow_cancel':return self.cancel(request['session_id'])
        if action=='workflow_release':self.close();return {'released':True}
        if action=='workflow_inspect':
            from .semantic_colour_batch_ledger import inspect
            return inspect(self.engine._batch_controller(),cancelled=cancelled)
        if action in ('batch_prepare','preset_prepare'):
            session=S.identifier(request['session_id'])
            if len(session)!=32:raise ValueError('追色工作会话身份无效')
            for previous in list(self.sessions):self.cancel(previous)
            self.photo.close();batch=self.engine._batch_controller()
            options={'cmd':'batch','action':'preflight','request_id':session,'module_scope':[S.OP],
                'semantic_colour':{'source':'current'},'conflict_policy':request.get('policy','recheck')}
            extra={}
            if action=='batch_prepare':options['docs']=request['targets']
            else:
                imported=self.imports.get(request['import_id'])
                if imported is None:raise ValueError('便携预设导入已释放，请重新选择文件')
                options['docs']=[self.engine._docs[self.engine._doc_index]['path']]
                extra={'intent':imported['intent'],'bundle':imported['chunks'],'include_current':True}
            body=B.owner(self.engine).preflight(batch.preflight,options,cancelled=cancelled,
                progress=lambda value:self._progress(session,value),**extra)
            self.sessions[session]=body['preflight_token']
            try:
                self.photo._guard(request['context'])
                if cancelled():raise InterruptedError('追色方案发布前已取消')
            except BaseException:self.cancel(session);raise
            return body
        if action=='batch_preview':
            batch,plan=self._prepared(request['preflight_token'])
            return B.owner(self.engine).preview(batch.preflight,plan.token,request['document_id'])
        if action=='batch_apply':
            if request['reviewed'] is not True:raise ValueError('请审核逐目标结果和警告后明确应用')
            batch,plan=self._prepared(request['preflight_token'])
            result=B.owner(self.engine).commit(batch.preflight,{'cmd':'batch','action':'commit','preflight_token':plan.token},plan,
                cancelled=cancelled,before_write=self._flag_write,record_live_history=True)
            for session,token in list(self.sessions.items()):
                if token==plan.token:self.sessions.pop(session,None)
            return result
        if action=='batch_restore':
            if type(request['redo']) is not bool:raise ValueError('追色恢复方向无效')
            from .semantic_colour_batch_ledger import restore
            before=self.engine._history_capture()
            result=restore(self.engine._batch_controller(),{'batch_id':request['batch_id'],'action':'redo' if request['redo'] else 'undo'},before_write=self._flag_write)
            self.engine._history_record('AI 追色批次恢复',before,coalesce=False);return result
        if action=='preset_export_prepare':
            if len(self.exports)>=2:raise ValueError('已有两个待保存预设，请先保存或取消')
            from . import reference_color_assets as A
            state=self.engine._capture_state();recipe=S.check(state.get(S.KEY))
            if request['include_reference'] is not True:raise ValueError('导出包含完整样片照片，必须明确勾选同意')
            from .semantic_colour_batch_reference import hydrate
            hydrate(recipe['reference'],state.get(BUNDLE))
            prepared=E.prepare_export(recipe,include_reference=True)
            try:
                if cancelled():raise InterruptedError('便携预设准备已取消')
                self.photo._guard(request['context']);ident=uuid.uuid4().hex;self.exports[ident]=prepared
                return {'export_id':ident,**prepared.metadata}
            except BaseException:prepared.close();raise
        if action=='preset_export_release':
            prepared=self.exports.pop(request['export_id'],None)
            if prepared is not None:prepared.close()
            return {'released':True}
        if action=='preset_export_status':
            prepared=self.exports.get(request['export_id'])
            expected=request['expected']
            if type(expected) is not dict or set(expected)!={'file_bytes','file_sha256'}:raise ValueError('导出核对需要原始不可变文件回执')
            expected={'file_bytes':E._integer(expected['file_bytes'],E.MAX_FILE_BYTES),'file_sha256':S.digest(expected['file_sha256'])}
            if prepared is not None and expected!={k:prepared.metadata[k] for k in expected}:raise ValueError('核对回执与原待保存内容不一致')
            path=request['path']
            if type(path) is not str or not 1<=len(path)<=4096:raise ValueError('导出核对路径无效')
            try:actual=E._file_identity(path)
            except FileNotFoundError:return {'state':'missing','path':os.path.abspath(path)}
            # A restarted engine no longer has its temporary artifact. The UI
            # retains the original receipt, so exact read-only hash inspection
            # still works; this never recreates an export or retries a write.
            return {'state':'matching' if actual==expected else 'different','path':os.path.abspath(path),**actual}
        if action=='preset_export_write':
            prepared=self.exports.get(request['export_id'])
            if prepared is None:raise ValueError('待保存预设已释放')
            path=request['path']
            if type(path) is not str or not 1<=len(path)<=4096 or type(request['overwrite']) is not bool:raise ValueError('预设保存路径或覆盖许可无效')
            self._flag_write();result=E.write_prepared(prepared,path,overwrite=request['overwrite'])
            # Keep immutable prepared bytes until explicit receipt acknowledgement
            # or close, so a lost success reply can be reconciled by exact readback.
            return {'state':'exported','path':os.path.abspath(path),**result}
        if action=='preset_import':
            if len(self.imports)>=2:raise ValueError('已有两个导入预设，请先应用或释放')
            path=request['path']
            if type(path) is not str or not 1<=len(path)<=4096:raise ValueError('便携预设路径无效')
            from .cpu_memory_budget import available_estimate
            from . import reference_color_assets as A
            # Conservative admission covers opaque chunks plus authentic NPZ
            # verification temporaries before any imported photo decompression.
            if available_estimate()<2*A.MAX_RAW_BYTES+2*A.MAX_BYTES+128*1024*1024:
                raise ValueError('便携预设完整样片验证内存不足，不会以缩略图代替')
            envelope=E.load_file(path)
            if cancelled():raise InterruptedError('便携预设导入已取消')
            intent=E.hydrate(envelope)
            if cancelled():raise InterruptedError('便携预设导入已取消')
            ident=uuid.uuid4().hex;self.imports[ident]=envelope
            return {'import_id':ident,'intent':intent,'reference_included':True,
                'reference_bytes':envelope['reference_resource']['bytes'],'reference_sha256':intent['reference']['asset_id'],
                'notice':'仅导入拥有的样片和意图；必须对当前目标重新拟合并审核，不会直接复制颜色参数。'}
        if action=='preset_forget':
            self.imports.pop(request['import_id'],None);return {'released':True}
        raise ValueError('不支持的追色工作操作')


def dispatch(photo,request,*,cancelled=lambda:False):
    service=getattr(photo,'workflow',None)
    if service is None:service=photo.workflow=Workflow(photo)
    return service.execute(request,cancelled=cancelled)
