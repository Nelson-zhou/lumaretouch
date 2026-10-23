"""Independent source-owned sclera candidates for local purification.

Geometry plus pixel gates are conservative heuristics, not anatomical semantic
segmentation. Each eye is solved separately; the other eye is never its clean
reference. The full-source ROI is solved before export tiles are cut.
"""
import math
import numpy as np

KEYS = ('sclera_purify',)


def active(amounts):
    return amounts.get('sclera_purify', 0) > 0


def capability():
    from .sclera_purify_native import available
    ready = available()
    return {'sclera_purify_available': ready, 'sclera_purify_reason': None if ready else
            '眼白净化 Rust 核心未安装或 ABI 不匹配；不会以提亮或祛血丝替代'}


def ramp(value, lo, hi):
    t = np.clip((value-lo)/(hi-lo), 0, 1)
    return t*t*(3-2*t)


def regions(source, landmarks):
    from .ops import enhance as H
    height,width = source.shape[:2]
    if min(height,width)<1 or max(height,width)>65536 or height*width>64_000_000:
        raise ValueError('Sclera purification source exceeds canvas budget; no proxy fallback')
    lm = H._landmark_pixels(landmarks,height,width)
    result, facts = [], []
    specs = ((H.EYE_RING_LEFT,H.IRIS_LEFT,H.IRIS_RIM_LEFT),
             (H.EYE_RING_RIGHT,H.IRIS_RIGHT,H.IRIS_RIM_RIGHT))
    for index,(ring,iris,rim) in enumerate(specs):
        centre, vertices = lm[iris],lm[list(ring)]
        radii = np.linalg.norm(lm[list(rim)]-centre,axis=1)
        radius = float(radii.mean())
        eye_width = float(np.linalg.norm(vertices[0]-vertices[8]))
        reason = H._star_ok(vertices,*centre)
        if radius<3 or radii.min()<.60*radii.max() or eye_width<12:
            reason = 'tiny_or_foreshortened_eye'
        if np.linalg.norm(vertices-centre,axis=1).min()<.55*radius:
            reason = 'closed_or_occluded_central_aperture'
        filter_radius = max(1,math.ceil(.12*radius))
        if filter_radius>32:
            reason = 'full_source_filter_radius_exceeds_budget'
        if reason is not None:
            facts.append({'eye_index':index,'reason':reason,'geom_px':0,'gated_px':0})
            continue
        x0,y0 = np.maximum(np.floor(vertices.min(axis=0))-filter_radius-1,0).astype(int)
        x1,y1 = np.minimum(np.ceil(vertices.max(axis=0))+filter_radius+2,[width,height]).astype(int)
        if x1<=x0 or y1<=y0:
            facts.append({'eye_index':index,'reason':'eye_outside_canvas','geom_px':0,'gated_px':0})
            continue
        from .sclera_purify_native import _admit
        from .cpu_memory_budget import available_estimate
        roi_width,roi_height=int(x1-x0),int(y1-y0)
        _admit(roi_width,roi_height,filter_radius)
        # Raster helpers use several float64 grid/geometry temporaries. Admit
        # those BEFORE mgrid, not only the smaller native snapshots afterward.
        if 256*roi_width*roi_height > available_estimate():
            raise MemoryError('眼白净化几何栅格超出内存预算；不扩张或改用代理蒙版')
        yy,xx = np.mgrid[y0:y1,x0:x1];xs,ys=xx+.5,yy+.5
        inner = centre+.85*(vertices-centre)
        safety = centre+.90*(vertices-centre)
        aperture = H._star_weight(xs,ys,*centre,inner,max(.5,.1*radius))
        aperture *= H._star_weight(xs,ys,*centre,safety,0)
        distance = np.hypot(xs-centre[0],ys-centre[1])
        # Use the maximum measured rim radius, not its mean, to exclude limbus.
        aperture *= ramp(distance,1.20*float(radii.max()),1.40*float(radii.max()))
        for corner in (vertices[0],vertices[8]):
            aperture *= ramp(np.hypot(xs-corner[0],ys-corner[1]),.08*eye_width,.14*eye_width)
        geometry_count = int(np.count_nonzero(aperture>.15))
        if geometry_count<12:
            facts.append({'eye_index':index,'reason':'insufficient_exposed_sclera_geometry',
                          'geom_px':geometry_count,'gated_px':0})
            continue
        crop = source[y0:y1,x0:x1]
        value = crop.max(axis=2); minimum=crop.min(axis=2)
        saturation=(value-minimum)/np.maximum(value,1e-8)
        reference=float(np.median(value[aperture>.15]))
        # Keep genuinely dark lashes/frames, coloured iris leakage and near-white
        # specular highlights out of both edit support and neighbour statistics.
        floor=max(.04,.35*reference); ceiling=max(floor+.02,.65*reference)
        coverage=aperture*ramp(value,floor,ceiling)*(1-ramp(saturation,.35,.65))
        coverage*=1-ramp(value,.96,1.0)
        coverage=np.ascontiguousarray(coverage,dtype=np.float32)
        kept=int(np.count_nonzero(coverage>.15))
        fact={'eye_index':index,'geom_px':geometry_count,'gated_px':kept,
              'reason':None if kept>=8 else 'insufficient_sclera_pixel_evidence',
              'iris_radius_px':radius,'filter_radius_px':filter_radius,'pool_value_median':reference,
              'donor_candidate_px':int(np.count_nonzero(coverage>=.75))}
        facts.append(fact)
        if kept>=8:
            result.append(((int(y0),int(x0),int(y1-y0),int(x1-x0)),coverage,filter_radius,index))
    if not result:
        raise ValueError('眼白净化没有足够的源图眼白支持；不会扩张到虹膜、眼睑或复制另一只眼')
    return result,facts


def correct(source,landmarks,amount,*,cancelled=lambda:False):
    if not amount:
        return source,{'reason':'disabled','geom_px':0,'gated_px':0}
    from .sclera_purify_native import apply
    if cancelled():raise InterruptedError('Sclera purification cancelled before preparation')
    rgb=np.asarray(source)
    if rgb.ndim!=3 or rgb.shape[2]!=3 or not np.isfinite(rgb).all() or np.any((rgb<0)|(rgb>1)):
        raise ValueError('Sclera purification needs finite SDR RGB; no alpha/HDR clipping')
    eyes,facts=regions(rgb,landmarks)
    out=rgb.copy();changed=0
    occupied=np.zeros(rgb.shape[:2],dtype=bool)
    for (y,x,h,w),coverage,radius,index in eyes:
        if cancelled():raise InterruptedError('Sclera purification cancelled between eyes')
        if np.any(occupied[y:y+h,x:x+w] & (coverage>0)):
            raise ValueError('Overlapping sclera evidence refused rather than applying twice')
        original=rgb[y:y+h,x:x+w]
        frozen=np.ascontiguousarray(original,dtype=np.float32)
        corrected=apply(frozen,coverage,amount,radius,cancelled=cancelled)
        delta=corrected-frozen
        count=int(np.count_nonzero(np.any(delta!=0,axis=2)))
        out[y:y+h,x:x+w]=np.where(delta!=0,original+delta.astype(rgb.dtype,copy=False),out[y:y+h,x:x+w])
        occupied[y:y+h,x:x+w]|=coverage>0
        facts[index]['changed_px']=count;changed+=count
    return out,{'reason':None if changed else 'no_eligible_local_sclera_correction',
                'geom_px':sum(f['geom_px'] for f in facts),'gated_px':changed,'eyes':facts,
                'support':'inward-eye-minus-iris-corners-and-source-photometric-gates-not-segmentation',
                'native_solver':'rust-sclera-purify-v1','requested':amount}
