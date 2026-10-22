# SPDX-License-Identifier: GPL-3.0-or-later
"""Thin shared-host contracts. Replay validates retained data, never reruns ML."""
from copy import deepcopy
from . import semantic_colour_state as S, semantic_colour_assets as MA
from .semantic_colour_stage import SemanticColourStage


def current_binding(engine,recipe):
    from .semantic_colour_capture import geometry_key
    from . import local_mask_state as M
    target=deepcopy(recipe['target'])
    if target is None:return None
    source=M.bind_source(engine);state=engine._capture_state()
    people=None
    if hasattr(engine,'_people_owner') and engine._people_managed():
        people={'state':engine._people_owner().snapshot(),'asset_sha256':source['sha256']}
    target['source']=source;target['geometry_sha256']=geometry_key(state,people)
    return target

def sync(engine,*,strict=False):
    if engine._vram is None:return
    recipe=S.check(getattr(engine,S.KEY,None))
    stage=SemanticColourStage(recipe)
    if S.active(recipe):
        try:
            MA.hydrate(recipe,getattr(engine,MA.KEY,{}))
            stage=SemanticColourStage(recipe,binding=current_binding(engine,recipe))
        except (ValueError,OSError) as error:stage.suspension='AI 追色保留暂停：'+str(error)
    if strict and stage.suspension:raise ValueError(stage.suspension)
    engine._vram.semantic_colour=stage

def report(engine):
    p=S.check(getattr(engine,S.KEY,None));out=deepcopy(p)
    for m in out['masks']:
        if m['base'] is not None:m['base']={k:v for k,v in m['base'].items() if k!='data'}
    stage=getattr(getattr(engine,'_vram',None),'semantic_colour',None)
    return {'recipe':out,'suspended':getattr(stage,'suspension',None),'method':S.ALGORITHM,
            'fit_runtime_quality':'UNRUN','backend':'licensed-neural-semantics-plus-original-Rust-optimization',
            'pending_capabilities':['sky-specific semantics','landmark lip support','individual-person correspondence','batch/preset host integration']}

def configure_export(spec,snap,shape,*,for_document):
    recipe=S.check(snap.get('semantic_colour'))
    if S.active(recipe) and not for_document:raise ValueError('AI 追色必须逐目标重新分析/拟合/审核；不能复制源图拟合值')
    MA.hydrate(recipe,snap.get('semantic_colour_mask_assets',{}))
    spec.semantic_colour=recipe;spec.semantic_colour_binding=snap.get('semantic_colour_binding')
    if S.active(recipe):
        from . import local_mask_state as LM
        if spec.semantic_colour_binding is None:raise ValueError('AI 追色导出缺少当前渲染几何身份')
        path=snap.get('semantic_colour_source_path')
        if not path:raise ValueError('AI 追色导出缺少真实源文件验证')
        LM.verify_source({'source':recipe['target']['source']},path,shape)
        spec.semantic_colour_source_path=path;spec.semantic_colour_source_stamp=LM.file_stamp(path)

def export_binding(state,people,source,recipe):
    from .semantic_colour_capture import geometry_key
    p=S.check(recipe)
    if not p['target']:return None
    value=deepcopy(p['target']);value['source']=source;value['geometry_sha256']=geometry_key(state,people)
    return value


def verify_render_source(spec):
    if S.active(spec.semantic_colour):
        from .local_mask_state import file_stamp
        if file_stamp(spec.semantic_colour_source_path)!=spec.semantic_colour_source_stamp:
            raise ValueError('AI 追色源文件在完整渲染期间变化，停止输出')
