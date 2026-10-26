"""One full-source preparation shared by proxy and tiled float export."""
import numpy as np
from . import portrait_protection_state as S
from .ops.portrait_protection import prepare


def budget():
    from .creative_document_host import memory_budget
    return memory_budget()


def install(pipe, field, *, bounds=None, preview=False):
    pipe.portrait_delta=None; pipe.portrait_support=None; pipe.portrait_overlay=None
    if field is None:return
    import torch
    def tensor(value, channels=False):
        if value is None:return None
        if bounds is not None:
            y0,x0,y1,x1=bounds;value=value[y0:y1,x0:x1]
        value=np.array(value,dtype=np.float32,order='C',copy=True)
        return torch.from_numpy(value.transpose(2,0,1)[None] if channels else value[None,None]).to(pipe.device)
    pipe.portrait_delta=tensor(field['delta'],True)
    pipe.portrait_support=tensor(field['smoothing_support'])
    if preview:pipe.portrait_overlay=tensor(field['overlay'])


def sync(engine):
    if engine._vram is None:return
    engine._vram.grading_prefix_cache.invalidate()
    engine._portrait_protection_suspended=None
    recipe=S.check(getattr(engine,S.KEY,None))
    if not S.needs_analysis(recipe):install(engine._vram,None);return
    from .creative_derived_source import binding
    from .local_mask_state import file_stamp
    row=engine._docs[engine._doc_index]
    if row.get('_local_source_stamp')!=file_stamp(engine._doc_path):raise ValueError('Portrait source changed since decode; reload required')
    if binding(engine)!=recipe['source']:raise ValueError('Portrait recipe belongs to another source')
    try: owner_check(engine,recipe)
    except ValueError as error:
        install(engine._vram,None)
        engine._portrait_protection_suspended=str(error)
        return
    admitted=budget()
    if engine._vram.w*engine._vram.h*160+16*1024**2>admitted:raise ValueError('Portrait proxy preparation exceeds working budget')
    source=engine._vram.base().detach().cpu().numpy()[0].transpose(1,2,0)
    field=prepare(np.ascontiguousarray(source),recipe,byte_budget=admitted)
    install(engine._vram,field,preview=True)


def configure_export(spec,snapshot,*,for_document):
    recipe=S.check(snapshot.get('portrait_protection'))
    if S.needs_analysis(recipe):
        if not for_document:raise ValueError('P0 portrait evidence cannot transfer to another photo')
        path=snapshot.get('portrait_protection_path')
        if not path:raise ValueError('Portrait export requires exact source path proof')
        from .creative_derived_source import binding
        if binding(snapshot,path,(recipe['source']['width'],recipe['source']['height']))!=recipe['source']:
            raise ValueError('Portrait export source binding changed')
        from .local_mask_state import file_stamp
        if list(file_stamp(path))!=snapshot.get('portrait_protection_stamp'):raise ValueError('Portrait source changed after snapshot')
    spec.portrait_protection=recipe
    spec.portrait_protection_path=snapshot.get('portrait_protection_path')
    spec.portrait_protection_stamp=snapshot.get('portrait_protection_stamp')


def prepare_export(spec,source,base_f,divisor,*,cancelled):
    recipe=S.check(spec.portrait_protection)
    if not S.needs_analysis(recipe):return None
    from .local_mask_state import file_stamp
    path=spec.portrait_protection_path
    if not path or list(file_stamp(path))!=spec.portrait_protection_stamp:raise ValueError('Portrait source changed during export')
    if source.shape[:2]!=(recipe['source']['height'],recipe['source']['width']):raise ValueError('Portrait full-source dimensions changed')
    admitted=budget()
    if source.shape[0]*source.shape[1]*160+16*1024**2>admitted:raise ValueError('Portrait export preparation exceeds working budget')
    # Raw integer samples are converted once; native16 never goes through uint8.
    pixels=base_f if base_f is not None else np.ascontiguousarray(source,dtype=np.float32)/divisor
    field=prepare(pixels,recipe,byte_budget=admitted,cancelled=cancelled)
    if list(file_stamp(path))!=spec.portrait_protection_stamp:raise ValueError('Portrait source changed while preparing')
    # Diagnostic overlay is forbidden in exports, including accurate inspection.
    if field is not None:field['overlay']=None
    return field


def owner_check(engine,recipe=None):
    from .creative_derived_source import binding
    graph=engine._people_owner().snapshot()
    return S.check_owner(recipe,getattr(engine,'_face_manual',None),graph,
                         source_sha256=binding(engine)['sha256'] if recipe is None else None)


def present_frame(engine, rgba, *, original=False):
    """Diagnostic COPY at shm delivery only. Canonical RGB/frame buffers stay clean.

    Align exactly with source deformation, manual geometry, optical GREEN control
    geometry, crop/rotation and final reflection. No colour operator sees tint.
    """
    pipe=engine._vram
    field=getattr(pipe,'portrait_overlay',None)
    if original or field is None:return rgba
    import torch
    from . import optics_state as O
    from .optics_native import sample
    if pipe.w*pipe.h*160+16*1024**2>budget():raise ValueError('Portrait display overlay exceeds memory budget')
    weight=pipe.align_source_grade_mask(field.expand(-1,3,-1,-1))
    manual_ms=pipe.manual_liquify.last_ms
    try:weight=pipe.manual_liquify.apply(weight)
    finally:pipe.manual_liquify.last_ms=manual_ms
    if O.active(pipe.optics.value):
        if pipe.optics.suspended:raise ValueError('Cannot project portrait overlay through suspended optics')
        source=np.ascontiguousarray(weight[0].permute(1,2,0).detach().cpu().numpy(),dtype=np.float64)
        mapped=np.empty_like(source,dtype=np.float32)
        rows=max(1,min(64,1048576//pipe.w))
        for y in range(0,pipe.h,rows):
            coords=pipe.optics.coordinates(y0=y,rows=min(rows,pipe.h-y))[...,1,:]
            mapped[y:y+rows]=sample(source,coords).astype(np.float32)
        weight=torch.from_numpy(mapped).permute(2,0,1)[None].to(pipe.device)
    geometry_ms=pipe.last_geometry_ms
    try:weight=pipe.apply_geometry(weight)
    finally:pipe.last_geometry_ms=geometry_ms
    # Reflection of presentation coverage has exactly the final image axes;
    # no re-inference, interpolation or colour transform is involved.
    if pipe.final_canvas_flip['horizontal']:weight=torch.flip(weight,[-1])
    if pipe.final_canvas_flip['vertical']:weight=torch.flip(weight,[-2])
    alpha=np.clip(weight[0,0].detach().cpu().numpy(),0,1)[...,None]*.3
    if rgba.shape[:2]!=alpha.shape[:2]:raise ValueError('Portrait display coverage/frame extent mismatch')
    output=rgba.copy()
    output[...,:3]=np.rint(rgba[...,:3].astype(np.float32)*(1-alpha)+np.array([255.,25.5,38.25],np.float32)*alpha).astype(np.uint8)
    return output
