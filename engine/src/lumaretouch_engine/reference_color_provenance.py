"""Conservative original-scene evidence admission and actual geometry transport."""
import numpy as np


def admit(state):
    if '_params' not in state or '_light' not in state: raise ValueError('参考统一缺少完整目标状态')
    if state.get('_inpaint_ops'): raise ValueError('此生成层缺少已支持的来源足迹；未将其当作原场景')


def source_support(pipe,window,full_shape,spec):
    """Use the SAME composite image deformation, then manual geometry; no face-template grid."""
    import torch
    cy0,cx0,cy1,cx1=window;h,w=full_shape
    mask=np.ones((cy1-cy0,cx1-cx0,3),np.float32)
    # Original frame edge is not geometric extrapolation evidence. Tile edges are
    # not zeroed: halos are actual source pixels and cropped after this mapping.
    if cy0==0:mask[:2]=0
    if cx0==0:mask[:,:2]=0
    if cy1==h:mask[-2:]=0
    if cx1==w:mask[:,-2:]=0
    for y0,y1,x0,x1 in repair_bounds(spec,full_shape):
        ay0,ay1=max(y0,cy0)-cy0,min(y1,cy1)-cy0
        ax0,ax1=max(x0,cx0)-cx0,min(x1,cx1)-cx0
        if ay1>ay0 and ax1>ax0:mask[ay0:ay1,ax0:ax1]=0
    t=torch.as_tensor(mask,device=pipe.device).permute(2,0,1)[None]
    studio=pipe.studio_background
    if studio.required and (studio.suspended or not studio.fields): raise ValueError('棚拍来源足迹缺失')
    for name,field in studio.fields.items():
        changed=field.abs().amax(dim=1,keepdim=True)>0
        if name in studio.recovery: changed &= studio.recovery[name]<1
        t=t*(~changed)

    t=pipe.align_source_grade_mask(t)
    sky=pipe.sky_replacement
    if sky.value['enabled']:
        if sky.suspended or set(sky.fields)!={'sky','person','water','recovery'}: raise ValueError('天空来源足迹缺失')
        f={k:pipe.align_source_grade_mask(v).clamp(0,1) for k,v in sky.fields.items()}
        p=sky.value['parameters'];protected=(1-f['person'])*(1-f['recovery'])
        replaced=f['sky']*protected*(p['opacity']/100)
        if p['reflection']>0: replaced=replaced+f['water']*protected*(p['reflection']/100)*(p['opacity']/100)
        t=t*(replaced<=0)
    if pipe.has_background():
        # Same background consumer geometry policy as apply_background.
        from . import mouth_shape_runtime as MOUTH
        matte=pipe.align_source_grade_mask(pipe.bg_matte) if MOUTH.has_source_geometry(pipe) else pipe.bg_matte
        removed=1-matte
        recovery=pipe.effect_recovery
        if 'background_replace' in recovery.required:
            if recovery.suspended or 'background_replace' in recovery.suspended_targets:raise ValueError('换背景恢复来源未知')
            weight=recovery.fields.get('background_replace')
            if weight is None:raise ValueError('换背景恢复足迹缺失')
            removed=removed*(1-pipe.align_source_grade_mask(weight.to(torch.float32)/255).clamp(0,1))
        t=t*(removed<=0)
    identity=pipe.id_background
    if identity.required:
        if identity.suspended or identity.fields is None:
            raise ValueError('证件照换背景来源足迹缺失')
        # The exact ID compositor alpha, transported through its actual geometry.
        # Restoring ID contribution does not restore upstream replaced pixels:
        # t still carries all previous exclusions.
        if getattr(identity,'spill_source',None) is not None:
            if identity.fields.shape[1]!=8:raise ValueError('祛染色来源足迹缺失')
            # Use one transport of the exact packed consumer fields. A manually
            # permitted, evidence-backed foreground correction is not original
            # scene colour, even where the replacement alpha is fully opaque.
            packed=pipe.align_source_grade_mask(identity.fields)
            alpha=packed[:,:1].clamp(0,1)
            spill_changed=(packed[:,4:7].abs().amax(dim=1,keepdim=True)>0) & (packed[:,7:8]>0) & (alpha>0)
            removed=(1-alpha)+spill_changed.to(alpha.dtype)
        else:
            removed=1-pipe.align_source_grade_mask(identity.fields[:,:1]).clamp(0,1)
        recovery=pipe.effect_recovery
        if 'id_background' in recovery.required:
            if recovery.suspended or 'id_background' in recovery.suspended_targets:
                raise ValueError('证件照恢复来源未知')
            weight=recovery.fields.get('id_background')
            if weight is None:raise ValueError('证件照恢复足迹缺失')
            removed=removed*(1-pipe.align_source_grade_mask(weight.to(torch.float32)/255).clamp(0,1))
        t=t*(removed<=0)
    t=pipe.manual_liquify.apply(t)
    return np.ascontiguousarray(t[0].permute(1,2,0).detach().cpu().numpy())


def optical_support(pixels,spec):
    from . import optics_state as S
    from .optics_stage import OpticsStage
    from .optics_native import sample
    if not S.active(spec.optics):return pixels
    stage=OpticsStage(spec.optics,pixels.shape[:2]);out=np.empty_like(pixels)
    for y in range(0,len(pixels),64):
        rows=min(64,len(pixels)-y)
        # Sample channel-specific real geometric coordinates, but no vignetting gains.
        coords=stage.coordinates(y0=y,rows=rows)
        for channel in range(3):
            out[y:y+rows,:,channel]=sample(pixels,coords[...,channel,:])[...,channel]
    return out


def repair_bounds(spec,shape):
    """Conservative operator-written ROI, including patch feather outside brush.

    Derive from the real replay planners; do not mistake recorded brush coverage
    for the source-patch operator's Gaussian-feathered write footprint.
    """
    cached=getattr(spec,'_reference_repair_bounds',None)
    if cached is not None:return cached
    boxes=[]
    for op in spec.repair or []:
        if op.weight.shape!=tuple(shape):raise ValueError('修补来源足迹不属于完整原图')
        if op.kind=='clone_stamp':
            from .ops.clone_stamp import raster_plan
            _,_,box,_=raster_plan(shape,op.params)
        elif op.kind=='source_patch':
            from .ops.source_patch import _plan
            box,*_=_plan(shape,op.params)
        elif op.kind=='heal':
            from .ops.inpaint import mask_bbox
            from .repair_record import DEFAULT_REPAIR
            box=mask_bbox(op.weight.astype(np.float32)/255,pad=int(op.params.get('pad',DEFAULT_REPAIR['pad'])),grow=float(op.params.get('grow',DEFAULT_REPAIR['grow'])))
        else:raise ValueError('此修补操作缺少原场景支持生产者')
        if box is not None:boxes.append(box)
    spec._reference_repair_bounds=boxes
    return boxes
