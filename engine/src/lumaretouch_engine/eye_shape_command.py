"""Acknowledged atomic eye edit, with source-person ownership."""
from . import eye_shape_state as S,eye_shape_runtime as R


def apply(engine,p,emit):
    if type(p) is not dict or set(p)!={'cmd','recipe','base','document_id','control'} or p['cmd']!='eye_shape':
        raise ValueError('眼形命令字段无效')
    if type(p['document_id']) is not str or p['document_id']!=engine._load_id: raise ValueError('照片已切换，眼形修改未应用')
    reason=engine._guard_editable('eye shape')
    if reason: raise ValueError(reason)
    if p['recipe'] is None: raise ValueError('眼形提交需要完整配方')
    value=S.check(p['recipe']); previous=S.check(getattr(engine,'_eye_shape',None))
    control=p['control']
    if control not in (*S.KEYS,'all'): raise ValueError('未知眼形控件')
    if p['base'] is None: raise ValueError('眼形修改缺少已确认的基准配方')
    base=S.check(p['base'])
    if base!=previous:
        raise ValueError('眼形参数已变化，请等待当前预览后重试；未覆盖较新的参数')
    # One-inflight owner submits the full latest intent; control is metadata.
    old_owner=getattr(engine,'_eye_shape_owner',None)
    pc=engine._precompute
    owner=R.identity(pc.landmarks) if S.active(value) and pc is not None else None
    if S.active(previous) and old_owner is not None and old_owner!=owner and S.active(value):
        raise ValueError('眼形参数属于另一人物，请先重置眼形后再调整当前人物')
    pipe=engine._vram
    if pipe is None: raise ValueError('眼形缺少活动照片管线')
    names=('eye_shape','eye_shape_field','eye_shape_signature','eye_shape_version',
           'eye_shape_key','eye_shape_suspended','eye_shape_combined','_deform_warp','_deform_warp_key')
    old={name:getattr(pipe,name,None) for name in names}
    engine._eye_shape_refusal=None
    try:
        engine._eye_shape=value; engine._eye_shape_owner=owner
        R.sync(engine,strict=True)
        frame=engine._write_current_frame('eye_shape'); frame['doc_state']=engine.doc_state(); emit(frame)
    except Exception as error:
        engine._eye_shape=previous; engine._eye_shape_owner=old_owner
        for name,stored in old.items(): setattr(pipe,name,stored)
        try:
            frame=engine._write_current_frame('eye_shape_rollback'); frame['doc_state']=engine.doc_state(); emit(frame)
        except Exception:
            engine._vram=None
            emit({'event':'error','error':'眼形回滚画面失败，请重新加载照片；未报告修改成功'})
        if isinstance(error,R.EyeRefusal):
            engine._eye_shape_refusal=(engine._load_id,R.identity(engine._precompute.landmarks),error.facts)
        raise
