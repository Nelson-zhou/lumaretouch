# SPDX-License-Identifier: GPL-3.0-or-later
"""Worker-only genuine target recomputation, with reusable reference evidence.

The cache contains the reference's own full-precision spatial samples and actual
model receipt. No target masks, fitted gains, or target analysis enter that cache.
"""
from copy import deepcopy
from hashlib import sha256
import numpy as np
from . import semantic_colour_state as S, semantic_colour_analysis as A
from .batch_preflight import canonical


def cache_proof(value):
    return sha256(canonical({k:v for k,v in value.items() if k!='proof'}).encode()).hexdigest()


def check_reference(value):
    keys={'version','reference','binding','analysis','samples','coverage','proof'}
    if type(value) is not dict or set(value)!=keys or type(value['version']) is not int or value['version']!=1 or value['proof']!=cache_proof(value):
        raise ValueError('批量追色样片分析缓存不完整或改变')
    from .reference_color_scope import check_params
    reference=check_params({'version':1,'strength':1.,'reference':value['reference']})['reference']
    binding=S.binding(value['binding'])
    if binding['source']!=reference['source'] or binding['render_sha256']!=reference['render_sha256']:
        raise ValueError('批量追色样片分析与真实渲染资产不同')
    analysis=A.check_receipt(value['analysis'])
    if analysis['target_input_sha256']!=analysis['reference_input_sha256']:raise ValueError('样片缓存不能携带其它目标分析')
    samples=value['samples']
    if type(samples) is not list or not 32<=len(samples)<=6144 or any(type(row) is not list or len(row)!=5 or any(type(v) not in (int,float) for v in row) for row in samples):
        raise ValueError('样片联合样本必须是有界的真实数值行')
    rows=np.asarray(samples,dtype=np.float64)
    if rows.ndim!=2 or rows.shape[1]!=5 or not 32<=len(rows)<=6144 or not np.isfinite(rows).all():raise ValueError('样片联合样本形状或数值无效')
    if np.any(np.abs(rows[:,:3])>16) or np.any(rows[:,3]!=np.floor(rows[:,3])) or np.any(rows[:,3]<0) or np.any(rows[:,3]>5) or np.any(rows[:,4]<=0) or np.any(rows[:,4]>1):
        raise ValueError('样片联合样本超出原生有界颜色/类别/权重契约')
    coverage=value['coverage']
    if type(coverage) is not list or len(coverage)!=6:raise ValueError('样片语义覆盖证据不完整')
    for i,row in enumerate(coverage):
        if type(row) is not dict or set(row)!={'class','usable_pixels','weighted_coverage'} or row['class']!=S.CLASSES[i] or type(row['usable_pixels']) is not int or not 0<=row['usable_pixels']<=A.LIMIT:
            raise ValueError('样片语义覆盖证据无效')
        S.number(row['weighted_coverage'],0,1)
    return deepcopy(value)


def reference(request,image,rgb):
    probabilities,receipt=A.infer(image)
    rows,_,coverage=A.samples(rgb,probabilities)
    analysis=A.check_receipt({'backend':A.MODEL,'model_sha256':receipt['model_sha256'],'runtime':receipt['runtime'],
        'target_input_sha256':receipt['input_sha256'],'reference_input_sha256':receipt['input_sha256'],
        'classes':list(S.CLASSES),'analysis_policy':'bounded-rgb8-view-full-float-spatial-samples-v1'})
    record={'version':1,'reference':request['reference'],'binding':request['binding'],'analysis':analysis,
        'samples':rows.tolist(),'coverage':coverage}
    record['proof']=cache_proof(record)
    return check_reference(record)


def target(request,image,rgb):
    from .semantic_colour_native import fit
    from . import semantic_colour_masks as M, semantic_colour_review as R, semantic_colour_portable as P
    intent=P.check(request['intent']);cache=check_reference(request['reference_analysis'])
    if cache['reference']!=intent['reference']:raise ValueError('批量目标与缓存样片不同')
    binding=S.binding(request['binding']);probabilities,receipt=A.infer(image)
    if receipt['model_sha256']!=cache['analysis']['model_sha256'] or receipt['runtime']!=cache['analysis']['runtime']:
        raise ValueError('样片/目标实际模型或运行库版本不同，必须重新分析样片')
    rows,weights,coverage=A.samples(rgb,probabilities)
    parameters,stats=fit(cache['samples'],rows,intent['mode'])
    analysis=A.check_receipt({**cache['analysis'],'target_input_sha256':receipt['input_sha256']})
    recipe=S.empty();recipe.update(enabled=True,mode=intent['mode'],strengths=intent['strengths'],
        target=binding,reference=intent['reference'],analysis=analysis)
    def group(ident,name,p,mask):
        return {'id':ident,'name':name,'enabled':True,'mask_id':mask,'baseline':deepcopy(p),'parameters':deepcopy(p)}
    recipe['groups']=[group('global','全图基础追色',parameters[0],None)]
    for i,name in enumerate(S.LABELS):
        if not stats[i+1][9]:continue
        mask=M.create('semantic_'+S.CLASSES[i],name,binding,weights[...,i]);recipe['masks'].append(mask)
        recipe['groups'].append(group(S.CLASSES[i],name,parameters[i+1],mask['id']))
    recipe=P.apply_offsets(S.check(recipe),intent)
    warnings=['每张目标独立渲染、真实语义分析与 Rust 联合颜色拟合；仅样片分析复用。',
        '精确手动差量叠加在每张目标的新拟合基线上，未复制源照片的拟合参数或蒙版。',
        '诊断是手动差量之前的初始拟合，不是修改后残差或摄影质量证明。',
        '缺少请求类别或差量越界会拒绝该目标，不会悄悄夹取、丢弃或替换。',
        '真实类别仅背景、头发、身体皮肤、面部皮肤、衣物、其它；不声称天空、嘴唇或独立人物分割。',
        '颜色算子不生成光照方向、材质、纹理、景深、季节或构图；非中性 HSV 八色仍为 SDR。']
    record={'version':1,'method':S.ALGORITHM,'target':binding,'reference':cache['binding'],
        'reference_asset':intent['reference'],'recipe':recipe,'diagnostics':stats,
        'coverage':{'target':coverage,'reference':cache['coverage']},'reference_selection':None,'target_selection':None,
        'warnings':warnings,'quality_acceptance':'UNRUN','owned_fields':[S.KEY,'_semantic_colour_bundle','_semantic_colour_mask_assets'],
        'portable_intent':intent,'reference_analysis_proof':cache['proof']}
    record['proof']=R.proof(record)
    R.verify(record,target_binding=binding,reference=intent['reference'])
    return record
