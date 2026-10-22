"""Align source-bound post-geometry eye consumers with the same joint grid."""
def apply_enhance(pipe,t):
    import torch
    from .ops import enhance as ENH
    out=t
    if pipe.enhance_local is not None and pipe.enhance_gpu is not None and any(pipe.enhance_amounts.get(k,0)>0 for k in ENH.SUBS):
        y,x,h,w=pipe.enhance_local
        weight=torch.zeros((1,3,pipe.h,pipe.w),device=pipe.device,dtype=torch.float32)
        weight[:,:,y:y+h,x:x+w]=pipe.enhance_gpu[None]
        weight=pipe.align_source_grade_mask(weight)[0]
        out=ENH.enhance_t(out,weight,pipe.enhance_amounts)
    if pipe.under_eye_delta is not None:
        y,x,h,w=pipe.under_eye_local
        delta=torch.zeros_like(t)
        delta[:,:,y:y+h,x:x+w]=pipe.under_eye_delta
        delta=pipe.align_source_grade_mask(delta)
        out=torch.where(delta!=0,(out+delta).clamp(0,1),out)
    return out
