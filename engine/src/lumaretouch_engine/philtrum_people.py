# SPDX-License-Identifier: GPL-3.0-or-later
"""Outermost philtrum pullback AFTER chin_length and all prior geometry.

AUTHORED / UNRUN. Prefix lengths 4..10 preserve every prior field and exact
legacy mouth slot 3 by identity. There is no conflicting legacy equivalent to
clear, no sampler, no reordering and no migration. Retained-source nose/lip
guarantees are not global invariance promises after arbitrary earlier edits.
"""
from dataclasses import dataclass

import numpy as np

from . import philtrum_state as S, people_state as P
from .people_geometry import FaceGeometry


@dataclass(frozen=True)
class Philtrum(FaceGeometry):
    prefix: object
    protected_boxes: tuple

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Composed philtrum needs finite Nx2 coordinates')
        result = np.empty_like(points)
        h, w = self.shape
        for start in range(0, len(points), 65536):
            q = points[start:start + 65536]
            if not np.isfinite(q).all():
                raise ValueError('Composed philtrum needs finite Nx2 coordinates')
            gap = self.fields[-1].evaluate(q)
            if (type(gap) is not np.ndarray or gap.dtype != np.float64
                    or gap.shape != q.shape or not np.isfinite(gap).all()):
                raise ValueError('Composed philtrum received an invalid philtrum pullback')
            at = q - gap
            prior, baseline = self.prefix.evaluate(at), self.prefix.evaluate(q)
            if any(type(value) is not np.ndarray or value.dtype != np.float64
                   or value.shape != q.shape or not np.isfinite(value).all()
                   for value in (at, prior, baseline)):
                raise ValueError('Composed philtrum received an invalid prefix pullback')
            total = gap + prior
            if not np.isfinite(total).all():
                raise ValueError('Composed philtrum produced a nonfinite source pullback')
            moving = np.any(gap != 0., axis=1) | np.any(total != baseline, axis=1)
            if np.any(moving):
                # Cancellation cannot hide output, intermediate or actual source
                # footprints. The existing owner keeps its whole-joint-map guard.
                for coordinates in (q[moving], at[moving], (q - total)[moving]):
                    if np.any(coordinates < 1.) or np.any(coordinates > [w - 2, h - 2]):
                        raise ValueError('Composed philtrum footprint is outside the genuine source margin')
                    low, high = coordinates.min(0), coordinates.max(0)
                    for normalized in self.protected_boxes:
                        box = np.asarray(normalized) * [w - 1, h - 1, w - 1, h - 1]
                        if np.any(high < box[:2] - 1.) or np.any(low > box[2:] + 1.):
                            continue
                        if np.any(np.all((coordinates >= box[:2] - 1.) & (coordinates <= box[2:] + 1.), axis=1)):
                            raise ValueError('Composed philtrum touches another retained face')
            result[start:start + len(q)] = total
        return result

    def resident_bytes(self):
        return (self.prefix.resident_bytes() + self.fields[-1].resident_bytes()
                + 128 * len(self.protected_boxes) + 256)


def append(field, state, face_ref, analysis, source, recipe):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return field, None
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled']:
        raise ValueError('Philtrum requires its exact enabled canonical source face')
    from .philtrum_runtime import PhiltrumField, build
    if (type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3
            or not isinstance(field, FaceGeometry) or field.face_instance_id != ref['face_instance_id']
            or field.shape != tuple(source.shape[:2]) or len(field.fields) not in (4, 5, 6, 7, 8, 9, 10)
            or isinstance(field, Philtrum) or any(isinstance(part, PhiltrumField) for part in field.fields)):
        raise ValueError('Philtrum cannot reuse foreign or already-philtrum geometry')
    from .people_render_runtime import verify_analysis
    landmarks = verify_analysis(face, analysis, source.shape[:2])
    # All retained same-source neighbors count, including disabled/unresolved.
    boxes = tuple(tuple(other['box']) for key, other in state['faces'].items()
                  if key != ref['face_instance_id'] and other['asset_sha256'] == ref['asset_sha256'])
    gap = build(landmarks, recipe, source, analysis['excluded'],
                backend=face['evidence']['backend'], analysis=analysis, protected_boxes=boxes)
    if gap is None or gap.state is None:
        raise ValueError('Requested philtrum produced no admitted geometry; not silently skipped')
    facts = gap.facts
    if any(fact.get('requested') and not fact.get('applied') for fact in facts.values()):
        raise ValueError('Requested philtrum was refused; no partial result is published')
    return Philtrum(field.face_instance_id, field.shape, field.automatic,
                    (*field.fields, gap), field, boxes), facts
