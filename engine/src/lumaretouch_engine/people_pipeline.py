"""Preview/tile adapter preserving the established portrait stage order.

Host calls source_effect for chroma/skin/wrinkle/lip before geometry, warp once for RGB and
all source masks, then post_effects for eye/teeth and eye-detail. Prepared full
source layers are cropped into tile halos, NEVER re-solved per export tile.
"""
import numpy as np
from .ops.deform import prepare_warp_t, apply_prepared_warp_t, identity_grid
from .ops import enhance as H
from .people_effects import verify_recovery


def active(pipe):
    return getattr(pipe,'people_prepared',None) is not None


def install(pipe, prepared, *, origin=(0,0)):
    import torch
    y,x=origin; h,w=pipe.h,pipe.w
    delta=prepared.geometry.delta
    if min(y,x)<0 or y+h>delta.shape[1] or x+w>delta.shape[2]: raise ValueError('People tile is outside its frozen source')
    dtype=torch.float64 if pipe.high_precision_warp else torch.float32
    cropped=torch.as_tensor(np.array(delta[:,y:y+h,x:x+w],copy=True),device=pipe.device,dtype=dtype)
    warp=prepare_warp_t(cropped,h,w,base=identity_grid(h,w,pipe.device,dtype=dtype))
    # Publish only after tensor/grid allocation succeeds; old prepared state is
    # still available to the existing transaction owner for rollback.
    pipe.people_prepared=prepared;pipe.people_origin=tuple(origin);pipe.people_warp=warp


def clear(pipe):
    pipe.people_prepared=None;pipe.people_origin=(0,0);pipe.people_warp=None


def warp(pipe,pixels):
    import torch
    if not active(pipe): raise ValueError('All-face map has not been prepared')
    sample=pixels.to(torch.float64) if pipe.high_precision_warp else pixels
    result=apply_prepared_warp_t(sample,pipe.people_warp).to(pixels.dtype)
    if not torch.isfinite(result).all(): raise ValueError('All-face sampler produced nonfinite values')
    return result


def _local(pipe,record,values,channels):
    """Place one source ROI inside current tile; no owner or scale inference."""
    import torch
    output=torch.zeros((1,channels,pipe.h,pipe.w),device=pipe.device,dtype=torch.float32)
    if values is None:return output
    oy,ox=pipe.people_origin;y,x,h,w=record.window
    y0,x0=max(y,oy),max(x,ox);y1,x1=min(y+h,oy+pipe.h),min(x+w,ox+pipe.w)
    if y1<=y0 or x1<=x0:return output
    crop=np.ascontiguousarray(values[y0-y:y1-y,x0-x:x1-x])
    if crop.shape!=(y1-y0,x1-x0,channels):raise ValueError('People effect ROI channel mismatch')
    output[:,:,y0-oy:y1-oy,x0-ox:x1-ox]=torch.as_tensor(crop,device=pipe.device).permute(2,0,1)[None]
    return output


def _attenuated(pipe,record,delta):
    prepared=pipe.people_prepared;ref=record.face_ref;stage=record.stage
    recovery=prepared.recovery.get((ref['face_instance_id'],stage))
    if recovery is None:return delta
    fullshape=prepared.geometry.delta.shape[1:3]
    coverage=verify_recovery(ref,stage,recovery,fullshape)
    y,x,h,w=record.window
    return delta*(1-coverage[y:y+h,x:x+w,None])


def _merge_delta(pipe,stage,*,align):
    import torch
    result=torch.zeros((1,3,pipe.h,pipe.w),device=pipe.device,dtype=torch.float32)
    occupied=torch.zeros((1,1,pipe.h,pipe.w),device=pipe.device,dtype=torch.bool)
    records=sorted((r for r in pipe.people_prepared.effects if r.stage==stage),key=lambda r:r.face_ref['face_instance_id'])
    for record in records:
        if record.delta is None:continue
        delta=_local(pipe,record,_attenuated(pipe,record,record.delta),3)
        if align:delta=warp(pipe,delta)
        take=delta.ne(0).any(dim=1,keepdim=True)&~occupied
        result=torch.where(take,delta,result);occupied|=take
    return result


def _merge_chroma(pipe, stage):
    import torch
    result=torch.zeros((1,2,pipe.h,pipe.w),device=pipe.device,dtype=torch.float32)
    occupied=torch.zeros((1,1,pipe.h,pipe.w),device=pipe.device,dtype=torch.bool)
    records=sorted((r for r in pipe.people_prepared.effects if r.stage==stage),
                   key=lambda r:r.face_ref['face_instance_id'])
    for record in records:
        if pipe.people_prepared.recovery.get((record.face_ref['face_instance_id'],record.stage)) is not None:
            raise ValueError('Skin evenness has no reviewed dedicated recovery consumer')
        if record.chroma_shift is None:raise ValueError('Missing source-owned chroma field')
        field=_local(pipe,record,record.chroma_shift,2)
        take=field.ne(0).any(dim=1,keepdim=True)&~occupied
        result=torch.where(take,field,result);occupied|=take
    return result


def source_effect(pipe,stage,pixels):
    import torch
    if stage not in ('body_skin_evenness','skin_evenness','skin_colour','facial_wrinkles','lip_texture','lip_makeup','hair_colour','eye_light','blush_makeup','lipstick','eyeliner','eyelash','brow_enhance','brow_makeup','iris_makeup'):raise ValueError('This effect belongs after common geometry')
    if stage in ('body_skin_evenness', 'skin_evenness', 'brow_enhance', 'lip_texture') and not any(r.stage == stage for r in pipe.people_prepared.effects):
        return pixels  # Exact neutral: no new full-frame scratch or native work.
    if stage in ('skin_evenness', 'body_skin_evenness'):
        from .skin_evenness_composition import apply_t
        return apply_t(pixels, _merge_chroma(pipe, stage))
    delta=_merge_delta(pipe,stage,align=False)
    if stage == 'lip_texture':
        from .lip_texture_composition import apply_t
        return apply_t(pixels, delta)
    if stage == 'brow_enhance':
        from .brow_enhance_composition import apply_t
        return apply_t(pixels, delta)
    if stage=='skin_colour':
        from .people_skin_composition import apply as compose_skin
        return compose_skin(pixels,delta)
    return torch.where(delta!=0,pixels+delta if stage=='eye_light' else (pixels+delta).clamp(0,1),pixels)


def post_effects(pipe,pixels):
    import torch
    out=pixels;occupied=torch.zeros((1,1,pipe.h,pipe.w),device=pipe.device,dtype=torch.bool)
    records=sorted((r for r in pipe.people_prepared.effects if r.stage=='enhance'),key=lambda r:r.face_ref['face_instance_id'])
    for record in records:
        weights=_local(pipe,record,record.weights.transpose(1,2,0),3)
        weights=warp(pipe,weights)
        support=torch.zeros_like(occupied)
        for i,amount in enumerate(H.support_amounts(record.amounts)):
            if amount>0:support|=weights[:,i:i+1]>0
        take=support&~occupied
        corrected=H.enhance_t(pixels,weights[0],record.amounts,cancelled=getattr(pipe,"teeth_colour_cancelled",lambda:False))
        out=torch.where(take,corrected,out);occupied|=take
    delta=_merge_delta(pipe,'eye_detail',align=True)
    return torch.where(delta!=0,(out+delta).clamp(0,1),out)


def resident_bytes(pipe):
    return sum(value.numel()*value.element_size() for value in (getattr(pipe,'people_warp',None) or ()) if value is not None)
