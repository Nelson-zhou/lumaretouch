# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen proposal/review proof. A low colour residual never certifies quality."""
from copy import deepcopy
from hashlib import sha256
import numpy as np
from . import semantic_colour_state as S, semantic_colour_masks as M
from .batch_preflight import canonical


def proof(record):return sha256(canonical({k:v for k,v in record.items() if k!='proof'},limit=24*1024*1024).encode()).hexdigest()

def prepare(request,reference_image,reference_rgb,target_image,target_rgb):
    from .semantic_colour_analysis import infer,samples,check_receipt,MODEL
    from .semantic_colour_native import fit
    rp,ri=infer(reference_image);tp,ti=infer(target_image)
    if ri['model_sha256']!=ti['model_sha256'] or ri['runtime']!=ti['runtime']:raise ValueError('双图分析模型/运行库不一致')
    local=request['local_only'];rsel=tsel=None
    if local:
        for key,binding in (('reference_selection',request['reference_binding']),('target_selection',request['target_binding'])):
            selected=M.check(request[key])
            if selected['binding']!=binding:raise ValueError('双图局部选择不属于自己的冻结画布')
        rsel=M.raster(request['reference_selection'],reference_rgb.shape[:2]);tsel=M.raster(request['target_selection'],target_rgb.shape[:2])
        if any(np.count_nonzero(v>.05)<64 for v in (rsel,tsel)):raise ValueError('局部追色需要两张图各自至少 64 个有效支持像素')
    r,_,rc=samples(reference_rgb,rp,rsel);t,weights,tc=samples(target_rgb,tp,tsel)
    parameters,stats=fit(r,t,request['mode'])
    receipt=check_receipt({'backend':MODEL,'model_sha256':ti['model_sha256'],'runtime':ti['runtime'],
        'target_input_sha256':ti['input_sha256'],'reference_input_sha256':ri['input_sha256'],
        'classes':list(S.CLASSES),'analysis_policy':'bounded-rgb8-view-full-float-spatial-samples-v1'})
    recipe=S.empty();recipe.update(enabled=True,mode=request['mode'],local_only=local,
        strengths=request['strengths'],target=request['target_binding'],reference=request['reference'],analysis=receipt)
    def group(ident,name,p,mask):return {'id':ident,'name':name,'enabled':True,'mask_id':mask,'baseline':deepcopy(p),'parameters':deepcopy(p)}
    if local:
        selection=deepcopy(request['target_selection']);selection['id']='selected_target';selection['name']='目标局部选区'
        recipe['masks']=[selection];recipe['groups']=[group('selected','局部追色',parameters[0],selection['id'])]
    else:
        recipe['groups']=[group('global','全图基础追色',parameters[0],None)]
        for c,name in enumerate(S.LABELS):
            if not stats[c+1][9]:continue
            mask=M.create('semantic_'+S.CLASSES[c],name,request['target_binding'],weights[...,c])
            recipe['masks'].append(mask);recipe['groups'].append(group(S.CLASSES[c],name,parameters[c+1],mask['id']))
    recipe=S.check(recipe)
    warnings=['真实六类分割 + 原创受约束颜色参数优化；不是训练好的追色神经网络。',
        '低残差只说明所选语义颜色分布接近，不代表照片自然、肤色正确或摄影质量合格。',
        '不生成纹理，不改变光照方向、材质、景深、季节或构图。',
        '当前真实类别仅人像背景、头发、身体皮肤、面部皮肤、衣物、其它；不声称天空、嘴唇或独立人物分割。',
        '非中性八色控件沿用 SDR HSV 分段语义，会夹到 0–1；不是 HDR HSL。']
    unmatched=[S.LABELS[i] for i in range(6) if not stats[i+1][9]]
    if unmatched:warnings.append('两图缺少可用共同支持的类别：'+'、'.join(unmatched)+'；没有为这些类别生成局部组。')
    if local:warnings.append('局部双图追色不支持批量或预设同步。')
    record={'version':1,'method':S.ALGORITHM,'target':request['target_binding'],'reference':request['reference_binding'],
        'reference_asset':request['reference'],'recipe':recipe,'diagnostics':stats,'coverage':{'target':tc,'reference':rc},
        'reference_selection':deepcopy(request['reference_selection']),'target_selection':deepcopy(request['target_selection']),
        'warnings':warnings,'quality_acceptance':'UNRUN','owned_fields':[S.KEY,'_semantic_colour_bundle','_semantic_colour_mask_assets']}
    record['proof']=proof(record)
    return record

def verify(record,*,target_binding,reference):
    if type(record) is not dict or record.get('version')!=1 or record.get('method')!=S.ALGORITHM or record.get('proof')!=proof(record):raise ValueError('AI 追色审核记录不完整或已变化')
    if record['target']!=S.binding(target_binding) or record['reference_asset']!=reference:raise ValueError('目标/样片在审核后变化，请重新分析；未应用旧结果')
    ref_binding=S.binding(record['reference'])
    if ref_binding['source']!=reference['source'] or ref_binding['render_sha256']!=reference['render_sha256']:raise ValueError('AI 追色参考像素与资源身份不一致')
    recipe=S.check(record['recipe'])
    if recipe['target']!=record['target'] or recipe['reference']!=reference:raise ValueError('AI 追色审核与参数归属不一致')
    return recipe

def public(record):
    """No multi-MiB retained mask blobs or original photo pixels in status."""
    r=deepcopy(record)
    r.pop('reference_selection');r.pop('target_selection')
    for m in r['recipe']['masks']:
        m['base']=None if m['base'] is None else {k:v for k,v in m['base'].items() if k!='data'}
    return r


def check_saved_review(value):
    expected={'proof','reference_binding','diagnostics','coverage','warnings','quality_acceptance','owned_fields'}
    if type(value) is not dict or set(value)!=expected or value['quality_acceptance']!='UNRUN':raise ValueError('AI 追色保留审核摘要无效')
    S.digest(value['proof']);S.binding(value['reference_binding'])
    if value['owned_fields']!=[S.KEY,'_semantic_colour_bundle','_semantic_colour_mask_assets']:raise ValueError('AI 追色审核所有权无效')
    rows=value['diagnostics']
    if type(rows) is not list or len(rows)!=7 or any(type(row) is not list or len(row)!=10 for row in rows):raise ValueError('AI 追色诊断维度无效')
    for row in rows:
        for item in row:S.number(item,0,1e100)
    coverage=value['coverage']
    if type(coverage) is not dict or set(coverage)!={'reference','target'}:raise ValueError('AI 追色双图覆盖度无效')
    for side in coverage.values():
        if type(side) is not list or len(side)!=6:raise ValueError('AI 追色覆盖类别数无效')
        for i,row in enumerate(side):
            if type(row) is not dict or set(row)!={'class','usable_pixels','weighted_coverage'} or row['class']!=S.CLASSES[i]:raise ValueError('AI 追色覆盖类别无效')
            if type(row['usable_pixels']) is not int or not 0<=row['usable_pixels']<=262144:raise ValueError('AI 追色支持点预算无效')
            S.number(row['weighted_coverage'],0,1)
    if type(value['warnings']) is not list or len(value['warnings'])>20 or any(type(w) is not str or len(w)>1000 for w in value['warnings']):raise ValueError('AI 追色警告摘要过大')
    return deepcopy(value)


def saved_review(record):
    return check_saved_review({'proof':record['proof'],'reference_binding':record['reference'],
        **{key:record[key] for key in ('diagnostics','coverage','warnings','quality_acceptance','owned_fields')}})
