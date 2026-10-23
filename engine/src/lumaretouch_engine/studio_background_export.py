"""Full-source semantic input and export validation, not proxy-mask enlargement."""
import numpy as np
from . import studio_background_state as S,studio_background_runtime as R,local_mask_state as M


def check_spec(spec):
    value=S.check(spec.studio_background);spec.studio_background=value
    if not S.active(value):return
    if not spec.studio_background_path or type(spec.studio_background_stamp) is not list or len(spec.studio_background_stamp)!=5:
        raise ValueError('背景导出缺少已验证的原照片与解码时间戳')
    if spec.bg_matte is not None:raise ValueError('完整换底会覆盖影棚背景调整，请先选择保留的效果')
    if spec.studio_background_prepared is not None:
        from .studio_background_stage import check_prepared
        binding=value['source'];check_prepared(spec.studio_background_prepared,(binding['height'],binding['width']))


def full_semantic(source,value):
    """Model receives an 8-bit observation only. Rendering keeps original RGB16/float.

    Feed the complete decoded photo to the official existing six-class segmenter;
    regenerate confidence at this output size. No old proxy mask is enlarged.
    """
    if value['region_mode']!='semantic_background':return None,None
    import mediapipe as mp
    from .face import MediaPipeFace,_resize_float
    from .semantic_sources import probability_sources,edit_sources
    from .ops.studio_background import rgb_float
    observation=np.round(np.clip(rgb_float(source),0,1)*255).astype(np.uint8)
    with MediaPipeFace() as backend:
        _,segmenter=backend._ensure()
        owner=M.semantic_owner(backend,backend.name)
        if owner!=value['semantic_owner']:raise ValueError('全尺寸背景模型摘要与保存配方不一致')
        result=segmenter.segment(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.ascontiguousarray(observation)))
        confidence=[]
        for channel in list(getattr(result,'confidence_masks',None) or []):
            v=channel.numpy_view;confidence.append(v() if callable(v) else v)
        probabilities=probability_sources(confidence);h,w=source.shape[:2]
        field=probabilities['background']
        field=_resize_float(field,h,w) if field.shape!=(h,w) else field
        return edit_sources({'background':field})['background'],owner


def prepare_export(spec,source,*,cancelled=lambda:False):
    check_spec(spec);value=spec.studio_background
    if not S.active(value):spec.studio_background_prepared=None;return
    if cancelled():raise InterruptedError('背景导出已取消')
    if getattr(spec,'creative_base',None) is not None:
        from .creative_derived_studio import verify_export
        verify_export(spec,source)  # Before model observation conversion or inference.
    field,owner=full_semantic(source,value)
    R.export_prepare(spec,source,semantic_background=field,semantic_owner=owner,cancelled=cancelled)


def resident_bytes(spec):
    prepared=spec.studio_background_prepared
    if prepared is None:return 0
    return sum(v.nbytes for group in ('fields','recovery','masks') for v in prepared[group].values())
