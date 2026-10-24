# SPDX-License-Identifier: GPL-3.0-or-later
"""Outermost below-lip chin-length pullback, AFTER chin_shape and predecessors.

AUTHORED / UNRUN. No sampler, legacy deformation changes or prior-class edits.
Every prior field and exact legacy mouth slot 3 survives by identity. Active
legacy small_chin and active new chin_length refuse together; neutral new
chin_length leaves the complete old field untouched, without migrating it.
"""
from dataclasses import dataclass

import numpy as np

from . import chin_length_state as S, people_state as P
from .people_geometry import FaceGeometry


@dataclass(frozen=True)
class ChinLength(FaceGeometry):
    prefix: object
    protected_boxes: tuple

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Composed chin length needs finite Nx2 coordinates')
        result = np.empty_like(points)
        h, w = self.shape
        for start in range(0, len(points), 65536):
            q = points[start:start + 65536]
            if not np.isfinite(q).all():
                raise ValueError('Composed chin length needs finite Nx2 coordinates')
            chin = self.fields[-1].evaluate(q)
            if (type(chin) is not np.ndarray or chin.dtype != np.float64
                    or chin.shape != q.shape or not np.isfinite(chin).all()):
                raise ValueError('Composed chin length received an invalid chin pullback')
            at = q - chin
            prior, baseline = self.prefix.evaluate(at), self.prefix.evaluate(q)
            if any(type(value) is not np.ndarray or value.dtype != np.float64
                   or value.shape != q.shape or not np.isfinite(value).all()
                   for value in (at, prior, baseline)):
                raise ValueError('Composed chin length received an invalid prefix pullback')
            total = chin + prior
            if not np.isfinite(total).all():
                raise ValueError('Composed chin length produced a nonfinite source pullback')
            moving = np.any(chin != 0., axis=1) | np.any(total != baseline, axis=1)
            if np.any(moving):
                # Cancellation cannot hide a moved output, intermediate or
                # actual source query. All three bilinear footprints count.
                for coordinates in (q[moving], at[moving], (q - total)[moving]):
                    if np.any(coordinates < 1.) or np.any(coordinates > [w - 2, h - 2]):
                        raise ValueError('Composed chin length footprint is outside the genuine source margin')
                    low, high = coordinates.min(0), coordinates.max(0)
                    for normalized in self.protected_boxes:
                        box = np.asarray(normalized) * [w - 1, h - 1, w - 1, h - 1]
                        if np.any(high < box[:2] - 1.) or np.any(low > box[2:] + 1.):
                            continue
                        if np.any(np.all((coordinates >= box[:2] - 1.) & (coordinates <= box[2:] + 1.), axis=1)):
                            raise ValueError('Composed chin length touches another retained face')
            result[start:start + len(q)] = total
        return result

    def resident_bytes(self):
        return (self.prefix.resident_bytes() + self.fields[-1].resident_bytes()
                + 128 * len(self.protected_boxes) + 256)


def append(field, state, face_ref, analysis, source, recipe, *, legacy_amount):
    recipe = S.check(recipe)
    if not S.active(recipe):
        # In particular, do not clear or reinterpret an old small_chin field.
        return field, None
    S.check_coexistence(recipe, legacy_amount)
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled']:
        raise ValueError('Chin length requires its exact enabled canonical source face')
    from .chin_length_runtime import ChinLengthField, build
    if (type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3
            or not isinstance(field, FaceGeometry) or field.face_instance_id != ref['face_instance_id']
            or field.shape != tuple(source.shape[:2]) or len(field.fields) not in (4, 5, 6, 7, 8, 9)
            or isinstance(field, ChinLength) or any(isinstance(part, ChinLengthField) for part in field.fields)):
        raise ValueError('Chin length cannot reuse foreign or already-chin-length geometry')
    from .people_render_runtime import verify_analysis
    landmarks = verify_analysis(face, analysis, source.shape[:2])
    boxes = tuple(tuple(other['box']) for key, other in state['faces'].items()
                  if key != ref['face_instance_id'] and other['asset_sha256'] == ref['asset_sha256'])
    chin = build(landmarks, recipe, source, analysis['excluded'],
                 backend=face['evidence']['backend'], analysis=analysis, protected_boxes=boxes)
    if chin is None or chin.state is None:
        raise ValueError('Requested chin length produced no admitted geometry; not silently skipped')
    facts = chin.facts
    if any(fact.get('requested') and not fact.get('applied') for fact in facts.values()):
        raise ValueError('Requested chin length was refused; no partial result is published')
    return ChinLength(field.face_instance_id, field.shape, field.automatic,
                      (*field.fields, chin), field, boxes), facts
