"""Full-image fabric measurement and same-field tiled render support."""
from .fabric_stage import check_amount, clothing_mask, face_scale, measure_field

def configure_export(spec, snap, h, w):
    import numpy as np
    spec.fabric_amount = check_amount(snap.get('fabric_amount', 0.0))
    if not spec.fabric_amount:
        return
    pc = snap.get('precompute')
    mask = clothing_mask(pc)
    if mask is None:
        raise ValueError('衣物细褶导出缺少这张图片的衣物语义蒙版；禁止静默省略或扩大范围')
    mask = np.asarray(mask, dtype=np.float32)
    if mask.shape != (h, w):
        import cv2
        # Semantic confidence resampling, not enlargement of a measured gain.
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
    spec.fabric_mask = mask
    spec.fabric_face_px = face_scale(pc, h, w)

def prepare_export(spec, src, base, divisor):
    import numpy as np
    if not check_amount(spec.fabric_amount):
        return None
    rgb = base if base is not None else src.astype(np.float32) / divisor
    return measure_field(rgb, spec.fabric_mask, spec.fabric_face_px)
