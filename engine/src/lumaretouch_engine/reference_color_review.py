"""Target-owned prepare/verify hooks for the existing frozen batch/preset owner.

No mutation, disk writes or network. The owner must supply full late-colour
canvases and retained reference asset, and commit all reviewed changes in one
undo group. A matching histogram is NOT admissible correspondence evidence.
"""
from dataclasses import dataclass
from hashlib import sha256
from copy import deepcopy
import numpy as np
from . import reference_color_state as S, reference_color_native as N
from .reference_color_correspondence import pixels,paired_patches,consensus_coverage
from .reference_color_stage import ReferenceColorStage
from .optics_candidate_identity import fingerprint
from .batch_preflight import canonical


@dataclass(frozen=True)
class ColorInput:
    document_id:str
    revision:str
    source:dict
    state_key:str
    rgb:np.ndarray
    authentic_mask:np.ndarray  # True only for retained original-scene support, after geometry.
    domain:str=S.DOMAIN


def validate(frame):
    if not isinstance(frame,ColorInput) or frame.domain!=S.DOMAIN: raise ValueError('参考色彩输入阶段不正确')
    if type(frame.document_id) is not str or not 1<=len(frame.document_id)<=128:
        raise ValueError('参考色彩文档身份无效')
    if type(frame.revision) is not str or not frame.revision.isdecimal(): raise ValueError('参考色彩版本无效')
    S.binding(frame.source);S.digest(frame.state_key)
    rgb=pixels(frame.rgb)
    if not isinstance(frame.authentic_mask,np.ndarray) or frame.authentic_mask.dtype!=np.bool_ or frame.authentic_mask.shape!=rgb.shape[:2]:
        raise ValueError('缺少与编辑画布对应的真实原场景来源掩码')
    return rgb


def pixel_digest(rgb):
    a=np.ascontiguousarray(rgb)
    h=sha256(str((a.shape,a.dtype.str)).encode());h.update(memoryview(a).cast('B'));return h.hexdigest()


def identity(frame,rgb):
    return {'document_id':frame.document_id,'revision':frame.revision,'source':deepcopy(frame.source),
            'state_key':frame.state_key,'render_sha256':pixel_digest(rgb),
            'authentic_mask_sha256':pixel_digest(frame.authentic_mask)}


def prepare(reference,target,*,reference_asset_id,strength=1.,cancelled=lambda:False):
    amount=S.number(strength,0,1);S.digest(reference_asset_id)
    r=validate(reference);t=validate(target)
    if reference.document_id==target.document_id: raise ValueError('参考图保持不变，不可作为统一目标')
    rid=identity(reference,r);tid=identity(target,t)
    a,b,geometry,tp,rp=paired_patches(r,t,reference.authentic_mask,target.authentic_mask,cancelled=cancelled)
    fit=N.fit(a,b)
    geometry.update({'authentic_reference_fraction':float(np.mean(reference.authentic_mask)),
                     'authentic_target_fraction':float(np.mean(target.authentic_mask)),
                     'input':'current-rendered-original-scene-support-not-unedited-illumination'})
    geometry.update(consensus_coverage(tp,rp,fit.pop('inliers'),t.shape,r.shape))
    recipe=S.check({'version':1,'algorithm':S.ALGORITHM,'domain':S.DOMAIN,'strength':amount,
        'log2_gains':fit['log2_gains'],'source':target.source,
        'reference':{'source':reference.source,'render_sha256':rid['render_sha256'],'asset_id':reference_asset_id}})
    # Bounded diagnostics from deterministic evenly-spaced full-precision target samples.
    h,w=t.shape[:2];ys=np.linspace(0,h-1,min(h,256),dtype=int);xs=np.linspace(0,w-1,min(w,256),dtype=int)
    sample=t[ys[:,None],xs[None,:]]
    after=ReferenceColorStage(recipe).apply_np(sample)
    old=np.any((sample<0)|(sample>1),axis=-1)
    new=np.any((after<0)|(after>1),axis=-1)
    added=float(np.mean(new&~old))
    if added>.05: raise ValueError('参考校正预计新增超过 5% 越界像素；请降低程度并重新预检')
    warnings=['非语义匹配；相似纹理、运动主体、不同景深与混合光仍需逐图检查',
              '校正当前编辑成片；真实场景纹理可能已被手动调色或场景染色，不是原始光源测量']
    if added>.005: warnings.append('校正增加超出输出色域的像素，导出可能剪切')
    if fit['residual_p90_stops']>.1: warnings.append('对应区域亮度/颜色存在差异，建议降低程度')
    record={'version':1,'reference':rid,'target':tid,'recipe':recipe,'fit':fit,'geometry':geometry,
            'new_gamut_fraction':added,'warnings':warnings,'method':S.ALGORITHM}
    record['proof']=sha256(canonical(record).encode()).hexdigest()
    return record


def verify(record,reference,target,*,reference_asset_id):
    expected={'version','reference','target','recipe','fit','geometry','new_gamut_fraction','warnings','method','proof'}
    if type(record) is not dict or set(record)!=expected or type(record['version']) is not int or record['version']!=1:
        raise ValueError('参考色彩预检记录无效')
    if sha256(canonical({k:v for k,v in record.items() if k!='proof'}).encode()).hexdigest()!=record['proof']:
        raise ValueError('参考色彩预检记录变化')
    r=validate(reference);t=validate(target)
    if identity(reference,r)!=record['reference'] or identity(target,t)!=record['target']:
        raise ValueError('参考或目标的源图、编辑、版本或输入画布已改变；请重新预检')
    recipe=S.check(record['recipe'])
    if recipe['reference']['asset_id']!=reference_asset_id or recipe['source']!=target.source:
        raise ValueError('参考色彩资源身份变化')
    if record['method']!=S.ALGORITHM or recipe['reference']['source']!=reference.source:
        raise ValueError('参考色彩算法或原样片身份不一致')
    if recipe['reference']['render_sha256']!=record['reference']['render_sha256']:
        raise ValueError('样片渲染摘要不一致')
    return recipe


def candidate_key(state):
    # Target is sampled without old match, then new match replaces it. All manual
    # and non-colour edits remain in the target-owned candidate identity.
    return fingerprint({k:v for k,v in state.items() if k not in (S.KEY,"_reference_color_bundle")})
