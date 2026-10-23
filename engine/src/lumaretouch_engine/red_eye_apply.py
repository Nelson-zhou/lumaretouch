"""Source-owned flash-red correction, not an iris/pupil segmentation model.

The inward eye aperture and central iris disk bound a conservative candidate
region. The Rust solver independently tests actual RGB red dominance. No pupil
is reconstructed and no claimed eye colour is inferred from another person.
"""
import numpy as np

KEYS = ('red_eye',)


def active(amounts):
    return amounts.get('red_eye', 0) > 0


def capability():
    from .red_eye_native import available
    ready = available()
    return {'red_eye_available': ready, 'red_eye_reason': None if ready else
            '祛红眼 Rust 核心未安装或 ABI 不匹配；不会以祛血丝替代'}


def support(landmarks, height, width):
    # Delayed import avoids the enhance -> red_eye_apply -> enhance cycle.
    from .ops import enhance as H
    if (min(height,width) < 1 or max(height,width) > 65536 or height*width > 64_000_000):
        raise ValueError('Red-eye support exceeds the source canvas budget; no proxy fallback')
    lm = H._landmark_pixels(landmarks, height, width)
    coverage = np.zeros((height, width), np.float32)
    facts = []
    specs = ((H.EYE_RING_LEFT, H.IRIS_LEFT, H.IRIS_RIM_LEFT),
             (H.EYE_RING_RIGHT, H.IRIS_RIGHT, H.IRIS_RIM_RIGHT))
    for ring, iris, rim in specs:
        centre = lm[iris]
        radii = np.linalg.norm(lm[list(rim)] - centre, axis=1)
        radius = float(radii.mean())
        vertices = lm[list(ring)]
        reason = H._star_ok(vertices, *centre)
        # A measured iris centre is not a pupil label. Refuse tiny or severely
        # foreshortened measurements rather than expand into an eyelid/skin.
        if radius < 2 or radii.min() < .55 * radii.max():
            reason = 'tiny_or_foreshortened_iris'
        if reason is not None:
            facts.append({'reason': reason, 'geom_px': 0})
            continue
        x0, y0 = np.maximum(np.floor(centre-.65*radius), 0).astype(int)
        x1, y1 = np.minimum(np.ceil(centre+.65*radius)+1, [width,height]).astype(int)
        if x1 <= x0 or y1 <= y0:
            facts.append({'reason': 'iris_outside_canvas', 'geom_px': 0})
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        xs, ys = xx+.5, yy+.5
        inward = centre + .88 * (vertices - centre)
        aperture = H._star_weight(xs, ys, *centre, inward, 0)
        distance = np.hypot(xs-centre[0], ys-centre[1]) / radius
        # Exact zero outside .65 measured iris radius. The narrow central
        # candidate deliberately leaves large/off-axis flash pupils incomplete.
        t = np.clip((distance-.40)/.25, 0, 1)
        disk = 1 - t*t*(3-2*t)
        local = aperture * disk
        count = int(np.count_nonzero(local > 0))
        if count < 4:
            facts.append({'reason': 'insufficient_central_iris_samples', 'geom_px': count})
            continue
        coverage[y0:y1,x0:x1] = np.maximum(coverage[y0:y1,x0:x1], local.astype(np.float32))
        facts.append({'reason': None, 'geom_px': count, 'iris_radius_px': radius})
    if not np.any(coverage):
        raise ValueError('祛红眼没有可信的中央虹膜几何支持；未生成瞳孔或替代蒙版')
    return coverage, facts


def correct(source, landmarks, amount, *, cancelled=lambda: False):
    from .red_eye_native import apply
    if not amount:
        return source, {'reason': 'disabled', 'geom_px': 0, 'gated_px': 0}
    if cancelled():
        raise InterruptedError('Red-eye correction cancelled before source preparation')
    rgb = np.asarray(source)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or not np.isfinite(rgb).all() or np.any((rgb < 0) | (rgb > 1)):
        raise ValueError('Red-eye correction requires finite SDR RGB; no alpha/HDR clipping')
    coverage, eyes = support(landmarks, *rgb.shape[:2])
    rows = np.flatnonzero(np.any(coverage > 0, axis=1))
    cols = np.flatnonzero(np.any(coverage > 0, axis=0))
    y0,y1 = int(rows[0]),int(rows[-1])+1
    x0,x1 = int(cols[0]),int(cols[-1])+1
    original = rgb[y0:y1,x0:x1]
    frozen = np.ascontiguousarray(original, dtype=np.float32)
    corrected = apply(frozen, np.ascontiguousarray(coverage[y0:y1,x0:x1]), amount, cancelled=cancelled)
    delta = corrected - frozen
    count = int(np.count_nonzero(np.any(delta != 0, axis=2)))
    out = rgb.copy()
    out[y0:y1,x0:x1] = np.where(delta != 0, original + delta.astype(rgb.dtype, copy=False), original)
    return out, {'reason': None if count else 'no_red_dominant_central_iris_pixels',
                 'geom_px': int(np.count_nonzero(coverage)), 'gated_px': count,
                 'eyes': eyes, 'support': 'inward-central-iris-geometry-and-RGB-not-pupil-segmentation',
                 'native_solver': 'rust-red-eye-v1', 'requested': amount}
