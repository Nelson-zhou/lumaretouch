"""A measured lip ring, NEVER the existing teeth mask or a face-box fill.

Six-class portrait semantics are only known-occluder vetoes, not lip labels.
Unknown skin-coloured occluders remain a documented limitation; recovery can
remove their contribution. No invented confidence or template landmarks.
"""
import numpy as np
from .face_scope import _polygon_field
from .ops.enhance import LIP_CHAIN_UPPER, LIP_CHAIN_LOWER
OUTER = LIP_CHAIN_UPPER + tuple(reversed(LIP_CHAIN_LOWER[1:-1]))
# MediaPipe FACEMESH_LIPS inner closed contour, separate from outer vermilion.
INNER = (78,191,80,81,82,13,312,311,310,415,308,324,318,402,317,14,87,178,88,95)


def _crossed(points):
    """Reject proper intersections of non-neighbouring contour segments."""
    def cross(a,b,c):
        u,v=b-a,c-a
        return float(u[0]*v[1]-u[1]*v[0])
    n=len(points)
    for i in range(n):
        a,b=points[i],points[(i+1)%n]
        for j in range(i+2,n):
            if i==0 and j==n-1: continue
            c,d=points[j],points[(j+1)%n]
            if cross(a,b,c)*cross(a,b,d)<-1e-6 and cross(c,d,a)*cross(c,d,b)<-1e-6:
                return True
    return False


def geometry(lm, shape, source, excluded, *, backend):
    h, w = shape
    empty = np.zeros(shape, np.float32)
    fact = {'geom_px': 0, 'gated_px': 0, 'reason': None,
            'visibility_method': 'landmark_ring_known_occluder_and_colour_veto',
            'limitation': 'not_a_lip_segmentation_or_complete_occlusion_detector'}
    def fail(reason):
        return empty, {**fact, 'reason': reason}, 0.
    if backend != 'mediapipe': return fail('actual_selected_face_required')
    lm = np.asarray(lm, np.float32)
    if lm.shape != (478, 2) or not np.isfinite(lm).all():
        raise ValueError('唇妆需要真实选中人物 478 点')
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
        raise ValueError('唇妆可见性排除场无效')
    import cv2
    lab = cv2.cvtColor(np.ascontiguousarray(source),cv2.COLOR_RGB2Lab)
    candidates = hard & (veto < .2)
    if candidates.sum() < 30: return fail('occluded_or_insufficient_support')
    # Reject atypical colours and crushed/clipped samples, without assuming red
    # lipstick or skin tone. This is only a veto, never a generated lip mask.
    chroma = lab[...,1:]
    center = np.median(chroma[candidates],axis=0)
    deviation = np.linalg.norm(chroma-center,axis=2)
    spread = max(8., float(np.median(deviation[candidates]))*3.)
    visibility = (veto < .2) & (deviation < spread*2) & (lab[...,0] > 2) & (lab[...,0] < 98)
    safe = hard & visibility
    if safe.sum() < max(30, hard.sum()*.45): return fail('occluded_or_insufficient_support')
    inward = np.minimum(np.clip((distance-.71)/clearance,0,1),
                         np.clip((inner_distance-clearance)/clearance,0,1))
    # Feather only inward. Neither interpolation nor blur can leak to teeth,
    # tongue, oral cavity, skin outside outer ring, or known semantic occluders.
    mask = np.ascontiguousarray(safe * inward * (1-veto),dtype=np.float32)
    fact['gated_px'] = int(np.count_nonzero(mask > .01))
    if fact['gated_px'] < 20: return fail('insufficient_lip_ring')
    return mask, fact, width
