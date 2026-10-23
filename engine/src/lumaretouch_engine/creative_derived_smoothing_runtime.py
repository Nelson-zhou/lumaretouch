"""Cheap consumer fences after owned smoothing input validation.

Binding is internal, after the live/export source owner verifies actual pixels.
No arrays or filter outputs are persisted. Existing guided-band math is unchanged.
"""
from copy import deepcopy
import numpy as np


def _signature(tensor):
    if tensor is None:return None
    return (id(tensor),tensor.data_ptr(),int(tensor._version),tuple(tensor.shape),
            str(tensor.dtype),str(tensor.device))


def _array(tensor):
    return tensor[0].permute(1,2,0).detach().cpu().numpy()


def reset(pipe):
    pipe._creative_smoothing_binding=None
    pipe._creative_smoothing_cache=None


def bind(pipe,source,pixels,*,mask_channel=None,mask_pixels=None,domain='preview',evidence_key=None):
    """INTERNAL: bind actual verified base and selected mask, never a filename."""
    from .creative_derived_repairs import check_binding
    source=check_binding(source)
    if source is None or domain not in ('preview','export-tile'):
        raise ValueError('Smoothing requires an immutable source and explicit pixel domain')
    value=np.asarray(pixels)
    actual=_array(pipe.base())
    if (value.dtype!=np.float32 or value.shape!=(pipe.h,pipe.w,3)
            or not np.isfinite(value).all() or np.any(value<0) or np.any(value>1)
            or actual.dtype!=np.float32 or not np.array_equal(actual,value)):
        raise ValueError('Smoothing pipeline does not contain its verified float pixels')
    if domain=='preview' and getattr(pipe,'_creative_repair_source',None)!=source:
        raise ValueError('Smoothing preview has another immutable repair source')
    if mask_channel is None:
        if mask_pixels is not None:raise ValueError('Unmasked smoothing cannot retain a hidden mask')
        mask_signature=None
    else:
        if type(mask_channel) is not str or not mask_channel:
            raise ValueError('Invalid smoothing channel')
        mask=np.asarray(mask_pixels)
        actual_mask=pipe.mask(mask_channel).detach().cpu().numpy()
        if (mask.dtype!=np.float32 or mask.shape!=(pipe.h,pipe.w)
                or not np.isfinite(mask).all() or np.any(mask<0) or np.any(mask>1)
                or actual_mask.dtype!=np.float32 or not np.array_equal(actual_mask[0,0],mask)):
            raise ValueError('Smoothing channel pixels differ from verified coverage')
        mask_signature=(_signature(pipe.masks_gpu),tuple(pipe.mask_names))
    record={'source':deepcopy(source),'domain':domain,'channel':mask_channel,
            'source_tensor':_signature(pipe.src_f32),'base_tensor':_signature(pipe.base()),
            'mask_tensor':mask_signature,'evidence_key':deepcopy(evidence_key)}
    old=getattr(pipe,'_creative_smoothing_binding',None)
    if old!=record:
        prefix=getattr(pipe,'grading_prefix_cache',None)
        if prefix is not None:prefix.invalidate()
        # A channel/evidence change need not rerun source-only bands. Input
        # identity changes do; keys are also source-owned as a second fence.
        if old is None or any(old[k]!=record[k] for k in ('source','domain','source_tensor','base_tensor')):
            pipe.retouched=None;pipe.filter_key=None;pipe.bands=None;pipe.bands_key=None
            pipe._creative_smoothing_cache=None
    pipe._creative_smoothing_binding=record
    return record


def check(pipe,channel=None,*,require=False,check_channel=True):
    record=getattr(pipe,'_creative_smoothing_binding',None)
    if record is None:
        if require and getattr(pipe,'_creative_repair_source',None) is not None:
            raise ValueError('Derived smoothing has not bound its actual source and coverage')
        return None
    if record['source_tensor']!=_signature(pipe.src_f32) or record['base_tensor']!=_signature(pipe.base()):
        raise ValueError('Smoothing source pixels changed after owned installation')
    if record['domain']=='preview' and getattr(pipe,'_creative_repair_source',None)!=record['source']:
        raise ValueError('Smoothing source identity changed after installation')
    if check_channel:
        if channel!=record['channel']:raise ValueError('Smoothing channel changed without owned installation')
        if channel is not None and record['mask_tensor']!=(_signature(pipe.masks_gpu),tuple(pipe.mask_names)):
            raise ValueError('Smoothing coverage changed after owned installation')
    source=record['source']
    return (source['sha256'],source['width'],source['height'],record['domain'],record['base_tensor'])


def cache_check(pipe):
    record=getattr(pipe,'_creative_smoothing_binding',None)
    if record is None:return
    cached=getattr(pipe,'_creative_smoothing_cache',None)
    if cached is None:return
    # Existing repair invalidation can clear one or both caches legitimately.
    if pipe.bands is not None and cached['bands_key']==pipe.bands_key:
        if cached['bands']!=tuple(_signature(t) for t in pipe.bands):
            raise ValueError('Owned smoothing bands changed after calculation')
    if pipe.retouched is not None and cached['filter_key']==pipe.filter_key:
        if cached['result']!=_signature(pipe.retouched):
            raise ValueError('Owned smoothing result changed after calculation')


def cache_record(pipe):
    if getattr(pipe,'_creative_smoothing_binding',None) is None:return
    pipe._creative_smoothing_cache={'bands_key':pipe.bands_key,'filter_key':pipe.filter_key,
        'bands':tuple(_signature(t) for t in pipe.bands),'result':_signature(pipe.retouched)}
