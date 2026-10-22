"""Atomic edit adapter; server's ordinary edit transaction owns history."""
from . import lip_makeup_state as S, lip_makeup_runtime as R


def apply(engine,p,emit):
    if type(p) is not dict or set(p)!={'cmd','recipe','document_id','control'} or p['cmd']!='lip_makeup':
        raise ValueError('唇妆命令字段无效')
    if type(p['document_id']) is not str or p['document_id']!=engine._load_id:
        raise ValueError('照片已切换，唇妆修改未应用')
    reason=engine._guard_editable('lip makeup')
    if reason: raise ValueError(reason)
    if p['recipe'] is None: raise ValueError('唇妆提交必须包含完整配方')
    value=S.check(p['recipe'])
    previous=S.check(getattr(engine,'_lip_makeup',None))
    control=p['control']
    if control not in (*S.KEYS,'all'): raise ValueError('唇妆控件无效')
    if control!='all': value=S.patch(previous,{control:value[control]})
    pipe=engine._vram
    names=('lip_makeup','lip_makeup_layer','lip_makeup_delta','lip_makeup_local',
           'lip_makeup_face','lip_makeup_facts','lip_makeup_suspended')
    old={name:getattr(pipe,name,None) for name in names}
    old_layer=old['lip_makeup_layer']
    cache_state=dict(old_layer.__dict__) if old_layer is not None else None
    try:
        # Keep source analysis across slider updates; retain immutable arrays
        # and the prior solver cache metadata for atomic rollback.
        engine._lip_makeup=value
        R.sync(engine,strict=True)
        frame=engine._write_current_frame('lip_makeup')
        frame['doc_state']=engine.doc_state()
        emit(frame)
        emit({'event':'lip_makeup_done','document_id':engine._load_id,
              'recipe':value,'facts':getattr(pipe,'lip_makeup_facts',{})})
    except Exception:
        engine._lip_makeup=previous
        if old_layer is not None: old_layer.__dict__.clear(); old_layer.__dict__.update(cache_state)
        for name,stored in old.items(): setattr(pipe,name,stored)
        try:
            frame=engine._write_current_frame('lip_makeup_rollback')
            frame['doc_state']=engine.doc_state(); emit(frame)
        except Exception:
            engine._vram=None
            emit({'event':'error','error':'唇妆回滚画面失败，请重新加载照片；未报告修改成功'})
        raise
