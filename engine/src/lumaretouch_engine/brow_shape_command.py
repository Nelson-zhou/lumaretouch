"""Acknowledged atomic eyebrow edit, with source-person ownership."""
from . import brow_shape_state as S,brow_shape_runtime as R


def apply(engine,p,emit):
    if type(p) is not dict or set(p)!={'cmd','recipe','base','document_id','control'} or p['cmd']!='brow_shape':
        raise ValueError('眉形命令字段无效')
    if type(p['document_id']) is not str or p['document_id']!=engine._load_id: raise ValueError('照片已切换，眉形修改未应用')
    reason=engine._guard_editable('brow shape')
    if reason: raise ValueError(reason)
    if p['recipe'] is None: raise ValueError('眉形提交需要完整配方')
    value=S.check(p['recipe']); previous=S.check(getattr(engine,'_brow_shape',None))
    control=p['control']
    if control not in (*S.KEYS,'all'): raise ValueError('未知眉形控件')
    if p['base'] is None: raise ValueError('眉形修改缺少已确认的基准配方')
    base=S.check(p['base'])
    if base!=previous:
        raise ValueError('眉形参数已变化，请等待当前预览后重试；未覆盖较新的左右值')
    old_owner=getattr(engine,'_brow_shape_owner',None)
    pc=engine._precompute
    owner=R.identity(pc.landmarks) if S.active(value) and pc is not None else None
    if S.active(previous) and old_owner is not None and old_owner!=owner and S.active(value):
        raise ValueError('眉形参数属于另一人物，请先重置眉形后再调整当前人物')
    pipe=engine._vram
    names=('brow_shape','brow_shape_field','brow_shape_signature','brow_shape_version',
           'brow_shape_key','brow_shape_suspended','brow_shape_combined','_deform_warp','_deform_warp_key')
    old={name:getattr(pipe,name,None) for name in names}
    try:
        engine._brow_shape=value; engine._brow_shape_owner=owner
        R.sync(engine,strict=True)
        frame=engine._write_current_frame('brow_shape'); frame['doc_state']=engine.doc_state(); emit(frame)
        emit({'event':'brow_shape_done','document_id':engine._load_id,**R.report(engine)})
    except Exception:
        engine._brow_shape=previous; engine._brow_shape_owner=old_owner
        for name,stored in old.items(): setattr(pipe,name,stored)
        try:
            frame=engine._write_current_frame('brow_shape_rollback'); frame['doc_state']=engine.doc_state(); emit(frame)
        except Exception:
            engine._vram=None
            emit({'event':'error','error':'眉形回滚画面失败，请重新加载照片；未报告修改成功'})
        raise
