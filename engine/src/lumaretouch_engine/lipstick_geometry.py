"""A measured lip ring, NEVER the existing teeth mask or a face-box fill.

Six-class semantics are known-occluder vetoes, not lip labels. No colour/skin-tone veto.
Unknown skin-coloured occluders remain a documented limitation; recovery can
remove their contribution. No invented confidence or template landmarks.
"""
import numpy as np
from .face_scope import _polygon_field
from .lip_makeup_geometry import OUTER, INNER, _crossed


def geometry(lm, shape, excluded, reviewed, *, backend):
    h, w = shape
    empty = np.zeros(shape, np.float32)
    fact = {'geom_px': 0, 'gated_px': 0, 'reason': None,
            'visibility_method': 'landmark_ring_known_occluder_and_source_owned_review',
            'limitation': 'not_a_lip_segmentation_or_complete_occlusion_detector'}
    def fail(reason):
        raise ValueError('口红几何拒绝：'+reason)
    if backend != 'mediapipe': return fail('actual_selected_face_required')
    lm = np.asarray(lm, np.float32)
    if lm.shape != (478, 2) or not np.isfinite(lm).all():
        raise ValueError('口红需要真实选中人物 478 点')
    width = float(np.linalg.norm(lm[61] - lm[291]))
    if width < 24: return fail('insufficient_resolution')
    eyes = [float(np.linalg.norm(lm[a] - lm[b])) for a,b in ((33,133),(263,362))]
    halves = [float(np.linalg.norm(lm[i] - lm[0])) for i in (61,291)]
    if min(eyes) < 8 or min(eyes) < .5 * max(eyes) or min(halves) < .42 * max(halves):
        return fail('sideface_or_foreshortened')
    outer, inner = lm[list(OUTER)], lm[list(INNER)]
    across=(lm[291]-lm[61])/width
    # A genuinely closed mouth still spans almost the full mouth width. A
    # collapsed point/short inner chain must not expose the oral cavity.
    if float(np.ptp(inner@across)) < .55*width:
        return fail('clipped_or_degenerate_lips')
    if _crossed(outer) or _crossed(inner): return fail('clipped_or_degenerate_lips')
    try: contained,_ = _polygon_field(inner[:,0],inner[:,1],outer)
    except ValueError: return fail('clipped_or_degenerate_lips')
    if not np.all(contained): return fail('clipped_or_degenerate_lips')
    if np.any(outer < 1) or np.any(outer[:,0] > w-2) or np.any(outer[:,1] > h-2):
        return fail('clipped_or_degenerate_lips')
    # Reject crossed/outward inner contours. Closed mouths may have near-zero
    # inner area; still protect the complete inner line by segment distance.
    ys, xs = np.mgrid[:h,:w].astype(np.float32); xs += .5; ys += .5
    try:
        inside, distance = _polygon_field(xs, ys, outer)
        inner_inside, inner_distance = _polygon_field(xs, ys, inner)
    except ValueError:
        # A collapsed cavity is normal for a closed mouth. Use its real polyline
        # distance, not an invented aperture or outer-polygon teeth substitute.
        try: inside, distance = _polygon_field(xs, ys, outer)
        except ValueError: return fail('clipped_or_degenerate_lips')
        inner_inside = np.zeros(shape, bool)
        inner_distance = np.full(shape, np.inf)
        for a,b in zip(inner, np.roll(inner,-1,axis=0)):
            d = b-a; den = float(d@d)
            if den < 1e-8: continue
            t = np.clip(((xs-a[0])*d[0]+(ys-a[1])*d[1])/den,0,1)
            inner_distance = np.minimum(inner_distance,np.hypot(xs-a[0]-t*d[0],ys-a[1]-t*d[1]))
    if np.count_nonzero(inner_inside & ~inside) > max(2, .01*np.count_nonzero(inner_inside)):
        return fail('clipped_or_degenerate_lips')
    clearance = max(.8, width * .012)
    hard = inside & ~inner_inside & (distance > .71) & (inner_distance > clearance)
    fact['geom_px'] = int(hard.sum())
    if hard.sum() < 30: return fail('insufficient_lip_ring')
    if excluded is None: return fail('visibility_support_unavailable')
    veto = np.asarray(excluded,np.float32)
    if veto.shape != shape or not np.isfinite(veto).all() or np.any((veto<0)|(veto>1)):
        raise ValueError('口红可见性排除场无效')
    review = np.asarray(reviewed,np.float32)
    if review.shape != shape or not np.isfinite(review).all() or np.any((review<0)|(review>1)):
        raise ValueError('口红需要当前人物的已审核可见唇部范围')
    safe = hard & (veto < .2) & (review > 0)
    if safe.sum() < 30: return fail('occluded_or_insufficient_support')
    inward = np.minimum(np.clip((distance-.71)/clearance,0,1),
                         np.clip((inner_distance-clearance)/clearance,0,1))
    # Feather only inward. Neither interpolation nor blur can leak to teeth,
    # tongue, oral cavity, skin outside outer ring, or known semantic occluders.
    mask = np.ascontiguousarray(safe * inward * (1-veto) * review,dtype=np.float32)
    fact['gated_px'] = int(np.count_nonzero(mask > .01))
    if fact['gated_px'] < 20: return fail('insufficient_lip_ring')
    # Normalized coordinates follow measured mouth axes, including roll.
    center=(lm[61]+lm[291])*.5
    down=np.array([-across[1],across[0]],np.float32)
    if np.dot(lm[17]-lm[0],down)<0:down=-down
    height=max(2.,float(np.ptp(outer@down)))
    u=((xs-center[0])*across[0]+(ys-center[1])*across[1])/(width*.5)
    v=((xs-center[0])*down[0]+(ys-center[1])*down[1])/(height*.5)
    depth=inner_distance/np.maximum(inner_distance+distance,1e-6)
    uv=np.ascontiguousarray(np.stack((u,v,np.clip(depth,0,1)),axis=-1),dtype=np.float32)
    return mask, fact, uv
