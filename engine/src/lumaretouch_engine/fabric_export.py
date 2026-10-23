"""Full-image fabric measurement and same-field tiled render support."""
from .fabric_stage import check_amount, clothing_mask, face_scale, measure_field

def configure_export(spec, snap, h, w):
    import numpy as np
    spec.fabric_amount = check_amount(snap.get('fabric_amount', 0.0))
    if not spec.fabric_amount:
        return
    from .creative_derived_source import record
    derived = record(snap) is not None
    pc = snap.get('precompute')
    if derived:
        from .creative_derived_fabric import verify_snapshot, face_scale as owned_scale
        context = verify_snapshot(snap)
        spec.creative_fabric_context = context
        mask = context['mask']
    else:
        mask = clothing_mask(pc)
    if mask is None:
        raise ValueError('衣物细褶导出缺少这张图片的衣物语义蒙版；禁止静默省略或扩大范围')
    mask = np.asarray(mask, dtype=np.float32)
    if mask.shape != (h, w):
        import cv2
        # Semantic confidence resampling, not enlargement of a measured gain.
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
    spec.fabric_mask = mask
    spec.fabric_face_px = owned_scale(context, h, w) if derived else face_scale(pc, h, w)
    if derived:
        from .creative_derived_fabric import _hash
        spec._creative_fabric_resampled = (_hash(mask), spec.fabric_face_px)

def prepare_export(spec, src, base, divisor):
    import numpy as np
    if not check_amount(spec.fabric_amount):
        return None
    if getattr(spec, 'creative_base', None) is not None:
        from .creative_derived_fabric import export_pixels, _hash
        rgb = export_pixels(spec, src, base, divisor)
        if getattr(spec, '_creative_fabric_resampled', None) != (_hash(spec.fabric_mask), spec.fabric_face_px):
            raise ValueError('Fabric resampled semantic evidence changed before full-image measurement')
    else:
        rgb = base if base is not None else src.astype(np.float32) / divisor
    return measure_field(rgb, spec.fabric_mask, spec.fabric_face_px)
