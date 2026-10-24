# SPDX-License-Identifier: GPL-3.0-or-later
"""Outermost mid-face pullback, AFTER existing contour/slim/size/lower face.

AUTHORED / UNRUN. No new sampler, no reorder/replacement of existing controls.
The exact legacy mouth slot 3 and every prior field are shared by identity.
Previously relocated points can enter this operator's feather; source-landmark
plateau guarantees do not imply global invariance after arbitrary prior edits.
"""
from dataclasses import dataclass

import numpy as np

from . import mid_face_state as S, people_state as P
from .people_geometry import FaceGeometry


@dataclass(frozen=True)
class MidFace(FaceGeometry):
    prefix: object
    protected_boxes: tuple

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Composed mid face needs finite Nx2 coordinates')
        result = np.empty_like(points)
        h, w = self.shape
        for start in range(0, len(points), 65536):
            q = points[start:start + 65536]
            if not np.isfinite(q).all():
                raise ValueError('Composed mid face needs finite Nx2 coordinates')
            mid = self.fields[-1].evaluate(q)
            if (type(mid) is not np.ndarray or mid.dtype != np.float64
                    or mid.shape != q.shape or not np.isfinite(mid).all()):
                raise ValueError('Composed mid face received an invalid mid-face pullback')
            at = q - mid
            prior, baseline = self.prefix.evaluate(at), self.prefix.evaluate(q)
            if any(type(value) is not np.ndarray or value.shape != q.shape or not np.isfinite(value).all()
                   for value in (at, prior, baseline)):
                raise ValueError('Composed mid face received an invalid prefix pullback')
            total = mid + prior
            if not np.isfinite(total).all():
                raise ValueError('Composed mid face produced a nonfinite source pullback')
            # Output, intermediate and genuine-source positions all matter.
            # Cancellation and relocated prefix queries cannot evade guards.
            moving = np.any(mid != 0., axis=1) | np.any(total != baseline, axis=1)
            if np.any(moving):
                for coordinates in (q[moving], at[moving], (q - total)[moving]):
                    if np.any(coordinates < 1.) or np.any(coordinates > [w - 2, h - 2]):
                        raise ValueError('Composed mid face footprint is outside the genuine source margin')
                    low, high = coordinates.min(0), coordinates.max(0)
                    for normalized in self.protected_boxes:
                        box = np.asarray(normalized) * [w - 1, h - 1, w - 1, h - 1]
                        if np.any(high < box[:2] - 1.) or np.any(low > box[2:] + 1.):
                            continue
                        if np.any(np.all((coordinates >= box[:2] - 1.) & (coordinates <= box[2:] + 1.), axis=1)):
                            raise ValueError('Composed mid face touches another retained face')
            result[start:start + len(q)] = total
        # No new claim for wholly unchanged legacy footprints. The existing
        # joint-map owner continues checking the complete all-face deformation.
        return result

    def resident_bytes(self):
        # Prior wrappers' guard metadata survives; shared fields count once.
        return (self.prefix.resident_bytes() + self.fields[-1].resident_bytes()
                + 128 * len(self.protected_boxes) + 256)


def append(field, state, face_ref, analysis, source, recipe):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return field, None
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled']:
        raise ValueError('Mid face requires its exact enabled canonical source face')
    from .mid_face_runtime import MidFaceField, build
    if (type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3
            or not isinstance(field, FaceGeometry) or field.face_instance_id != ref['face_instance_id']
            or field.shape != tuple(source.shape[:2]) or len(field.fields) not in (4, 5, 6, 7)
            or isinstance(field, MidFace) or any(isinstance(part, MidFaceField) for part in field.fields)):
        raise ValueError('Mid face cannot reuse foreign or already-mid-face geometry')
    from .people_render_runtime import verify_analysis
    landmarks = verify_analysis(face, analysis, source.shape[:2])
    # Unresolved and disabled retained same-source neighbors remain protected.
    boxes = tuple(tuple(other['box']) for key, other in state['faces'].items()
                  if key != ref['face_instance_id'] and other['asset_sha256'] == ref['asset_sha256'])
    mid = build(landmarks, recipe, source, analysis['excluded'],
                backend=face['evidence']['backend'], analysis=analysis, protected_boxes=boxes)
    if mid is None or mid.state is None:
        raise ValueError('Requested mid face produced no admitted geometry; not silently skipped')
    facts = mid.facts
    if any(fact.get('requested') and not fact.get('applied') for fact in facts.values()):
        raise ValueError('Requested mid face was refused; no partial result is published')
    return MidFace(field.face_instance_id, field.shape, field.automatic,
                   (*field.fields, mid), field, boxes), facts
