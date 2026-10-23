# SPDX-License-Identifier: GPL-3.0-or-later
"""Concrete editor/render adapter for genuine per-target batch recomputation."""
from copy import deepcopy
from hashlib import sha256
from . import semantic_colour_state as S, semantic_colour_assets as MA, semantic_colour_review as R
from .semantic_colour_project import BUNDLE
from .semantic_colour_capture import candidate_key,geometry_key
from .semantic_colour_host import OWNED
from .batch_preflight import canonical


def owned_key(state):
    recipe=S.check(state.get(S.KEY));MA.check(recipe,state.get(MA.KEY,{}))
    from .semantic_colour_project import validate_decoded
    validate_decoded(state)
    return sha256(canonical({'recipe':recipe,'mask_assets':sorted(state.get(MA.KEY,{})),
        'reference_asset':None if recipe['reference'] is None else recipe['reference']['asset_id']}).encode()).hexdigest()


def reference_analysis(intent,bundle,*,cancelled=lambda:False):
    from . import semantic_colour_portable as P,reference_color_assets as A
    from .semantic_colour_canvas import from_reference
    from .semantic_colour_batch_job import BatchFitJob
    intent=P.check(intent)
    if cancelled():raise InterruptedError('追色样片准备已取消')
    from .semantic_colour_batch_reference import hydrate
    hydrate(intent['reference'],bundle)
    frame=from_reference(intent['reference'])
    job=BatchFitJob(frame,reference=intent['reference']);del frame
    return job.wait(cancelled=cancelled)


def prepare(engine,row,state,document_id,revision,intent,cache,*,cancelled=lambda:False):
    import numpy as np
    from .semantic_colour_capture import render
    from .render_snapshot import own_render_inputs
    from .semantic_colour_batch_job import BatchFitJob
    from .semantic_colour_analysis import view
    from .semantic_colour_stage import SemanticColourStage
    from .semantic_colour_controller import png
    from .cpu_memory_budget import available_estimate
    # Snapshot array copying itself is admitted, before the renderer's stricter
    # full-resolution allocation admission. No old fitted masks/reference copy.
    budget=min(512*1024*1024,max(0,available_estimate()-512*1024*1024))
    snapshot=own_render_inputs({k:v for k,v in state.items() if k not in OWNED},max_asset_bytes=budget).value
    frame=render(engine,row,snapshot,document_id,revision,cancelled=cancelled)
    record=BatchFitJob(frame,intent=intent,reference_analysis=cache).wait(cancelled=cancelled)
    _,sample=view(frame)
    after=SemanticColourStage(record['recipe'],binding=frame.binding).apply_np(sample)
    if cancelled():raise InterruptedError('追色目标审核准备已取消')
    record['preview']={'before':png(np.rint(np.clip(sample,0,1)*255).astype(np.uint8)),
        'after':png(np.rint(np.clip(after,0,1)*255).astype(np.uint8)),
        'notice':'完整浮点原画布的空间采样检查预览；不是整幅摄影质量验收。'}
    record['proof']=R.proof(record)
    verify(engine,row,state,document_id,revision,intent,record)
    return record


def verify(engine,row,state,document_id,revision,intent,record):
    from . import semantic_colour_portable as P,local_mask_state as LM,reference_color_assets as A
    intent=P.check(intent);version=engine._document_versions().version(row)
    if version.document_id!=document_id or str(version.revision)!=str(revision):raise ValueError('追色目标编辑版本改变')
    recipe=R.verify(record,target_binding=record['target'],reference=intent['reference'])
    if record.get('portable_intent')!=intent:raise ValueError('追色审核意图与预设/批量请求不同')
    target=record['target']
    if target['document_id']!=document_id or target['revision']!=str(revision):raise ValueError('追色审核属于其它目标版本')
    shape=(row.get('src_h'),row.get('src_w'))
    LM.verify_source({'source':target['source']},row['path'],shape if all(shape) else None)
    from . import virtual_copy_people as VP
    snap=engine._state_to_export_snap(state,device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0.,source_path=row['path'],people_context=VP.row_context(engine,row),people_graph=VP.row_snapshot(engine,row))
    if target['state_key']!=candidate_key(state,snap.get('people')) or target['geometry_sha256']!=geometry_key(state,snap.get('people')):
        raise ValueError('追色目标、素材或共用人物几何在审核后改变')
    path=A.cache_root()/(intent['reference']['asset_id']+'.npz')
    if path.is_symlink() or not path.is_file() or A._hash(path)!=intent['reference']['asset_id']:raise ValueError('追色参考资源在审核后改变')
    return recipe


def install(state,record,bundle):
    recipe=S.check(record['recipe']);recipe['last_review']=R.saved_review(record)
    recipe,assets=MA.retain(recipe)
    out={**state,S.KEY:recipe,MA.KEY:assets,BUNDLE:bundle}
    from .semantic_colour_project import validate_decoded
    validate_decoded(out)
    return out


def public(record):
    return {'proof':record['proof'],'target':deepcopy(record['target']),'diagnostics':deepcopy(record['diagnostics']),
        'coverage':deepcopy(record['coverage']),'analysis':deepcopy(record['recipe']['analysis']),'warnings':list(record['warnings']),'quality_acceptance':'UNRUN',
        'requested_groups':[{'id':g['id'],'enabled':g['enabled']} for g in record['recipe']['groups']]}
