# SPDX-License-Identifier: GPL-3.0-or-later
"""AI-owned fields in the existing BatchSyncController ledger, never another undo stack."""
from copy import deepcopy
from . import semantic_colour_state as S
from .semantic_colour_host import OWNED
from .semantic_colour_batch_target import owned_key


def publish(owner,planned,*,policy,source_snapshot=None,review_token=None,automatic_authority=None):
    """Candidates are independently fitted and verified before this publication."""
    if automatic_authority is not None:
        from .semantic_colour_review import automatic_authority as check_authority
        automatic_authority=check_authority(automatic_authority)
        if review_token is not None:raise ValueError('Automatic assessment cannot claim a reviewed batch token')
    if not planned:raise ValueError('没有可提交的追色目标')
    live=owner.documents.current_index();frame=None
    for index,row,before,after in planned:
        owner.versions.check_advance(row)
        if owner.documents.rows()[index] is not row or not isinstance(row.get('undo'),list) or not isinstance(row.get('redo'),list):raise ValueError('追色目标或历史改变，整批未写入')
        owned_key(before);owned_key(after)
    owner.semantic_colour_inspection=_attempt(owner,planned,'commit',review_token=review_token)
    owner.sequence+=1;bid=f'batch-{owner.sequence:03d}-{int(owner.clock()*1000)}'
    owner.semantic_colour_inspection['batch_id']=bid
    active=next((item for item in planned if item[0]==live),None)
    if active:
        _,row,before,after=active;owner.versions.advance(row)
        try:frame=owner.editor.replay(after,mode='batch',replayed_for=f'semantic_colour:{bid}',strict_local=True)
        except Exception:
            try:owner.editor.replay(before,mode='batch',replayed_for=f'semantic_colour_rollback:{bid}')
            except Exception:owner.editor.invalidate()
            raise
    targets={}
    for index,row,before,after in planned:
        if index!=live:
            owner.versions.advance(row);row['undo'].append(before)
            if len(row['undo'])>owner.history_limit:del row['undo'][0]
            row['redo'].clear()
        row['state']=after
        targets[str(index)]={'path':row['path'],'document_id':owner.versions.version(row).document_id,
            'before':before,'after':after,'applied':owned_key(after),'before_owned':owned_key(before)}
    owner.ledger[bid]={'ops':[S.OP],'targets':targets,'at_ns':owner.monotonic(),'undone':False,
        'policy':policy,'source_snapshot':source_snapshot,'semantic_colour_owned':True,'review_token':review_token}
    if automatic_authority is not None:owner.ledger[bid]['automatic_authority']=deepcopy(automatic_authority)
    owner.last_result={'kind':'commit','batch_id':bid,'applied':[x[0] for x in planned],'skipped':[]}
    owner.editor.mark_dirty();return bid,frame


def restore(owner,request,*,before_write=lambda:None):
    bid=str(request.get('batch_id') or '');batch=owner.ledger.get(bid);redo=request.get('action')=='redo'
    if batch is None or not batch.get('semantic_colour_owned') or bool(batch['undone'])!=redo:raise ValueError('追色批次不在请求的撤销/重做状态')
    owner.documents.remember_current();planned=[];conflicts=[]
    from .semantic_colour_project import validate_decoded
    for rec in batch['targets'].values():
        found=owner.versions.find(owner.documents.rows(),rec['document_id'])
        if found is None:conflicts.append('目标已移除');continue
        index,row=found;before=row['state'];expected=rec['before_owned'] if redo else rec['applied']
        try:
            if row['path']!=rec['path'] or owned_key(before)!=expected:raise ValueError('追色贡献已有后续编辑，不覆盖它')
            original=rec['after'] if redo else rec['before']
            after=dict(before)
            for key in OWNED:after[key]=deepcopy(original[key]) if key==S.KEY else original[key]
            validate_decoded(after);owner.versions.check_advance(row)
            if not isinstance(row.get('undo'),list) or not isinstance(row.get('redo'),list):raise ValueError('目标历史不可用')
            planned.append((index,row,before,after))
        except Exception as error:conflicts.append(str(error)[:500])
    if conflicts:raise ValueError('整组未修改：'+'；'.join(conflicts))
    # Restoration preserves later ordinary edits. Geometry changes suspend the
    # retained masks visibly; they are not remapped or refitted during undo.
    owner.semantic_colour_inspection=_attempt(owner,planned,'redo' if redo else 'undo',batch_id=bid)
    before_write();live=owner.documents.current_index();frame=None
    active=next((x for x in planned if x[0]==live),None)
    if active:
        _,row,before,after=active;owner.versions.advance(row)
        try:frame=owner.editor.replay(after,mode='batch',replayed_for=f'semantic_colour_restore:{bid}')
        except Exception:
            try:owner.editor.replay(before,mode='batch',replayed_for=f'semantic_colour_restore_rollback:{bid}')
            except Exception:owner.editor.invalidate()
            raise
    for index,row,before,after in planned:
        if index!=live:
            owner.versions.advance(row);row['undo'].append(before)
            if len(row['undo'])>owner.history_limit:del row['undo'][0]
            row['redo'].clear()
        row['state']=after
    batch['undone']=not redo;owner.editor.mark_dirty()
    body={'event':'batch_redone' if redo else 'batch_undone','batch_id':bid,'module_scope':[S.OP],
        'restored':[x[0] for x in planned],'conflicts':[],'doc_state':owner.editor.status()}
    owner.last_result={'kind':'redo' if redo else 'undo','batch_id':bid,'restored':body['restored'],'conflicts':[]}
    owner.emit(body)
    if frame is not None:owner.emit(frame)
    return body


def _attempt(owner,planned,kind,**identity):
    return {'kind':kind,**identity,'targets':[{'document_id':owner.versions.version(row).document_id,
        'path':row['path'],'before':owned_key(before),'after':owned_key(after)} for _,row,before,after in planned]}


def inspect(owner,*,cancelled=lambda:False):
    """Explicit whole-attempt inspection, not an ordinary slider/state callback."""
    owner.documents.remember_current();attempt=getattr(owner,'semantic_colour_inspection',None);rows=[]
    if attempt is not None:
        for target in attempt['targets']:
            if cancelled():raise InterruptedError('追色批次核对已取消，不能认定全部核对完成')
            item={k:target[k] for k in ('document_id','path')};found=owner.versions.find(owner.documents.rows(),target['document_id'])
            if found is None or found[1]['path']!=target['path']:item['state']='missing'
            else:
                index,row=found;item['revision']=str(owner.versions.version(row).revision)
                try:
                    actual=owned_key(owner.editor.capture() if index==owner.documents.current_index() else row['state'])
                    before=actual==target['before'];after=actual==target['after']
                    item['state']='both' if before and after else 'after' if after else 'before' if before else 'different'
                except Exception as error:item.update(state='invalid',error=str(error)[:500])
            rows.append(item)
    return {'state':'inspected','inspection':None if attempt is None else {**{k:v for k,v in attempt.items() if k!='targets'},'targets':rows,
        'notice':'仅核对当前保留的追色参数/蒙版/样片资源与本次写入前后身份；不代表当前摄影质量、几何有效性或重新拟合。不能重放原提交 token。'},
        'batches':[{'batch_id':bid,'undone':value['undone'],'targets':len(value['targets'])}
            for bid,value in list(owner.ledger.items())[-32:] if value.get('semantic_colour_owned')]}
